'use client';

/**
 * Database/datastore deep dive — applies the universal 20-dimension
 * interview framework to each datastore role this project uses.
 *
 * Pattern: same as /admin/llmops/deep + /admin/python/deep, but using
 * the new <UniversalDeepDive /> component so future deep-dive pages
 * can reuse the same shape without reimplementing it.
 *
 * Six datastore roles (the user's "by role, not by technology" framing):
 *   1. Postgres + RLS    (transactional truth)
 *   2. Qdrant            (semantic retrieval)
 *   3. Redis             (cache + transient state)
 *   4. Kafka             (durable event transport)
 *   5. ClickHouse        (analytics / time series)
 *   6. S3 / object store (raw artifact)
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const DATASTORES: Topic[] = [
  // ---- 1. Postgres + RLS ----
  {
    slug: 'postgres-rls',
    title: '1. Postgres + RLS (transactional truth)',
    status: 'shipped',
    coreConcept: 'Postgres is the system of record for transactional, relational, and auditable domain data. RLS forces tenant isolation at the database layer — defense in depth even when app-layer checks slip.',
    problem: 'You need ACID guarantees, tenant isolation, queryable domain state, and an audit-grade access path. Mocking it isn\'t enough — RLS bugs only surface against a real cluster.',
    whyThisApproach: 'Postgres is the right choice when correctness matters more than throughput, multi-tenancy is required, and the data is relational. RLS provides tenant isolation as a database invariant, not just an application convention.',
    whenToUse: [
      'Transactional domain data (audit_log, action_drafts, prompts, identities)',
      'Multi-tenant SaaS where leakage is unacceptable',
      'Relational queries with joins',
      'Auditable operational access',
    ],
    whenNotToUse: [
      'Semantic nearest-neighbor search → use a vector DB',
      'Ultra-high-volume telemetry → use ClickHouse',
      'Ephemeral state → use Redis',
      'Raw blob storage → use S3',
    ],
    input: 'Request with tenant_id (header) + actor (JWT sub) + domain payload',
    process: [
      'Middleware sets app.current_tenant via SET LOCAL',
      'Application uses NOBYPASSRLS app role (documind_app)',
      'Query/write executes under RLS policy',
      'Privileged ops use a separate audited role (documind_ops)',
      'Migrations run as owner role with explicit grants',
    ],
    output: 'Tenant-isolated row read/write with transactional consistency and an auditable access path.',
    flowchart: `flowchart LR
  a[Request arrives] --> b[Middleware resolves tenant]
  b --> c[Acquire pool conn as documind_app]
  c --> d[SET LOCAL app.current_tenant]
  d --> e[Run query/write]
  e --> f{RLS allows?}
  f -->|yes| g[Commit + emit audit/metrics]
  f -->|no| h[Reject: row hidden or insert blocked]
  g --> i[Response]
  h --> j[Empty result OR error]`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant Svc as Service
  participant Mid as Middleware
  participant PG as Postgres
  participant Aud as audit_log
  Cli->>Svc: request + X-Tenant-ID + JWT
  Svc->>Mid: extract tenant + actor
  Mid->>PG: BEGIN; SET LOCAL app.current_tenant=...
  Svc->>PG: SELECT/INSERT
  PG->>PG: RLS policy applies
  PG-->>Svc: rows or error
  Svc->>Aud: write event {tenant, actor, action, cid}
  PG-->>Svc: COMMIT
  Svc-->>Cli: response`,
    alternatives: [
      { name: 'MongoDB', tradeoff: 'Flexible schema; no native RLS; weaker for relational queries' },
      { name: 'MySQL', tradeoff: 'Mature; no RLS until 8.0+ and weaker than PG\'s; less expressive policy' },
      { name: 'CockroachDB', tradeoff: 'Distributed strong consistency; fewer extensions; higher latency' },
      { name: 'DynamoDB', tradeoff: 'Auto-scale but key-value; no joins; denormalization heavy' },
    ],
    challenges: [
      'Every query MUST respect tenant context — easy to forget',
      'RLS is misunderstood without real-DB tests',
      'Privileged role misuse blurs the security boundary',
      'Migration coordination across schemas',
      'Connection pool exhaustion under load',
    ],
    edgeCases: [
      { case: 'Migration accidentally bypasses tenant assumptions', solution: 'Migrations as owner role; tested against representative seeded data' },
      { case: 'Admin/ops job needs cross-tenant access', solution: 'Use documind_ops role with audit row + explicit scope' },
      { case: 'App query fails because tenant context not set', solution: 'Middleware enforces SET LOCAL; never trust callers' },
      { case: 'Test passes with mocks but real RLS fails', solution: 'Drill against real Postgres (drill_retrieval_tenant_isolation)' },
      { case: 'Background job writes without role separation', solution: 'Worker uses dedicated role + tenant_connection() helper' },
    ],
    failureModes: [
      { mode: 'Connection pool exhaustion', detect: 'asyncpg pool wait time histogram', recover: 'Tune max_size; identify long-running queries' },
      { mode: 'RLS policy regression', detect: 'drill_retrieval_tenant_isolation goes red', recover: 'Revert migration; re-test against real DB' },
      { mode: 'Cross-tenant leak via missing app.current_tenant', detect: 'Audit anomaly + tenant scoping drill', recover: 'Quarantine, scan, fix middleware path' },
      { mode: 'Slow query → cascading timeouts', detect: 'pg_stat_statements; p95 latency alert', recover: 'EXPLAIN ANALYZE; index; query plan fix' },
    ],
    monitoring: [
      'asyncpg pool size + wait time + active connections',
      'pg_stat_statements top-N by total_time',
      'audit_log write-failure counter (documind_audit_write_failures_total)',
      'connection limits per role',
      'Replication lag (if applicable)',
    ],
    testing: [
      'Real Postgres in CI (no mocks for RLS)',
      'Integration drill: insert under tenant A, lookup under tenant B → zero rows',
      'Migration test: seed data + run migration + verify behaviour',
      'Pool-exhaustion fault injection',
      'Audit-chain hash verification (drill_audit_seal)',
    ],
    security: [
      'NOBYPASSRLS on app role (documind_app)',
      'Privileged role (documind_ops) for cross-tenant ops with audit',
      'Migration role separate from runtime role',
      'No PII in audit_log.details unless redact_pii=True (ADR-013)',
      'Hash-chained audit log per tenant',
    ],
    scaling: [
      '10x: tune connection pool; index hot queries',
      '100x: read replicas; partition large tables (audit_log by month)',
      '1000x: shard by tenant_id range; consider Citus or CockroachDB',
      'Cost driver: storage (audit retention); IOPS (hot tables)',
    ],
    maturity: {
      mvp: 'Single Postgres, schema-per-service, no RLS yet',
      production: 'RLS forced; role separation; pool tuning; pg_stat_statements + slow-query alerts',
      enterprise: 'Read replicas; partition by month; audit retention policy; cross-region replication; PITR',
    },
    limitations: [
      'RLS protects relational access, not all business correctness',
      'Single cluster can become noisy with many services',
      'DB isolation does not replace app-layer auth/policy',
      'Privileged ops still needs governance even with role separation',
    ],
    projectFit: [
      'governance.audit_log (hash-chained per tenant)',
      'governance.action_drafts (state machine with CHECK constraints)',
      'governance.prompts (status enum, A/B versions)',
      'governance.mcp_idempotency (durable idempotency keys)',
      'documind_app role NOBYPASSRLS; documind_ops role audited',
    ],
    interviewLine: 'For domain truth we use Postgres with schema-per-service and row-level security. The key design choice is role separation: the app runtime cannot bypass RLS, while privileged operational access is isolated and audited.',
  },

  // ---- 2. Qdrant ----
  {
    slug: 'qdrant',
    title: '2. Qdrant — vector DB (semantic retrieval)',
    status: 'shipped',
    coreConcept: 'Qdrant is a retrieval accelerator for embedding-based nearest-neighbor search — NOT a transactional source of truth.',
    problem: 'Keyword search misses semantic similarity. RAG quality depends on retrieving relevant chunks based on meaning, not exact match.',
    whyThisApproach: 'Qdrant gives sub-100ms ANN search at scale, supports per-tenant collections + metadata filtering, and is straightforward to self-host.',
    whenToUse: [
      'Semantic search (RAG context retrieval)',
      'Similarity-based recommendations',
      'Duplicate detection at scale',
      'Hybrid retrieval combined with keyword/graph',
    ],
    whenNotToUse: [
      'Source of truth for domain data → Postgres',
      'Exact-match keyword search → use BM25 or pg_trgm',
      'Tiny corpora (< 10K docs) — overkill',
      'Strict ACID writes',
    ],
    input: 'Document chunks + embeddings + metadata (tenant_id, doc_id, chunk_id)',
    process: [
      'Embed text via configured embedding model',
      'Insert into per-tenant collection (or filter on tenant_id)',
      'Query: embed query → ANN search top-K with metadata filter',
      'Optional rerank step',
      'Return chunks for prompt assembly',
    ],
    output: 'Top-K relevant chunks with similarity scores for grounded context.',
    flowchart: `flowchart LR
  a[Document chunks] --> b[Embed]
  b --> c[Store in Qdrant + metadata]
  d[User query] --> e[Embed query]
  e --> f[ANN search with tenant filter]
  f --> g[Top-K chunks]
  g --> h[Optional rerank]
  h --> i[Pass to inference for grounded answer]`,
    sequence: `sequenceDiagram
  autonumber
  participant Ing as ingestion-svc
  participant Emb as Embedder
  participant Q as Qdrant
  participant Ret as retrieval-svc
  participant Inf as inference-svc
  Ing->>Emb: chunks
  Emb-->>Ing: vectors
  Ing->>Q: upsert(vectors, metadata{tenant_id, doc_id})
  Inf->>Ret: query "What is the leave policy?"
  Ret->>Emb: embed query
  Ret->>Q: search(vector, filter={tenant_id})
  Q-->>Ret: top-K with scores
  Ret-->>Inf: chunks
  Inf-->>Inf: assemble prompt + generate`,
    alternatives: [
      { name: 'Weaviate', tradeoff: 'Built-in modules (multi-modal, hybrid); higher operational complexity' },
      { name: 'Milvus', tradeoff: 'Massive scale (billions); heavier to deploy' },
      { name: 'pgvector (Postgres extension)', tradeoff: 'Single-store simplicity; slower at scale; no specialized index tuning' },
      { name: 'Pinecone (managed)', tradeoff: 'Zero-ops; vendor lock-in; cost per million vectors' },
    ],
    challenges: [
      'Embedding drift — model upgrade silently changes recall',
      'Tenant filtering must be enforced on EVERY query',
      'Rebuild cost on embedding model bump',
      'Recall vs precision tuning (ef_search, threshold)',
      'Index versioning is rarely managed',
    ],
    edgeCases: [
      { case: 'Wrong embedding model version against old index', solution: 'Pin embedding_model_version + index_version; rebuild on bump' },
      { case: 'Duplicate content floods retrieval', solution: 'Dedupe by content_hash on ingest' },
      { case: 'Missing tenant filter exposes wrong data', solution: 'Per-tenant collection OR enforce filter in MCPClient wrapper' },
      { case: 'Poor chunk granularity (too small/large)', solution: 'Token-aware chunker per doc type (256-1024 tokens, 10-20% overlap)' },
      { case: 'Cold start — no relevant chunks', solution: 'Degrade-honestly path; tell user the corpus has no answer' },
    ],
    failureModes: [
      { mode: 'Qdrant unreachable', detect: '/health/upstreams kind=mcp + transport breaker open', recover: 'Transport CB; degraded retrieval; alert on duration' },
      { mode: 'Index corruption', detect: 'Anomalous recall metrics in eval-svc', recover: 'Rebuild from source documents' },
      { mode: 'Recall collapse after model bump', detect: 'eval-svc retrieval scores drop past tolerance', recover: 'Roll back embedding model; rebuild index' },
      { mode: 'Tenant filter dropped (regression)', detect: 'drill_retrieval_tenant_isolation red', recover: 'Revert; restore filter in client' },
    ],
    monitoring: [
      'p95 query latency per collection',
      'Recall@K metric from eval-svc',
      'Index size + memory growth',
      'Per-collection query rate',
      'Transport breaker state for Qdrant',
    ],
    testing: [
      'drill_retrieval_tenant_isolation — multi-tenant write + cross-tenant read returns zero',
      'drill_retrieval_transport_breaker — Qdrant down → CB opens',
      'Eval against benchmark dataset',
      'Embedding-model-version compatibility test',
    ],
    security: [
      'Per-tenant collection OR per-call tenant filter (enforced in MCPClient)',
      'No PII in chunk text without redaction',
      'API key auth on Qdrant',
      'Network isolation (private network only)',
    ],
    scaling: [
      '10x: HNSW tuning (M, ef_construction, ef_search)',
      '100x: Sharded collections; read replicas',
      '1000x: Migrate to Milvus or distributed Qdrant',
      'Cost driver: vector count × dimension × bytes (4 for f32, 1 for i8 quantized)',
    ],
    maturity: {
      mvp: 'Single collection, no tenant filter, default HNSW',
      production: 'Per-tenant collection or filter; transport CB; eval-monitored recall',
      enterprise: 'Embedding/index version registry; rebuild orchestration; A/B index comparison; cost-tracked vector storage',
    },
    limitations: [
      'Not a source of truth — chunk content lives in Postgres',
      'ANN is approximate — may miss ideal matches',
      'Weak without metadata discipline',
      'Embedding model coupling makes upgrades expensive',
    ],
    projectFit: [
      'retrieval-svc connects via QdrantClient with API key auth',
      'Per-tenant filter enforced in retrieval path',
      'Transport breaker around Qdrant (ADR-008)',
      'drill_retrieval_tenant_isolation locks tenant boundary',
      'drill_retrieval_transport_breaker locks CB behaviour',
    ],
    interviewLine: 'Vector DB is a retrieval accelerator, not a transactional source of truth. The hardest discipline is embedding/index version coupling — silent drift here destroys recall.',
  },

  // ---- 3. Redis ----
  {
    slug: 'redis',
    title: '3. Redis — cache + transient state',
    status: 'partial',
    coreConcept: 'Low-latency temporary store for hot data, throttling state, and short-lived coordination — every entry needs a correctness story (tenant key, TTL, invalidation).',
    problem: 'Repeated reads or transient coordination should not always hit the primary store; some operations need cross-process state without DB round-trips.',
    whyThisApproach: 'Redis gives microsecond reads, native data structures (hash, list, sorted set, streams), and atomic operations (Lua, MULTI/EXEC) — enough for cache, rate limiting, distributed locks, and ephemeral session state.',
    whenToUse: [
      'Hot read cache (read-through with TTL)',
      'Rate-limit counters (sliding window, token bucket)',
      'Distributed locks for short critical sections',
      'Ephemeral session/coordination state',
    ],
    whenNotToUse: [
      'Source of truth → Postgres',
      'Long-lived data without eviction policy',
      'Anything containing PII without explicit policy',
      'Operations needing strict cross-key transactions',
    ],
    input: 'Hot keys, rate-limit counters, cached lookup results, transient session state',
    process: [
      'Read-through / write-through / explicit write',
      'TTL enforced on every key',
      'Tenant-scoped key prefixes (tenant:<id>:...)',
      'Invalidation on source change',
      'Eviction policy (allkeys-lru) when memory tight',
    ],
    output: 'Lower latency, lower DB load, fast cross-process coordination state.',
    flowchart: `flowchart LR
  a[Request arrives] --> b{Cache hit?}
  b -->|yes| c[Return cached]
  b -->|no| d[Compute / fetch from source]
  d --> e[Set with TTL + tenant prefix]
  e --> f[Return]
  g[Source change event] --> h[Invalidate matching keys]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Svc as Service
  participant R as Redis
  participant DB as Postgres
  U->>Svc: GET /docs/{id}
  Svc->>R: GET tenant:T:doc:id
  R-->>Svc: nil
  Svc->>DB: SELECT * FROM docs WHERE id=...
  DB-->>Svc: row
  Svc->>R: SETEX tenant:T:doc:id 300 row
  Svc-->>U: doc
  Note over Svc,R: Next request hits cache; saves a DB round-trip`,
    alternatives: [
      { name: 'In-memory dict', tradeoff: 'Process-local; lost on restart; not shared across replicas' },
      { name: 'Memcached', tradeoff: 'Simpler; no data structures; no persistence' },
      { name: 'KeyDB', tradeoff: 'Multi-threaded Redis fork; same API; less mainstream' },
      { name: 'Hazelcast', tradeoff: 'In-memory data grid; JVM-centric; heavier' },
    ],
    challenges: [
      'Stale data — cache is wrong source of truth',
      'Invalidation is hard (one of two famous problems)',
      'Tenant key namespacing must be enforced',
      'Accidental caching of sensitive data',
      'Memory growth without eviction policy',
    ],
    edgeCases: [
      { case: 'Stale answer after document update', solution: 'Invalidate on source change; or short TTL on hot reads' },
      { case: 'Tenant A reads tenant B cache (key collision)', solution: 'Mandatory tenant prefix; CI check that helpers always inject it' },
      { case: 'No TTL → zombie values', solution: 'Wrap SET with helper that requires expiry argument' },
      { case: 'Sensitive response cached', solution: 'No-PII cache rule; explicit allowlist of cacheable response types' },
      { case: 'Eviction kills hot key', solution: 'Volatile-LRU; tune max-memory-policy' },
    ],
    failureModes: [
      { mode: 'Redis unreachable', detect: '/health/upstreams kind=cache; instrument_redis spans show errors', recover: 'Cache-aside fail-open: degrade to direct DB; circuit-breaker around the client' },
      { mode: 'Memory full → eviction storm', detect: 'evicted_keys metric spike + latency rise', recover: 'Increase memory; tune TTL; drop rarely-used patterns' },
      { mode: 'Stale cache poisoning', detect: 'Application-level inconsistency; user reports wrong data', recover: 'Targeted invalidation; in worst case FLUSHDB on the affected pattern' },
      { mode: 'Cluster failover during heavy traffic', detect: 'Connection-error rate spike', recover: 'Sentinel/cluster reconnect; client retries with backoff' },
    ],
    monitoring: [
      'Hit ratio per pattern (cache_hits / cache_misses)',
      'Memory used / max',
      'evicted_keys counter',
      'Connected clients',
      'p99 GET/SET latency',
    ],
    testing: [
      'Invalidation drill: write to source → assert cache miss on next read',
      'Tenant-key drill: write under T1, read under T2 → miss',
      'Failover drill: kill primary → client reconnects',
      'TTL expiry test',
    ],
    security: [
      'AUTH password required',
      'Network isolation',
      'No PII without explicit redaction',
      'Tenant prefix enforced via helper',
      'Audit cache flushes (operational action)',
    ],
    scaling: [
      '10x: tune max-memory-policy; pre-warm hot keys',
      '100x: Redis Cluster or sharding by tenant',
      '1000x: KeyDB / multi-threaded Redis or move hot patterns to in-memory cache + invalidation events',
      'Cost driver: memory (RAM-bound)',
    ],
    maturity: {
      mvp: 'Redis with TTL on most reads',
      production: 'Tenant key prefix enforced; eviction policy tuned; hit-ratio dashboards',
      enterprise: 'Cluster mode + Sentinel; audit-grade logging of admin commands; per-tenant memory quotas',
    },
    limitations: [
      'Cache is optimization, not truth',
      'Consistency is weaker than source store',
      'Memory-bound; cost grows with data volume',
      'Single-shard atomicity only',
    ],
    projectFit: [
      'instrument_redis OTel auto-instrumentation in inference-svc + retrieval-svc',
      'redis_url config in BaseServiceSettings',
      'RateLimitMiddleware uses Redis sliding window (libs/py/documind_core/rate_limiter.py)',
      'Cache TTL discipline still partial — see /admin/llmops scorecard',
    ],
    interviewLine: 'Redis improves latency, but every cache entry needs a correctness story: tenant keying, TTL, and invalidation. Without those, cache is a correctness bug waiting to happen.',
  },

  // ---- 4. Kafka ----
  {
    slug: 'kafka',
    title: '4. Kafka — durable event transport',
    status: 'partial',
    coreConcept: 'Kafka decouples workflows from request paths via durable, append-only event logs — at the cost of pushing complexity into idempotency, lag, and schema discipline.',
    problem: 'Some workflows shouldn\'t be synchronous: ingestion stages, audit fan-out, replay jobs, cross-service notifications. Direct HTTP couples lifetimes; events let consumers scale + replay independently.',
    whyThisApproach: 'Kafka gives durability (configurable replication), partition-ordered delivery, replay (log retention), and decoupled consumers — proven at scale.',
    whenToUse: [
      'Async workflows that survive consumer crashes',
      'Fan-out to N consumers with independent state',
      'Replay-after-bug-fix scenarios',
      'High write rate with eventual consistency tolerance',
    ],
    whenNotToUse: [
      'Sync request/response',
      'Strict ordering across partitions (only per-partition ordering)',
      'Tiny systems (operational overhead too high)',
      'Sub-millisecond latency requirements',
    ],
    input: 'Domain events (CloudEvents-shaped) + outbox row reference + correlation_id',
    process: [
      'DB write happens first (truth)',
      'Outbox row published to Kafka by relay',
      'Consumer reads with consumer group',
      'Idempotent processing (event_id dedup)',
      'Offset commit AFTER successful side effect',
      'DLQ on persistent failure',
    ],
    output: 'Decoupled async workflows + replayable history + parallel consumers.',
    flowchart: `flowchart LR
  a[Service writes DB row + outbox row] --> b[Outbox relay publishes to Kafka]
  b --> c[Topic partition]
  c --> d[Consumer reads]
  d --> e{Process side effect}
  e -->|success| f[Commit offset]
  e -->|fail| g{Retry budget left?}
  g -->|yes| d
  g -->|no| h[DLQ + alert]`,
    sequence: `sequenceDiagram
  autonumber
  participant Svc as Service
  participant DB as Postgres
  participant Out as Outbox relay
  participant K as Kafka
  participant Con as Consumer
  participant Side as Side effect target
  Svc->>DB: BEGIN; INSERT row + INSERT outbox; COMMIT
  Out->>DB: poll outbox
  Out->>K: publish event
  Out->>DB: mark outbox sent
  Con->>K: poll partition
  Con->>Side: perform side effect
  Side-->>Con: ok / fail
  Con->>K: commit offset (only on ok)`,
    alternatives: [
      { name: 'RabbitMQ', tradeoff: 'Lower volume; more flexible routing; weaker replay' },
      { name: 'NATS / NATS JetStream', tradeoff: 'Lighter; simpler; smaller ecosystem' },
      { name: 'AWS Kinesis / GCP Pub/Sub', tradeoff: 'Managed; vendor lock-in; per-message cost' },
      { name: 'PostgreSQL LISTEN/NOTIFY', tradeoff: 'No persistence; single-instance; for tiny scale' },
    ],
    challenges: [
      'Schema evolution without breaking consumers',
      'Duplicate delivery (at-least-once)',
      'Consumer lag during traffic spikes',
      'Poison messages blocking partition progress',
      'Rebalance storms when consumer group changes',
    ],
    edgeCases: [
      { case: 'Publish succeeds twice (producer retry)', solution: 'Idempotent producer + event_id dedup on consumer' },
      { case: 'Consumer crashes after side effect, before offset commit', solution: 'Idempotent side effect; consumer detects on restart' },
      { case: 'Poison message blocks partition', solution: 'DLQ after N retries; manual review + replay' },
      { case: 'Schema change breaks old consumers', solution: 'Backwards-compatible additive changes; schema registry; consumer-version-aware deploys' },
      { case: 'Partition skew under hot tenant', solution: 'Better key strategy (tenant + sub-key) or repartition' },
    ],
    failureModes: [
      { mode: 'Broker unavailable', detect: '/health/upstreams kind=kafka returns reachable=false', recover: 'Producer buffers; consumer pauses; manual broker recovery' },
      { mode: 'Consumer lag growing', detect: 'consumer_lag metric (end_offset - committed_offset)', recover: 'Scale consumer instances; investigate slow side effect' },
      { mode: 'Topic backlog spike', detect: 'topic_size metric or backpressure on producers', recover: 'Add partitions (one-way change); tune retention; throttle producers' },
      { mode: 'Rebalance storm', detect: 'Consumer instability; high reconnect rate', recover: 'Static membership; tune session.timeout.ms' },
    ],
    monitoring: [
      'Consumer lag per (topic, group, partition)',
      'Producer error rate',
      'Broker disk usage + retention horizon',
      'Rebalance count',
      'DLQ depth',
    ],
    testing: [
      'Duplicate-delivery drill (idempotent consumer)',
      'Replay-after-bug drill (offset reset, no double side effect)',
      'Poison-message drill (DLQ catches it)',
      'Schema-evolution drill (old consumer + new producer)',
      'Broker-down drill (producer + consumer behaviour)',
    ],
    security: [
      'TLS + SASL between clients and brokers',
      'Topic-level ACLs',
      'No PII in event payloads without redaction',
      'Tenant_id on every event for downstream filtering',
      'Audit event includes actor + correlation_id',
    ],
    scaling: [
      '10x: more partitions; tune fetch sizes',
      '100x: scale consumer count up to partition count',
      '1000x: dedicated brokers per topic family; tiered storage',
      'Cost driver: storage (retention × throughput × replication factor)',
    ],
    maturity: {
      mvp: 'Single broker, single-partition topics, in-process producer',
      production: 'Multi-broker cluster; outbox pattern; idempotent consumers; DLQ; schema discipline',
      enterprise: 'Schema registry; per-topic ACLs; tiered storage; cross-region replication; compliance-grade audit',
    },
    limitations: [
      'Eventual consistency by design',
      'Operational complexity is real (Zookeeper or KRaft, partitions, retention)',
      'Not all paths benefit from async — adds latency for low-volume use cases',
      'Replay assumes idempotent consumers — easy to forget',
    ],
    projectFit: [
      'document.lifecycle topic (ingestion-svc events)',
      'libs/py/documind_core/kafka_client.py — EventProducer + IdempotentConsumer',
      '/health/upstreams Kafka TCP probe (commit 0536b45)',
      'DOCUMIND_KAFKA_BOOTSTRAP_SERVERS=localhost:59092 in dev stack',
      'Outbox + DLQ patterns documented but not yet fully wired',
    ],
    interviewLine: 'Kafka solves workflow decoupling and replay, but it shifts complexity into idempotency, lag, and schema discipline. The hard parts aren\'t producing — they\'re consuming safely.',
  },

  // ---- 5. ClickHouse ----
  {
    slug: 'clickhouse',
    title: '5. ClickHouse — analytics / time-series',
    status: 'open',
    coreConcept: 'Columnar analytical store optimized for append-heavy ingest and aggregate queries across huge event sets — for observability and reporting, not transactional correctness.',
    problem: 'Postgres at OLAP scale is the wrong shape: row-oriented, ACID-bound, slow for "sum tokens for tenant T over the last 30 days." ClickHouse turns minutes into milliseconds.',
    whyThisApproach: 'Columnar storage + vectorized execution + materialized views give ~100x speedup on aggregate queries over time-series. Append-only ingest fits Kafka → ClickHouse pipelines naturally.',
    whenToUse: [
      'Token usage dashboards per tenant',
      'Latency / error rate aggregations',
      'Cost-tracking and FinOps reports',
      'Audit-log-derived analytics (eventual freshness)',
    ],
    whenNotToUse: [
      'Transactional updates → Postgres',
      'Strong consistency required',
      'High UPDATE/DELETE volume',
      'Tiny datasets (overkill)',
    ],
    input: 'Append-only events from Kafka (token usage, latency samples, audit projections)',
    process: [
      'Kafka consumer batches events',
      'Insert into MergeTree-family table',
      'Background merges optimize storage',
      'Materialized views pre-aggregate hot dimensions',
      'Query by time window + dimension filters',
    ],
    output: 'Fast aggregate queries for dashboards + reports + cost tracking.',
    flowchart: `flowchart LR
  a[Service emits event] --> b[Kafka topic]
  b --> c[Consumer batches]
  c --> d[INSERT into ClickHouse MergeTree]
  d --> e[Background merge]
  e --> f[Materialized view aggregates]
  g[Dashboard query] --> h[Group by time + dim]
  h --> i[Return aggregate]`,
    sequence: `sequenceDiagram
  autonumber
  participant Svc as Service
  participant K as Kafka
  participant Con as CH consumer
  participant CH as ClickHouse
  participant UI as Dashboard
  Svc->>K: emit usage event
  Con->>K: poll batch
  Con->>CH: INSERT INTO usage_events VALUES (...batch...)
  Note over CH: background merges + materialized views
  UI->>CH: SELECT sum(tokens) FROM mv_usage_daily WHERE tenant=T AND day>='2026-04-01'
  CH-->>UI: aggregate result (ms)`,
    alternatives: [
      { name: 'TimescaleDB (Postgres extension)', tradeoff: 'SQL familiarity; tighter PG integration; slower than columnar at scale' },
      { name: 'Druid', tradeoff: 'Lambda-architecture roots; complex ops; strong real-time' },
      { name: 'BigQuery', tradeoff: 'Managed; pay-per-query; vendor lock-in' },
      { name: 'DuckDB', tradeoff: 'In-process columnar; great for laptops; not multi-user serving' },
    ],
    challenges: [
      'Schema discipline matters more than engine speed',
      'Late-arriving events break naive aggregates',
      'Duplicate event deduplication',
      'Dashboard query cost',
      'Freshness vs cost tradeoff',
    ],
    edgeCases: [
      { case: 'Late-arriving events', solution: 'Time-window-based aggregation with late-data tolerance; ReplacingMergeTree for deduplication' },
      { case: 'Double-counted events', solution: 'Idempotent insert with event_id dedup' },
      { case: 'Dashboard query too expensive', solution: 'Materialized view pre-aggregation; sample for exploration' },
      { case: 'Schema change mid-flight', solution: 'Additive ALTER TABLE; backfill if needed' },
    ],
    failureModes: [
      { mode: 'Insert lag from Kafka', detect: 'Consumer lag spike + dashboard freshness alert', recover: 'Scale consumer; investigate insert bottleneck' },
      { mode: 'Disk full from retention misconfiguration', detect: 'Disk usage alert', recover: 'Adjust TTL on table; archive old partitions' },
      { mode: 'Slow merge causing query degradation', detect: 'parts_count metric high; query latency spike', recover: 'OPTIMIZE TABLE; investigate insert pattern' },
    ],
    monitoring: [
      'Insert rate + batch size',
      'Merge backlog (parts_count)',
      'Query p95 + p99',
      'Disk usage + projected retention horizon',
      'Materialized view refresh lag',
    ],
    testing: [
      'Idempotent-insert drill',
      'Late-arrival drill (event with timestamp T inserted at T+1h)',
      'Materialized view consistency drill',
      'Schema-evolution drill',
    ],
    security: [
      'Network isolation',
      'Per-user grants (SELECT only for read-side)',
      'No raw PII; pre-aggregate or hash',
      'Audit log of admin queries',
    ],
    scaling: [
      '10x: tune insert batch size',
      '100x: distributed table across shards; replication for read scale',
      '1000x: tiered storage (hot SSD / cold S3); pre-aggregated columns',
      'Cost driver: storage + CPU on aggregate queries',
    ],
    maturity: {
      mvp: 'Single ClickHouse, single table, raw inserts',
      production: 'MergeTree with TTL; materialized views; monitoring',
      enterprise: 'Distributed cluster + replicas; tiered storage; per-tenant quotas; compliance-grade audit',
    },
    limitations: [
      'Not OLTP — UPDATE/DELETE are expensive',
      'Eventual freshness depending on pipeline',
      'Joins are limited compared to Postgres',
      'Operational expertise required',
    ],
    projectFit: [
      'NOT YET WIRED in this repo',
      'Planned for FinOps cost tracking + observability analytics',
      'Would consume from Kafka outbox (events → ClickHouse pipeline)',
      'LLMOps scorecard row "data" lists this as open',
    ],
    interviewLine: 'ClickHouse is for observability and analytics shapes, not transactional correctness. The discipline isn\'t the engine; it\'s event quality and aggregation strategy.',
  },

  // ---- 6. Object/blob storage ----
  {
    slug: 'object-storage',
    title: '6. S3-compatible object storage (raw artifacts)',
    status: 'shipped',
    coreConcept: 'Durable, cheap, decoupled storage for large binary artifacts — keeps raw files OUT of relational tables, where they don\'t belong.',
    problem: 'Storing PDFs, images, audio, video as bytea in Postgres bloats the cluster, slows queries, and breaks backup economics. Object storage decouples bytes from metadata.',
    whyThisApproach: 'S3-compatible object stores (MinIO, AWS S3, GCS) give 11-9s durability, lifecycle policies, multipart upload for large files, and presigned URLs for direct browser access — at storage costs orders of magnitude lower than DB.',
    whenToUse: [
      'Original document uploads (PDFs, images, audio, video)',
      'Backup snapshots',
      'Logs / audit archives (cold tier)',
      'Generated artifacts (rendered reports, exported data)',
    ],
    whenNotToUse: [
      'Indexable searchable content → text in DB or vector store',
      'Hot reads with < 50ms requirement → CDN in front',
      'Tiny metadata blobs (overhead not worth it)',
      'Real-time mutating state',
    ],
    input: 'Binary file (PDF, image, audio, video) + metadata (tenant, document_id, content_type)',
    process: [
      'Client / service uploads via PUT or multipart',
      'Object stored at tenant-prefixed key',
      'Metadata pointer stored in Postgres (documents.file_path)',
      'Downstream parsers read by key',
      'Lifecycle policy archives or deletes after N days',
    ],
    output: 'Durable raw artifact + small DB row pointing to it, with decoupled lifecycle.',
    flowchart: `flowchart LR
  a[Client uploads file] --> b[ingestion-svc receives bytes]
  b --> c[PUT to S3 at tenant/<id>/raw/<doc_id>]
  c --> d[INSERT row in documents table with file_path]
  d --> e[Emit document.uploaded event]
  e --> f[Parser reads object by key]
  f --> g[Chunks + embeddings stored downstream]
  h[Lifecycle policy] --> i[Move to cold tier OR delete after N days]`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant Ing as ingestion-svc
  participant S3 as MinIO/S3
  participant PG as Postgres
  participant Parser as Parser
  Cli->>Ing: POST /api/v1/documents/upload (multipart)
  Ing->>S3: PUT tenant/T/raw/D.pdf
  S3-->>Ing: ETag
  Ing->>PG: INSERT documents (file_path, tenant, doc_id, status='uploaded')
  Ing-->>Cli: 201 + document_id
  Parser->>S3: GET tenant/T/raw/D.pdf
  S3-->>Parser: bytes
  Parser->>PG: UPDATE documents SET status='parsing'`,
    alternatives: [
      { name: 'AWS S3', tradeoff: 'Managed; pay-per-use; vendor-locked; mature ecosystem' },
      { name: 'GCS / Azure Blob', tradeoff: 'Same shape as S3; different IAM model; cloud lock-in' },
      { name: 'MinIO (self-hosted)', tradeoff: 'S3-compatible; full control; ops cost' },
      { name: 'Postgres bytea', tradeoff: 'Single store; awful for large files; backup pain' },
      { name: 'Filesystem (NFS, EFS)', tradeoff: 'Familiar; doesn\'t scale to multi-region; consistency issues' },
    ],
    challenges: [
      'Lifecycle policy correctness (don\'t delete in-flight files)',
      'Versioning vs immutability tradeoffs',
      'Metadata-pointer drift (object exists but DB row missing or vice versa)',
      'Large upload handling (multipart, retry)',
      'Cross-region replication cost',
    ],
    edgeCases: [
      { case: 'File stored but DB pointer missing (post-PUT crash)', solution: 'Two-phase: upload first, INSERT after success; recovery sweep finds orphaned objects' },
      { case: 'DB row exists but object deleted (manual ops mistake)', solution: 'Soft delete in DB; lifecycle policy never deletes referenced objects' },
      { case: 'Duplicate upload', solution: 'Hash content; dedupe at insert' },
      { case: 'Multipart upload fails mid-way', solution: 'Resume from last completed part; abandoned multiparts cleaned up by lifecycle' },
      { case: 'Tenant-key collision', solution: 'Tenant-prefixed key path enforced (tenant/<id>/...)' },
    ],
    failureModes: [
      { mode: 'S3 unreachable', detect: 'PUT failure rate; ingestion-svc /health/upstreams', recover: 'Retry with backoff; quarantine failed uploads' },
      { mode: 'Storage quota exceeded', detect: 'Bucket size alert', recover: 'Lifecycle policy archive; alert tenant if over quota' },
      { mode: 'Object deleted by ops mistake', detect: 'Audit log of admin actions; metadata-pointer health check', recover: 'Restore from versioning if enabled; otherwise re-upload' },
      { mode: 'Tenant prefix dropped (regression)', detect: 'Cross-tenant access drill', recover: 'Revert; verify all keys' },
    ],
    monitoring: [
      'Upload success rate per tenant',
      'p99 PUT/GET latency',
      'Bucket size growth',
      'Lifecycle transition events',
      'Multipart upload completion rate',
    ],
    testing: [
      'Upload-then-DB-crash drill (orphaned object cleanup)',
      'Tenant-prefix drill (cross-tenant access blocked)',
      'Lifecycle policy drill (don\'t delete in-flight objects)',
      'Large-file multipart drill',
    ],
    security: [
      'Bucket policy denies anonymous access',
      'IAM per-service credentials',
      'Tenant-prefixed key path',
      'Server-side encryption (SSE-S3 or SSE-KMS)',
      'Audit log of admin operations',
    ],
    scaling: [
      '10x: scales linearly (S3 is built for it)',
      '100x: same; tune multipart threshold',
      '1000x: cross-region replication; CDN for hot reads',
      'Cost driver: storage GB-months + GET/PUT request count + egress',
    ],
    maturity: {
      mvp: 'MinIO single-node, no lifecycle policy',
      production: 'Versioning enabled; lifecycle policy; tenant-prefixed keys; audit',
      enterprise: 'Cross-region replication; CMK encryption; per-tenant quotas; immutable bucket retention',
    },
    limitations: [
      'Not a query engine — needs metadata system around it',
      'Eventual consistency historically; strong consistency in modern S3',
      'Cost grows with retention',
      'Direct browser access requires presigned URLs (expiry management)',
    ],
    projectFit: [
      'MinIO at localhost:59000 in dev stack (DOCUMIND_MINIO_*)',
      'ingestion-svc uploads documents here',
      'documents table stores file_path pointing to MinIO key',
      'Tenant-prefixed key path enforced',
    ],
    interviewLine: 'Blob storage keeps raw artifacts cheap and durable; metadata and workflow state still live in Postgres. Mixing the two is the most common architectural mistake.',
  },
];

export default function DatabaseDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Database / datastore deep dive — 20-dimension framework</h1>
          <p className="page-subtitle">
            Six datastore roles in this project, each explained through the
            universal interview framework: core concept · problem · why ·
            when/when-not · IPO · flowchart · sequence · alternatives ·
            challenges · edge cases · failure modes · monitoring · testing
            · security · scaling · maturity · limitations · project fit ·
            interview line.
          </p>
        </div>
      </div>

      {/* TOC */}
      <div className="card">
        <strong>Datastores ({DATASTORES.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18, columnCount: 2, columnGap: 24 }}>
          {DATASTORES.map((d) => (
            <li key={d.slug}>
              <a href={`#${d.slug}`} style={{ color: '#1e3a8a' }}>
                {d.title}
              </a>
            </li>
          ))}
        </ul>
      </div>

      {/* Opener — interview framing */}
      <div className="card" style={{ backgroundColor: '#dbeafe', marginBottom: 16 }}>
        <strong>Best opener</strong>
        <p style={{ marginTop: 6, fontStyle: 'italic' }}>
          &ldquo;I group data stores by role, not by technology name. Each
          store solves a different shape of problem: transactional truth,
          fast retrieval, cache, event durability, analytics, or raw
          artifact storage.&rdquo;
        </p>
      </div>

      {DATASTORES.map((d) => (
        <UniversalDeepDive key={d.slug} t={d} />
      ))}

      {/* Final summary */}
      <div className="card" style={{ backgroundColor: '#f3f4f6' }}>
        <strong>Final senior-level summary</strong>
        <p style={{ marginTop: 8, fontStyle: 'italic' }}>
          &ldquo;In this project, we don&apos;t talk about databases as
          products first. We talk about them as roles. Postgres is for
          transactional truth and tenant-safe state. Vector storage is
          for semantic retrieval. Redis is for transient speed and
          coordination. Kafka is for async workflow durability.
          Analytical stores are for reporting and observability. Object
          storage is for raw artifacts. That separation keeps correctness,
          performance, and operational behaviour understandable.&rdquo;
        </p>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <strong>How to choose a datastore (decision logic)</strong>
        <ol style={{ marginTop: 8, paddingLeft: 20 }}>
          <li>Is this source of truth or derived/auxiliary?</li>
          <li>Do I need ACID or eventual consistency?</li>
          <li>What&apos;s the access pattern: point lookup / relational / semantic / append-heavy / ephemeral / fan-out?</li>
          <li>What&apos;s the isolation model? (per-tenant collection, RLS, key prefix, ...)</li>
          <li>What are the failure + replay requirements?</li>
          <li>What observability + audit evidence is required?</li>
        </ol>
      </div>
    </>
  );
}
