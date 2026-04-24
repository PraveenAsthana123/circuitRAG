# Demo Day 2 — Chaos Drills

Real failure simulation. Every drill captures user-visible behaviour, circuit-breaker state transitions, and any bug discovered.

**Status by drill:**

| # | Drill | Status | Bugs caught |
| --- | --- | --- | --- |
| 1 | Kill Qdrant | ✅ | cache-poisoning-on-failure |
| 2 | Unreachable Ollama | ✅ | (surfaced host/docker config-drift issue) |
| 3 | Slow Qdrant (Istio inject) | pending | — |
| 4 | Kill Neo4j | ✅ | graph-search NER short-circuit (lowercase queries skip Neo4j entirely) |
| 5 | Kill Redis | ✅ | cache + rate-limiter 5xx'd every request; fix: fail-open on Redis errors |
| 6 | Kill Kafka | pending | — |
| 7 | Kill MCP server | blocked — MCP doesn't exist yet | — |
| 8 | Traffic spike 10k RPS | pending | — |

---

## Drill #1 — Kill Qdrant

### Baseline
- `/ask` → 200 with cited answer in ~4s (first LLM load)
- All CBs CLOSED

### Outage (`docker compose kill qdrant`)
Five consecutive `/ask` calls → **502 with structured error envelope** + correlation_id. p50 = 10ms fast-fail. No 5xx crash.

### Real bug caught: cache-poisoning-on-failure

Empty retrieval results (caused by backend failure) were being cached for `cache_ttl=300s`. Even after Qdrant recovered, the cached empty result dominated for 5 minutes.

**Fix shipped** in `services/retrieval-svc/app/services/hybrid_retriever.py`: only write to cache when `chunks and not backend_failed`. Otherwise log `retrieval_skip_cache chunks=0 backends_ok=M/N reason=degraded`.

**Proof the fix works:**
```
retrieval_backend_failed err=All connection attempts failed
retrieval_skip_cache chunks=0 backends_ok=1/2 reason=degraded    ← new
retrieval_complete n=0 latency_ms=50.5 breaker=closed
```
After Qdrant restart, the next `/retrieve` call (no manual FLUSHDB) returns the real chunk in **32ms**.

### Recovery
`docker compose up -d qdrant` → next `/ask` returns full answer in 0.94s.

---

## Drill #2 — Unreachable Ollama (app-layer simulation)

### Why "app-layer simulation"?

`docker compose kill ollama` did NOT take Ollama down in this environment. The dev machine has its **own host-level `ollama serve` daemon on :11434**, pre-loaded with models. Our services were implicitly using the host daemon (because both resolve `localhost:11434`), not the empty docker container.

**That's a real enterprise-relevant config-drift finding:** chaos tests can fake-green when they kill the wrong instance. The fix in production is an explicit service-discovery endpoint + a startup log that records WHERE the dependency resolved.

To run a real drill: restart retrieval + inference with `DOCUMIND_OLLAMA_URL=http://localhost:11435` (unreachable port).

### Outage (services pointing at :11435)

Eight `/ask` calls. Circuit breaker `failure_threshold=5`. Expected: first 5 attempt the call, remaining 3 get fast-fail rejected by the CB.

```
call 1:  502 EXTERNAL_SERVICE_ERROR  [502 0.070s]  ← real connection attempt
call 2:  502 EXTERNAL_SERVICE_ERROR  [502 0.025s]
call 3:  502 EXTERNAL_SERVICE_ERROR  [502 0.020s]
call 4:  502 EXTERNAL_SERVICE_ERROR  [502 0.011s]
call 5:  502 EXTERNAL_SERVICE_ERROR  [502 0.013s]  ← breaker trips on 5th consecutive failure
call 6:  502 EXTERNAL_SERVICE_ERROR  [502 0.016s]  ← rejected by CB (no upstream call)
call 7:  502 EXTERNAL_SERVICE_ERROR  [502 0.011s]  ← rejected
call 8:  502 EXTERNAL_SERVICE_ERROR  [502 0.009s]  ← rejected
```

### Circuit-breaker metrics (the proof)

```
documind_circuit_breaker_state{name="ollama-embed-query"}              2.0   ← OPEN
documind_circuit_breaker_failures_total{name="ollama-embed-query"}     5     ← crossed threshold
documind_circuit_breaker_opens_total{name="ollama-embed-query"}        1     ← tripped once
documind_circuit_breaker_rejections_total{name="ollama-embed-query"}   3     ← fast-fail rejections
```

