"""ObserverAgent (Phase B6 scaffold).

Reads metrics (Prom + Loki) at soak window end and decides:
  'healthy' → finalize task
  'degraded' → log + alert (caller decides escalation)
  'rollback_required' → caller invokes mcp_deploy.rollback(handle)

Two-signal threshold (§47.7): rollback only triggers when BOTH
alerts_fired AND p95_delta exceed thresholds. Single-signal events
are 'degraded' (operator review), not 'rollback'.
"""
from __future__ import annotations

from typing import Any

from .llm_clients import AllBackendsUnavailable, LlmClientPool


RouteFn = Any
P95_BREACH_RATIO = 2.0       # p95 > 2x baseline → breach
ALERTS_THRESHOLD_COUNT = 1   # ≥1 alert fired → breach


class ObserverAgent:
    def __init__(
        self, *,
        ollama=None, spec=None,
        pool: LlmClientPool | None = None, route_fn: RouteFn | None = None,
        mcp_observe_client=None,
        role_id: str = "observer",
    ) -> None:
        self._ollama = ollama
        self._spec = spec
        self._pool = pool
        self._route_fn = route_fn
        self._mcp = mcp_observe_client
        self._role_id = role_id

    @staticmethod
    def evaluate_metrics(
        *, alerts_fired: int, p95_baseline_ms: int | None, p95_observed_ms: int | None,
    ) -> tuple[str, list[str]]:
        """Pure decision function. Returns (status, concerns).

        Two-signal rule per §47.7: rollback ONLY when BOTH dimensions
        breach. Single dimension → 'degraded' (operator reviews).
        """
        concerns: list[str] = []
        alerts_breach = alerts_fired >= ALERTS_THRESHOLD_COUNT
        p95_breach = (
            p95_baseline_ms is not None
            and p95_observed_ms is not None
            and p95_observed_ms > p95_baseline_ms * P95_BREACH_RATIO
        )
        if alerts_breach:
            concerns.append(f"alerts fired: {alerts_fired}")
        if p95_breach:
            concerns.append(f"p95 spike: {p95_observed_ms}ms vs baseline {p95_baseline_ms}ms")

        if alerts_breach and p95_breach:
            return "rollback_required", concerns
        if alerts_breach or p95_breach:
            return "degraded", concerns
        return "healthy", []

    async def observe(
        self, *, alerts_fired: int = 0,
        p95_baseline_ms: int | None = None, p95_observed_ms: int | None = None,
        complexity: str = "medium", novelty: str = "routine",
    ) -> dict[str, Any]:
        status, concerns = self.evaluate_metrics(
            alerts_fired=alerts_fired,
            p95_baseline_ms=p95_baseline_ms,
            p95_observed_ms=p95_observed_ms,
        )
        return {
            "status": status,
            "alerts_fired": alerts_fired,
            "p95_baseline_ms": p95_baseline_ms,
            "p95_observed_ms": p95_observed_ms,
            "concerns": concerns,
            "recommended_action": (
                "trigger mcp_deploy.rollback(handle)" if status == "rollback_required"
                else "operator review" if status == "degraded"
                else "finalize task"
            ),
            "source_origin": "deterministic",
        }
