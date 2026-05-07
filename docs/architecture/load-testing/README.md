# Load Testing — 5-Phase + RAG-Layered

> Per CLAUDE.md §47.10 (5-phase load testing) + §57.1
> (production-grade only) + §38 (governance gate 10 — performance).
>
> Load testing is not "we'll do it before launch." From day 1, every
> service has a smoke + load script. Catalogs reference them via
> `testing.smoke_cmd` (§57.4 self-healing as data).

## The 5 phases (none optional)

| Phase | VU profile | Pass criteria | Tool | Cadence |
|---|---|---|---|---|
| **Smoke** | 1–10 VU for 1 min | 0 errors | k6 / locust | every PR |
| **Load** | Target SLA (e.g. 500 VU steady) for 10 min | p95 < SLA, error rate < 1% | k6 | every release |
| **Stress** | 0 → 2000 VU ramp over 20 min | Find breakpoint VU; recover < 60s after ramp-down | k6 | every release |
| **Soak** | Target VU for 24h | Memory growth < 10%, no FD leak | k6 + observability | weekly |
| **Spike** | 0 → peak VU in 60s, hold 5 min | Recovery < 60s after spike subsides | k6 | every release |

Skipping a phase means: the unmeasured failure mode hits production.

## RAG-specific layered approach

Per §47.10, RAG systems have layered subsystems each with own load
profile. **Test each layer in isolation BEFORE end-to-end.**

| Layer | What to load-test | Bottleneck |
|---|---|---|
| Embedder | `nomic-embed-text` via `ollama.generate` | CPU/GPU; vectorize throughput tokens/sec |
| Vector DB | Qdrant `/collections/<col>/points/search` | RAM / RPS / payload size |
| Reranker | cross-encoder Stage-2 | CPU; latency per pair |
| LLM | `ollama.generate` `/api/generate` | GPU VRAM; concurrent generations |
| Orchestrator | agent-orchestrator-svc `/api/v1/agentic/tasks` | DB connections; task queue depth |
| End-to-end | retrieval-svc `/ask` | All layers compounded |

Layered isolation first → end-to-end second. End-to-end without
layered isolation tells you "it's slow" but not "the LLM is the
bottleneck at 500 VU." Useless for capacity planning.

## Cost as a first-class metric (§41 FinOps)

Every load test MUST log:

- `tokens_per_request` (prompt + completion)
- `cost_per_request_usd` (provider × tokens)
- `requests_per_second` (sustained)
- Projected `cost_per_day_usd` at sustained RPS

Without this, a "successful" load test ships a $40k/month surprise
bill.

## Catalog of in-repo load tests

| Service | Smoke | Load | Stress | Spike | Path |
|---|---|---|---|---|---|
| inference-svc | ✓ | ✓ | ✓ | TODO | `tests/load/inference_smoke.js` |
| retrieval-svc | ✓ | ✓ | ✓ | TODO | `tests/load/retrieval_smoke.js` |
| agent-orchestrator-svc | ✓ | TODO | TODO | TODO | drilled at `mcp/tests/drill_orchestrator_load.py` |
| Per-MCP server | ✓ via fleet-health | TODO | TODO | TODO | `scripts/mcp_fleet_health.py --probe-timeout 1.5` |

## Pre-release gate

Before any release tag:

- [ ] Smoke phase green on every service (1 min, 0 errors)
- [ ] Load phase green on critical path: ingest → retrieve → ask (10 min, p95 < SLA, error < 1%)
- [ ] Stress phase: breakpoint VU documented in release notes
- [ ] Spike phase: recovery time < 60s from peak ramp-down
- [ ] Cost: projected daily cost at target RPS within budget
- [ ] Soak phase: queued for 24h post-deploy in staging

## Reference k6 script — smoke

```javascript
// tests/load/inference_smoke.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '60s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<2000'],
  },
};

export default function () {
  const r = http.post('http://localhost:8087/api/v1/agentic/tasks',
    JSON.stringify({ prompt: 'smoke test' }),
    { headers: { 'Content-Type': 'application/json' } });
  check(r, { 'status is 200': (resp) => resp.status === 200 });
  sleep(0.5);
}
```

## Cross-service correlation during load

Every load-test request injects a trace `request_id`. Operator
investigates a p95 spike via:

1. Grafana panel → click on histogram bar > p95
2. Trace exemplar → Jaeger
3. `request_id` → Kibana log query → cross-service flow

If the trace exemplar is missing on a spike, the load test is
not load-test-grade — it's a smoke test pretending to be load.

## The brutal rule

> A service deployed without 5-phase load testing is a customer
> incident waiting to happen. The breakpoint VU is information you
> need at design time; first-customer-discovers-it costs ~10×.
> Layered isolation first, end-to-end second. Cost is a first-class
> metric, not an afterthought.
