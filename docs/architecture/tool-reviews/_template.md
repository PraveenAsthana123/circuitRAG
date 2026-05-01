# `<TOOL_NAME>` — Brutal Tool Review

> Per `~/.claude/policies/brutal-tool-review.md`. Mark each row `✓` / `✗` / `n/a`
> with one-line justification. Every `✗` becomes a backlog item.

**Source:** `<path/to/source.py>`
**Reviewer:** `<name / agent>`
**Date:** `<YYYY-MM-DD>`
**Status:** `<draft | reviewed | shipped>`

---

## A. Critical correctness

| # | Dimension | Status | Note |
|---|---|---|---|
| 1 | Per-call timeout |  |  |
| 2 | Cancellation safety |  |  |
| 3 | Atomic state transitions |  |  |
| 4 | Race-free state writes |  |  |
| 5 | Narrowed exception scope |  |  |
| 6 | No silent fallback to fake data |  |  |

## B. Resilience

| # | Dimension | Status | Note |
|---|---|---|---|
| 7 | Concurrency cap on probe / recovery |  |  |
| 8 | Required success threshold |  |  |
| 9 | Exponential backoff + jitter |  |  |
| 10 | Bulkhead / max-concurrent |  |  |
| 11 | Slow-call detection |  |  |
| 12 | Sliding-window decisions |  |  |

## C. Observability

| # | Dimension | Status | Note |
|---|---|---|---|
| 13 | Latency histogram |  |  |
| 14 | Success counter |  |  |
| 15 | Exception-class label |  |  |
| 16 | State-transition counters |  |  |
| 17 | Stuck-in-X duration gauge |  |  |
| 18 | Drill / unit tests |  |  |

## D. Operator API

| # | Dimension | Status | Note |
|---|---|---|---|
| 19 | Manual override |  |  |
| 20 | State-change callback |  |  |
| 21 | Persistent state across restarts |  |  |
| 22 | Health-derived recovery |  |  |

## E. Integration with project policies

| # | Dimension | Status | Note |
|---|---|---|---|
| 23 | Cost-of-failures (§41.1) |  |  |
| 24 | Auto-rollback signal (§47.7) |  |  |
| 25 | Audit row carries tool state (§48.4) |  |  |
| 26 | Per-tenant scope (§41.3) |  |  |
| 27 | OTel propagation |  |  |
| 28 | Sync + async share one lock |  |  |
| 29 | No dead code |  |  |
| 30 | Public API drilled |  |  |

## F. Cross-cutting

| # | Dimension | Status | Note |
|---|---|---|---|
| 31 | Identity boundary enforcement |  |  |
| 32 | Body / payload size limit |  |  |
| 33 | Rate limit on entry point |  |  |
| 34 | Graceful shutdown |  |  |
| 35 | Memory-bounded internal state |  |  |
| 36 | DB / dependency CB around tool |  |  |
| 37 | Idempotency under retry |  |  |
| 38 | Deadletter path |  |  |
| 39 | Cost ceiling + downgrade audit |  |  |
| 40 | Cold-start performance |  |  |

---

## Triage summary

| Severity | Count | Items |
|---|---|---|
| P0 (will-break-prod) |  | row #s |
| P1 (silent-degradation) |  | row #s |
| P2 (operational-hazard) |  | row #s |
| P3 (polish) |  | row #s |

## Stakeholder lens

| Lens | Status | Gap |
|---|---|---|
| Developer |  |  |
| Architect |  |  |
| Eng Manager |  |  |
| Business User (basic) |  |  |
| Business User (advanced) |  |  |
| Business User (expert) |  |  |

## Brutal one-liner

> `<one-sentence verdict — what's true production blocker, what's polish>`
