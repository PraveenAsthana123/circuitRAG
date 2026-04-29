# Phase 5 — Databases / Stores

**Status:** Specified. Clean starting stack running (see [DEMO-DAY-1.md](../DEMO-DAY-1.md)). Per-store scenarios still need integration tests.

---

## 1. Clean starting stack

| Purpose | Store | Dev port | Production substitutes |
| --- | --- | --- | --- |
| Metadata + history | **PostgreSQL 16** | 55432 | Azure PG / RDS / CloudSQL |
| Vector search | **Qdrant 1.12** | 6333 | Milvus / pgvector / Weaviate / Pinecone |
| Cache | **Redis 7.4** | 56379 | Valkey / DragonflyDB |
| Graph reasoning | **Neo4j 5.23** | 7687 | Neptune / Memgraph / ArangoDB |
| Object / blob | **MinIO** | 59000 | S3 / Azure Blob / GCS |
| Events | **Kafka 3.7** | 59092 | Redpanda / Pulsar / Kinesis |
| Keyword (fallback) | **OpenSearch** (planned) | — | Elasticsearch / Solr |
| Metrics (TSDB) | **Prometheus** | 9090 | Mimir / VictoriaMetrics / Timescale |

Port overrides in [docker-compose.override.yml](../../docker-compose.override.yml). All six core stores verified healthy on Day 1.

## 2. Per-store scenario tables

### Vector DB (Qdrant)

| Scenario | What happens | Edge case / fallback |
| --- | --- | --- |
| Semantic chunk retrieval | Query embedding → top-K chunks | Low score → ask clarification |
| Tenant-aware search | `must: [{tenant_id}]` filter | Missing tenant → **fail closed** |
| Metadata-filtered retrieval | Filter by region / role / doc type | Mismatch → no result |
| Multi-index retrieval | Policy index + FAQ index | Merge + rerank |
| Embedding version upgrade | Re-embed via shadow collection | Version conflict → flag flip |
| Similar-document detection | Compare vectors | Duplicates flagged at ingest |
| Multimodal retrieval | Image + text embeddings | Fallback to text-only |
| Vector DB slow | CB opens | BM25 / cache fallback |

### Historical DB (Postgres)

| Scenario | What is stored |
| --- | --- |
| Document metadata | `ingestion.documents` — id, tenant, source, version |
| Chunk metadata | `ingestion.chunks` — chunk_id, parent, section, offsets, embedding_version |
| Conversation history | `identity.sessions` — session, turns, citations |
| Audit history | `governance.audit_log` — who, what, when, policy_version |
| Evaluation results | `eval.runs` — faithfulness, context precision/recall |
| Cost history | `finops.token_usage` partitioned daily |
| Policy versions | `governance.policies` — versioned CEL rules |
| MCP action history | `governance.mcp_actions` — tool, payload hash, idempotency key |

### Cache DB (Redis)

| Key pattern | Scenario | TTL |
| --- | --- | --- |
| `tenant:{id}:q:{hash}` | Semantic answer cache | 1h |
| `tenant:{id}:retr:{hash}` | Retrieval result cache | 15m |
| `tenant:{id}:sess:{uid}` | Session + conversation state | 1h sliding |
| `rl:{tenant}:{window}` | Rate-limit counter | Window |
| `cb:{name}:{instance}` | Circuit breaker state | Live |
| `docmeta:{tenant}:{doc_id}` | Hot document metadata | 24h |
| `mcp:{tool}:{req_hash}` | MCP tool result cache | 5m |
| `flags:{tenant_id}` | Feature flag cache | 5m |

### Graph DB (Neo4j)

| Scenario | Graph example |
| --- | --- |
| Policy dependency | `policy → clause → exception` |
| Customer 360 | `customer → account → product → case` |
| Supply chain | `supplier → part → plant → shipment` |
| Legal reasoning | `contract → obligation → risk` |
| IT incident analysis | `service → dependency → incident` |
| Entity expansion | retrieved chunk → related entities |
| Impact analysis | changed document → affected processes |

Schema: `(:Document)-[:CONTAINS]->(:Chunk)-[:MENTIONS]->(:Entity)`. Unique constraint on `(tenant_id, id)` per label.

### Object store (MinIO)

| Scenario | Stored object |
| --- | --- |
| Original upload | PDF / DOCX / image (tenant bucket) |
| Parsed text | Extracted .txt / JSON |
| OCR output | Text + confidence score |
| Chunk artifact | Chunk JSON (debugging) |
| Eval dataset | Golden Q/A files |
| Generated report | PDF / CSV export (signed URL access) |
| Model artifact | Prompt / model config snapshot |
| Failed ingestion | Bad-file sample for debug |

### Event store (Kafka)

See [phase-02-kafka-event-architecture.md](phase-02-kafka-event-architecture.md) for the full topic catalog.

## 3. Database failure matrix

