# Latency budget + cache layer inventory — per-tool ms breakdown

> Where time goes per request, what's cached at each layer, and the
> ms-level improvements available per tool. Real benchmark numbers
> where measured; estimates where not yet measured (clearly marked).
>
> Locked by `mcp/tests/drill_latency_budget.py`.

## Cache layers — what's cached, where, TTL

| Layer | Cache | TTL | Hit rate target | Code |
| --- | --- | --- | --- | --- |
| **NGINX edge** | `/_next/static/.*` (hashed assets) | 7 days | 95%+ after warmup | `infra/nginx/nginx.conf` `proxy_cache_path` `keys_zone=static_cache:64m max_size=1g` |
| **NGINX bypass** | `/api/*` and `/api/v1/documents/upload` | NEVER | n/a | `proxy_no_cache 1; proxy_cache_bypass 1` (per CDN cache contract) |
| **Browser HTTP cache** | static assets via `Cache-Control: public; expires 7d` | 7 days | client-side | `nginx.conf` `expires 7d` directive |
| **Next.js RSC cache** | server-rendered pages (selective) | per-page | varies | Next.js `revalidate` API (per route) |
| **Redis (rate-limit)** | per-tenant token-bucket counters | sliding window | 100% (write-through) | `services/api-gateway/internal/middleware/ratelimit.go` |
| **Redis (idempotency)** | per-(idempotency-key, tool, fingerprint) | 24 hours | varies by client retry rate | `mcp/server_common.py` `_IDEMPOTENCY` |
| **Redis (response cache)** | tenant-namespaced; per-call sites | per-call TTL | varies | `libs/py/documind_core/cache.py` |
| **Postgres connection pool** | up to N connections per service | persistent | n/a (latency-eliminator) | `libs/py/documind_core/db_client.py` `asyncpg.Pool` |
| **Qdrant query cache** | per-collection, internal | LRU | provider-managed | `services/retrieval-svc/app/services/vector_searcher.py` |
| **Neo4j query cache** | per-database, internal | LRU | provider-managed | `services/retrieval-svc/app/services/graph_searcher.py` |
| **Ollama VRAM** | recently-used model weights | until eviction | 100% within session | container `documind-ollama` |
| **JWKS cache (api-gateway)** | per-kid JWT public keys | configurable (default 5 min) | 99%+ | `services/api-gateway/internal/middleware/jwt.go` |
| **Embedding cache (planned)** | content-hash → vector | 30 days | high for re-ingested content | `cache.py` placeholder |
| **LLM completion cache (PLANNED)** | (prompt-hash, model, params) → completion | 1 hour | varies; high for canned-Q&A | not shipped |

## Per-tool latency budget (real where measured)

### Health probe path — `GET /healthz`

| Hop | Latency | Source |
| --- | --- | --- |
| Browser → NGINX | < 1ms | local |
| NGINX → api-gateway (or upstream) | 1-2ms | local network |
| api-gateway → response | 1-3ms | health handler trivial |
| **Total p95** | **30ms** | k6 100 VU benchmark (`docs/benchmarks/2026-04-30-laptop.md`) |
| **Total p99** | **87ms** | same benchmark |

Cache improvement opportunity: NONE — health probes intentionally bypass cache.

### Sidecar event submission — `POST /api/v1/sidecar/events`

| Hop | Estimated | Notes |
| --- | --- | --- |
| Browser → NGINX | < 1ms | local |
| NGINX rate-limit check | 1ms | `limit_req` zone in shared memory |
| NGINX → api-gateway | 1-2ms | HTTP/2 reuse |
| api-gateway JWT validate | 2-5ms (cached pubkey) | JWKS cache hit; first call ~50ms |
| api-gateway rate-limit (Redis) | 2-5ms | Redis round-trip |
| api-gateway → sidecar-advisor | 1-2ms | local network |
| sidecar-advisor `event_id` calc | < 1ms | sha256 hash |
| sidecar-advisor SQLite insert | 5-15ms | WAL fsync |
| Response serialize | 1ms | pydantic |
| **Total p95** | **49ms (measured)** | k6 100 VU (matches sum of above ±) |
| **Total p99** | **122ms (measured)** | tail dominated by SQLite WAL fsync |

Cache improvement opportunities:
- **JWKS cache**: avoid first-call 50ms penalty by warming on startup. **Estimated save: 45ms p99** for the first request after cold start.
- **Redis rate-limit**: per-process LRU in front of Redis. **Estimated save: 2-3ms p99** under load.
- **No cache available** for the SQLite write — it IS the persistence step.

### Council pattern — full 3-model run on one issue

