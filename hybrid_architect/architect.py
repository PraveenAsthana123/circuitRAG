"""Hybrid Architect — composes Hub-and-Spoke + Council (CLAUDE.md §47).

Public entrypoint:
    process(user_input, *, request_id=None, actor="hybrid_architect") -> HybridDecision

Internal entrypoint (for drills + DI):
    _process(user_input, *, request_id, actor, hub_fn, council_fn) -> HybridDecision
"""
from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

from agent_cli.orchestrator import CouncilResult
from agent_cli.orchestrator import run_council as _run_hub
from council_engine.orchestrator import run_council as _run_full_council
from risk_classifier import classify
from safety_store import save_history

Lane = Literal[
    "hub_only",
    "hub_council",
    "hub_council_deep",
    "hub_council_deep_hitl",
]


@dataclass
class HybridDecision:
    request_id: str
    user_input: str
    risk_level: str
    lane: Lane
    hub_final_answer: str
    hub_approval: str
    council_decision: dict[str, Any] | None
    final_decision: str
    final_answer: str
    history_id: str
    requires_hitl: bool
    elapsed_ms: int

    def short(self) -> str:
        return (
            f"lane={self.lane} risk={self.risk_level} "
            f"final={self.final_decision} hitl={self.requires_hitl} "
            f"hist={self.history_id}"
        )


def _pick_lane(risk: str) -> tuple[Lane, bool]:
    """Map risk tier → (lane, requires_hitl).

    Unknown risk defaults to the safest lane (deep council + HITL).
    """
    if risk == "low":
        return ("hub_only", False)
    if risk == "medium":
        return ("hub_council", False)
    if risk == "high":
        return ("hub_council_deep", False)
    if risk == "critical":
        return ("hub_council_deep_hitl", True)
    return ("hub_council_deep_hitl", True)


def _lane_to_council_risk(lane: Lane) -> str:
    return {
        "hub_only": "low",
        "hub_council": "medium",
        "hub_council_deep": "high",
        "hub_council_deep_hitl": "critical",
    }.get(lane, "high")


