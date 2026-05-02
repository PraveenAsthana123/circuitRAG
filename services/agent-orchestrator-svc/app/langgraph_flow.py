from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from .agents import ManagerAgent, ReviewerAgent, SecurityAdvisor, WorkerAgent
from .models import AgenticPolicyView
from .policy import evaluate_approval_reasons

# Type-only import marker (avoid circular imports for the new agents).
# build_graph accepts Any for these so the legacy 4-agent path doesn't
# need them at all.


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
    # B3: review-loop retry counter. Incremented when review_output
    # routes back to worker_execute. Capped at MAX_REVIEW_ITERATIONS.
    retry_count: int


# B3: Lobster-style review-loop. After reviewer returns confidence,
# if score < REVIEW_THRESHOLD AND retry_count < MAX_REVIEW_ITERATIONS,
# the graph routes back to worker_execute with a bumped counter.
# Otherwise advances to advisory/policy.
#
# These thresholds are constants (not env-driven) because changing them
# silently changes pipeline behaviour for every task — the kind of
# decision §47 ADRs gate. Override via a future ADR-NNN if needed.
MAX_REVIEW_ITERATIONS = 3
REVIEW_THRESHOLD = 0.7


def build_graph(
    *,
    manager: ManagerAgent,
    worker: WorkerAgent,
    reviewer: ReviewerAgent,
    advisor: SecurityAdvisor,
    default_policy: AgenticPolicyView,
    # D1: pipeline-v2 optional agents. When provided, build_graph
    # inserts the corresponding nodes + edges. When omitted, the
    # graph is identical to pre-D1 (backward compat per §28).
    strategist: Any = None,
    researcher: Any = None,
    tester: Any = None,
    deployer: Any = None,
):
    from langgraph.graph import END, StateGraph

    # NOTE: a `pipeline_v2 = (strategist|researcher|tester|deployer) is not None`
    # local previously lived here for an upcoming router gate but was never
    # consumed; ruff F841 caught it. The router decision is made downstream
    # via the per-spec model + Tier-A/B routing, so the local was redundant.

    async def entry_router(state: AgenticState) -> AgenticState:
        return state

    async def strategist_classify(state: AgenticState) -> AgenticState:
        # D1: classify task complexity/novelty so downstream nodes can
        # consult them when routing. Strategist always runs at Tier B
        # when pipeline_v2 + cloud CLI available; otherwise heuristic.
        result = await strategist.classify(state["goal"])
        events = list(state.get("audit_events", []))
        events.append({
            "role": "strategist",
            "event": "classified",
            "complexity": result.get("overall_complexity"),
            "novelty": result.get("overall_novelty"),
            "needs_research": result.get("needs_research"),
            "source": result.get("source"),
            "at": datetime.utcnow().isoformat(),
        })
        return {
            "complexity": result.get("overall_complexity"),
            "novelty": result.get("overall_novelty"),
            "needs_research": bool(result.get("needs_research")),
            "strategist_summary": result.get("summary"),
            "status": "classified",
            "audit_events": events,
        }

    async def researcher_node(state: AgenticState) -> AgenticState:
        # D1: researcher runs only when strategist set needs_research=True.
        out = await researcher.research(
            state["goal"],
            complexity=state.get("complexity") or "high",
            novelty=state.get("novelty") or "novel",
        )
        events = list(state.get("audit_events", []))
        events.append({
            "role": "researcher", "event": "researched",
            "source": out.get("source_origin"),
            "sources_count": len(out.get("sources") or []),
            "at": datetime.utcnow().isoformat(),
        })
        return {
            "research_summary": out.get("summary"),
            "research_sources": out.get("sources") or [],
            "research_risks": out.get("risks") or [],
            "status": "researched",
            "audit_events": events,
        }

    async def tester_node(state: AgenticState) -> AgenticState:
        # D1: tester runs after review_output (when not retrying coder)
        # and before policy_evaluate. Failing tests cause retry-back
        # to worker_execute with bumped retry counter (max 3 — same
        # cap as B3 review-loop).
        out = await tester.run_tests(
            worker_output=state.get("worker_output") or "",
            complexity=state.get("complexity") or "medium",
            novelty=state.get("novelty") or "routine",
        )
        events = list(state.get("audit_events", []))
        events.append({
            "role": "tester", "event": "ran",
            "passed": out.get("passed"),
            "runner": out.get("runner"),
            "source": out.get("source_origin"),
            "at": datetime.utcnow().isoformat(),
        })
        return {
            "tests_passed": bool(out.get("passed")),
            "tests_failed": out.get("failed") or [],
            "tests_runner": out.get("runner"),
            "status": "tested",
            "audit_events": events,
        }

    async def deployer_preflight(state: AgenticState) -> AgenticState:
        # D1: §42 HARD STOP — deployer.preflight() NEVER auto-applies.
        # It produces a preflight report that the operator reviews
        # before approving the actual deploy (POST .../approve).
        out = await deployer.preflight(
            diff_summary=state.get("worker_output") or "",
            target="docker-compose",
            complexity=state.get("complexity") or "high",
            novelty=state.get("novelty") or "routine",
        )
        events = list(state.get("audit_events", []))
        events.append({
            "role": "deployer", "event": "preflight",
            "deploy_safety": out.get("deploy_safety"),
            "auto_applied": out.get("auto_applied"),  # always False (drilled)
            "approval_required": out.get("approval_required"),  # always True
            "at": datetime.utcnow().isoformat(),
        })
        # Preflight ALWAYS sets approval_required=True (§42). The graph
        # routes to human_gate after this node — never auto-finalises
        # a deploy without the operator's approve_task call.
        approval_reasons = list(state.get("approval_reasons") or [])
        approval_reasons.append("deploy step requires human approval (§42 hard stop)")
        return {
            "deployer_safety": out.get("deploy_safety"),
            "deployer_summary": out.get("summary"),
            "approval_reasons": approval_reasons,
            "status": "deploy_preflight_complete",
            "audit_events": events,
        }

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
        events.append({
            "role": "reviewer",
            "event": "reviewed",
            "confidence": result.confidence,
            "retry_count": state.get("retry_count", 0),
            "at": datetime.utcnow().isoformat(),
        })
        return {
            "reviewer_notes": [result.text],
            "reviewer_risks": result.risks or [],
            "confidence": min(state.get("confidence", 1.0), result.confidence),
            "status": "reviewed",
            "next_action": "policy_evaluate",
            "audit_events": events,
        }

    async def review_retry_bump(state: AgenticState) -> AgenticState:
        """B3: bump retry_count + audit before looping back to worker_execute.

        Separated from review_output so the conditional edge logic stays
        readable: review_output → router → review_retry_bump → worker_execute.
        """
        current = int(state.get("retry_count", 0))
        events = list(state.get("audit_events", []))
        events.append({
            "role": "orchestrator",
            "event": "review_retry",
            "from_retry_count": current,
            "to_retry_count": current + 1,
            "reviewer_confidence": state.get("confidence"),
            "at": datetime.utcnow().isoformat(),
        })
        return {
            "retry_count": current + 1,
            "status": "review_retry",
            "next_action": "worker_execute",
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
        # B3: Lobster-style review-loop. If reviewer is unconvinced
        # AND we haven't blown the retry cap, loop back to worker_execute.
        # Negative-assertion contract (drilled): retry_count >= 3 must
        # exit the loop and never re-enter worker_execute.
        confidence = float(state.get("confidence") or 1.0)
        retry_count = int(state.get("retry_count", 0))
        if confidence < REVIEW_THRESHOLD and retry_count < MAX_REVIEW_ITERATIONS:
            return "review_retry_bump"
        if _needs_board(state):
            return "advisory_board"
        return "policy_evaluate"

    def route_after_board(state: AgenticState) -> str:
        return "policy_evaluate"

    def route_after_policy(state: AgenticState) -> str:
        return "human_gate" if _needs_human(state, state.get("approval_reasons", [])) else "finalize"

    graph = StateGraph(AgenticState)
    graph.add_node("entry_router", entry_router)
    if strategist is not None:
        graph.add_node("strategist_classify", strategist_classify)
    if researcher is not None:
        graph.add_node("researcher_node", researcher_node)
    graph.add_node("manager_plan", manager_plan)
    graph.add_node("worker_execute", worker_execute)
    graph.add_node("review_output", review_output)
    graph.add_node("review_retry_bump", review_retry_bump)  # B3
    if tester is not None:
        graph.add_node("tester_node", tester_node)
    graph.add_node("advisory_board", advisory_board)
    graph.add_node("policy_evaluate", policy_evaluate)
    if deployer is not None:
        graph.add_node("deployer_preflight", deployer_preflight)
    graph.add_node("human_gate_plan", human_gate_plan)
    graph.add_node("human_gate", human_gate)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("entry_router")

    # D1: when v2, strategist_classify becomes the FIRST node after
    # entry_router. When researcher is present, strategist routes
    # through a 'needs_research?' conditional. When neither, the
    # legacy flow (entry → manager_plan) preserves.
    entry_dispatch = {
        "manager_plan": "manager_plan",
        "worker_execute": "worker_execute",
        "review_output": "review_output",
        "advisory_board": "advisory_board",
        "human_gate": "human_gate",
        "human_gate_plan": "human_gate_plan",
        "finalize": "finalize",
    }
    if strategist is not None:
        entry_dispatch["strategist_classify"] = "strategist_classify"
    graph.add_conditional_edges("entry_router", route_entry, entry_dispatch)

    if strategist is not None:
        # strategist → researcher (if needs_research) or → manager_plan
        def _route_after_strategist(state: AgenticState) -> str:
            if researcher is not None and state.get("needs_research"):
                return "researcher_node"
            return "manager_plan"

        post_strat_dispatch: dict[str, str] = {"manager_plan": "manager_plan"}
        if researcher is not None:
            post_strat_dispatch["researcher_node"] = "researcher_node"
        graph.add_conditional_edges("strategist_classify", _route_after_strategist, post_strat_dispatch)

    if researcher is not None:
        graph.add_edge("researcher_node", "manager_plan")
    graph.add_conditional_edges(
        "manager_plan",
        route_after_plan,
        {
            "human_gate_plan": "human_gate_plan",
            "worker_execute": "worker_execute",
        },
    )
    graph.add_edge("worker_execute", "review_output")
    review_dispatch = {
        "review_retry_bump": "review_retry_bump",  # B3 retry path
        "advisory_board": "advisory_board",
        "policy_evaluate": "policy_evaluate",
    }
    if tester is not None:
        # When tester wired, review's success path goes through tester first.
        review_dispatch["tester_node"] = "tester_node"

    def _route_after_review_v2(state: AgenticState) -> str:
        # D1 extension of route_after_review: when tester is wired and
        # review passes, route to tester_node before advisory/policy.
        confidence = float(state.get("confidence") or 1.0)
        retry_count = int(state.get("retry_count", 0))
        if confidence < REVIEW_THRESHOLD and retry_count < MAX_REVIEW_ITERATIONS:
            return "review_retry_bump"
        if tester is not None:
            return "tester_node"
        if _needs_board(state):
            return "advisory_board"
        return "policy_evaluate"

    graph.add_conditional_edges(
        "review_output",
        _route_after_review_v2 if tester is not None else route_after_review,
        review_dispatch,
    )
    graph.add_edge("review_retry_bump", "worker_execute")  # B3 loop closure

    if tester is not None:
        # tester → if pass and risk warrants, advisor; else policy.
        def _route_after_tester(state: AgenticState) -> str:
            # Failed tests + retry available → loop to coder.
            if not state.get("tests_passed") and int(state.get("retry_count", 0)) < MAX_REVIEW_ITERATIONS:
                return "review_retry_bump"
            if _needs_board(state):
                return "advisory_board"
            return "policy_evaluate"

        graph.add_conditional_edges(
            "tester_node",
            _route_after_tester,
            {
                "review_retry_bump": "review_retry_bump",
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
    # D1: when deployer wired, the no-gate path from policy_evaluate
    # goes through deployer_preflight first (which ALWAYS adds an
    # approval_reason → routes to human_gate per §42).
    policy_dispatch = {
        "human_gate": "human_gate",
        "finalize": "finalize",
    }
    if deployer is not None:
        policy_dispatch["deployer_preflight"] = "deployer_preflight"

    def _route_after_policy_v2(state: AgenticState) -> str:
        # If approval already needed, gate (existing behavior).
        if _needs_human(state, state.get("approval_reasons", [])):
            return "human_gate"
        # Otherwise: when deployer wired, run preflight (which will
        # itself force human_gate via §42). When not, finalize.
        if deployer is not None:
            return "deployer_preflight"
        return "finalize"

    graph.add_conditional_edges(
        "policy_evaluate",
        _route_after_policy_v2 if deployer is not None else route_after_policy,
        policy_dispatch,
    )

    if deployer is not None:
        # deployer_preflight ALWAYS goes to human_gate (§42 hard stop)
        graph.add_edge("deployer_preflight", "human_gate")

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