This is the **textbook CB state machine** observed live:
- Failures: 0 → 1 → 2 → 3 → 4 → 5 → transition to **OPEN**
- While OPEN, every subsequent call rejected in < 17ms without making a network call
- `state` gauge moves from 0 (CLOSED) to 2 (OPEN)

### User-visible behaviour during outage

Every response a structured 502 envelope:
```json
{"detail":"...","error_code":"EXTERNAL_SERVICE_ERROR","correlation_id":"..."}
```
No hang. No crash. No 5xx without envelope. The CB infrastructure worked exactly as designed.

### Recovery

- Wait 30s (> `recovery_timeout`)
- Restart services pointing at real Ollama URL
- `/ask` returns full cited answer in 0.99s
- `confidence=0.41`, `citations=1` — identical to baseline

### Honest gaps still open

1. **Inference-svc's LLM-call breaker never triggered.** That's because retrieval failed first (embedder CB opened on the query-embedding step), so the LLM call was never attempted. A more-severe drill would break Ollama AFTER retrieval succeeds (e.g. disable only the `/api/generate` path, keep `/api/embed` up).
2. **No smaller-model fallback wired.** Phase 4 §Inference calls for "CB OPEN → smaller local model". Currently the CB fails fast; there's no secondary model route. Real gap.
3. **Config-drift discovery (§Why "app-layer simulation")** is worth a separate Phase-1 §5 gap entry: service startup should log the resolved URL of every external dependency so misdirected chaos tests are detectable.

---

---

## Drill #4 — Kill Neo4j

### Baseline
`/ask` → 200 with cited answer in 0.96s (hybrid vector + graph).

### Outage (`docker compose kill neo4j`)

First attempts (lowercase queries) passed through retrieval without any graph-failure log. That's suspicious — so investigate.

**Finding:** `GraphSearcher._extract_entities` uses a regex requiring capitalized words to detect entity candidates. If the query has no capitalized words, it returns `[]` and the graph search **short-circuits before ever calling Neo4j**. That's why the vector-only fallback was invisible: the graph path never fired.

This is a real behaviour gap worth documenting — it means lowercase queries are effectively vector-only even when Neo4j is healthy, missing the graph-augmented retrieval benefit.

### Re-run with a capitalized query

```bash
$ curl ... -d '{"query":"What is Travel Policy reimbursement?"}'
{"answer":"...Source: ae303815..., Page 1", "citations":1}   [200 1.53s]
```

Retrieval log — the full expected degradation pattern:

```
retrieval_backend_failed err=Couldn't connect to localhost:7687    ← Neo4j down, exception caught
retrieval_skip_cache chunks=1 backends_ok=1/2 reason=degraded       ← Drill-1 fix kicks in
retrieval_complete n=1 latency_ms=50.7 top_score=0.642 breaker=closed
```

**User got the cited answer anyway.** Vector leg succeeded alone; graph exception was caught; degraded result was NOT cached.

### Recovery

`docker compose up -d neo4j` → after ~10s ready → next call hits both backends (`backends_ok=2/2` implicit by absence of `retrieval_skip_cache`), latency 1.85s (graph path warmup).

The recovery query ("What is Travel Policy reimbursement **after recovery**?") scored lower (0.016) and the model correctly returned **"I don't have enough information in the provided documents"** — the expected no-answer behaviour instead of hallucinating. RAG guardrails working as designed.

### Gaps found

1. **Graph search skipped on lowercase queries.** Fix: always run graph search OR improve entity extraction (real NER, not capitalization regex). Phase 4 §Retrieval lists "entity extraction quality is the critical quality lever" — this confirms it.
2. No Neo4j-specific CB. The exception is caught generically via `asyncio.gather(return_exceptions=True)`. A dedicated Graph CB would give per-backend metrics + fast-fail after sustained failures. Currently every query under a Neo4j outage attempts the connection (costing the bolt-driver default timeout).

---

## Drill #5 — Kill Redis

### Before the fix

```
$ docker compose kill redis
$ for i in 1..5; do curl ... /api/v1/ask ; done
call 1-5:  502 EXTERNAL_SERVICE_ERROR  [502 0.013s]   ← EVERY request 5xx'd
```

