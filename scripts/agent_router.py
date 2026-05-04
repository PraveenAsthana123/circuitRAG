#!/usr/bin/env python3
"""Agent Router Stage-1 — intent + risk classifier (conservative-default).

Per CLAUDE.md §47 (11-layer architecture, Layer 3) — sits BETWEEN
API Gateway and PolisAI. The user request flows:

    API Gateway → Agent Router → PolisAI → Council → ...

Stage-1 ships a HEURISTIC classifier (regex + keyword matching) so
the layer is present + drill-locked without first requiring an
LLM-backed classifier. Stage-2 swaps the heuristics for an Ollama
call (with PolisAI gate per the existing §47 pattern); the contract
stays the same — drill locks the contract, not the implementation.

Contract:

    classify(message, context=None)
      -> RouterDecision {
           intent: str               # "fix" | "explain" | "deploy" | ...
           risk:   "low" | "medium" | "high" | "unknown"
           recommended_actor:  str   # routes to a PolisAI rule
           recommended_tool:   str   # the policy-tool to evaluate
           confidence: float         # [0, 1]
           reasons: list[str]        # why this classification
         }

Conservative-default posture: anything that doesn't match a known
pattern → intent="unknown", risk="high", recommended_actor=
"operator:human", recommended_tool="human_review". This is the
§47.6 four-lens DevSecOps "deny-by-default" posture applied at the
classifier layer.

Stage-2 will wire:
  - Ollama-backed classifier (qwen2.5 with policy gate)
  - Fall back to heuristic on Ollama timeout / unavailable
  - Confidence calibration via held-out eval set
  - Integration with /admin/agent-router page

Stage-3 wires risk-tier escalation (high-risk requests → 2-of-3
council vote OR human approval).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[1]
AUDIT_LOG = REPO / ".loop" / "agent_router_audit.jsonl"

# Stage-2 opt-in — same pattern as KAFKA_PUBLISH / LITELLM_ENABLED /
# PYDANTICAI_ENABLED. When set, classify() tries Ollama qwen2.5 FIRST;
# on failure or non-conforming output, falls back to heuristic.
AGENT_ROUTER_OLLAMA_ENABLED = os.getenv("AGENT_ROUTER_OLLAMA_ENABLED", "").strip() == "1"

RiskLevel = Literal["low", "medium", "high", "unknown"]


@dataclass
class RouterDecision:
    intent: str
    risk: RiskLevel
    recommended_actor: str
    recommended_tool: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    message_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Stage-1 heuristic patterns. Stage-2 swaps the body of classify()
# to an Ollama call; these patterns become a fallback layer when the
# LLM call times out or the gate denies it.
#
# Each pattern carries:
#   - intent (semantic verb)
#   - risk tier (low / medium / high)
#   - recommended_actor (matches a PolisAI rule)
#   - recommended_tool (the policy tool)
#
# Order matters: earlier patterns win. Place high-risk patterns
# BEFORE low-risk ones so a "delete and explain" message classifies
# as high-risk delete, not low-risk explain.
# ---------------------------------------------------------------------------

HIGH_RISK_PATTERNS = [
    # Pattern: triggers, intent, risk, actor, tool
    (r"\b(delete|drop|truncate|destroy|wipe)\b",
        "delete", "high", "operator:human", "human_review"),
    (r"\b(force[-\s]?push|force\s+merge|reset\s+--hard)\b",
        "destructive_git", "high", "operator:human", "git_push"),
    (r"\b(deploy|production|prod\b|release)\b",
        "deploy", "high", "operator:human", "human_review"),
    (r"\b(secret|password|credential|api[-\s]?key|token)\b",
        "secret_handling", "high", "operator:human", "human_review"),
    (r"\b(rollback|revert\s+production|undo\s+deploy)\b",
        "rollback", "high", "operator:human", "human_review"),
]

MEDIUM_RISK_PATTERNS = [
    (r"\b(fix|patch|repair)\b.*\b(lint|ruff|mypy|bandit|eslint)\b",
        "fix_lint", "medium", "council:author", "ollama:generate"),
    (r"\b(refactor|rename|extract|inline)\b",
        "refactor", "medium", "council:author", "ollama:generate"),
    (r"\b(merge|rebase|cherry[-\s]?pick)\b",
        "git_merge", "medium", "operator:human", "human_review"),
    # Tolerant of articles + adjectives: "write a test", "create new spec"
    (r"\b(write|create|add)\s+(?:a\s+|an\s+|the\s+|some\s+|new\s+)?(?:\w+\s+){0,2}(test|drill|spec)s?\b",
        "write_test", "medium", "council:author", "ollama:generate"),
    (r"\b(commit|stage)\b",
        "commit", "medium", "operator:human", "git_push"),
]

LOW_RISK_PATTERNS = [
    (r"\b(explain|describe|summarize|tell\s+me|what\s+(is|does))\b",
        "explain", "low", "council:researcher", "ollama:generate"),
    (r"\b(read|view|show|list|dump|cat)\b",
        "read", "low", "paperclip:manager", "read_snapshot"),
    (r"\b(search|find|grep|locate)\b",
        "search", "low", "council:researcher", "ollama:generate"),
    (r"\b(snapshot|status|health|ping)\b",
        "health_check", "low", "paperclip:manager", "read_snapshot"),
]


def _hash_message(message: str) -> str:
    """Short stable hash for audit correlation. NOT for security."""
    import hashlib
    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Stage-2 — Ollama-backed classifier (feature-flag opt-in).
# ---------------------------------------------------------------------------

class _OllamaClassifierUnavailable(Exception):
    """Internal — Ollama path not applicable; heuristic should fire.

    Raised when (a) flag off, (b) Ollama call fails, (c) Ollama
    output doesn't conform to the expected JSON shape. The dispatcher
    catches this and falls through to the heuristic path — Stage-1
    behavior preserved.
    """


def _classify_via_ollama(message: str) -> RouterDecision:
    """Stage-2 — call qwen2.5 with a structured prompt; parse + validate.

    Raises _OllamaClassifierUnavailable on any failure (flag off,
    network error, malformed output, missing fields). Caller falls back
    to heuristic.

    Why qwen2.5: matches the council's Researcher role; ~7B model is
    fast enough for classifier latency. PolisAI gate fires via
    call_ollama itself (actor='council:researcher').
    """
    if not AGENT_ROUTER_OLLAMA_ENABLED:
        raise _OllamaClassifierUnavailable("AGENT_ROUTER_OLLAMA_ENABLED!=1")

    # Lazy import — only loads call_ollama when this Stage-2 path fires
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        from local_council import call_ollama  # noqa: PLC0415
    except ImportError as exc:
        raise _OllamaClassifierUnavailable(f"call_ollama import failed: {exc}") from exc

    system_prompt = (
        "You are a request classifier. Given a user message, return ONLY "
        "JSON of shape:\n"
        "{\n"
        '  "intent": "<short verb>",\n'
        '  "risk": "low" | "medium" | "high",\n'
        '  "recommended_actor": "operator:human" | "council:author" | '
        '"council:researcher" | "council:reviewer" | "council:advisor" | '
        '"paperclip:manager",\n'
        '  "recommended_tool": "<short tool name>",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reason": "<one sentence>"\n'
        "}\n"
        "Rules:\n"
        "- delete/deploy/secret/force-push → high risk\n"
        "- fix-lint/refactor/write-test → medium risk\n"
        "- explain/read/search → low risk\n"
        "- ambiguous/unknown → high risk + operator:human"
    )

    try:
        text, _tokens = call_ollama(
            model="qwen2.5:latest",
            system=system_prompt,
            prompt=message,
            timeout=30.0,
            actor="council:researcher",
        )
    except Exception as exc:  # noqa: BLE001 — wrap as Unavailable for fallback
        raise _OllamaClassifierUnavailable(f"call_ollama failed: {str(exc)[:120]}") from exc

    # Parse — bracket-aware JSON extraction (LLMs sometimes pre/post-amble)
    cleaned = text.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise _OllamaClassifierUnavailable(f"no JSON object in output: {text[:120]!r}")

    try:
        parsed = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise _OllamaClassifierUnavailable(f"output not JSON: {exc}") from exc

    # Validate required fields + types
    required = {"intent", "risk", "recommended_actor", "recommended_tool", "confidence"}
    missing = required - set(parsed.keys())
    if missing:
        raise _OllamaClassifierUnavailable(f"output missing fields: {missing}")

    risk = parsed.get("risk")
    if risk not in ("low", "medium", "high"):
        raise _OllamaClassifierUnavailable(f"risk not in valid set: {risk!r}")

    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        raise _OllamaClassifierUnavailable(f"confidence out of [0,1]: {confidence!r}")

    return RouterDecision(
        intent=str(parsed["intent"])[:40],
        risk=risk,  # type: ignore[arg-type]
        recommended_actor=str(parsed["recommended_actor"])[:40],
        recommended_tool=str(parsed["recommended_tool"])[:40],
        confidence=float(confidence),
        reasons=[
            "ollama:qwen2.5",
            parsed.get("reason", "")[:120],
        ],
        timestamp=time.time(),
        message_hash=_hash_message(message),
    )


def classify(
    message: str,
    context: dict[str, Any] | None = None,
    *,
    persist_audit: bool = True,
) -> RouterDecision:
    """Stage-1 heuristic classifier. Conservative default-deny.

    The classifier ALWAYS returns a decision — never raises on
    ambiguous input. Unknown / ambiguous input → conservative
    (high-risk + operator:human + human_review).
    """
    if not isinstance(message, str):
        raise TypeError(f"message must be str; got {type(message).__name__}")

    text = message.lower().strip()
    if not text:
        # Empty input is conservative-deny (operator must specify).
        return _conservative_default(message, reasons=["empty input"])

    # Stage-2: try Ollama-backed classifier FIRST when AGENT_ROUTER_OLLAMA_ENABLED=1.
    # On any failure (flag off, network, malformed output) → fall through
    # to the Stage-1 heuristic path. Stage-1 behavior preserved verbatim
    # when flag is off (default).
    if AGENT_ROUTER_OLLAMA_ENABLED:
        try:
            decision = _classify_via_ollama(message)
            if persist_audit:
                _append_audit(decision)
            return decision
        except _OllamaClassifierUnavailable:
            # Fall through to heuristic — same Stage-1 path
            pass

    reasons: list[str] = []

    # Walk patterns in order: high → medium → low. First match wins.
    for pattern_list, _ in (
        (HIGH_RISK_PATTERNS, "high"),
        (MEDIUM_RISK_PATTERNS, "medium"),
        (LOW_RISK_PATTERNS, "low"),
    ):
        for regex, intent, risk, actor, tool in pattern_list:
            if re.search(regex, text, re.IGNORECASE):
                reasons.append(f"matched pattern: {regex!r}")
                decision = RouterDecision(
                    intent=intent,
                    risk=risk,  # type: ignore[arg-type]
                    recommended_actor=actor,
                    recommended_tool=tool,
                    confidence=0.7,  # Stage-1 heuristic confidence; Stage-2 calibrates
                    reasons=reasons,
                    timestamp=time.time(),
                    message_hash=_hash_message(message),
                )
                if persist_audit:
                    _append_audit(decision)
                return decision

    # No pattern matched — conservative default
    return _conservative_default(message, reasons=["no pattern matched"], persist=persist_audit)


def _conservative_default(
    message: str,
    *,
    reasons: list[str],
    persist: bool = True,
) -> RouterDecision:
    """The Stage-1 conservative-default posture: unknown → high-risk → human."""
    decision = RouterDecision(
        intent="unknown",
        risk="high",
        recommended_actor="operator:human",
        recommended_tool="human_review",
        confidence=0.0,
        reasons=reasons,
        timestamp=time.time(),
        message_hash=_hash_message(message),
    )
    if persist:
        _append_audit(decision)
    return decision


def _append_audit(decision: RouterDecision) -> None:
    """Best-effort append to .loop/agent_router_audit.jsonl + Kafka fan-out."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict(), default=str) + "\n")
    except OSError:
        pass
    # Stage-2 fan-out to Kafka observability bus per §47 Layer 8.
    # Fail-open: publish failure never blocks classify() return.
    try:
        from event_publisher import publish_router_classification  # noqa: PLC0415
        publish_router_classification(classification=decision.to_dict())
    except Exception:  # noqa: BLE001 — fan-out is best-effort
        pass


