# Prometheus Gauges for External Breaker State

**Status:** 🟢 Green. 5-step drill passes; `documind_circuit_breaker_state{name="mcp_hr"}` transitions 0 → 2 → 0 visible on `/metrics`.
**Date:** 2026-04-24

Closes the last "visibility" follow-up from the trace + detailed-health
commits. The `/api/v1/health/detailed` endpoint is a good one-shot
probe for humans; Grafana wants a continuously-scrapeable time series.
This commit bridges two breakers that couldn't report themselves —
`mcp_hr` (MCP client, lives in decoupled `mcp/` package) and
`otlp-export` (OCB, inverted polarity) — into the shared
`documind_circuit_breaker_state` Prometheus gauge.

---

## What shipped

```
libs/py/documind_core/circuit_breaker.py
  + record_breaker_state(name, state)    ← public helper for external breakers
  + _STATE_NUMERIC mapping                ← closed=0, half_open=1, open=2
services/inference-svc/app/workers/
  + breaker_metrics.py                    ← BreakerMetricsExporter
services/inference-svc/app/main.py        ← lifespan start/stop
mcp/tests/drill_prometheus_breakers.py    ← 5-step drill
docs/DEMO-PROMETHEUS-BREAKERS.md          ← this file
```

## Data flow

```
┌─────────────────────┐     poll every 5s      ┌──────────────────────────────┐
│ mcp_client._breaker │──────────────────────▶│ BreakerMetricsExporter       │
│   .cb_state         │                        │  _sample_once()               │
└─────────────────────┘                        │                               │
┌─────────────────────┐                        │  record_breaker_state(        │
│ obs_breaker.state   │──────────────────────▶│    name, state)               │
└─────────────────────┘                        └──────────────┬───────────────┘
                                                              │
                                                              ▼
                                         documind_circuit_breaker_state{name}
                                         (same Gauge already populated by
                                          retrieval-svc + ollama-llm breakers)
                                                              │
                                                              ▼
                                              Prometheus scrape → Grafana
```

The clever bit: the exporter doesn't own a new gauge. It pushes into
the same `documind_circuit_breaker_state` series the core
`CircuitBreaker` class writes to on every transition. So a Grafana
dashboard filters on that one gauge with `name=~".*"` and gets every
breaker — retrieval, ollama, MCP, OCB — on the same chart with no
special cases.

## Before / after

Before:
```
documind_circuit_breaker_state{name="retrieval-svc"} 0.0
documind_circuit_breaker_state{name="ollama-llm"} 0.0
```

After (inference-svc boot):
```
documind_circuit_breaker_state{name="retrieval-svc"} 0.0
documind_circuit_breaker_state{name="ollama-llm"} 0.0
documind_circuit_breaker_state{name="mcp_hr"} 0.0
documind_circuit_breaker_state{name="otlp-export"} 0.0
```

## Why a polling exporter instead of in-breaker updates

The obvious alternative: make `mcp.client._MCPBreaker.record_failure`
import `documind_core.circuit_breaker.record_breaker_state` and call
it directly on every transition. Real-time, no polling, one fewer
moving part.

Rejected because `mcp/` is a deliberately decoupled package — one of
its selling points is that services can consume it without taking
`documind_core` as a transitive dependency. Adding a core import
there would break that contract the first time anyone wrote an
`mcp-server-standalone` binary.

Polling the state from the *service* that glues `mcp` + `core`
together keeps the boundary clean. The 5s cadence is coarse enough
that the additional load is negligible; fine enough to see a
transition well before Prometheus's default 15s scrape cycle.

## The 5-step drill

```
── 1. baseline — /metrics has mcp_hr + otlp-export at 0 ──
  ✓ baseline series: [('mcp_hr', 0.0), ('ollama-llm', 0.0),
                      ('otlp-export', 0.0), ('retrieval-svc', 0.0)]

── 2. kill MCP + 3 agent/ask → CB trips to OPEN ──
  ✓ 3 degraded calls; MCP CB should be OPEN

── 3. wait one exporter cycle (7s) + assert mcp_hr=2 on /metrics ──
  ✓ mcp_hr=2 (open) — other series unchanged

── 4. restart MCP, wait recovery_timeout (32s), fire probe ──
    waiting 32s for CB recovery_timeout...
  ✓ probe succeeded ticket=HR-...

── 5. wait another exporter cycle + assert mcp_hr=0 again ──
  ✓ mcp_hr=0 (closed) — transition round-trip visible in Prometheus

════════════════════════════════════════
  ALL 5 PROMETHEUS-GAUGE STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_prometheus_breakers.py`

## Grafana / alerting recipe

Once the series is visible, alerting is a three-line
Prometheus rule:

```yaml
- alert: DocumindBreakerStuckOpen
  expr: documind_circuit_breaker_state > 1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Breaker {{ $labels.name }} has been OPEN for 5+ minutes"
```

The `> 1` catches both OPEN (2) and HALF_OPEN (1) — HALF_OPEN for
5+ minutes means the probe keeps failing, which is the same
operational signal. `for: 5m` suppresses transient flaps.

## Remaining follow-ups

- Counter for worker-driven state changes (`documind_breaker_transitions_total{name,from,to}`).
  Today the exporter only writes the *current* state; no cumulative
  transition history is surfaced.
- Scope the exporter to other services (retrieval-svc's httpx CB for
  Qdrant, ingestion's Kafka producer CB). Identical pattern — the
  exporter is 80 lines and takes a list of (name, state_provider) pairs.
- Grafana dashboard JSON checked into `infra/observability/grafana/` so
  the breaker chart is provisioned on `docker compose up`.
