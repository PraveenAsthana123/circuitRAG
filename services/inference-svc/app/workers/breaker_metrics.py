"""
Background exporter: bridges non-CircuitBreaker breakers into the
shared ``documind_circuit_breaker_state`` Prometheus gauge.

Why this exists
---------------
* ``RetrievalCircuitBreaker`` and the generic ``CircuitBreaker`` (both
  in ``documind_core``) already write their own state to the gauge on
  every transition.
* ``mcp.client._MCPBreaker`` is intentionally decoupled from
  ``documind_core`` — it can't update the gauge from inside itself.
* ``ObservabilityCircuitBreaker`` has its own separate ``obs_breaker_*``
  counters; the *state* of the OCB wasn't surfaced as a gauge before
  this commit.

Both of those states are now queryable over HTTP via
``/api/v1/health/detailed``. A human operator can curl it. But
Prometheus alerting + Grafana dashboards need a scrapeable time
series, not a one-shot JSON endpoint. This exporter polls every
``interval_s`` seconds and feeds the shared gauge so
``documind_circuit_breaker_state{name="mcp_hr"}`` and
``documind_circuit_breaker_state{name="otlp-export"}`` join
``retrieval-svc`` and ``ollama-llm`` on the same chart.

The polling frequency is deliberately low (5s default) — these
gauges don't need to chase every transition, they're for alerting
on stuck-open breakers over minutes.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from documind_core.circuit_breaker import record_breaker_state

log = logging.getLogger(__name__)


class BreakerMetricsExporter:
    """Polls breaker states at a fixed interval and pushes to Prometheus."""

    def __init__(
        self,
        *,
        mcp_client: Any = None,
        mcp_clients: dict[str, Any] | None = None,
        obs_breaker: Any = None,
        interval_s: int = 5,
    ) -> None:
        # mcp_clients is the multi-namespace surface (preferred).
        # mcp_client is kept for back-compat: a single client implicitly
        # lives under the "hr" namespace — same convention as
        # AgentService's back-compat wrap.
        if mcp_clients is None:
            mcp_clients = {"hr": mcp_client} if mcp_client is not None else {}
        # Drop Nones; accept pre-built dict verbatim.
        self._mcps: dict[str, Any] = {k: v for k, v in mcp_clients.items() if v is not None}
        self._obs = obs_breaker
        self._interval = max(1, interval_s)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.stats = {"cycles": 0, "errors": 0}

    async def start(self) -> None:
        if self._task is not None:
            return
        log.info(
            "breaker_metrics_exporter_start interval=%ds mcps=%s obs=%s",
            self._interval,
            sorted(self._mcps.keys()),
            self._obs is not None,
        )
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="breaker_metrics_exporter")
        # Do one cycle eagerly so the gauge is populated before the first
        # Prometheus scrape — otherwise the series simply doesn't exist
        # for the first `interval_s` seconds.
        await self._sample_once()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=self._interval + 2)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None
        log.info("breaker_metrics_exporter_stopped stats=%s", self.stats)

    async def sample_once(self) -> None:
        """Deterministic single sample — exposed for tests."""
        await self._sample_once()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                return
            try:
                await self._sample_once()
            except Exception as exc:  # noqa: BLE001
                self.stats["errors"] += 1
                log.error("breaker_metrics_cycle_failed err=%s", exc)

    async def _sample_once(self) -> None:
        self.stats["cycles"] += 1
        for namespace, client in self._mcps.items():
            state = getattr(client, "cb_state", None)
            if state is not None:
                record_breaker_state(f"mcp_{namespace}", str(state))
        if self._obs is not None:
            inner_state = getattr(self._obs, "state", None)
            # ObservabilityCircuitBreaker.state is a StrEnum (has .value)
            value = getattr(inner_state, "value", None) or (
                str(inner_state) if inner_state is not None else None
            )
            if value is not None:
                record_breaker_state(self._obs.name, value)
