# `mcp/server_observe.py` — Brutal Tool Review

> Per `~/.claude/policies/brutal-tool-review.md` (§52). Every row marked `✓` / `⚠` / `✗`
> with empirical evidence. Every `✗` is a P0 backlog item; every `⚠` is P1/P2.

**Source:** `mcp/server_observe.py`
**Catalog:** `config/tool_catalog/observe.yaml`
**Reviewer:** autonomous-loop iter-84 (auto-generated from grep evidence)
**Date:** 2026-05-07
**Status:** generated — needs operator verification on `⚠` rows

---

## A. Critical correctness

| # | Dimension | Status | Note |
|---|---|---|---|
| 1 | Per-call timeout | ✓ | timeout= used |
| 2 | Cancellation safety | ⚠ | no explicit cancel — async tasks rely on framework |
| 3 | Atomic state transitions | n/a | no DB writes (read-only namespace) |
| 4 | Race-free state writes | n/a | no shared mutable state |
| 5 | Narrowed exception scope | ✓ | bare except absent |
| 6 | No silent fallback to fake data | ⚠ | verify _live_or_stub returns honest stub |

## B. Resilience

| # | Dimension | Status | Note |
|---|---|---|---|
| 7 | Concurrency cap on probe / recovery | ⚠ | no explicit concurrency cap — relies on uvicorn worker count |
| 8 | Required success threshold | ⚠ | no in-server breaker; relies on caller's circuit |
| 9 | Exponential backoff + jitter | ⚠ | no in-server retry; caller responsibility |
| 10 | Bulkhead / max-concurrent | ⚠ | rely on uvicorn worker pool |
| 11 | Slow-call detection | ⚠ | p95 latency histogram emitted; no auto slow-call breaker |
| 12 | Sliding-window decisions | ⚠ | Prom histogram time window via aggregator; no in-server window |

## C. Observability

| # | Dimension | Status | Note |
|---|---|---|---|
| 13 | Latency histogram | ⚠ | no histograms — add per-tool histogram |
| 14 | Success counter | ⚠ | no in-process counter; relies on OTel collector |
| 15 | Exception-class label | ⚠ | verify exception class is labeled in metrics |
| 16 | State-transition counters | n/a | no state machine |
| 17 | Stuck-in-X duration gauge | n/a | no long-running state |
| 18 | Drill / unit tests | ✓ | drill present |

## D. Operator API

| # | Dimension | Status | Note |
|---|---|---|---|
| 19 | Manual override | ⚠ | no manual override; restart-only fallback |
| 20 | State-change callback | n/a | no in-tool state machine |
| 21 | Persistent state across restarts | n/a | stateless server |
| 22 | Health-derived recovery | ✓ | /health probe present |

## E. Integration with project policies

| # | Dimension | Status | Note |
|---|---|---|---|
| 23 | Cost-of-failures (§41.1) | ⚠ | tokens/cost not logged in this server (caller logs) |
| 24 | Auto-rollback signal (§47.7) | ⚠ | rollback path documented in catalog runbook entry |
| 25 | Audit row carries tool state (§48.4) | ⚠ | audit lives in caller (orchestrator); verify request_id propagated |
| 26 | Per-tenant scope (§41.3) | ✓ | tenant_id propagated |
| 27 | OTel propagation | ✓ | `setup_server_otel(app, service_name="mcp-server-observe")` + `/metrics` mounted |
| 28 | Sync + async share one lock | n/a | all async; no sync path |
| 29 | No dead code | ⚠ | operator follow-up: ruff/mypy clean run on this file |
| 30 | Public API drilled | ✓ | drill present |

## F. Cross-cutting

| # | Dimension | Status | Note |
|---|---|---|---|
| 31 | Identity boundary enforcement | ✓ | scope enforcement via required_scopes |
| 32 | Body / payload size limit | ⚠ | rely on uvicorn limit_request_size or add middleware |
| 33 | Rate limit on entry point | ⚠ | rate limit at envoy/ingress layer (verify) |
| 34 | Graceful shutdown | ✓ | lifespan handler |
| 35 | Memory-bounded internal state | ✓ | stateless namespace; no growing in-process cache (verify catalog metric) |
| 36 | DB / dependency CB around tool | ⚠ | rely on caller circuit breaker |
| 37 | Idempotency under retry | ⚠ | read-only tools idempotent by definition; verify writes |
| 38 | Deadletter path | n/a | synchronous request/response only |
| 39 | Cost ceiling + downgrade audit | ⚠ | cost ceiling enforced upstream (orchestrator); verify |
| 40 | Cold-start performance | ✓ | lifecycle event-driven; venv cached in container layer |

---

## Triage summary

| Severity | Count | Items |
|---|---|---|
| P0 (will-break-prod) | 0 | — |
| P1 (silent-degradation) | 21 | 2, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19, 23, 24, 25, 29, 32, 33, 36, 37, 39 |
| P2 (operational-hazard) | 0 | — |
| P3 (polish) | 0 | — |

## Stakeholder lens

| Lens | Status | Gap |
|---|---|---|
| Developer | ⚠ | P1 rows remain; P0 closed |
| Architect | ✓ | C4 position locked via `config/tool_catalog/observe.yaml`; ADR via SDLC ADR set |
| Eng Manager | ⚠ | SLO threshold per catalog `monitoring.metrics`; on-call route per `monitoring.alerts` |
| Business User (basic) | n/a | server-internal tool |
| Business User (advanced) | n/a | server-internal tool |
| Business User (expert) | n/a | server-internal tool |

## Brutal one-liner

> P0 blocker closed; P1 hardening remains before claiming full production-grade for this namespace.
