# Areas 9–20 · State, Consistency, Paths, Sync/Async, Events, Sagas, Idempotency

## Area 9 · State Model

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/ingestion-svc/app/repositories/document_repo.py` → `ALLOWED_TRANSITIONS` |
| **Components** | State enum · Transition matrix · Optimistic lock (`version`) · Audit trail |
| **Technical details** | Each domain entity has an explicit FSM. `ALLOWED_TRANSITIONS` rejects invalid jumps at repo level. `version` column prevents lost-update on concurrent writes. |
| **Implementation** | `document_repo.transition_state(to_state, expected_from)` validates against the transition map and updates with `WHERE version = $old` — zero rows affected means concurrent modification. |
| **Tools & frameworks** | `transitions` (PyPI) · `xstate` (JS) · Temporal · custom table-driven FSM |
| **How to implement** | 1. Enumerate states · 2. Map allowed transitions · 3. Each transition logs to audit · 4. Add `version` column · 5. Reject invalid in code, not DB trigger (easier to test). |
| **Real-world example** | Doc goes UPLOADED→PARSING→FAILED. Attempt to go FAILED→ACTIVE directly is rejected; must go FAILED→PARSING first. |
| **Pros** | Invalid states can't happen · Predictable ops behavior · Audit-friendly |
| **Cons** | Every new transition is a code change · Table-driven FSMs can grow |
| **Limitations** | Hard to model parallel sub-states (use nested FSMs if needed) · Doesn't model time |
| **Recommendations** | Keep transitions small (< 15 states) · Every state has an owner · Don't reuse states across entities |
| **Challenges** | FSM refactors with live data · Back-compat on transitions · Reporting across states |
| **Edge cases + solutions** | Stuck state → recovery worker (like saga recovery) · Concurrent transitions → `version` optimistic lock · Legacy data with invalid state → one-time migration |
| **Alternatives** | No explicit FSM (boolean flags) · Event-sourced state · Actor-based state machines (Orleans, Akka) |

---

## Area 10 · Session State

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — Redis plumbing in place; no session-service yet |
| **Class / file** | `libs/py/documind_core/cache.py`, `rate_limiter.py` use tenant-namespaced Redis; session helpers documented in spec |
| **Components** | Redis keys (`session:{id}`) · TTL · Conversation history (sorted set) · Last-retrieved context for follow-ups |
| **Technical details** | Externalized state — no pod holds session data in memory. Sticky sessions NOT used. |
| **Implementation** | `session:{sid}` → JSON blob (user_id, tenant_id, roles, preferences). `session:{sid}:history` → sorted set of `(ts, message)`. TTL refreshed on activity. |
| **Tools & frameworks** | Redis · Valkey · Elasticache · Upstash · Memorystore |
| **How to implement** | 1. Session key schema · 2. JWT carries session_id · 3. TTL 30min, rolling · 4. Explicit logout deletes · 5. Per-tenant session quotas. |
| **Real-world example** | User logs in → session in Redis · pod 3 serves query 1 · pod 7 serves query 2 · both read same session; follow-up "tell me more about that" uses stored context from query 1. |
| **Pros** | Any pod serves any request · Zero-downtime rolling deploys · Simple horizontal scale |
| **Cons** | Redis is a SPOF unless clustered · Serialization overhead · Session TTL tuning |
| **Limitations** | Very chatty sessions hit Redis hot · No offline replay without Kafka mirror |
| **Recommendations** | Short TTL + explicit refresh · Cap history length (trim oldest) · Never store PII in session; keep references |
| **Challenges** | Cross-region session replication · Re-auth without disrupting UX · Session hijack prevention |
| **Edge cases + solutions** | Redis down → fail gracefully (return 503, not wrong user's session) · Session too large → store pointer, materialize on demand · Very long convos → summarize-and-trim |
| **Alternatives** | JWT-as-session (stateless but larger) · DynamoDB · CockroachDB with TTL · sticky cookies (avoid) |

---

## Area 11 · Agent State

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — AgentLoopCircuitBreaker + MultiHopRagAgent skeleton |
| **Class / file** | `libs/py/documind_core/breakers.py::AgentLoopCircuitBreaker`, `services/inference-svc/app/agents/multi_hop_agent.py` |
| **Components** | Per-run state (steps, elapsed, tool_calls, last_hash) · Hot store (Redis) · Cold store (Postgres) · Loop/timeout/budget guardrails |
| **Technical details** | Agent runs are PER-REQUEST scoped. Guardrails: max_steps=5, total_timeout=120s, per-step_timeout=30s, loop-detection window=3. |
| **Implementation** | `AgentLoopCircuitBreaker.start()` resets per-run state. `check_before_step()` and `record_step(action, result_hash)` enforce guards. Snapshot persisted to Postgres on completion. |
| **Tools & frameworks** | LangGraph · AutoGen · CrewAI · Temporal (for durable agents) · Redis for hot state |
| **How to implement** | 1. Bound max_steps (≤ 5 for most) · 2. Hash each step's output for loop detection · 3. Persist trace for audit · 4. User-abort path. |
| **Real-world example** | Multi-hop RAG: decomposes query → retrieves sub-chunks → synthesizes. If planner generates same action 3x → LOOP_DETECTED → abort with partial answer. |
| **Pros** | Runaway agents bounded · Explainable trace per run · Replay for debug |
| **Cons** | State grows fast · Memory pressure on long runs · Hard to get decomposition right |
| **Limitations** | Stateless planner may re-plan loops · Tool-budget picking is empirical |
| **Recommendations** | Log every step · Visualize the step graph in debug UI · Allow user to abort |
| **Challenges** | Knowing when to stop vs when to retry · Hallucinated tool calls · Multi-agent coordination |
| **Edge cases + solutions** | Same-action different-result = valid (exclude from loop detection) · Network timeout inside a step → circuit-breaker, no retry if idempotency unknown |
| **Alternatives** | Bounded while-loop · Temporal workflow · AWS Step Functions |

---

## Area 12 · Consistency Model

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `DbClient` (strong/Postgres), `QdrantRepo`/`Neo4jRepo` (eventual), `kafka_client.py` (at-least-once) |
| **Components** | Per-store consistency guarantees · Saga · Idempotent consumers · Read-your-writes tokens |
| **Technical details** | Each store uses its native consistency. Cross-store consistency via saga, NOT 2PC. |
| **Implementation** | Postgres SERIALIZABLE for critical; READ COMMITTED default. Qdrant eventual. Neo4j causal. Redis eventual with TTL. Kafka at-least-once; consumers dedupe. |
| **Tools & frameworks** | Postgres MVCC · Qdrant · Neo4j · Kafka · `aiokafka` · Saga libs (SagaPy, Temporal) |
| **How to implement** | 1. Pick per-store level · 2. No distributed tx · 3. Idempotent writes · 4. Consumer dedup table · 5. Monitor replication lag. |
| **Real-world example** | Upload → doc row + chunks (Postgres strong) · embeddings (Qdrant eventual, visible to readers shortly after) · entities (Neo4j causal, visible after session commit). |
| **Pros** | Scales each store to its native speed · Failure of one doesn't block all · Simpler than 2PC |
| **Cons** | Dev must reason per-store · Ordering surprises across stores · Saga compensations required |
| **Limitations** | Eventually consistent UX (docs appear "shortly") · No global atomic snapshot |
| **Recommendations** | Promote state to ACTIVE only after ALL stores indexed · Readers filter by state · Document guarantees in spec |
| **Challenges** | Replication lag thresholds · Read-your-writes during write path · Debugging inconsistencies |
| **Edge cases + solutions** | Consumer replays event → idempotency table skips · Qdrant lag spike → readers see older version until sync · Neo4j session retry on transient |
| **Alternatives** | 2PC (XA) — only if all participants support · CockroachDB (global serializable, cost) · Distributed transactions via Temporal sagas |

---

## Area 13 · Read Path vs Write Path

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | write: `services/ingestion-svc`; read: `services/retrieval-svc` (CQRS at the domain level) |
| **Components** | Async write pipeline · Sync read pipeline · Separate scaling · Shared data stores |
| **Technical details** | Writes: Kafka-driven saga, optimize for throughput. Reads: sync fan-out (vector+graph), optimize for latency. Same DB, different workload. |
| **Implementation** | Ingestion writes to Qdrant/Neo4j/Postgres via saga. Retrieval reads all three in parallel, fuses with RRF, caches in Redis. |
| **Tools & frameworks** | Kafka (write backbone) · Redis (read cache) · Qdrant (both) · asyncio.gather (parallel reads) |
| **How to implement** | 1. Separate services · 2. Writes are async w/ job ID · 3. Reads are sync w/ timeout · 4. Scale independently (HPA per service) · 5. Measure p95/throughput separately. |
| **Real-world example** | Bulk upload of 1k PDFs → ingestion queues in Kafka, writes over minutes (throughput) · user query hits retrieval, p95=200ms · the two never block each other. |
| **Pros** | Each path tuned · Independent failure modes · Easier capacity planning |
| **Cons** | Duplication of domain model (DTOs drift) · Two services to deploy · Eventual consistency |
| **Limitations** | No transactional read-after-write · Requires discipline (no cross-service DB writes) |
| **Recommendations** | Share DTOs via proto · Readers filter by state=ACTIVE · Publish `document.indexed` event for read cache warmup |
| **Challenges** | Staleness window · Read models drifting from write models · Versioned contracts |
| **Edge cases + solutions** | User uploads and immediately asks → readers see PROCESSING; UX shows "still indexing" · Re-index under load → swap alias atomically |
| **Alternatives** | Shared service (simpler, couples perf) · Event-sourced read projections · Materialized views |

---

## Area 14 · Admin Path Isolation

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/api-gateway/cmd/main.go` admin group, `internal/middleware/jwt.go::RequireRole`, `internal/middleware/ratelimit.go` separate bucket |
| **Components** | `/api/v1/admin/*` prefix · separate DB pool · separate rate limit · RBAC · separate Istio VS |
| **Technical details** | Admin traffic NEVER shares resources with user traffic. A bulk admin op cannot starve user queries. |
| **Implementation** | Gateway admin group requires `platform_admin` or `tenant_admin`. Admin rate = 50/min (stricter on writes). Admin audit log row per action. |
| **Tools & frameworks** | chi router groups · Istio VS with different `destination` · Postgres separate pool · AuditLog table |
| **How to implement** | 1. URL prefix · 2. Role-require middleware · 3. Separate rate bucket · 4. Separate Postgres pool if heavy · 5. Audit every admin action. |
| **Real-world example** | Admin bulk-deletes old docs → admin pool handles; user queries keep flowing through user pool unimpeded. |
| **Pros** | User latency isolated from admin ops · Audit-friendly · Clean RBAC |
| **Cons** | More config (pools, policies) · Must remember to use the right pool |
| **Limitations** | Doesn't isolate at DB/storage level — see Blast Radius Control (Area 52) |
| **Recommendations** | Always separate pool · Cap admin concurrency · All admin writes require approval workflow |
| **Challenges** | Admin paths often neglected in testing · Audit log volume |
| **Edge cases + solutions** | Admin needs read-only emergency access → break-glass role logged loudly · Long-running job → background task, not synchronous admin endpoint |
| **Alternatives** | Separate service (stronger isolation, higher ops cost) · Separate cluster for control plane |