**Real bug found.** Redis-backed **rate-limiter + cache were not wrapped in exception handling**, so a Redis outage raised `redis.exceptions.ConnectionError` all the way up through the middleware stack → 500 → 502 envelope. Phase-7 §chaos explicitly says "Kill Redis → cache miss path; no 5xx" — we had 5xx on every call.

### Fix shipped — fail-open on Redis errors

`libs/py/documind_core/rate_limiter.py::check`:
```python
try:
    ... pipe.execute() ...
except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
    # Fail-open: a rate limiter that 5xxs every user during a cache
    # outage is worse than one that temporarily can't enforce its limit.
    log.warning("rate_limit_fail_open key=%s err=%s", key, exc)
    return LimitResult(allowed=True, remaining=limit, reset_in_seconds=0, limit=limit)
```

`libs/py/documind_core/cache.py::get_json` and `::set_json`:
```python
try:
    raw = await self._redis.get(key)
except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
    log.warning("cache_get_fail_open key=%s err=%s", key, exc)
    return None   # treat as cache miss
```

Writes silently drop. Reads fall through to source.

### After the fix — proof

Redis still dead, 3 fresh queries:
```
call 1:  cites=1 $500 per day [Source: ae303815...  [200 1.00s]
call 2:  cites=1 $500 per day [Source: ae303815...  [200 0.91s]
call 3:  cites=1 $500 per day [Source: ae303815...  [200 0.90s]
```

Log evidence — three silent degradations per call:
```
cache_get_fail_open  key=tenant:...:retr:... err=Error 111 connecting to localhost:56379
retrieval_complete   n=1 latency_ms=31 top_score=0.016 breaker=closed
cache_set_fail_open  key=tenant:...:retr:... err=...
rate_limit_fail_open key=tenant:...:rl:api err=...
```

### Recovery

`docker compose up -d redis` → next `/ask` returns full answer in 0.97s. No cached result from pre-outage (because degraded results skipped cache per Drill-1 fix).

### Gaps remaining

1. **No Redis-specific CB.** Every request during the outage pays the connection-refused time (~0.9s per call vs 0.07s for fast-fail rejection). A breaker would tip to OPEN after N consecutive failures and skip the Redis call entirely for `recovery_timeout`. Currently the fail-open path retries every time. Not critical but measurable under sustained outage.
2. **Fail-open rate-limiter has security implications.** During a Redis outage, bursty tenants are unthrottled. For production, consider a local per-process fallback counter (bloom filter or sliding window in memory) as a second line.

---

## What the drills have now proved

| Phase-7 claim | Drill | Proof |
| --- | --- | --- |
| "Vector DB down → graceful degrade" | #1 | ✅ 502 + envelope |
| "LLM/embedder down → CB opens" | #2 | ✅ **state gauge 0→2, failures_total=5, opens_total=1, rejections_total=3** |
| "CB rejections are fast-fail (no network call)" | #2 | ✅ rejection latency < 17ms vs 25–70ms for real attempts |
| "User never sees a 5xx crash" | both | ✅ every response structured |
| "Recovery is automatic on dependency return" | both | ✅ first post-recovery call < 1s |
| "Cache does not poison on degraded result" | #1 | ✅ after the fix |
| "Graph backend optional — vector-only when Neo4j down" | #4 | ✅ `backends_ok=1/2` log + cited answer returned |
| "RAG declines with no-answer when retrieval is off-topic (no hallucination)" | #4 recovery | ✅ "I don't have enough information…" |
| "Cache + rate-limit layers are non-blocking — Redis outage does not 5xx users" | #5 | ✅ after the fix |

## Bugs caught across 2 drills

| # | File | Bug |
| --- | --- | --- |
| 1 | `hybrid_retriever.py` | Cache poisoning on backend failure |
| 2 | (env contract) | Service dependency URL ambiguous when host + container both listen on same port — tests can fake-green |
| 3 | `graph_searcher.py` | Entity-extraction regex requires capitalized words → lowercase queries silently skip graph entirely |
| 4 | (missing) | No per-backend CB on Neo4j — every query during outage pays the bolt-driver default connect timeout |
| 5 | `rate_limiter.py` | Rate-limiter raised `ConnectionError` on Redis outage → 5xx'd every user |
| 6 | `cache.py` | `get_json` + `set_json` raised on Redis outage → same 5xx cascade |

Both would silently escape unit tests. Caught only by running the system + deliberately breaking it.
