/**
 * 74 design areas with full per-area explanations.
 *
 * Mirrors docs/design-areas/table/00-INDEX.md. Each entry adds three fields
 * beyond the status snapshot:
 *   why          — why this area exists (the failure mode it prevents)
 *   how          — how DocuMind actually implements it
 *   risk         — what goes wrong in production if you skip it
 *
 * Keep each field ≤ ~400 chars so cards stay scannable.
 */

export type DAStatus = 'implemented' | 'partial' | 'designed';

export type DesignArea = {
  id: string;
  group: string;
  name: string;
  status: DAStatus;
  classRef: string;
  why: string;
  how: string;
  risk: string;
};

export const DESIGN_AREAS: DesignArea[] = [
  // ---- System & Boundaries (1–8) ------------------------------------------
  {
    id: '1', group: 'System & Boundaries', name: 'System Boundary', status: 'implemented',
    classRef: 'infra/nginx/nginx.conf + services/api-gateway/cmd/main.go',
    why: 'Defines the single network surface the outside world talks to. Every request enters here; no other port is exposed.',
    how: 'NGINX terminates TLS, strips unknown headers, applies global rate limits; then the Go API Gateway validates JWT, attaches correlation-id, and routes. Everything behind this pair is mesh-internal mTLS only.',
    risk: 'Multiple entry points = multiple audit surfaces. One forgotten port becomes the breach.',
  },
  {
    id: '2', group: 'System & Boundaries', name: 'Responsibility Boundary', status: 'implemented',
    classRef: 'schema-per-service in db_client.py + migrations',
    why: 'Each service owns its data. Cross-service writes happen through APIs, never through shared tables or foreign keys.',
    how: 'Postgres schemas identity / ingestion / governance / finops / eval / observability are owned by the respective service role. No cross-schema joins allowed; analytics flows through events.',
    risk: 'Shared schemas couple deploys. A migration on "documents" can break retrieval and eval simultaneously.',
  },
  {
    id: '3', group: 'System & Boundaries', name: 'Trust Boundary', status: 'implemented',
    classRef: 'documind_core/middleware.py, encryption.py, infra/istio/20-peer-authentication.yaml',
    why: 'Marks where unauthenticated/untrusted input becomes authenticated/trusted. Everything crossing this line gets validated.',
    how: 'Middleware validates JWT, scopes, tenant context; encryption.py Fernet-encrypts secrets at rest; Istio PeerAuthentication STRICT forces mTLS between all internal services.',
    risk: 'Treating internal callers as trusted = one compromised pod owns the cluster.',
  },
  {
    id: '4', group: 'System & Boundaries', name: 'Failure Boundary', status: 'implemented',
    classRef: 'documind_core/circuit_breaker.py + breakers.py (5 specialized)',
    why: 'Contains failure within the component that caused it. One dead upstream does not cascade.',
    how: 'Generic CB + 5 specialized (Retrieval, Token, Agent-Loop, Observability, Cognitive) wrap every external call. HALF_OPEN probes test recovery without hammering.',
    risk: 'Without breakers, a slow Ollama fills every pod’s thread pool; health checks fail; pods recycle; new pods pile up — cascading outage.',
  },
  {
    id: '5', group: 'System & Boundaries', name: 'Tenant Boundary', status: 'implemented',
    classRef: 'DbClient.tenant_connection + FORCE RLS migrations',
    why: 'Tenants must never see each other’s data. Cannot rely on app-level WHERE clauses; that is one missing clause from a data-leak incident.',
    how: 'Postgres RLS policies filter by app.current_tenant; FORCE RLS ensures even the table owner obeys; three DB roles separate migrations (owner), app (NOBYPASSRLS), jobs (BYPASSRLS, audited).',
    risk: 'Miss FORCE RLS and the service role = owner = RLS no-op. Tenant A reads tenant B. We verified this exact bug before the fix.',
  },
  {
    id: '6', group: 'System & Boundaries', name: 'Control Plane', status: 'partial',
    classRef: 'services/governance-svc + policy tables',
    why: 'Separates decisions about the system (policies, flags, allowlists) from the data plane doing the work.',
    how: 'governance-svc owns feature_flags, hitl_queue, policies, prompt templates. Services read control-plane state at startup + on change events.',
    risk: 'Mixing control with data means a runaway request can mutate policy. Keep them isolated.',
  },
  {
    id: '7', group: 'System & Boundaries', name: 'Data Plane', status: 'implemented',
    classRef: 'ingestion-svc, retrieval-svc, inference-svc',
    why: 'Handles user traffic at scale. Optimized for latency and throughput; does not own policy.',
    how: 'Three services, each stateless, horizontally scaled, per-tenant rate-limited. Decisions come from the control plane; execution happens here.',
    risk: 'Putting policy in the data path adds latency and creates config-drift between instances.',
  },
  {
    id: '8', group: 'System & Boundaries', name: 'Management Plane', status: 'partial',
    classRef: 'observability-svc + Prom + Grafana + Kibana + Kiali',
    why: 'Operators need a read-only view of everything without touching production traffic.',
    how: 'observability-svc owns SLO targets + alert rules; Prometheus + Grafana + Jaeger + Kibana + Kiali provide views. Writes to this plane never block user requests.',
    risk: 'Using the data plane for ops views adds load during incidents, the worst possible moment.',
  },

  // ---- State & Async (9–20) -----------------------------------------------
  {
    id: '9', group: 'State & Async', name: 'State Model', status: 'implemented',
    classRef: 'DocumentRepo.ALLOWED_TRANSITIONS',
    why: 'Makes illegal states unrepresentable. A document cannot jump from "uploaded" to "indexed" without passing through "chunked" and "embedded".',
    how: 'Explicit state machine in DocumentRepo.ALLOWED_TRANSITIONS; UPDATE statements check the current state; illegal transition raises InvalidStateTransitionError.',
    risk: 'Implicit state = bug factory. "Failed" without "why" is worst-of-both.',
  },
  {
    id: '10', group: 'State & Async', name: 'Session State', status: 'partial',
    classRef: 'documind_core.cache (Redis)',
    why: 'User sessions, agent contexts, short-lived caches need a fast shared store that any replica can read.',
    how: 'Redis with tenant-namespaced keys and TTLs. Sessions time out; locked-out users are explicit not implicit.',
    risk: 'Storing sessions in pod memory kills horizontal scaling — every deploy logs everyone out.',
  },
  {
    id: '11', group: 'State & Async', name: 'Agent State', status: 'partial',
    classRef: 'AgentLoopCircuitBreaker + MultiHopRagAgent skeleton',
    why: 'Agents have loop depth, step counts, tool-call history. This state is dangerous unbounded.',
    how: 'Agent-Loop CB tracks depth + wall-clock + step count, trips at thresholds. State persisted in Redis so a reconnecting client continues the same agent, not a new one.',
    risk: 'Unbounded agent = unbounded spend. A bad prompt cost us real money before the breaker existed.',
  },
  {
    id: '12', group: 'State & Async', name: 'Consistency Model', status: 'implemented',
    classRef: 'tenant_connection + Kafka idempotent consumers',
    why: 'Declare what you guarantee (strong within a transaction, eventual across services) so consumers know what to expect.',
    how: 'Writes inside tenant_connection are ACID; cross-service propagation is eventual via Kafka, with idempotent consumers deduping on event UUID.',
    risk: 'Pretending "everything is consistent" leads to UI that shows stale state as fresh, or duplicated creates on retry.',
  },
  {
    id: '13', group: 'State & Async', name: 'Read Path vs Write Path', status: 'implemented',
    classRef: 'ingestion-svc (write) ≠ retrieval-svc (read)',
    why: 'Read and write workloads have different scale curves. Separating lets each scale and be cached independently.',
    how: 'ingestion-svc handles uploads and the multi-stage saga; retrieval-svc is latency-optimized with cache-through. They share no in-memory state.',
    risk: 'One service doing both = write spikes degrade read p95, and read caches complicate write consistency.',
  },
  {
    id: '14', group: 'State & Async', name: 'Admin Path Isolation', status: 'implemented',
    classRef: '/api/v1/admin/* in api-gateway',
    why: 'Admin traffic must never be rate-limited alongside user traffic, and must require elevated auth.',
    how: 'Routes prefixed /api/v1/admin/* have their own rate bucket, require admin-scoped JWT, and are not counted in user SLOs.',
    risk: 'A flood of user requests = admins locked out during the incident they need to fix.',
  },
  {
    id: '15', group: 'State & Async', name: 'Evaluation Path Isolation', status: 'implemented',
    classRef: 'evaluation-svc + eval schema',
    why: 'Evals run heavy queries. Must not degrade live retrieval.',
    how: 'evaluation-svc hits frozen snapshots or a read replica. Its own schema, its own Prometheus namespace, its own rate bucket.',
    risk: 'Running an eval on live prod = p95 spike right when the eval is trying to measure p95. Noise eats signal.',
  },
  {
    id: '16', group: 'State & Async', name: 'Sync vs Async', status: 'implemented',
    classRef: 'run_saga_inline flag + Kafka consumer',
    why: 'Sync is simpler and traceable; async is necessary for long jobs. Be explicit, not accidental.',
    how: 'Short operations run inline. Long ones (chunk+embed+index) become Kafka events consumed by workers. The flag forces explicit choice.',
    risk: 'Blocking a user request on a 5-minute embedding job = timeout, retry, duplicate work.',
  },
  {
    id: '17', group: 'State & Async', name: 'Event-Driven Design', status: 'implemented',
    classRef: 'documind_core/kafka_client.py + schemas/events/*.json',
    why: 'Loose coupling. Ingestion does not need to know retrieval exists. Add consumers without touching producers.',
    how: 'CloudEvents envelope over Kafka; JSON Schemas versioned per event type; producers/consumers validate against the schema registry.',
    risk: 'Direct RPCs between services = deploy ordering constraints and cascading failures.',
  },
  {
    id: '18', group: 'State & Async', name: 'Workflow Orchestration', status: 'implemented',
    classRef: 'ingestion-svc/app/saga/document_saga.py',
    why: 'Multi-step business flows need explicit orchestration so you know where you are when step 5 fails.',
    how: 'DocumentIngestionSaga: parse → chunk → embed → index → stamp-model. Each step reads-writes through the same transaction where possible; state transitions are logged.',
    risk: 'Implicit orchestration = ten places re-implementing step ordering, each with a subtly different compensation strategy.',
  },
  {
    id: '19', group: 'State & Async', name: 'Compensation Logic', status: 'implemented',
    classRef: 'DocumentIngestionSaga._run_compensations',
    why: 'Distributed transactions do not exist. Compensations are your only recourse when step N fails after steps 1..N-1 succeeded.',
    how: 'Each step has a _compensate_* counterpart. On failure, the saga walks the completed steps in reverse and compensates each. recovery-worker picks up stuck sagas.',
    risk: 'Half-completed sagas leak resources (Qdrant entries without DB rows, DB rows without Qdrant entries) — silent data drift.',
  },
  {
    id: '20', group: 'State & Async', name: 'Idempotency Strategy', status: 'implemented',
    classRef: 'IdempotencyStore + IdempotencyMiddleware',
    why: 'At-least-once delivery + client retries = duplicate resources unless idempotency keys dedupe.',
    how: 'Client sends Idempotency-Key header. Middleware caches the first response for 24h. Re-submit within window returns the cached 201, never creates a second resource.',
    risk: 'Without it, one network blip during upload = two identical documents, two embedding bills, confused users.',
  },

  // ---- Services (21–29) ---------------------------------------------------
  {
    id: '21', group: 'Services', name: 'Service Decomposition', status: 'implemented',
    classRef: '10 services; Go for IO, Python for ML',
    why: 'Different failure domains need different boundaries. Ingestion (throughput-bound) ≠ inference (latency+cost-bound) ≠ eval (batch).',
    how: '10 services, clear ownership. Go for I/O-bound paths (gateway, identity), Python for ML-bound paths (ingestion, retrieval, inference, eval).',
    risk: 'Monolith = any one bad workload blocks all of them. Small decomposition = painful debugging. Medium is the goal.',
  },
  {
    id: '22', group: 'Services', name: 'Identity Service', status: 'partial',
    classRef: 'services/identity-svc (Go skeleton + proto)',
    why: 'Auth must be isolated so compromising any other service does not yield tokens.',
    how: 'Go service mints short-lived JWTs, manages API keys (Fernet-encrypted), rotates keys, and publishes user events.',
    risk: 'Auth in the main app = compromise of any endpoint = full auth compromise.',
  },
  {
    id: '23', group: 'Services', name: 'Knowledge Ingestion Service', status: 'implemented',
    classRef: 'services/ingestion-svc',
    why: 'The heaviest service. Parsing PDFs, chunking, embedding — must be isolated so a bad upload does not block queries.',
    how: 'FastAPI + saga orchestrator + Kafka workers for chunk/embed. Every document state explicitly tracked.',
    risk: 'Combining with query path = a big upload tanks p95 for every user on the tenant.',
  },
  {
    id: '24', group: 'Services', name: 'Retrieval Service', status: 'implemented',
    classRef: 'services/retrieval-svc',
    why: 'Query latency is the single biggest UX lever. Dedicate a service optimized for it.',
    how: 'Hybrid: Qdrant ANN + Neo4j graph + cross-encoder rerank. Cache-through. p95 budget 800ms enforced by CB.',
    risk: 'Slow retrieval = users think the product is broken even when inference is instant.',
  },
  {
    id: '25', group: 'Services', name: 'Inference Service', status: 'implemented',
    classRef: 'services/inference-svc',
    why: 'LLM calls have their own resource profile (GPU, token budget, latency tail). Isolated service, isolated scale.',
    how: 'Wraps Ollama/vLLM calls; applies PromptInjectionDetector, PIIScanner, ResponsibleAIChecker, CCB.',
    risk: 'Running LLM inline with orchestration = token budget overruns take down everything.',
  },
  {
    id: '26', group: 'Services', name: 'Evaluation Service', status: 'implemented',
    classRef: 'services/evaluation-svc',
    why: 'Eval is batch-heavy and non-user-facing; must not sit on the hot path.',
    how: 'POST /api/v1/evaluation/run enqueues jobs; workers compute precision@k, nDCG, faithfulness, drift; results stored in eval schema.',
    risk: 'Running evals inline adds seconds to user requests.',
  },
  {
    id: '27', group: 'Services', name: 'Governance Service', status: 'partial',
    classRef: 'services/governance-svc (Go skeleton)',
    why: 'HITL queue, audit log, policy decisions, prompt registry — control-plane concerns.',
    how: 'Go service owns governance schema; surfaces HITL + policy APIs; will host reviewer UI.',
    risk: 'Audit and HITL in the main app = compliance gaps if the app is deployed in regions with different rules.',
  },
  {
    id: '28', group: 'Services', name: 'Observability Service', status: 'partial',
    classRef: 'services/observability-svc (Go skeleton + alert rules)',
    why: 'SLOs, alert rules, incident log are business state, not raw telemetry. They deserve their own service.',
    how: 'Owns observability schema (slo_targets, alert_rules, incident_log); exposes SLO status + alert config APIs.',
    risk: 'SLOs in Prometheus alone = gone when Prometheus restarts. Need durable business state.',
  },
  {
    id: '29', group: 'Services', name: 'FinOps Service', status: 'partial',
    classRef: 'services/finops-svc (Go skeleton + shadow-pricing)',
    why: 'Token usage + budget + billing = compliance surface. Access must be narrow.',
    how: 'Go service ingests token events, maintains per-tenant budgets, powers Token CB decisions, reconciles billing periods.',
    risk: 'Billing data mixed with app data = broad access = insider risk.',
  },

  // ---- Contracts & Retrieval (30–42) --------------------------------------
  {
    id: '30', group: 'Contracts & Retrieval', name: 'API Contract Strategy', status: 'implemented',
    classRef: 'REST (OpenAPI) + gRPC protos',
    why: 'Contracts are the stable part. Internal refactors must not break consumers.',
    how: 'REST external (OpenAPI auto-generated from FastAPI), gRPC internal (proto-first). Versioned paths /api/v1/*.',
    risk: 'Implicit contracts break silently. v1 without a plan for v2 = painful migration later.',
  },
  {
    id: '31', group: 'Contracts & Retrieval', name: 'Event Contract Strategy', status: 'implemented',
    classRef: 'schemas/events/*.json (CloudEvents)',
    why: 'Events live forever in logs and warehouses. Contract breakage 6 months later is someone else’s problem — avoid.',
    how: 'CloudEvents envelope + JSON Schema per event; event_version field; backward-compatible evolution rules documented.',
    risk: 'Mutating a schema in place silently corrupts downstream analytics.',
  },
  {
    id: '32', group: 'Contracts & Retrieval', name: 'Prompt Contract Strategy', status: 'implemented',
    classRef: 'PromptBuilder + PROMPT_TEMPLATES + governance.prompts',
    why: 'Prompts change model behavior immediately. Version them like code.',
    how: 'Templates in the governance.prompts table; every decision record stamps prompt_version; roll back by flipping the active version flag.',
    risk: 'Untracked prompt edit = behavior regression with no git blame trail.',
  },
  {
    id: '33', group: 'Contracts & Retrieval', name: 'Output Contract Strategy', status: 'implemented',
    classRef: 'GuardrailChecker + CCB signals',
    why: 'Callers depend on response shape + citation structure. Random model output violating it breaks integrations.',
    how: 'Pydantic response models; GuardrailChecker rejects malformed LLM output; CCB signals can BLOCK before a bad output streams.',
    risk: 'Model free-text in place of structured response = client parse errors, broken downstreams.',
  },
  {
    id: '34', group: 'Contracts & Retrieval', name: 'Retrieval Schema', status: 'implemented',
    classRef: 'retrieval-svc/app/schemas + proto RetrievedChunk',
    why: 'Retrieval is an internal product surface — inference and eval both consume it. Its contract is load-bearing.',
    how: 'RetrievedChunk (chunk_id, doc_id, score, content, neighbors[], metadata). gRPC + REST serve the same shape.',
    risk: 'Unstructured retrieval → downstream code re-parses the same data five different ways.',
  },
  {
    id: '35', group: 'Contracts & Retrieval', name: 'Knowledge Lifecycle', status: 'implemented',
    classRef: 'document state machine (10 states)',
    why: 'Documents go through many states: uploaded, parsing, chunking, embedding, indexing, active, archived, failed, reindexing, deleted. Each is observable.',
    how: 'Explicit states in DocumentRepo; every transition logs; failed can retry or compensate.',
    risk: 'Binary "done/not done" = debugging a stuck document means reading three services’ logs to guess where it is.',
  },
  {
    id: '36', group: 'Contracts & Retrieval', name: 'Source Trust Model', status: 'designed',
    classRef: 'spec only',
    why: 'Not all sources are equal. An internal policy PDF is ground truth; a web scrape is suggestive.',
    how: '(Designed, not built) source_trust_score per document; retrieval rerank weights by trust; citations label the source tier.',
    risk: 'Treating Wikipedia and the company handbook as equal = confidently-wrong answers.',
  },
  {
    id: '37', group: 'Contracts & Retrieval', name: 'Historical Knowledge Policy', status: 'designed',
    classRef: 'spec only (cold-tier archive)',
    why: 'Hot Postgres grows linearly. Audit log and old eval runs belong on cheap cold storage.',
    how: '(Designed) auto-archive rows older than N days to S3 Parquet; DuckDB / Athena for analytics; hot DB stays small.',
    risk: 'Unbounded growth = Postgres slows; vacuum pain; storage bill creeps.',
  },
  {
    id: '38', group: 'Contracts & Retrieval', name: 'Index Lifecycle', status: 'partial',
    classRef: 'QdrantRepo.ensure_collection + zero-downtime swap doc',
    why: 'Indexes need to be created, migrated (new embedding model), and retired without downtime.',
    how: 'ensure_collection + shadow-index pattern: new collection, re-embed, flip read traffic, delete old.',
    risk: 'In-place rebuild = write locks = minutes of outage every model upgrade.',
  },
  {
    id: '39', group: 'Contracts & Retrieval', name: 'Embedding Lifecycle', status: 'partial',
    classRef: 'model-versioning fields; re-embed worker deferred',
    why: 'Embeddings from different models are incomparable. Mixing them in one index is silent quality drop.',
    how: 'embedding_model + embedding_version stamped on every chunk; re-embed flow documented; worker under construction.',
    risk: 'Model upgrade without re-embed = retrieval quality regresses, no alarm, users just notice.',
  },
  {
    id: '40', group: 'Contracts & Retrieval', name: 'Cache Architecture', status: 'implemented',
    classRef: 'documind_core/cache.py',
    why: 'Inference is expensive. Retrieval is cheap but not free. Cache carefully-chosen keys.',
    how: 'Redis with tenant-namespaced keys. Answer cache keyed on sha256(tenant||question||model_version). TTL based on content change rate.',
    risk: 'No cache = unneeded token spend. Bad cache = stale answers with no audit trail.',
  },
  {
    id: '41', group: 'Contracts & Retrieval', name: 'Cache Consistency', status: 'implemented',
    classRef: 'TTL + invalidate_prefix + event-driven helpers',
    why: 'Stale cache is worse than no cache when users notice.',
    how: 'TTL as baseline; document-change events trigger invalidate_prefix for affected tenants; cache-busting available on explicit admin request.',
    risk: 'Caching without an invalidation plan = "why is this user seeing yesterday’s answer?" tickets.',
  },
  {
    id: '42', group: 'Contracts & Retrieval', name: 'Tenant-Aware Cache', status: 'implemented',
    classRef: 'Cache.tenant_key namespace',
    why: 'Cross-tenant cache hit = cross-tenant data leak — same class of bug as RLS bypass.',
    how: 'tenant_key(t, k) forces every cache op to carry the tenant. The API never accepts a raw key.',
    risk: 'One global cache with no tenant prefix = first user’s sensitive answer cached for everyone.',
  },

  // ---- Capacity & Release (43–55) ----------------------------------------
  {
    id: '43', group: 'Capacity & Release', name: 'Capacity Model', status: 'partial',
    classRef: 'HPA manifests + inference_inflight metric',
    why: 'You cannot operate what you cannot forecast. Capacity = throughput ceilings per service per tenant.',
    how: 'HPA scales replicas on CPU + custom metrics (inference_inflight, queue_depth). Per-tenant caps at the gateway.',
    risk: 'No model = rush-buy compute during incidents; over-provision in quiet periods; bill surprises.',
  },
  {
    id: '44', group: 'Capacity & Release', name: 'Queue Strategy', status: 'implemented',
    classRef: 'Kafka + DLQ in kafka_client.py',
    why: 'Back-pressure needs somewhere to go. Queues absorb spikes; DLQ catches poison.',
    how: 'Kafka topics per event type; 3-try exponential backoff; failed messages parked on DLQ with alerting.',
    risk: 'No queue = producer retries hammer downstream. No DLQ = poison message blocks the partition forever.',
  },
  {
    id: '45', group: 'Capacity & Release', name: 'Backpressure Strategy', status: 'implemented',
    classRef: '4 layers: nginx → gateway → service → CB',
    why: 'Rate limits alone are not enough. You need graduated pushback before hitting compute limits.',
    how: 'Four layers: edge rate-limit → gateway per-tenant bucket → service-local semaphore → circuit breaker on upstream.',
    risk: 'Single-layer limit = one bursty tenant still takes down the shared infra past the limit.',
  },
  {
    id: '46', group: 'Capacity & Release', name: 'Database Strategy', status: 'implemented',
    classRef: 'Postgres schema-per-service + RLS + WAL',
    why: 'One Postgres cluster, many schemas — simple to operate, clear ownership, RLS-enforced boundaries.',
    how: 'WAL mode; connection pooling; schema-per-service; RLS with role separation; migrations idempotent and numbered.',
    risk: 'One schema for everything = deploys coupled; NoSQL where Postgres fits = reinvent transactions badly.',
  },
  {
    id: '47', group: 'Capacity & Release', name: 'Vector DB Strategy', status: 'implemented',
    classRef: 'QdrantRepo HNSW + scalar quantization',
    why: 'ANN structure + quantization = 10x cost reduction with ~1% precision loss. Worth it.',
    how: 'Qdrant HNSW with scalar quantization; tenant_id as a mandatory payload filter; shadow-index for model upgrades.',
    risk: 'Flat-index at scale = unbounded RAM. Mix models in one index = nonsense distances.',
  },
  {
    id: '48', group: 'Capacity & Release', name: 'Graph Strategy', status: 'implemented',
    classRef: 'Neo4jRepo entity-chunk-document',
    why: 'Multi-hop reasoning over documents (entity A mentioned with entity B in source C) beats pure ANN on compound questions.',
    how: '(Document)-[:CONTAINS]->(Chunk)-[:MENTIONS]->(Entity). 1-hop expansion from top ANN chunks.',
    risk: 'Graph without schema discipline = spaghetti that nobody wants to query.',
  },
  {
    id: '49', group: 'Capacity & Release', name: 'HA Strategy', status: 'implemented',
    classRef: '2+ replicas + anti-affinity + probes',
    why: 'One replica = node failure = outage. Two + anti-affinity = survivable.',
    how: 'minReplicas: 2, anti-affinity across nodes, readiness + liveness probes, graceful shutdown on SIGTERM.',
    risk: 'Single-replica "production" = the first AZ blip is a P1.',
  },
  {
    id: '50', group: 'Capacity & Release', name: 'DR Strategy', status: 'partial',
    classRef: 'runbooks/DR_RUNBOOK.md; automated restore test deferred',
    why: 'Backups that have never been restored are not backups.',
    how: 'PITR for Postgres; periodic Qdrant/Neo4j snapshots; runbook for failover. (Automated restore drill is the remaining gap.)',
    risk: 'Unverified backups = discovering corruption mid-incident = extended outage.',
  },
  {
    id: '51', group: 'Capacity & Release', name: 'Multi-Region Strategy', status: 'designed',
    classRef: 'design docs only',
    why: 'Regional data residency (GDPR) and DR require two regions at minimum.',
    how: '(Designed) active-passive first, active-active later; tenant pinning to region; Kafka MirrorMaker for cross-region events.',
    risk: 'One region = full outage during cloud regional incident. Prospective enterprise customers ask on day one.',
  },
  {
    id: '52', group: 'Capacity & Release', name: 'Blast Radius Control', status: 'implemented',
    classRef: 'NetworkPolicy + Istio AuthorizationPolicy + tenant quotas',
    why: 'Contain failures so one bad tenant or one compromised service does not spread.',
    how: 'Default-deny NetworkPolicy; per-service egress allowlists; Istio AuthorizationPolicy peer-to-peer; per-tenant rate / token quotas.',
    risk: 'Flat network + open auth = RCE in one service = access to everything.',
  },
  {
    id: '53', group: 'Capacity & Release', name: 'Release Isolation', status: 'implemented',
    classRef: 'Istio VS canary + K8s rolling',
    why: 'Small blast radius for new code = smaller regret surface when something’s wrong.',
    how: 'Istio VirtualService 90/10 canary; K8s maxUnavailable: 0 rolling; CI-gated artifact tagging.',
    risk: 'Big-bang releases = big-bang rollbacks = angry users.',
  },
  {
    id: '54', group: 'Capacity & Release', name: 'Rollback Isolation', status: 'implemented',
    classRef: 'kubectl rollout undo + feature-flag kill switches',
    why: 'Most production problems are mitigated, not solved, in the first 15 minutes. Rollback must be instant.',
    how: 'Container rollback via rollout undo; feature-flag kill switches disable new code paths without a redeploy.',
    risk: 'No rollback plan = a bad release becomes a 6-hour debug session at 3am.',
  },
  {
    id: '55', group: 'Capacity & Release', name: 'Feature Flag Strategy', status: 'partial',
    classRef: 'governance.feature_flags schema; runtime client deferred',
    why: 'Deploy risky changes dark; enable per-tenant / per-user / percentage of traffic.',
    how: 'governance.feature_flags table; SDK reads flags at startup + on event. (Runtime client wiring is the remaining piece.)',
    risk: 'No flags = every release is all-or-nothing. Big bet every Tuesday.',
  },

  // ---- Policy & Eval (56–67) ---------------------------------------------
  {
    id: '56', group: 'Policy & Eval', name: 'Policy-as-Code', status: 'partial',
    classRef: 'governance.policies table; CEL engine deferred',
    why: 'Policy rules in comments or wiki rot. Express as code, version-controlled, evaluated at runtime.',
    how: 'Policies stored in governance.policies with CEL expression strings; engine evaluates on every decision. (CEL runtime integration deferred.)',
    risk: 'Human-interpreted policies drift between reviewers. Auditors want reproducibility.',
  },
  {
    id: '57', group: 'Policy & Eval', name: 'Human-in-the-Loop', status: 'partial',
    classRef: 'governance.hitl_queue schema; reviewer UI deferred',
    why: 'When AI confidence is low or impact is high, humans must make the final call.',
    how: 'Low-confidence decisions or high-risk tools escalate to governance.hitl_queue; reviewer resolves via the governance-svc UI (in progress).',
    risk: 'Auto-deploying AI decisions to regulated domains = regulatory exposure.',
  },
  {
    id: '58', group: 'Policy & Eval', name: 'Feedback Architecture', status: 'partial',
    classRef: 'eval.feedback schema; capture endpoints deferred',
    why: 'User feedback is gold for retraining and prompt tuning. Need a structured capture path.',
    how: 'eval.feedback table with decision_id, rating, comment, metadata. Capture endpoints wired per surface. (Active learning loop not yet built.)',
    risk: 'Feedback lost to Slack and ticketing = no signal = no improvement.',
  },
  {
    id: '59', group: 'Policy & Eval', name: 'Offline Evaluation', status: 'implemented',
    classRef: 'evaluation-svc POST /run + metrics',
    why: 'Before touching prod, measure on a frozen dataset with labeled answers.',
    how: 'evaluation-svc queues runs; computes precision@k, nDCG, faithfulness, answer-relevance; results in eval schema.',
    risk: 'Deploying prompt changes without offline eval = learning from users = expensive way to A/B test.',
  },
  {
    id: '60', group: 'Policy & Eval', name: 'Online Evaluation', status: 'designed',
    classRef: 'sampling consumer not yet built',
    why: 'Offline ≠ online. Real user traffic exposes prompt injection, long-tail queries, distribution drift.',
    how: '(Designed) sampling consumer reads a small % of live traffic, evaluates against reference, pushes drift metrics.',
    risk: 'Blind spots at scale. First news of a regression comes from support tickets.',
  },
  {
    id: '61', group: 'Policy & Eval', name: 'Regression Gate', status: 'partial',
    classRef: 'AIops alert rule active; compute-and-compare deferred',
    why: 'CI must block merges that regress retrieval/answer quality, not just ones that break unit tests.',
    how: 'Alert on drift metrics; planned: CI job compares eval metrics to last-merged baseline, blocks if delta > threshold.',
    risk: 'Unit-tests-green-ship-it culture + AI systems = quality regressions reach prod.',
  },
  {
    id: '62', group: 'Policy & Eval', name: 'Observability by Design', status: 'implemented',
    classRef: 'documind_core.observability + breaker-guarded exporters',
    why: 'Observability bolted on afterwards is always incomplete. Design for it from day one.',
    how: 'OTel SDK on every service, correlation-id propagation, structured JSON logs, Prometheus metrics, Observability CB around every exporter.',
    risk: 'Retrofitting observability means instrumenting at the very moment you are already firefighting.',
  },
  {
    id: '63', group: 'Policy & Eval', name: 'Auditability by Design', status: 'partial',
    classRef: 'governance.audit_log; hash-chain writer deferred',
    why: 'Regulated customers will ask who did what when. The answer must exist before they ask.',
    how: 'Every admin action + AI decision logged with actor, tenant, correlation-id, prev-state, next-state. Hash-chaining for tamper evidence is the remaining piece.',
    risk: 'No audit trail = fail the audit, lose the customer.',
  },
  {
    id: '64', group: 'Policy & Eval', name: 'SLO-Driven Design', status: 'implemented',
    classRef: 'observability.slo_targets + Prom alerts',
    why: 'Without SLOs, "fast enough" is negotiated every month. With SLOs, it is measured.',
    how: 'observability.slo_targets seeds availability, query_latency_p95, retrieval_precision, answer_faithfulness; Prometheus alerts fire on error-budget burn.',
    risk: 'No SLOs = endless debates. Every team lowers the bar to ship.',
  },
  {
    id: '65', group: 'Policy & Eval', name: 'Design-for-Change', status: 'implemented',
    classRef: 'every external dep behind an interface',
    why: 'Every external tool will change pricing, license, or API. You will switch vendors — design for it.',
    how: 'Interfaces: VectorSearcher, GraphSearcher, Chunker, EmbeddingProvider, DocumentParser. Implementations are swap-in.',
    risk: 'Tight coupling to one vendor = held hostage on pricing or unable to meet residency rules.',
  },
  {
    id: '66', group: 'Policy & Eval', name: 'Design-for-Debuggability', status: 'implemented',
    classRef: '?debug=true + correlation IDs + CB metrics',
    why: 'Incident response time is dominated by "where is this request?" Make the answer trivial.',
    how: '?debug=true dumps breaker states + CCB snapshot + retrieval trace in the response; correlation-id ties logs/traces/metrics together.',
    risk: 'Debug-by-reading-three-dashboards = minutes of MTTR, not seconds.',
  },
  {
    id: '67', group: 'Policy & Eval', name: 'Socio-Technical', status: 'implemented',
    classRef: 'docs/runbooks/* + per-service ownership',
    why: 'Software is operated by humans. Runbooks, ownership, on-call boundaries are load-bearing.',
    how: 'Per-service runbook in docs/runbooks/; CODEOWNERS maps directories to teams; on-call rotation per service.',
    risk: 'Systems with no owner = bugs nobody fixes = bitrot.',
  },

  // ---- AI Governance Extras (E1–E7) --------------------------------------
  {
    id: 'E1', group: 'AI Governance (Extras)', name: 'Cognitive Circuit Breaker', status: 'implemented',
    classRef: 'libs/py/documind_core/ccb.py',
    why: 'Standard breakers protect against external failure. CCB protects against model failure — agent loops, hallucination drift, jailbreak chaining.',
    how: 'Signals (RepetitionSignal, DriftSignal, RuleBreach, ForbiddenPattern, CitationDeadline) watch the token stream; breaker opens when thresholds are crossed.',
    risk: 'Unbounded LLM loop = $20 bill for one prompt before anyone notices. CCB is the only defense.',
  },
  {
    id: 'E2', group: 'AI Governance (Extras)', name: 'Debuggability (AI-specific)', status: 'implemented',
    classRef: 'InterpretabilityTrace + ?debug=true + CB snapshot',
    why: 'AI debugging needs the retrieval set, the prompt, the model version, and every guardrail decision — all correlated.',
    how: 'InterpretabilityTrace records every stage; ?debug=true returns it inline; CCB snapshot shows why it opened.',
    risk: 'LLM "that felt wrong" tickets with no trace = expensive guesswork.',
  },
  {
    id: 'E3', group: 'AI Governance (Extras)', name: 'Explainability (XAI)', status: 'implemented',
    classRef: 'ai_governance.py::AIExplainer',
    why: 'Users and auditors need "why this answer?" at the decision level, not "because the model said so".',
    how: 'AIExplainer produces {top_sources, confidence, reasoning_steps, alternative_answers_considered} per decision.',
    risk: 'Opaque AI = users do not trust it, auditors reject it.',
  },
  {
    id: 'E4', group: 'AI Governance (Extras)', name: 'Responsibility (RAI)', status: 'implemented',
    classRef: 'ai_governance.py::ResponsibleAIChecker',
    why: 'Toxicity, bias, disallowed content, PII exfiltration — output must be scanned before it returns.',
    how: 'ResponsibleAIChecker runs on the output before emit. Fail-closed. Violations go to audit + HITL if confidence is low.',
    risk: 'One toxic response in prod = brand damage + possible legal exposure.',
  },
  {
    id: 'E5', group: 'AI Governance (Extras)', name: 'Secure AI', status: 'implemented',
    classRef: 'PromptInjectionDetector + AdversarialInputFilter + PIIScanner',
    why: 'Prompt injection, adversarial inputs, PII leakage — attacker surface is new but real.',
    how: 'Defense in depth: regex + classifier for injection; char-level adversarial filter; regex PII scanner. Fail-closed.',
    risk: 'No defense = "ignore previous instructions" jailbreaks + "list every email in the docs" exfil. Both happen weekly.',
  },
  {
    id: 'E6', group: 'AI Governance (Extras)', name: 'Portability', status: 'implemented',
    classRef: 'interface-based; vLLM/Ollama compat; cloud-agnostic K8s',
    why: 'Vendor lock-in is the hidden cost. Swap models, swap cloud, swap mesh — design enables it.',
    how: 'Interfaces hide providers; K8s manifests avoid cloud-specific resources; protos decouple service contracts.',
    risk: 'Locked to one LLM = pricing pressure + compliance risk + no exit strategy.',
  },
  {
    id: 'E7', group: 'AI Governance (Extras)', name: 'Interpretability (business-step)', status: 'implemented',
    classRef: 'ai_governance.py::InterpretabilityTrace',
    why: 'Business stakeholders need "what business steps did the AI take?" not model internals.',
    how: 'InterpretabilityTrace emits user-facing steps: "retrieved 5 sources", "ranked by relevance", "applied policy X", "escalated to HITL".',
    risk: 'Model-only explanation = stakeholders do not trust production decisions.',
  },
];

export const STATUS_META: Record<DAStatus, { label: string; emoji: string; cssClass: string }> = {
  implemented: { label: 'Implemented', emoji: '✅', cssClass: 'status-implemented' },
  partial:     { label: 'Partial',     emoji: '🟡', cssClass: 'status-partial' },
  designed:    { label: 'Designed',    emoji: '❌', cssClass: 'status-designed' },
};

export const GROUP_ORDER = [
  'System & Boundaries',
  'State & Async',
  'Services',
  'Contracts & Retrieval',
  'Capacity & Release',
  'Policy & Eval',
  'AI Governance (Extras)',
];
