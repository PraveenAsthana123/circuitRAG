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
        # P1 #21 — caching layer. Eliminates duplicate fetches on
        # repeat queries for the same topic. cache_ttl_s default 1
        # hour; cache_max default 100 entries (~1 MB at typical
        # research-result size). Set cache_max=0 to disable.
        cache_ttl_s: float = 3600.0,
        cache_max: int = 100,
    ) -> None:
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._mcp = mcp_research_client
        self._role_id = role_id
        self._cache_ttl_s = max(0.0, cache_ttl_s)
        self._cache_max = max(0, cache_max)
        # P1 #21: LRU cache. OrderedDict for eviction; entries are
        # (timestamp, result_dict). Bounded by cache_max.
        import threading as _threading
        from collections import OrderedDict
        self._cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._cache_lock = _threading.Lock()

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
                    escape = False
                    continue
                if c == "\\":
                    escape = True
                    continue
                if c == '"':
                    in_str = not in_str
                    continue
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
        research_timeout_s: float = 60.0,
    ) -> dict[str, Any]:
        # P1 #21: cache check BEFORE timeout/LLM path.
        cached = self._cache_get(topic)
        if cached is not None:
            cached["cache_hit"] = True
            return cached
        # P0 #1: own deadline.
        import asyncio as _asyncio
        try:
            result = await _asyncio.wait_for(
                self._research_unbounded(topic, complexity=complexity, novelty=novelty),
                timeout=research_timeout_s,
            )
        except TimeoutError:
            heuristic = self._heuristic_research(topic)
            heuristic["llm_unavailable"] = f"researcher exceeded {research_timeout_s}s"
            return heuristic
        # P1 #21: cache the successful result. Heuristic-fallback results
        # get cached too (they're sticky for the cache_ttl_s window —
        # operators who fix the upstream don't need to wait for the cache
        # to expire because clear_cache() is exposed).
        self._cache_put(topic, result)
        result["cache_hit"] = False
        return result

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if self._cache_max <= 0:
            return None
        import time as _time
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, value = entry
            if _time.monotonic() - ts > self._cache_ttl_s:
                del self._cache[key]
                return None
            # Move-to-end for LRU.
            self._cache.move_to_end(key)
            # Return a copy so callers can mutate without affecting cache.
            return dict(value)

    def _cache_put(self, key: str, value: dict[str, Any]) -> None:
        if self._cache_max <= 0:
            return
        import time as _time
        with self._cache_lock:
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = (_time.monotonic(), dict(value))
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)

    def clear_cache(self) -> int:
        """Operator hook — drop all cached research results. Returns
        the number of entries evicted (for observability)."""
        with self._cache_lock:
            n = len(self._cache)
            self._cache.clear()
            return n

    async def _research_unbounded(
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
            except Exception:  # noqa: BLE001, S110 — fall through to LLM
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
