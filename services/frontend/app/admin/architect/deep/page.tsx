'use client';

/**
 * Architect lens: system-level decisions, boundaries, and ADRs for
 * a multi-tenant RAG platform. This page applies the master 36-section
 * interview framework with emphasis on §4 HLD, §5 Architecture
 * relevance, §32 Trade-offs, §33 Decision matrix.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'multi-tenant-rag-architecture',
    title: '1. Multi-tenant RAG architecture (architect lens)',
    status: 'shipped',
    coreConcept: 'A RAG platform serving N tenants needs ACID truth (Postgres + RLS), semantic retrieval (Qdrant), graph reasoning (Neo4j), and a hot path that fails-fast on backend trouble — all stitched by a service mesh that enforces mTLS + circuit breakers per transport.',
    oneLiner: 'Multi-tenant RAG = ACID + ANN + graph + cache + breakers, with tenant isolation as a database invariant.',
    businessContext: 'We need to design a SaaS RAG platform where one tenant cannot read or generate against another tenant\'s corpus, AND the platform survives per-backend outages without cascading failures.',
    fiveW: {
      what: 'A composed retrieval-and-generation system: ingestion saga writes to Postgres + Qdrant + Neo4j; retrieval service queries all three behind transport breakers; inference service grounds the LLM on returned chunks.',
      why: 'Single-store retrieval (vector-only OR keyword-only) misses recall; single-tenant systems don\'t scale economically; lack of breakers means one slow backend takes the whole RAG path down.',
      where: 'Six services on Istio mesh: api-gateway (Go), ingestion-svc, retrieval-svc, inference-svc, governance-svc, eval-svc. Postgres + Qdrant + Neo4j + Redis + Kafka + MinIO behind.',
      when: 'Multi-tenant SaaS, ≥ 10 tenants, ≥ 100K chunks per tenant, audit + compliance requirements (HIPAA/SOC2/EU AI Act).',
      who: 'Platform / infra teams own the mesh + datastores; product teams own per-tenant features; security owns RLS policies + audit chain; FinOps owns token/cost budgets.',
    },
    interview30s: 'For a multi-tenant RAG platform, I split data by role not technology: Postgres for transactional truth with RLS, Qdrant for semantic retrieval, Neo4j for multi-hop relationships, Redis for cache, Kafka for durable ingestion events, MinIO for raw artifacts. Every retrieval call goes through a transport breaker so a slow Qdrant doesn\'t kill the inference path. Tenant isolation is a database invariant via FORCE RLS, not just an app-layer WHERE clause. The proof is a real-Postgres drill that writes under tenant A and reads under tenant B and asserts zero rows.',
    coreBuildingBlocks: [
      'Mesh: Istio — mTLS, retries, circuit breakers per service',
      'Gateway: Go API gateway — JWT decode, tenant_id header, rate-limit',
      'Stores: Postgres (FORCE RLS) + Qdrant (per-tenant filter) + Neo4j + Redis + Kafka + MinIO',
      'Saga: ingestion saga (parse → chunk → embed → index → stamp-model) with per-step compensation',
      'Breakers: 5 specialized breakers (Retrieval, Token, Agent-Loop, Observability, CCB)',
      'Audit: hash-chained audit_log, write-on-decision for every BYPASSRLS op',
    ],
    architectureRelevance: {
      backend: 'Six Python services + one Go gateway. Each owns its DB schema. Repository pattern enforces tenant_connection() at boundary.',
      rag: 'Vector + graph + keyword fusion via reciprocal rank, then cross-encoder rerank top-20 → top-5. Embedding versioned + shadow-indexed for upgrades.',
      ai: 'Token CB enforces per-tenant FinOps budgets. Cognitive CB monitors LLM token stream for drift/repetition/forbidden patterns. Decision audit per request_id.',
      microservices: 'mTLS strict via PeerAuthentication. AuthorizationPolicy per service. VirtualService canary 90/10 for new revisions. PodDisruptionBudget per workload.',
    },
    hld: `flowchart TB
  subgraph clients[Clients]
    UI[Admin UI]
    SDK[API caller]
  end
  subgraph edge[Edge]
    AGW["api-gateway — JWT + tenant_id"]
  end
  subgraph mesh[Istio service mesh]
    ING[ingestion-svc]
    RET[retrieval-svc]
    INF[inference-svc]
    GOV[governance-svc]
    EVAL[eval-svc]
  end
  subgraph stores[Datastores]
    PG[(Postgres + RLS)]
    Q[(Qdrant)]
    N[(Neo4j)]
    R[(Redis)]
    K[(Kafka)]
    M[(MinIO)]
  end
  UI --> AGW
  SDK --> AGW
  AGW --> ING
  AGW --> RET
  AGW --> INF
  AGW --> GOV
  ING --> K
  ING --> M
  ING --> Q
  ING --> N
  RET --> Q
  RET --> N
  RET --> R
  INF --> RET
  INF --> PG
  GOV --> PG
  EVAL --> PG`,
    networkFlow: `flowchart LR
  C[Client] --> AGW["api-gateway — JWT decode + tenant_id header"]
  AGW -->|HTTPS X-Tenant-ID| INF[inference-svc]
  INF -->|gRPC X-Tenant-ID| RET[retrieval-svc]
  RET -->|HTTP MCP X-Tenant-ID| Q["Qdrant — payload filter tenant_id"]
  RET -->|Bolt X-Tenant-ID| N[Neo4j]
  RET -->|Redis tenant prefix| R[Redis]
  INF -->|HTTP X-Tenant-ID| OL[Ollama LLM]
  INF -->|asyncpg ops role + audit| PG[(Postgres)]`,
    flowchart: `flowchart LR
  Q[User query + tenant] --> CAP[Capture trace + correlation_id]
  CAP --> RET[retrieval-svc]
  RET -->|vector_breaker| QV[Qdrant ANN]
  RET -->|graph_breaker| NG[Neo4j hop]
  RET -->|cache| RC[Redis cache]
  QV --> AGG[Aggregate + rerank]
  NG --> AGG
  RC --> AGG
  AGG -->|chunks + degraded flag| INF[inference-svc]
  INF -->|prompt + chunks| LLM[Ollama]
  LLM --> OUT[Streaming response + citations]
  OUT --> AUD[audit_log + cost_log]`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant GW as api-gateway
  participant Inf as inference-svc
  participant Ret as retrieval-svc
  participant Q as Qdrant
  participant L as Ollama
  Cli->>GW: POST /ask + JWT
  GW->>GW: decode JWT extract tenant_id
  GW->>Inf: forward + X-Tenant-ID
  Inf->>Ret: query + tenant
  Ret->>Q: search top-K filter tenant_id
  Q-->>Ret: chunks
  Ret-->>Inf: chunks + degraded=false
  Inf->>L: prompt with grounded context
  L-->>Inf: tokens stream
  Inf-->>Cli: SSE response with citations`,
    coreLayers: [
      { layer: 'Edge', responsibility: 'TLS termination, JWT decode, tenant_id header injection, rate-limiting per-IP and per-tenant.' },
      { layer: 'Mesh', responsibility: 'mTLS strict between services, retries with budget, circuit breakers, traffic-shifting for canary deploys.' },
      { layer: 'Service', responsibility: 'Domain logic per service — ingestion saga, retrieval fusion, inference grounding, governance audit.' },
      { layer: 'Repository', responsibility: 'tenant_connection() context manager wraps every DB op. No raw SQL outside repos. Schema-per-service grants.' },
      { layer: 'Datastore', responsibility: 'ACID (PG with FORCE RLS) + ANN (Qdrant per-tenant collection) + graph (Neo4j) + cache (Redis tenant-prefixed) + log (Kafka outbox) + blob (MinIO).' },
      { layer: 'Audit', responsibility: 'Every BYPASSRLS op writes a hash-chained audit_log row. Decision audit per request_id captures input + chunks + score + override.' },
      { layer: 'Eval', responsibility: 'Offline golden dataset + online sampling. Recall@K, latency p95, cost per request all monitored. Eval gates CI on regression.' },
    ],
    lld: `flowchart LR
  subgraph req[Request scope]
    M[Middleware]
    R[Repository]
  end
  subgraph pool[asyncpg pool]
    P1[conn 1]
    P2[conn 2]
  end
  subgraph pg[Postgres]
    POL["RLS policy: tenant_id = current_setting"]
    TBL[(audit_log)]
  end
  M -->|extract tenant_id from JWT| R
  R -->|acquire conn| P1
  R -->|BEGIN + SET LOCAL app.current_tenant| POL
  R -->|SELECT/INSERT| POL
  POL -->|filter by tenant_id| TBL
  TBL --> R
  R -->|COMMIT + release| P1`,
    problem: 'A single-store, single-tenant system can\'t serve multiple regulated customers economically. ACID truth, semantic retrieval, and graph reasoning each have different scaling curves; combining them naively means cascading failures and cross-tenant leaks.',
    whyThisApproach: 'Role-per-store gives each backend its native shape. Service mesh + transport breakers contains backend failures. RLS makes tenant isolation a database invariant. Audit chain makes admin ops reconstructible.',
    whenToUse: [
      'Multi-tenant SaaS with regulated customers',
      '≥ 10 tenants and ≥ 100K chunks per tenant',
      'Compliance requires audit-grade access path',
      'Recall + latency both matter (not pure-vector)',
    ],
    whenNotToUse: [
      'Single-tenant POC — overkill',
      'Pure semantic search no audit needs — Pinecone + simple cache',
      'Strict offline mode — managed services not viable',
      'Sub-second p99 on 100M+ chunks — different architecture (sharded ANN + custom rerank)',
    ],
    input: 'Tenant request (JWT + question text) + corpus state',
    process: [
      'Edge: gateway decodes JWT, extracts tenant_id, sets header',
      'Service: retrieval-svc queries Qdrant + Neo4j + Redis in parallel through transport breakers',
      'Service: rerank top-20 → top-5 via cross-encoder',
      'Service: inference-svc grounds LLM call on chunks + emits citations',
      'Cross-cutting: audit + cost log + trace + cache write',
    ],
    output: 'Streaming answer + citations + degraded flag, with audit trail and cost log per request_id.',
    alternatives: [
      { name: 'Single Pinecone + RAG-as-a-service vendor', tradeoff: 'Faster MVP; vendor lock-in; weaker tenant isolation; less control over RLS-shaped invariants' },
      { name: 'Postgres pgvector only', tradeoff: 'One store to operate; slower at scale; index rebuild locks writes' },
      { name: 'LangChain + cloud-managed everything', tradeoff: 'Easier prototyping; harder to enforce custom RLS + breaker patterns; cost grows fast' },
    ],
    challenges: [
      'Embedding-version drift on upgrade — shadow index discipline required',
      'Tenant filter must be inescapable on every retrieval path — easy to forget',
      'Per-tenant Qdrant collections explode operational footprint at high tenant count',
      'Graph schema discipline non-negotiable — Cypher easy to write, easy to misuse',
      'Token CB thresholds need real production data to tune',
    ],
    edgeCases: [
      { case: 'Embedding model upgrade leaves old vectors incomparable', solution: 'Shadow-index with embedding_version + feature-flag flip after eval gate' },
      { case: 'Slow Qdrant takes inference latency past SLA', solution: 'Transport breaker opens on N consecutive timeouts; degraded=true returned' },
      { case: 'Cross-tenant query slips through admin endpoint', solution: 'Forbid BYPASSRLS in runtime path; admin endpoints route through documind_ops with audit' },
      { case: 'Cold tenant — no chunks indexed yet', solution: 'Degrade-honestly path: return "no relevant chunks" instead of hallucinating' },
    ],
    failureModes: [
      { mode: 'Postgres pool exhaustion', detect: 'asyncpg pool wait time histogram + statement_timeout firing rate', recover: 'Tune pool size; identify long queries via pg_stat_statements; statement_timeout' },
      { mode: 'Qdrant unreachable', detect: '/health/upstreams kind=qdrant returns reachable=false', recover: 'Transport breaker opens; degraded=true; alert SRE' },
      { mode: 'Embedding model breaks API contract', detect: 'Recall@K falls past tolerance in eval-svc', recover: 'Roll back model version; re-run eval; rebuild shadow index' },
      { mode: 'Cross-tenant leak via missing tenant_connection()', detect: 'drill_retrieval_tenant_isolation goes red', recover: 'Quarantine endpoint; restore middleware; ship drill to CI' },
      { mode: 'Token budget exceeded at peak', detect: 'Token CB throttle + block decisions > N/min', recover: 'Tier-aware budgets; route to smaller model; tenant-level rate-limit' },
    ],
    monitoring: [
      'Per-service: p95 latency, error rate, retry count',
      'Mesh: circuit breaker state per (service, target), open events',
      'Stores: pool wait time, slow query top-N, cache hit ratio',
      'Eval: Recall@K trend, hallucination rate, latency p95',
      'Cost: tokens per request, cost per tenant, budget breach events',
    ],
    testing: [
      'drill_retrieval_tenant_isolation — multi-tenant write/read returns zero',
      'drill_retrieval_transport_breaker — Qdrant down → CB opens',
      'drill_audit_seal — hash-chain integrity',
      'drill_token_cb — budget enforcement decisions',
      'drill_frontend_ui_validator — Playwright, all deep-dive pages',
    ],
    security: [
      'NOBYPASSRLS on app role; BYPASSRLS only via audited ops role',
      'mTLS strict between services',
      'JWT validated at edge, signed claim trusted internally',
      'PII redaction in audit_log via redact_pii=True',
      'Hash-chained audit per tenant',
    ],
    scaling: [
      '10x: pool tuning + index hot queries + read replicas',
      '100x: per-tenant Qdrant collection + Postgres partitioning',
      '1000x: shard by tenant_id range + multi-region',
      'Cost driver: Qdrant memory + LLM tokens',
    ],
    maturity: {
      mvp: 'Single Postgres + single Qdrant collection + Ollama, no mesh',
      production: 'Mesh + transport breakers + RLS forced + per-tenant filter + audit chain + Token CB',
      enterprise: 'Per-tenant Qdrant + read replicas + multi-region + DLP + dedicated FinOps dashboard + on-call rotation',
    },
    limitations: [
      'Architect-lens omits per-feature LLD detail — see /admin/techlead/deep',
      'Operating playbook (incident response, on-call) lives in runbooks not the architecture doc',
      'Cost projection requires per-tenant traffic profile — separate FinOps doc',
    ],
    projectFit: [
      'libs/py/documind_core/ — shared modules (db, breakers, audit, cache)',
      'services/*/migrations/ — schema-per-service',
      'mcp/server_*.py — MCP tool servers per namespace',
      'mcp/tests/drill_*.py — drill suite for every architectural invariant',
    ],
    interviewLine: 'A multi-tenant RAG architecture is not one decision — it\'s six: where tenant isolation lives (Postgres FORCE RLS), how retrieval fuses three stores (vector + graph + keyword), how the mesh contains failure (transport breakers per backend), how cost is bounded (Token CB), how audit is reconstructible (hash-chained log), and how the embedding model upgrades without taking the index down (shadow index). Each is independently defensible. Together they ship.',
    implementationSteps: [
      { step: 'Decide isolation primitive', logic: 'FORCE RLS on every tenant-owned table; app role NOBYPASSRLS; ops role BYPASSRLS but audited.' },
      { step: 'Schema-per-service grants', logic: 'Each service gets least-privilege grants on its own schema only; cross-service traffic via API not DB.' },
      { step: 'Define retrieval fusion', logic: 'Vector top-K + graph hop top-K + keyword fallback → reciprocal-rank fuse → cross-encoder rerank top-5.' },
      { step: 'Wire transport breakers', logic: 'One breaker per (caller, target) pair: Retrieval→Qdrant, Retrieval→Neo4j, Inference→Ollama, Inference→Postgres.' },
      { step: 'Mesh policy', logic: 'PeerAuthentication=STRICT; AuthorizationPolicy explicit per service; VirtualService canary 90/10 for new revisions.' },
      { step: 'Audit chain', logic: 'audit_log table with HMAC chain per tenant; fail_closed write — if audit DB is down, return 503, not silent 200.' },
      { step: 'Cost gate', logic: 'Token CB with per-tenant budget; on breach return 429 + Retry-After; daily budget reset cron.' },
      { step: 'Embedding upgrade pattern', logic: 'Add embedding_version column; shadow-index new model; eval gate on golden set; feature-flag flip.' },
      { step: 'Drill suite', logic: 'One drill per architectural invariant: tenant isolation, breaker transitions, audit seal, token budget, RLS forced.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/db.py — tenant-scoped connection
import contextlib
from asyncpg import Connection
from .audit import audit_chain_write

@contextlib.asynccontextmanager
async def tenant_connection(pool, tenant_id: str, *, role: str = "app"):
    """Acquire a pool conn, set the tenant invariant, yield.

    The RLS policy reads current_setting('app.current_tenant_id'), so
    forgetting to call SET LOCAL is the same as a missing WHERE — the
    runtime rejects the query rather than leaking rows.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {role}")
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', $1, true)",
                tenant_id,
            )
            try:
                yield conn
            finally:
                # transaction commit/rollback handles cleanup; SET LOCAL
                # is scoped to the txn so no manual reset needed.
                pass

# Usage in retrieval-svc/repository.py
async def list_chunks(pool, tenant_id: str, doc_id: str):
    async with tenant_connection(pool, tenant_id) as conn:
        return await conn.fetch(
            "SELECT id, text, embedding FROM chunks WHERE doc_id = $1",
            doc_id,
        )  # RLS policy adds AND tenant_id = current_setting(...)

# Admin ops with audit: BYPASSRLS forbidden in runtime path.
async def admin_purge_tenant(pool, tenant_id: str, actor_id: str):
    async with tenant_connection(pool, tenant_id, role="documind_ops") as conn:
        deleted = await conn.fetchval(
            "DELETE FROM chunks WHERE tenant_id = $1 RETURNING count(*)",
            tenant_id,
        )
        await audit_chain_write(
            conn, tenant_id=tenant_id, actor_id=actor_id,
            action="admin_purge_tenant", payload={"deleted": deleted},
        )
        return deleted`,
    },
    realUseCase: 'A new compliance customer onboards with 2M chunks. Day 1: shadow-indexed under embedding-version=v3 while v2 serves live. Day 2: eval-svc reports Recall@10 within 0.5pp of v2 on the customer\'s golden set. Day 3: feature-flag flip. Live retrieval moves to v3 in 30 seconds; old v2 vectors evicted by retention job at week 1. Zero query downtime. Zero index rebuild. The architectural invariant — embedding_version per row + shadow index — made this routine, not an outage.',
    prosCons: {
      pros: [
        'Tenant isolation is a database invariant, not an app discipline',
        'Per-backend breakers contain failure to one transport',
        'Audit chain makes admin ops reconstructible for compliance',
        'Schema-per-service supports parallel team velocity',
        'Shadow-index pattern enables zero-downtime model upgrades',
      ],
      cons: [
        'Six datastores = six SREs of operational surface',
        'Per-tenant Qdrant collection inflates ops cost at high tenant count',
        'Hash-chained audit adds write latency vs fire-and-forget log',
        'Mesh adds ~5–8 ms p50 overhead per hop vs direct calls',
        'Cross-tenant analytics (e.g., aggregate metrics) needs explicit BYPASSRLS path',
      ],
    },
    comparison: {
      left: 'Single-store / vendor-managed (e.g., Pinecone or pgvector-only)',
      right: 'This architecture (PG + Qdrant + Neo4j + mesh + breakers)',
      rows: [
        { aspect: 'Tenant isolation', left: 'API key or app-layer WHERE — easy to miss', right: 'Postgres FORCE RLS — database invariant' },
        { aspect: 'Failure containment', left: 'Vendor-managed or none', right: 'Per-(caller,target) transport breakers' },
        { aspect: 'Multi-store fusion', left: 'Vector only or vector+keyword', right: 'Vector + graph + keyword + cache' },
        { aspect: 'Audit', left: 'Vendor logs (limited) or manual logging', right: 'Hash-chained per tenant; tamper-evident' },
        { aspect: 'Cost predictability', left: 'Per-vector or per-query vendor billing', right: 'Self-host + Token CB per-tenant cap' },
        { aspect: 'Time to MVP', left: '1–2 weeks', right: '4–6 weeks' },
        { aspect: 'Recall@10 ceiling', left: '~85–90% on multi-hop questions', right: '95%+ via fusion + rerank' },
      ],
    },
    solutions: [
      { problem: 'Cross-tenant leak risk', solution: 'FORCE RLS + drill_retrieval_tenant_isolation in CI' },
      { problem: 'Slow backend cascading', solution: 'Transport breaker per (caller, target) pair' },
      { problem: 'Audit DB outage', solution: 'fail_closed: return 503 not silent 200' },
      { problem: 'Embedding model drift', solution: 'Shadow index + eval gate + feature flag' },
      { problem: 'Token budget surprise', solution: 'Daily-reset Token CB with 429+Retry-After' },
      { problem: 'Stale Qdrant after deletes', solution: 'Reconcile worker compares PG truth vs Qdrant payload' },
    ],
    bestPractices: {
      do: [
        'FORCE RLS on every tenant-owned table',
        'tenant_connection() context manager at every repo call',
        'One transport breaker per (caller, target) pair',
        'Audit hash-chain per tenant with periodic seal verification',
        'Schema-per-service grants — least privilege',
        'Shadow-index any embedding-model upgrade',
        'Eval gate on every retrieval/inference change',
      ],
      avoid: [
        'BYPASSRLS in runtime path (admin only, audited)',
        'Cross-service joins in DB — go through APIs',
        'One global breaker for all backends',
        'Logging audit to file before chain write completes',
        'Embedding upgrade without shadow index',
      ],
      optimize: [
        'Read replicas for governance + eval queries',
        'Per-tenant Qdrant collections only for hot tenants; shared collection w/ filter for cold',
        'Cache rerank scores at (query_hash, embedding_version) key',
        'Async audit batch flush ≤ 200 ms behind transaction commit',
        'Cross-encoder rerank only on top-20, not full corpus',
      ],
    },
    antiPatterns: [
      'App-layer tenant filter as the only isolation (one missed JOIN = leak)',
      'Single circuit breaker covering all backends (one slow transport opens everything)',
      'Audit log as fire-and-forget (loses entries during DB blip)',
      'Embedding upgrade by re-indexing in place (downtime + rollback impossible)',
      'BYPASSRLS in the user-facing service role (compliance violation)',
      'Per-tenant Qdrant collection for every tenant from day 1 (ops explosion)',
    ],
    testTypes: [
      'Unit: each service in isolation with mocked stores',
      'Integration: real Postgres + Qdrant + Neo4j via docker-compose',
      'Drill: end-to-end invariant proofs (tenant isolation, breaker, audit)',
      'Eval: golden-set Recall@K + hallucination rate, gates CI',
      'Chaos: kill Qdrant/Neo4j/Redis randomly, verify breaker + degraded path',
      'Load: per-tenant rate ladder up to budget breach',
      'Pen: cross-tenant probe via leaked JWT — must 403 + audit',
    ],
    testScenarios: [
      { scenario: 'Tenant A ingests doc; Tenant B queries it', expected: 'Zero rows + audit row noting cross-tenant denial' },
      { scenario: 'Qdrant returns 500 on retrieval', expected: 'Breaker opens at N consecutive; degraded=true to client' },
      { scenario: 'Embedding model upgraded mid-traffic', expected: 'Live queries served by old model until flag flip' },
      { scenario: 'Token budget exhausted at 90% of day', expected: '429 + Retry-After until tomorrow midnight UTC' },
      { scenario: 'Audit DB unreachable', expected: 'Write returns 503, no silent success' },
    ],
    testData: [
      { type: 'Multi-tenant fixture', example: '4 tenants × 50 docs × 200 chunks each; one cross-tenant duplicate phrase to flush leaks' },
      { type: 'Slow-backend mock', example: 'Toxiproxy in front of Qdrant adds 5s latency to N% of requests' },
      { type: 'Golden eval set', example: '500 (query, expected-doc-id, expected-section) tuples scored on recall@10' },
      { type: 'Audit chain seed', example: '1 sealed window per tenant with 10K rows each — verifier must accept all' },
    ],
    debuggingChecklist: [
      'Is the JWT decode dropping tenant_id? Check api-gateway logs for "no tenant claim"',
      'Did SET LOCAL run? Check pg_stat_activity for session app.current_tenant_id',
      'Is the breaker open? GET /admin/breakers → state per (caller, target)',
      'Is Qdrant healthy? GET /health/upstreams kind=qdrant → reachable + p95',
      'Is audit chain valid? Run drill_audit_seal — verifies HMAC chain per tenant',
      'Is embedding_version mismatched? SELECT DISTINCT embedding_version FROM chunks WHERE tenant=$1',
      'Token budget? GET /admin/cost/budget tenant=$1 → today_used / daily_cap',
    ],
    productionIssues: [
      { issue: 'Cross-tenant rows returned during a recall@10 sweep', rootCause: 'New endpoint missed tenant_connection() context manager. RLS skipped because session role was set globally.' },
      { issue: 'Inference latency p99 spike from 1.2s → 9s', rootCause: 'Qdrant pod OOM-killed. No transport breaker on Inference→Retrieval; cascade.' },
      { issue: 'Audit gap — 12 minutes of decisions missing', rootCause: 'Audit DB write timeout configured 50ms; bursty writes silently dropped instead of 503.' },
      { issue: 'Embedding upgrade dropped recall by 18pp', rootCause: 'Shadow-index built but eval gate not enforced; flag flipped before recall regression caught.' },
    ],
    performance: [
      'p50 latency: gateway 2ms + retrieval 80ms + rerank 25ms + LLM stream first-token 350ms = ~457ms',
      'p95: 850ms (LLM dominates); breaker open path ~120ms (degraded)',
      'Throughput per inference pod: 30 req/s sustained; 60 req/s burst',
      'Cache hit ratio: 35% on retrieval (query→chunks), 60% on rerank',
      'Storage: ~120 KB per chunk (text + 768-d float32 + metadata) → 24 GB per 200K chunks',
    ],
    costConsiderations: [
      'Qdrant memory: ~1.5 KB per vector @ 768-d quantized → 300 MB per 200K chunks per tenant',
      'LLM tokens: ~80% of cost at scale; gate via Token CB per-tenant daily cap',
      'Postgres I/O: WAL-heavy from audit chain; reserve r6i.xlarge minimum',
      'Neo4j: ~50% memory overhead vs vector store; only justified if multi-hop queries are common',
      'Mesh overhead: Istio sidecar adds ~50 MB RAM per pod and ~5ms p50',
    ],
    observability: [
      'Trace: OTel from edge → mesh → service → store; correlation_id propagated as W3C TraceParent',
      'Metrics: per-service histogram (latency p50/p95/p99), CB state gauge, pool wait time',
      'Logs: JSON structured with correlation_id, tenant_id, request_id; ship to Loki/CloudWatch',
      'Decision audit: per-request_id row with input + chunks + score + final answer',
      'Cost log: per-request token count + USD cost; aggregate by tenant + day',
    ],
    metrics: [
      { name: 'documind_request_duration_seconds', example: 'histogram_quantile(0.95, sum(rate(...[5m])) by (le, service))' },
      { name: 'documind_circuit_breaker_state', example: '1 = open, 0 = closed; alert if open > 5min for any (caller,target)' },
      { name: 'documind_tenant_isolation_violations_total', example: 'Counter; alert at any value > 0 (page on-call)' },
      { name: 'documind_audit_write_failures_total', example: 'Counter; alert if rate(5m) > 0.1/min' },
      { name: 'documind_eval_recall_at_10', example: 'Gauge per embedding_version; alert on regression > 2pp' },
      { name: 'documind_token_budget_exhausted_total', example: 'Counter by tenant; weekly review of top breaches' },
    ],
    tradeoffs: [
      { decision: 'FORCE RLS vs app-layer filter', tradeoff: 'Invariant but adds 2–4% query overhead from policy eval' },
      { decision: 'Per-tenant Qdrant vs shared+filter', tradeoff: 'Isolation + tuning but Nx ops cost at high tenant count' },
      { decision: 'Shadow index vs in-place upgrade', tradeoff: 'Zero downtime but 2x storage during transition window' },
      { decision: 'Hash-chain audit vs append-only log', tradeoff: 'Tamper-evident but write-amplification ~1.3x' },
      { decision: 'Mesh vs direct gRPC', tradeoff: 'Policy + observability but 5–8ms p50 hop overhead' },
    ],
    decisionMatrix: [
      { option: 'Pinecone managed', whenToUse: 'Single-tenant POC, no audit needs, time-to-MVP critical' },
      { option: 'pgvector only', whenToUse: '< 100K total chunks, no graph queries, single team' },
      { option: 'This (PG+Qdrant+Neo4j+mesh)', whenToUse: 'Multi-tenant SaaS ≥ 10 tenants, compliance, recall + latency both matter' },
      { option: 'Custom sharded ANN + own rerank', whenToUse: '100M+ chunks, < 100ms p99 retrieval, infra team can operate' },
    ],
    starStory: {
      situation: 'A new compliance customer flagged that our admin "purge-tenant" endpoint could theoretically read another tenant\'s data — even though it never had in production — because it ran with BYPASSRLS implicitly.',
      task: 'Eliminate the implicit BYPASSRLS path while keeping admin operability. Prove the fix with a drill that fails closed if the discipline regresses.',
      action: 'Split the DB role into app (NOBYPASSRLS) and documind_ops (BYPASSRLS, audited). Wrapped admin paths in a context manager that switches role + writes a hash-chained audit row before every BYPASSRLS query. Wrote drill_admin_audit that asserts: (1) admin op without audit fails 503, (2) the chain HMAC verifies post-op.',
      result: 'Compliance customer accepted the architecture. drill_admin_audit added to CI; gates main. Zero compliance findings in subsequent quarterly review. Pattern documented as ADR-007 and adopted by three other internal services.',
    },
    interviewTraps: [
      'Saying "we use RLS" without explaining FORCE — non-FORCE leaks via superuser path',
      'Claiming "circuit breakers" without specifying per-(caller,target) — one global CB is half a CB',
      'Conflating audit with logging — audit is hash-chained, append-only, fail-closed',
      'Treating embedding upgrade as a deploy — it\'s a data migration with eval gate',
      'Saying "Pinecone is the same" — it\'s not; vendor-trust ≠ DB invariant',
      'Forgetting the cold-tenant degrade path — silent hallucination is the failure mode',
    ],
    finalScript: 'A multi-tenant RAG platform is six decisions stitched into one architecture. First, tenant isolation lives in the database via FORCE RLS — not in the app layer where it\'s one missed JOIN from a leak. Second, retrieval fuses three stores: Qdrant for semantic, Neo4j for graph, and a keyword fallback. Third, every transport gets its own circuit breaker so a slow Qdrant doesn\'t take inference down. Fourth, cost is bounded by a Token CB enforcing per-tenant FinOps budgets. Fifth, every BYPASSRLS operation writes a hash-chained audit row — admin ops are reconstructible. Sixth, embedding upgrades use a shadow index with feature-flag flip after eval gate — zero downtime. Each decision is independently defensible. The non-negotiable test is a real-Postgres drill that writes under tenant A and reads under tenant B and asserts zero rows.',
  },
];

export default function ArchitectDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Architect — Deep Dive</h1>
        <p className="design-areas-sub">
          The architect lens: system-level decisions, boundaries, and ADRs. Emphasis on §4 HLD,
          §5 Network Flow, §7 Core Components, §32 Trade-offs, §33 Decision matrix. Use this
          when explaining the platform shape to senior reviewers, hiring panels, or compliance.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
