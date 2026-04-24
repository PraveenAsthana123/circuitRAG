/**
 * Tech-inventory data — drives the /tools UI.
 *
 * Each Tool has 6 tabs of content. Keep the text ≤ ~300 words per tab so
 * the UI stays readable. Scoring is a subjective 0-10 on each axis —
 * maturity (how stable), operational-load (higher = more ops pain),
 * project-benefit (bigger = more valuable for DocuMind's goals).
 */

export type Scoring = {
  maturity: number;      // 0=experimental, 10=battle-tested
  operational: number;   // 0=self-driving, 10=constant babysitting
  benefit: number;       // 0=decorative, 10=load-bearing
};

export type Tab = {
  title: string;
  body: string;          // Markdown-ish: supports **bold**, `code`, simple lists starting with "- " or "1. "
};

export type Tool = {
  slug: string;
  name: string;
  category:
    | "data-store"
    | "ai"
    | "networking"
    | "observability"
    | "service"
    | "framework"
    | "reliability";
  weblink: string;
  oneLine: string;
  scoring: Scoring;
  tabs: {
    dashboard: Tab;
    feature: Tab;
    benefitMonitoring: Tab;
    integration: Tab;
    visualization: Tab;
    interview: Tab;
  };
};

// ---------------------------------------------------------------------------

