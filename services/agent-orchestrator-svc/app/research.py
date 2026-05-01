"""ResearchAgent (Phase B2 scaffold).

Three-tier behaviour mirroring StrategistAgent (B1):
  1. Routed LLM (when pool+route_fn wired): runs research prompt,
     parses JSON output { summary, sources[], suggested_approach, risks[] }.
  2. Direct Ollama (legacy): same parse path.
  3. Heuristic fallback: returns conservative empty research with
     'consult upstream MCP_research when wired' note.

The 'real' integration — web search + RAG retrieval + Microsoft Docs
MCP composite — lives behind mcp/server_research.py (future commit).
This module talks to that server through MCPClient when available;
otherwise relies on the LLM-routed or heuristic path.

§48.5 four-part contract: when wired to mcp_research, this agent
returns retrieval_trail (chunk IDs + similarity scores) so downstream
nodes can map answer-spans back to source chunks. The artifact row
in orchestration.research_artifacts persists the trail.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .llm_clients import AllBackendsUnavailable, LlmClientPool


# Type alias — see app/agents.py::RouteFn comment.
RouteFn = Any


class ResearchAgent:
    def __init__(
        self,
        *,
        ollama=None,
        spec=None,
        pool: LlmClientPool | None = None,
        route_fn: RouteFn | None = None,
        mcp_research_client=None,  # set by service.py when MCP server wired
        role_id: str = "researcher",
    ) -> None:
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._mcp = mcp_research_client
        self._role_id = role_id

    @staticmethod
    def _heuristic_research(topic: str) -> dict[str, Any]:
        """Conservative fallback. Marks 'no real sources' so downstream
        nodes treat the result as low-confidence."""
        return {
            "topic": topic,
            "summary": f"No upstream research available for: {topic}",
            "sources": [],
            "suggested_approach": "Defer to manual research; flag for operator review.",
            "risks": ["no upstream research; suggestion based on heuristic only"],
            "source_origin": "heuristic_fallback",
        }

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        """Bracket-aware JSON extraction (mirrors StrategistAgent._parse_json_classification)."""
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = cleaned.replace("```", "").strip()
        for start in range(len(cleaned)):
            if cleaned[start] != "{":
                continue
            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(cleaned)):
                c = cleaned[i]
                if escape:
                    escape = False; continue
                if c == "\\":
                    escape = True; continue
                if c == '"':
                    in_str = not in_str; continue
                if in_str:
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = cleaned[start:i + 1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict) and ("summary" in obj or "sources" in obj):
                                return obj
                        except json.JSONDecodeError:
                            pass
                        break
        return None

    async def research(
        self,
        topic: str,
        *,
        complexity: str = "high",
        novelty: str = "novel",
    ) -> dict[str, Any]:
        # MCP research server path (when wired) — the production path.
        if self._mcp is not None:
            try:
                result = await self._mcp.call_tool(
                    "research.synthesize",
                    {"topic": topic},
                    tenant_id="",  # set by caller; placeholder for stub
                )
                if result.ok:
                    payload = dict(result.data)
                    payload["source_origin"] = "mcp_research"
                    payload.setdefault("topic", topic)
                    return payload
            except Exception:  # noqa: BLE001 — fall through to LLM
                pass

        # Routed LLM path.
        if self._pool is not None and self._route_fn is not None and self._spec is not None:
            try:
                from .agents import _routed_generate  # local import to avoid cycle
                prompt_template = getattr(self._spec, "prompt_template", None)
                if prompt_template is None:
                    return self._heuristic_research(topic)
                prompt = prompt_template.format(goal=topic) if "{goal}" in prompt_template else f"Research topic: {topic}"
                text, routing, t_in, t_out, cost = await _routed_generate(
                    pool=self._pool,
                    route_fn=self._route_fn,
                    role_id=self._role_id,
                    prompt=prompt,
                    complexity=complexity,
                    novelty=novelty,
                )
                parsed = self._parse_json(text)
                if parsed is not None:
                    parsed.setdefault("topic", topic)
                    parsed.setdefault("sources", [])
                    parsed.setdefault("risks", [])
                    parsed["source_origin"] = "llm_routed"
                    parsed["routing"] = routing
                    parsed["tokens_in"] = t_in
                    parsed["tokens_out"] = t_out
                    parsed["cost_usd_cents"] = cost
                    return parsed
                heuristic = self._heuristic_research(topic)
                heuristic["llm_text_unparseable"] = text[:300]
                heuristic["routing"] = routing
                return heuristic
            except AllBackendsUnavailable as exc:
                heuristic = self._heuristic_research(topic)
                heuristic["llm_unavailable"] = str(exc)
                return heuristic

        return self._heuristic_research(topic)
