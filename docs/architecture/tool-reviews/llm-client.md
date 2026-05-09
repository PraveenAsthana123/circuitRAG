# `LlmClient` Protocol + `LlmClientPool` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/llm_clients/`
**Date:** 2026-05-01 (review) · 2026-05-08 (P0 #36 closure verified)

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0 — will-break-prod** | **0** | row #36 closed: per-backend `CircuitBreaker` wired into `LlmClientPool.__init__` with `expected_exception=LlmClientUnavailable`; `execute()` routes via `breaker.call_async`; `CircuitOpenError` caught + logged with `kind='breaker_open'` in fallback_log. Drilled by `mcp/tests/drill_llm_pool_breaker.py` (8 steps, 4 negative — empirical trip + per-backend isolation). |
| **P1 — silent-degradation** | **3** | rows #11 (no slow-call), #12 (no sliding window), #34 (no graceful shutdown of subprocess clients) |
| **P2 — operational** | 4 | rows #19 (no force-flip backend), #20 (no on-call hooks), #21 (no persistent backend-health), #22 (no health probe) |
| **P3** | several | metrics, audit hooks |

## Critical (A)

| # | Dimension | Status | Note |
|---|---|---|---|
| 1 | Per-call timeout | ✅ | `timeout_seconds` on every backend (`asyncio.wait_for`) |
| 2 | Cancellation safety | ✅ | Subprocess clients catch `asyncio.TimeoutError` separately from `CancelledError` |
| 3 | Atomic state transitions | ✅ | Pool dispatch is stateless |
| 4 | Race-free state writes | n/a | Stateless pool |
| 5 | Narrowed exception scope | ✅ | `LlmClientUnavailable` is the boundary error |
| 6 | No silent fallback | ✅ | `AllBackendsUnavailable` raised when chain exhausted; logs every transition |

## Resilience (B)

| # | Dimension | Status | Note |
|---|---|---|---|
| 7 | Concurrency cap | ✗ | **P1** — pool admits unlimited concurrent calls per backend |
| 8 | Success threshold | n/a | Pool is dispatch, not state machine |
| 9 | Exp backoff | ✗ | **P1** — fallback chain tries each handle once; no backoff on retry |
| 10 | Bulkhead | ✗ | **P1** — same as #7; no max-concurrent on backend |
| 11 | Slow-call detection | ✗ | Per-call latency not tracked |
| 12 | Sliding-window | ✗ | No backend-level health rate; just succeeds/fails |

## Observability (C)

| # | Dimension | Status | Note |
|---|---|---|---|
| 13 | Latency histogram | ✗ | **P1** — no Prom histogram on `LlmCallResult` |
| 14 | Success counter | ✗ | No counter |
| 15 | Exception-class label | ✗ | Errors logged but not Prom-labeled |
| 16 | Transition counter | n/a | Not a state machine |
| 17 | Stuck-in-X | n/a | — |
| 18 | Drills | ⚠ | `drill_llm_clients_protocol` exists; doesn't drill latency/cost flow end-to-end |

## Operator API (D)

| # | Dimension | Status | Note |
|---|---|---|---|
| 19 | Manual override | ✗ | **P2** — operator can't disable a backend ('claude_cli temporarily flaky, route to ollama') without code change |
| 20 | State-change callback | ✗ | No hook on backend availability changes |
| 21 | Persistent backend-health | ✗ | Each pool starts fresh; backend-flap memory not shared |
| 22 | Health-derived | ✗ | No periodic backend probe |

## Project policies (E)

| # | Dimension | Status | Note |
|---|---|---|---|
| 23 | Cost-of-failures | ⚠ | `LlmCallResult.cost_usd_cents` exists on success; no parallel for failed calls |
| 24 | Rollback signal | ✗ | Pool failure not a Observer signal |
| 25 | Audit row | ⚠ | Routing trail flows to audit_events but not to /explain |
| 26 | Per-tenant scope | ✗ | **P2** — pool is per-service, not per-tenant; tenant A's bad prompts can saturate Claude for tenant B |
| 27 | OTel propagation | ✗ | No span attributes from the pool |
| 28 | Sync+async lock | n/a | Async-only |
| 29 | Dead code | ✅ | clean |
| 30 | API drilled | ✅ | Protocol drilled |

## Cross-cutting (F)

| # | Dimension | Status | Note |
|---|---|---|---|
| 31 | Identity boundary | ✗ | **P0** — no propagation of caller identity into Tier-B (Claude/Codex run as the local CLI's user, not the request's user) |
| 32 | Body size limit | ⚠ | Prompt size not capped at the pool boundary |
| 33 | Rate limit | ✗ | No rate limit on pool calls; one tenant can starve others |
| 34 | Graceful shutdown | ✗ | **P1** — `pool.close()` exists but isn't called by service.aclose() reliably for subprocess clients |
| 35 | Memory-bounded state | ✅ | Stateless |
| 36 | DB/dep CB around tool | ✗ | **P0** — there's no CB wrapping the LlmClient itself! ClaudeCliClient can hang forever (modulo the per-call timeout — fixed in CB-A1 but not auto-applied here) |
| 37 | Idempotency under retry | ✗ | No idempotency key on LLM calls |
| 38 | Deadletter | ✗ | Failed calls just log + raise |
| 39 | Cost ceiling | ⚠ | Router has budget; pool itself doesn't |
| 40 | Cold-start | ✗ | Subprocess CLI cold-start (~2-5s for Claude CLI first call) not measured |

## Brutal one-liner

> The Pool dispatches correctly but offers **none of the resilience surface
> the underlying CB has** — no breaker, no rate limit, no per-tenant scope, no
> graceful shutdown of subprocess clients. **6 P0/P1 items.** A hung Claude CLI
> still takes the pool down today; the breaker on the LlmClient call site
> is what saved us in CB-A1, not anything in this module.
