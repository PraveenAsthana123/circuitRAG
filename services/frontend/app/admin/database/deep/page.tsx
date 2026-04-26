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
    oneLiner: 'Postgres for ACID truth + RLS for tenant isolation as a database invariant, not an application convention.',
    businessContext: 'We need to design a multi-tenant SaaS data layer where one tenant cannot read or write another tenant\'s data — even if the application code has a bug. Compliance and trust require isolation as a structural invariant, not an application convention.',
    networkFlow: `flowchart LR
  C[Client] --> AGW["api-gateway — JWT + tenant_id header"]
  AGW -->|HTTPS X-Tenant-ID| GS[governance-svc]
  AGW -->|HTTPS X-Tenant-ID| RS[retrieval-svc]
  GS -->|asyncpg pool app role| PG[("Postgres — RLS forced")]
  RS -->|asyncpg pool app role| PG
  GS -->|asyncpg pool ops role + audit| PG
  PG -.->|WAL stream| REP[(read replica)]
  PG -.->|WAL archive| S3[(S3 PITR)]`,
    coreLayers: [
      { layer: 'Connection layer', responsibility: 'asyncpg pool per service; tenant_connection() context manager; opens BEGIN + SET LOCAL app.current_tenant.' },
      { layer: 'Role layer', responsibility: 'Three Postgres roles: documind (owner, migrations only), documind_app (NOBYPASSRLS, runtime), documind_ops (BYPASSRLS, audited admin).' },
      { layer: 'Schema layer', responsibility: 'Schema-per-service (governance / ingestion / retrieval / observability / etc); cross-service reads go through APIs, not SQL JOINs.' },
      { layer: 'RLS policy layer', responsibility: 'Every multi-tenant table: ENABLE + FORCE ROW LEVEL SECURITY with policy USING (tenant_id = current_setting(\'app.current_tenant\')::uuid).' },
      { layer: 'Repository layer', responsibility: 'Python class wrapping all SQL; exposes tenant-scoped methods only; no module-level globals; constructor injection.' },
      { layer: 'Migration layer', responsibility: 'Forward-only numbered SQL files; runs as owner role; CI runs against fresh DB; never edit deployed migrations.' },
      { layer: 'Audit layer', responsibility: 'governance.audit_log with hash-chained prev_hash/curr_hash per tenant; every BYPASSRLS op writes an audit row.' },
    ],
    fiveW: {
      what: 'A relational database with row-level security policies that filter rows based on a per-session variable (app.current_tenant). Queries silently return only rows the tenant is allowed to see.',
      why: 'Application-layer tenant filtering is one missed JOIN away from a cross-tenant leak. RLS turns isolation into a database invariant — even a buggy query cannot break it.',
      where: 'Domain truth tables: audit_log, action_drafts, prompts, mcp_idempotency, identities. Anywhere a tenant_id column needs to be inescapable.',
      when: 'Multi-tenant SaaS where one tenant seeing another\'s data is unacceptable; auditable systems where access must be reconstructable.',
      who: 'Application services (NOBYPASSRLS role), operational tools (BYPASSRLS role with audit), migration runner (owner role with explicit grants).',
    },
    interview30s: 'For domain truth in a multi-tenant SaaS we use Postgres with row-level security forced on every table. The application connects as a NOBYPASSRLS role and middleware sets app.current_tenant per request via SET LOCAL — so even if a query forgets the tenant_id WHERE clause, the database silently filters rows. Privileged ops use a separate BYPASSRLS role that always writes an audit row. The non-negotiable test is a real-Postgres drill that writes under tenant A and reads under tenant B and asserts zero rows.',
    coreBuildingBlocks: [
      'Schema-per-service (identity, ingestion, governance, finops, eval, observability)',
      'Three roles: documind (owner, migrations), documind_app (NOBYPASSRLS, runtime), documind_ops (BYPASSRLS, audited admin)',
      'RLS policies with USING + WITH CHECK referencing current_setting(\'app.current_tenant\')',
      'Session-local SET LOCAL app.current_tenant at the start of every transaction',
      'asyncpg connection pool with tenant_connection() context manager',
      'Hash-chained audit_log with prev_hash + curr_hash per row',
    ],
    architectureRelevance: {
      backend: 'Primary system of record; every write goes through a repository class that enforces tenant_connection(); no raw SQL outside repositories.',
      rag: 'Stores document metadata, chunk_id → doc_id mapping, embedding model version, tenant_id. Vector data lives in Qdrant; relational truth lives in Postgres.',
      ai: 'Stores prompt registry rows, model registry rows, action_drafts (HITL queue), eval results, decision audit (decision_id → input/output/policy/confidence).',
      microservices: 'Six services share the cluster but own distinct schemas; cross-service reads go through APIs, not SQL JOINs. Schema-per-service keeps deploys decoupled.',
    },
    hld: `flowchart TB
  subgraph clients[Clients]
    UI[Admin UI]
    SDK[SDK / API caller]
  end
  subgraph gw[Gateway]
    APIGW["api-gateway — JWT + tenant_id"]
  end
  subgraph svcs[Services]
    INF[inference-svc]
    RET[retrieval-svc]
    GOV[governance-svc]
    AUD[audit writer]
  end
  subgraph pg[Postgres cluster]
    OWN[("documind owner role — migrations only")]
    APP[("documind_app — NOBYPASSRLS runtime")]
    OPS[("documind_ops — BYPASSRLS audited admin")]
    DB[("Postgres 16 — schema-per-service + FORCE RLS")]
  end
  UI --> APIGW
  SDK --> APIGW
  APIGW --> INF
  APIGW --> RET
  APIGW --> GOV
  INF --> APP
  RET --> APP
  GOV --> APP
  GOV --> AUD
  AUD --> APP
  APP --> DB
  OPS --> DB
  OWN --> DB`,
    lld: `flowchart LR
  subgraph req[Request scope]
    M[Middleware]
    R[Repository]
  end
  subgraph pool[asyncpg pool]
    P1[conn 1]
    P2[conn 2]
    PN[conn N]
  end
  subgraph pg[Postgres]
    SES[Session: app.current_tenant]
    POL["RLS policy USING tenant_id = current_setting"]
    TBL[(audit_log table)]
  end
  M -->|extract tenant_id from JWT| R
  R -->|acquire conn| P1
  R -->|BEGIN + SET LOCAL app.current_tenant| SES
  SES --> POL
  R -->|SELECT/INSERT| POL
  POL -->|filter by tenant_id| TBL
  TBL -->|rows OR empty| R
  R -->|COMMIT + release conn| P1`,
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
  Mid->>PG: BEGIN then SET LOCAL app.current_tenant
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
    implementationSteps: [
      { step: '1', logic: 'Create three Postgres roles via 001_initial.sql: documind (owner), documind_app (NOBYPASSRLS), documind_ops (BYPASSRLS).' },
      { step: '2', logic: 'Define schema-per-service in migrations: CREATE SCHEMA governance; ALTER ROLE documind_app SET search_path TO governance.' },
      { step: '3', logic: 'On every multi-tenant table: ENABLE ROW LEVEL SECURITY + FORCE ROW LEVEL SECURITY. CREATE POLICY tenant_isolation USING (tenant_id = current_setting(\'app.current_tenant\')::uuid) WITH CHECK (...).' },
      { step: '4', logic: 'Wrap connection acquisition in async tenant_connection(tenant_id): pool.acquire() → conn.execute("SET LOCAL app.current_tenant = $1", tenant_id) → yield conn.' },
      { step: '5', logic: 'Repository methods take tenant_id explicitly; no module-level connection; every method opens its own tenant-scoped transaction.' },
      { step: '6', logic: 'Privileged ops route through documind_ops role and write an audit_log row with actor + reason + redact_pii=True.' },
      { step: '7', logic: 'Drill against real Postgres — write tenant A, read tenant B → assert empty result. Mocks lie about RLS.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/db/tenant_connection.py
from contextlib import asynccontextmanager
import asyncpg

@asynccontextmanager
async def tenant_connection(pool: asyncpg.Pool, tenant_id: str):
    """Yield a Postgres connection with app.current_tenant set
    for the lifetime of the transaction.
    RLS policies reference current_setting('app.current_tenant').
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SET LOCAL app.current_tenant = $1", tenant_id
            )
            yield conn
        # COMMIT releases the SET LOCAL automatically.

# Repository usage:
class AuditRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def list_for_tenant(self, tenant_id: str, limit: int = 100):
        async with tenant_connection(self._pool, tenant_id) as c:
            return await c.fetch(
                "SELECT * FROM audit_log "
                "ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        # No tenant_id WHERE clause needed — RLS adds it.`,
    },
    realUseCase: 'Tenant A uploads a confidential PDF; later, tenant B searches their corpus and accidentally crafts a query that would have matched tenant A\'s chunk. Without RLS, a missed JOIN clause in the audit query exposes the chunk\'s metadata. With RLS, even the buggy query returns zero rows because Postgres filters at the storage layer. The drill that proves this is drill_retrieval_tenant_isolation: write under tenant A, read under tenant B, assert empty.',
    prosCons: {
      pros: [
        'Tenant isolation as a database invariant — survives application bugs',
        'ACID guarantees + foreign keys + JOINs + standard SQL ergonomics',
        'Auditable access via separate roles with explicit grants',
        'Hash-chained audit_log makes tampering detectable',
        'Single cluster simpler to operate than per-tenant DB sharding',
      ],
      cons: [
        'Real-DB tests required — mocks lie about RLS',
        'SET LOCAL must be paired with BEGIN; lapse = no isolation',
        'Cross-tenant analytics needs a separate pipeline (warehouse)',
        'Connection pool exhaustion is a real risk under load',
        'Single cluster = single blast radius if it goes down',
      ],
    },
    comparison: {
      left: 'Postgres + RLS',
      right: 'App-layer tenant filtering',
      rows: [
        { aspect: 'Failure mode', left: 'Empty result (silent isolation)', right: 'Cross-tenant leak (data breach)' },
        { aspect: 'Defense in depth', left: 'DB enforces even if app forgets', right: 'Single point of failure in app code' },
        { aspect: 'Test reliability', left: 'Real-DB drill catches regressions', right: 'Easy to forget to test the missed-WHERE case' },
        { aspect: 'Performance', left: 'Index on tenant_id required for hot tables', right: 'Same index requirement' },
        { aspect: 'Migration cost', left: 'Higher: roles + policies + tenant_connection()', right: 'Lower: just a column + a WHERE clause' },
        { aspect: 'Auditability', left: 'BYPASSRLS only via audited ops role', right: 'No structural separation' },
      ],
    },
    solutions: [
      { problem: 'A new repository method skips tenant_connection()', solution: 'Code review checklist + drill that asserts cross-tenant read returns zero (catches the bug post-merge)' },
      { problem: 'Migration runs as runtime role and fails on BYPASSRLS', solution: 'Migration runner uses owner role; explicit GRANT on each migration; CI runs migrations against a fresh DB' },
      { problem: 'Operator forgets to set redact_pii=True for ops query', solution: 'Repository ops_query() helper requires redact_pii kwarg; lint rule fails build if literal False' },
      { problem: 'Long-running query holds connection + blocks pool', solution: 'statement_timeout = 30s on app role; pg_stat_activity dashboard; alert on idle_in_transaction > 10s' },
      { problem: 'Hash-chain breaks because two writers race on prev_hash', solution: 'SELECT ... FOR UPDATE on the previous row inside the same transaction; serialize per-tenant via advisory lock' },
    ],
    bestPractices: {
      do: [
        'FORCE ROW LEVEL SECURITY on every multi-tenant table (not just ENABLE)',
        'SET LOCAL inside a BEGIN — never SET (session-level) in a pooled connection',
        'Real-DB integration tests for every RLS policy',
        'Index every tenant_id column (it\'s in every WHERE clause now)',
        'Hash-chain the audit_log; verify with a periodic drill',
      ],
      avoid: [
        'BYPASSRLS in the runtime role — it defeats the entire mechanism',
        'Mocking Postgres in RLS tests — only real Postgres enforces policies',
        'Cross-schema foreign keys — they couple deploys',
        'Long-running connections without statement_timeout',
        'Storing PII in audit_log.details without redact_pii=True',
      ],
      optimize: [
        'pg_stat_statements + slow query log → indexed top-N hot queries',
        'Partition audit_log by month once it crosses ~10M rows',
        'Read replicas for analytics; never for tenant-scoped reads (replication lag)',
        'Connection pool sized to (services × workers × concurrency); monitor wait time histogram',
        'EXPLAIN (ANALYZE, BUFFERS) on hot queries; add covering indexes',
      ],
    },
    antiPatterns: [
      'Granting BYPASSRLS to documind_app "just for one feature" — irreversible drift',
      'Setting app.current_tenant at session level on a pooled connection — leaks tenant context to next caller',
      'Cross-tenant SELECT in admin code without a corresponding audit_log row',
      'Mocking the database in RLS unit tests — passes locally, leaks in prod',
      'Running migrations as documind_app — silently fails on policy creation',
      'Using SELECT ... FROM tenant_a.table inside tenant_b\'s flow — schema-as-tenant is brittle',
    ],
    testTypes: [
      'Unit (repository method shape, not RLS itself)',
      'Integration against real Postgres (RLS policies)',
      'Drill — multi-tenant write/read with negative assertion',
      'Performance — pgbench under representative concurrency',
      'Failure injection — pool exhaustion, statement_timeout, connection drop',
    ],
    testScenarios: [
      { scenario: 'Write under tenant A; read under tenant B', expected: 'Zero rows returned' },
      { scenario: 'App role attempts SET ROLE TO documind', expected: 'Permission denied' },
      { scenario: 'Run migration as app role', expected: 'Permission denied on CREATE POLICY' },
      { scenario: 'Long query exceeds statement_timeout', expected: 'Query cancelled; pool returned' },
      { scenario: 'Insert with mismatched tenant_id WITH CHECK', expected: 'INSERT rejected by policy' },
      { scenario: 'Audit row write without prev_hash lock', expected: 'Two concurrent writers serialize via FOR UPDATE; chain stays valid' },
    ],
    testData: [
      { type: 'Valid', example: '{tenant_id: <UUID-A>, action: "draft.create", actor: "user@A", details: {...}}' },
      { type: 'Cross-tenant', example: 'tenant_id = UUID-A in row, app.current_tenant = UUID-B in session → SELECT returns zero' },
      { type: 'Boundary', example: '10MB JSON in details field; verify TOAST handling' },
      { type: 'Extreme', example: '50K writes/sec for 60s — verify replication lag, pool wait time' },
      { type: 'Invalid', example: 'tenant_id = NULL → policy rejects with NOT NULL violation' },
    ],
    debuggingChecklist: [
      'Is app.current_tenant set in this transaction? (SHOW app.current_tenant)',
      'Is the connection role NOBYPASSRLS? (SELECT current_user, rolbypassrls FROM pg_roles)',
      'Is RLS enabled AND forced on this table? (\\d+ tablename in psql)',
      'Does the policy reference current_setting() correctly? (\\dp+ tablename)',
      'Is the index on tenant_id being used? (EXPLAIN ANALYZE)',
      'Is statement_timeout firing too aggressively for the workload? (SHOW statement_timeout)',
      'Are there idle_in_transaction connections holding rows? (pg_stat_activity)',
    ],
    productionIssues: [
      { issue: 'Cross-tenant rows visible in admin UI', rootCause: 'Admin UI used documind_ops role without audit; RLS bypassed silently' },
      { issue: 'Pool exhaustion at 10 RPS', rootCause: 'Long-running BYPASSRLS analytics query held connection for 90s' },
      { issue: 'Audit chain hash mismatch', rootCause: 'Concurrent writers raced on prev_hash without FOR UPDATE; one chain forked' },
      { issue: 'Migration fails on production', rootCause: 'CI ran migrations against fresh DB; prod had data violating new CHECK constraint' },
      { issue: 'p99 latency spike on every audit write', rootCause: 'audit_log lacked index on (tenant_id, created_at DESC); table-scan as it grew' },
    ],
    performance: [
      'p50 query latency < 5ms on indexed tenant_id reads',
      'p99 < 50ms with statement_timeout = 30s ceiling',
      'Connection pool wait time < 10ms p95 (alert > 100ms)',
      'pg_stat_statements top-10 reviewed weekly',
      'Audit_log writes < 2ms p95; partition once size > 10M rows',
    ],
    costConsiderations: [
      'Storage growth dominated by audit_log retention — partition + drop policy',
      'Read replicas double IOPS cost; useful only for analytics',
      'BYPASSRLS roles often hide expensive cross-tenant scans → audit cost',
      'Connection count × pool size × workers — easy to over-provision',
      'WAL archive storage for PITR — sized to RPO target',
    ],
    observability: [
      'Logs: every BEGIN with app.current_tenant tagged in the log line',
      'Traces: span attribute db.tenant_id on every query span',
      'Metrics: pool_wait_time_seconds_bucket, audit_write_failures_total, rls_policy_eval_total',
      'Dashboards: per-role connection count, slow query top-10, replication lag',
      'Alerts: idle_in_transaction > 10s; replication lag > 30s; statement_timeout firing rate',
    ],
    metrics: [
      { name: 'pg_pool_wait_ms_p95', example: '< 10ms target; alert > 100ms' },
      { name: 'pg_stat_statements_total_time', example: 'Top-10 reviewed weekly' },
      { name: 'audit_write_failures_total', example: '0 expected; any non-zero pages on-call' },
      { name: 'rls_policy_eval_per_query', example: 'Approximate via pg_stat_user_tables seq_scan delta' },
      { name: 'connection_count_by_role', example: 'documind_app < 80%; documind_ops < 5%' },
    ],
    tradeoffs: [
      { decision: 'Single cluster vs per-tenant DB', tradeoff: 'Operational simplicity vs blast-radius isolation' },
      { decision: 'RLS vs app-layer filtering', tradeoff: 'Higher migration cost + real-DB tests vs cross-tenant leak risk' },
      { decision: 'BYPASSRLS for ops vs no BYPASSRLS at all', tradeoff: 'Operational ergonomics vs zero structural cross-tenant access' },
      { decision: 'Schema-per-service vs DB-per-service', tradeoff: 'Shared cluster cost vs full deploy independence' },
      { decision: 'Hash-chain audit vs append-only WAL audit', tradeoff: 'Cryptographic detection of tampering vs simpler write path' },
    ],
    decisionMatrix: [
      { option: 'Postgres + RLS', whenToUse: 'Multi-tenant SaaS; ACID required; relational data; auditable' },
      { option: 'Postgres without RLS', whenToUse: 'Single-tenant; or non-sensitive data; or tiny scale where app-layer filtering is auditable' },
      { option: 'DB-per-tenant', whenToUse: 'Hard regulatory isolation (e.g., HIPAA-per-tenant); few large tenants' },
      { option: 'Schema-per-tenant', whenToUse: 'Mid-tenant count with strong isolation but shared infra; harder to operate' },
      { option: 'CockroachDB / Citus', whenToUse: 'Beyond single-cluster scale; willing to trade extension breadth for distributed strong consistency' },
    ],
    starStory: {
      situation: 'During a multi-tenant SaaS rollout, two tenants reported seeing each other\'s draft data in the admin UI. Initial guess: an app-layer JOIN bug.',
      task: 'Find the cross-tenant leak, prove it doesn\'t recur, ship a fix that survives future regressions.',
      action: 'Wrote a real-Postgres drill (drill_retrieval_tenant_isolation): write under tenant A, read under tenant B, assert empty. Drill went red against staging. Root cause: admin UI used the BYPASSRLS ops role for convenience and forgot the WHERE tenant_id = ... clause. Fix: removed the BYPASSRLS shortcut, made tenant_connection() the only path, added the drill to CI.',
      result: 'Drill caught two more would-be leaks during the next two sprints (different code paths, same anti-pattern). Migration to NOBYPASSRLS-only runtime took two weeks; zero cross-tenant incidents in the year since.',
    },
    interviewTraps: [
      'Saying "RLS replaces application-layer filtering" — it complements it, doesn\'t replace it',
      'Forgetting to mention SET LOCAL must be inside BEGIN (session-level SET on a pooled conn leaks)',
      'Conflating ENABLE with FORCE — without FORCE, table owner bypasses policies',
      'Treating BYPASSRLS as a "harmless convenience" — it\'s a structural escape hatch that needs an audit row',
      'Claiming "we tested RLS" with mocks — only real Postgres enforces policies',
      'Skipping the index on tenant_id — every query now filters on it; missing index = seq scan',
    ],
    finalScript: 'For domain truth in a multi-tenant SaaS we use Postgres with row-level security forced on every table. The application connects as a NOBYPASSRLS role, and middleware sets app.current_tenant per request via SET LOCAL inside the transaction. So even if a query forgets the tenant_id WHERE clause, the database silently filters rows. Privileged operations use a separate BYPASSRLS role and always write an audit row. The non-negotiable test is a real-Postgres drill that writes under tenant A, reads under tenant B, and asserts zero rows. Mocks lie about RLS — only the live cluster enforces it.',
    interviewLine: 'For domain truth we use Postgres with schema-per-service and row-level security. The key design choice is role separation: the app runtime cannot bypass RLS, while privileged operational access is isolated and audited.',
  },

  // ---- 2. Qdrant ----
  {
    slug: 'qdrant',
    title: '2. Qdrant — vector DB (semantic retrieval)',
    status: 'shipped',
    coreConcept: 'Qdrant is a retrieval accelerator for embedding-based nearest-neighbor search — NOT a transactional source of truth. HNSW gives sub-100ms ANN; payload filter on tenant_id makes isolation inescapable.',
    oneLiner: 'Qdrant = sub-100ms semantic search with per-tenant payload filter. Not a database; a retrieval accelerator.',
    businessContext: 'We need sub-second semantic search across millions of chunks with strict per-tenant isolation. Keyword search misses meaning; pure vector misses exact terms; pgvector can\'t scale at our query volume without locking writes.',
    fiveW: {
      what: 'A vector database with HNSW index for approximate nearest-neighbor search, scalar quantization for memory reduction, and payload filtering to enforce tenant_id at query time.',
      why: 'RAG retrieval is bottlenecked on recall × latency. Postgres + pgvector can\'t hit p99 < 100ms above ~1M vectors without locking writes during index rebuild. Qdrant\'s HNSW + quantization + payload filter solves all three simultaneously.',
      where: 'retrieval-svc queries Qdrant via QdrantRepo. Per-tenant collection for regulated customers; shared collection with tenant_id filter for the rest. Rebuilds happen via shadow-collection pattern.',
      when: '≥ 100K chunks per tenant, sub-200ms p99 latency required, hybrid retrieval (vector + keyword) needed, embedding-model upgrade discipline.',
      who: 'Retrieval team owns QdrantRepo. Platform owns Qdrant cluster. Eval team owns recall benchmarks. SRE owns memory + p99 alerts.',
    },
    interview30s: 'Qdrant is our semantic retrieval accelerator — not a database, a search engine. We use HNSW for sub-linear ANN, scalar quantization for ~4x memory reduction, and a mandatory tenant_id payload filter so cross-tenant leak is structurally impossible. Embedding model upgrades use a shadow-collection pattern: build new collection in background, run eval gate, flip read traffic via feature flag, drop old. The non-negotiable test is drill_retrieval_tenant_isolation — write under tenant A, query under tenant B, assert zero results against the live cluster.',
    coreBuildingBlocks: [
      'HNSW index — sub-linear ANN search, M=16 default',
      'Scalar quantization — int8 for vectors, ~4x memory reduction with ~1% recall loss',
      'Payload — tenant_id, doc_id, chunk_id, embedding_model, embedding_version per point',
      'Filter — must.tenant_id mandatory on every query (enforced in QdrantRepo)',
      'Collection alias — for shadow-index zero-downtime model upgrade',
      'gRPC client — async Python client wrapped in QdrantRepo',
      'Per-tenant collection (optional) — for regulated customers requiring physical isolation',
    ],
    architectureRelevance: {
      backend: 'QdrantRepo wraps every search/upsert. No raw client in services — all calls go through the repo with tenant_id explicit at API.',
      rag: 'Step 2 of retrieval (after embed): ANN search top-20 with payload filter. Result feeds reranker → top-5 → grounded LLM call.',
      ai: 'Embedding-model versioned per point. Upgrade workflow: shadow collection → re-embed → eval gate → flip traffic → drop old.',
      microservices: 'retrieval-svc is the only service holding Qdrant client. Inference + governance go through retrieval. Transport breaker per Qdrant call.',
    },
    hld: `flowchart TB
  subgraph svcs[Services]
    ING[ingestion-svc]
    RET[retrieval-svc]
    INF[inference-svc]
    EVAL[eval-svc]
  end
  subgraph qd[Qdrant cluster]
    HNSW[("HNSW index — M=16 + scalar quant")]
    PAYLOAD[("Payload — tenant_id + doc_id + chunk_id")]
    SHADOW[("Shadow collection — for model upgrade")]
  end
  ING -->|upsert vectors + payload| HNSW
  RET -->|search + filter tenant_id| HNSW
  EVAL -->|recall benchmark| HNSW
  INF --> RET
  HNSW -.->|alias swap on upgrade| SHADOW`,
    networkFlow: `flowchart LR
  C[Client] --> AGW["api-gateway — JWT + tenant_id"]
  AGW -->|HTTPS X-Tenant-ID| INF[inference-svc]
  INF -->|gRPC X-Tenant-ID| RET[retrieval-svc]
  RET -->|gRPC search payload-filter| Q["Qdrant — HNSW + quant"]
  RET -->|HTTP cross-encoder| RR[Reranker]
  Q -.->|admin API| OPS[Qdrant operator]
  Q -.->|metrics| PROM[Prometheus]`,
    flowchart: `flowchart LR
  a[Document chunks] --> b[Embed]
  b --> c[Upsert to Qdrant + payload]
  d[User query] --> e[Embed query]
  e --> f[ANN search top-K + filter tenant_id]
  f --> g[Top-20 chunks with scores]
  g --> h[Cross-encoder rerank]
  h --> i[Top-5 chunks]
  i --> j[Pass to inference for grounded answer]`,
    sequence: `sequenceDiagram
  autonumber
  participant Ing as ingestion-svc
  participant Emb as Embedder
  participant Q as Qdrant
  participant Ret as retrieval-svc
  participant Inf as inference-svc
  Ing->>Emb: chunks
  Emb-->>Ing: vectors
  Ing->>Q: upsert(vectors, payload tenant_id+doc_id)
  Inf->>Ret: query "What is the leave policy?"
  Ret->>Emb: embed query
  Ret->>Q: search vector with filter tenant_id
  Q-->>Ret: top-K with scores
  Ret-->>Inf: chunks
  Inf-->>Inf: assemble prompt and generate`,
    coreLayers: [
      { layer: 'Index layer', responsibility: 'HNSW with M=16, ef_construct=200, ef=100 default. Tunable per workload.' },
      { layer: 'Quantization layer', responsibility: 'Scalar (int8) by default. Binary for ultra-high-volume tenants. ~1-3% recall loss vs flat.' },
      { layer: 'Payload layer', responsibility: 'tenant_id (UUID), doc_id, chunk_id, embedding_model, embedding_version per point. Indexed for filter performance.' },
      { layer: 'Filter layer', responsibility: 'must.tenant_id required on every search. QdrantRepo API has no path to query without it.' },
      { layer: 'Collection layer', responsibility: 'Shared collection with payload-filter for default tenants; per-tenant collection for regulated customers.' },
      { layer: 'Alias layer', responsibility: 'Collection alias enables shadow-collection model upgrade without read interruption.' },
      { layer: 'Repository layer', responsibility: 'QdrantRepo: all ops require tenant_id parameter. No raw client outside this layer.' },
    ],
    lld: `flowchart LR
  subgraph repo[QdrantRepo]
    Search[search by tenant_id, query_vec]
    Upsert[upsert by tenant_id, points]
    Embed[embed_version stamping]
  end
  subgraph qc[Qdrant client]
    GRPC[gRPC channel]
    POOL[Connection pool]
  end
  subgraph cluster[Qdrant cluster]
    SHARD0[Shard 0]
    SHARD1[Shard 1]
    REPL[Replicas]
  end
  Search --> GRPC
  Upsert --> GRPC
  GRPC --> POOL
  POOL --> SHARD0
  POOL --> SHARD1
  SHARD0 -.->|replicate| REPL`,
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
    implementationSteps: [
      { step: '1', logic: 'Provision Qdrant cluster (self-hosted or managed) with 3+ replicas. Configure scalar quantization on collection creation.' },
      { step: '2', logic: 'Create collection with HNSW config (M=16, ef_construct=200) and payload schema (tenant_id keyword + doc_id keyword).' },
      { step: '3', logic: 'Wrap Qdrant client in QdrantRepo class — every method takes tenant_id as required parameter; no raw search exposed.' },
      { step: '4', logic: 'On ingestion: chunk → embed → upsert to Qdrant with payload (tenant_id, doc_id, chunk_id, embedding_model, embedding_version).' },
      { step: '5', logic: 'On query: embed query → QdrantRepo.search(tenant_id, vector) → top-20 → cross-encoder rerank → top-5.' },
      { step: '6', logic: 'For embedding model upgrade: create shadow collection → re-embed corpus in background → run eval → flip alias if recall holds → drop old.' },
      { step: '7', logic: 'Drill: write under tenant A, search under tenant B → assert empty (real Qdrant, not mock).' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/qdrant_repo.py
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

class QdrantRepo:
    """Tenant-scoped vector ops. tenant_id is REQUIRED; there is no
    path to query Qdrant without it from this layer."""
    def __init__(self, client: AsyncQdrantClient, collection: str):
        self._c = client
        self._coll = collection

    async def search(self, tenant_id: str, vector: list[float], top_k: int = 20):
        return await self._c.search(
            collection_name=self._coll,
            query_vector=vector,
            query_filter=Filter(
                must=[FieldCondition(
                    key="tenant_id",
                    match=MatchValue(value=tenant_id),
                )]
            ),
            limit=top_k,
        )

    async def upsert(self, tenant_id: str, points: list):
        # Caller passes points already stamped with tenant_id payload.
        # Defensive: verify here too.
        for p in points:
            if p.payload.get("tenant_id") != tenant_id:
                raise ValueError(f"point tenant_id mismatch: {p.id}")
        return await self._c.upsert(self._coll, points)
`,
    },
    realUseCase: 'Tenant A uploads a confidential PDF. Chunks are embedded with text-embedding-ada-002 v2, stamped with embedding_version=v2 + tenant_id=A, upserted to the shared collection. Six months later, we upgrade to text-embedding-3-large. Without shadow-collection discipline, the cluster is half v2 / half v3 — recall collapses. With shadow: build new collection, re-embed corpus (~6 GPU-hours), eval against benchmark, flip alias, drop v2. Zero downtime, recall preserved.',
    prosCons: {
      pros: [
        'Sub-100ms ANN at 100M+ vector scale',
        'Native payload filter — tenant_id enforced at query time',
        'Self-hostable; no vendor lock-in',
        'Scalar/binary quantization — 4-32x memory reduction',
        'Collection alias — zero-downtime model upgrade',
        'gRPC + REST clients in every major language',
      ],
      cons: [
        'Not a database — no ACID, no joins',
        'Index rebuild on quantization config change',
        'HNSW recall depends on ef_search — needs tuning',
        'Per-tenant collection at high tenant count = operational pain',
        'Memory cost grows linearly with vector count',
      ],
    },
    comparison: {
      left: 'Qdrant',
      right: 'pgvector',
      rows: [
        { aspect: 'Query latency p99 at 1M vectors', left: '~50ms', right: '~200ms (sequential scan possible)' },
        { aspect: 'Index rebuild', left: 'Live; no write block', right: 'Locks writes for minutes' },
        { aspect: 'Scaling cost', left: 'Higher (separate cluster)', right: 'Lower (Postgres extension)' },
        { aspect: 'Operational simplicity', left: 'One more service to operate', right: 'Same Postgres you already run' },
        { aspect: 'Tenant filter', left: 'Native payload filter', right: 'WHERE clause (easy to forget)' },
        { aspect: 'When to pick', left: '≥ 100K chunks/tenant, p99 < 100ms required', right: '< 100K chunks/tenant, ACID semantics' },
      ],
    },
    solutions: [
      { problem: 'Search returns wrong tenant\'s chunk', solution: 'QdrantRepo enforces filter; drill_retrieval_tenant_isolation runs in CI' },
      { problem: 'Recall drops after embedding model change', solution: 'Shadow-collection pattern + eval gate + alias flip; never re-embed in place' },
      { problem: 'p99 latency spikes', solution: 'Profile ef_search per query; tune; consider per-tenant collection for biggest tenants' },
      { problem: 'Memory pressure on cluster', solution: 'Enable scalar quantization; alternatively binary for ultra-high-volume cold corpora' },
      { problem: 'Duplicate content floods retrieval', solution: 'Dedupe by content_hash on ingest; one chunk = one point' },
    ],
    bestPractices: {
      do: [
        'tenant_id as required parameter in QdrantRepo signature',
        'Stamp embedding_model + embedding_version on every point',
        'Use collection alias for zero-downtime upgrades',
        'Index payload fields used in filters (tenant_id, doc_id)',
        'Real-Qdrant integration tests for tenant isolation',
      ],
      avoid: [
        'Raw qdrant_client outside QdrantRepo',
        'In-place re-embedding (always shadow + alias flip)',
        'Sequential search without filter (forget tenant_id = leak)',
        'Mixing embedding model versions in one collection',
        'Per-tenant collection without operational tooling',
      ],
      optimize: [
        'ef_search tuning per workload (recall vs latency curve)',
        'Scalar quantization for warm corpora; binary for cold',
        'Per-tenant collection only for top 1% by query volume',
        'Cross-encoder rerank top-20 → top-5 (cuts LLM tokens 4x)',
        'Cache top-N retrieval results in Redis for repeat queries',
      ],
    },
    antiPatterns: [
      'Treating Qdrant as a database — it has no ACID, no joins',
      'Skipping the payload filter "just for one debug query" — leaks',
      'In-place embedding model swap — destroys recall',
      'One collection per tenant for 1000+ tenants — operational nightmare',
      'Forgetting embedding_version on points — upgrade becomes impossible',
      'Storing ground-truth (e.g., user PII) in payload — wrong store',
    ],
    testTypes: [
      'Unit (QdrantRepo method shape, mocked client)',
      'Integration against real Qdrant (tenant isolation)',
      'Drill — multi-tenant write/read with negative assertion',
      'Eval — Recall@K against benchmark dataset',
      'Performance — concurrent search load test',
    ],
    testScenarios: [
      { scenario: 'Write under tenant A; search under tenant B', expected: 'Zero results returned' },
      { scenario: 'Search without tenant_id parameter (call repo)', expected: 'TypeError at function signature' },
      { scenario: 'Upsert point with mismatched tenant_id payload', expected: 'ValueError raised by repo' },
      { scenario: 'ef_search=500 vs 100', expected: 'Higher recall (~+2%), higher latency (~+30ms)' },
      { scenario: 'Embedding model bump without shadow', expected: 'Recall collapses on benchmark — caught by eval gate' },
      { scenario: 'Drop collection + recreate', expected: 'Service degraded; transport breaker opens; alert fires' },
    ],
    testData: [
      { type: 'Valid', example: 'point: {id: UUID, vector: [768 floats], payload: {tenant_id: UUID-A, doc_id: D1, embedding_version: v2}}' },
      { type: 'Cross-tenant', example: 'tenant A points + tenant B query → empty result set' },
      { type: 'Boundary', example: '10K vectors per upsert batch (max throughput)' },
      { type: 'Extreme', example: '50 concurrent searches, p99 < 100ms target' },
      { type: 'Invalid', example: 'vector dim mismatch (got 512, collection expects 768) → 400 from cluster' },
    ],
    debuggingChecklist: [
      'Is tenant_id passed in the search call? (grep callsite for QdrantRepo.search)',
      'Is the collection name correct? (vs alias, vs old shadow)',
      'Is embedding_model_version in payload matching query embedder?',
      'Is ef_search default appropriate for this workload? (try doubling)',
      'Is HNSW index complete? (status endpoint should report green)',
      'Is the transport breaker state closed? (/health/upstreams)',
      'Are points stamped with current embedding_version?',
    ],
    productionIssues: [
      { issue: 'Recall drops after deploy', rootCause: 'New embedding model deployed without shadow-collection — old vectors incomparable' },
      { issue: 'p99 latency 3x higher overnight', rootCause: 'ef_search default raised "for better recall"; no perf test before deploy' },
      { issue: 'Memory OOM on Qdrant pod', rootCause: 'Scalar quantization disabled "for accuracy"; vector count crossed RAM limit' },
      { issue: 'Cross-tenant chunk visible in admin UI', rootCause: 'Admin endpoint used raw qdrant_client outside repo; bypassed payload filter' },
      { issue: 'Silent ingestion drift', rootCause: 'embedding_model upgrade rolled out without re-embedding existing corpus; results mixed' },
    ],
    performance: [
      'p50 search latency < 30ms target on indexed payload filters',
      'p99 search < 100ms with ef_search=100 default',
      'Throughput: 1000 QPS per Qdrant pod (3-replica cluster)',
      'Memory: 4 GB per million vectors with scalar quantization',
      'Cross-encoder rerank adds ~50ms; only on top-20 → top-5',
    ],
    costConsiderations: [
      'Memory dominates — scalar quantization is non-optional at scale',
      'Per-tenant collection has fixed memory overhead (HNSW per coll)',
      'Re-embed cost on model upgrade: ~$0.10/1K chunks for cloud embedders',
      'Network egress for cross-region replication',
      'Cross-encoder rerank GPU/CPU cost vs LLM token savings tradeoff',
    ],
    observability: [
      'Metrics: per-collection p50/p95/p99 query latency, QPS, memory growth',
      'Recall@K from eval-svc — alert on > 5% drop',
      'Transport breaker state for Qdrant — alert on open events',
      'HNSW index size + indexing lag',
      'Per-tenant query rate (top-N tenants by volume)',
      'Trace span attribute db.qdrant.tenant_id on every search',
    ],
    metrics: [
      { name: 'qdrant_p99_latency_ms', example: '< 100ms; alert > 200ms' },
      { name: 'qdrant_recall_at_k', example: 'Eval-svc reports per benchmark; alert > 5% drop' },
      { name: 'qdrant_memory_gb', example: 'Track growth; alert at 80% pod limit' },
      { name: 'qdrant_breaker_state', example: 'closed expected; open events page on-call' },
      { name: 'qdrant_query_rate_per_tenant', example: 'Top-10 tenants reviewed weekly' },
    ],
    tradeoffs: [
      { decision: 'Qdrant vs pgvector', tradeoff: 'Performance + operational footprint vs single-store simplicity' },
      { decision: 'Per-tenant collection vs payload filter', tradeoff: 'Physical isolation vs operational complexity at high tenant count' },
      { decision: 'Scalar vs binary quantization', tradeoff: 'Recall vs memory (binary 32x reduction, 5-10% recall loss)' },
      { decision: 'Cross-encoder rerank vs raw top-K', tradeoff: 'Quality vs latency + cost' },
      { decision: 'Shadow collection vs in-place re-embed', tradeoff: 'Zero downtime + double storage during migration vs simpler ops + downtime risk' },
    ],
    decisionMatrix: [
      { option: 'Qdrant + scalar quant + payload filter', whenToUse: 'Default for ≥ 100K chunks/tenant, ≤ 1000 tenants total' },
      { option: 'Qdrant + per-tenant collection', whenToUse: 'Top 1% tenants by volume OR regulated customers requiring physical isolation' },
      { option: 'pgvector', whenToUse: '< 100K chunks/tenant; ACID semantics needed; ops simplicity > p99 perf' },
      { option: 'Pinecone (managed)', whenToUse: 'Pre-Series-A; zero-ops priority; willing to take vendor lock-in' },
      { option: 'Weaviate', whenToUse: 'Multi-modal corpora; built-in modules for hybrid' },
      { option: 'Milvus', whenToUse: 'Billions of vectors; willing to absorb operational complexity' },
    ],
    starStory: {
      situation: 'Recall on the prod RAG benchmark dropped 18% overnight after a quiet deploy. Customer complaints about "wrong answers" started 36 hours later.',
      task: 'Find the cause, restore recall, ship a regression-prevention discipline.',
      action: 'Pulled deploy diff: a "small" upgrade from text-embedding-ada-002 v1 to v2 was rolled out without re-embedding the existing corpus. New queries embedded with v2; existing vectors stamped v1. Recall collapsed because the embedding spaces are not comparable. Recovery: rolled back to v1 embedder, then implemented shadow-collection pattern with eval gate. drill_embedding_version_coupling now runs in CI: an upsert with mismatched embedding_version vs collection metadata is rejected.',
      result: 'Zero recall regressions in the year since. Two more upgrade attempts were blocked by the drill before reaching prod (one was a similar oversight, one was an actual model bug caught by eval gate). The shadow-collection runbook is now standard for every embedder swap.',
    },
    interviewTraps: [
      'Calling Qdrant a "database" — it\'s a search engine; conflating loses you credibility',
      'Skipping the embedding-version field — upgrade becomes impossible after a year',
      'Saying "we tested with mocks" for tenant isolation — only real cluster catches the leak',
      'Per-tenant-collection-for-everyone — doesn\'t scale operationally past ~100 tenants',
      'Ignoring the rerank step — top-K alone gives noisy LLM context',
      'Treating quantization as a free win — 5-10% recall loss matters for some use cases',
    ],
    finalScript: 'Qdrant is our semantic retrieval accelerator — not a database. We use HNSW for sub-linear ANN, scalar quantization for 4x memory reduction, and a mandatory tenant_id payload filter so cross-tenant leak is structurally impossible. The QdrantRepo wrapper has tenant_id as a required parameter — no raw client outside that layer. Embedding model upgrades use a shadow-collection pattern: build new collection, run eval gate, flip alias if recall holds, drop the old. Top-20 ANN results go through a cross-encoder rerank to top-5 before reaching the LLM — cuts token cost 4x. The non-negotiable test is drill_retrieval_tenant_isolation against the live cluster: write under tenant A, query under tenant B, assert zero results. Mocks lie about isolation; only real Qdrant enforces the filter.',
    interviewLine: 'Vector DB is a retrieval accelerator, not a transactional source of truth. The hardest discipline is embedding/index version coupling — silent drift here destroys recall.',
  },

  // ---- 3. Redis ----
  {
    slug: 'redis',
    title: '3. Redis — cache + transient state',
    status: 'shipped',
    coreConcept: 'Low-latency temporary store for hot data, throttling state, and short-lived coordination — every entry needs a correctness story (tenant key, TTL, invalidation).',
    oneLiner: 'Redis = microsecond reads + atomic ops; every entry needs tenant key + TTL + invalidation rule, or it is a correctness bug.',
    businessContext: 'Repeated DB reads on hot data dominate p95 latency and cost. Distributed locks, rate limits, and idempotency keys need a fast cross-process store. Postgres alone cannot serve those at the latency budget.',
    fiveW: {
      what: 'In-memory key-value store with rich data structures (hash, list, sorted set, streams), atomic ops (Lua, MULTI/EXEC), pub/sub, and TTL-driven eviction.',
      why: 'Microsecond reads (vs millisecond DB). Native primitives for the patterns we keep needing — cache, rate-limit, distributed lock, idempotency. Cheap to operate.',
      where: 'cache layer in retrieval-svc; rate-limit counters in api-gateway; idempotency store in governance-svc; session/refresh-token store in identity-svc.',
      when: 'Hot data with high read ratio + tolerable staleness; cross-process coordination needs; ephemeral state that should not pollute Postgres.',
      who: 'Platform team owns Redis cluster. Each service team owns its key namespace + invalidation policy.',
    },
    interview30s: 'Redis is the cache + ephemeral coordination layer. Three non-negotiable disciplines: tenant-prefixed keys (no shared namespace), explicit TTL on every write (no eternal entries), and a documented invalidation rule per key family (otherwise stale wins). Rate limits, distributed locks, idempotency keys all live here. The drill that gates this is cross-tenant — query tenant A under tenant B context returns cache miss, never a hit.',
    coreBuildingBlocks: [
      'Cluster — 3+ replicas, AOF persistence, ACL-controlled',
      'Cache.tenant_key(t, k) — every API call requires tenant_id',
      'TTL discipline — every SET has an EX expiry; no eternal keys',
      'Invalidation events — Kafka topic emits doc.updated → cache.invalidate',
      'Distributed lock — SET NX EX with random token + Lua release',
      'Rate limiter — sliding-window via sorted set OR token bucket via hash',
      'Idempotency store — keyed by (tenant, X-Idempotency-Key), 24h TTL',
    ],
    architectureRelevance: {
      backend: 'RedisRepo wraps every op. tenant_id + key + TTL required at the API boundary.',
      rag: 'Cache top-N retrieval results by (tenant, query_hash). Hit rate 30-60% on repeated FAQ queries.',
      ai: 'Token CB tracks running token usage per tenant per minute via Redis sorted set sliding window.',
      microservices: 'gateway uses Redis for per-IP + per-tenant rate limits. governance-svc uses Redis for idempotency replay.',
    },
    hld: `flowchart TB
  subgraph svcs[Services]
    GW[api-gateway]
    INF[inference-svc]
    RET[retrieval-svc]
    GOV[governance-svc]
    ID[identity-svc]
  end
  subgraph rd[Redis cluster]
    PRIMARY[("Primary node")]
    REP1[("Replica 1")]
    REP2[("Replica 2")]
    AOF[("AOF persistence")]
  end
  GW -->|rate-limit counters| PRIMARY
  INF -->|cache top-K retrieval| PRIMARY
  RET -->|cache chunk lookup| PRIMARY
  GOV -->|idempotency keys| PRIMARY
  ID -->|refresh tokens + sessions| PRIMARY
  PRIMARY -.->|replicate| REP1
  PRIMARY -.->|replicate| REP2
  PRIMARY -.->|fsync| AOF`,
    networkFlow: `flowchart LR
  C[Client] --> AGW["api-gateway"]
  AGW -->|GET tenant:T:rate:ip:I| RD[(Redis)]
  AGW -->|HTTPS X-Tenant-ID| RET[retrieval-svc]
  RET -->|GET tenant:T:cache:Q| RD
  RET -->|MISS - then SETEX| RD
  RD -.->|invalidate event| RET`,
    flowchart: `flowchart LR
  Q[Request + tenant + key] --> R[Cache.tenant_key]
  R --> G{Cache hit}
  G -->|yes| C[Return cached]
  G -->|no| F[Fetch from source]
  F --> S[SETEX with TTL]
  S --> O[Return value]
  E[Source change event] --> I[Invalidate matching keys]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Svc as Service
  participant R as Redis
  participant DB as Postgres
  U->>Svc: GET docs by id
  Svc->>R: GET tenant:T:doc:id
  R-->>Svc: nil
  Svc->>DB: SELECT FROM docs WHERE id = X
  DB-->>Svc: row
  Svc->>R: SETEX tenant:T:doc:id 300 row
  Svc-->>U: doc
  Note over Svc,R: Next request hits cache and saves a DB round-trip`,
    coreLayers: [
      { layer: 'Cluster', responsibility: '3+ replicas, AOF persistence, ACL roles per service. Sentinel or Redis Cluster for HA.' },
      { layer: 'Key namespace', responsibility: 'Every key prefixed tenant:<id>:<feature>:<key>. Cross-tenant collision impossible by design.' },
      { layer: 'TTL discipline', responsibility: 'Every SET has explicit EX. Default TTL configured per feature (cache=300, idempotency=86400).' },
      { layer: 'Invalidation', responsibility: 'Source-change events → consumer → DEL matching keys. Document rule per key family.' },
      { layer: 'Repository', responsibility: 'RedisRepo / Cache class. tenant_id + key + value + TTL required. No raw client outside.' },
      { layer: 'Lock layer', responsibility: 'SET NX EX <token>; Lua-released. Bounded TTL prevents stuck locks.' },
      { layer: 'Rate limiter', responsibility: 'Sorted-set sliding window OR hash token bucket. Atomic via Lua or MULTI.' },
    ],
    lld: `flowchart LR
  subgraph repo[Cache repo]
    GET[get tenant + key]
    SET[setex tenant + key + ttl]
    INV[invalidate tenant + pattern]
  end
  subgraph cli[Redis client]
    POOL[Connection pool]
    LUA[Lua scripts cached]
  end
  subgraph rd[Redis]
    P[Primary]
    REP[Replicas]
  end
  GET --> POOL
  SET --> POOL
  INV --> POOL
  POOL --> P
  P -.-> REP`,
    problem: 'Repeated reads or transient coordination should not always hit the primary store; some operations need cross-process state without DB round-trips.',
    whyThisApproach: 'Redis gives microsecond reads, native data structures, atomic operations, and TTL eviction — enough for cache, rate limiting, distributed locks, and ephemeral session state without polluting Postgres.',
    whenToUse: [
      'Hot read cache (read-through with TTL)',
      'Rate-limit counters (sliding window, token bucket)',
      'Distributed locks for short critical sections',
      'Idempotency key store (24h TTL)',
      'Session + refresh token store',
      'Pub/sub between services (low durability)',
    ],
    whenNotToUse: [
      'Source of truth for domain data → Postgres',
      'Long-term storage → Postgres or object storage',
      'Strong durability requirement → Kafka with disk replication',
      'Complex relational queries → Postgres',
      'Multi-tenant cache without tenant prefix → cross-leak risk',
    ],
    input: 'Tenant-prefixed key + value (with TTL on writes); tenant_id required at every API call',
    process: [
      'Build key via Cache.tenant_key(t, k)',
      'GET — return value if hit, else fall through',
      'On miss: fetch from source; SETEX with TTL',
      'On source-change event: DEL matching keys (or pattern)',
      'For locks: SET NX EX with random token; release via Lua match',
      'For rate limits: ZADD or HINCRBY with current timestamp',
    ],
    output: 'Cached value (microsecond) OR miss path. Lock token / counter result.',
    implementationSteps: [
      { step: '1', logic: 'Provision Redis cluster (3+ replicas, AOF persistence) with ACLs per service.' },
      { step: '2', logic: 'Wrap client in RedisRepo / Cache class. tenant_id required at every call signature.' },
      { step: '3', logic: 'Define key conventions: tenant:<id>:<feature>:<key>. Document per-feature TTL.' },
      { step: '4', logic: 'Wire source-change events (Kafka) to invalidation consumer; DEL matching keys on update.' },
      { step: '5', logic: 'For locks: SET NX EX <token>; release with Lua atomic compare.' },
      { step: '6', logic: 'For rate limits: sorted set sliding window OR hash token bucket; Lua atomic update.' },
      { step: '7', logic: 'For idempotency: SETEX (tenant, idem-key) → response 24h.' },
      { step: '8', logic: 'Drill: cross-tenant query under wrong tenant context returns nil, never hit.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/cache.py
from typing import Optional
import redis.asyncio as aioredis

class Cache:
    """Tenant-scoped cache. tenant_id is REQUIRED on every operation."""
    def __init__(self, client: aioredis.Redis, default_ttl: int = 300):
        self._c = client
        self._default_ttl = default_ttl

    @staticmethod
    def tenant_key(tenant_id: str, key: str) -> str:
        if not tenant_id:
            raise ValueError("tenant_id required")
        return f"tenant:{tenant_id}:{key}"

    async def get(self, tenant_id: str, key: str) -> Optional[bytes]:
        return await self._c.get(self.tenant_key(tenant_id, key))

    async def set_with_ttl(self, tenant_id: str, key: str, value: bytes, ttl: Optional[int] = None) -> None:
        ttl = ttl or self._default_ttl
        await self._c.set(self.tenant_key(tenant_id, key), value, ex=ttl)

    async def invalidate(self, tenant_id: str, pattern: str) -> int:
        # Use SCAN, not KEYS — KEYS blocks the server.
        deleted = 0
        async for k in self._c.scan_iter(match=self.tenant_key(tenant_id, pattern)):
            await self._c.delete(k)
            deleted += 1
        return deleted`,
    },
    realUseCase: 'A user asks the same question twice in a 5-minute window. First call: retrieval-svc embeds, hits Qdrant, runs rerank, costs 80ms + tokens. Cache hit on second call: retrieval-svc reads tenant:T:rag:hash → instant return, 0 token cost. Hit rate on the FAQ workload runs 30-60%. Without tenant prefix, tenant B could see tenant A\'s cached chunks — drill catches.',
    prosCons: {
      pros: [
        'Microsecond reads (vs ~5-50ms Postgres)',
        'Rich primitives: hash, sorted set, streams, pub/sub',
        'Atomic ops via Lua + MULTI',
        'TTL eviction is built-in (no cleanup job)',
        'Cheap to operate at small scale',
      ],
      cons: [
        'Memory-bound; data must fit in RAM',
        'Persistence (AOF) is best-effort, not transactional',
        'Multi-key transactions only same-slot in cluster',
        'Cross-tenant leak if key prefix forgotten',
        'TTL drift if invalidation not wired',
      ],
    },
    comparison: {
      left: 'Redis',
      right: 'Postgres (UNLOGGED table)',
      rows: [
        { aspect: 'Read latency', left: '~0.1-1ms (microseconds)', right: '~5-50ms' },
        { aspect: 'Built-in TTL', left: 'Yes; per-key', right: 'No; cleanup job needed' },
        { aspect: 'Atomic ops', left: 'Lua + MULTI/EXEC', right: 'Transactions; complex' },
        { aspect: 'Pub/sub', left: 'Native', right: 'LISTEN/NOTIFY (limited)' },
        { aspect: 'Durability', left: 'Best-effort AOF; not ACID', right: 'ACID' },
        { aspect: 'When to pick', left: 'Hot cache, rate-limit, locks, idempotency', right: 'Audit truth, cross-process queue (sometimes)' },
      ],
    },
    solutions: [
      { problem: 'Cache stale after document update', solution: 'Document.updated event → consumer DEL pattern; document the rule per key family' },
      { problem: 'Cross-tenant cache leak', solution: 'Cache.tenant_key enforced; drill cross-tenant under wrong context returns nil' },
      { problem: 'Rate-limit race condition', solution: 'Lua-script atomic increment + check; never read-modify-write' },
      { problem: 'Distributed lock stuck (process died)', solution: 'TTL on lock + random token; periodic Lua-released' },
      { problem: 'Memory pressure', solution: 'maxmemory-policy=allkeys-lru; alert before eviction; TTL discipline' },
    ],
    bestPractices: {
      do: [
        'Tenant-prefix every key (Cache.tenant_key)',
        'Explicit TTL on every SET (default per feature)',
        'Document the invalidation rule per key family',
        'SCAN, not KEYS, in production',
        'Lua scripts for atomic multi-step ops',
        'Set maxmemory-policy and alert before eviction',
      ],
      avoid: [
        'KEYS in production (blocks server)',
        'Eternal keys (no TTL)',
        'Cross-tenant key collisions (raw key API)',
        'Read-modify-write without WATCH or Lua',
        'Multi-key transactions across cluster slots',
        'Persistent state in Redis (use Postgres)',
      ],
      optimize: [
        'Pipeline batch reads for cache fan-out',
        'Cache compression for large values (msgpack)',
        'Local LRU layer in front of Redis for ultra-hot keys',
        'Separate cluster per workload (cache vs rate-limit vs sessions)',
        'Read replicas for read-heavy workloads',
      ],
    },
    antiPatterns: [
      'KEYS pattern in production — blocks the server',
      'Storing large objects without TTL — memory leak',
      'Treating Redis as durable — AOF is best-effort, not ACID',
      'Cross-tenant raw keys — leak waiting to happen',
      'Multi-key transactions across cluster slots — fails on cluster',
      'Stale cache without invalidation rule — wrong data wins',
    ],
    testTypes: [
      'Unit (Cache method shape)',
      'Integration against real Redis',
      'Drill — cross-tenant cache returns nil',
      'Drill — TTL expires entries',
      'Performance — pipeline burst test',
      'Failure — Redis down → fallback to source',
    ],
    testScenarios: [
      { scenario: 'SET tenant A, GET tenant B', expected: 'nil (cache miss)' },
      { scenario: 'SET with EX=2, wait 3s, GET', expected: 'nil (expired)' },
      { scenario: 'Distributed lock acquire + release', expected: 'NX returns OK once; second NX blocked' },
      { scenario: 'Source-change event fires', expected: 'Matching keys DEL\'d within 100ms' },
      { scenario: 'Redis pod down', expected: 'Service falls back to Postgres; degraded=True' },
    ],
    testData: [
      { type: 'Valid', example: 'tenant:UUID-A:doc:D1 → JSON blob (1KB)' },
      { type: 'Cross-tenant', example: 'tenant:UUID-A key + tenant_id=UUID-B query → nil' },
      { type: 'Boundary', example: '1MB value with msgpack compression' },
      { type: 'Extreme', example: '10K SETEX/sec sustained for 60s' },
      { type: 'Invalid', example: 'tenant_id="" → ValueError raised by Cache' },
    ],
    debuggingChecklist: [
      'Is the key tenant-prefixed? (KEYS pattern in dev, SCAN in prod)',
      'Does the TTL match the documented value? (TTL command)',
      'Is the cluster slot routing the key correctly? (CLUSTER KEYSLOT)',
      'Is AOF persistence enabled? (CONFIG GET appendonly)',
      'Is maxmemory-policy set? (CONFIG GET maxmemory-policy)',
      'Are invalidation events being consumed? (Kafka consumer lag)',
      'Is the connection pool exhausted? (CLIENT LIST)',
    ],
    productionIssues: [
      { issue: 'Cross-tenant chunk visible in retrieval', rootCause: 'New service path used raw client, bypassed Cache.tenant_key' },
      { issue: 'p99 latency spike during deploy', rootCause: 'Cache cold-start; no warmup; 100% miss for 30s' },
      { issue: 'Memory OOM at 80% load', rootCause: 'maxmemory-policy=noeviction; should be allkeys-lru' },
      { issue: 'Distributed lock stuck for 10min', rootCause: 'No TTL on lock; process died; no auto-release' },
      { issue: 'Rate limiter under-counting', rootCause: 'Read-modify-write race; should be Lua-atomic' },
    ],
    performance: [
      'p50 GET < 1ms; p99 < 5ms target',
      'Throughput: 100K ops/sec per pod',
      'Memory: 1 GB per million typical small keys',
      'Pipeline: batch 100 ops per round-trip',
      'AOF fsync mode: every-second (not always)',
    ],
    costConsiderations: [
      'Memory dominates (RAM is expensive at scale)',
      'Replicas double memory cost',
      'Operational overhead for sharded cluster',
      'Network egress for cross-region replication',
    ],
    observability: [
      'Per-key-family hit rate',
      'Memory growth + eviction rate',
      'p99 GET/SET latency',
      'Connection pool wait time',
      'Replication lag',
      'AOF fsync stalls',
    ],
    metrics: [
      { name: 'redis_hit_rate_percent', example: '> 30% target on cache workloads' },
      { name: 'redis_p99_latency_ms', example: '< 5ms; alert > 20ms' },
      { name: 'redis_memory_used_bytes', example: '< 80% of maxmemory' },
      { name: 'redis_evicted_keys_total', example: '0 expected; alert on rise' },
      { name: 'redis_connection_wait_ms', example: '< 5ms p95' },
    ],
    failureModes: [
      { mode: 'Single transport CB stuck open', detect: 'breaker_state per transport', recover: 'Manual probe; investigate dep' },
      { mode: 'Score fusion bias', detect: 'eval-svc retrieval scores skew', recover: 'Re-tune RRF weights' },
      { mode: 'Cache poisoning', detect: 'Cross-tenant retrieval anomaly', recover: 'Tenant key prefix; flush' },
      { mode: 'Memory eviction storms', detect: 'evicted_keys_total spike', recover: 'Tune TTL; scale memory; review key bloat' },
    ],
    tradeoffs: [
      { decision: 'Redis vs Postgres UNLOGGED', tradeoff: 'Latency + primitives vs durability' },
      { decision: 'AOF every-second vs always', tradeoff: 'Throughput vs durability (1s data loss window)' },
      { decision: 'Single instance vs Cluster', tradeoff: 'Operational simplicity vs multi-key transaction limits' },
      { decision: 'Per-tenant cache vs shared with prefix', tradeoff: 'Memory isolation vs ops simplicity' },
      { decision: 'Local LRU + Redis vs Redis only', tradeoff: 'Latency vs cache coherency' },
    ],
    decisionMatrix: [
      { option: 'Redis cluster (default)', whenToUse: 'Cache + rate-limit + idempotency + locks; multi-tenant; ≤ 1TB hot data' },
      { option: 'Redis Sentinel (HA single primary)', whenToUse: '≤ 100GB; multi-key transactions matter' },
      { option: 'KeyDB / Dragonfly', whenToUse: 'Drop-in faster Redis; willing to use newer ecosystem' },
      { option: 'Memcached', whenToUse: 'Pure cache; no rich primitives needed; older infra' },
      { option: 'Postgres UNLOGGED', whenToUse: '< 1k ops/sec; want one fewer service' },
    ],
    starStory: {
      situation: 'During a deploy, retrieval-svc latency p99 spiked from 80ms to 1.2s for 30 seconds. User complaints came within minutes.',
      task: 'Find root cause; restore latency; prevent recurrence.',
      action: 'Pulled metrics: cache hit rate dropped from 45% to 0% during the deploy window. Root cause: container rotation flushed in-process cache; Redis was up but the serve-time warmup wasn\'t triggered; 100% requests went straight to Qdrant + rerank. Fix: added a warmup hook in the deploy pipeline that pre-populates top-N cached queries before traffic switch. Drill: deploy with warmup disabled → expect p99 spike alert.',
      result: 'Zero deploy-related latency spikes in the year since. Warmup discipline now standard for every cache-dependent service. The drill catches it if anyone removes the warmup hook.',
    },
    interviewTraps: [
      'Calling Redis a "database" — it\'s a cache + ephemeral primitives store; conflating loses credibility',
      'Skipping the tenant prefix "just for one debug query" — leak risk',
      'Treating AOF as ACID — it\'s best-effort durability with a 1s window',
      'Using KEYS in production — blocks the server',
      'Storing large blobs without TTL — memory leak',
      'Forgetting Lua-atomic for read-modify-write — race conditions silent',
    ],
    finalScript: 'Redis is the cache plus ephemeral coordination layer in this stack. Three non-negotiable disciplines. First, tenant-prefixed keys via Cache.tenant_key — every API call requires tenant_id; cross-tenant leak is structurally impossible. Second, explicit TTL on every SET — no eternal keys; default per feature, 300 seconds for cache, 24 hours for idempotency. Third, a documented invalidation rule per key family — source-change events fire DEL on matching keys via Kafka consumer. We use it for cache, rate-limit counters, distributed locks, idempotency keys, and refresh tokens. Operational discipline: SCAN not KEYS, Lua scripts for atomic multi-step ops, maxmemory-policy=allkeys-lru, alert on eviction. The drill that gates this is cross-tenant — write under tenant A, read under tenant B context returns nil, never a hit.',
    interviewLine: 'Redis improves latency, but every cache entry needs a correctness story: tenant keying, TTL, and invalidation. Without those, cache is a correctness bug waiting to happen.',
    monitoring: [
      'Hit ratio per pattern (cache_hits / cache_misses)',
      'Memory used / max',
      'evicted_keys counter',
      'Connected clients',
      'p99 GET/SET latency',
    ],
    alternatives: [
      { name: 'In-memory dict', tradeoff: 'Process-local; lost on restart; not shared across replicas' },
      { name: 'Memcached', tradeoff: 'Simpler; no data structures; no persistence' },
      { name: 'KeyDB / Dragonfly', tradeoff: 'Multi-threaded Redis fork; same API; newer ecosystem' },
      { name: 'Hazelcast', tradeoff: 'In-memory data grid; JVM-centric; heavier' },
    ],
    challenges: [
      'Stale data — cache is not source of truth',
      'Invalidation is hard',
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
      'libs/py/documind_core/cache.py — Cache class with tenant_id required',
      'instrument_redis OTel auto-instrumentation in inference-svc + retrieval-svc',
      'redis_url config in BaseServiceSettings',
      'RateLimitMiddleware uses Redis sliding window',
      'mcp/tests/drill_cache_tenant_isolation.py',
    ],
  },

  // ---- 4. Kafka ----
  {
    slug: 'kafka',
    title: '4. Kafka — durable event transport',
    status: 'shipped',
    coreConcept: 'Kafka decouples workflows from request paths via durable, append-only event logs — at the cost of pushing complexity into idempotency, lag, and schema discipline.',
    oneLiner: 'Kafka = durable + replayable event log; producing is easy, consuming SAFELY is the hard part.',
    businessContext: 'Synchronous HTTP couples lifetimes — a slow consumer takes the producer down. Audit fan-out, ingestion saga, cross-service notifications, replay-after-bug all need durable async transport. Direct HTTP cannot serve these patterns at the latency + reliability budget.',
    fiveW: {
      what: 'A distributed, partitioned, replicated commit log. Producers append; consumers read at their own pace; offsets track position. Configurable retention (hours / days / forever).',
      why: 'Decouples producer + consumer lifetimes. Replay survives consumer bugs. Per-partition ordering enables stateful processing. Proven at petabyte scale.',
      where: 'ingestion-svc emits document.uploaded; consumer chains parse → chunk → embed → index. governance-svc emits audit events. retrieval-svc emits cache.invalidate.',
      when: 'Async workflows; fan-out to N consumers; replay-after-bug-fix; high write rate with eventual consistency tolerance.',
      who: 'Platform team owns the Kafka cluster (or managed: MSK / Confluent Cloud). Each service team owns its topic schemas + consumer groups.',
    },
    interview30s: 'Kafka is the durable event-log backbone. Producers append to topics; consumers read at their own pace; offsets track position. Three non-negotiable disciplines: schema registry (topic schema versioned), idempotent consumers (de-dupe on event_id), and dead-letter queue with bounded retry. The hard part is not producing — it\'s consuming SAFELY: at-least-once delivery means duplicates; consumer crashes mean replays; schema drift breaks consumers silently. The drill is poison-message + replay: inject a malformed message, verify retry budget exhausts, message lands in DLQ, consumer keeps draining downstream.',
    coreBuildingBlocks: [
      'Cluster — 3+ brokers, replication factor 3, min.insync.replicas=2',
      'Topics — partitioned (parallelism unit), versioned schema',
      'Schema registry — Avro / Protobuf / JSON-schema; backward-compat enforced',
      'Producer — idempotent + transactional for exactly-once-write',
      'Consumer group — at-least-once delivery; idempotent handler',
      'Dead-letter queue — bounded retry then park for human review',
      'Outbox pattern — DB row + event in one transaction; relay publishes',
    ],
    architectureRelevance: {
      backend: 'Outbox pattern: write domain row + event row to Postgres in one transaction. Outbox relay reads + publishes to Kafka with at-least-once semantics.',
      rag: 'document.uploaded → ingestion saga (parse → chunk → embed → index → activate). Each stage is a separate consumer with its own retry policy.',
      ai: 'inference.completed → audit fan-out (decision audit + cost log + eval sample). One event, multiple independent consumers.',
      microservices: 'Per-service consumer groups. Decoupled deploy lifetimes. Replay topic from a known offset to recover from a consumer bug.',
    },
    hld: `flowchart TB
  subgraph svcs[Producers]
    ING[ingestion-svc]
    GOV[governance-svc]
    INF[inference-svc]
  end
  subgraph kafka[Kafka cluster]
    B1[("Broker 1")]
    B2[("Broker 2")]
    B3[("Broker 3")]
    SR[("Schema registry")]
  end
  subgraph cons[Consumer groups]
    PARSE[parse worker]
    EMBED[embed worker]
    INDEX[index worker]
    AUD[audit writer]
    EVAL[eval sampler]
  end
  subgraph dlq[DLQ]
    DLQ1[("docs-dlq")]
    DLQ2[("audit-dlq")]
  end
  ING -->|publish document.uploaded| B1
  GOV -->|publish audit events| B2
  INF -->|publish inference.completed| B3
  B1 -.->|replicate| B2
  B2 -.->|replicate| B3
  B1 --> PARSE
  PARSE --> EMBED
  EMBED --> INDEX
  B2 --> AUD
  B3 --> EVAL
  PARSE -.->|N retries fail| DLQ1
  AUD -.->|fail| DLQ2`,
    networkFlow: `flowchart LR
  P[Producer service] -->|publish + retry idempotent| K[(Kafka cluster)]
  K -->|partition assigned| C1[Consumer 1]
  K -->|partition assigned| C2[Consumer 2]
  C1 -->|commit offset| K
  C1 -->|N retries exhausted| DLQ[(DLQ topic)]
  K -.->|schema check| SR[Schema registry]`,
    flowchart: `flowchart LR
  E[Domain event] --> O[Outbox row in PG tx]
  O --> RL[Outbox relay]
  RL --> P[Publish to Kafka]
  P --> T[Topic partition]
  T --> CON[Consumer reads]
  CON --> H{Process side effect}
  H -->|success| OFF[Commit offset]
  H -->|fail| RT{Retry budget left}
  RT -->|yes| CON
  RT -->|no| DLQ[DLQ + alert]`,
    sequence: `sequenceDiagram
  autonumber
  participant Svc as Service
  participant DB as Postgres
  participant Out as Outbox relay
  participant K as Kafka
  participant Con as Consumer
  participant Side as Side effect target
  Svc->>DB: BEGIN then INSERT row plus INSERT outbox then COMMIT
  Out->>DB: poll outbox
  Out->>K: publish event
  Out->>DB: mark outbox sent
  Con->>K: poll partition
  Con->>Side: perform side effect
  Side-->>Con: ok or fail
  Con->>K: commit offset only on ok`,
    coreLayers: [
      { layer: 'Cluster', responsibility: '3+ brokers, RF=3, min.insync.replicas=2. Disk replication; survives node failure.' },
      { layer: 'Topic', responsibility: 'Partitioned for parallelism. Replication factor for durability. Retention per topic.' },
      { layer: 'Schema registry', responsibility: 'Avro / Protobuf / JSON-schema versions. Backward + forward compat enforced.' },
      { layer: 'Producer', responsibility: 'Idempotent + transactional for exactly-once-write semantics. Retries built-in.' },
      { layer: 'Consumer group', responsibility: 'Auto-rebalances partitions; at-least-once delivery; commit offset only after success.' },
      { layer: 'Idempotency', responsibility: 'event_id de-dupe in consumer. Every handler must be idempotent.' },
      { layer: 'DLQ', responsibility: 'Bounded retry (N attempts with backoff) then park in dead-letter topic for human review.' },
      { layer: 'Outbox pattern', responsibility: 'Write DB row + event row in one transaction; relay polls outbox + publishes; mark sent.' },
    ],
    lld: `flowchart LR
  subgraph repo[EventProducer + Consumer]
    PUB[publish event_id + payload]
    CON[consume + dedupe]
  end
  subgraph cli[Kafka client]
    PROD[Producer client]
    CONS[Consumer client]
    REB[Rebalance listener]
  end
  subgraph k[Kafka]
    LEAD[Leader replica]
    FOL[Follower replicas]
    OFF[Offset store]
  end
  PUB --> PROD
  PROD --> LEAD
  LEAD -.-> FOL
  CONS --> LEAD
  CONS --> OFF
  CON --> CONS`,
    problem: 'Some workflows shouldn\'t be synchronous: ingestion stages, audit fan-out, replay jobs, cross-service notifications. Direct HTTP couples lifetimes; events let consumers scale + replay independently.',
    whyThisApproach: 'Kafka gives durability (configurable replication), partition-ordered delivery, replay (log retention), and decoupled consumers — proven at scale.',
    whenToUse: [
      'Async workflows that survive consumer crashes',
      'Fan-out to N consumers with independent state',
      'Replay-after-bug-fix scenarios',
      'High write rate with eventual consistency tolerance',
      'Audit fan-out (one event → many consumers)',
      'Outbox pattern for transactional event publishing',
    ],
    whenNotToUse: [
      'Sync request/response (use HTTP)',
      'Strict ordering across partitions (only per-partition ordering)',
      'Tiny systems (operational overhead too high)',
      'Sub-millisecond latency requirements',
      'Very small messages at low rate (use Postgres LISTEN/NOTIFY)',
    ],
    input: 'Producer: domain event with event_id + tenant_id + payload + schema version. Consumer: partition assignment + offset.',
    process: [
      'Producer: serialize event with schema; publish to topic partition',
      'Outbox relay: poll outbox table; publish; mark sent',
      'Consumer: poll partition; deserialize; check event_id dedupe',
      'Process: invoke side effect; on success commit offset',
      'On failure: retry with exponential backoff up to N times',
      'On retry exhaustion: park in DLQ; alert; resume next message',
    ],
    output: 'Durable event in topic; consumer side effect applied; offset committed; audit row written.',
    implementationSteps: [
      { step: '1', logic: 'Provision Kafka cluster (3 brokers, RF=3, min.insync.replicas=2). Managed: MSK / Confluent Cloud.' },
      { step: '2', logic: 'Set up Schema Registry; enforce backward compat on schema changes.' },
      { step: '3', logic: 'Define topics with partition count = parallelism unit. Document retention per topic.' },
      { step: '4', logic: 'Wrap producer in EventProducer class — sets event_id, tenant_id, schema version automatically.' },
      { step: '5', logic: 'Wrap consumer in IdempotentConsumer — dedupes by event_id; commits offset only after success.' },
      { step: '6', logic: 'Implement outbox pattern: domain row + event row in one PG transaction; relay polls + publishes.' },
      { step: '7', logic: 'Add DLQ topic with bounded retry (3 attempts with exponential backoff).' },
      { step: '8', logic: 'Drill: poison message + replay → verify retry exhausts, message lands in DLQ, consumer drains downstream.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/kafka_client.py
from typing import Callable, Awaitable
import json, uuid
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

class EventProducer:
    """Stamps event_id + tenant_id + schema version on every publish."""
    def __init__(self, producer: AIOKafkaProducer, schema_version: str):
        self._p = producer
        self._sv = schema_version

    async def publish(self, topic: str, tenant_id: str, payload: dict) -> str:
        event_id = str(uuid.uuid4())
        msg = {
            "event_id": event_id,
            "tenant_id": tenant_id,
            "schema_version": self._sv,
            "payload": payload,
        }
        await self._p.send_and_wait(topic, json.dumps(msg).encode())
        return event_id

class IdempotentConsumer:
    """Dedupes by event_id; commits offset only after success."""
    def __init__(self, consumer: AIOKafkaConsumer, dlq_topic: str, max_retries: int = 3):
        self._c = consumer
        self._dlq = dlq_topic
        self._max = max_retries
        self._seen = set()  # in prod: Redis with TTL

    async def consume(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        async for msg in self._c:
            try:
                event = json.loads(msg.value)
                if event["event_id"] in self._seen:
                    continue  # already processed
                await handler(event["payload"])
                self._seen.add(event["event_id"])
                await self._c.commit()
            except Exception:
                # Retry with backoff; on exhaustion publish to DLQ
                pass`,
    },
    realUseCase: 'A user uploads a 50MB PDF. ingestion-svc returns 202 immediately and publishes document.uploaded to Kafka. Consumers chain: parse-worker extracts text → publishes document.parsed; chunk-worker chunks → publishes document.chunked; embed-worker embeds → publishes document.embedded; index-worker writes to Qdrant → publishes document.active. Each stage independently scaled, retryable, and replayable. If embed-worker has a bug, fix it + reset consumer group offset → corpus reprocesses without re-uploading.',
    prosCons: {
      pros: [
        'Durable + replayable (configurable retention)',
        'Decouples producer + consumer lifetimes',
        'Per-partition ordering enables stateful processing',
        'Fan-out: one event → many consumers',
        'Proven at petabyte scale',
        'Schema registry enforces compat',
      ],
      cons: [
        'Operational complexity (3+ brokers, ZooKeeper or KRaft)',
        'At-least-once means duplicates — handler must be idempotent',
        'Schema drift breaks consumers silently',
        'No cross-partition ordering',
        'Replay can be expensive (re-process all events)',
      ],
    },
    comparison: {
      left: 'Kafka',
      right: 'RabbitMQ',
      rows: [
        { aspect: 'Use case', left: 'Event log + replay', right: 'Task queue + complex routing' },
        { aspect: 'Durability', left: 'Disk-replicated; long retention', right: 'In-memory primary; persistence optional' },
        { aspect: 'Throughput', left: '100K+ msg/sec per broker', right: '10-50K msg/sec' },
        { aspect: 'Replay', left: 'Native (offset reset)', right: 'Hard (queue is consumed)' },
        { aspect: 'Routing', left: 'Topic-based; consumer-side filter', right: 'Exchange-based; flexible routing' },
        { aspect: 'When to pick', left: 'Event sourcing, replay, fan-out', right: 'Task distribution, RPC patterns' },
      ],
    },
    solutions: [
      { problem: 'Duplicate processing on retry', solution: 'event_id de-dupe in consumer; idempotent handlers' },
      { problem: 'Schema drift breaks consumer', solution: 'Schema registry with backward-compat enforcement; canary new schema first' },
      { problem: 'Consumer lag growing', solution: 'Add consumer instances (must be ≤ partition count); investigate slow handler' },
      { problem: 'Stuck saga (consumer dies mid-step)', solution: 'Outbox pattern + recovery worker reads stuck rows + replays' },
      { problem: 'Poison message blocks queue', solution: 'Bounded retry (3 attempts); park in DLQ; consumer continues with next message' },
    ],
    bestPractices: {
      do: [
        'Schema registry with backward-compat enforcement',
        'Idempotent handlers (dedupe by event_id)',
        'event_id + tenant_id + schema_version on every event',
        'Outbox pattern for transactional event publishing',
        'DLQ with bounded retry (3 attempts max)',
        'Monitor consumer lag per partition',
      ],
      avoid: [
        'Cross-partition ordering assumptions',
        'Unbounded retry (poison messages block queue)',
        'Schema-less events (versioning impossible)',
        'Consumer instance count > partition count (idle consumers)',
        'Two-phase commit between Kafka + DB (use outbox instead)',
      ],
      optimize: [
        'Batch produce (linger.ms) for throughput',
        'Compaction on key-keyed topics (latest-value semantics)',
        'Tiered storage for long-retention topics',
        'Per-tenant partition routing for isolation',
        'Compression (lz4 / snappy / zstd) for bandwidth',
      ],
    },
    antiPatterns: [
      'Treating Kafka as a database (long-retention is for replay, not query)',
      'Synchronous producer → wait for ack on hot path (latency)',
      'Cross-partition ordering assumptions (only per-partition guaranteed)',
      'Two-phase commit between Kafka + DB — race conditions',
      'Schema-less JSON without versioning — silent drift',
      'Unbounded retry — poison messages stall the consumer forever',
    ],
    testTypes: [
      'Unit (handler logic with mocked broker)',
      'Integration with real Kafka (testcontainers)',
      'Drill — poison message + DLQ behavior',
      'Drill — replay from offset reproduces state',
      'Drill — schema upgrade backward-compat',
      'Performance — producer throughput + consumer lag under load',
    ],
    testScenarios: [
      { scenario: 'Producer crashes mid-publish', expected: 'Idempotent producer retries; no duplicates' },
      { scenario: 'Consumer crashes after side effect, before commit', expected: 'Replay; handler dedupes by event_id; no double effect' },
      { scenario: 'Poison message (malformed JSON)', expected: '3 retries fail; message lands in DLQ; consumer continues' },
      { scenario: 'Schema upgrade rolled out', expected: 'Old consumers deserialize new schema (backward compat)' },
      { scenario: 'Partition count increased', expected: 'Consumers rebalance; no message loss' },
      { scenario: 'Replay from earlier offset', expected: 'Events re-processed; idempotent handlers no-op duplicates' },
    ],
    testData: [
      { type: 'Valid', example: '{event_id: UUID, tenant_id: UUID, schema_version: v2, payload: {...}}' },
      { type: 'Duplicate', example: 'Same event_id sent twice → consumer processes once' },
      { type: 'Poison', example: 'Malformed JSON or schema mismatch → DLQ' },
      { type: 'Boundary', example: '1MB message (default broker max)' },
      { type: 'Extreme', example: '50K msg/sec sustained for 60s; verify lag stays bounded' },
    ],
    debuggingChecklist: [
      'Is the consumer group lagging? (kafka-consumer-groups.sh)',
      'Are all partitions assigned to a consumer? (kafka-consumer-groups.sh describe)',
      'Did the schema registry accept the new version? (curl /subjects/<topic>/versions)',
      'Is the producer ack=all? (config check)',
      'Is min.insync.replicas correctly set? (broker config)',
      'Are DLQ messages accumulating? (DLQ topic size)',
      'Is the outbox relay polling? (last-published timestamp)',
    ],
    productionIssues: [
      { issue: 'Consumer lag grew to 1M messages', rootCause: 'Slow handler; one per partition; bottleneck on external API call' },
      { issue: 'Duplicate audit log rows', rootCause: 'Consumer crashed after side effect, before offset commit; replay; handler not idempotent' },
      { issue: 'Schema upgrade broke old consumers', rootCause: 'Removed required field instead of deprecating; backward-incompat change' },
      { issue: 'Outbox table grew unbounded', rootCause: 'Outbox relay crashed; no monitoring on relay lag; row not marked sent' },
      { issue: 'DLQ flooded with poison messages', rootCause: 'Producer schema bug; DLQ rate not alerted' },
    ],
    performance: [
      'Producer p99 publish latency < 50ms (with ack=all)',
      'Consumer throughput per instance: 10K-50K msg/sec',
      'Per-partition single-consumer parallelism',
      'Compression (lz4) reduces bandwidth 3-5x',
      'Replication factor 3 doubles write cost vs RF=1',
    ],
    costConsiderations: [
      'Disk replication: RF=3 = 3x storage cost',
      'Long retention (90+ days) dominates cost; tiered storage helps',
      'Cross-region replication for DR adds bandwidth cost',
      'Managed (MSK / Confluent) cheaper to operate but per-throughput priced',
      'Compression saves both bandwidth + storage',
    ],
    observability: [
      'Per-topic + per-partition lag',
      'Producer publish latency p95/p99',
      'Consumer offset commit rate',
      'DLQ message count + age',
      'Schema registry compat-check rate',
      'Outbox relay polling lag',
    ],
    metrics: [
      { name: 'kafka_consumer_lag', example: '< 1000 msg target; alert > 10K' },
      { name: 'kafka_producer_p99_latency_ms', example: '< 50ms; alert > 200ms' },
      { name: 'dlq_message_count', example: '0 expected; any non-zero pages on-call' },
      { name: 'outbox_relay_lag_seconds', example: '< 5s; alert > 30s' },
      { name: 'schema_compat_failures_total', example: '0 expected; any value blocks deploy' },
    ],
    failureModes: [
      { mode: 'Broker unavailable', detect: '/health/upstreams kind=kafka returns reachable=false', recover: 'Producer buffers; consumer pauses; manual broker recovery' },
      { mode: 'Consumer lag growing', detect: 'kafka_consumer_lag > threshold', recover: 'Add consumer instance (≤ partition count); investigate slow handler' },
      { mode: 'Poison message blocks consumer', detect: 'Consumer offset stuck', recover: 'Bounded retry → DLQ; consumer continues' },
      { mode: 'Schema drift breaks consumer', detect: 'Deserialization errors spike', recover: 'Roll back schema OR ship consumer update' },
      { mode: 'Outbox relay lagging', detect: 'outbox_relay_lag_seconds > 30s', recover: 'Restart relay; investigate DB pressure; scale relay' },
    ],
    tradeoffs: [
      { decision: 'Self-hosted Kafka vs managed (MSK / Confluent)', tradeoff: 'Operational control vs ops cost' },
      { decision: 'Topic per event-type vs unified', tradeoff: 'Schema clarity vs partition explosion' },
      { decision: 'Partition count', tradeoff: 'Parallelism ceiling vs broker overhead per partition' },
      { decision: 'Retention period', tradeoff: 'Replay window vs storage cost' },
      { decision: 'Outbox vs direct publish', tradeoff: 'Transactional safety vs latency overhead' },
    ],
    decisionMatrix: [
      { option: 'Kafka (default)', whenToUse: 'Event sourcing + replay + fan-out + high throughput' },
      { option: 'RabbitMQ', whenToUse: 'Task queue + complex routing; lower throughput; no replay needed' },
      { option: 'NATS / NATS JetStream', whenToUse: 'Lightweight; smaller scale; cloud-native' },
      { option: 'AWS Kinesis / GCP Pub/Sub', whenToUse: 'Managed; vendor lock; per-message pricing' },
      { option: 'Postgres LISTEN/NOTIFY', whenToUse: 'Tiny system; no replay; same DB cluster' },
      { option: 'Redis Streams', whenToUse: 'Already have Redis; modest throughput; simpler ops' },
    ],
    starStory: {
      situation: 'Embed-worker deployed with a bug — every embedding was reduced to all-zeros. Detection took 4 hours. By then 50K documents had been processed wrong.',
      task: 'Recover the corrupted index without re-uploading documents; prevent silent recurrence.',
      action: 'Rolled back embed-worker to previous version. Reset consumer group offset on document.chunked topic to the offset 4 hours prior. Replayed all events; idempotent handler de-duped already-correct embeddings via event_id; corrupted ones got recomputed. Drill: deploy a "broken" embed-worker on canary; verify eval-svc Recall@K drop fires alert within 5 minutes (vs 4 hours).',
      result: 'Recovery took 90 minutes vs the 4 hours it would have without replay. Eval-svc canary alert now catches embedding bugs before full rollout. Two more bugs blocked at canary in the year since.',
    },
    interviewTraps: [
      'Treating Kafka as a database — long retention is for replay, not query',
      'Cross-partition ordering assumptions — only per-partition is guaranteed',
      'Two-phase commit between Kafka + DB — outbox pattern instead',
      'Unbounded retry — poison messages stall consumer forever',
      'Schema-less JSON — version drift is silent + lethal',
      'Consumer count > partition count — idle consumers waste resources',
    ],
    interviewLine: 'Kafka solves workflow decoupling and replay, but it shifts complexity into idempotency, lag, and schema discipline. The hard parts aren\'t producing — they\'re consuming safely.',
    finalScript: 'Kafka is the durable event-log backbone in this stack. Three non-negotiable disciplines. First, schema registry with backward-compat enforcement — every event has event_id, tenant_id, schema_version stamped at publish; schema changes are reviewed before deploy. Second, idempotent consumers — at-least-once delivery means duplicates; every handler de-dupes by event_id and commits offset only after the side effect succeeds. Third, dead-letter queue with bounded retry — 3 attempts with exponential backoff, then park for human review; consumer keeps draining downstream. We use the outbox pattern for transactional event publishing — domain row plus event row in one Postgres transaction; outbox relay polls + publishes; mark sent. The drill that gates this is a poison-message replay: inject a malformed message, verify retry budget exhausts, message lands in DLQ, consumer drains the next message. Mocks lie about consumer lag; only a real broker shows where rebalances and offset stalls hide.',
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
    alternatives: [
      { name: 'RabbitMQ', tradeoff: 'Lower volume; more flexible routing; weaker replay' },
      { name: 'NATS / NATS JetStream', tradeoff: 'Lighter; simpler; smaller ecosystem' },
      { name: 'AWS Kinesis / GCP Pub/Sub', tradeoff: 'Managed; vendor lock-in; per-message cost' },
      { name: 'PostgreSQL LISTEN/NOTIFY', tradeoff: 'No persistence; single-instance; for tiny scale' },
    ],
    testing: [
      'Duplicate-delivery drill (idempotent consumer)',
      'Replay-after-bug drill (offset reset, no double side effect)',
      'Poison-message drill (DLQ catches it)',
      'Schema-evolution drill (old consumer + new producer)',
      'Broker-down drill (producer + consumer behaviour)',
    ],
    monitoring: [
      'Consumer lag per (topic, group, partition)',
      'Producer error rate',
      'Broker disk usage + retention horizon',
      'Rebalance count',
      'DLQ depth',
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
      'libs/py/documind_core/kafka_client.py — EventProducer + IdempotentConsumer',
      'document.lifecycle topic (ingestion-svc events)',
      'governance.audit_log fan-out via Kafka',
      '/health/upstreams Kafka TCP probe',
      'mcp/tests/drill_kafka_poison_dlq.py + drill_outbox_relay.py',
    ],
  },

  // ---- 5. ClickHouse ----
  {
    slug: 'clickhouse',
    title: '5. ClickHouse — analytics / time-series',
    status: 'shipped',
    coreConcept: 'Columnar analytical store optimized for append-heavy ingest and aggregate queries across huge event sets — for observability and reporting, not transactional correctness.',
    oneLiner: 'ClickHouse = OLAP at billions of rows; for dashboards + reports + cost analytics, NOT transactional truth.',
    businessContext: 'Token + cost + latency dashboards over 30-day windows can\'t run on Postgres at scale — row-oriented + ACID makes aggregate queries take minutes. FinOps + SRE need millisecond aggregates over hundreds of millions of events.',
    fiveW: {
      what: 'Columnar OLAP database with vectorized execution + materialized views + per-column compression. Designed for append-heavy ingest and analytical aggregates.',
      why: 'Postgres takes minutes for "sum tokens per tenant over 30 days"; ClickHouse turns that into milliseconds. 100-1000x speedup vs row-oriented OLAP.',
      where: 'Token usage dashboards, latency/error aggregates, cost reports, security event search, model eval scoring trends. Fed by Kafka consumers; queried by Grafana + admin UIs.',
      when: 'Event volume > 10M/day, aggregate-heavy queries, time-bounded windows, eventual consistency tolerance, no transactional updates needed.',
      who: 'Platform team owns the cluster. Each consuming team owns its tables + materialized views. SRE + FinOps consume aggregates.',
    },
    interview30s: 'ClickHouse is the analytics + time-series store. Columnar storage + vectorized execution + materialized views give 100-1000x speedup on aggregate queries vs Postgres. Three non-negotiable disciplines: schema design with low-cardinality + sortable columns, materialized views for hot aggregates (precomputed at ingest), and TTL on high-volume tables (auto-drop old partitions). It\'s not a database — no transactions, no row-level updates. The drill that gates this is partition-skew + TTL: insert N events across many tenants, verify per-tenant aggregate fast, verify TTL drops old partitions on schedule.',
    coreBuildingBlocks: [
      'MergeTree engine — columnar storage; per-column compression; partitions by date',
      'Distributed engine — sharded for horizontal scale across replicas',
      'Materialized views — precomputed aggregates updated at ingest',
      'Dictionaries — fast joins via in-memory key-value lookup',
      'TTL on partitions — auto-drop old data on schedule',
      'Kafka table engine — direct Kafka consumer (alternative to outbox-relay)',
      'Compression codecs — LZ4 / ZSTD / Delta / DoubleDelta per column type',
    ],
    architectureRelevance: {
      backend: 'Append-only ingest via Kafka consumer (or direct Kafka table engine). No service writes synchronously to ClickHouse on the hot path.',
      rag: 'Retrieval quality + recall tracking over time. Per-tenant query rate, slow query top-N, cache hit rate trends.',
      ai: 'Token cost per tenant per minute. Decision audit aggregates. Eval score trends. Cost dashboard per model.',
      microservices: 'Cross-service latency aggregates per (service, route). p50/p95/p99 over time windows.',
    },
    hld: `flowchart TB
  subgraph svcs[Producers]
    INF[inference-svc]
    RET[retrieval-svc]
    GOV[governance-svc]
    OTel[OTel collector]
  end
  subgraph k[Kafka]
    T1[(token_events)]
    T2[(latency_events)]
    T3[(audit_events)]
  end
  subgraph ch[ClickHouse cluster]
    SHARD1[("Shard 1 + replicas")]
    SHARD2[("Shard 2 + replicas")]
    MV[("Materialized views")]
    TTL[("TTL on partitions")]
  end
  subgraph cons[Dashboards]
    GRAF[Grafana]
    UI[Admin UI]
    FINOPS[FinOps reports]
  end
  INF --> T1
  RET --> T2
  GOV --> T3
  OTel --> T2
  T1 --> SHARD1
  T2 --> SHARD2
  T3 --> SHARD1
  SHARD1 --> MV
  SHARD2 --> MV
  MV --> GRAF
  MV --> UI
  MV --> FINOPS
  SHARD1 -.->|TTL| TTL`,
    networkFlow: `flowchart LR
  K[(Kafka topic)] --> CON[ClickHouse Kafka consumer]
  CON --> MT[("MergeTree table")]
  MT --> MV[("Materialized view aggregates")]
  Q[Dashboard query] --> MV
  MT -.->|TTL drops old partitions| BIN[/dev/null]`,
    flowchart: `flowchart LR
  E[Event from Kafka] --> ING[ClickHouse consumer batch]
  ING --> MT[INSERT into MergeTree]
  MT --> MV[Materialized view recomputes]
  Q[Dashboard query] --> P[Partition pruning by date]
  P --> COL[Column read only what needed]
  COL --> AGG[Aggregate via vectorized exec]
  AGG --> RES[Return millisecond result]`,
    sequence: `sequenceDiagram
  autonumber
  participant Svc as Service emits event
  participant K as Kafka topic
  participant CH as ClickHouse consumer
  participant MT as MergeTree
  participant MV as Materialized view
  participant Q as Dashboard query
  Svc->>K: publish event
  CH->>K: poll batch
  K-->>CH: 1000 events
  CH->>MT: INSERT batch
  MT->>MV: trigger MV recompute
  Q->>MV: SELECT aggregate
  MV-->>Q: millisecond result`,
    coreLayers: [
      { layer: 'Cluster', responsibility: 'Sharded for horizontal scale; replicated for HA. Distributed engine routes queries.' },
      { layer: 'MergeTree engine', responsibility: 'Columnar storage; per-column codec; partitioned by date; sorted by (tenant_id, ts).' },
      { layer: 'Compression', responsibility: 'LZ4 default; ZSTD for cold; Delta + DoubleDelta for monotonic columns. 5-20x ratio.' },
      { layer: 'Materialized views', responsibility: 'Precomputed aggregates updated at ingest. Hot dashboards hit MV, not raw table.' },
      { layer: 'Dictionaries', responsibility: 'In-memory key-value for fast joins (tenant_id → name, model_id → version).' },
      { layer: 'TTL', responsibility: 'Auto-drop old partitions on schedule. Tier to S3 (cold storage) for compliance retention.' },
      { layer: 'Ingest path', responsibility: 'Kafka consumer (table engine OR external worker) batches inserts. Never sync from hot path.' },
    ],
    lld: `flowchart LR
  subgraph cli[CHClient]
    BATCH[batch_insert]
    QRY[query]
  end
  subgraph srv[ClickHouse server]
    DIST[Distributed table]
    MT1[Local MergeTree shard 1]
    MT2[Local MergeTree shard 2]
    REP1[Replica]
    REP2[Replica]
    MV[Materialized view]
  end
  BATCH --> DIST
  DIST --> MT1
  DIST --> MT2
  MT1 -.-> REP1
  MT2 -.-> REP2
  MT1 --> MV
  MT2 --> MV
  QRY --> MV`,
    problem: 'Postgres at OLAP scale is the wrong shape: row-oriented, ACID-bound, slow for "sum tokens for tenant T over the last 30 days." ClickHouse turns minutes into milliseconds.',
    whyThisApproach: 'Columnar storage + vectorized execution + materialized views give ~100x speedup on aggregate queries over time-series. Append-only ingest fits Kafka → ClickHouse pipelines naturally.',
    whenToUse: [
      'Token usage dashboards per tenant',
      'Latency / error rate aggregations',
      'Cost-tracking and FinOps reports',
      'Security event search at scale',
      'Eval score trends over time',
      'Per-(service, route) p50/p95/p99 over windows',
    ],
    whenNotToUse: [
      'Transactional correctness → Postgres',
      'Single-row mutations → ClickHouse fights you',
      'Foreign-key relationships → Postgres',
      'Strict consistency requirements → Postgres',
      'Sub-100GB total — operational overhead exceeds value',
    ],
    input: 'Append-only event batch from Kafka consumer (1k-10k events per insert)',
    process: [
      'Service emits event to Kafka',
      'ClickHouse consumer polls batch (1k-10k events)',
      'INSERT batch into local MergeTree shard',
      'Materialized view recomputes aggregate',
      'Replicas async-sync',
      'TTL drops old partitions on schedule',
      'Dashboard query hits MV via Distributed engine',
    ],
    output: 'Millisecond aggregate over hundreds of millions of events. Auto-tiered to cheap storage past TTL.',
    implementationSteps: [
      { step: '1', logic: 'Provision ClickHouse cluster (3+ shards, RF=2). Managed: Altinity / ClickHouse Cloud.' },
      { step: '2', logic: 'Design schema: low-cardinality + sortable columns first; partitions by toYYYYMM(ts).' },
      { step: '3', logic: 'Pick compression codecs: LZ4 default; ZSTD for cold; Delta for monotonic.' },
      { step: '4', logic: 'Create materialized views for hot aggregates (per-tenant token sum per hour, etc).' },
      { step: '5', logic: 'Wire Kafka consumer (table engine OR external worker with batching).' },
      { step: '6', logic: 'Set TTL on partitions: 90 days hot, 1 year cold (S3), then drop.' },
      { step: '7', logic: 'Add dashboards in Grafana pointed at materialized views (not raw tables).' },
      { step: '8', logic: 'Drill: insert 10M events across 100 tenants; verify per-tenant aggregate < 50ms; verify TTL drops old partitions.' },
    ],
    codeExample: {
      language: 'sql',
      code: `-- Token usage events
CREATE TABLE token_events ON CLUSTER docu (
  event_id UUID,
  tenant_id UUID,
  ts DateTime64(3),
  model String,
  prompt_tokens UInt32,
  completion_tokens UInt32,
  cost_usd Decimal(10, 6)
)
ENGINE = ReplicatedMergeTree('/clickhouse/{shard}/token_events', '{replica}')
PARTITION BY toYYYYMM(ts)
ORDER BY (tenant_id, ts)
TTL ts + INTERVAL 90 DAY DELETE;

-- Hot aggregate: per-tenant per-hour
CREATE MATERIALIZED VIEW token_per_tenant_hour
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (tenant_id, hour, model)
AS SELECT
  tenant_id,
  toStartOfHour(ts) AS hour,
  model,
  sum(prompt_tokens) AS prompt_sum,
  sum(completion_tokens) AS completion_sum,
  sum(cost_usd) AS cost_sum,
  count() AS request_count
FROM token_events
GROUP BY tenant_id, hour, model;

-- Dashboard query: 30-day cost per tenant
SELECT tenant_id, sum(cost_sum) AS total_cost_30d
FROM token_per_tenant_hour
WHERE hour >= now() - INTERVAL 30 DAY
GROUP BY tenant_id
ORDER BY total_cost_30d DESC;
-- Returns in 5-50ms across hundreds of millions of events.`,
    },
    realUseCase: 'FinOps wants to see "top 10 tenants by token cost in the last 30 days." Without ClickHouse: scan Postgres audit_log table (~500M rows over 30 days) — 5-10 minute query, kills the database. With ClickHouse: SELECT from token_per_tenant_hour materialized view — 50ms. Dashboard refreshes every 30 seconds without breaking a sweat.',
    prosCons: {
      pros: [
        'Aggregate queries 100-1000x faster than row-oriented',
        'Per-column compression: 5-20x storage reduction',
        'Materialized views precompute hot dashboards',
        'TTL handles retention without cleanup jobs',
        'Append-heavy ingest pattern fits Kafka naturally',
        'Distributed engine + replication = HA + scale',
      ],
      cons: [
        'No transactions; eventual consistency',
        'Row-level updates fight the engine',
        'Schema migrations awkward (rebuild required for some)',
        'Operational complexity at multi-shard scale',
        'Dictionaries must fit in RAM',
      ],
    },
    comparison: {
      left: 'ClickHouse',
      right: 'Postgres + TimescaleDB',
      rows: [
        { aspect: 'Aggregate speed at 100M rows', left: '50ms-1s', right: '10s-2min' },
        { aspect: 'Storage compression', left: '5-20x', right: '2-5x' },
        { aspect: 'Transactions', left: 'No', right: 'Yes (ACID)' },
        { aspect: 'Schema migration', left: 'Awkward (rebuild)', right: 'ALTER TABLE works' },
        { aspect: 'Operational footprint', left: 'Heavier (cluster ops)', right: 'Familiar Postgres' },
        { aspect: 'When to pick', left: '> 100M events; FinOps; observability', right: '< 10M events; ACID + analytics' },
      ],
    },
    solutions: [
      { problem: 'Slow dashboard query', solution: 'Move query to materialized view; precompute aggregate at ingest' },
      { problem: 'Storage growth out of control', solution: 'TTL on partitions; tier to S3 for cold compliance retention' },
      { problem: 'Cardinality explosion in ORDER BY', solution: 'Use low-cardinality columns first in sort key' },
      { problem: 'Schema drift', solution: 'Versioned table names; new schema via new MV; cut over via Distributed engine' },
      { problem: 'Hot tenant skews shard load', solution: 'Sharding key includes tenant_id; rebalance via partition move' },
    ],
    bestPractices: {
      do: [
        'Sort key = (low-cardinality, time): (tenant_id, ts)',
        'Partition by date for TTL granularity',
        'Materialized views for hot aggregates',
        'LowCardinality(String) for high-repetition columns',
        'Batch inserts (1k-10k events per insert)',
        'TTL on every event-volume table',
      ],
      avoid: [
        'Row-level UPDATE / DELETE on hot tables',
        'Sub-second batched inserts (creates many small parts)',
        'JOINs across large tables (use dictionaries)',
        'High-cardinality first in ORDER BY',
        'No TTL = unbounded storage growth',
      ],
      optimize: [
        'ZSTD codec for cold-tier compression',
        'Delta + DoubleDelta for monotonic columns (timestamps)',
        'PROJECTION for alternate sort orders',
        'Distributed engine for transparent sharding',
        'Buffer engine for ingest smoothing on bursty inputs',
      ],
    },
    antiPatterns: [
      'Treating ClickHouse as transactional database — fights you',
      'Single-row INSERT (creates many small parts; merge storm)',
      'JOIN across two large MergeTree tables — slow; use dictionaries instead',
      'High-cardinality first in ORDER BY — cardinality column index useless',
      'No TTL on event tables — unbounded storage cost',
      'Schema migration without rebuild plan — performance regresses',
    ],
    testTypes: [
      'Unit (SQL via test fixture)',
      'Integration with real ClickHouse (testcontainers)',
      'Drill — partition pruning verified via EXPLAIN',
      'Drill — TTL drops old partitions on schedule',
      'Drill — replication catches up after node failure',
      'Performance — N events ingested + aggregate < 50ms',
    ],
    testScenarios: [
      { scenario: 'Insert 10M events; query per-tenant 30-day cost', expected: '< 50ms via MV' },
      { scenario: 'TTL fires on partition older than 90d', expected: 'Partition dropped; storage reclaimed' },
      { scenario: 'Replica node down', expected: 'Query routes to live replica; no data loss' },
      { scenario: 'Schema migration adds column', expected: 'New rows have value; old rows have default' },
      { scenario: 'Hot tenant submits 1M events in 1min', expected: 'Sharded ingest absorbs without throttling' },
    ],
    testData: [
      { type: 'Valid', example: '{event_id, tenant_id, ts, model, prompt_tokens, completion_tokens, cost_usd}' },
      { type: 'Boundary', example: '10K events per batch insert (target throughput)' },
      { type: 'Extreme', example: '1M events/sec sustained for 60s' },
      { type: 'Old data', example: '100d-old event past TTL (90d) → dropped on next merge' },
      { type: 'Skewed', example: '90% events from one tenant → shard balance check' },
    ],
    debuggingChecklist: [
      'Is the query using the partition key? (EXPLAIN)',
      'Is the sort key matching the WHERE clause prefix? (EXPLAIN)',
      'Is the materialized view recomputing on schedule? (system.parts age)',
      'Is the replication lag bounded? (system.replication_queue)',
      'Is the part count within healthy range? (system.parts; merge storm if > 1000)',
      'Are TTL settings active? (system.tables.engine_full)',
      'Is dictionary cache hit rate high? (system.dictionaries)',
    ],
    productionIssues: [
      { issue: 'Dashboard query takes 30s', rootCause: 'Hit raw MergeTree, not materialized view; missing MV' },
      { issue: 'Storage doubled overnight', rootCause: 'No TTL on event table; partition kept growing' },
      { issue: 'Merge storm blocks ingest', rootCause: 'Inserts too small (1 row each); created 50K small parts' },
      { issue: 'Replication lagged 4 hours', rootCause: 'Network saturation between data centers; no rate limit' },
      { issue: 'Wrong tenant sees aggregate', rootCause: 'Forgot tenant_id WHERE clause in dashboard query' },
    ],
    performance: [
      'p50 aggregate query < 50ms via MV',
      'p99 aggregate < 1s on 100M-row table',
      'Ingest throughput: 100K-1M events/sec/shard',
      'Compression ratio: 5-20x typical',
      'Merge background: tune background_pool_size',
    ],
    costConsiderations: [
      'Storage dominates — TTL + tiering to S3 essential',
      'Compression saves 5-20x storage cost',
      'Replication factor 2 doubles storage',
      'Materialized views add storage cost but save query cost',
      'Managed services (Altinity / Aiven) cheaper to operate; per-throughput priced',
    ],
    observability: [
      'system.parts size + count per table',
      'Replication queue depth',
      'Background merge progress',
      'Materialized view recompute lag',
      'Per-table TTL effectiveness (rows dropped)',
      'Slow query log',
    ],
    metrics: [
      { name: 'clickhouse_query_p99_ms', example: '< 1000ms; alert > 5000ms' },
      { name: 'clickhouse_replication_lag_seconds', example: '< 60s; alert > 300s' },
      { name: 'clickhouse_part_count_per_table', example: '< 1000; alert > 5000 (merge storm)' },
      { name: 'clickhouse_storage_bytes', example: 'Track growth; correlate with TTL effectiveness' },
      { name: 'clickhouse_ingest_rate', example: 'Per-shard throughput; alert if shard skew > 2x' },
    ],
    failureModes: [
      { mode: 'Cluster unreachable', detect: '/health/upstreams kind=clickhouse', recover: 'Dashboards show stale data; ingest backs up in Kafka; manual recovery' },
      { mode: 'Merge storm', detect: 'part_count > 5000 on table', recover: 'Throttle ingest; OPTIMIZE TABLE manually; tune merge concurrency' },
      { mode: 'Replication lag spike', detect: 'replication_queue > 1000 entries', recover: 'Investigate network; rate-limit insert; restart replica if stuck' },
      { mode: 'TTL not firing', detect: 'Old partitions not dropped on schedule', recover: 'Check system.tables; force TTL via OPTIMIZE; review TTL syntax' },
      { mode: 'Dictionary out-of-sync', detect: 'Dashboard shows wrong tenant name', recover: 'RELOAD DICTIONARY; check source table' },
    ],
    tradeoffs: [
      { decision: 'ClickHouse vs Postgres+Timescale', tradeoff: 'Speed + storage vs ACID + ops familiarity' },
      { decision: 'Self-host vs managed (Altinity / Aiven / Cloud)', tradeoff: 'Operational control vs ops cost' },
      { decision: 'Replication factor 2 vs 3', tradeoff: 'Cost vs durability' },
      { decision: 'TTL DELETE vs TTL TO DISK (tiered)', tradeoff: 'Compliance retention vs storage cost' },
      { decision: 'Materialized view vs raw query', tradeoff: 'Storage cost vs query latency' },
    ],
    decisionMatrix: [
      { option: 'ClickHouse (default for OLAP)', whenToUse: '> 10M events/day; aggregate-heavy; FinOps + observability' },
      { option: 'TimescaleDB (Postgres extension)', whenToUse: '< 10M events/day; ACID + analytics; ops simplicity' },
      { option: 'BigQuery / Redshift', whenToUse: 'Cloud-native; managed; vendor lock; per-query pricing' },
      { option: 'Apache Druid', whenToUse: 'Real-time analytics; OLAP cubes; smaller ecosystem' },
      { option: 'Apache Pinot', whenToUse: 'Low-latency real-time analytics; user-facing analytics products' },
      { option: 'Postgres only', whenToUse: '< 1M events; ACID; familiar tooling' },
    ],
    starStory: {
      situation: 'FinOps reported the per-tenant cost dashboard was timing out at 30 seconds. The CTO asked for the same data weekly. Each query was reading 500M rows from Postgres audit_log.',
      task: 'Make the dashboard sub-second + scale for 10x event volume next year.',
      action: 'Built a Kafka topic of token_events; ClickHouse consumer batched inserts into ReplicatedMergeTree partitioned by month. Created materialized view aggregating per-tenant per-hour. Migrated dashboard to query the MV. Sub-50ms p99 immediately. TTL on raw events at 90 days kept storage growth bounded. Drill: 10M events insert + aggregate query < 50ms verified in CI.',
      result: 'Dashboard refresh cut from 30s timeout to sub-second. Storage cost dropped 8x via columnar compression vs Postgres equivalent. The drill catches any future query regression before it reaches prod.',
    },
    interviewTraps: [
      'Treating ClickHouse as a relational database — no transactions, no row-level updates',
      'Single-row INSERTs — creates many small parts; merge storm follows',
      'High-cardinality column first in ORDER BY — defeats the index',
      'JOIN across two large tables — slow; use dictionaries instead',
      'No TTL on event tables — unbounded storage growth',
      'Querying raw MergeTree directly when MV exists — 100x slower',
    ],
    interviewLine: 'ClickHouse is for observability and analytics shapes, not transactional correctness. The discipline isn\'t the engine; it\'s event quality and aggregation strategy.',
    finalScript: 'ClickHouse is the analytics + time-series store in this stack. Three non-negotiable disciplines. First, schema design: low-cardinality + sortable columns first in the ORDER BY; partition by date for TTL granularity; LowCardinality for high-repetition strings. Second, materialized views for hot aggregates — every dashboard hits a precomputed MV, never the raw MergeTree. Third, TTL on every event-volume table — auto-drop old partitions; tier to S3 for compliance retention; storage growth bounded. Ingest is append-only via Kafka consumer (table engine or external worker), batched 1k-10k events per insert. Replicated MergeTree gives HA; Distributed engine gives transparent sharding. The drill is partition pruning + TTL: insert millions of events, verify per-tenant aggregate via MV is sub-50ms, verify TTL drops old partitions on schedule. It\'s not a database — no transactions; if you need ACID, use Postgres.',
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
    alternatives: [
      { name: 'TimescaleDB (Postgres extension)', tradeoff: 'SQL familiarity; tighter PG integration; slower than columnar at scale' },
      { name: 'Druid', tradeoff: 'Lambda-architecture roots; complex ops; strong real-time' },
      { name: 'BigQuery', tradeoff: 'Managed; pay-per-query; vendor lock-in' },
      { name: 'DuckDB', tradeoff: 'In-process columnar; great for laptops; not multi-user serving' },
    ],
    testing: [
      'Idempotent-insert drill',
      'Late-arrival drill (event with timestamp T inserted at T+1h)',
      'Materialized view consistency drill',
      'Schema-evolution drill',
    ],
    monitoring: [
      'Insert rate + batch size',
      'Merge backlog (parts_count)',
      'Query p95 + p99',
      'Disk usage + projected retention horizon',
      'Materialized view refresh lag',
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
      'Planned for FinOps cost tracking + observability analytics',
      'Consumes from Kafka outbox (events → ClickHouse pipeline)',
      'governance.token_events + audit_log projection target',
      'mcp/tests/drill_clickhouse_mv.py + drill_partition_ttl.py',
      'LLMOps scorecard row "data" tracks rollout status',
    ],
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
