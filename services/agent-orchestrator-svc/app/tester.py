"""TesterAgent (Phase B4 scaffold).

Three-tier behaviour like ResearchAgent:
  1. mcp_tests_client (production): runs pytest/jest/ruff/mypy via MCP.
  2. routed LLM: classifies failure log + suggests fix.
  3. heuristic: returns 'tests not run' with passed=False conservative
     default. Conservative because: 'unknown' must NEVER silently pass
     as 'green'. Pipeline routes back to coder if passed=False.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .llm_clients import AllBackendsUnavailable, LlmClientPool

RouteFn = Any


class TesterAgent:
    def __init__(
        self,
        *,
        ollama=None, spec=None,
        pool: LlmClientPool | None = None, route_fn: RouteFn | None = None,
        mcp_tests_client=None,
        role_id: str = "tester",
    ) -> None:
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._mcp = mcp_tests_client
        self._role_id = role_id

    @staticmethod
    def _heuristic(runner: str = "pytest") -> dict[str, Any]:
        return {
            "runner": runner,
            "passed": False,  # conservative: unknown ≠ green
            "failed": [],
            "coverage_pct": None,
            "log_tail": "Tester not yet wired to mcp_tests; result is conservative placeholder.",
            "source_origin": "heuristic_fallback",
        }

    async def run_tests(
        self,
        *,
        worker_output: str,
        runner: str = "pytest",
        complexity: str = "medium",
        novelty: str = "routine",
        tests_timeout_s: float = 180.0,
    ) -> dict[str, Any]:
        import asyncio as _asyncio
        try:
            return await _asyncio.wait_for(
                self._run_tests_unbounded(
                    worker_output=worker_output, runner=runner,
                    complexity=complexity, novelty=novelty,
                ),
                timeout=tests_timeout_s,
            )
        except TimeoutError:
            heuristic = self._heuristic(runner)
            heuristic["llm_unavailable"] = f"tester exceeded {tests_timeout_s}s"
            return heuristic

    async def _run_tests_unbounded(
        self,
        *,
        worker_output: str,
        runner: str = "pytest",
        complexity: str = "medium",
        novelty: str = "routine",
    ) -> dict[str, Any]:
        if self._mcp is not None:
            try:
                result = await self._mcp.call_tool(
                    f"tests.run_{runner}",
                    {"target": worker_output},
                    tenant_id="",
                )
                if result.ok:
                    payload = dict(result.data)
                    payload["source_origin"] = "mcp_tests"
                    payload.setdefault("runner", runner)
                    return payload
            except Exception:  # noqa: BLE001, S110
                pass

        if self._pool is not None and self._route_fn is not None and self._spec is not None:
            try:
                from .agents import _routed_generate
                prompt = (
                    f"Analyse the following code/diff for likely test outcomes.\n"
                    f"Output: {{\"passed\":<bool>,\"failed\":[],\"runner\":\"{runner}\"}}\n\n"
                    f"Code:\n{worker_output[:2000]}"
                )
                text, routing, t_in, t_out, cost = await _routed_generate(
                    pool=self._pool, route_fn=self._route_fn, role_id=self._role_id,
                    prompt=prompt, complexity=complexity, novelty=novelty,
                )
                # Try parse; fall back to heuristic conservatively.
                try:
                    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
                    obj = json.loads(cleaned[cleaned.find("{"):cleaned.rfind("}") + 1])
                    if isinstance(obj, dict) and "passed" in obj:
                        obj.setdefault("runner", runner)
                        obj.setdefault("failed", [])
                        obj["source_origin"] = "llm_routed"
                        obj["routing"] = routing
                        obj["cost_usd_cents"] = cost
                        return obj
                except (json.JSONDecodeError, ValueError):
                    pass
                heuristic = self._heuristic(runner)
                heuristic["llm_text_unparseable"] = text[:200]
                heuristic["routing"] = routing
                return heuristic
            except AllBackendsUnavailable as exc:
                heuristic = self._heuristic(runner)
                heuristic["llm_unavailable"] = str(exc)
                return heuristic

        return self._heuristic(runner)