| Failure | Impact | Fallback |
| --- | --- | --- |
| Qdrant down | Semantic search fails | BM25 + cache |
| Postgres down | Metadata / policy risk | **Fail closed** on secured queries |
| Redis down | Cache + rate-limit lost | Bypass cache; stricter gateway limits |
| Neo4j down | Graph expansion unavailable | Vector-only retrieval |
| MinIO down | Upload / download fails | Reject upload with 503; **keep Q&A alive** |
| Kafka down | Async events delayed | Local outbox buffers; relay catches up |
| OpenSearch down | Keyword fallback unavailable | Vector-only |
| Prometheus down | Visibility degraded | App logs still emitted |

## 4. Exit criteria

- [ ] ERD generated from `pg_dump --schema-only` → `docs/architecture/erd.md` (Mermaid).
- [ ] Event catalog generated from `schemas/events/*.json` → `docs/events/catalog.md`.
- [ ] Graph schema + sample Cypher in `docs/architecture/neo4j.md`.
- [ ] Cache key style guide in `docs/architecture/cache-keys.md`.
- [ ] `test_rls_isolation.py` green. **DONE.**
- [ ] Per-store integration test asserts failure matrix (kill store → expected fallback):
  - [ ] `tests/db/test_qdrant_down_fallback.py`
  - [ ] `tests/db/test_redis_bypass.py`
  - [ ] `tests/db/test_neo4j_down_vector_only.py`

## 5. Brutal checklist

| Question | Required |
| --- | --- |
| Is tenant ID enforced in every store? | Yes |
| Are vector indexes versioned? | Yes — `embedding_version` per chunk |
| Are chunks + embeddings versioned? | Yes |
| Are cache keys tenant-safe? | Yes — `tenant_key()` wrapper |
| Can raw document be traced to answer citation? | Yes — `doc_id` + `chunk_id` in citation |
| Can graph expansion fail safely? | Yes — vector-only fallback |
| Is audit history immutable? | Append-only; hash-chain writer planned |
| Can events be replayed? | Yes — `eval.replay.requested.v1` |

---

## 6. How to explain datastore choices in interviews

Do not present the stack as a shopping list. Present it as **roles**:

- Postgres for transactional truth
- Qdrant for semantic retrieval
- Redis for cache and short-lived coordination
- Kafka for durable async event flow
- MinIO / S3 for raw artifacts
- ClickHouse / Prometheus style stores for analytics and time-series behavior

Use the same explanation frame for every store:

1. core concept
2. problem it solves
3. why this store fits
4. when to use
5. when not to use
6. input -> process -> output
7. flowchart
8. sequence
9. tradeoffs
10. challenges
11. edge cases
12. limitations

### Example: Postgres + RLS

**Core concept**

Postgres is the system of record for transactional, relational, and
auditable domain state.

**Problem**

You need ACID semantics, tenant isolation, queryable domain data, and
privileged access that can be audited.

**Why this store fits**

- transactions matter
- relational joins matter
- tenant isolation matters
- operational access must be explainable

**When not to use**

- semantic retrieval
- append-heavy observability firehose
- large binary objects
- ultra-ephemeral coordination state

**Input -> Process -> Output**

- `Input:` tenant-scoped request + actor + domain payload
- `Process:` service sets tenant context, query/write executes under RLS, audit emitted
- `Output:` correct tenant-isolated transactional state

**Flowchart**

```text
Request arrives
  -> resolve tenant + actor
  -> open transaction
  -> set tenant context
  -> run read/write under RLS
  -> commit or rollback
  -> emit audit + metrics + traces
```

**Sequence**

```text
Client -> Service: request
Service -> Middleware: resolve tenant
Middleware -> Postgres: SET LOCAL app.current_tenant
Service -> Postgres: SELECT / INSERT / UPDATE
Postgres -> RLS policy: apply tenant filter
Postgres -> Service: rows or error
Service -> Audit: write event
Service -> Client: response
```

### Challenges to call out

- real RLS correctness cannot be proven with mocks
- ops-role separation increases learning curve
- pool sizing and long-running queries can degrade the whole service
- migrations and privilege boundaries must stay intentional

### Edge cases to call out

- app role missing tenant context
- admin job needing cross-tenant reads
- migration passes locally but breaks real policy assumptions
- background worker accidentally using privileged connection path

### Limitations to call out

- relational correctness does not replace app-layer policy
- single cluster can still be a noisy-neighbor risk
- RLS protects row visibility, not all business semantics

---

## 7. Datastore decision questions

Use these questions when choosing a store:

1. Is this source-of-truth or derived state?
2. Do I need ACID or eventual consistency?
3. Is the access pattern relational, semantic, append-heavy, or ephemeral?
4. What is the tenant/isolation boundary?
5. What are the replay and failure-recovery requirements?
6. What evidence and observability does this store need?

### Short mapping

- `Postgres` -> transactional truth
- `Qdrant` -> semantic retrieval
- `Redis` -> cache / session / rate-limit state
- `Kafka` -> async event durability
- `MinIO/S3` -> raw file storage
- `ClickHouse / TSDB` -> analytics and observability

That is the datastore story interviewers care about: **role-driven choice,
not product-name memorization**.
