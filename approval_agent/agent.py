"""Approval agent — decides auto-approve / human-required / deny / revise.

THE BRUTAL RULE (codified per the user's spec):
  - Agents may approve PROGRESS.
  - Agents may NOT approve dangerous actions.
  - Human approves all system-level changes.

Decision flow:
  blocked_action      → DENY                       (always; no override)
  human_required      → HUMAN_REQUIRED             (pause + notify)
  risk > max_risk     → HUMAN_REQUIRED             (pause + notify)
  tests_passed=False  → REVISION_REQUIRED          (loop back to author)
  confidence < min    → REVISION_REQUIRED
  governance != allow → REVISION_REQUIRED
  reviewer != APPROVED → REVISION_REQUIRED         (Claude or local council)
  otherwise           → AUTO_APPROVED              (continue)

Composes with:
  - ops_worker.worker (called between Ollama proposal + Claude review)
  - safety_store.save_history (every decision is a history row)
  - CLAUDE.md §38 governance + §52 brutal tool review
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

RULES_FILE = Path(__file__).resolve().parent / "rules.json"
log = logging.getLogger(__name__)

# Backend selector. Default is ``opa`` per drill_opa_approval_parity
# (12-input cross-product green + fallback drill green). Inline stays
# available as the fallback path when OPA binary or policy is missing,
# AND as an explicit override (DOCUMIND_APPROVAL_ENGINE=inline).
#
# Flip rationale: the rego file is the source of truth for governance.
# Keeping inline as default would make rules.json the implicit truth,
# leading to drift between the two. With opa default + inline fallback,
# the rego file owns the rules and the Python is the safety net.
APPROVAL_ENGINE = os.getenv("DOCUMIND_APPROVAL_ENGINE", "opa").lower()


@dataclass
class ApprovalDecision:
    decision: str  # AUTO_APPROVED | HUMAN_REQUIRED | DENY | REVISION_REQUIRED
    reason: str
    requires_human: bool
    next_action: str
    rule_hits: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)


def _load_rules() -> dict[str, Any]:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def decide(
    *,
    task: dict[str, Any],
    test_result: str = "PASS",
    governance_result: str = "ALLOW",
    reviewer_decision: str = "APPROVED",
    confidence: float = 0.85,
    rules: dict[str, Any] | None = None,
    engine: str | None = None,
) -> ApprovalDecision:
    """Pure function — same inputs → same decision. Drillable.

    ``task`` keys consulted: ``id``, ``action``, ``type``, ``risk``.
    ``reviewer_decision`` ∈ {APPROVED, REVISION_REQUIRED, SKIPPED}.
      - SKIPPED is treated as "no signal" — does NOT block AUTO_APPROVED
        but also does NOT itself approve. The other gates decide.

    Engine selector:
      ``engine='opa'`` (or env DOCUMIND_APPROVAL_ENGINE=opa) → delegates to
      OPA via ``opa_client.evaluate``. The drill enforces parity between
      the inline + OPA paths. If OPA is requested but unavailable, falls
      back to inline + logs a warning (don't break the request path).
    """
    chosen_engine = (engine or APPROVAL_ENGINE).lower()
    if chosen_engine == "opa":
        from .opa_client import OpaError, evaluate, opa_available
        if not opa_available():
            log.warning("opa_engine_requested_but_unavailable — falling back to inline")
        else:
            try:
                opa_result = evaluate(
                    task=task, test_result=test_result,
                    governance_result=governance_result,
                    reviewer_decision=reviewer_decision,
                    confidence=confidence,
                )
                return ApprovalDecision(
                    decision=opa_result.decision,
                    reason=f"opa: {opa_result.decision} (policy.rego)",
                    requires_human=opa_result.decision == "HUMAN_REQUIRED",
                    next_action={
                        "AUTO_APPROVED": "move_to_next_task",
                        "HUMAN_REQUIRED": "pause_for_human",
                        "DENY": "block",
                        "REVISION_REQUIRED": "loop_back_to_author",
                    }.get(opa_result.decision, "unknown"),
                    rule_hits=[f"opa:{opa_result.decision}"],
                    inputs={"engine": "opa"},
                )
            except OpaError as e:
                log.warning("opa_eval_failed err=%s — falling back to inline", e)

    rules = rules or _load_rules()
    rule_hits: list[str] = []

    action = (task.get("action") or "").lower()
    task_type = (task.get("type") or "").lower()
    risk = (task.get("risk") or "medium").lower()

    # 1. BLOCKED — non-overridable. Always DENY.
    blocked = set(rules.get("blocked_actions", []))
    if action in blocked:
        rule_hits.append(f"blocked_action:{action}")
        return ApprovalDecision(
            decision="DENY",
            reason=f"Blocked action: {action!r} is on the always-deny list",
            requires_human=False,
            next_action="block",
            rule_hits=rule_hits,
            inputs={"action": action, "risk": risk},
        )

    # 2. HUMAN-REQUIRED actions or types — never auto-approve.
    human_actions = set(rules.get("human_required_actions", []))
    human_types = set(rules.get("human_required_task_types", []))
    if action in human_actions:
        rule_hits.append(f"human_required_action:{action}")
        return ApprovalDecision(
            decision="HUMAN_REQUIRED",
            reason=f"Action {action!r} requires human approval",
            requires_human=True,
            next_action="pause_for_human",
            rule_hits=rule_hits,
        )
    if task_type in human_types:
        rule_hits.append(f"human_required_type:{task_type}")
        return ApprovalDecision(
            decision="HUMAN_REQUIRED",
            reason=f"Task type {task_type!r} requires human approval",
            requires_human=True,
            next_action="pause_for_human",
            rule_hits=rule_hits,
        )

    # 3. Risk above max → HUMAN.
    max_risk = rules.get("max_risk", "medium")
    if _RISK_ORDER.get(risk, 99) > _RISK_ORDER.get(max_risk, 2):
        rule_hits.append(f"risk_above_max:{risk}>{max_risk}")
        return ApprovalDecision(
            decision="HUMAN_REQUIRED",
            reason=f"Risk {risk!r} exceeds auto-approval ceiling {max_risk!r}",
            requires_human=True,
            next_action="pause_for_human",
            rule_hits=rule_hits,
        )

    # 4. Quality gates — tests passed, confidence, governance, reviewer.
    if rules.get("requires_tests_passed", True) and test_result.upper() != "PASS":
        rule_hits.append(f"tests_not_passed:{test_result}")
        return ApprovalDecision(
            decision="REVISION_REQUIRED",
            reason=f"Tests did not pass (got {test_result!r})",
            requires_human=False,
            next_action="loop_back_to_author",
            rule_hits=rule_hits,
        )

    min_conf = float(rules.get("min_confidence", 0.7))
    if confidence < min_conf:
        rule_hits.append(f"confidence_below_min:{confidence}<{min_conf}")
        return ApprovalDecision(
            decision="REVISION_REQUIRED",
            reason=f"Confidence {confidence:.2f} below threshold {min_conf}",
            requires_human=False,
            next_action="loop_back_to_author",
            rule_hits=rule_hits,
        )

    if governance_result.upper() != "ALLOW":
        rule_hits.append(f"governance:{governance_result}")
        return ApprovalDecision(
            decision="REVISION_REQUIRED",
            reason=f"Governance verdict {governance_result!r} (not ALLOW)",
            requires_human=False,
            next_action="loop_back_to_author",
            rule_hits=rule_hits,
        )

    rd = reviewer_decision.upper()
    if rd not in {"APPROVED", "SKIPPED"}:
        rule_hits.append(f"reviewer:{rd}")
        return ApprovalDecision(
            decision="REVISION_REQUIRED",
            reason=f"Reviewer verdict {rd!r}",
            requires_human=False,
            next_action="loop_back_to_author",
            rule_hits=rule_hits,
        )

    # 5. Auto-approve only if task_type is in the explicit allow list.
    auto_types = set(rules.get("auto_approve_task_types", []))
    if auto_types and task_type and task_type not in auto_types:
        rule_hits.append(f"task_type_not_in_auto_list:{task_type}")
        return ApprovalDecision(
            decision="HUMAN_REQUIRED",
            reason=f"Task type {task_type!r} not in auto-approve allowlist",
            requires_human=True,
            next_action="pause_for_human",
            rule_hits=rule_hits,
        )

    rule_hits.append("all_gates_passed")
    return ApprovalDecision(
        decision="AUTO_APPROVED",
        reason=(
            f"risk={risk} test={test_result} gov={governance_result} "
            f"reviewer={rd} confidence={confidence:.2f} — all gates passed"
        ),
        requires_human=False,
        next_action="move_to_next_task",
        rule_hits=rule_hits,
    )


def to_dict(d: ApprovalDecision) -> dict[str, Any]:
    return asdict(d)


__all__ = ["ApprovalDecision", "decide", "to_dict"]