---

## Area 15 · Evaluation Path Isolation

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/evaluation-svc/app/main.py`, `services/evaluation-svc/migrations/001_initial.sql` |
| **Components** | Dedicated eval service · Separate `eval.*` schema · Tagged eval requests (`X-Eval: true`) · Not billed · Separate metrics |
| **Technical details** | Eval runs use the SAME retrieval+inference pipeline but are tagged. FinOps excludes them. Observability tracks separately. |
| **Implementation** | evaluation-svc submits requests with `eval=true` header. inference-svc detects and skips FinOps + marks span as eval. Eval results in `eval.results`. |
| **Tools & frameworks** | RAGAS · TruLens · HELM · pytest for unit evals · separate Prom labels |
| **How to implement** | 1. Separate service · 2. Separate schema · 3. Tag requests · 4. Off-peak cron · 5. Block deploy on regression. |
| **Real-world example** | Nightly: eval-svc runs 500 eval questions through live pipeline · computes faithfulness/precision · compares to last-week baseline · posts regression report. |
| **Pros** | Eval traffic doesn't pollute prod metrics/billing · Runs against real services, not mocks · Regression-gate confidence |
| **Cons** | Still costs tokens · Risk of eval affecting prod under load (off-peak only) · Dataset curation effort |
| **Limitations** | Offline eval vs prod drift · Eval dataset ages · Small eval set = high variance |
| **Recommendations** | Eval dataset versioning · Minimum sample size for statistical confidence · Canary eval on new prompts before rollout |
| **Challenges** | Maintaining ground truth · Eval metric correlation with user satisfaction |
| **Edge cases + solutions** | Eval dataset contaminated by prod → rotate · Prod schema changes break eval → version lock |
| **Alternatives** | Shadow eval in prod (Area 60) · Offline on cached responses · Mock pipeline (loses real-world signal) |

---

## Area 16 · Sync vs Async

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `ingestion_service.ingest_upload(run_saga_inline=...)`; `kafka_client.py` for async path; `/ask` sync |
| **Components** | Sync request-response (FastAPI) · Async Kafka pipeline · Job ID polling · Webhooks (future) |
| **Technical details** | Rule: user waiting AND < 2s → sync; otherwise async with job ID. |
| **Implementation** | `/ask` is sync (user waits for answer). `/documents/upload` returns 202 + doc_id, saga runs async. `sync=true` flag for demos. |
| **Tools & frameworks** | FastAPI sync · Celery · FastAPI BackgroundTasks · Kafka async · SSE for progressive updates |
| **How to implement** | 1. Decision rule at route-design time · 2. Return 202 + job_id for async · 3. `/jobs/{id}` polling or SSE · 4. Explicit UX state. |
| **Real-world example** | Upload 100MB PDF → 202 + doc_id · frontend polls `/documents/{id}` every 2s · state goes PARSING→CHUNKING→…→ACTIVE. |
| **Pros** | UX responsiveness · Server-side capacity utilization · Backpressure natural |
| **Cons** | More client code · Polling overhead (or SSE complexity) · Harder to debug partial state |
| **Limitations** | Retry semantics differ · Sync path has hard latency budget |
| **Recommendations** | Explicit sync boundary · SSE/WebSocket for progressive results · Heartbeat on long-running sync calls |
| **Challenges** | Front-end state machines for async UX · Timeout tuning · Poll-vs-push tradeoffs |
| **Edge cases + solutions** | Client disconnects mid-sync → server continues (idempotency key ensures no double-work) · Stuck async → recovery worker |
| **Alternatives** | All-async (harder UX) · All-sync (blows SLO on big ops) · GraphQL subscriptions |

---

## Area 17 · Event-Driven Design

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/kafka_client.py`, `schemas/events/*.json` |
| **Components** | Kafka · CloudEvents envelope · Topic-per-domain · Producers + idempotent consumers · Schema registry |
| **Technical details** | Events are immutable, versioned (`type: document.indexed.v1`), self-describing. Topic keyed by tenant or doc for ordering. |
| **Implementation** | `EventProducer.publish(topic, type, data, tenant_id, correlation_id)`. `IdempotentConsumer` dedupes by `event.id`. JSON Schemas in `schemas/events/`. |
| **Tools & frameworks** | Kafka · Confluent Schema Registry · CloudEvents · Pulsar · AWS EventBridge · NATS |
| **How to implement** | 1. Define topics · 2. CloudEvents envelope · 3. Producer validates schema · 4. Consumer dedupes + validates · 5. DLQ per topic. |
| **Real-world example** | `document.indexed.v1` → retrieval cache invalidator consumes · FinOps token-counter consumes · eval sampler consumes 5% of them. Same event, three consumers. |
| **Pros** | Loose coupling · Replayable · New consumers added without producer change |
| **Cons** | Debugging distributed flows · Schema evolution discipline · Operational Kafka overhead |
| **Limitations** | No request-response (use RPC for that) · Exactly-once is hard |
| **Recommendations** | Small events + reference big blobs · Version in `type` · Compatible evolution rules · DLQ alerts |
| **Challenges** | Schema drift · Consumer lag monitoring · Out-of-order events |
| **Edge cases + solutions** | Breaking schema change → publish v2 alongside v1, migrate consumers, retire v1 · Consumer falls behind → scale OR purge |
| **Alternatives** | RabbitMQ (AMQP) · NATS JetStream · AWS SQS+SNS · Redis Streams (simpler at small scale) |

