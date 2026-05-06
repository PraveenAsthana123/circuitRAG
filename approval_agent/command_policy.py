"""Command-pattern policy classifier — reads configs/approval_policy.yaml.

Per CLAUDE.md §42 + §38 + §52 row 4 (operator-API gap closure).
This module is the *command-pattern* counterpart to ``agent.decide()``:

  agent.decide()       — task-lifecycle approvals (gates: tests, governance,
                         reviewer, confidence, action allowlist) — used by
                         ops_worker between Ollama proposal + Claude review

  command_policy.classify(cmd) — shell-command-pattern approvals (regex
                         allowlist / ask_once / always_ask / block) — used
                         by the operator approval orchestrator BEFORE a
                         shell command actually runs

The two are orthogonal: a task-lifecycle decision can route through the
command-policy when its action is a shell command, but neither replaces
the other. agent.decide() answers *should this work be auto-approved?*;
command_policy.classify() answers *should this command pattern auto-run?*

Drill-locked: drill_approval_batching.py enforces the precedence order
AND the negative invariants (block-cannot-be-cached, always-ask-cannot-
be-cached, denylist-pattern-precedence-over-allowlist).

Read-only by §42 contract. NEVER mutates the YAML file. NEVER caches
to disk. Cache lives in approval_agent.session_cache (separate module
so the lookup remains pure).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "configs" / "approval_policy.yaml"

# Decision constants — lowercase to match agent.decide() string convention
# but kept distinct here because the semantics are different (command
# patterns vs task lifecycles).
AUTO_APPROVE = "AUTO_APPROVE"
ASK_ONCE = "ASK_ONCE"
ALWAYS_ASK = "ALWAYS_ASK"
BLOCK = "BLOCK"

VALID_DECISIONS = (AUTO_APPROVE, ASK_ONCE, ALWAYS_ASK, BLOCK)

# Risk → bucket mapping. Used by paperclip_manager.aggregate_approval_engine
# to roll up by risk class. The mapping is here (not in YAML) because risk
# is derived from the bucket, not declared per-pattern — keeps the YAML
# tight.
DECISION_TO_RISK: dict[str, str] = {
    AUTO_APPROVE: "low",
    ASK_ONCE: "medium",
    ALWAYS_ASK: "high",
    BLOCK: "critical",
}


@dataclass(frozen=True)
class CommandDecision:
    """Result of classifying a single command. Immutable, audit-ready."""

    decision: str  # one of VALID_DECISIONS
    risk: str  # low | medium | high | critical
    matched_pattern: str | None  # the regex that matched, if any
    matched_bucket: str | None  # auto_approve | ask_once | always_ask | block
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _CompiledPolicy:
    """Compiled view of the YAML policy. Cached at module load time."""

    version: str
    default: str
    session_ttl_minutes: int
    batch_medium_risk: bool
    batch_interval_minutes: int
    block_patterns: list[tuple[str, re.Pattern[str]]]
    always_ask_patterns: list[tuple[str, re.Pattern[str]]]
    ask_once_patterns: list[tuple[str, re.Pattern[str]]]
    auto_approve_patterns: list[tuple[str, re.Pattern[str]]]
    raw_path: Path


def _load_yaml(path: Path) -> dict[str, Any]:
    """Tiny YAML loader.

    Prefers PyYAML if available (already a dependency in this repo).
    Falls back to a minimal hand-rolled parser for the specific shape
    this file uses — flat scalars + named lists of strings — so the
    policy keeps working even if PyYAML is uninstalled. The fallback
    is intentionally restricted: any feature beyond the documented
    shape (anchors, multi-line strings, nested maps) raises and the
    caller falls back to default policy.
    """
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        log.warning("pyyaml_missing — using minimal_yaml_fallback for policy load")
        return _minimal_yaml_parse(text)


def _minimal_yaml_parse(text: str) -> dict[str, Any]:
    """Fallback parser. Handles only:
    - top-level scalars (key: value)
    - top-level lists of quoted strings (key:\n  - "value")
    - # comments
    """
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current_list_key is None:
                continue
            v = line[4:].strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1].replace('\\\\', '\\').replace('\\"', '"')
            elif v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
            result[current_list_key].append(v)
        elif ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                # opens a new list
                current_list_key = key
                result[key] = []
            else:
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                if val.lower() in {"true", "false"}:
                    result[key] = val.lower() == "true"
                else:
                    try:
                        result[key] = int(val)
                    except ValueError:
                        result[key] = val
                current_list_key = None
    return result


def _compile_patterns(patterns: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for pat in patterns:
        try:
            compiled.append((pat, re.compile(pat)))
        except re.error as exc:
            log.warning("invalid_regex_pattern pat=%s err=%s — skipping", pat, exc)
    return compiled


def load_policy(path: Path | str | None = None) -> _CompiledPolicy:
    """Load + compile the policy. Idempotent.

    Returns a frozen-ish compiled view. Callers should re-call to pick up
    file changes; we don't auto-watch (operator decision territory).
    """
    p = Path(path) if path else DEFAULT_POLICY_PATH
    if not p.exists():
        log.warning("approval_policy_missing path=%s — using safe defaults", p)
        return _safe_default_policy(p)
    try:
        data = _load_yaml(p)
    except Exception as exc:  # noqa: BLE001 — never break on bad policy
        log.warning("approval_policy_parse_failed path=%s err=%s — using safe defaults", p, exc)
        return _safe_default_policy(p)

    return _CompiledPolicy(
        version=str(data.get("version", "v1")),
        default=str(data.get("default", ASK_ONCE)).upper().replace("-", "_"),
        session_ttl_minutes=int(data.get("session_ttl_minutes", 30)),
        batch_medium_risk=bool(data.get("batch_medium_risk", True)),
        batch_interval_minutes=int(data.get("batch_interval_minutes", 15)),
        block_patterns=_compile_patterns(list(data.get("block", []))),
        always_ask_patterns=_compile_patterns(list(data.get("always_ask", []))),
        ask_once_patterns=_compile_patterns(list(data.get("ask_once", []))),
        auto_approve_patterns=_compile_patterns(list(data.get("auto_approve", []))),
        raw_path=p,
    )


def _safe_default_policy(path: Path) -> _CompiledPolicy:
    """When the YAML is missing/broken, use a hard-coded safe default
    that prefers ASK_ONCE over AUTO_APPROVE — the operator can never be
    silently auto-approved into something dangerous because the policy
    file vanished. Drill enforces this.
    """
    return _CompiledPolicy(
        version="safe-default",
        default=ASK_ONCE,
        session_ttl_minutes=30,
        batch_medium_risk=True,
        batch_interval_minutes=15,
        block_patterns=_compile_patterns([
            r"^rm -rf /(\s|$)",
            r"curl .*\|\s*sh",
            r"wget .*\|\s*sh",
        ]),
        always_ask_patterns=_compile_patterns([
            r"^sudo\s",
            r"^rm\s",
            r"^chmod\s",
            r"^chown\s",
            r"\bprod\b",
            r"secret",
            r"password",
        ]),
        ask_once_patterns=[],
        auto_approve_patterns=[],
        raw_path=path,
    )


def classify(
    command: str,
    *,
    policy: _CompiledPolicy | None = None,
) -> CommandDecision:
    """Classify a single command pattern. Pure function.

    Decision precedence (most-restrictive wins):
      1. block         (any match → BLOCK; cannot be overridden)
      2. always_ask    (any match → ALWAYS_ASK; cache cannot promote)
      3. ask_once      (any match → ASK_ONCE; eligible for cache)
      4. auto_approve  (any match → AUTO_APPROVE)
      5. (none)        → policy.default

    Multiple-bucket overlap: if a command matches BOTH always_ask and
    auto_approve (operator misconfiguration), always_ask wins. Drill
    locks this — operator misconfiguration cannot accidentally widen
    the auto-approve surface.
    """
    if policy is None:
        policy = load_policy()
    cmd = command.strip()
    if not cmd:
        return CommandDecision(
            decision=ALWAYS_ASK,
            risk="high",
            matched_pattern=None,
            matched_bucket=None,
            reason="empty command — default to ALWAYS_ASK as a safety floor",
        )

    # 1. block
    for pat, rx in policy.block_patterns:
        if rx.search(cmd):
            return CommandDecision(
                decision=BLOCK,
                risk=DECISION_TO_RISK[BLOCK],
                matched_pattern=pat,
                matched_bucket="block",
                reason=f"command matches BLOCK pattern {pat!r}",
            )

    # 2. always_ask
    for pat, rx in policy.always_ask_patterns:
        if rx.search(cmd):
            return CommandDecision(
                decision=ALWAYS_ASK,
                risk=DECISION_TO_RISK[ALWAYS_ASK],
                matched_pattern=pat,
                matched_bucket="always_ask",
                reason=f"command matches ALWAYS_ASK pattern {pat!r}",
            )

    # 3. ask_once
    for pat, rx in policy.ask_once_patterns:
        if rx.search(cmd):
            return CommandDecision(
                decision=ASK_ONCE,
                risk=DECISION_TO_RISK[ASK_ONCE],
                matched_pattern=pat,
                matched_bucket="ask_once",
                reason=f"command matches ASK_ONCE pattern {pat!r}",
            )

    # 4. auto_approve
    for pat, rx in policy.auto_approve_patterns:
        if rx.search(cmd):
            return CommandDecision(
                decision=AUTO_APPROVE,
                risk=DECISION_TO_RISK[AUTO_APPROVE],
                matched_pattern=pat,
                matched_bucket="auto_approve",
                reason=f"command matches AUTO_APPROVE pattern {pat!r}",
            )

    # 5. default
    return CommandDecision(
        decision=policy.default,
        risk=DECISION_TO_RISK.get(policy.default, "medium"),
        matched_pattern=None,
        matched_bucket=None,
        reason=f"no pattern matched — applying policy default {policy.default!r}",
    )


__all__ = [
    "AUTO_APPROVE", "ASK_ONCE", "ALWAYS_ASK", "BLOCK",
    "VALID_DECISIONS", "DECISION_TO_RISK",
    "CommandDecision", "load_policy", "classify",
]
