"""Agent council orchestrator — sequential pipeline with safety gates.

Flow:
  Router → Planner → Researcher → Advisor → Critic → (approval gate) →
  Presenter → save_history(action='session_complete') → done

Safety integration:
  - approval_agent.decide() runs BEFORE Presenter — if DENY, abort.
  - safety_store.save_history records every session for replay/audit.
  - Destructive intent (regex against blocked verbs) auto-routes to DENY.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent_cli.agents import advisor, cli_logger, critic, planner, presenter, researcher
from approval_agent import decide as approval_decide
from risk_classifier import classify
from safety_store import save_history

# Heuristic — text-only detection of dangerous intent. Operators
# treat this as ONE layer of defence; the approval_agent's blocked
# action list is the SECOND layer.
DESTRUCTIVE_PATTERNS = re.compile(
    r"\b(rm\s+-rf|drop\s+(database|table)|delete\s+(production|history|audit)|"
    r"force.?push|sudo\s+rm|truncate\s+table)\b",
    re.IGNORECASE,
)


@dataclass
class CouncilResult:
    user_input: str
    final_answer: str
    plan: str
    research: str
    advice: str
    critique: str
    approval_decision: str
    approval_reason: str
    history_id: str
    session_id: str

    def short(self) -> str:
        return (
            f"approval={self.approval_decision}  "
            f"history={self.history_id}  "
            f"answer_chars={len(self.final_answer)}"
        )


def _detect_destructive_intent(text: str) -> str | None:
    m = DESTRUCTIVE_PATTERNS.search(text)
    return m.group(0) if m else None


def run_council(
    user_input: str,
    *,
    actor: str = "agent_cli",
    session_id: str | None = None,
    skip_presenter: bool = False,
) -> CouncilResult:
    """Run the full council. Raises ValueError if input is empty."""
    if not user_input.strip():
        raise ValueError("user_input must be non-empty")
    sid = session_id or _new_session_id()
    cli_logger.log("router", f"session={sid}  request={user_input[:80]!r}")

    # ── Pre-gate: destructive verb in the prompt itself ────────────────
    hit = _detect_destructive_intent(user_input)
    if hit:
        cli_logger.log("blocked", f"destructive_intent={hit!r} — DENY")
        record = save_history(
            entity_type="agent_cli_session",
            entity_id=sid,
            action="denied_destructive_intent",
            old_value=None,
            new_value={"user_input": user_input, "trigger": hit},
            actor=actor,
            reason=f"destructive verb pattern matched: {hit!r}",
            rollback_allowed=False,
        )
        return CouncilResult(
            user_input=user_input,
            final_answer=(
                f"REQUEST DENIED — destructive intent detected: {hit!r}. "
                "Re-phrase without the destructive verb. The CLI does NOT "
                "execute commands; it produces plans only."
            ),
            plan="", research="", advice="", critique="",
            approval_decision="DENY",
            approval_reason=f"destructive_intent:{hit}",
            history_id=record.history_id,
            session_id=sid,
        )

    # ── Pipeline: Planner → Researcher → Advisor → Critic ──────────────
    cli_logger.log("planner", "decomposing into phases")
    plan = planner.run(user_input)["response"]

    cli_logger.log("researcher", "surveying tools / patterns")
    research = researcher.run(user_input)["response"]

    cli_logger.log("advisor", "picking one path")
    advice = advisor.run(user_input)["response"]

    combined = (
        f"=== PLAN ===\n{plan}\n\n"
        f"=== RESEARCH ===\n{research}\n\n"
        f"=== ADVICE ===\n{advice}"
    )
    cli_logger.log("critic", "finding gaps")
    critique = critic.run(combined)["response"]

    # ── Approval gate ──────────────────────────────────────────────────
    # The CLI itself produces RECOMMENDATIONS — task type =
    # "recommendation", risk inferred from prompt.
    inferred_risk = _infer_risk(user_input)
    pseudo_task = {
        "id": sid,
        "action": "recommendation",  # always recommendation from this CLI
        "type": "recommendation",
        "risk": inferred_risk,
    }
    decision = approval_decide(
        task=pseudo_task,
        test_result="PASS",
        governance_result="ALLOW",
        reviewer_decision="APPROVED",
        confidence=0.85,
    )
    cli_logger.log("approval", f"{decision.decision} — {decision.reason}")

    if decision.decision == "DENY":
        record = save_history(
            entity_type="agent_cli_session",
            entity_id=sid,
            action="denied_by_approval",
            old_value=None,
            new_value={"user_input": user_input, "rule_hits": decision.rule_hits},
            actor=actor,
            reason=decision.reason,
            rollback_allowed=False,
        )
        return CouncilResult(
            user_input=user_input,
            final_answer=f"REQUEST DENIED by approval_agent: {decision.reason}",
            plan=plan, research=research, advice=advice, critique=critique,
            approval_decision="DENY",
            approval_reason=decision.reason,
            history_id=record.history_id,
            session_id=sid,
        )

    # ── Presenter (optional skip for tests) ────────────────────────────
    if skip_presenter:
        final_answer = combined + "\n\n=== CRITIQUE ===\n" + critique
    else:
        cli_logger.log("presenter", "synthesizing structured answer")
        final_answer = presenter.run(combined + "\n\n=== CRITIQUE ===\n" + critique)["response"]

    record = save_history(
        entity_type="agent_cli_session",
        entity_id=sid,
        action="session_complete",
        old_value=None,
        new_value={
            "user_input": user_input,
            "approval_decision": decision.decision,
            "answer_chars": len(final_answer),
        },
        actor=actor,
        reason=f"agent council session id={sid}",
        approved_by="approval_agent",
    )
    cli_logger.log("done", f"session_complete history={record.history_id}")
    return CouncilResult(
        user_input=user_input,
        final_answer=final_answer,
        plan=plan, research=research, advice=advice, critique=critique,
        approval_decision=decision.decision,
        approval_reason=decision.reason,
        history_id=record.history_id,
        session_id=sid,
    )


def _infer_risk(text: str) -> str:
    """Delegate to risk_classifier. The local heuristic is gone — keyword
    coverage and audit triggers belong in one place (risk_classifier),
    not duplicated across three modules."""
    return classify(description=text).level


def _new_session_id() -> str:
    from uuid import uuid4
    return f"S_{uuid4().hex[:10]}"
