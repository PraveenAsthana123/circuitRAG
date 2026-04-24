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