def _env_truthy(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _run_fast_low_risk_hub(
    user_input: str,
    *,
    actor: str,
    session_id: str,
    skip_presenter: bool = False,
) -> CouncilResult:
    """Deterministic low-risk hub for status/explanation requests.

    The normal hub spends four local model calls before approval. Low-risk
    Hybrid Architect requests do not need that spend to preserve governance:
    this path still records an agent_cli_session row and lets the outer
    hybrid_decision row persist the lane decision.
    """
    del skip_presenter
    record = save_history(
        entity_type="agent_cli_session",
        entity_id=session_id,
        action="fast_low_risk_session",
        old_value=None,
        new_value={
            "user_input": user_input,
            "approval_decision": "AUTO_APPROVED",
            "fast_path": "hybrid_low_risk",
        },
        actor=actor,
        reason=f"hybrid low-risk fast path session id={session_id}",
        approved_by="hybrid_architect",
    )
    final_answer = (
        "FAST-PATH LOW-RISK RESPONSE\n"
        f"Request: {user_input}\n"
        "Decision: AUTO_APPROVED. The request was classified as low risk, "
        "so Hybrid Architect skipped the multi-agent LLM hub and preserved "
        "the audit trail through the fast-path history row."
    )
    return CouncilResult(
        user_input=user_input,
        final_answer=final_answer,
        plan="low-risk fast path",
        research="not required for low-risk status/explanation request",
        advice="proceed",
        critique="no high-risk action detected",
        approval_decision="AUTO_APPROVED",
        approval_reason="hybrid_low_risk_fast_path",
        history_id=record.history_id,
        session_id=session_id,
    )


def _maybe_open_trace(request_id: str):
    """Lazy + offline-safe Langfuse trace context.

    Returns a context manager that yields (ctx, span_fn) where ctx and
    span_fn may be None when Langfuse is unavailable. Callers always
    work — span emission is a no-op when offline.
    """
    import contextlib

    @contextlib.contextmanager
    def _noop():
        yield (None, None)

    try:
        from scripts.langfuse_tracer import is_available, span, trace_context
    except Exception:
        return _noop()

    if not is_available():
        return _noop()

    @contextlib.contextmanager
    def _real():
        with trace_context(
            correlation_id=request_id,
            tenant_id="default",
            name="hybrid_architect.process",
        ) as ctx:
            yield (ctx, span)

    return _real()


def _process(
    user_input: str,
    *,
    request_id: str | None,
    actor: str,
    skip_presenter: bool,
    hub_fn: Callable[..., Any],
    council_fn: Callable[..., Any],
    fast_low_risk: bool = False,
) -> HybridDecision:
    if not user_input or not user_input.strip():
        raise ValueError("user_input must be non-empty")

    rid = request_id or f"H_{uuid.uuid4().hex[:10]}"
    started = time.time()

    # 1. Risk → lane
    assessment = classify(description=user_input)
    risk = assessment.level
    lane, hitl = _pick_lane(risk)

    council_decision_dump: dict[str, Any] | None = None
    council_run = None

    with _maybe_open_trace(rid) as (ctx, span_fn):
        # 2. Hub always runs
        selected_hub_fn = (
            _run_fast_low_risk_hub
            if fast_low_risk and lane == "hub_only"
            else hub_fn
        )
        if span_fn and ctx is not None:
            with span_fn(ctx, "hub.run", inputs={"user_input": user_input[:200]}) as sp:
                hub = selected_hub_fn(
                    user_input,
                    actor=actor,
                    session_id=rid,
                    skip_presenter=skip_presenter,
                )
                sp.outputs["approval"] = hub.approval_decision
                sp.outputs["history_id"] = hub.history_id
        else:
            hub = selected_hub_fn(
                user_input,
                actor=actor,
                session_id=rid,
                skip_presenter=skip_presenter,
            )

        # 3. Council runs only when (a) lane warrants it AND (b) hub
        #    didn't already deny. Asking a council to debate a
        #    pre-denied request burns LLM cost for no decision delta.
        if lane != "hub_only" and hub.approval_decision != "DENY":
            deep = lane in ("hub_council_deep", "hub_council_deep_hitl")
            task = {
                "id": rid,
                "risk": _lane_to_council_risk(lane),
                "type": "hybrid_review",
            }
            review_input = (
                f"Original user request:\n{user_input}\n\n"
                f"Hub answer to review:\n{hub.final_answer}"
            )
            if span_fn and ctx is not None:
                with span_fn(
                    ctx,
                    f"council.run.deep={deep}",
                    inputs={"task_risk": task["risk"]},
                ) as sp:
                    council_run = council_fn(
                        task=task,
                        user_input=review_input,
                        actor=actor,
                        deep=deep,
                    )
                    sp.outputs["final_decision"] = council_run.decision.final_decision
                    sp.outputs["confidence"] = council_run.decision.confidence
            else:
                council_run = council_fn(
                    task=task,
                    user_input=review_input,
                    actor=actor,
                    deep=deep,
                )
            council_decision_dump = council_run.decision.model_dump()

    # 4. Compose final decision
    final_answer = hub.final_answer
    final_decision = hub.approval_decision
    if council_run is not None:
        cd = council_run.decision
        if cd.final_decision in ("reject", "escalate"):
            # Council veto. Hub's answer is suppressed in the final
            # response so downstream callers cannot accidentally
            # surface it. The full hub_final_answer is still in the
            # audit row for forensics (§51).
            final_answer = (
                f"COUNCIL OVERRIDE — verdict={cd.final_decision} "
                f"confidence={cd.confidence:.2f}\n"
                f"Council recommended_action: {cd.recommended_action}\n"
                f"(Hub answer suppressed; preserved in history_id for replay.)"
            )
            final_decision = cd.final_decision.upper()

    # 5. Persist hybrid decision row (forensic substrate per §51)
    rec = save_history(
        entity_type="hybrid_architect_run",
        entity_id=rid,
        action="hybrid_decision",
        old_value=None,
        new_value={
            "user_input": user_input,
            "risk_level": risk,
            "lane": lane,
            "hub_approval": hub.approval_decision,
            "council_decision": council_decision_dump,
            "requires_hitl": hitl,
            "final_decision": final_decision,
        },
        actor=actor,
        reason=f"hybrid lane={lane} risk={risk} final={final_decision}",
        approved_by="hybrid_architect",
    )

    return HybridDecision(
        request_id=rid,
        user_input=user_input,
        risk_level=risk,
        lane=lane,
        hub_final_answer=hub.final_answer,
        hub_approval=hub.approval_decision,
        council_decision=council_decision_dump,
        final_decision=final_decision,
        final_answer=final_answer,
        history_id=rec.history_id,
        requires_hitl=hitl,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def process(
    user_input: str,
    *,
    request_id: str | None = None,
    actor: str = "hybrid_architect",
    skip_presenter: bool = False,
    fast_low_risk: bool | None = None,
) -> HybridDecision:
    """Public entrypoint — composes hub + council per risk tier."""
    return _process(
        user_input,
        request_id=request_id,
        actor=actor,
        skip_presenter=skip_presenter,
        fast_low_risk=(
            _env_truthy("HYBRID_ARCHITECT_FAST_LOW_RISK", "1")
            if fast_low_risk is None
            else fast_low_risk
        ),
        hub_fn=_run_hub,
        council_fn=_run_full_council,
    )


def to_dict(decision: HybridDecision) -> dict[str, Any]:
    """Stable JSON-friendly serializer."""
    return asdict(decision)


__all__ = ["HybridDecision", "process", "to_dict", "_pick_lane", "_process"]
