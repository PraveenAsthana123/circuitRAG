"""Command-approval orchestrator — wires policy + cache + batcher.

The single entry point for the operator pain pattern:

  evaluate_command(cmd) → EvaluatedCommand:
    decision    — terminal action (AUTO_APPROVE / ASK / BATCHED / BLOCK)
    cache_hit   — whether session cache promoted ASK_ONCE → AUTO_APPROVE
    batched     — whether ASK_ONCE was enqueued for batch approval
    matched     — pattern + bucket from command_policy
    ttl_left_s  — when this approval expires (cache hits only)

Decision flow:

  classify(cmd) →
    BLOCK         → return BLOCK (cache cannot promote, batch cannot enqueue)
    ALWAYS_ASK    → return ASK   (cache cannot promote)
    ASK_ONCE      →
      cache hit?  → return AUTO_APPROVE (cache_hit=True)
      cache miss? →
        batch enabled? → enqueue + return BATCHED
        batch disabled? → return ASK
    AUTO_APPROVE  → return AUTO_APPROVE (always; pattern is the contract)

This module is the operator-pain-fix in one place. Drill-locked — the
complete decision matrix has 12+ cells and each is asserted by
drill_approval_batching.py with ≥3 negative invariants.

Composes with:
  - command_policy.classify        — input classifier
  - session_cache.SessionCache     — TTL cache for ASK_ONCE
  - batcher.ApprovalBatcher        — medium-risk batch queue
  - approval_agent.agent.decide()  — orthogonal task-level approver
  - paperclip_manager.aggregate_approval_engine — operator dashboard
  - CLAUDE.md §42 + §38 + §52 row 4 (operator-API gap closure)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .batcher import DEFAULT_FLUSH_INTERVAL_SECONDS, ApprovalBatcher
from .command_policy import (
    ALWAYS_ASK,
    ASK_ONCE,
    AUTO_APPROVE,
    BLOCK,
    CommandDecision,
    classify,
    load_policy,
)
from .session_cache import DEFAULT_TTL_SECONDS, SessionCache

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_PATH = REPO_ROOT / ".loop" / "command_approval_audit.jsonl"

# Terminal outcomes — these are what the orchestrator returns AFTER
# applying cache/batch logic. Distinct from CommandDecision.decision
# (which is the raw classifier output).
TERMINAL_AUTO = "AUTO_APPROVE"
TERMINAL_ASK = "ASK"
TERMINAL_BATCHED = "BATCHED"
TERMINAL_BLOCK = "BLOCK"


@dataclass
class EvaluatedCommand:
    command: str
    terminal: str  # TERMINAL_AUTO / TERMINAL_ASK / TERMINAL_BATCHED / TERMINAL_BLOCK
    raw_decision: str  # CommandDecision.decision (AUTO/ASK_ONCE/ALWAYS_ASK/BLOCK)
    risk: str  # low | medium | high | critical
    cache_hit: bool
    batched: bool
    matched_pattern: str | None
    matched_bucket: str | None
    reason: str
    ttl_left_s: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CommandApprovalOrchestrator:
    """Operator-facing API. Single entry point for command evaluation."""

    def __init__(
        self,
        *,
        policy_path: Path | str | None = None,
        cache: SessionCache | None = None,
        batcher: ApprovalBatcher | None = None,
        audit_path: Path | str | None = None,
    ) -> None:
        self._policy = load_policy(policy_path)
        # Cache TTL inherits from YAML policy unless explicitly passed
        cache_ttl = self._policy.session_ttl_minutes * 60
        self._cache = cache or SessionCache(ttl_seconds=cache_ttl)
        # Batcher interval inherits from YAML policy
        batch_interval = self._policy.batch_interval_minutes * 60
        self._batcher = batcher or ApprovalBatcher(
            flush_interval_seconds=batch_interval,
        )
        self._audit_path = Path(audit_path) if audit_path else DEFAULT_AUDIT_PATH
        self._batch_enabled = self._policy.batch_medium_risk

    @property
    def cache(self) -> SessionCache:
        return self._cache

    @property
    def batcher(self) -> ApprovalBatcher:
        return self._batcher

    @property
    def policy_version(self) -> str:
        return self._policy.version

    def evaluate(self, command: str) -> EvaluatedCommand:
        """The single decision API. Pure-ish: writes to audit + cache/batch."""
        raw = classify(command, policy=self._policy)
        terminal, cache_hit, batched, ttl_left = self._route(raw, command)
        evaluated = EvaluatedCommand(
            command=command,
            terminal=terminal,
            raw_decision=raw.decision,
            risk=raw.risk,
            cache_hit=cache_hit,
            batched=batched,
            matched_pattern=raw.matched_pattern,
            matched_bucket=raw.matched_bucket,
            reason=raw.reason,
            ttl_left_s=ttl_left,
        )
        self._audit(evaluated)
        return evaluated

    def _route(
        self,
        raw: CommandDecision,
        command: str,
    ) -> tuple[str, bool, bool, int | None]:
        """Apply the cache + batch logic on top of the raw classifier.

        Returns (terminal, cache_hit, batched, ttl_left_s).

        Cache + batch ONLY apply to ASK_ONCE. Drill verifies BLOCK and
        ALWAYS_ASK never touch the cache.
        """
        if raw.decision == BLOCK:
            return TERMINAL_BLOCK, False, False, None
        if raw.decision == ALWAYS_ASK:
            return TERMINAL_ASK, False, False, None
        if raw.decision == AUTO_APPROVE:
            return TERMINAL_AUTO, False, False, None
        if raw.decision == ASK_ONCE:
            entry = self._cache.lookup(raw.matched_pattern)
            if entry is not None:
                ttl_left = max(0, int(entry.expires_at - time.time()))
                return TERMINAL_AUTO, True, False, ttl_left
            if self._batch_enabled and raw.matched_pattern:
                self._batcher.enqueue(
                    pattern=raw.matched_pattern,
                    command=command,
                    decision=raw.decision,
                    risk=raw.risk,
                )
                return TERMINAL_BATCHED, False, True, None
            return TERMINAL_ASK, False, False, None
        # Defensive: unknown decision falls through to ASK
        return TERMINAL_ASK, False, False, None

    def approve_pattern(self, pattern: str, *, approved_by: str = "operator") -> int:
        """Operator API — approve one pattern session-wide.

        Returns the new TTL (seconds). Used after the operator clicks
        "Approve Similar for 30 min" on the UI.
        """
        entry = self._cache.store(pattern, approved_by=approved_by)
        return int(entry.expires_at - time.time())

    def approve_batch(
        self,
        *,
        approved_by: str = "operator",
        force: bool = False,
    ) -> dict[str, Any]:
        """Operator API — flush the batch queue, store all patterns into
        cache. Returns flush summary.

        If ``force=True`` flushes regardless of interval (the "approve
        all pending similar now" button). If False, only flushes when
        the timer is due.
        """
        entries = (
            self._batcher.flush_now() if force else self._batcher.flush_due()
        )
        if not entries:
            return {"flushed": 0, "patterns_approved": 0, "patterns": []}
        unique_patterns = {e.pattern for e in entries}
        for pat in unique_patterns:
            self._cache.store(pat, approved_by=approved_by)
        return {
            "flushed": len(entries),
            "patterns_approved": len(unique_patterns),
            "patterns": sorted(unique_patterns),
        }

    def reject_pattern(self, pattern: str) -> bool:
        """Operator API — invalidate cache for a pattern."""
        return self._cache.invalidate(pattern)

    def stats(self) -> dict[str, Any]:
        """Operator-readable summary. Surfaced by paperclip aggregator."""
        return {
            "policy_version": self._policy.version,
            "policy_path": str(self._policy.raw_path),
            "policy_default": self._policy.default,
            "patterns": {
                "auto_approve": len(self._policy.auto_approve_patterns),
                "ask_once": len(self._policy.ask_once_patterns),
                "always_ask": len(self._policy.always_ask_patterns),
                "block": len(self._policy.block_patterns),
            },
            "cache": self._cache.stats(),
            "batch": self._batcher.stats(),
            "audit_path": str(self._audit_path),
        }

    def _audit(self, evaluated: EvaluatedCommand) -> None:
        """Append one JSON line per evaluation. Atomic enough — single
        line append with flush. The drill verifies the audit row shape.
        """
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": time.time(),
                "command": evaluated.command[:200],  # cap so audit doesn't blow
                "terminal": evaluated.terminal,
                "raw_decision": evaluated.raw_decision,
                "risk": evaluated.risk,
                "cache_hit": evaluated.cache_hit,
                "batched": evaluated.batched,
                "matched_pattern": evaluated.matched_pattern,
                "matched_bucket": evaluated.matched_bucket,
                "ttl_left_s": evaluated.ttl_left_s,
            }
            with self._audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception as exc:  # noqa: BLE001
            log.warning("audit_write_failed path=%s err=%s",
                        self._audit_path, exc)


__all__ = [
    "CommandApprovalOrchestrator",
    "EvaluatedCommand",
    "TERMINAL_AUTO", "TERMINAL_ASK", "TERMINAL_BATCHED", "TERMINAL_BLOCK",
    "DEFAULT_TTL_SECONDS", "DEFAULT_FLUSH_INTERVAL_SECONDS",
]
