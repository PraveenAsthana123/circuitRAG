"""DeployerAgent (Phase B5 scaffold).

§42 HARD STOP: this agent never auto-applies a deploy. Its job is
pre-flight summary + risk identification. The actual apply call goes
through service.py with explicit ApprovalRequest gating.
"""
from __future__ import annotations

from typing import Any

from .llm_clients import AllBackendsUnavailable, LlmClientPool

RouteFn = Any


class DeployerAgent:
    def __init__(
        self, *,
        ollama=None, spec=None,
        pool: LlmClientPool | None = None, route_fn: RouteFn | None = None,
        mcp_deploy_client=None,
        role_id: str = "deployer",
    ) -> None:
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._mcp = mcp_deploy_client
        self._role_id = role_id

    async def preflight(
        self, *, diff_summary: str, target: str = "docker-compose",
        complexity: str = "high", novelty: str = "routine",
        preflight_timeout_s: float = 60.0,
    ) -> dict[str, Any]:
        import asyncio as _asyncio
        try:
            return await _asyncio.wait_for(
                self._preflight_unbounded(
                    diff_summary=diff_summary, target=target,
                    complexity=complexity, novelty=novelty,
                ),
                timeout=preflight_timeout_s,
            )
        except TimeoutError:
            return self._heuristic(diff_summary, target, error=f"deployer exceeded {preflight_timeout_s}s")

    async def _preflight_unbounded(
        self, *, diff_summary: str, target: str = "docker-compose",
        complexity: str = "high", novelty: str = "routine",
    ) -> dict[str, Any]:
        """Pre-flight ONLY. Never applies. Caller (service.py) must
        check approval before invoking the actual apply RPC."""
        if self._pool is not None and self._route_fn is not None and self._spec is not None:
            try:
                from .agents import _routed_generate
                prompt = self._spec.prompt_template.format(worker_output=diff_summary)
                text, routing, t_in, t_out, cost = await _routed_generate(
                    pool=self._pool, route_fn=self._route_fn, role_id=self._role_id,
                    prompt=prompt, complexity=complexity, novelty=novelty,
                )
                lowered = text.lower()
                deploy_safety = (
                    "block" if "block" in lowered or "unsafe" in lowered
                    else "review_required" if "risk" in lowered or "review" in lowered
                    else "safe"
                )
                return {
                    "summary": text[:1000],
                    "deploy_safety": deploy_safety,
                    "target": target,
                    "auto_applied": False,  # ALWAYS — §42 hard stop
                    "approval_required": True,
                    "source_origin": "llm_routed",
                    "routing": routing,
                    "cost_usd_cents": cost,
                }
            except AllBackendsUnavailable as exc:
                return self._heuristic(diff_summary, target, error=str(exc))

        return self._heuristic(diff_summary, target)

    @staticmethod
    def _heuristic(diff: str, target: str, error: str | None = None) -> dict[str, Any]:
        return {
            "summary": f"Heuristic preflight: diff size {len(diff)} chars, target={target}",
            "deploy_safety": "review_required",  # conservative
            "target": target,
            "auto_applied": False,
            "approval_required": True,  # §42 hard stop
            "source_origin": "heuristic_fallback",
            "llm_unavailable": error,
        }
