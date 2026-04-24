# Phase 23 — Capacity Planning & Estimation

Capacity planning is not infra — it is business survival. Skip this and the system crashes / cost explodes / SLA breaks.

---

## 1. Core inputs (you must define these per deploy)

| Input | Example |
| --- | --- |
| Daily users | 10,000 |
| Peak concurrent users | 1,000 |
| Queries per user/day | 20 |
| Avg tokens per query | 2000 |
| Avg doc size | 5 MB |
| Docs/day | 1,000 |
| Top-K retrieval | 5–10 |
| LLM latency | 2–5 s |
| SLA | p95 < 3 s |

## 2. Request-capacity math

| Metric | Value |
| --- | --- |
| Users | 10,000 |
| Queries/day | 200,000 |
| Queries/sec (avg) | ~2.3 |
| Peak factor (× 10) | ~25 QPS |

**Design for peak, not average.**

## 3. Component capacity targets

### Gateway
| Metric | Target |
| --- | --- |
| RPS | 25–100 |
| Latency | < 50 ms |
| Scaling | horizontal |

### Retrieval
| Metric | Target |
| --- | --- |
| QPS | 25–100 |
| Latency | < 500 ms |
| Vector DB | optimized HNSW + quantization |
| Cache hit | > 30% |

### Inference (most expensive)
| Metric | Target |
| --- | --- |
| Concurrent calls | 50–200 |
| Latency | 2–5 s |
| Tokens/sec | model-dependent |
| GPU/CPU | model-dependent |

### Ingestion
| Metric | Target |
| --- | --- |
| Docs/day | 1000+ |
| Chunks/sec | scalable workers |
| Embedding throughput | batch-optimized |

### MCP
| Metric | Target |
| --- | --- |
| Tool latency | 2–10 s |
| Async support | required |
| Queue | Kafka |

## 4. Token-driven capacity

| Metric | Value |
| --- | --- |
| Queries/sec | 25 |
| Tokens/query | 2000 |
| Tokens/sec | 50,000 |
| Tokens/min | 3M |
| Tokens/day | 4.3B |

Drives cost, model selection, scaling strategy.

## 5. Cost estimation

| Lever | Effect |
| --- | --- |
| Token cost per 1K | primary cost driver |
| Cache hit 30% | ~30% cost reduction |
| Model downgrade (tier) | 3–10x cost reduction |
| Batch processing | 2–3x throughput gain |

## 6. Scaling strategies

| Strategy | Where |
| --- | --- |
| Horizontal scaling | gateway, retrieval |
| GPU scaling | inference |
| Auto-scaling | Kubernetes HPA |
| Queue buffering | Kafka |
| Cache layer | Redis (hit-rate > 30%) |
| Async processing | ingestion, MCP |
| Model routing | cheap for low-risk |
| Region scaling | multi-region |
| Load shedding | drop low-priority first |
| Circuit breaker | protect the protected |

## 7. Storage estimation

| Item | Value |
| --- | --- |
| Docs/day | 1000 |
| Avg size | 5 MB |
| Daily storage | 5 GB |
| Chunks/doc | 100 |
| Chunks/day | 100,000 |
| Vector size | 768 × float32 |
| Vector storage/day | ~300 MB |

## 8. Failure scenarios

| Failure | Cause | Fix |
| --- | --- | --- |
| LLM overload | too many requests | rate limit + queue |
| Vector DB slow | high QPS | index tuning + cache |
| High latency | large tokens | reduce context |
| Cost spike | token explosion | budget CB |
| Kafka lag | ingestion spike | scale consumers |
| MCP delay | slow external API | async |
| Memory crash | large docs | chunk streaming |
| GPU exhaustion | heavy model | route to cheaper |
| Cache-miss storm | cold start | warm cache |
| Region failure | infra issue | failover |

## 9. Load-test contracts

| Test | Tool | Assertion |
| --- | --- | --- |
| Baseline (25 QPS) | k6 / Locust | p95 < 3s; 0 5xx |
| Peak (100 QPS) | k6 | p95 < 5s; < 1% 5xx |
| Token spike | synthetic prompts | cost tracked; Token CB trips at budget |
| LLM failure | kill Ollama | fallback works; UI shows degraded |
| Cache cold-start | flush Redis | p95 spikes for 1 min then recovers |
| Region failover | stop region A | p95 in region B stays within SLA |

## 10. Exit criteria

- [ ] `docs/architecture/capacity-planning.md` with filled-in deployment numbers.
- [ ] `scripts/load/` with k6/Locust scripts per scenario.
- [ ] HPA manifests use custom metric `inference_inflight` (not just CPU).
- [ ] `finops.token_usage` roll-up Grafana panel per tenant.
- [ ] Alerts: token-budget burn, Kafka consumer lag, HPA saturation.
- [ ] Documented cost model per-tenant-per-month in `docs/architecture/cost-estimation.md`.

## 11. Brutal checklist

| Question | Required |
| --- | --- |
| Do you know your peak QPS? | Yes |
| Can the system scale automatically? | Yes |
| Can cost be estimated per-query? | Yes |
| Can the system handle traffic spikes? | Yes |
| Can it degrade gracefully? | Yes |
| Is storage growth planned? | Yes |
| Are capacity metrics tracked live? | Yes |
