# Load testing — k6 baseline + 5-phase profiles

> Per global §47.10 + `/admin/load-testing/deep` playbook. Multi-phase
> k6 profile from sanity smoke (1 VU) through stress (1000 VU) and
> spike (0→2000 VU) — wired so any operator can run any phase against
> any environment in one command.
>
> Locked by `mcp/tests/drill_load_test_setup.py`.

## The 5 phases

| Phase | VUs | Duration | Goal |
| --- | --- | --- | --- |
| **smoke** | 1 | 10s | Sanity — endpoints respond; no errors |
| **load** | 100 | 3m | SLA target sustain — p95 < 500ms; error rate < 1% |
| **stress** | 100 → 1000 | 5m | Find breakpoint — at what VU does p95 explode? |
| **soak** | 100 | 10m | Memory growth detection — RSS shouldn't climb monotonically |
| **spike** | 0 → 2000 | 60s | Recovery — does the system recover after burst? |
| **full** | all 5 | ~22min | Production-readiness gate |

For 10k / 100k / 1M users: extend `STAGES.stress` and run on infrastructure that can drive that many connections (single laptop maxes out around 5k-10k VUs depending on endpoint cost). Real 100k+ tests need k6 Cloud or a multi-machine load-generator cluster (see "Scaling beyond one host" below).

## Prerequisites

| Tool | Install |
| --- | --- |
| **k6** | `curl -L https://github.com/grafana/k6/releases/latest/download/k6-linux-amd64.tar.gz \| tar xz && sudo mv k6-*/k6 /usr/local/bin/` (Linux) — or `brew install k6` (macOS) |
| target | NGINX + api-gateway running. Bring up via `docker compose up -d nginx api-gateway redis` (or `--profile app` for containerized api-gateway). |

## Run

```bash
# Single phase
bash scripts/load-test.sh smoke              # ~15s
bash scripts/load-test.sh load               # ~4 min
bash scripts/load-test.sh stress              # ~5 min
bash scripts/load-test.sh soak                # ~11 min
bash scripts/load-test.sh spike               # ~3 min

# All 5 phases sequentially
bash scripts/load-test.sh full                 # ~22 min

# Custom target
BASE_URL=https://staging.documind.com bash scripts/load-test.sh load

# With JWT auth (required for /api/v1/* once api-gateway JWT is on)
AUTH_BEARER="$(cat .loop/test-jwt.txt)" bash scripts/load-test.sh load
```

Results land in `.loop/load-test/<profile>-<timestamp>.json` per run.

## SLO thresholds (k6 enforces these)

| Metric | Threshold | Source |
| --- | --- | --- |
| `/healthz` p95 latency | < 100ms | health probe must be fast |
| `/api/v1/*` p95 latency | < 500ms | global §47.10 production SLA |
| Total error rate | < 1% | global §47.10 |
| Custom error counter | < 1000 over run | sanity cap |

If any threshold breaches, k6 exits 99 → the wrapper script propagates that → CI fails (when wired).

## Output interpretation

After a run:

```
✓ http_req_failed       0.00% / 1.00%
✗ http_req_duration{name:api}    p(95)=621ms / p(95)<500ms     ← breach
✓ documind_errors_total          37 / 1000

http_req_duration..............: avg=234ms p(95)=621ms p(99)=1.2s
http_req_failed................: 0.00%   ← no error, but slow
iterations.....................: 14322 / 60.18req/s
vus............................: 100 max
```

Reading this: zero hard errors but p95 breached. Likely causes:
- DB query slow (check Postgres `pg_stat_activity`)
- Cache miss rate high (check Redis hit rate)
- Connection pool too small (tune `max_connections`)
- Single replica saturated (scale horizontally)

## Scaling beyond one host

A single laptop drives at most ~5-10k VUs before TCP / FD exhaustion. Real 100k+ tests:

1. **k6 Cloud** — `k6 cloud infra/load-test/k6/baseline.js`. Paid; managed load generators in multiple regions.
2. **Distributed k6** — operator-managed cluster of k6 workers (`k6 run --execution-segment=...`).
3. **External load tool** — Gatling / JMeter / Locust on a multi-machine grid.

The k6 script in this repo is intentionally configuration-as-code: same script, different driver. `BASE_URL` + `AUTH_BEARER` env vars cover environment portability.

## What this k6 script tests

| Hot path | Endpoint | Tag |
| --- | --- | --- |
| Health probe | `GET /healthz` | `health` |
| Sidecar event submit | `POST /api/v1/sidecar/events` | `api` |

Future iterations should add:
- Council run (POST `/api/v1/sidecar/events/<id>/rating` after submission)
- Retrieval (POST `/api/v1/retrieve` against retrieval-svc)
- LLM proxy (POST `/api/v1/agentic/tasks` against agent-orchestrator-svc)

Each hot path = its own k6 file under `infra/load-test/k6/<path>.js`.

## Composes with

- `/admin/load-testing/deep` — narrative playbook this implements
- `infra/observability/grafana-dashboards/` — view k6 metrics in Grafana via the Prometheus exporter
- `docs/architecture/performance-and-load-testing.md` — extended performance design notes
- `.github/workflows/ci.yml` — future iteration: smoke phase on every PR
- §47.10 — 5-phase requirement; this file IS the implementation

## Brutal rule

> A platform that hasn't been load-tested isn't production-ready. The
> `smoke` phase takes 15 seconds and proves the endpoints respond.
> Run it on every deploy. The `full` profile takes 22 minutes and
> proves SLOs hold under stress + soak + spike — run it before
> shipping a release.
