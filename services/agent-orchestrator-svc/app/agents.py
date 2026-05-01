"""Agentic role implementations.

Phase A4 adds optional router-based LLM dispatch alongside the legacy
ollama+spec path. When `pool` and `route_fn` are provided to an agent,
generation flows: route_fn → ModelHandle → pool.execute → LlmCallResult.
When they aren't, the agent falls back to spec.model + OllamaGenerateClient
exactly as before A4.

Why the dual path: existing tests (tests/test_smoke.py) instantiate agents
with the legacy signature. Breaking them on A4 would make every later
phase ride on red tests. Backward-compatible by construction; B-track
phases will opt the agents in to the router path.

The routed path returns AgentOutput.routing — a dict carrying handle_used,
fallback_log, and cost_usd_cents. Service.py reads this and writes it
into the task_runs.outputs payload (A5 adds the column).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from mcp import MCPClient

from .agent_registry import AgentRoleSpec
from .llm_clients import AllBackendsUnavailable, LlmClientPool
from .ollama_client import OllamaGenerateClient


# Type alias: route_fn returns RouteDecision but we keep this loose so
# agents.py doesn't import model_router (avoids tight coupling — the pool
# only needs duck typing on `chosen` + `fallback_chain`).
RouteFn = Callable[..., Any]


@dataclass(frozen=True)
class AgentOutput:
    text: str
    confidence: float = 0.8
    risks: list[str] | None = None
    routing: dict[str, Any] | None = None  # A4: handle_used + fallback + cost
    cost_usd_cents: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


async def _routed_generate(
    *,
    pool: LlmClientPool,
    route_fn: RouteFn,
    role_id: str,
    prompt: str,
    complexity: str = "medium",
    novelty: str = "routine",
    timeout_seconds: float = 60.0,
) -> tuple[str, dict[str, Any], int, int, int]:
    """Run prompt through the router + pool. Returns (text, routing_dict,
    tokens_in, tokens_out, cost_cents).

    Raises AllBackendsUnavailable if every handle in the chain fails.
    Caller (the agent) catches and degrades the AgentOutput to a low-
    confidence placeholder so the graph keeps moving rather than dying.
    """
    decision = route_fn(
        role_id=role_id,
        complexity=complexity,
        novelty=novelty,
        has_tier_b=pool.has_tier_b(),
    )
    outcome = await pool.execute(
        decision=decision,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
    )
    routing = {
        "decision": decision.to_dict(),
        "handle_used": outcome.handle_used,
        "fallback_log": outcome.fallback_log,
    }
    return (
        outcome.result.text,
        routing,
        outcome.result.tokens_in,
        outcome.result.tokens_out,
        outcome.result.cost_usd_cents,
    )


class ManagerAgent:
    async def plan(self, goal: str) -> list[str]:
        return [
            "classify task",
            "execute bounded worker step",
            "review output",
            "request advisory review if needed",
            "finalize or wait for approval",
        ]

    async def expand_project(self, goal: str) -> list[dict[str, Any]]:
        return [
            {
                "step_id": "scope",
                "title": "Scope and classify project",
                "goal": f"Break down the project goal into concrete work items: {goal}",
                "suggested_risk": "low",
            },
            {
                "step_id": "execute",
                "title": "Execute primary implementation step",
                "goal": f"Perform the main implementation work for: {goal}",
                "suggested_risk": "medium",
            },
            {
                "step_id": "review",
                "title": "Review and validate outputs",
                "goal": f"Review outputs, validate edge cases, and summarize risks for: {goal}",
                "suggested_risk": "medium",
            },
            {
                "step_id": "finalize",
                "title": "Finalize and hand off",
                "goal": f"Prepare final completion summary and handoff artifacts for: {goal}",
                "suggested_risk": "low",
            },
        ]


class WorkerAgent:
    def __init__(
        self,
        *,
        mcp_clients: dict[str, MCPClient] | None = None,
        ollama: OllamaGenerateClient | None = None,
        spec: AgentRoleSpec | None = None,
        # A4: new router path (optional). When BOTH pool and route_fn are set,
        # the agent uses the routed path; otherwise legacy ollama path.
        pool: LlmClientPool | None = None,
        route_fn: RouteFn | None = None,
        role_id: str = "coder_executor",
    ) -> None:
        self._mcp_clients = mcp_clients or {}
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._role_id = role_id

    async def run(
        self,
        goal: str,
        *,
        tenant_id: str,
        tool_namespace: str | None = None,
        tool_name: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
        complexity: str = "medium",
        novelty: str = "routine",
    ) -> AgentOutput:
        if tool_namespace and tool_name:
            client = self._mcp_clients.get(tool_namespace)
            if client is None:
                return AgentOutput(
                    text=f"No MCP client configured for namespace '{tool_namespace}'.",
                    confidence=0.25,
                    risks=[f"missing MCP namespace: {tool_namespace}"],
                )
            result = await client.call_tool(
                tool_name,
                tool_arguments or {},
                tenant_id=tenant_id,
            )
            if result.ok:
                return AgentOutput(
                    text=f"MCP tool {tool_namespace}.{tool_name} succeeded: {result.data}",
                    confidence=0.84,
                    risks=[],
                )
            if result.degraded:
                return AgentOutput(
                    text=f"MCP tool {tool_namespace}.{tool_name} degraded to draft {result.draft_id}.",
                    confidence=0.52,
                    risks=["tool execution degraded to draft fallback"],
                )
            return AgentOutput(
                text=f"MCP tool {tool_namespace}.{tool_name} failed: {result.error}",
                confidence=0.31,
                risks=["tool execution failed"],
            )

        # New routed path (A4+): take precedence when both pool and route_fn set.
        if self._pool is not None and self._route_fn is not None and self._spec is not None:
            tool_context = (
                f"namespace={tool_namespace!r} name={tool_name!r} args={tool_arguments or {}}"
                if tool_namespace or tool_name
                else "no tool requested"
            )
            prompt = self._spec.prompt_template.format(
                tenant_id=tenant_id,
                goal=goal,
                tool_context=tool_context,
            )
            try:
                text, routing, t_in, t_out, cost = await _routed_generate(
                    pool=self._pool,
                    route_fn=self._route_fn,
                    role_id=self._role_id,
                    prompt=prompt,
                    complexity=complexity,
                    novelty=novelty,
                )
            except AllBackendsUnavailable as exc:
                return AgentOutput(
                    text=f"Worker LLM unavailable: {exc}",
                    confidence=0.30,
                    risks=["all routed backends failed"],
                    routing={"errors": [{"handle": h, "error": e} for h, e in exc.errors]},
                )
            confidence = 0.86 if text else 0.42
            risks = [] if text else ["routed worker returned empty output"]
            return AgentOutput(
                text=text or "Executor returned no content.",
                confidence=confidence,
                risks=risks,
                routing=routing,
                tokens_in=t_in,
                tokens_out=t_out,
                cost_usd_cents=cost,
            )

        # Legacy ollama path (pre-A4 callers).
        if self._ollama is not None and self._spec is not None:
            tool_context = (
                f"namespace={tool_namespace!r} name={tool_name!r} args={tool_arguments or {}}"
                if tool_namespace or tool_name
                else "no tool requested"
            )
            prompt = self._spec.prompt_template.format(
                tenant_id=tenant_id,
                goal=goal,
                tool_context=tool_context,
            )
            text = await self._ollama.generate(model=self._spec.model, prompt=prompt)
            confidence = 0.86 if text else 0.42
            risks = [] if text else ["ollama returned empty executor output"]
            return AgentOutput(
                text=text or "Executor returned no content.",
                confidence=confidence,
                risks=risks,
            )

        return AgentOutput(
            text=f"Worker completed non-tool goal: {goal}",
            confidence=0.78,
            risks=["result is placeholder non-tool output"],
        )


def _parse_score(text: str) -> float:
    score = 0.81
    if "SCORE:" in text:
        try:
            score_value = int(text.rsplit("SCORE:", 1)[1].strip().split()[0])
            score = max(0.0, min(1.0, score_value / 10))
        except ValueError:
            score = 0.74
    return score


class ReviewerAgent:
    def __init__(
        self,
        *,
        ollama: OllamaGenerateClient | None = None,
        spec: AgentRoleSpec | None = None,
        pool: LlmClientPool | None = None,
        route_fn: RouteFn | None = None,
        role_id: str = "reviewer",
    ) -> None:
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._role_id = role_id

    async def review(
        self,
        goal: str,
        worker_output: str,
        *,
        complexity: str = "medium",
        novelty: str = "routine",
    ) -> AgentOutput:
        if self._pool is not None and self._route_fn is not None and self._spec is not None:
            prompt = self._spec.prompt_template.format(goal=goal, worker_output=worker_output)
            try:
                text, routing, t_in, t_out, cost = await _routed_generate(
                    pool=self._pool,
                    route_fn=self._route_fn,
                    role_id=self._role_id,
                    prompt=prompt,
                    complexity=complexity,
                    novelty=novelty,
                )
            except AllBackendsUnavailable as exc:
                return AgentOutput(
                    text=f"Reviewer LLM unavailable: {exc}",
                    confidence=0.30,
                    risks=["all routed backends failed"],
                    routing={"errors": [{"handle": h, "error": e} for h, e in exc.errors]},
                )
            score = _parse_score(text)
            return AgentOutput(
                text=text,
                confidence=score,
                risks=[] if score >= 0.6 else ["reviewer found low-confidence or weak output"],
                routing=routing,
                tokens_in=t_in,
                tokens_out=t_out,
                cost_usd_cents=cost,
            )

        if self._ollama is not None and self._spec is not None:
            text = await self._ollama.generate(
                model=self._spec.model,
                prompt=self._spec.prompt_template.format(goal=goal, worker_output=worker_output),
            )
            score = _parse_score(text)
            return AgentOutput(
                text=text,
                confidence=score,
                risks=[] if score >= 0.6 else ["reviewer found low-confidence or weak output"],
            )
        return AgentOutput(
            text=f"Reviewer checked output: {worker_output}",
            confidence=0.81,
            risks=[],
        )


class SecurityAdvisor:
    def __init__(
        self,
        *,
        ollama: OllamaGenerateClient | None = None,
        spec: AgentRoleSpec | None = None,
        pool: LlmClientPool | None = None,
        route_fn: RouteFn | None = None,
        role_id: str = "security_advisor",
    ) -> None:
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._role_id = role_id

    async def advise(
        self,
        goal: str,
        worker_output: str,
        *,
        complexity: str = "medium",
        novelty: str = "routine",
    ) -> AgentOutput:
        if self._pool is not None and self._route_fn is not None and self._spec is not None:
            prompt = self._spec.prompt_template.format(goal=goal, worker_output=worker_output)
            try:
                text, routing, t_in, t_out, cost = await _routed_generate(
                    pool=self._pool,
                    route_fn=self._route_fn,
                    role_id=self._role_id,
                    prompt=prompt,
                    complexity=complexity,
                    novelty=novelty,
                )
            except AllBackendsUnavailable as exc:
                return AgentOutput(
                    text=f"Security advisor LLM unavailable: {exc}",
                    confidence=0.30,
                    risks=["all routed backends failed", "security_advisor degraded"],
                    routing={"errors": [{"handle": h, "error": e} for h, e in exc.errors]},
                )
            risks = []
            lowered = text.lower()
            if any(token in lowered for token in ("blocking", "secret", "auth", "unsafe", "injection")):
                risks.append("security advisor flagged a potential control issue")
            return AgentOutput(
                text=text,
                confidence=0.79 if text else 0.45,
                risks=risks,
                routing=routing,
                tokens_in=t_in,
                tokens_out=t_out,
                cost_usd_cents=cost,
            )

        if self._ollama is not None and self._spec is not None:
            text = await self._ollama.generate(
                model=self._spec.model,
                prompt=self._spec.prompt_template.format(goal=goal, worker_output=worker_output),
            )
            lowered = text.lower()
            risks = []
            if any(token in lowered for token in ("blocking", "secret", "auth", "unsafe", "injection")):
                risks.append("security advisor flagged a potential control issue")
            return AgentOutput(
                text=text,
                confidence=0.79 if text else 0.45,
                risks=risks,
            )
        return AgentOutput(
            text=f"Security advisor reviewed goal '{goal}' and found no blocking issue in skeleton flow.",
            confidence=0.74,
            risks=["real implementation must enforce tool allowlists and approval policy"],
        )
