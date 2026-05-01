# Debug & Performance Guide

> §19 mandate. Substantive content lives at:
>
> See: [`performance-and-load-testing.md`](performance-and-load-testing.md)
> See: [`performance-load-tooling-and-matrices.md`](performance-load-tooling-and-matrices.md)
> See: [`LATENCY-BUDGET.md`](LATENCY-BUDGET.md) — per-tool latency budget
> See: [`../../infra/load-test/k6/`](../../infra/load-test/k6/) — k6 scripts (5-phase)
> See: [`../DEMO-ERROR-TRACKER.md`](../DEMO-ERROR-TRACKER.md) — F12 long-task capture

## Performance budget (CLAUDE.md §30.1)

| Metric | Target | Red flag |
|---|---|---|
| Initial bundle (gzip) | <200KB | >500KB |
| LCP | <2.5s | >4s |
| CLS | <0.1 | >0.25 |
| Time to Interactive | <3.5s | >5s |
| API p95 | <500ms | >2s |
| Page switch | <300ms | >1s |
| Memory | <50MB | >150MB |

## 5-phase load testing (CLAUDE.md §47.10)

1. **Smoke** (1-10 VU) — sanity, no errors
2. **Load** (target SLA, e.g. 500 VU) — p95 < SLA
3. **Stress** (0→2000 VU) — find breakpoint
4. **Soak** (24h target) — no memory growth >10%
5. **Spike** (0→peak in 60s) — recover <60s

For RAG: layered isolation first (embedder + vector + LLM
separately), then end-to-end with prod query mix. Tokens + cost =
first-class metrics.

## Backend performance debug surface

| Tool | What it shows |
|---|---|
| Jaeger | per-request span tree across services |
| Prometheus | rate / latency / error per route |
| Grafana | SLO burn-rate + capacity dashboards |
| `pprof` | Go service CPU / heap profile |
| `py-spy` | Python service flamegraph (live process) |
| `EXPLAIN ANALYZE` | Postgres query plan |

## Frontend performance debug

| Tool | What it shows |
|---|---|
| `window.__errors.getReport()` | long tasks (>100ms) + CLS events |
| Chrome DevTools Performance | full timeline + CPU / network waterfall |
| Lighthouse | LCP / FID / CLS / TBT / SI / Speed Index |
| `source-map-explorer` | bundle composition |

## Common slowdowns

| Symptom | Likely cause |
|---|---|
| LCP > 4s | Heavy hero image or blocking JS |
| CLS > 0.25 | Layout shift during font load or async content |
| API p95 > 2s | DB query missing index or LLM call timeout |
| Memory grows during 24h soak | useEffect cleanup missing or unbounded cache |

## Drill-driven perf gate

```bash
# 5-phase k6 run
infra/load-test/k6/run-all-phases.sh

# Per-tool latency drill
.venv/bin/python mcp/tests/drill_latency_budget.py  # if present
```

## See also

- [`subsystem-ownership.md`](subsystem-ownership.md) — who owns what perf surface
- [`tool-troubleshooting-checklist.md`](tool-troubleshooting-checklist.md) — per-tool checklist