def list_patterns() -> dict[str, Any]:
    """Operator-readable surface — what patterns the Stage-1 classifier knows."""
    return {
        "stage": 1,
        "high_risk_count": len(HIGH_RISK_PATTERNS),
        "medium_risk_count": len(MEDIUM_RISK_PATTERNS),
        "low_risk_count": len(LOW_RISK_PATTERNS),
        "patterns": {
            "high": [{"regex": p[0], "intent": p[1], "actor": p[3], "tool": p[4]}
                     for p in HIGH_RISK_PATTERNS],
            "medium": [{"regex": p[0], "intent": p[1], "actor": p[3], "tool": p[4]}
                       for p in MEDIUM_RISK_PATTERNS],
            "low": [{"regex": p[0], "intent": p[1], "actor": p[3], "tool": p[4]}
                    for p in LOW_RISK_PATTERNS],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agent_router",
        description="Stage-1 intent + risk classifier (conservative-default).",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_class = sub.add_parser("classify", help="Classify a message")
    p_class.add_argument("--message", required=True)
    p_class.add_argument("--no-audit", action="store_true")

    sub.add_parser("patterns", help="List the heuristic patterns")

    args = parser.parse_args()

    if args.cmd == "classify":
        decision = classify(args.message, persist_audit=not args.no_audit)
        print(json.dumps(decision.to_dict(), indent=2, default=str))
        # Exit code by risk: low=0, medium=1, high=2, unknown=2
        return {"low": 0, "medium": 1, "high": 2, "unknown": 2}[decision.risk]

    if args.cmd == "patterns":
        print(json.dumps(list_patterns(), indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