export const TOOLS: Tool[] = [
  // ---- data stores ----
  {
    slug: "postgres-rls",
    name: "PostgreSQL + RLS",
    category: "data-store",
    weblink: "https://www.postgresql.org/docs/current/ddl-rowsecurity.html",
    oneLine:
      "Relational store; Row-Level Security enforces tenant isolation at the DB, not the app.",
    scoring: { maturity: 10, operational: 4, benefit: 10 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Port 5432 (dev), StatefulSet in K8s. Schema-per-service: identity, ingestion, eval, governance, finops, observability. **Role separation** is mandatory:
- \`documind\` — owner (SUPERUSER). Runs migrations.
- \`documind_app\` — runtime connection. **Not superuser, not BYPASSRLS**.
- \`documind_ops\` — privileged jobs (BYPASSRLS), audited.

Without role separation, RLS is a no-op because superusers bypass all policies. Verified by \`libs/py/tests/test_rls_isolation.py\` against live PG.`,
      },
      feature: {
        title: "Feature",
        body: `- ACID relational store, battle-tested since 1996
- Row-Level Security (RLS) — declarative per-tenant filtering
- \`FORCE ROW LEVEL SECURITY\` ensures owner doesn't bypass
- WAL replication for hot standby
- Logical replication for multi-region
- Parameterized queries prevent SQL injection
- JSONB columns for flexible schema-on-read (e.g. chunk metadata)`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Tenant isolation is structural — a bug in app code CANNOT leak cross-tenant because the DB itself refuses. Compliance (SOC2 / HIPAA / GDPR) gets dramatically easier.

**Monitoring:**
- \`pg_stat_activity\` — active connections per user / DB
- \`pg_stat_database\` — xact_commit, xact_rollback, blks_read, blks_hit
- Replication lag via \`pg_last_wal_receive_lsn()\`
- Slow-query log (\`log_min_duration_statement = 200\`)
- In DocuMind: every query's \`tenant_id\` is set via \`set_config('app.current_tenant', ..., true)\` and flows through RLS policies.`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** SQL from \`asyncpg\` via \`libs/py/documind_core/db_client.py\`. Every tenant-scoped query goes through \`DbClient.tenant_connection(tenant_id)\` which runs \`SELECT set_config('app.current_tenant', $1, true)\` inside a transaction.

**Process:** RLS policy \`USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\` filters rows at the storage engine before they reach the app.

**Output:** Rows the caller is allowed to see. Ops connections (\`documind_ops\`) bypass for audit / billing rollups — logged separately.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
sequenceDiagram
  actor Svc as ingestion-svc pod
  participant Pool as asyncpg pool
  participant PG as PostgreSQL
  Svc->>Pool: acquire() with tenant_id=A
  Pool->>PG: BEGIN
  Pool->>PG: SET LOCAL app.current_tenant='A'
  Svc->>Pool: SELECT * FROM ingestion.documents
  Pool->>PG: forward query
  PG->>PG: RLS policy: tenant_id = 'A' applied
  PG-->>Pool: only A's rows
  Pool-->>Svc: rows
  Svc->>Pool: COMMIT / release
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"We moved tenant isolation from the application layer into PostgreSQL itself via Row-Level Security. The key detail that interviewers often miss: enabling RLS is not enough — the table owner and any SUPERUSER bypass RLS by default, regardless of the policy. You must (a) run DDL as an owner that isn't what services connect as, (b) mark the table \`FORCE ROW LEVEL SECURITY\`, and (c) the runtime connection role must NOT have BYPASSRLS. We verify this with a cross-tenant read test that runs as the non-privileged role against a live database — if tenant A ever sees tenant B's row, the test fails red and the deploy blocks."`,
      },
    },
  },

  // ---- Qdrant ----
  {
    slug: "qdrant",
    name: "Qdrant",
    category: "data-store",
    weblink: "https://qdrant.tech/documentation/",
    oneLine:
      "Vector DB for semantic search; HNSW + scalar quantization; tenant-id as a payload filter.",
    scoring: { maturity: 8, operational: 5, benefit: 9 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Ports 6333 (REST) / 6334 (gRPC). One shared collection \`chunks\` across tenants — tenant isolation via payload filter on every query. HNSW graph with m=16, ef_construct=128. INT8 scalar quantization for 4× memory reduction.`,
      },
      feature: {
        title: "Feature",
        body: `- Approximate-nearest-neighbor search at p95 ~50ms for 10M vectors
- Hybrid search (dense + sparse + metadata filters)
- Tenant isolation via \`must: [{key: "tenant_id", match: ...}]\`
- Built-in snapshot/restore for DR
- Distributed cluster mode (3+ nodes)
- REST + gRPC APIs; Python async client`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Without a vector DB, RAG falls back to keyword search — shallow + miss-prone. Qdrant gives us semantic similarity in sub-100ms at scale.

**Monitoring:**
- Prometheus exporter: points_count, segments, collection size
- Custom metric \`documind_retrieval_quality\` tracks rolling avg top-score
- \`RetrievalCircuitBreaker\` opens when quality drops → alert fires
- Snapshots uploaded to MinIO nightly (DR)`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** \`QdrantRepo.upsert_chunks(tenant_id, document_id, chunk_ids, vectors, payloads)\` from the ingestion saga's index step.

**Process:** Vectors stored with payload \`{tenant_id, document_id, page, text, chunk_id}\`. Every search from retrieval-svc includes a \`must\` filter on tenant_id — structurally impossible to leak across tenants at query time.

**Output:** Scored hits returned by \`VectorSearcher.search\`, normalized into the common \`RetrievedChunk\` schema for RRF fusion with graph results.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph LR
  A[user query] --> B[embed]
  B -->|768-d vector| C[Qdrant]
  T["tenant_id filter<br/>{must: [{key:'tenant_id'}]}"] --> C
  C -->|top-K + scores| D[RRF fusion]
  D --> E[reranker]
  E --> F[LLM context]
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"We chose Qdrant over pgvector and Weaviate primarily because of its hybrid-search payload-filter ergonomics — the \`must: [{key:'tenant_id'}]\` idiom makes tenant isolation structural at the index, not app-enforced. Scalar INT8 quantization cuts memory 4× with ~1% recall loss, which for a multi-tenant RAG system is an excellent trade. For very large tenants we shard them into dedicated collections; decision lives in governance, not code, because the \`VectorSearcher\` interface is unchanged."`,
      },
    },
  },

  // ---- Neo4j ----
  {
    slug: "neo4j",
    name: "Neo4j",
    category: "data-store",
    weblink: "https://neo4j.com/docs/cypher-manual/current/",
    oneLine:
      "Graph DB for multi-hop reasoning: Document → Chunk → Entity → Entity relationships.",
    scoring: { maturity: 9, operational: 6, benefit: 7 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Ports 7474 (HTTP browser) / 7687 (Bolt). Single instance for dev; enterprise cluster for production. Schema: (:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(:Entity). Unique constraints on \`(tenant_id, id)\` per label.`,
      },
      feature: {
        title: "Feature",
        body: `- Multi-hop Cypher queries: "all clauses related to indemnification in contracts from vendor X"
- Property-based tenant filter on every node
- APOC extensions for text + graph algorithms
- ACID transactions
- Causal-consistency read-your-writes`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Vector search alone is shallow — it finds *similar* chunks, not *related* ones. A graph lets us traverse relationships: "find all chunks mentioning entities mentioned in chunks matching my query."

**Monitoring:**
- Metrics endpoint: page-cache hit rate, tx commit rate
- Graph staleness: \`MATCH (c:Chunk) WHERE c.updated_at < now() - duration('P7D')\` → count stale
- Orphan nodes: periodic cleanup job`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** \`Neo4jRepo.upsert_chunks\` + \`link_entities\` from ingestion saga's graph step. Entity extraction is stubbed (naive regex); production wires a proper NER (spaCy / LLM).

**Process:** Query-time, \`GraphSearcher\` extracts entities from the query, traverses \`(:Entity)-[:MENTIONED_IN]-(:Chunk)\`, ranks by mention count.

**Output:** Normalized \`RetrievedChunk[]\` fused with vector results via RRF.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph LR
  D[(:Document)] -->|HAS_CHUNK| C[(:Chunk)]
  C -->|MENTIONS| E[(:Entity)]
  E -->|RELATED_TO| E2[(:Entity)]
  E2 -->|MENTIONED_IN| C2[(:Chunk)]
  C2 -->|PART_OF| D2[(:Document)]
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"Vector alone answers 'similar chunks'; graph answers 'related chunks via explicit relationships' — multi-hop reasoning. We fuse the two with Reciprocal Rank Fusion. The ontology is minimal (Document/Chunk/Entity/Concept) because a richer ontology is domain-specific and slows operational agility. Entity extraction quality is the critical quality lever — a naive regex NER caps retrieval precision; wiring a proper NER (spaCy or an LLM) is the single most impactful improvement."`,
      },
    },
  },

  // ---- Redis ----
  {
    slug: "redis",
    name: "Redis",
    category: "data-store",
    weblink: "https://redis.io/docs/latest/",
    oneLine:
      "Cache + rate-limit counters + session + idempotency store. Tenant-namespaced keys everywhere.",
    scoring: { maturity: 10, operational: 3, benefit: 9 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Port 6379. Dev: single pod with AOF persistence + 512MB memory cap + allkeys-lru. Prod: Redis Sentinel or Cluster. Every key prefixed \`tenant:{id}:...\` so cross-tenant hits are structurally impossible.`,
      },
      feature: {
        title: "Feature",
        body: `- Sub-millisecond reads
- Sorted sets → sliding-window rate limit
- Pub/Sub for cache invalidation events
- Pipelining for batch ops (used in rate limiter)
- \`SET NX\` for stampede-prevention locks
- \`SCAN\` for bulk invalidation by prefix`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Without cache, every query hits Qdrant + Neo4j + LLM. With cache at 30% hit rate, you cut cost and latency proportionally.

**Monitoring:**
- Cache hit-rate metric (target > 0.3 in production)
- \`redis-cli INFO memory\` — used_memory, evicted_keys, keyspace
- Per-tenant key counts (namespacing makes this trivial)
- \`ObservabilityCircuitBreaker\` protects app from Redis outages`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** \`Cache.get_or_load(key, loader, ttl)\` — cache-aside with Redis-backed stampede lock.

**Process:** Hit returns immediately. Miss: acquire \`SET NX lock:{key}\`, double-check cache, call loader, store with TTL, release lock. Other callers block briefly on the lock.

**Output:** Cached JSON (queries, embeddings, configs, sessions, rate-limit counters).`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
sequenceDiagram
  actor U as User
  participant R as retrieval-svc
  participant C as Redis
  participant Q as Qdrant+Neo4j
  U->>R: query
  R->>C: GET tenant:X:retr:{hash}
  alt cache hit
    C-->>R: chunks
    R-->>U: chunks (fast)
  else cache miss
    R->>C: SET NX lock:key
    R->>Q: parallel fetch
    Q-->>R: chunks
    R->>C: SETEX tenant:X:retr:{hash} 300
    R->>C: DEL lock:key
    R-->>U: chunks (slow)
  end
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"Redis is four products in one for us: cache, rate-limit store, session store, idempotency-key store. Every key is tenant-namespaced — \`tenant:{id}:retr:{query-hash}\` — so cross-tenant hits are structurally impossible even if application code has a bug. The single non-obvious design choice is the sliding-window rate limiter using sorted sets: \`ZADD\` the timestamp, \`ZREMRANGEBYSCORE\` older than window, \`ZCARD\` to count. Unlike fixed-window, it doesn't allow boundary-bursting 2× the limit."`,
      },
    },
  },

  // ---- Kafka ----
  {
    slug: "kafka",
    name: "Kafka",
    category: "data-store",
    weblink: "https://kafka.apache.org/documentation/",
    oneLine:
      "Event backbone with CloudEvents envelope; outbox pattern guarantees atomic domain+event commit.",
    scoring: { maturity: 10, operational: 7, benefit: 8 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Port 9092 (internal) + 9094 (external). Topics per domain: document.lifecycle, query.lifecycle, cost.events, policy.changes, audit.events. Partitions: 6 for document events (key=document_id), 12 for query events (key=tenant_id). Retention 7d, 30d for audit.`,
      },
      feature: {
        title: "Feature",
        body: `- At-least-once delivery with \`acks=all\` + \`enable_idempotence=true\`
- Per-partition ordering (key-based)
- Dead-letter queue (\`*.dlq\` topic per main topic)
- Log compaction for \`policy.changes\`
- CloudEvents 1.0 envelope for every event
- Consumer groups for horizontal scale`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Decouples producer from consumer. New consumers (eval sampler, FinOps, cache invalidator) added without touching producers. Replay for debugging and backfills.

**Monitoring:**
- Consumer lag per group (alert > 1000)
- Broker JMX metrics: BytesInPerSec, BytesOutPerSec
- DLQ depth (alert > 0)
- Our outbox drain worker watches \`ingestion.outbox\` for rows older than 1m — alerts if growing`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** \`OutboxRepo.enqueue(conn, ...)\` from within the saga's transaction. The outbox row commits atomically with the domain write.

**Process:** \`OutboxDrainWorker\` reads \`FOR UPDATE SKIP LOCKED\`, publishes via \`EventProducer\`, marks \`published_at\`. Retries with attempts counter.

**Output:** Events consumed by: cache invalidator (retrieval-svc), cost tracker (finops), eval sampler (evaluation-svc), audit writer (governance).`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph LR
  S[saga step] -->|INSERT row<br/>same txn| O[(ingestion.outbox)]
  S -->|COMMIT| PG[(Postgres)]
  W[OutboxDrainWorker] -->|SELECT FOR UPDATE<br/>SKIP LOCKED| O
  W -->|publish| K[Kafka]
  K -->|consume| C1[retrieval cache<br/>invalidator]
  K -->|consume| C2[FinOps]
  K -->|consume| C3[eval sampler]
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"Kafka on its own doesn't guarantee 'domain write and event publish are atomic' — if your service commits to Postgres then crashes before publishing, the event is lost. The outbox pattern closes that hole: you INSERT into an \`outbox\` table in the SAME transaction as your domain write, and a separate worker drains the outbox to Kafka. We use \`SELECT FOR UPDATE SKIP LOCKED\` so multiple drain workers coexist. The event eventually lands in Kafka; consumers dedup by event id for idempotency. At-most-once-ish via DB + at-least-once via Kafka = effectively exactly-once at the business level."`,
      },
    },
  },

  // ---- Ollama / vLLM ----
  {
    slug: "ollama-vllm",
    name: "Ollama / vLLM",
    category: "ai",
    weblink: "https://github.com/vllm-project/vllm",
    oneLine:
      "LLM + embedding server; OpenAI-compatible API. Ollama for dev, vLLM for GPU prod.",
    scoring: { maturity: 7, operational: 6, benefit: 10 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Port 11434 for both (they're wire-compatible on the OpenAI paths). Dev: Ollama CPU, llama3.1:8b + nomic-embed-text. Prod GPU: vLLM (5–20× throughput via PagedAttention + continuous batching). docker-compose.gpu.yml swaps the container; zero code change.`,
      },
      feature: {
        title: "Feature",
        body: `- OpenAI-compatible \`/v1/chat/completions\` + \`/api/chat\`
- Streaming token output
- Embedding API on the same server
- Multiple models loaded simultaneously
- vLLM: PagedAttention, tensor-parallel for multi-GPU
- Ollama: zero-config model pulls`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** The whole product. Without an LLM, we have a search engine. With one, we have RAG.

**Monitoring:**
- Request latency histogram (p50, p95, p99)
- Token throughput
- GPU utilization + VRAM
- Ollama-level circuit breaker: 5 consecutive failures → OPEN for 60s
- Cognitive CB guards the STREAM: degenerate loops, missing citations → interrupt
- Token CB guards the BUDGET: pre-flight rejection if tenant is over quota`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** \`OllamaClient.generate(system, user, ...)\` or \`.stream(...)\` from \`RagInferenceService.ask\`.

**Process:** Wrapped in a \`CircuitBreaker\` for failure isolation + a \`CognitiveCircuitBreaker\` for intrinsic output quality (repetition, missing citations, PII, forbidden patterns). Token usage reported to FinOps via Kafka.

**Output:** Generated text → guardrails (post-hoc) → citations + confidence → AskResponse.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
sequenceDiagram
  participant I as inference-svc
  participant T as TokenCB
  participant R as retrieval-svc
  participant CB as CircuitBreaker
  participant O as Ollama/vLLM
  participant CCB as CognitiveCB
  I->>T: check_or_raise(tokens)
  I->>R: retrieve
  R-->>I: chunks
  I->>CB: call_async(stream)
  CB->>O: POST /api/chat (stream=true)
  loop token delta
    O-->>CB: token
    CB-->>I: token
    I->>CCB: on_tokens(delta)
    alt CCB says BLOCK
      CCB--xI: CognitiveInterrupt
    end
  end
  I-->>User: answer + citations
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"We abstract the LLM behind an OpenAI-compatible interface so swapping Ollama for vLLM (or a cloud API) is a config change, not a rewrite. The non-obvious detail: production-grade RAG needs THREE circuit-breakers around the LLM — the generic one for network failure, a token budget breaker for pre-flight cost control, and a Cognitive Circuit Breaker that runs DURING generation and interrupts the stream if it detects hallucination signals. The CCB is the single highest-leverage addition; it catches hallucinations before the user sees them."`,
      },
    },
  },

  // ---- Istio ----
  {
    slug: "istio",
    name: "Istio (service mesh)",
    category: "networking",
    weblink: "https://istio.io/latest/docs/",
    oneLine:
      "mTLS + AuthorizationPolicy + traffic shifting + canary rollouts + outlier detection.",
    scoring: { maturity: 8, operational: 8, benefit: 8 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `PeerAuthentication: STRICT mTLS namespace-wide. AuthorizationPolicy per service with least-privilege callers (e.g. retrieval-svc is ONLY callable from inference-svc + evaluation-svc). VirtualService: canary 90/10 for inference-svc. DestinationRule: outlier-detection (mesh-level circuit breaker).`,
      },
      feature: {
        title: "Feature",
        body: `- Automatic mTLS between pods (Envoy sidecars)
- AuthorizationPolicy — least-privilege L7 access control
- Traffic shifting: canary / blue-green / shadow
- Outlier detection (eject 5×5xx pods for 60s)
- Retries with backoff
- Fault injection for chaos testing`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Zero-trust between pods without app code changes. Canary releases without blue-green infra. Mesh-level circuit breaker as the second layer beyond app-level.

**Monitoring:**
- Kiali: live service graph from Prometheus + Jaeger
- Istio metrics: request_count, request_duration, response_size
- mTLS status per edge
- DestinationRule outlier stats (ejected pods, recoveries)`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** YAML manifests under \`infra/istio/\` applied via \`kubectl apply\` (after \`istioctl install\`).

**Process:** Envoy sidecar injected into every pod in the labeled namespace. Intercepts all traffic; applies policies; emits telemetry.

**Output:** mTLS-encrypted service-to-service traffic + Prometheus metrics + Jaeger spans + Kiali graph.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph TB
  subgraph IngressGW[Istio Ingress Gateway]
    G[nginx] --> E[Envoy]
  end
  E -->|mTLS| AG[api-gateway + sidecar]
  AG -->|mTLS authz-policy| INF[inference-svc + sidecar]
  AG -->|mTLS authz-policy| ING[ingestion-svc + sidecar]
  INF -->|mTLS authz-policy| RET[retrieval-svc + sidecar]
  style AG stroke:#4f46e5
  style INF stroke:#4f46e5
  style ING stroke:#4f46e5
  style RET stroke:#4f46e5
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"Istio gives us three things we'd otherwise build: mesh-wide mTLS (no per-service cert rotation), declarative authorization at the network layer (retrieval-svc can't be called from outside its authorized callers — defense in depth over our JWT in the gateway), and traffic shifting for canary releases. The operational cost is real — Envoy sidecars are a load, and debugging mesh issues needs Kiali/Jaeger fluency. For a DocuMind-sized stack, it's worth it; for a 3-service startup, it's over-kill."`,
      },
    },
  },

  // ---- API gateway ----
  {
    slug: "api-gateway",
    name: "API Gateway (Go)",
    category: "service",
    weblink: "https://github.com/go-chi/chi",
    oneLine:
      "Edge: RS256 JWT, Redis sliding-window rate limit, body cap, correlation ID.",
    scoring: { maturity: 6, operational: 4, benefit: 9 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Port 8080. Behind nginx (TLS + L4 rate limit). Stack: Go + chi + \`golang-jwt/jwt/v5\` + \`redis/go-redis/v9\`. Graceful shutdown on SIGTERM with 30s drain.`,
      },
      feature: {
        title: "Feature",
        body: `- CorrelationIdMiddleware — X-Correlation-ID on every request
- SecurityHeadersMiddleware — CSP, HSTS, X-Frame-Options
- BodyLimit — 1MB default, 50MB on upload routes
- JWTAuth — RS256 verify with deny-list (Redis-backed)
- RequireRole — RBAC gate on admin routes
- RateLimit — sliding window, per-tenant or per-IP
- Reverse proxy to Python services`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Single chokepoint for authN/authZ/ratelimit. Services downstream trust the signed \`X-Tenant-ID\` header because Istio AuthorizationPolicy restricts access to the gateway SA.

**Monitoring:**
- Prometheus counters: requests_total, request_duration_seconds
- Rate-limit headers on every response: X-RateLimit-Limit/Remaining/Reset
- CorrelationID in every log line — one ID traces request across services
- \`X-RateLimit-Error: redis_unavailable\` header signals fallback mode`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** HTTPS from nginx → HTTP to gateway pod.

**Process:** Middleware chain: CorrelationID → SecurityHeaders → Logger → CORS → BodyLimit → JWTAuth → RateLimit → (RequireRole on admin) → reverse proxy.

**Output:** Authenticated request forwarded to the appropriate internal service with signed headers (X-Tenant-ID, X-User-ID, X-User-Roles, X-Correlation-ID).`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph LR
  Browser --> nginx[nginx TLS+edge RL]
  nginx --> GW[api-gateway]
  subgraph Middleware chain
    M1[CorrelationID] --> M2[SecurityHeaders] --> M3[CORS] --> M4[BodyLimit] --> M5[JWTAuth] --> M6[RateLimit]
  end
  GW --> M1
  M6 --> R{route}
  R -->|/api/v1/documents| ING[ingestion-svc]
  R -->|/api/v1/ask| INF[inference-svc]
  R -->|/api/v1/retrieve| RET[retrieval-svc]
  R -->|/api/v1/admin/*| GOV[governance-svc + role check]
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"We chose Go at the edge for three reasons: goroutine concurrency makes JWT verification + rate-limit CPU-cheap per request, static binaries are trivial to deploy, and the \`chi\` router is minimal. The gateway is the ONLY place JWTs are verified. Downstream services trust signed headers because Istio's AuthorizationPolicy restricts their traffic to the gateway's service account — that's why the mesh and the gateway are a pair, not alternatives."`,
      },
    },
  },

  // ---- nginx / CDN ----
  {
    slug: "nginx-cdn",
    name: "NGINX (edge + CDN)",
    category: "networking",
    weblink: "https://nginx.org/en/docs/",
    oneLine: "TLS termination, static-asset caching (CDN-edge), L4 rate-limit, upstream LB.",
    scoring: { maturity: 10, operational: 3, benefit: 8 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Ports 80 + 443. Behind a real CDN in production (CloudFront / Cloudflare). Upstream: \`api-gateway:8080\` (scale via \`server\` lines). Cache path for \`_next/static/*\` with 7-day TTL.`,
      },
      feature: {
        title: "Feature",
        body: `- TLS 1.2/1.3 with HSTS
- HTTP → HTTPS redirect
- Static-asset proxy cache (CDN-edge behavior)
- Sliding-window rate limit (per-IP)
- Upstream LB with \`least_conn\` + keepalive
- Gzip compression
- Header security defaults`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Unbundles L4 concerns (TLS, DDoS shield, static cache) from the app. 1000× throughput on cached assets vs hitting Next.js directly.

**Monitoring:**
- JSON access logs with request_time, upstream_response_time, X-Correlation-ID
- \`nginx -T\` to dump config
- \`stub_status\` module for live connection stats
- Cache hit rate via X-Cache-Status header (HIT / MISS / BYPASS)`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** Browser requests to \`https://documind.local\`. In prod: via CDN.

**Process:** TLS terminated, static paths served from \`/var/cache/nginx\`, API paths proxied to the Go gateway. Upload endpoints stream (no request buffering).

**Output:** Either cached static bytes (fast) or proxied API response with standard security headers added.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph LR
  U[user] --> C[CDN - prod]
  C --> N[nginx edge]
  N -->|_next/static/*| Cache[(disk cache)]
  N -->|/api/*| GW[api-gateway]
  N -->|/upload rate-limited| GW
  Cache -->|7d TTL hits| U
  GW --> U
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"Most teams skip nginx in the K8s era because Istio handles traffic. The mistake: Istio terminates mTLS between pods, but you still need TLS termination from the Internet + static-asset caching + DDoS defense. nginx (or CloudFront / Cloudflare) fills that. The split we use: nginx does L4/L7 edge concerns, Istio does service-mesh concerns. They don't overlap — they compose."`,
      },
    },
  },

  // ---- Circuit breakers (5 types) ----
  {
    slug: "circuit-breakers",
    name: "Circuit Breakers (×5)",
    category: "reliability",
    weblink: "https://martinfowler.com/bliki/CircuitBreaker.html",
    oneLine:
      "5 specialized: base + Retrieval (quality) + Token (budget) + Agent-Loop + Observability (inverted) + Cognitive (intrinsic).",
    scoring: { maturity: 8, operational: 3, benefit: 10 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Base class: CLOSED/HALF_OPEN/OPEN state machine. 5 specialized variants for different failure modes. Prometheus metrics on every breaker: \`documind_circuit_breaker_state\`, \`_failures_total\`, \`_opens_total\`, \`_rejections_total\`.`,
      },
      feature: {
        title: "Feature",
        body: `- **Base** — protects against per-request failures (any external call)
- **RetrievalCB** — quality-aware: opens when rolling avg top_score drops
- **TokenCB** — pre-flight budget check (no retrieval if over budget)
- **AgentLoopCB** — per-agent-run: max_steps, timeout, loop detection, tool budget
- **ObservabilityCB** — INVERTED: when open, export is SKIPPED (never blocks)
- **Cognitive (CCB)** — intrinsic: runs DURING generation, interrupts on repetition / missing citations / PII`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Cascading failure is the #1 cause of compound outages. 5 specialized breakers cover 5 distinct failure modes the base one misses.

**Monitoring:**
- Grafana: circuit state per name (colored heatmap)
- Alert rule: any breaker OPEN for >3min = SEV2
- CCB interrupt rate per signal: alert when >0.2/s
- Agent-loop stops by reason (loop / timeout / tool-budget)`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** Call wrapped in \`cb.call_async(fn)\`.

**Process:**
1. If OPEN and cooldown not elapsed → raise \`CircuitOpenError\` fast (no network).
2. If OPEN and cooldown elapsed → HALF_OPEN; single probe.
3. On success → CLOSED.
4. On failure → count up; threshold → OPEN.

**Output:** Either the real result, or \`CircuitOpenError\` / \`CognitiveInterrupt\` / \`PolicyViolationError\` depending on breaker type.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
stateDiagram-v2
  [*] --> CLOSED
  CLOSED --> OPEN: N consecutive failures
  OPEN --> HALF_OPEN: recovery_timeout elapsed
  HALF_OPEN --> CLOSED: probe succeeds
  HALF_OPEN --> OPEN: probe fails
  note right of OPEN
    fast-fail w/ CircuitOpenError
    NO network round-trip
  end note
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"Most teams ship ONE circuit breaker and think they're done. We ship five because each guards a different failure mode: the base one guards *network*, but the retrieval one guards *quality degradation* (retrieval SUCCEEDS but returns garbage — the base CB can't see that). The Cognitive CB is the newest and highest-leverage: it runs DURING LLM streaming and interrupts on repetition, missing citations, or PII — catching hallucinations before the user sees them. The observability CB has INVERTED polarity — when OPEN, telemetry is SKIPPED, not retried, because observability must never take the app down."`,
      },
    },
  },

  // ---- Cognitive CB (expanded) ----
  {
    slug: "ccb",
    name: "Cognitive Circuit Breaker",
    category: "reliability",
    weblink: "https://arxiv.org/abs/2604.13417",
    oneLine:
      "Intrinsic reliability during LLM streaming: aborts on repetition / missing citation / PII / low confidence.",
    scoring: { maturity: 6, operational: 4, benefit: 9 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Per-request instance. Runs \`on_tokens(delta)\` every ~32 tokens during LLM streaming. Signals: RepetitionSignal, CitationDeadlineSignal, ForbiddenPatternSignal, LogprobConfidenceSignal. Metric: \`documind_ccb_interrupts_total{signal=...}\`.`,
      },
      feature: {
        title: "Feature",
        body: `- Mid-stream evaluation (no wait for full response)
- Pluggable \`CognitiveSignal\` interface
- Decision vocabulary: CONTINUE / WARN / BLOCK
- Accumulated-warning escalation (N warnings → BLOCK)
- Raises \`CognitiveInterrupt\` with reasons + partial output
- Caller swaps partial for safe fallback`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Post-hoc guardrails catch bad answers AFTER the user has seen them. CCB catches them DURING generation — user sees only the safe fallback. Latency win (abort early) + cost win (don't finish bad generation).

**Monitoring:**
- Interrupt rate by signal (which guard fired)
- Warning rate (escalating signals)
- Partial-output length at interrupt (correlates with severity)
- Calibrate per tenant: eval-svc replays against held-out set`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** \`CognitiveCircuitBreaker(signals=[...], check_every_tokens=32)\`.

**Process:** Within the LLM streaming loop, \`ccb.on_tokens(delta)\` is called for every delta. If any signal returns BLOCK → raises \`CognitiveInterrupt(reasons, partial)\`. Caller catches, swaps partial for safe fallback.

**Output:** Either the real generated answer, or a templated safe fallback: "I don't have enough confidence in the answer I was generating. Please rephrase."`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
sequenceDiagram
  participant I as inference-svc
  participant CCB as Cognitive CB
  participant Sig as Signals[]
  participant O as Ollama
  I->>CCB: start()
  I->>O: stream chat
  loop token delta
    O-->>I: "The"
    I->>CCB: on_tokens("The")
    CCB->>Sig: evaluate each
    Sig-->>CCB: CONTINUE
  end
  loop more tokens
    O-->>I: "...api_key..."
    I->>CCB: on_tokens(partial)
    CCB->>Sig: ForbiddenPattern
    Sig-->>CCB: BLOCK
    CCB--xI: CognitiveInterrupt
  end
  I-->>User: safe fallback
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"The traditional guardrail runs AFTER the LLM finishes — if it's bad, too bad, you paid for the tokens and the user saw the stream. The Cognitive Circuit Breaker runs DURING streaming with cheap signals: repetition detection, citation-by-token-N deadline, regex deny-lists, logprob confidence. When any signal hits BLOCK, we raise a typed interrupt and swap in a safe fallback. It's not a replacement for post-hoc guardrails — it's a complementary layer. The highest-leverage addition to RAG in the last year; directly inspired by arXiv 2604.13417."`,
      },
    },
  },

  // ---- ELK ----
  {
    slug: "elk",
    name: "ELK Stack",
    category: "observability",
    weblink: "https://www.elastic.co/guide/index.html",
    oneLine: "Elasticsearch + Filebeat + Kibana. JSON stdout → Filebeat → ES index `documind-*`.",
    scoring: { maturity: 10, operational: 7, benefit: 8 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Ports 9200 (ES) + 5601 (Kibana). Filebeat autodiscovers docker containers, parses JSON (keys_under_root: true). Index pattern \`documind-*\`. Every document has correlation_id + tenant_id + trace_id + service_name searchable.`,
      },
      feature: {
        title: "Feature",
        body: `- Lucene full-text + structured-field queries
- Kibana visualizations + saved searches
- Filebeat zero-config ingest via docker autodiscover
- 30-day retention by default; ILM for long-term
- Alerting (Kibana) on query thresholds`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Metrics tell you SOMETHING is wrong; logs tell you WHAT. Structured JSON logs with correlation IDs mean "user reports bug" → "paste CID" → "Kibana query" → "root cause in 2 minutes."

**Monitoring:**
- ES cluster health (yellow/green/red)
- Indexing rate
- Search latency p95
- Log volume spike alerts (often signal an error cascade)`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** Every Python service logs JSON to stdout via \`structlog\` configured in \`libs/py/documind_core/logging_config.py\`. Every line has \`correlation_id\`, \`tenant_id\`, \`trace_id\`, \`span_id\`, \`service_name\`.

**Process:** Filebeat tails docker logs, parses JSON keys as top-level fields, ships to ES.

**Output:** Kibana Discover: filter by \`correlation_id: "abc-123"\` → all logs for one request across all services.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph LR
  S1[ingestion-svc stdout] --> F[Filebeat]
  S2[retrieval-svc stdout] --> F
  S3[inference-svc stdout] --> F
  S4[api-gateway stdout] --> F
  F -->|JSON parsed| ES[(Elasticsearch)]
  ES --> K[Kibana]
  O[on-call] --> K
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"Logs without correlation IDs are just noise. Every DocuMind service uses structlog with a correlation ID bound to a ContextVar at the middleware layer — every log line inherits it automatically, no handler-level work. A single CID traces a request through gateway → inference → retrieval → Qdrant → back. ELK is heavy ops-wise; Loki is a cheaper alternative if you're mostly grepping by structured fields. Splunk is the commercial equivalent. For OSS + long retention + complex queries, ELK is still the default."`,
      },
    },
  },

  // ---- Prometheus + Grafana + Jaeger ----
  {
    slug: "otel-stack",
    name: "OpenTelemetry + Prom/Grafana/Jaeger",
    category: "observability",
    weblink: "https://opentelemetry.io/docs/",
    oneLine: "Unified metrics + traces + logs. OTel collector fans out to Prom, Jaeger, Loki.",
    scoring: { maturity: 8, operational: 6, benefit: 9 },
    tabs: {
      dashboard: {
        title: "Dashboard",
        body: `Ports 4317 (OTLP gRPC), 4318 (OTLP HTTP), 9090 (Prom), 3001 (Grafana), 16686 (Jaeger). Every service auto-instruments via \`opentelemetry.instrumentation.fastapi\` + asyncpg + httpx + redis.`,
      },
      feature: {
        title: "Feature",
        body: `- Vendor-neutral (OTel spec)
- Auto-instrumentation for FastAPI / asyncpg / httpx / redis
- Trace propagation across async boundaries
- Prometheus for metrics, Jaeger for traces
- Grafana for dashboards
- ObservabilityCircuitBreaker protects app from collector outages`,
      },
      benefitMonitoring: {
        title: "Benefit + Monitoring",
        body: `**Benefit:** Three pillars of observability without per-service plumbing. CID-linked logs + trace_id + span_id means every observation is cross-referenceable.

**Monitoring:**
- OTel collector queue depth
- Prom scrape duration
- Jaeger query latency
- Grafana dashboard uptime
- Our own ObservabilityCircuitBreaker metric: skipped exports / min`,
      },
      integration: {
        title: "Integration",
        body: `**Input:** \`setup_observability(service_name, otlp_endpoint, ...)\` at service startup.

**Process:** OTel SDK creates a TracerProvider + MeterProvider. Exporters push OTLP to the collector. Collector fans out to Jaeger (traces) + Prometheus (metrics via scrape).

**Output:** Unified dashboards in Grafana; trace timelines in Jaeger; log search in Kibana all keyed on the same correlation_id.`,
      },
      visualization: {
        title: "Diagram",
        body: `\`\`\`mermaid
graph LR
  S1[svc A] -->|OTLP| OC[OTel Collector]
  S2[svc B] -->|OTLP| OC
  OC -->|traces| J[Jaeger]
  OC -->|metrics| P[Prometheus]
  OC -->|logs| L[Loki/ES]
  P --> G[Grafana]
  J --> G
  L --> G
\`\`\``,
      },
      interview: {
        title: "Interview",
        body: `"OpenTelemetry is the standard — vendor-neutral, auto-instrumented, single SDK for traces + metrics + logs. The critical detail most teams skip: the OBSERVABILITY CIRCUIT BREAKER. If your OTel collector is down and your span exporter retries with a 10s timeout, every request hangs 10s waiting on telemetry. A dead collector brings down the app. We wrap exporters in an inverted-polarity breaker that SKIPS export silently when the backend is unhealthy — telemetry is best-effort; user requests are not."`,
      },
    },
  },
];

export function getToolBySlug(slug: string): Tool | undefined {
  return TOOLS.find((t) => t.slug === slug);
}
