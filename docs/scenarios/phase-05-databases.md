# Phase 5 — Databases / Stores

**Status:** Stub. Catalog at [/tools/database-scenarios](../../services/frontend/app/tools/database-scenarios/page.tsx).

## Clean starting stack (deliberately minimal)

| Purpose | Store | Port (dev) | Why |
| --- | --- | --- | --- |
| Metadata + history | PostgreSQL 16 | 55432 | ACID + RLS + transactional outbox |
| Vector search | Qdrant 1.12 | 6333 | HNSW + scalar quantization + mandatory tenant payload filter |
| Cache | Redis 7.4 | 56379 | sub-ms reads, tenant-namespaced keys, rate-limit + CB state |
| Graph reasoning | Neo4j 5.23 | 7687 | 1-hop entity expansion from ANN top-K |
| Files | MinIO | 59000 / 59001 | S3-compat, signed URLs for direct upload |
| Events | Kafka 3.7 | 59092 | ingestion + audit + billing + eval replay |

Port overrides live in `docker-compose.override.yml`. See [DEMO-DAY-1.md](../DEMO-DAY-1.md) for why.

## Per-store scenarios (exit criteria)

### Postgres

- [ ] FORCE RLS on every tenant table (`ingestion.*`, `identity.*`, `governance.*`, `finops.*`, `eval.*`).
- [ ] Three roles: `documind` (owner) · `documind_app` (NOBYPASSRLS) · `documind_ops` (BYPASSRLS, audited).
- [ ] `libs/py/tests/test_rls_isolation.py` green against live PG. **DONE.**
- [ ] WAL mode + PgBouncer-ready DSN.

### Qdrant

- [ ] Shared collection + payload filter per tenant (default).
- [ ] Per-tenant collection option for regulated customers.
- [ ] Shadow-index pattern documented for embedding upgrades.

### Redis

- [ ] `Cache.tenant_key(t, k)` — no raw-key API.
- [ ] TTL per cache layer (see phase-04-rag-core.md § Cache).
- [ ] Never cache PII responses (enforced at Cache.set level).

### Neo4j

- [ ] Schema: `(:Document)-[:CONTAINS]->(:Chunk)-[:MENTIONS]->(:Entity)`.
- [ ] Unique constraint on `(tenant_id, id)` per label.
- [ ] Sample Cypher queries in `docs/architecture/cypher-queries.md`.

### Kafka

- [ ] Topic catalog: `document.lifecycle`, `query.lifecycle`, `cost.events`, `policy.changes`, `audit.events`.
- [ ] DLQ pattern + `max_retries=3` consumer.
- [ ] CloudEvents envelope + JSON Schema per event type.

### MinIO

- [ ] Bucket policy per tenant.
- [ ] Signed URL direct upload (service never proxies bytes).
- [ ] Lifecycle rule: archive → cold tier after 90d.

## Gaps not yet closed

| Store | Missing |
| --- | --- |
| Cold-tier (Parquet + DuckDB/Athena) | Design Area 37 — designed only, not built |
| Time-series TSDB (Prometheus TSDB is OK for metrics; no Mimir for long-range) | fine for dev; plan for prod |
| Keyword-only search (Elasticsearch for BM25) | using Postgres full-text today; acceptable |
| Partitioned tables for `audit_log`, `token_usage` | planned, not applied |

## Phase-5 exit criteria (concrete)

- [ ] ERD in `docs/architecture/erd.md` (generated via `pg_dump --schema-only` → Mermaid or PlantUML).
- [ ] Event catalog generated from `schemas/events/*.json` → `docs/events/catalog.md`.
- [ ] Graph schema + sample queries in `docs/architecture/neo4j.md`.
- [ ] Cache key style guide in `docs/architecture/cache-keys.md`.