| Stage | Measured | Notes |
| --- | --- | --- |
| Issue load + prompt render | < 50ms | local file read + Jinja2 |
| Author 1 (deepseek-coder:6.7b) | 30-50s | Ollama first call (cold) ~120s; warm ~30s |
| Author 2 + 3 (parallel) | included in author 1 (asyncio.gather) | bounded by slowest |
| Reviewer (codegemma:7b) | 117s | empirical from drill batch |
| Advisor (codellama:7b) | 60s | empirical |
| Total empirical (warm) | **225s (3:45)** | 5 issues × ~225s = ~19 min batch |

Cache improvement opportunities:
- **Model preload**: keep all 3 council models in VRAM simultaneously. **Estimated save: 15-20s** by avoiding model swap cost. Requires GPU with > 12GB VRAM (current: 11GB).
- **Prompt-prefix cache**: vLLM's prefix cache reuses KV-cache for shared prompt prefixes. **Estimated save: 30-40% on token-heavy prompts**. Not available with Ollama.
- **LLM completion cache**: identical (prompt, model) → cached completion. **Estimated save: 100% (instant)** for repeated identical issues. Not shipped.
- **Switch to vLLM**: continuous batching + paged attention. **Estimated 2-5× throughput** at ≥ 100 concurrent.

### RAG retrieve — `POST /api/v1/retrieve`

| Hop | Estimated | Notes |
| --- | --- | --- |
| BFF → retrieval-svc | 1-2ms | local |
| Embed query (Ollama nomic-embed-text) | 30-100ms | first call cold; warm ~30ms |
| Vector search (Qdrant) | 10-30ms | depends on collection size + top_k |
| Graph search (Neo4j) | 20-100ms | depends on hop count |
| Fusion + dedupe | 5-10ms | in-process |
| Rerank (if enabled) | 20-50ms | cross-encoder forward pass |
| Response serialize | 5ms | |
| **Estimated p95** | **150-300ms** | NOT yet measured against full stack |

Cache improvement opportunities:
- **Embedding cache**: content-hash → vector. **Estimated save: 30-100ms** on cache hit (eliminates Ollama call).
- **Qdrant collection in-memory**: increase `optimizers_config` for in-RAM collections. **Estimated save: 10-15ms p95**.
- **Reranker batched on GPU**: if many top_k → batch the rerank pass. **Estimated save: 15-30ms p95** at top_k > 20.

### Ollama LLM call

| Phase | Cold | Warm | Notes |
| --- | --- | --- | --- |
| Model load (first call, model not in VRAM) | 30-90s | n/a | model-size dependent |
| Token generation | ~30 t/s on CPU; ~80 t/s on GPU | same | depends on hardware |
| Total for 200-token completion (warm) | n/a | 6-8s | typical |
| Total for 1000-token completion (warm) | n/a | 25-35s | council-reviewer prompts |

Cache improvement opportunities:
- **Pin council models in VRAM**: `OLLAMA_KEEP_ALIVE=24h`. **Estimated save: 30-90s on second call**.
- **Switch to vLLM**: 2-24× throughput via paged attention. **Estimated p95 reduction: 60-80% under load**.
- **Switch to TensorRT-LLM** (NVIDIA): 1.5-2× over vLLM. Requires CUDA/Hopper.
- **Cloud Kimi via langfuse-traced calls**: lower per-call latency for chair-tier; pay-per-use.

## Where the ms goes — Pareto chart (estimated)

For a typical end-to-end request (BFF → council → audit):

```
LLM generation (council)     ████████████████████████████████  3-4 minutes (96%)
Ollama model load (cold)     ███                                30-90s (3% if cold)
SQLite WAL fsync             █                                  5-15ms
JWKS validate (warm)         █                                  2-5ms
Vector search                █                                  10-30ms
Embed query                  █                                  30ms
Network + serialize          █                                  5-10ms
```

**The bottleneck is LLM generation, not infrastructure.** Optimizing NGINX or api-gateway saves ms; optimizing LLM saves minutes.

## Improvement opportunities ranked by ROI

| Rank | Change | Effort | Estimated impact | Where documented |
| --- | --- | --- | --- | --- |
| 1 | Pin council models in VRAM (`OLLAMA_KEEP_ALIVE=24h`) | 1 env var | 30-90s saved per cold call | this doc |
| 2 | Switch Ollama → vLLM for production-throughput | 2-3 iterations + GPU host | 2-5× throughput | `docs/MISSING.md` |
| 3 | LLM completion cache (prompt-hash → completion) | 1 iteration + Redis backed | 100% latency on repeated queries | `cache.py` placeholder |
| 4 | Embedding cache (content-hash → vector) | 1 iteration + Redis | 30-100ms on cache hit | `cache.py` placeholder |
| 5 | Warmup JWKS on api-gateway startup | 1-line code | 45ms saved on first request | new |
| 6 | Reranker batching on GPU | 1 iteration | 15-30ms p95 at top_k > 20 | RAG pipeline |
| 7 | Per-process LRU in front of Redis rate-limit | 1 iteration | 2-3ms p99 under load | api-gateway |
| 8 | Qdrant in-memory collection config | 1-line config | 10-15ms p95 | `vector_searcher.py` |

