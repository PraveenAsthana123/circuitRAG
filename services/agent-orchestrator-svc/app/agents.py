from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp import MCPClient

from .agent_registry import AgentRoleSpec
from .ollama_client import OllamaGenerateClient


@dataclass(frozen=True)
class AgentOutput:
    text: str
    confidence: float = 0.8
    risks: list[str] | None = None


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
    ) -> None:
        self._mcp_clients = mcp_clients or {}
        self._ollama = ollama
        self._spec = spec

    async def run(
        self,
        goal: str,
        *,
        tenant_id: str,
        tool_namespace: str | None = None,
        tool_name: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
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


class ReviewerAgent:
    def __init__(self, *, ollama: OllamaGenerateClient | None = None, spec: AgentRoleSpec | None = None) -> None:
        self._ollama = ollama
        self._spec = spec

    async def review(self, goal: str, worker_output: str) -> AgentOutput:
        if self._ollama is not None and self._spec is not None:
            text = await self._ollama.generate(
                model=self._spec.model,
                prompt=self._spec.prompt_template.format(goal=goal, worker_output=worker_output),
            )
            score = 0.81
            if "SCORE:" in text:
                try:
                    score_value = int(text.rsplit("SCORE:", 1)[1].strip().split()[0])
                    score = max(0.0, min(1.0, score_value / 10))
                except ValueError:
                    score = 0.74
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
    def __init__(self, *, ollama: OllamaGenerateClient | None = None, spec: AgentRoleSpec | None = None) -> None:
        self._ollama = ollama
        self._spec = spec

    async def advise(self, goal: str, worker_output: str) -> AgentOutput:
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
