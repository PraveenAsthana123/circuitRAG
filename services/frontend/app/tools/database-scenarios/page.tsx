import Link from 'next/link';
import DerivedRows from '../../../components/DerivedRows';

export const metadata = { title: 'Database Scenarios — DocuMind' };

type Scenario = {
  category: string;
  pattern: string;
  problem: string;
  solution: string;
  documindExample: string;
  tradeoffs: string;
  docsUrl: string;
  docsLabel: string;
};

const SCENARIOS: Scenario[] = [
  // ---- Relational ---------------------------------------------------------
  {
    category: 'Relational',
    pattern: 'Postgres + RLS + role separation',
    problem: 'Source of truth for domain data needs ACID + tenant isolation + auditable access.',
    solution: 'Postgres with schema-per-service + ROW LEVEL SECURITY + FORCE RLS + three roles (owner / app NOBYPASSRLS / ops BYPASSRLS).',
    documindExample: 'identity / ingestion / governance / finops / eval / observability schemas. documind_app role cannot bypass RLS; migrations run as documind; billing jobs run as documind_ops with audit.',
    tradeoffs: 'One cluster, many owners — simple to operate, clear ownership. The role-separation learning curve is real; mocked tests lie about RLS correctness.',
    docsUrl: 'https://www.postgresql.org/docs/current/ddl-rowsecurity.html',
    docsLabel: 'PostgreSQL — Row Security',
  },
  {
    category: 'Relational',
    pattern: 'Schema-per-service',
    problem: 'Shared schemas couple service deploys; one migration blocks everyone.',
    solution: 'Each service owns its schema; cross-service reads go through APIs or events, never SQL joins.',
    documindExample: 'Postgres cluster with six schemas. grants locked down per service; no cross-schema foreign keys.',
    tradeoffs: 'Easier deploys, harder reporting — analytics needs a dedicated warehouse path, not JOINs.',
    docsUrl: 'https://microservices.io/patterns/data/database-per-service.html',
    docsLabel: 'microservices.io — Database per Service',
  },
  {
    category: 'Relational',
    pattern: 'Migration system',
    problem: 'Schema evolution without downtime; rollback without losing data.',
    solution: 'Forward-only numbered SQL migrations; _migrations table tracks applied versions; every DDL change has a paired rollback migration.',
    documindExample: 'services/*/migrations/NNN_*.sql. make migrate loops all services. 003_rls_force.sql came after 002 — never edit a deployed migration.',
    tradeoffs: 'Disciplined but verbose. No auto-generated DDL from ORM models (which is the point).',
    docsUrl: 'https://www.postgresql.org/docs/current/sql-alter-table.html',
    docsLabel: 'PostgreSQL — ALTER TABLE',
  },

  // ---- Vector ------------------------------------------------------------
  {
    category: 'Vector DB',
    pattern: 'Qdrant HNSW + scalar quantization',
    problem: 'Sub-second semantic search across 10M+ chunks at reasonable memory cost.',
    solution: 'HNSW for sub-linear ANN; scalar quantization for ~4x memory reduction; payload filter on tenant_id mandatory.',
    documindExample: 'QdrantRepo wraps every query with must.tenant_id filter. Per-tenant optional collection for regulated customers. Tenant_id filter is inescapable in the repo API.',
    tradeoffs: '~1% recall loss vs. flat index; rebuild on major schema change; operationally heavier than pgvector for tiny workloads.',
    docsUrl: 'https://qdrant.tech/documentation/',
    docsLabel: 'Qdrant docs',
  },
  {
    category: 'Vector DB',
    pattern: 'pgvector (fallback for small tenants)',
    problem: 'Operational cost of running Qdrant doesn\'t pay off below ~100K chunks per tenant.',
    solution: 'pgvector extension on the same Postgres cluster; ACID semantics with embeddings; HNSW available.',
    documindExample: 'Planned fallback path (Design Area 47). The VectorSearcher interface abstracts both backends so the repo layer is unchanged.',
    tradeoffs: 'Slower insert at scale; index rebuild locks writes for minutes on large tables; great for small tenants with strong consistency needs.',
    docsUrl: 'https://github.com/pgvector/pgvector',
    docsLabel: 'pgvector',
  },
  {
    category: 'Vector DB',
    pattern: 'Shadow-index for embedding upgrades',
    problem: 'New embedding model means all old vectors are incomparable — in-place rebuild locks writes for hours.',
    solution: 'Create a second Qdrant collection; re-embed in the background; verify quality on eval set; flip read traffic via feature flag; delete old collection.',
    documindExample: 'embedding_model + embedding_version on every chunk row. Re-embed worker reads the old, writes the new. Zero downtime.',
    tradeoffs: 'Double storage during migration; re-embed cost (GPU hours); complex operational playbook.',
    docsUrl: 'https://qdrant.tech/documentation/tutorials/aliases/',
    docsLabel: 'Qdrant — Collection aliases',
  },

  // ---- Graph DB ----------------------------------------------------------
  {
    category: 'Graph DB',
    pattern: 'Neo4j for multi-hop reasoning',
    problem: 'Pure ANN misses relationships — "which doc mentions both entity A and entity B, together with entity C?"',
    solution: '(Document)-[:CONTAINS]->(Chunk)-[:MENTIONS]->(Entity) schema; 1-hop neighbor expansion from top-ANN chunks.',
    documindExample: 'GraphSearcher complements VectorSearcher in hybrid retrieval. Neo4j CB protects the caller when graph is slow.',
    tradeoffs: 'Extra store to operate; schema discipline is non-negotiable; query language (Cypher) learning curve.',
    docsUrl: 'https://neo4j.com/docs/',
    docsLabel: 'Neo4j docs',
  },

  // ---- Cache DB ----------------------------------------------------------
  {
    category: 'Cache DB',
    pattern: 'Redis with tenant-namespaced keys',
    problem: 'Shared cache = cross-tenant data leak, same class of bug as RLS bypass.',
    solution: 'Every cache op goes through Cache.tenant_key(t, k); no raw-key API; Redis keys literally start with {tenant}:.',
    documindExample: 'libs/py/documind_core/cache.py. Every read/write signature requires tenant_id. Wrong tenant_id = cache miss, never a cross-tenant hit.',
    tradeoffs: 'Small key overhead; forces discipline; developers occasionally forget and try to bypass for "admin" cases (reject in review).',
    docsUrl: 'https://redis.io/docs/',
    docsLabel: 'Redis docs',
  },
  {
    category: 'Cache DB',
    pattern: 'Answer cache (inference)',
    problem: 'LLM calls are expensive; same question asked twice should not cost twice.',
    solution: 'sha256(tenant || normalized_question || model_version || prompt_version) as key. TTL from content-change rate.',
    documindExample: 'retrieval-svc consults the cache before hitting Qdrant + inference. ~30% of production traffic is cache-hit.',
    tradeoffs: 'Stale answers after content change unless invalidation is event-driven; never cache PII responses; cost of wrong answer > cost of cache miss.',
    docsUrl: 'https://redis.io/docs/manual/eviction/',
    docsLabel: 'Redis — Cache eviction',
  },
  {
    category: 'Cache DB',
    pattern: 'Session + rate-limit state',
    problem: 'Stateless services need a shared store for sessions, tokens, rate buckets.',
    solution: 'Redis for short-lived, high-QPS state. AOF + periodic RDB for durability.',
    documindExample: 'Session TTLs, per-tenant rate buckets, idempotency cache for POSTs (24h TTL). Lives in Redis, survives pod restarts.',
    tradeoffs: 'Need Sentinel or Cluster for HA; backup/restore is less straightforward than Postgres.',
    docsUrl: 'https://redis.io/docs/management/persistence/',
    docsLabel: 'Redis persistence',
  },

  // ---- Event log ---------------------------------------------------------
  {
    category: 'Event Log',
    pattern: 'Kafka as the event backbone',
    problem: 'Services need loose coupling, retry safety, and replayable event history.',
    solution: 'CloudEvents envelope over Kafka; JSON Schema per event type; idempotent consumers dedupe on event UUID; DLQ for poison messages.',
    documindExample: 'ingestion → chunk-ready events → retrieval-svc indexer. DLQ for parse failures. schemas/events/*.json.',
    tradeoffs: 'Operational complexity (Kafka is not easy); eventual consistency; ordering guarantees require partition discipline.',
    docsUrl: 'https://kafka.apache.org/documentation/',
    docsLabel: 'Kafka docs',
  },
  {
    category: 'Event Log',
    pattern: 'Outbox (transactional event publishing)',
    problem: 'Writing to DB + publishing to Kafka is not atomic — crash between them = inconsistent state.',
    solution: 'Write the domain row AND the event to the same DB transaction (outbox table). A relay tails the outbox and publishes.',
    documindExample: 'libs/py/documind_core/outbox.py. Saga steps write via a shared connection so the domain + outbox insert commit together.',
    tradeoffs: 'Write amplification; relay lag; tight budget for relay-to-Kafka latency.',
    docsUrl: 'https://microservices.io/patterns/data/transactional-outbox.html',
    docsLabel: 'microservices.io — Transactional Outbox',
  },

  // ---- Historical / Cold DB ----------------------------------------------
  {
    category: 'Historical DB',
    pattern: 'Cold-tier Parquet on S3',
    problem: 'Hot Postgres storage grows linearly; 90-day audit log eventually dwarfs the working set.',
    solution: 'Auto-archive rows older than N days to S3 as Parquet. Analytics via DuckDB or Athena; hot DB stays small.',
    documindExample: 'Design Area 37 — planned. Audit log, finops token_usage, completed jobs are candidates.',
    tradeoffs: 'Two storage tiers to operate; queries across the boundary are slow; worth it at ~100GB+ of hot data.',
    docsUrl: 'https://duckdb.org/docs/',
    docsLabel: 'DuckDB docs',
  },
  {
    category: 'Historical DB',
    pattern: 'ILM-managed Elasticsearch',
    problem: 'Logs are cheap to write, expensive to store; searchability value decays with age.',
    solution: 'Elasticsearch ILM policy: hot 7d (SSD) → warm 30d (HDD) → cold 90d (frozen) → delete. Searchable throughout.',
    documindExample: 'documind-logs-YYYY.MM.dd indices; ILM policy deployed at cluster bootstrap; frozen tier on object storage.',
    tradeoffs: 'Queries across tiers are slower; frozen-tier search is minute-scale; storage tier tuning is continuous ops work.',
    docsUrl: 'https://www.elastic.co/guide/en/elasticsearch/reference/current/index-lifecycle-management.html',
    docsLabel: 'Elasticsearch ILM',
  },
  {
    category: 'Historical DB',
    pattern: 'Partitioned tables (Postgres-native)',
    problem: 'Single giant table — vacuum pain, slow queries, index bloat.',
    solution: 'Declarative partitioning by time (monthly or daily); drop old partitions with DROP TABLE (fast).',
    documindExample: 'finops.token_usage partitioned daily; observability.incident_log partitioned monthly. Drop old partitions in a cron job.',
    tradeoffs: 'Constraint exclusion pitfalls; cross-partition queries need planner discipline; partition key change = painful.',
    docsUrl: 'https://www.postgresql.org/docs/current/ddl-partitioning.html',
    docsLabel: 'PostgreSQL — Partitioning',
  },

  // ---- Blob / Object Store -----------------------------------------------
  {
    category: 'Blob Store',
    pattern: 'S3-compatible object storage',
    problem: 'Large files (PDFs, images) shouldn\'t live in Postgres; DB row size blows up, backups blow up.',
    solution: 'S3 or MinIO; store only the URI/ETag in the DB; signed URLs for direct-to-store upload.',
    documindExample: 'ingestion.documents stores blob_uri. Direct-to-MinIO upload via pre-signed URL; service never proxies the bytes.',
    tradeoffs: 'Two stores to back up together; eventual consistency in some configurations; bucket lifecycle rules for cost.',
    docsUrl: 'https://min.io/docs/minio/linux/index.html',
    docsLabel: 'MinIO docs',
  },

  // ---- ORM --------------------------------------------------------------
  {
    category: 'ORM Strategy',
    pattern: 'No-ORM — hand-written SQL in Repo classes',
    problem: 'ORMs hide RLS intent; SET LOCAL app.current_tenant per-txn is fragile through an ORM; "clever" queries escape review.',
    solution: 'Every SQL statement lives in a Repository class; parameterized asyncpg calls; no ORM.',
    documindExample: 'DocumentRepo, ChunkRepo, TenantRepo, AuditLogRepo — each file has every SQL the service runs. Readable, reviewable, RLS-safe.',
    tradeoffs: 'More code to write; no auto-generated DDL; no lazy-loading "magic" (which is exactly the point).',
    docsUrl: 'https://magicstack.github.io/asyncpg/current/',
    docsLabel: 'asyncpg docs',
  },
  {
    category: 'ORM Strategy',
    pattern: 'SQLAlchemy 2.0 async (alternative)',
    problem: 'Teams that want an ORM — expression language, declarative mapper, migrations via Alembic.',
    solution: 'SQLAlchemy 2.0 core + async engine + session-scoped transaction; explicit execution options for RLS session variables.',
    documindExample: 'Not used in DocuMind. Listed as an alternative because prospective contributors ask for it weekly.',
    tradeoffs: 'Familiar to Python devs; more layers between developer and wire; RLS integration requires discipline.',
    docsUrl: 'https://docs.sqlalchemy.org/',
    docsLabel: 'SQLAlchemy docs',
  },

  // ---- Reusability --------------------------------------------------------
  {
    category: 'Reusability',
    pattern: 'Base Repository class',
    problem: 'Every repo writes the same tenant_connection + logging + retry boilerplate.',
    solution: 'A common base (_connect context manager, standard error mapping, observability spans) — subclasses implement only the SQL.',
    documindExample: 'RepoBase in libs/py/documind_core. DocumentRepo, ChunkRepo etc. subclass it; each file contains only domain SQL.',
    tradeoffs: 'Inheritance is not free; base class bugs affect everyone; keep the base class tiny and stable.',
    docsUrl: 'https://martinfowler.com/eaaCatalog/repository.html',
    docsLabel: 'Fowler — Repository pattern',
  },
  {
    category: 'Reusability',
    pattern: 'Interface-first for every backend',
    problem: 'Tight coupling to a vendor makes swap-out a rewrite.',
    solution: 'Define Protocols / ABCs: VectorSearcher, GraphSearcher, EmbeddingProvider, DocumentParser, Chunker. Implementations are injected.',
    documindExample: 'retrieval-svc composes VectorSearcher + GraphSearcher + Reranker. Swap Qdrant → pgvector by changing the concrete class.',
    tradeoffs: 'Extra abstraction upfront; pays back on day one of a vendor change.',
    docsUrl: 'https://peps.python.org/pep-0544/',
    docsLabel: 'PEP 544 — Protocols',
  },
  {
    category: 'Reusability',
    pattern: 'Connection pooling',
    problem: 'Opening a connection per request kills throughput; too many connections kills the DB.',
    solution: 'asyncpg pool per service (min 2, max 10 typical); PgBouncer externally if needed; tenant set inside borrowed connection.',
    documindExample: 'DbClient owns the pool; tenant_connection() borrows + sets app.current_tenant per transaction; returns on exit.',
    tradeoffs: 'Pool sizing is per-service and per-env; under-sized = stalls; over-sized = DB connection exhaustion.',
    docsUrl: 'https://www.pgbouncer.org/',
    docsLabel: 'PgBouncer',
  },
  {
    category: 'Reusability',
    pattern: 'Shared migration runner',
    problem: 'Each service reinventing its migration loop = drift in behavior, e.g. one service leaves partial migrations applied.',
    solution: 'One runner in documind_core reads services/<svc>/migrations/*.sql in numeric order, records applied version in _migrations table.',
    documindExample: 'make migrate and the in-service startup hook both use the same runner. Idempotent. Crash-safe.',
    tradeoffs: 'Central code is load-bearing; every service depends on it. Gets heavy test coverage.',
    docsUrl: 'https://martinfowler.com/articles/evodb.html',
    docsLabel: 'Fowler — Evolutionary Database Design',
  },
];