Items 1, 5, 7, 8 are < 1-iteration each (config / 1-line code). Items 2-3-4-6 are larger architectural changes.

## Per-tool micro-benchmark (real ms, captured 2026-04-30)

Run via `scripts/bench-tools.sh --iters 20`. Locked by
`mcp/tests/drill_bench_tools.py`. Latest sample on this laptop
(Linux x86_64, ~5 GiB free):

| Tool | min ms | avg ms | p95 ms | max ms | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `postgres-ping` (libpq) | 39 | 45 | 65 | 68 | binary startup dominated |
| `postgres-select1` | 37 | 45 | 66 | 73 | psql startup, not query |
| `redis-ping` (docker exec) | 48 | 56 | 63 | 65 | docker-exec wrapper cost |
| `redis-set-get` | 120 | 141 | 199 | 201 | 2× docker exec |
| `qdrant-readyz` (HTTP) | 7 | 9 | 14 | 16 | true HTTP RTT |
| `qdrant-list` (api-key) | 8 | 8 | 13 | 13 | true HTTP RTT |
| `neo4j-cypher` (cypher-shell) | **1604** | **1768** | **1948** | **2020** | **JVM startup** — see warning |
| `ollama-tags` | 7 | 8 | 10 | 11 | local HTTP, very fast |
| `ollama-ps` | 6 | 9 | 22 | 25 | local HTTP |
| `prometheus-health` | 6 | 6 | 8 | 9 | local HTTP |
| `grafana-health` | 6 | 6 | 9 | 11 | local HTTP |
| `alertmgr-health` | 6 | 7 | 9 | 11 | local HTTP |
| `jaeger-root` | 6 | 7 | 10 | 11 | local HTTP |
| `loop-jsonl-append` | 2 | 2 | 2 | 3 | audit-row write speed |
| `drill-langgraph` (py drill) | 25 | 29 | 42 | 43 | drill runtime cost |
| `drill-cdn-cache` | 26 | 30 | 46 | 47 | drill runtime cost |
| `drill-load-test` | 26 | 31 | 40 | 56 | drill runtime cost |

**The 1.7-second neo4j number is the headline finding.** It is NOT
the Bolt protocol RTT (which is sub-ms). It is `docker exec` +
**JVM startup** + cypher-shell init. Operators who shell out to
`cypher-shell` in hot paths burn 1.7s per invocation. Use the Bolt
client from a long-lived Python process instead — the
`graph_searcher.py` does this correctly.

**Second observation: docker-exec adds ~50-100ms** to any container
probe (redis-ping, redis-set-get). The protocol underneath is sub-ms;
the wrapper dominates. For real protocol-level measurements, use a
persistent client.

**Third observation: pure-HTTP probes against local services
consistently hit 6-14ms p95** — that's the Linux loopback +
HTTP-server-handling floor for this hardware. `loop-jsonl-append`
at 2ms is the disk-write floor.

## What's NOT yet measured (honest gaps)

- **Per-hop OTel breakdown** for a real request: requires Jaeger UI inspection of a sample correlation_id while full stack is up. Not done in this benchmark.
- **Cache hit rates** in production: Redis cache.py exists but no metrics published; would need `documind_cache_hit_rate{layer}` histograms.
- **Tail latencies (p99.9)**: k6 baseline reports up to p99 only.
- **LLM token-level latency**: TTFT (time-to-first-token) not measured; would need streaming endpoint instrumentation.

## Cross-tool data tracking — correlation_id pattern reminder

Every request stamps a UUID v4 at the gateway. Trace it across every layer:

```bash
CID="<correlation-id-from-error-envelope>"
grep "$CID" /var/log/nginx/access.log              # NGINX layer time
grep "$CID" services/*/logs/*.json 2>/dev/null      # service times
psql ... -c "SELECT * FROM audit_log_partitioned WHERE correlation_id='$CID'"
grep "$CID" .loop/issue_audit.jsonl                # LLM call duration
curl -s "http://localhost:16686/api/traces?tags=correlation_id:$CID"  # OTel breakdown
```

The OTel trace is THE per-hop breakdown — once Jaeger has spans for a request, you see exact ms per layer.

## Composes with

- `docs/STATUS.md` — what's actually shipped
- `docs/MISSING.md` — what would top-tier need (vLLM, etc.)
- `docs/benchmarks/2026-04-30-laptop.md` — real k6 numbers
- `docs/runbooks/component-trust.md` — verification commands per component
- `infra/load-test/k6/baseline.js` — the load test producing these numbers

## Brutal rule

> Latency optimization without measurement is guessing. The Pareto
> shows LLM generation is 96% of council-time; tuning NGINX is a
> rounding error in that context. Measure first (Jaeger trace +
> Prometheus histograms), THEN optimize the actual bottleneck.
> Every "estimated save" above is a hypothesis until verified by
> a benchmark before/after.
