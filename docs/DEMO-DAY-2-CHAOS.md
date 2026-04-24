# Demo Day 2 — Chaos Drill #1: Kill Qdrant

**Status:** 🟢 Green — graceful degradation proven, recovery automatic, and a real cache-poisoning bug caught and fixed.

**Date:** 2026-04-24

---

## Baseline (Qdrant up)

```bash
$ curl -sX POST http://127.0.0.1:8084/api/v1/ask \
    -H "X-Tenant-Id: $TENANT_UUID" \
    -d '{"query":"reimbursement limit?"}'
```

```
answer: $500 per day [Source: ae303815..., Page 1]
citations: 1
confidence: 0.41
[200, 4.4s]

documind_circuit_breaker_state{name="ollama-embed-query"} 0.0   (CLOSED)
documind_circuit_breaker_state{name="retrieval-quality"} 0.0    (CLOSED)
```

## Outage (docker compose kill qdrant)

```bash
$ docker compose kill qdrant
 Container documind-qdrant  Killed

$ for i in 1..5; do curl ... /api/v1/ask ... ; done
call 1:  No chunks retrieved — is the corpus empty? [502 0.067s]
call 2:  No chunks retrieved — is the corpus empty? [502 0.011s]
call 3:  No chunks retrieved — is the corpus empty? [502 0.012s]
call 4:  No chunks retrieved — is the corpus empty? [502 0.008s]
call 5:  No chunks retrieved — is the corpus empty? [502 0.010s]
```

### Observations during outage

| Observation | Interpretation |
| --- | --- |
| HTTP 502 with structured error envelope | ✅ No 5xx crash |
| `correlation_id` present on every error | ✅ Debuggable |
| p50 latency 10ms (near-instant failure) | ✅ Fast-fail, no hang |
| `retrieval_backend_failed err=All connection attempts failed` | ✅ Exception caught by `asyncio.gather(return_exceptions=True)` |
| `retrieval_complete ... n=0 breaker=closed` | ⚠️ Retrieval CB stayed CLOSED even with all hits failing |

## Real bug caught during the drill

**Finding:** Empty retrieval results (caused by backend failure) were being cached for `cache_ttl=300s`. Even after Qdrant came back, the cached "empty" result would be served for 5 minutes — a textbook **cache-poisoning-on-failure** pattern.

### Proof (before fix)

```bash
# Qdrant was restarted but cached empty result dominated:
$ curl ... /api/v1/retrieve
{"chunks":[], "cached":true, "latency_ms":0.5}   # hit the poisoned cache
```

### Fix shipped

`services/retrieval-svc/app/services/hybrid_retriever.py`:

```python
# Cache — BUT ONLY on non-degraded results. If every backend failed
# (len(ranked_lists) < len(coros)) OR we got zero chunks back, skip the cache
# so a transient dependency outage doesn't poison retrieval for
# cache_ttl seconds.
backend_failed = len(ranked_lists) < len(coros)
if chunks and not backend_failed:
    await self._cache.set_json(key, {...}, ttl=self._cache_ttl)
else:
    log.info(
        "retrieval_skip_cache chunks=%d backends_ok=%d/%d reason=degraded",
        len(chunks), len(ranked_lists), len(coros),
    )
```

### Proof (after fix)

```
# During outage:
retrieval_backend_failed err=All connection attempts failed
retrieval_skip_cache chunks=0 backends_ok=1/2 reason=degraded   ← new log line
retrieval_complete n=0 latency_ms=50.5 breaker=closed

# After Qdrant recovery (no manual FLUSHDB):
$ curl ... /api/v1/retrieve
{"chunks":[{chunk_id:fbf7d170..., text:"The travel policy..."}],
 "latency_ms":32.1, "cached":false}   ← REAL RESULT IN 32ms
```

## Recovery (docker compose up -d qdrant)

After restart:
- `/ask` returns full answer with citation in 0.94s
- Confidence 0.41 (matches baseline)
- No manual intervention needed

## What the drill proved

| Claim from Phase 7 docs | Proof |
| --- | --- |
| "User-visible response is structured, not a crash" | ✅ 502 + envelope + correlation_id |
| "System degrades gracefully when Qdrant is down" | ✅ verified |
| "Cache policy must skip degraded results" | ✅ **enforced after fix** |
| "Retrieval CB opens under quality pressure" | ⚠️ CB stayed CLOSED — quality-window thresholds likely need tuning with real traffic data (Day-3 work) |
| "Recovery is automatic when dependency returns" | ✅ first call after restart: 32ms, real chunk, not cached |

## Remaining CB-behaviour gaps (honest)

1. `RetrievalCircuitBreaker` is a **quality-window** breaker (`min_quality=0.35` over 20 samples). 5 test failures weren't enough to cross the rolling threshold. Needs either a shorter window for dev or a separate failure-count breaker for hard backend errors.
2. BM25 fallback path was NOT exercised — the hybrid retriever's `ranked_lists` included only vector (failed) + graph (0 hits). No keyword fallback tier is wired in retrieval-svc yet. Phase 4 §Retrieval calls for this; it's a real gap.
3. No Jaeger trace captured — OTel collector is down so the Observability CB is skipping export silently (by design). Day-3 work: start collector + capture trace.

## Chaos drill matrix — status after Day 2.1

| Drill | Status |
| --- | --- |
| **Kill Qdrant** | ✅ this doc |
| Slow Qdrant (2s Istio fault inject) | ⏳ Day 2.2 |
| Kill Ollama | ⏳ Day 2.3 — will test inference-CB fallback to smaller model |
| Kill Neo4j | ⏳ Day 2.4 — should degrade to vector-only |
| Kill Redis | ⏳ Day 2.5 — cache miss path + stricter rate limits |
| Kill Kafka | ⏳ Day 2.6 — outbox accumulates; verify relay catches up |
| Kill MCP server | ❌ blocked — no MCP code yet |
| High traffic spike (10k RPS) | ⏳ load test |