---

## Area 18 · Workflow Orchestration

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/ingestion-svc/app/saga/document_saga.py`, `saga/recovery.py`, `SagaRepo` |
| **Components** | Orchestrator saga · Per-step execute/compensate pair · Persisted saga state · Recovery worker |
| **Technical details** | Centralized orchestrator drives the 5-step ingestion pipeline. State persisted so crash-recovery possible. |
| **Implementation** | `DocumentIngestionSaga.run()` iterates steps (parse→chunk→embed→graph→index). Each success is recorded in `ingestion.sagas`. Failure → reverse compensations. |
| **Tools & frameworks** | Temporal · Cadence · AWS Step Functions · Camunda Zeebe · hand-rolled orchestrator (DocuMind's choice) |
| **How to implement** | 1. Define steps · 2. Execute + compensate per step · 3. Persist step completion · 4. Compensate in reverse on failure · 5. Recovery worker on startup. |
| **Real-world example** | Embed step fails (Ollama OOM) → saga compensates chunk+parse · document marked FAILED · user sees error + retry. Worker on restart re-tries with backoff. |
| **Pros** | Testable · Traceable · Recoverable |
| **Cons** | More code than "happy path only" · Orchestrator is a dependency |
| **Limitations** | Orchestrator bottleneck at scale (shard by tenant) · Compensation semantics tricky |
| **Recommendations** | Persist state BEFORE calling next step · Idempotent compensations · Alert on stuck sagas |
| **Challenges** | Partial compensation failures (needs human) · Saga state bloat |
| **Edge cases + solutions** | Compensation itself fails → mark "stuck", page on-call · Step 3 succeeds but marker fails → worker replays, idempotent save is fine |
| **Alternatives** | Choreography (events only) · Temporal (durable workflow) · Step Functions (managed) |

---

## Area 19 · Compensation Logic

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `DocumentIngestionSaga._compensate_*` methods, `_run_compensations` |
| **Components** | One compensation per step · Idempotent · Alert on compensation failure |
| **Technical details** | Reverse-order undo. Each compensation is safe to run twice. Failure logs + flags for manual intervention. |
| **Implementation** | `_compensate_index` → `QdrantRepo.delete_document` by filter. `_compensate_graph` → Neo4j `DETACH DELETE`. `_compensate_chunk` → `DELETE FROM chunks`. |
| **Tools & frameworks** | N/A — domain-specific. Tempura / Temporal have built-in compensation DSL. |
| **How to implement** | 1. Pair each action with undo · 2. Use `ON CONFLICT DO NOTHING` or idempotent deletes · 3. Timeout per compensation · 4. Stuck-comp alert. |
| **Real-world example** | Embed fails after chunks written → saga deletes chunks, then parsed blob → doc marked FAILED. All reversible. |
| **Pros** | Roll-back semantics without XA · Simpler than distributed transactions |
| **Cons** | Every forward action needs a compensation · Temporal ordering of failures can leak data briefly |
| **Limitations** | Some actions are intrinsically irreversible (external webhook already sent) — use sagas that book "pending" then confirm |
| **Recommendations** | Compensation timeouts shorter than saga timeout · Logs for every comp step · Retry with backoff |
| **Challenges** | Compensation of non-transactional effects (emails, external API) |
| **Edge cases + solutions** | External webhook already fired → publish "reversal" event · Partial compensation success → retry the rest, escalate if stuck |
| **Alternatives** | No compensation (just mark failed, garbage collect nightly) · Two-phase commit where supported · Eventual consistency with read-side filters |

---

## Area 20 · Idempotency Strategy

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `libs/py/documind_core/idempotency.py`, `idempotency_middleware.py`, `kafka_client.IdempotentConsumer`, chunk `content_hash` skip |
| **Components** | `X-Idempotency-Key` header · Redis cache of (status, body) · Event dedup table · `ON CONFLICT` for DB · content-hash for embedding |
| **Technical details** | Every layer has its own dedup so retries are safe. |
| **Implementation** | Gateway + service middleware cache responses by (tenant, route, key) for 24h. Kafka consumer tracks `event.id` in dedup set. Embedding keyed on SHA-256 of normalized text. |
| **Tools & frameworks** | Redis · Postgres `UNIQUE` · Kafka headers · HTTP `Idempotency-Key` RFC draft |
| **How to implement** | 1. Require clients to send UUID per mutation · 2. Server caches response · 3. Consumer dedup table · 4. DB inserts use ON CONFLICT · 5. Content-hash where natural. |
| **Real-world example** | Mobile retries POST /upload after flaky network → server returns same 202 + doc_id → no double-create. |
| **Pros** | Safe client retries · No duplicate side-effects · Kafka replay is fine |
| **Cons** | Storage for key→response mapping · Clients must supply keys · Tricky for streams |
| **Limitations** | 24h window (longer needs Postgres) · Body cache size can grow |
| **Recommendations** | Document per-endpoint: "accepts Idempotency-Key" · TTL tuned to retry horizon · Compress stored body |
| **Challenges** | Streaming responses · Large bodies · Migrating existing endpoints |
| **Edge cases + solutions** | Same key, different body → reject (409) with `idempotency_conflict` · 5xx on first try → don't cache, let client retry |
| **Alternatives** | Natural keys (tenant+filename+checksum for upload) · Client-side dedup only (unsafe) · Transactional outbox |