const CATEGORY_ORDER = ['Relational', 'Vector DB', 'Graph DB', 'Cache DB', 'Event Log', 'Historical DB', 'Blob Store', 'ORM Strategy', 'Reusability'];

export default function DatabaseScenarios() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Database Scenarios</h1>
        <p className="design-areas-sub">
          Every data store in DocuMind, grouped by role. Each row is a pattern: the problem, the
          solution, the DocuMind-specific example, the trade-offs, and the canonical reference.
          Use as a menu for database-design interviews.
        </p>
        <Link href="/tools" className="sysdesign-back">← back to tool index</Link>
      </header>

      {CATEGORY_ORDER.map((cat) => {
        const rows = SCENARIOS.filter((s) => s.category === cat);
        if (rows.length === 0) return null;
        return (
          <section key={cat} className="design-areas-group">
            <h2 className="design-areas-group-title">{cat}</h2>
            <div className="method-grid">
              {rows.map((s) => (
                <article key={s.pattern} className="method-card">
                  <div className="method-card-head">
                    <h3 className="method-name">{s.pattern}</h3>
                  </div>
                  <dl className="cb-card-dl">
                    <dt>Problem</dt>
                    <dd>{s.problem}</dd>
                    <dt>Pattern</dt>
                    <dd>{s.solution}</dd>
                    <dt>DocuMind example</dt>
                    <dd>{s.documindExample}</dd>
                    <dt>Tradeoffs</dt>
                    <dd>{s.tradeoffs}</dd>
                    <DerivedRows narr={{ name: s.pattern, problem: s.problem, solution: s.solution, example: s.documindExample, category: s.category }} />
                    <dt>Reference</dt>
                    <dd>
                      <a href={s.docsUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                        {s.docsLabel} ↗
                      </a>
                    </dd>
                  </dl>
                </article>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
