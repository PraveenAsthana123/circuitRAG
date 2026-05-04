#!/usr/bin/env python3
"""Policy Stage-1 — local Rego-shaped policy evaluator.

Per CLAUDE.md §47 (orchestration architecture: Policy → Manager →
Workers) + §38 (decision audit) + ADR-012. Stage-1 ships a pure-Python
evaluator over a JSON policy file (config/policies/agent_dispatch.json)
so the council host does not need the OPA binary on the request hot
path. Stage-2 swaps to OPA + Rego while keeping the audit row schema
intact — the eval contract here IS the OPA-ready interface.

Contract:

  evaluate(actor, tool, scopes_granted, policy_file=DEFAULT)
    -> PolicyDecision {
         allow: bool,
         rule_matched: str,
         reason: str,
         actor: str,
         tool: str,
         scope_required: list[str],
         scope_granted: list[str],
         missing_scopes: list[str],
         policy_version: str,
         policy_id: str,
         timestamp: float,
       }

Default-deny: any (actor, tool) combination not matched by an explicit
allow rule is rejected. Wildcard `tool: "*"` allowed for operator-class
rules. Every decision (allow OR deny) is appended to .loop/
policy_audit.jsonl for the §38 / §48.4 audit trail.

CLI:

  python scripts/policy_check.py eval \
      --actor council:author --tool read_checklist \
      --scopes checklist:read

  python scripts/policy_check.py rules

  python scripts/policy_check.py reload   # show policy_version + rule count

The drill locks both directions: known-good → allow, every malformed /
unauthorized / wrong-scope / unknown-tool path → deny with reason.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO / "config" / "policies" / "agent_dispatch.json"
AUDIT_LOG = REPO / ".loop" / "policy_audit.jsonl"


@dataclass
class PolicyDecision:
    allow: bool
    rule_matched: str
    reason: str
    actor: str
    tool: str
    scope_required: list[str] = field(default_factory=list)
    scope_granted: list[str] = field(default_factory=list)
    missing_scopes: list[str] = field(default_factory=list)
    policy_version: str = ""
    policy_id: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PolicyError(ValueError):
    """Raised when the policy file itself is malformed.

    Distinct from a *deny* decision — a malformed policy is an
    operator bug, not a routine authorization failure.
    """


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    """Load + minimally validate the policy file.

    Validation here is intentionally strict: missing top-level keys
    or malformed rules raise PolicyError so the operator finds out
    BEFORE the council fires, not at the first denied request.
    """
    if not path.exists():
        raise PolicyError(f"policy file not found: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PolicyError(f"policy file not valid JSON: {e}") from e

    for key in ("policy_version", "policy_id", "rules", "default_effect"):
        if key not in doc:
            raise PolicyError(f"policy missing top-level key: {key!r}")

    if doc["default_effect"] not in ("allow", "deny"):
        raise PolicyError(
            f"default_effect must be 'allow' or 'deny'; got {doc['default_effect']!r}"
        )

    if not isinstance(doc["rules"], list):
        raise PolicyError("policy.rules must be a list")

    for idx, rule in enumerate(doc["rules"]):
        for key in ("rule_id", "actor", "tool", "scope_required", "effect"):
            if key not in rule:
                raise PolicyError(
                    f"rule[{idx}] missing key {key!r}: {rule.get('rule_id', '?')}"
                )
        if rule["effect"] not in ("allow", "deny"):
            raise PolicyError(
                f"rule[{idx}].effect must be 'allow' or 'deny'; got {rule['effect']!r}"
            )

    return doc


def _matches(rule_pattern: str, value: str) -> bool:
    """Wildcard-aware match. `*` matches any value; otherwise exact."""
    return rule_pattern == "*" or rule_pattern == value


def evaluate(
    actor: str,
    tool: str,
    scopes_granted: list[str] | tuple[str, ...] | None = None,
    policy_file: Path | None = None,
    *,
    persist_audit: bool = True,
) -> PolicyDecision:
    """The Stage-1 evaluator. Default-deny.

    Returns a PolicyDecision regardless of allow/deny; the caller MUST
    check `.allow`. A deny is NOT an exception — it's a normal, audited
    decision. PolicyError is reserved for malformed policies.
    """
    if not isinstance(actor, str) or not actor.strip():
        raise PolicyError(f"actor must be non-empty string; got {actor!r}")
    if not isinstance(tool, str) or not tool.strip():
        raise PolicyError(f"tool must be non-empty string; got {tool!r}")

    granted: list[str] = list(scopes_granted or [])
    policy = load_policy(policy_file or DEFAULT_POLICY)
    now = time.time()

    decision: PolicyDecision | None = None
    for rule in policy["rules"]:
        if not _matches(rule["actor"], actor):
            continue
        if not _matches(rule["tool"], tool):
            continue

        required = list(rule["scope_required"])
        missing = [s for s in required if s not in granted]

        if rule["effect"] == "allow":
            if not missing:
                decision = PolicyDecision(
                    allow=True,
                    rule_matched=rule["rule_id"],
                    reason=rule.get("rationale", "rule matched + scope granted"),
                    actor=actor,
                    tool=tool,
                    scope_required=required,
                    scope_granted=granted,
                    missing_scopes=[],
                    policy_version=policy["policy_version"],
                    policy_id=policy["policy_id"],
                    timestamp=now,
                )
                break
            decision = PolicyDecision(
                allow=False,
                rule_matched=rule["rule_id"],
                reason=f"matched allow-rule but missing scopes: {missing}",
                actor=actor,
                tool=tool,
                scope_required=required,
                scope_granted=granted,
                missing_scopes=missing,
                policy_version=policy["policy_version"],
                policy_id=policy["policy_id"],
                timestamp=now,
            )
            break
        if rule["effect"] == "deny":
            decision = PolicyDecision(
                allow=False,
                rule_matched=rule["rule_id"],
                reason=f"explicit deny: {rule.get('rationale', '')}",
                actor=actor,
                tool=tool,
                scope_required=required,
                scope_granted=granted,
                missing_scopes=[],
                policy_version=policy["policy_version"],
                policy_id=policy["policy_id"],
                timestamp=now,
            )
            break

    if decision is None:
        # No rule matched — apply default_effect (default-deny)
        decision = PolicyDecision(
            allow=(policy["default_effect"] == "allow"),
            rule_matched="default-deny" if policy["default_effect"] == "deny" else "default-allow",
            reason=policy.get("deny_rationale", "no rule matched (default-deny)"),
            actor=actor,
            tool=tool,
            scope_required=[],
            scope_granted=granted,
            missing_scopes=[],
            policy_version=policy["policy_version"],
            policy_id=policy["policy_id"],
            timestamp=now,
        )

    if persist_audit:
        _append_audit(decision)
        # Stage-2 fan-out to Kafka observability bus per §47 Layer 8.
        # Fail-open: publish failure never blocks the decision return.
        try:
            from event_publisher import publish_policy_decision  # noqa: PLC0415
            publish_policy_decision(decision=decision.to_dict())
        except Exception:  # noqa: BLE001 — fan-out is best-effort
            pass
    return decision


def _append_audit(decision: PolicyDecision) -> None:
    """Append decision to .loop/policy_audit.jsonl. Best-effort: an audit
    write failure must NOT block the decision from being returned."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict(), default=str) + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# CLI surface — used by drills + operator inspection.
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="policy_check",
        description="Stage-1 policy evaluator (Rego-shaped, Python-eval).",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_eval = sub.add_parser("eval", help="Evaluate (actor, tool, scopes)")
    p_eval.add_argument("--actor", required=True)
    p_eval.add_argument("--tool", required=True)
    p_eval.add_argument(
        "--scopes",
        default="",
        help="comma-separated list of scope tokens granted to the actor",
    )
    p_eval.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY),
        help="path to policy JSON (default: config/policies/agent_dispatch.json)",
    )
    p_eval.add_argument(
        "--no-audit",
        action="store_true",
        help="skip appending to .loop/policy_audit.jsonl (drill use)",
    )

    sub.add_parser("rules", help="List loaded policy rules")
    sub.add_parser("reload", help="Print policy version + rule count")

    args = parser.parse_args()

    if args.cmd == "eval":
        scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
        try:
            decision = evaluate(
                actor=args.actor,
                tool=args.tool,
                scopes_granted=scopes,
                policy_file=Path(args.policy),
                persist_audit=not args.no_audit,
            )
        except PolicyError as e:
            print(json.dumps({
                "ok": False,
                "error_code": "POLICY_MALFORMED",
                "message": str(e),
            }, indent=2))
            return 3  # malformed-policy exit (distinct from deny)
        print(json.dumps(decision.to_dict(), indent=2, default=str))
        return 0 if decision.allow else 1  # allow=0; deny=1

    if args.cmd == "rules":
        try:
            policy = load_policy()
        except PolicyError as e:
            print(json.dumps({"error": str(e)}, indent=2))
            return 3
        print(json.dumps({
            "policy_id": policy["policy_id"],
            "policy_version": policy["policy_version"],
            "default_effect": policy["default_effect"],
            "rule_count": len(policy["rules"]),
            "rules": [
                {
                    "rule_id": r["rule_id"],
                    "actor": r["actor"],
                    "tool": r["tool"],
                    "scope_required": r["scope_required"],
                    "effect": r["effect"],
                }
                for r in policy["rules"]
            ],
        }, indent=2))
        return 0

    if args.cmd == "reload":
        try:
            policy = load_policy()
        except PolicyError as e:
            print(json.dumps({"error": str(e)}, indent=2))
            return 3
        print(json.dumps({
            "policy_id": policy["policy_id"],
            "policy_version": policy["policy_version"],
            "rule_count": len(policy["rules"]),
            "default_effect": policy["default_effect"],
        }, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
