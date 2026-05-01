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
        *,
        alerts_fired: int,
        p95_baseline_ms: int | None,
        p95_observed_ms: int | None,
        # CB-E #24: third signal — list of OPEN breakers on the deployed
        # service. A wide-open breaker on the deployed service IS a
        # degradation signal stronger than p95 alone.
        open_breakers: list[str] | None = None,
    ) -> tuple[str, list[str]]:
        """Pure decision function. Returns (status, concerns).

        Three-signal rule per §47.7 + CB-E #24:
          - rollback_required: ANY TWO of {alerts_breach, p95_breach,
            breaker_open} → roll back
          - degraded: ANY ONE of the three → operator reviews
          - healthy: none of the three
        """
        open_breakers = open_breakers or []
        concerns: list[str] = []
        alerts_breach = alerts_fired >= ALERTS_THRESHOLD_COUNT
        p95_breach = (
            p95_baseline_ms is not None
            and p95_observed_ms is not None
            and p95_observed_ms > p95_baseline_ms * P95_BREACH_RATIO
        )
        breaker_breach = len(open_breakers) > 0

        if alerts_breach:
            concerns.append(f"alerts fired: {alerts_fired}")
        if p95_breach:
            concerns.append(f"p95 spike: {p95_observed_ms}ms vs baseline {p95_baseline_ms}ms")
        if breaker_breach:
            concerns.append(f"breakers OPEN: {open_breakers}")

        signals_breached = sum([alerts_breach, p95_breach, breaker_breach])
        if signals_breached >= 2:
            return "rollback_required", concerns
        if signals_breached == 1:
            return "degraded", concerns
        return "healthy", []

    async def observe(
        self, *, alerts_fired: int = 0,
        p95_baseline_ms: int | None = None, p95_observed_ms: int | None = None,
        # CB-E #24: optional list of OPEN breaker names on the deployed
        # service. Caller (service.py) reads breaker states from the
        # local LlmClientPool / MCPClient registry and passes them in.
        open_breakers: list[str] | None = None,
        complexity: str = "medium", novelty: str = "routine",
    ) -> dict[str, Any]:
        status, concerns = self.evaluate_metrics(
            alerts_fired=alerts_fired,
            p95_baseline_ms=p95_baseline_ms,
            p95_observed_ms=p95_observed_ms,
            open_breakers=open_breakers,
        )
        return {
            "status": status,
            "alerts_fired": alerts_fired,
            "p95_baseline_ms": p95_baseline_ms,
            "p95_observed_ms": p95_observed_ms,
            "open_breakers": open_breakers or [],
            "concerns": concerns,
            "recommended_action": (
                "trigger mcp_deploy.rollback(handle)" if status == "rollback_required"
                else "operator review" if status == "degraded"
                else "finalize task"
            ),
            "source_origin": "deterministic",
        }
