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
from .session_token import SessionToken, SessionTokenStore

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
    # v2 — session-token attribution. operator_id is set when the
    # request carries a valid SessionToken; None otherwise (anonymous
    # backwards-compat path). token_status enum:
    #   "valid"     — accepted; operator_id propagated
    #   "expired"   — token signature OK but past expires_at
    #   "revoked"   — token_id in revocation set
    #   "invalid"   — signature fails / malformed / no secret
    #   "anonymous" — no token presented (default; not an error)
    operator_id: str | None = None
    token_status: str = "anonymous"  # noqa: S105 - status enum value, not a credential
    metadata: dict[str, Any] = field(default_factory=dict)


class CommandApprovalOrchestrator:
    """Operator-facing API. Single entry point for command evaluation."""

    def __init__(
        self,
        *,
        policy_path: Path | str | None = None,
        cache: SessionCache | None = None,
        batcher: ApprovalBatcher | None = None,
        token_store: SessionTokenStore | None = None,
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
        # v2 — session-token store (optional). When None, evaluate()
        # treats every request as anonymous (backwards-compat).
        self._token_store = token_store
        self._audit_path = Path(audit_path) if audit_path else DEFAULT_AUDIT_PATH
        self._batch_enabled = self._policy.batch_medium_risk

    @property
    def cache(self) -> SessionCache:
        return self._cache

    @property
    def batcher(self) -> ApprovalBatcher:
        return self._batcher

    @property
    def token_store(self) -> SessionTokenStore | None:
        return self._token_store

    @property
    def policy_version(self) -> str:
        return self._policy.version

    def _verify_token(self, session_token: str | None) -> tuple[SessionToken | None, str]:
        """Return (token_obj_or_None, status_string).

        Status enum:
            "anonymous" — no token presented; backwards-compat path
            "valid"     — token verified
            "expired"   — payload OK but past expires_at
            "revoked"   — token_id in revocation set
            "invalid"   — signature/shape failure or no secret
        """
        if not session_token:
            return None, "anonymous"
        if self._token_store is None:
            # No store configured but a token was presented — treat as
            # invalid rather than silently anonymous (operator misconfig
            # is a real failure mode worth surfacing).
            return None, "invalid"
        # Pre-decode the token_id prefix so we can distinguish revoked
        # vs invalid in the audit row. Validate() collapses both to None.
        prefix = session_token.split(".", 1)[0] if "." in session_token else None
        if prefix and self._token_store.is_revoked(prefix):
            return None, "revoked"
        # Distinguish expired from invalid: validate() returns None for
        # both, so we re-decode the payload to check expiry separately.
        valid = self._token_store.validate(session_token)
        if valid is not None:
            return valid, "valid"
        # Token is shape-valid but not validate-valid. Check if it's
        # an expiry case by re-decoding without expiry check.
        try:
            import base64 as _b64
            import json as _json
            parts = session_token.split(".")
            if len(parts) == 3:
                pad = "=" * ((4 - len(parts[1]) % 4) % 4)
                payload = _json.loads(_b64.urlsafe_b64decode(parts[1] + pad))
                if isinstance(payload, dict) and float(payload.get("expires_at", 0)) < time.time():
                    return None, "expired"
        except Exception as exc:  # noqa: BLE001
            log.debug("token_expiry_recheck_failed err=%s", exc)
        return None, "invalid"

    def evaluate(
        self,
        command: str,
        *,
        session_token: str | None = None,
    ) -> EvaluatedCommand:
        """The single decision API. Pure-ish: writes to audit + cache/batch.

        ``session_token`` is optional; when present, the orchestrator
        verifies it via the configured SessionTokenStore and tags the
        EvaluatedCommand with the operator_id. Without a token, the
        orchestrator behaves as before (anonymous backwards-compat).
        """
        token_obj, token_status = self._verify_token(session_token)
        operator_id = token_obj.operator_id if token_obj else None

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
            operator_id=operator_id,
            token_status=token_status,
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
                # v2 — session-token attribution
                "operator_id": evaluated.operator_id,
                "token_status": evaluated.token_status,
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
