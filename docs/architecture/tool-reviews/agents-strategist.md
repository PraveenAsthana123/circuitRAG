# `StrategistAgent` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/agents.py::StrategistAgent`
**Date:** 2026-05-01 (review) · 2026-05-09 (P0 #1 closure verified)

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | row #1 closed: `classify()` wraps `_classify_unbounded()` in `asyncio.wait_for(timeout=classify_timeout_s)` (default 30s); on `TimeoutError` returns heuristic with `llm_unavailable` field. Drilled by `drill_p0_memory_and_strategist_timeout.py` step 6 — empirical "hung pool → heuristic returned in 201ms (timeout=200ms)". |
| **P1** | 4 | rows #5 (broad except), #11 (no slow-call), #18 (no drill on JSON parse edge cases), #25 (no audit field) |
| **P2** | 3 | rows #19, #20, #22 |

## Critical (A)

| # | Dimension | Status | Note |
|---|---|---|---|
| 1 | Per-call timeout | ✅ | **P0 CLOSED** — `classify(classify_timeout_s=30.0)` adds an outer `asyncio.wait_for` deadline regardless of pool config. Strategist's heuristic fallback is the safety net. See agents.py lines 160-173. |
| 2 | Cancellation safety | ✅ | `_routed_generate` propagates Cancelled correctly |
| 3 | Atomic state | n/a | Stateless |
| 4 | Race-free | n/a | — |
| 5 | Narrow exception scope | ✗ | **P1** — `except Exception` in legacy ollama path (line ~108) catches everything |
| 6 | No silent fallback | ✅ | Heuristic fallback explicitly self-marks `source_origin: "heuristic_fallback"` |

## Resilience (B)

| # | Dimension | Status | Note |
|---|---|---|---|
| 7 | Concurrency cap | n/a | Single-call agent |
| 8 | Success threshold | n/a | — |
| 9 | Backoff | ✗ | No retry on transient LLM failure |
| 10 | Bulkhead | n/a | — |
| 11 | Slow-call detection | ✗ | **P1** — slow strategist (10s+) silently passes |
| 12 | Sliding-window | n/a | — |

## Observability (C)

| # | Dimension | Status | Note |
|---|---|---|---|
| 13 | Latency histogram | ⚠ | Pool records latency; not surfaced per-agent |
| 14 | Success counter | ⚠ | Only via pool's counter |
| 15 | Exception class | ⚠ | LLM error class flows; JSON parse failure does not |
| 16 | Transition counter | n/a | — |
| 17 | Stuck gauge | n/a | — |
| 18 | Drills | ⚠ | **P1** — `drill_strategist_classification` covers happy + parse-fail; doesn't cover empty `goal`, malformed JSON with valid keys, or rate-limited Claude |

## Operator API (D)

| # | Dimension | Status | Note |
|---|---|---|---|
| 19 | Manual override | ✗ | **P2** — operator can't force a heuristic-only mode for cost emergency |
| 20 | State-change callback | ✗ | No hook on classification |
| 21 | Persistent state | n/a | Stateless |
| 22 | Health-derived | ✗ | **P2** — strategist doesn't know if Claude is degraded |

## Project policies (E)

| # | Dimension | Status | Note |
|---|---|---|---|
| 23 | Cost of failures | ⚠ | When LLM fails, fallback to heuristic — no record of "spent $X then fell back" |
| 24 | Rollback signal | n/a | — |
| 25 | Audit row | ✗ | **P1** — strategist's classification (complexity/novelty) NOT in `/explain` row |
| 26 | Per-tenant | ⚠ | Inherited from pool |
| 27 | OTel | ✗ | No span span on classify |
| 28 | Sync+async lock | n/a | — |
| 29 | Dead code | ✅ | clean |
| 30 | API drilled | ✅ | classify() drilled |

## Cross-cutting (F)

| # | Dimension | Status | Note |
|---|---|---|---|
| 31 | Identity boundary | ⚠ | tenant_id present in input, not validated |
| 32 | Body limit | ✗ | Goal text not capped (could pass 1MB string to Claude) |
| 33 | Rate limit | n/a | Caller's concern |
| 34 | Graceful shutdown | n/a | — |
| 35 | Memory-bounded | ✅ | Stateless |
| 36 | DB/dep CB | ⚠ | LLM call uses pool; pool has no CB (see llm-client.md) |
| 37 | Idempotency | ✗ | Same goal classified twice → 2× Claude calls |
| 38 | Deadletter | ✗ | Failed classification not quarantined |
| 39 | Cost ceiling | ⚠ | Router-level only |
| 40 | Cold start | ✗ | First Claude CLI call delay not surfaced |

## Brutal one-liner

> Strategist is the brain that decides every routing decision. **One P0 + four P1**.
> The brain has no per-call timeout of its own (relies on caller config), no audit
> of its own decisions in `/explain`, and no idempotency — same task can re-classify
> at Claude prices on every retry. Fix #1 + #25 + #37 first.
