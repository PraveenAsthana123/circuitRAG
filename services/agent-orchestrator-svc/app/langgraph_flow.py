from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from .agents import ManagerAgent, ReviewerAgent, SecurityAdvisor, WorkerAgent
from .models import AgenticPolicyView
from .policy import evaluate_approval_reasons


class AgenticState(TypedDict, total=False):
    task_id: str
    tenant_id: str
    goal: str
    status: str
    risk_level: str
    require_human_approval: bool
    approval_mode: str
    auto_advance: bool
    approved: bool | None
    resume_from: str
    confidence: float
    plan: list[str]
    tool_namespace: str | None
    tool_name: str | None
    tool_arguments: dict[str, Any]
    worker_output: str
    worker_risks: list[str]
    reviewer_notes: list[str]
    reviewer_risks: list[str]
    approval_reasons: list[str]
    advisor_summary: str
    advisor_risks: list[str]
    next_action: str
    audit_events: list[dict[str, Any]]
    policy: dict[str, Any]


def build_graph(
    *,
    manager: ManagerAgent,
    worker: WorkerAgent,
    reviewer: ReviewerAgent,
    advisor: SecurityAdvisor,
    default_policy: AgenticPolicyView,
):
    from langgraph.graph import END, StateGraph

    async def entry_router(state: AgenticState) -> AgenticState:
        return state

    async def manager_plan(state: AgenticState) -> AgenticState:
        plan = await manager.plan(state["goal"])
        events = list(state.get("audit_events", []))
        events.append({"role": "manager", "event": "planned", "plan": plan, "at": datetime.utcnow().isoformat()})
        return {
            "plan": plan,
            "status": "planned",
            "next_action": "worker_execute",
            "audit_events": events,
        }

    async def worker_execute(state: AgenticState) -> AgenticState:
        result = await worker.run(
            state["goal"],
            tenant_id=state["tenant_id"],
            tool_namespace=state.get("tool_namespace"),
            tool_name=state.get("tool_name"),
            tool_arguments=state.get("tool_arguments"),
        )
        events = list(state.get("audit_events", []))
        events.append({"role": "worker", "event": "executed", "confidence": result.confidence, "at": datetime.utcnow().isoformat()})
        return {
            "worker_output": result.text,
            "confidence": result.confidence,
            "worker_risks": result.risks or [],
            "status": "worked",
            "next_action": "review_output",
            "audit_events": events,
        }

    async def review_output(state: AgenticState) -> AgenticState:
        result = await reviewer.review(state["goal"], state["worker_output"])
        events = list(state.get("audit_events", []))
        events.append({"role": "reviewer", "event": "reviewed", "confidence": result.confidence, "at": datetime.utcnow().isoformat()})
        return {
            "reviewer_notes": [result.text],
            "reviewer_risks": result.risks or [],
            "confidence": min(state.get("confidence", 1.0), result.confidence),
            "status": "reviewed",
            "next_action": "policy_evaluate",
            "audit_events": events,
        }

    async def advisory_board(state: AgenticState) -> AgenticState:
        result = await advisor.advise(state["goal"], state["worker_output"])
        events = list(state.get("audit_events", []))
        events.append({"role": "advisor", "event": "advised", "confidence": result.confidence, "at": datetime.utcnow().isoformat()})
        return {
            "advisor_summary": result.text,
            "advisor_risks": result.risks or [],
            "status": "advised",
            "next_action": "policy_evaluate",
            "audit_events": events,
        }

    async def policy_evaluate(state: AgenticState) -> AgenticState:
        policy = _policy_from_state(state, default_policy)
        approval_reasons = evaluate_approval_reasons(state, policy)
        events = list(state.get("audit_events", []))
        events.append(
            {
                "role": "policy",
                "event": "evaluated",
                "approval_reasons": approval_reasons,
                "at": datetime.utcnow().isoformat(),
            },
        )
        return {
            "approval_reasons": approval_reasons,
            "status": "policy_evaluated",
            "next_action": "human_gate" if _needs_human(state, approval_reasons) else "finalize",
            "audit_events": events,
        }

    async def human_gate_plan(state: AgenticState) -> AgenticState:
        events = list(state.get("audit_events", []))
        events.append(
            {
                "role": "orchestrator",
                "event": "waiting_for_plan_approval",
                "approval_reasons": ["plan approval required by approval_mode=plan_once"],
                "at": datetime.utcnow().isoformat(),
            },
        )
        return {
            "status": "waiting_for_plan_approval",
            "next_action": "await_plan_approval",
            "approval_reasons": ["plan approval required by approval_mode=plan_once"],
            "audit_events": events,
        }

    async def human_gate(state: AgenticState) -> AgenticState:
        events = list(state.get("audit_events", []))
        events.append(
            {
                "role": "orchestrator",
                "event": "waiting_for_approval",
                "approval_reasons": state.get("approval_reasons", []),
                "at": datetime.utcnow().isoformat(),
            },
        )
        return {
            "status": "waiting_for_approval",
            "next_action": "await_approval",
            "audit_events": events,
        }

    async def finalize(state: AgenticState) -> AgenticState:
        events = list(state.get("audit_events", []))
        events.append({"role": "orchestrator", "event": "finalized", "at": datetime.utcnow().isoformat()})
        return {
            "status": "completed",
            "next_action": "done",
            "audit_events": events,
        }

    def route_entry(state: AgenticState) -> str:
        return state.get("resume_from", "manager_plan")

    def route_after_plan(state: AgenticState) -> str:
        return "human_gate_plan" if _needs_plan_gate(state) else "worker_execute"

    def route_after_review(state: AgenticState) -> str:
        if _needs_board(state):
            return "advisory_board"
        return "policy_evaluate"

    def route_after_board(state: AgenticState) -> str:
        return "policy_evaluate"

    def route_after_policy(state: AgenticState) -> str:
        return "human_gate" if _needs_human(state, state.get("approval_reasons", [])) else "finalize"

    graph = StateGraph(AgenticState)
    graph.add_node("entry_router", entry_router)
    graph.add_node("manager_plan", manager_plan)
    graph.add_node("worker_execute", worker_execute)
    graph.add_node("review_output", review_output)
    graph.add_node("advisory_board", advisory_board)
    graph.add_node("policy_evaluate", policy_evaluate)
    graph.add_node("human_gate_plan", human_gate_plan)
    graph.add_node("human_gate", human_gate)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("entry_router")
    graph.add_conditional_edges(
        "entry_router",
        route_entry,
        {
            "manager_plan": "manager_plan",
            "worker_execute": "worker_execute",
            "review_output": "review_output",
            "advisory_board": "advisory_board",
            "human_gate": "human_gate",
            "human_gate_plan": "human_gate_plan",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "manager_plan",
        route_after_plan,
        {
            "human_gate_plan": "human_gate_plan",
            "worker_execute": "worker_execute",
        },
    )
    graph.add_edge("worker_execute", "review_output")
    graph.add_conditional_edges(
        "review_output",
        route_after_review,
        {
            "advisory_board": "advisory_board",
            "policy_evaluate": "policy_evaluate",
        },
    )
    graph.add_conditional_edges(
        "advisory_board",
        route_after_board,
        {
            "policy_evaluate": "policy_evaluate",
        },
    )
    graph.add_conditional_edges(
        "policy_evaluate",
        route_after_policy,
        {
            "human_gate": "human_gate",
            "finalize": "finalize",
        },
    )
    graph.add_edge("human_gate_plan", END)
    graph.add_edge("human_gate", END)
    graph.add_edge("finalize", END)
    return graph.compile()


def _needs_board(state: AgenticState) -> bool:
    return state.get("risk_level") in {"medium", "high"} or state.get("confidence", 1.0) < 0.8


def _needs_human(state: AgenticState, approval_reasons: list[str]) -> bool:
    if state.get("approval_mode") == "policy_auto":
        return False
    if state.get("approval_mode") == "plan_once" and state.get("approved") is True:
        return False
    return len(approval_reasons) > 0


def _needs_plan_gate(state: AgenticState) -> bool:
    return state.get("approval_mode") == "plan_once" and state.get("approved") is not True


def _policy_from_state(state: AgenticState, default_policy: AgenticPolicyView) -> AgenticPolicyView:
    raw = state.get("policy")
    if isinstance(raw, dict):
        return AgenticPolicyView.model_validate(raw)
    return default_policy
