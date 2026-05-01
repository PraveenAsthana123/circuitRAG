# `ObserverAgent` + `mcp_observe` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/observer.py` + `mcp/server_observe.py`
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | — |
| **P1** | 3 | rows #20 (no async sweep / cron yet), #21 (no soak window persistence beyond the migration table), #38 (no deadletter for failed observes) |
| **P2** | 4 | — |

## Highlights

- ✅ E3 + E4: real Prometheus + Alertmanager backings (stub:'false')
- ✅ E-CB: 3-signal rollback rule (alerts + p95 + breakers)
- ✅ PromQL injection guards (regex allowlist on service/metric names)
- ✅ Two-signal-or-more for rollback decision (CB-E #24)

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 9 | Backoff on Prom failures | ✗ | Single retry; no backoff |
| 11 | Slow-prom-query detect | ✗ | Slow Prom returns ok with 10s latency; no flag |
| 20 | Async sweep / cron | ✗ | **P1** — `observe_windows` migration exists; no scheduled sweep yet that auto-resumes pending observers |
| 21 | Persistent state | ⚠ | Migration 012 exists; agent state across restarts not validated |
| 24 | Rollback signal | ✅ | E-CB wired |
| 25 | Audit row | ⚠ | Observer status NOT in /explain; only soak_windows |
| 36 | Dep CB | ✗ | **P1** — no breaker on Prometheus / Alertmanager calls |
| 38 | Deadletter | ✗ | **P1** — observe failure doesn't surface to operator |

## Brutal one-liner

> Observer's evaluate-metrics function is **pure and well-drilled**. What's missing
> is the **async sweep** — the cron / scheduled task that wakes up at `soak_ends_at`
> and acts on the result. Without it, observe_windows accumulate as `pending` rows
> indefinitely. Fix #20 first; everything else is polish.
