# Detailed Health Endpoint — `GET /api/v1/health/detailed`

**Status:** 🟢 Green. 4-step drill passes end-to-end: breaker transitions
are visible to an HTTP caller without log-scraping.
**Date:** 2026-04-24

Prompt: the trace drill surfaced that the Observability Circuit
Breaker (OCB) tripped silently when the OTel collector was mis-bound.
The only signal was the line `obs_breaker name=otlp-export from=closed
to=open` buried in service logs. Meanwhile the MCP client's CB is
internal to `MCPClient._breaker` — also invisible to operators.
Both are now reported on a single detailed-health endpoint.

---

## What shipped

```
services/inference-svc/
  app/schemas/__init__.py       — BreakerState + HealthDetailedResponse models
  app/routers/__init__.py       — GET /api/v1/health/detailed
  app/main.py                    — lifespan stashes started_at_monotonic
                                   and obs_breaker on app.state
mcp/tests/drill_health_detailed.py  — 4-step drill
docs/DEMO-HEALTH-DETAILED.md        — this file
```

## Response shape

```bash
curl -s http://127.0.0.1:8084/api/v1/health/detailed | jq .
```
```json
{
  "service": "inference-svc",
  "uptime_s": 36.338,
  "observed_at": "2026-04-24T20:26:53.556027+00:00",
  "breakers": [
    { "name": "mcp_hr",       "state": "closed", "failures": 0 },
    { "name": "otlp-export",  "state": "closed", "failures": null }
  ],
  "readiness": {
    "draft_store":         "postgres",
    "audit_log":           "on",
    "auth":                "optional",
    "agent_service":       "on",
    "draft_replay_worker": "off"
  }
}
```

The existing `/health` stays as a binary liveness probe (200 = process
alive). `/api/v1/health/detailed` is the operator-facing companion:

- **Always 200.** A degraded state does NOT change HTTP status — the
  caller decides what to alert on. A k8s liveness probe using this
  endpoint would NOT restart the pod when MCP is down; it would just
  surface `mcp_hr.state=open` to the dashboard. (Use `/health` for
  the liveness probe; use `/detailed` for the dashboard.)
- **No auth gate.** Readiness should be observable without a JWT —
  deploy-time checks, health scrapers, sidecars, all live above auth.
- **Breaker names are stable.** Scripts + dashboards bind to
  `mcp_hr` and `otlp-export` as identifiers.

## Two breakers reported today

| Name | Protects | Source of truth |
| --- | --- | --- |
| `mcp_hr` | MCP HR tool server | `MCPClient._breaker.state` (`cb_state` prop) |
| `otlp-export` | OTel OTLP exporter | module-level `obs_breaker` in `documind_core.observability` |

Future breakers can join by appending to the `breakers` list in the
route handler; no schema change required (`BreakerState` is a plain
Pydantic model).

## Readiness flags

| Flag | Values |
| --- | --- |
| `draft_store` | `postgres` \| `in_memory` — whether governance.action_drafts is connected |
| `audit_log` | `on` \| `off` — whether hash-chained audit rows are being written |
| `auth` | `required` \| `optional` — whether DOCUMIND_AUTH_REQUIRED is set |
| `agent_service` | `on` \| `off` — whether MCP URL was wired |
| `draft_replay_worker` | `on` \| `off` — whether the autonomous replay loop is scheduled |

A future PR scrapes these into Prometheus gauges — one per flag — so
the observability dashboard can surface a full matrix ("which tenants
have which capabilities") without code changes in each service.

## The 4-step drill

```
── 1. baseline — detailed health reports healthy state ──
  ✓ uptime=… mcp_hr=closed readiness={'draft_store': 'postgres',
    'audit_log': 'on', 'auth': 'optional', 'agent_service': 'on',
    'draft_replay_worker': 'off'}

── 2. kill MCP + 3 agent/ask calls to trip the CB ──
  ✓ 3 degraded drafts recorded — breaker should have tripped

── 3. GET /detailed — mcp_hr breaker now 'open' ──
  ✓ mcp_hr state=open failures=3

── 4. restart MCP + recovery — breaker returns to 'closed' after a probe ──
    waiting 32s for CB recovery_timeout...
  ✓ recovered: mcp_hr state=closed

════════════════════════════════════════
  ALL 4 DETAILED-HEALTH STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_health_detailed.py`

---

## Why this lands now

The HITL stack is six commits deep; the trace drill just went green.
Both used to have blind spots:

- **HITL replay worker** needed to know when MCP had recovered to
  productively hit `resolve_draft`. Without this endpoint it could
  only blindly retry every cycle and rely on the CB's bailout path.
  With this endpoint, a future commit teaches the worker to poll
  `mcp_hr.state` and only fire when it's `closed` or `half_open`.
- **Trace drill** surfaced the OCB tripping but could only report it
  post-hoc. With this endpoint, a CI harness could poll `otlp-export`
  and flag a CB that stays `open` beyond the recovery_timeout (i.e.
  the collector is still dead after retry) as a real alert.

The endpoint itself is three dozen lines; the value is that every
later observability or automation commit has an API to bind to.

## Remaining follow-ups

- `draft_replay_worker.state` — report the worker's `cycles` /
  `replayed` / `errors` counters so a dashboard can graph throughput.
- `mcp_hr.last_transition_at` — epoch seconds of the most recent
  state change, so a replay worker can wait a stabilization window
  before firing.
- Prometheus gauges for `documind_breaker_state{service,name}` with
  values 0=closed, 1=half_open, 2=open — so the existing Grafana
  stack can alert without parsing the JSON.
- Extend to retrieval-svc + ingestion-svc — identical endpoint shape,
  each service reports its own local breakers.
