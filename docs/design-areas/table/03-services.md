# Areas 21–29 · Service Decomposition and the 8 Services

## Area 21 · Service Decomposition

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | 10 services under `services/`; polyglot (Go + Python + TS) per spec §2.3 |
| **Components** | Bounded contexts · Scaling profile · Tech-stack choice · Team ownership · Database-per-service |
| **Technical details** | Decomposition criteria: one bounded context, independent deploy, independent scale, team ownership, DB ownership, failure isolation, tech heterogeneity. |
| **Implementation** | Go for I/O-bound (api-gateway, identity, governance, finops, observability). Python for ML-bound (ingestion, retrieval, inference, eval). TS/React for frontend. |
| **Tools & frameworks** | DDD · Team Topologies · Microservices patterns (Richardson) · Event Storming · C4 model |
| **How to implement** | 1. Event Storming to find contexts · 2. Team → service mapping (Conway's Law) · 3. Define API contracts BEFORE coding · 4. Each service owns its DB schema. |
| **Real-world example** | Adding "billing portal" → new service (`billing-ui`) or extend `frontend`? If different team + different deploy cadence → new service. |
| **Pros** | Independent velocity · Tech fit per workload · Clear ownership |
| **Cons** | Polyglot ops overhead · More CI/CD · Cross-service change needs choreography |
| **Limitations** | Small teams struggle with many services · Shared libs need discipline to not couple |
| **Recommendations** | Start with monolith, split along proven seams · No more services than teams · Shared libs versioned |
| **Challenges** | Premature decomposition · Shared domain types drifting · Distributed debugging |
| **Edge cases + solutions** | Two services constantly chatty → maybe they're one service · Shared domain → extract into a library, not a service |
| **Alternatives** | Monolith (simpler ops) · Modular monolith (best of both) · Serverless functions |

---

## Area 22 · Identity Service

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — Go skeleton + proto + migrations; full JWT flows + API-key issuance to be fleshed out |
| **Class / file** | `services/identity-svc/cmd/main.go`, `proto/identity/v1/identity.proto`, `services/identity-svc/migrations/001_initial.sql` |
| **Components** | Tenants · Users · Roles (RBAC) · JWT issue/refresh/verify · API keys · Sessions |
| **Technical details** | RS256 JWT. 15-min access + 7-day refresh. API keys hashed + prefixed for lookup. RBAC as `(user_id, role)` join table. |
| **Implementation** | Proto service with `Login/Refresh/VerifyToken/CreateTenant/CreateUser/AssignRole`. Postgres `identity.*` schema. Gateway calls `VerifyToken` on every request (cached). |
| **Tools & frameworks** | Keycloak (replaceable) · Auth0 · Ory Hydra · Casbin for ABAC · argon2 for passwords · `golang-jwt/jwt/v5` |
| **How to implement** | 1. Start from schema · 2. JWT mint + verify · 3. Login/refresh endpoints · 4. API-key mgmt · 5. Deprecation of old keys. |
| **Real-world example** | Login → access_token (15m) + refresh (7d). Refresh rotates both. Logout revokes via deny-list. |
| **Pros** | Standard OAuth/OIDC compatible · Services trust JWT claims only (decoupled) · Easy cross-system federation |
| **Cons** | JWT revocation is hard without deny-list · Refresh flow complexity · Clock skew issues |
| **Limitations** | Claim size grows · RS256 verify is CPU-costly (cache public key) |
| **Recommendations** | Short access TTL · JWKS endpoint for key rotation · Separate tenant_admin vs platform_admin roles |
| **Challenges** | Multi-IdP federation · SSO integrations · SCIM provisioning |
| **Edge cases + solutions** | Leaked token → add to deny-list; rotate signing key if widespread · Expired refresh → require re-auth |
| **Alternatives** | Keycloak (managed OIDC) · Auth0 · AWS Cognito · Firebase Auth · SPIFFE-only (no user tokens) |

---

## Area 23 · Knowledge Ingestion Service

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/ingestion-svc/app/*` — `parsers/`, `chunking/`, `embedding/`, `saga/`, `repositories/`, `services/`, `routers/` |
| **Components** | Parsers (PDF/DOCX/HTML/TXT/MD) · RecursiveChunker · OllamaEmbedder · DocumentRepo/ChunkRepo/SagaRepo/QdrantRepo/Neo4jRepo · BlobService · `DocumentIngestionSaga` |
| **Technical details** | Five-step saga, fully class-based with interfaces. Each parser/chunker/embedder is swappable. |
| **Implementation** | Upload → `POST /api/v1/documents/upload` → BlobService puts raw → DocumentRepo creates row → Saga runs (parse→chunk→embed→graph→index). |
| **Tools & frameworks** | `pypdf`, `python-docx`, `beautifulsoup4`, `markdown`, `tiktoken`, Ollama embed API, Qdrant, Neo4j, MinIO/S3 |
| **How to implement** | 1. Parser registry · 2. Token-aware chunker (512/50 overlap default) · 3. Embedder interface · 4. Orchestrator saga · 5. Tenant-scoped repos. |
| **Real-world example** | 50-page PDF → 180 chunks · 12s end-to-end · saved to Qdrant (vectors) + Neo4j (graph) + Postgres (chunks table) + MinIO (raw). |
| **Pros** | Every component testable in isolation · New format = new parser class · Zero-downtime model upgrades via embedding versioning |
| **Cons** | Saga complexity · Multi-store write amplification · Parser edge cases (malformed PDFs) |
| **Limitations** | OCR not built-in (add via parser) · Tables in PDF lose structure (use `unstructured.io`) |
| **Recommendations** | Validate MIME and extension (both) · Checksum for dedup · Streaming uploads for big files |
| **Challenges** | Scanned PDFs (OCR) · Non-UTF-8 text · Language detection |
| **Edge cases + solutions** | Password-protected PDF → parse-warning, mark FAILED · Empty document → reject with 400 |
| **Alternatives** | Unstructured.io (does everything) · LlamaIndex node parsers · LangChain document loaders · Apache Tika |

---

## Area 24 · Retrieval Service

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/retrieval-svc/app/services/` — `hybrid_retriever.py`, `vector_searcher.py`, `graph_searcher.py`, `reranker.py`, `embedder_client.py` |
| **Components** | OllamaEmbedderClient · VectorSearcher (Qdrant) · GraphSearcher (Neo4j) · ReciprocalRankFusion · Cache · RetrievalCircuitBreaker |
| **Technical details** | Hybrid: vector + graph in parallel (`asyncio.gather`), fused by RRF, cached in Redis. |
| **Implementation** | `HybridRetriever.retrieve(tenant_id, RetrieveRequest)` → cache check → parallel fetch → RRF → cache store → return top-K. Quality breaker records each retrieval. |
| **Tools & frameworks** | Qdrant · Neo4j · Redis · RRF (self-impl) · BGE-reranker-v2 (future cross-encoder stage) |
| **How to implement** | 1. Embed query · 2. Parallel vector + graph search · 3. RRF merge · 4. Cache by (tenant, query hash, strategy) · 5. Record quality. |
| **Real-world example** | Query "what does paragraph 3 say about indemnification?" → vector finds clause 3.2, graph finds related clauses in other docs, RRF top-5 returned. |
| **Pros** | Better recall than vector-only · Reasoning-capable (graph) · Cheap cache hits |
| **Cons** | Graph precision depends on entity extraction · Two stores to maintain · Cache invalidation |
| **Limitations** | Graph's naive NER is weak; a real NER (spaCy/LLM) improves · RRF is cheap but not learned |
| **Recommendations** | Hybrid always beats single-source at scale · Add cross-encoder re-rank if compute allows · Monitor quality breaker |
| **Challenges** | Staleness after re-index · Tenant-scoped caching · Ordering under concurrent writes |
| **Edge cases + solutions** | Empty results → fall through to fuzzy metadata search · Tenant's corpus not indexed yet → degrade to "still processing" |
| **Alternatives** | Weaviate hybrid (built-in BM25+vector) · OpenSearch hybrid · Pinecone + external keyword · LlamaIndex retrievers |

---

## Area 25 · Inference Service

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/inference-svc/app/services/` — `rag_inference.py`, `prompt_builder.py`, `ollama_client.py`, `guardrails.py`, `retrieval_client.py` |
| **Components** | RetrievalClient · PromptBuilder (versioned) · OllamaClient (streaming + CB) · GuardrailChecker · TokenCircuitBreaker · CognitiveCircuitBreaker |
| **Technical details** | Flow: budget check → retrieve → prompt → stream LLM through CCB → guardrails → response with citations. |
| **Implementation** | `RagInferenceService.ask()` orchestrates. Token budget pre-flight. CCB evaluates partial output every 32 tokens during streaming. Guardrails verify citations + PII. |
| **Tools & frameworks** | Ollama / vLLM / OpenAI-compatible · LangChain (not used — direct client keeps control) · tiktoken · `sse-starlette` for server-sent events |
| **How to implement** | 1. Token budget pre-flight · 2. Retrieve · 3. Build versioned prompt · 4. Stream w/ CCB · 5. Guardrails · 6. Citations check · 7. Record usage. |
| **Real-world example** | User asks "summarize the contract renewal clause" → 5 chunks retrieved, score ~0.8 · prompt built with [Source: x.pdf, Page 12] labels · LLM streams; CCB fine · guard passes citation · 200ms to first token, 2s total. |
| **Pros** | Fast feedback (streaming) · Hallucination caught early (CCB) · Cost-bounded (TokenCB) |
| **Cons** | CCB tuning is empirical · LLM latency dominates · Tight coupling to prompt template |
| **Limitations** | Single-model per request (no ensembling yet) · No self-consistency · Fixed temperature |
| **Recommendations** | Version prompts; promote via governance · A/B test at small % · CCB for every production use · Log prompt_version + model with every response |
| **Challenges** | Prompt regression detection · Cost control under spike · Model swap without UX change |
| **Edge cases + solutions** | CCB interrupts mid-stream → fallback response · Ollama times out → CB opens · Very long context → truncate oldest chunks |
| **Alternatives** | LangChain Runnables · LlamaIndex QueryEngine · Haystack Pipeline · raw OpenAI function calling |

---

## Area 26 · Evaluation Service

| Field | Content |
|---|---|
| **Status** | ✅ Implemented |
| **Class / file** | `services/evaluation-svc/app/main.py`, `app/metrics/` — retrieval + generation metrics |
| **Components** | PrecisionAtK · Recall · MRR · NDCG · Faithfulness · AnswerRelevance · Run API · Regression gate (stub) |
| **Technical details** | Class-per-metric; each has `.compute(retrieved=, relevant=)` or `.compute(answer=, context=)`. |
| **Implementation** | `POST /api/v1/evaluation/run` with list of ScoringDatapoint → computes all 6 metrics, returns aggregate. |
| **Tools & frameworks** | RAGAS · TruLens · LangSmith · DeepEval · custom (DocuMind's path) |
| **How to implement** | 1. Curate eval dataset (Q + expected chunks + GT answer) · 2. Run pipeline · 3. Compute metrics · 4. Store in `eval.runs` · 5. Compare to baseline · 6. Block deploy on regression. |
| **Real-world example** | Nightly run: 500 Qs, precision@5=0.82, recall=0.74, MRR=0.68, faithfulness=0.91. Dashboard charts trend. |
| **Pros** | Quantifiable quality · Regression prevention · Prompt A/B objective |
| **Cons** | Dataset labor · Metric-vs-UX gap · Faithfulness metric approximates (LLM judge is gold-standard but costs) |
| **Limitations** | Token-overlap faithfulness misses rephrasing · Small datasets = high variance |
| **Recommendations** | Ground truth from domain expert · Refresh dataset quarterly · Use LLM judge for faithfulness when budget allows |
| **Challenges** | Automated labeling drift · Metric interpretability · Business-relevant metrics |
| **Edge cases + solutions** | Multi-correct answers → use LLM judge or semantic similarity · Dataset overlap w/ corpus → rotate GT |
| **Alternatives** | RAGAS (full suite) · TruLens (built-in LLM judge) · HELM (academic) · Custom + vibe checks (not recommended alone) |

---

## Area 27 · Governance Service

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — Go skeleton + schema; CEL evaluator deferred |
| **Class / file** | `services/governance-svc/cmd/main.go`, `services/governance-svc/migrations/001_initial.sql` |
| **Components** | Policy engine (CEL) · HITL queue · Audit log (hash-chained) · Feature flags · Prompt registry · Model selection policy |
| **Technical details** | Policies as code (CEL expressions in Postgres). Flags with scope (global/tenant/user/percent). Audit log append-only. |
| **Implementation** | `governance.policies` + `.feature_flags` + `.hitl_queue` + `.audit_log` + `.prompts`. Go service exposes CRUD + evaluate. |
| **Tools & frameworks** | CEL · OPA · OpenPolicyAgent · Unleash / LaunchDarkly (alternatives) · Cerbos |
| **How to implement** | 1. Policy schema · 2. CEL eval loop · 3. HITL reviewer UI · 4. Audit chain (SHA-256 of prev entry) · 5. Flag lifecycle (draft→active→deprecated). |
| **Real-world example** | Rule "response.confidence < 0.6" → action `flag_for_review` → HITL queue → reviewer approves/edits/rejects. |
| **Pros** | Runtime behavior change · Auditable · Central policy truth |
| **Cons** | CEL learning curve · Policy conflicts · UI complexity |
| **Limitations** | CEL can't call LLMs (keep policies cheap) · Flag rollout needs discipline |
| **Recommendations** | Small set of core policies; expand carefully · Every policy has an owner + deprecation date · Audit log off-DB (WORM storage) |
| **Challenges** | Maintaining clean policy set · Cross-region replication of policies · Policy conflict resolution |
| **Edge cases + solutions** | Policy change breaks users → staged rollout via flag · Corrupt policy → rollback to last-known-good |
| **Alternatives** | OPA (Rego) · Cerbos · Homegrown config files (weaker) · AWS IAM policies |

---

## Area 28 · Observability Service

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — Go skeleton · Prom + Grafana + Jaeger + Loki/Kibana deployed |
| **Class / file** | `services/observability-svc/cmd/main.go`, `infra/observability/alert-rules.yml`, `infra/elk/filebeat.yml`, `infra/kiali/kiali.yaml` |
| **Components** | Metrics aggregation · SLO targets · Alert rules · Dashboards (Grafana) · Trace viz (Jaeger) · Mesh viz (Kiali) · Log viz (Kibana) |
| **Technical details** | Owns the config for all telemetry. Provides `/api/v1/admin/slo` and `/api/v1/admin/capacity` to the admin UI. |
| **Implementation** | Go service reads/writes `observability.*` tables. Prom scrapes services; OTel collector forwards traces + metrics; Filebeat ships logs to ES. |
| **Tools & frameworks** | Prometheus · Grafana · Jaeger · Loki/Kibana · OTel Collector · Kiali · AlertManager · SigNoz/Honeycomb (SaaS) |
| **How to implement** | 1. Prom scrape configs per service · 2. SLO targets in DB · 3. AlertManager routes (Slack/PagerDuty) · 4. Dashboards as code (JSON). |
| **Real-world example** | Faithfulness drops 5% → Prom alert → observability-svc posts to Slack + opens GitHub issue · on-call sees trend in Grafana · triggers retrain. |
| **Pros** | Single source of truth for ops · Central SLO · Consistent alerting |
| **Cons** | Store overhead at scale · Cardinality traps · Alert tuning |
| **Limitations** | Prom retention (local 15d default) · Log volume costly · Trace sampling loses detail |
| **Recommendations** | Burn-rate SLO alerts (multi-window) · Per-service runbooks linked from alerts · Alert-fatigue audits quarterly |
| **Challenges** | High-cardinality metrics · Log schema drift · Tracing context across async boundaries |
| **Edge cases + solutions** | Observability stack itself down → `ObservabilityCircuitBreaker` skips export, never blocks app · Alert storm → AlertManager grouping + inhibitions |
| **Alternatives** | Datadog · New Relic · Honeycomb · SigNoz (OSS APM) · AWS CloudWatch / GCP Cloud Operations |

---

## Area 29 · FinOps / Billing Service

| Field | Content |
|---|---|
| **Status** | 🟡 Partial — Go skeleton + shadow-pricing rates + Kafka-consumer scaffolding |
| **Class / file** | `services/finops-svc/cmd/main.go`, `services/finops-svc/migrations/001_initial.sql` |
| **Components** | Token counter · Cost attribution (per tenant/model) · Budgets · Shadow pricing · Billing period rollups |
| **Technical details** | Consumes `cost.events` from Kafka. Aggregates per-tenant daily/monthly. Shadow-prices Ollama against cloud API rates. |
| **Implementation** | Kafka consumer appends to `finops.token_usage`. Cron rolls up into `billing_periods`. Budget check via TokenCircuitBreaker. |
| **Tools & frameworks** | Kafka · Postgres rollups · Stripe (billing in prod) · Chargebee · Metronome · OpenCost (K8s cost) |
| **How to implement** | 1. Kafka consume cost events · 2. Aggregate into token_usage · 3. Nightly roll to billing_periods · 4. Alert at 50/80/100% budget · 5. Hook Stripe at month end. |
| **Real-world example** | Tenant A hits 80% of daily budget at 3pm → governance-svc sets `budget_warning` flag · UI shows yellow banner · at 100%, new requests rejected with PolicyViolationError. |
| **Pros** | Cost transparency · Budget enforcement · Per-model comparison |
| **Cons** | Kafka consumer lag = stale budget · Shadow pricing is an estimate |
| **Limitations** | GPU amortization is tricky · Multi-currency · Real-time budget check races with usage |
| **Recommendations** | Roll budget from DB at T-30s cached; enforce at call site · Monthly statements exported to data warehouse · Integration test per tier |
| **Challenges** | Reconciling shadow vs actual · Mid-month plan changes · Refunds/credits |
| **Edge cases + solutions** | Kafka down → degraded budget tracking, accept usage but warn · Overrun by race → negative budget, carry to next period |
| **Alternatives** | Stripe usage-based billing · Chargebee · OpenCost for K8s only · Homegrown (DocuMind path) |
