/**
 * Catalogs every *_scenario* category the product group asks about.
 * Each scenario is compact: problem / solution / example. One page renders
 * all categories so the consumer can scan 100+ scenarios in one scroll.
 */

export type ScenarioRow = {
  name: string;
  problem: string;
  solution: string;
  example: string;
};

export type ScenarioCategory = {
  id: string;
  title: string;
  blurb: string;
  docsUrl?: string;
  docsLabel?: string;
  rows: ScenarioRow[];
};

export const SCENARIO_CATEGORIES: ScenarioCategory[] = [
  // -------------------------------------------------- Observability
  {
    id: 'observability',
    title: 'Observability',
    blurb: 'Metrics, logs, traces — correlated by correlation-id, SLO-driven, protected from self-inflicted outage.',
    docsUrl: 'https://opentelemetry.io/docs/concepts/observability-primer/',
    docsLabel: 'OTel — observability primer',
    rows: [
      { name: 'Structured JSON logs', problem: 'Grep-joining logs across services is slow and lossy.', solution: 'structlog JsonFormatter: timestamp, level, correlation_id, tenant_id, event, fields.', example: 'libs/py/documind_core/logging_config.py — every service ships JSON to ELK.' },
      { name: 'Correlation-id propagation', problem: 'One user request = many service hops.', solution: 'Inject X-Correlation-Id at the gateway; forward as OTel baggage + log field.', example: 'Kibana query correlation_id:"abc123" shows every hop in order.' },
      { name: 'OTel tracing', problem: 'Which span is slow in the chain?', solution: 'Spans at every boundary; parent-child via W3C traceparent.', example: 'Jaeger UI renders the full waterfall.' },
      { name: 'Prometheus metrics', problem: 'Need aggregate signals, not just single-request forensics.', solution: 'Counters / gauges / histograms with bounded cardinality labels.', example: 'documind_request_duration_seconds{service,route,tenant_tier}.' },
      { name: 'SLO + error-budget alerts', problem: 'Alert on every error = alert fatigue.', solution: 'Burn-rate alerts on multi-window error-budget consumption.', example: 'observability.slo_targets seeds 4 SLOs; Prom alerts fire on burn.' },
      { name: 'Observability CB (inverted)', problem: 'Dead OTel collector hangs every request 10s.', solution: 'Breaker skips export silently when collector unhealthy.', example: 'ObservabilityCircuitBreaker in breakers.py. Telemetry is best-effort.' },
      { name: 'Tail-based sampling', problem: 'Head-sampling loses errors in rare flows.', solution: 'Collector decides after full trace: 100% errors, 10% normal, 100% > p99.', example: 'OTel Collector tail_sampling_processor.' },
      { name: 'Runbook-linked alerts', problem: 'Pager fires at 3am; responder has no context.', solution: 'Alert payload includes runbook URL + recent deploy link.', example: 'Alertmanager template includes runbook_url: annotation.' },
      { name: 'Kiali mesh visualization', problem: 'Operators can\'t mentally model 8 services.', solution: 'Kiali renders live mesh + policy overlays.', example: 'Weekly review catches orphan services + policy regressions.' },
      { name: 'Grafana dashboards (per SLO)', problem: 'Scattered dashboards = scattered truth.', solution: 'One dashboard per SLO, linking Prom + Jaeger + Kibana datasources.', example: 'Burn-rate panels + trace-exemplars link to Jaeger.' },
    ],
  },

  // -------------------------------------------------- API design scenarios
  {
    id: 'api',
    title: 'API Design',
    blurb: 'Versioning, pagination, auth, idempotency — the eight things every endpoint must answer.',
    docsUrl: 'https://restfulapi.net/',
    docsLabel: 'REST design principles',
    rows: [
      { name: 'Path-based versioning', problem: 'Breaking changes need to coexist with old clients.', solution: '/api/v1/*, /api/v2/*; deprecate on N+2 releases.', example: 'DocuMind: /api/v1/ask. v2 will ship behind a feature flag for early tenants.' },
      { name: 'Pagination', problem: 'Listing endpoints blow up under scale.', solution: 'offset/limit with max 500; cursor for very large lists.', example: 'GET /api/v1/documents?offset=0&limit=50; total + next_cursor in response.' },
      { name: 'Idempotency', problem: 'Retries on POST create duplicates.', solution: 'X-Idempotency-Key header; cache first response for 24h; replay on retry.', example: 'POST /api/v1/documents with Idempotency-Key: <uuid> returns the same 201 on retry.' },
      { name: 'Consistent error envelope', problem: 'Ad-hoc error shapes break clients.', solution: '{detail, error_code, correlation_id} on every non-2xx.', example: 'error_handlers.py maps every AppError subclass to this shape.' },
      { name: 'Rate limiting', problem: 'One bursty tenant degrades everyone.', solution: 'Token bucket per (tenant, IP); 429 + Retry-After.', example: 'Gateway enforces 100 rpm/API, 10 rpm/upload per tenant; surfaced via X-RateLimit-* headers.' },
      { name: 'Content negotiation', problem: 'Same resource, multiple representations (JSON/MsgPack/CSV).', solution: 'Accept header; explicit content-type per route.', example: '/api/v1/eval/runs/:id/export supports Accept: text/csv or application/json.' },
      { name: 'Deprecation policy', problem: 'Breaking clients without warning.', solution: 'Deprecation + Sunset headers + docs changelog.', example: 'Deprecation: "v1"; Sunset: Tue, 01 Dec 2026 00:00:00 GMT.' },
      { name: 'gRPC for internal', problem: 'REST overhead for hot internal paths.', solution: 'gRPC + proto contracts; REST only at the edge.', example: 'retrieval-svc <-> inference-svc via gRPC; external API stays REST.' },
    ],
  },
  // -------------------------------------------------- Chunking
  {
    id: 'chunking',
    title: 'Chunking',
    blurb: 'Document → retrievable units. Boundary quality is the #1 predictor of retrieval precision.',
    docsUrl: 'https://python.langchain.com/docs/modules/data_connection/document_transformers/',
    docsLabel: 'LangChain — chunking strategies',
    rows: [
      { name: 'Fixed-size sliding window', problem: 'Simplest baseline.', solution: '512 tokens, 15% overlap.', example: 'chunking/windowed.py. Default for unknown doc types.' },
      { name: 'Sentence-boundary', problem: 'Fixed-size cuts mid-sentence.', solution: 'pysbd segments; group sentences up to token budget.', example: 'chunking/sentence.py; fallback to window on long sentences.' },
      { name: 'Structural (headings, sections)', problem: 'Markdown / PDF have natural structure to respect.', solution: 'Split on H1/H2/H3 or section breaks; preserve hierarchy as metadata.', example: 'chunking/structural.py + unstructured for PDF.' },
      { name: 'Semantic (embedding-clustered)', problem: 'Boundary artifacts on dense prose.', solution: 'Cluster sentences by embedding similarity; cut at cluster boundaries.', example: 'Not yet implemented — flagged in GAP-ANALYSIS.md.' },
      { name: 'AST-based (code)', problem: 'Code needs function/class boundaries.', solution: 'Tree-sitter parse; chunk at function/class scope.', example: 'Not implemented; suggested for code-heavy corpora.' },
      { name: 'Late chunking', problem: 'Context lost at chunk boundaries.', solution: 'Embed the whole document with long-context model; chunk in embedding space.', example: 'Emerging 2025 technique; POC candidate.' },
      { name: 'Per-doc strategy override', problem: 'One chunker per tenant is a mismatch for mixed corpora.', solution: 'Tenant-level default + per-document override.', example: 'Tenant flag today; per-doc override is planned.' },
    ],
  },
  // -------------------------------------------------- Embedding
  {
    id: 'embedding',
    title: 'Embedding',
    blurb: 'Text → vector. Model choice, versioning, cross-encoder rerank.',
    docsUrl: 'https://huggingface.co/spaces/mteb/leaderboard',
    docsLabel: 'MTEB leaderboard',
    rows: [
      { name: 'Bi-encoder default', problem: 'Need fast vectors for ANN search.', solution: 'BGE-m3 1024-dim multilingual; sentence-transformers runtime.', example: 'retrieval-svc/app/services/embedder_client.py.' },
      { name: 'Cross-encoder rerank', problem: 'Bi-encoder top-20 is noisy.', solution: 'Cross-encoder rerank top-20 → top-5.', example: 'BGE reranker v2. Catches near-duplicates and off-topic.' },
      { name: 'Matryoshka / variable-dim', problem: 'Full 1024-dim is expensive for first probe.', solution: 'Truncate to 128-dim for ANN; full-dim for rerank.', example: 'Planned optimization; 3x latency win expected.' },
      { name: 'Per-modality embeddings', problem: 'Text embedder poor on tables, images, code.', solution: 'LayoutLMv3 for tables; CLIP for images; code-specific encoder.', example: 'Tables: LayoutLMv3. Images/code: single generic encoder today.' },
      { name: 'Fine-tuned domain embedder', problem: 'Generic model suboptimal on domain jargon.', solution: 'Fine-tune on labeled pairs from customer data.', example: 'Not implemented — unblocks only when a customer dataset exists.' },
      { name: 'Versioning per chunk', problem: 'Mix old and new embeddings in one index = garbage.', solution: 'embedding_model + embedding_version on every chunk row.', example: 'stamp_embedding_model on saga completion; shadow-index on upgrade.' },
      { name: 'Batch embedding queue', problem: 'Inline embed blocks upload API.', solution: 'Kafka topic; worker pool auto-scales.', example: 'chunk-ready events → embedder workers → embedded events.' },
    ],
  },
  // -------------------------------------------------- Pre-retrieval
  {
    id: 'pre-retrieval',
    title: 'Pre-Retrieval',
    blurb: 'Transform the user query before ANN. Bigger lever than retrieval tuning.',
    docsUrl: 'https://arxiv.org/abs/2212.10496',
    docsLabel: 'HyDE paper (arXiv 2212.10496)',
    rows: [
      { name: 'Query normalization', problem: 'Typos, casing, synonyms hurt recall.', solution: 'Lowercase + punctuation strip + lightweight typo correction.', example: 'Happens before cache-key hash; also before ANN.' },
      { name: 'Query expansion', problem: 'User query too terse.', solution: 'LLM proposes 2-3 related queries; union the retrieved sets.', example: 'Planned — gated by cost + quality eval.' },
      { name: 'HyDE (hypothetical document)', problem: 'Question is stylistically different from corpus.', solution: 'LLM drafts a plausible answer; embed the answer, retrieve with it.', example: 'Candidate for long-tail questions; not yet in prod.' },
      { name: 'Query decomposition', problem: 'Multi-part question, single retrieval misses one part.', solution: 'Decompose into sub-questions; retrieve per; merge context.', example: 'Used in MultiHopRagAgent flow.' },
      { name: 'Metadata filter construction', problem: 'Need to constrain by date, source, tag.', solution: 'LLM extracts filters; compose into Qdrant payload filter.', example: '"docs from 2025 only" → filter: {date: {gte: 2025-01-01}}.' },
      { name: 'Query cache', problem: 'Same query answered again = wasted compute.', solution: 'Hash(tenant || normalized || model_version) → cached response.', example: '~30% production traffic cache-hit.' },
      { name: 'Prompt injection pre-scan', problem: 'Attack payloads shouldn\'t even hit retrieval.', solution: 'PromptInjectionDetector on input; fail-closed.', example: 'libs/py/documind_core/ai_governance.py.' },
    ],
  },
  // -------------------------------------------------- Post-retrieval
  {
    id: 'post-retrieval',
    title: 'Post-Retrieval',
    blurb: 'Top-K is noisy. Rerank, diversify, compress, cite — before the model sees it.',
    docsUrl: 'https://arxiv.org/abs/2212.09156',
    docsLabel: 'Cross-encoder reranker survey',
    rows: [
      { name: 'Cross-encoder rerank', problem: 'Bi-encoder top-20 has near-duplicates and off-topic.', solution: 'Cross-encoder re-score on (query, chunk) pair; take top-5.', example: 'BGE reranker v2 in retrieval-svc.' },
      { name: 'MMR diversification', problem: 'Top-K is five near-identical chunks from one doc.', solution: 'Maximum marginal relevance: trade relevance for diversity.', example: 'Lambda ~0.5 balances precision and coverage.' },
      { name: 'Context-window packing', problem: 'Too many chunks overflow the LLM window.', solution: 'Greedy pack highest-score chunks until token budget hit.', example: 'inference-svc sizes context to (window - prompt - reserve).' },
      { name: 'Citation attachment', problem: 'Answer without sources is a trust hole.', solution: 'Attach chunk IDs to each generated sentence via constrained decoding.', example: 'Governance enforces citation presence before response returns.' },
      { name: 'Graph expansion (1-hop)', problem: 'ANN misses obvious relational neighbors.', solution: '1-hop neighbors of top chunks via Neo4j.', example: 'GraphSearcher in retrieval-svc.' },
      { name: 'Confidence scoring', problem: 'Need a single number for downstream decisions (HITL, cache).', solution: 'Weighted mix: rerank score, graph degree, source trust.', example: 'Confidence < threshold → HITL escalation.' },
      { name: 'Output sanitization', problem: 'Model might hallucinate citations or PII.', solution: 'ResponsibleAIChecker + PII scanner on output.', example: 'Fail-closed before response returns to user.' },
    ],
  },
  // -------------------------------------------------- Output evaluation
  {
    id: 'output-eval',
    title: 'Output Evaluation',
    blurb: 'Is the answer good? Precision, faithfulness, drift, user feedback.',
    docsUrl: 'https://docs.ragas.io/',
    docsLabel: 'Ragas — RAG evaluation',
    rows: [
      { name: 'Precision@K / Recall@K', problem: 'Was the right chunk in the top-K?', solution: 'Labeled eval set; compute per-query and aggregate.', example: 'evaluation-svc POST /api/v1/evaluation/run.' },
      { name: 'nDCG', problem: 'Rank matters — top-1 is worth more than top-5.', solution: 'Normalized DCG weights by rank position.', example: 'Standard run metric in eval.runs table.' },
      { name: 'Faithfulness', problem: 'Is the answer supported by retrieved context?', solution: 'Embed answer; cosine to context chunks; heuristic threshold.', example: 'Shipping. LLM-as-judge version pending.' },
      { name: 'Answer relevance', problem: 'Answer grammatically correct but off-question.', solution: 'LLM judge compares answer to question; score 0–1.', example: 'Planned — needs a cost/governance review first.' },
      { name: 'LLM-as-judge (Ragas)', problem: 'Heuristics miss nuance.', solution: 'Strong LLM grades (faithfulness, relevance, context-precision).', example: 'GAP-ANALYSIS.md priority #4.' },
      { name: 'Drift detection', problem: 'Traffic distribution shifts; eval set stops representing reality.', solution: 'PSI/CSI on embedding distribution vs. reference.', example: 'Implemented; alerts if PSI > 0.2.' },
      { name: 'Human feedback', problem: 'Systems lie; users don\'t.', solution: 'Thumbs-up/down + optional comment; store in eval.feedback.', example: 'Capture deferred; schema shipped.' },
    ],
  },
  // -------------------------------------------------- PII
  {
    id: 'pii',
    title: 'PII Handling',
    blurb: 'Detect, redact, never cache. Regex for structured, NER for named entities.',
    docsUrl: 'https://microsoft.github.io/presidio/',
    docsLabel: 'Microsoft Presidio (PII NER)',
    rows: [
      { name: 'Regex scanner', problem: 'Catch structured PII (emails, phones, SSN, cc#, IP).', solution: 'Compiled regex patterns; offsets returned for redaction.', example: 'ai_governance.py::PIIScanner.' },
      { name: 'Input scan (fail-closed)', problem: 'PII in prompts = PII in model logs + prompt cache.', solution: 'Reject request at governance layer; audit.', example: 'Rejected unless tenant explicitly opts in.' },
      { name: 'Output scan', problem: 'Model might hallucinate or leak PII.', solution: 'Scan before response returns; redact or block.', example: 'Second pass after generation.' },
      { name: 'NER-based scan (Presidio)', problem: 'Regex misses person names, addresses, dates.', solution: 'Named-entity recognition via Presidio.', example: 'GAP-ANALYSIS.md priority #3.' },
      { name: 'PII-aware caching', problem: 'Caching a PII response = persistent leak.', solution: 'Never cache responses containing PII; cache-key hash excludes PII-flagged keys.', example: 'Cache.set() checks pii_flag; refuses on true.' },
      { name: 'Per-tenant policy', problem: 'Regulated tenant handles PII legitimately.', solution: 'Tenant flag: "we handle PII; do not scan"; logged to audit.', example: 'governance.policies table.' },
      { name: 'Redaction API', problem: 'Need to show the PII was detected without exposing it.', solution: 'Return offsets; caller decides mask strategy.', example: 'Detection returns offsets; redaction is caller-scoped.' },
    ],
  },
  // -------------------------------------------------- AuthN / AuthZ
  {
    id: 'authnz',
    title: 'AuthN / AuthZ',
    blurb: 'JWT for users, API keys for machines, scopes for capabilities.',
    docsUrl: 'https://www.rfc-editor.org/rfc/rfc7519',
    docsLabel: 'RFC 7519 — JWT',
    rows: [
      { name: 'JWT (short-lived)', problem: 'Long-lived tokens = bigger blast radius on compromise.', solution: '15-minute access + refresh; identity-svc rotates keys.', example: 'Gateway verifies via JWKS cache from identity-svc.' },
      { name: 'API keys (machine)', problem: 'SDK can\'t interactively login.', solution: 'Fernet-encrypted keys in DB; scoped per tenant + role.', example: 'POST header X-API-Key or Authorization: Bearer <key>.' },
      { name: 'Scopes', problem: 'Coarse roles leak capability.', solution: 'Fine-grained scopes: docs:read, docs:write, admin:all.', example: 'Every endpoint declares required scope; gateway enforces.' },
      { name: 'RBAC', problem: 'Who can do what at the role level.', solution: 'Role table + role_scopes join; assigned at tenant boundary.', example: 'governance-svc owns the role/scope matrix.' },
      { name: 'ABAC / attribute-based', problem: 'RBAC alone can\'t express "same department" or "owner".', solution: 'Policy rule evaluates attributes (resource owner, tenant tier).', example: 'CEL-backed policies in governance.policies; engine integration pending.' },
      { name: 'mTLS (service-to-service)', problem: 'Any pod-to-pod trust is a breach path.', solution: 'Istio PeerAuthentication STRICT; AuthorizationPolicy per service.', example: 'infra/istio/20-peer-authentication.yaml.' },
      { name: 'Idempotent auth ops', problem: 'Retrying a key-rotation can double-invalidate.', solution: 'Idempotency keys on rotation; audit every change.', example: 'Rotation endpoint requires Idempotency-Key.' },
    ],
  },
  // -------------------------------------------------- SSO
  {
    id: 'sso',
    title: 'SSO',
    blurb: 'OIDC, SAML, SCIM — every enterprise asks on day one.',
    docsUrl: 'https://openid.net/connect/',
    docsLabel: 'OpenID Connect spec',
    rows: [
      { name: 'OIDC (Google/MS/Okta)', problem: 'Enterprise users expect SSO, not a separate password.', solution: 'OIDC discovery + code flow + PKCE.', example: 'GAP-ANALYSIS.md priority #1. Identity-svc will mint local JWTs from OIDC claims.' },
      { name: 'SAML 2.0', problem: 'Many enterprises still run SAML IdPs.', solution: 'SAML SP endpoint; metadata federation.', example: 'Not yet — required by specific verticals.' },
      { name: 'SCIM', problem: 'Hand-provisioning users is a compliance failure.', solution: 'SCIM 2.0 API for automated create/update/deactivate.', example: 'Planned alongside SSO.' },
      { name: 'IdP group mapping', problem: 'Roles in DocuMind must derive from IdP groups.', solution: 'group_claim → role mapping table per tenant.', example: 'groups: ["docu-admin"] → role admin.' },
      { name: 'MFA', problem: 'SSO without MFA leaves a password gap.', solution: 'Delegate to IdP; optionally TOTP for local fallback.', example: 'TOTP implemented locally; SSO users enforce IdP-side MFA.' },
      { name: 'Just-in-time provisioning', problem: 'First login of an SSO user — no DocuMind row yet.', solution: 'Create tenant_user row on first successful assertion.', example: 'JIT under the OIDC flow.' },
    ],
  },
  // -------------------------------------------------- LDAP
  {
    id: 'ldap',
    title: 'LDAP / Directory',
    blurb: 'Air-gapped or legacy enterprises — SSO is not always an option.',
    docsUrl: 'https://www.rfc-editor.org/rfc/rfc4511',
    docsLabel: 'RFC 4511 — LDAPv3',
    rows: [
      { name: 'Simple bind', problem: 'User authenticates against Active Directory.', solution: 'ldap3 bind with userPrincipalName.', example: 'Planned — required by some air-gapped customers.' },
      { name: 'Group search', problem: 'Role derivation from AD groups.', solution: 'Search memberOf; map DN → role.', example: 'Mirrors the OIDC group-mapping pattern.' },
      { name: 'Nested groups', problem: 'AD groups contain groups.', solution: 'Recursive DN resolution.', example: 'Guarded by depth limit to prevent cycles.' },
      { name: 'Cert / Kerberos auth', problem: 'Enterprises ban passwords entirely.', solution: 'mTLS client cert or GSSAPI/Kerberos.', example: 'Enterprise feature; deprioritized until first request.' },
      { name: 'Periodic sync', problem: 'User roles change in AD; DocuMind must follow.', solution: 'Hourly sync job; reconciler updates roles.', example: 'Scheduled job emits events into governance-svc.' },
    ],
  },
  // -------------------------------------------------- Istio
  {
    id: 'istio',
    title: 'Istio',
    blurb: 'mTLS everywhere, policy at the sidecar, canary + retry without touching code.',
    docsUrl: 'https://istio.io/latest/docs/',
    docsLabel: 'Istio documentation',
    rows: [
      { name: 'PeerAuthentication STRICT', problem: 'Internal traffic unencrypted = breach path.', solution: 'PeerAuthentication mode: STRICT at namespace or mesh level.', example: 'infra/istio/20-peer-authentication.yaml — STRICT mesh-wide.' },
      { name: 'AuthorizationPolicy (default-deny)', problem: 'Any service can call any service.', solution: 'Default-deny + explicit allow per source principal.', example: 'infra/istio/30-authorization-policy.yaml.' },
      { name: 'VirtualService canary', problem: 'New revisions need gradual traffic shifting.', solution: 'VS weight 90/10 → 50/50 → 0/100 over bake time.', example: 'Used for every revision bump.' },
      { name: 'DestinationRule outlier detection', problem: 'One bad pod shouldn\'t get traffic.', solution: 'Eject hosts with consecutive 5xxs for a window.', example: 'Complements circuit breakers at the transport layer.' },
      { name: 'Retry + timeout', problem: 'Transient failures shouldn\'t reach the user.', solution: 'VS retry policy: 3 retries with 100ms jitter; 3s upstream timeout.', example: 'Per-route tuned for GET vs POST.' },
      { name: 'Envoy filter extensions', problem: 'Need mesh-native request transforms (header inject, rate-limit).', solution: 'EnvoyFilter resources; RateLimitService for advanced cases.', example: 'Header sanitization at the ingress gateway.' },
      { name: 'Kiali graph', problem: 'Operators can\'t mentally model 8+ services.', solution: 'Kiali renders the live mesh + policy overlays.', example: 'Weekly review catches orphans and policy regressions.' },
    ],
  },
  // -------------------------------------------------- Circuit breaker types
  {
    id: 'cb-types',
    title: 'Circuit Breaker Types',
    blurb: 'Not just OPEN/CLOSED — specialized breakers for token, loop, telemetry, cognition.',
    docsUrl: 'https://martinfowler.com/bliki/CircuitBreaker.html',
    docsLabel: 'Martin Fowler — CircuitBreaker',
    rows: [
      { name: 'Generic failure-count CB', problem: 'Basic pattern: trip after N consecutive failures.', solution: 'CLOSED → (threshold) → OPEN → (timeout) → HALF_OPEN.', example: 'libs/py/documind_core/circuit_breaker.py.' },
      { name: 'Retrieval CB', problem: 'Qdrant/Neo4j slow = retrieval cascade.', solution: 'Wrap vector + graph calls; fail fast + degraded mode.', example: 'RetrievalCircuitBreaker in breakers.py.' },
      { name: 'Token CB', problem: 'Runaway LLM loop eats budget.', solution: 'Check per-tenant token quota; decision: allow / throttle / block.', example: 'TokenCircuitBreaker + TokenBreakerDecision enum.' },
      { name: 'Agent-loop CB', problem: 'Agents can recurse forever.', solution: 'Track depth + wall-clock + step count; open at thresholds.', example: 'AgentLoopCircuitBreaker for multi-hop agents.' },
      { name: 'Observability CB (inverted)', problem: 'Dead OTel collector hangs every request.', solution: 'Inverted polarity — OPEN means "skip export silently".', example: 'ObservabilityCircuitBreaker; telemetry is best-effort.' },
      { name: 'Cognitive CB (CCB)', problem: 'Model itself fails: loops, drifts, jailbreaks.', solution: 'Signals watch token stream; open on repetition/drift/rule-breach.', example: 'libs/py/documind_core/ccb.py + breakers.py (paper arXiv:2604.13417).' },
      { name: 'Rate-based CB', problem: 'Failure rate % matters more than absolute count.', solution: 'Rolling window; open if failure-rate > threshold.', example: 'Alternative config of generic CB; not default.' },
      { name: 'Concurrency limiter (bulkhead)', problem: 'One slow call holds N threads.', solution: 'Semaphore-bounded concurrent calls per dep.', example: 'Complements CB; applied on inference-svc Ollama calls.' },
      { name: 'Adaptive CB', problem: 'Static thresholds don\'t track actual upstream health.', solution: 'Slide thresholds based on rolling latency + error percentiles.', example: 'Not yet — candidate for future work.' },
    ],
  },
  // -------------------------------------------------- API Gateway
  {
    id: 'api-gateway',
    title: 'API Gateway',
    blurb: 'Single enforcement point for TLS, auth, rate-limit, correlation, idempotency.',
    docsUrl: 'https://microservices.io/patterns/apigateway.html',
    docsLabel: 'microservices.io — API Gateway',
    rows: [
      { name: 'JWT validation', problem: 'Every service re-implementing JWT = drift + bugs.', solution: 'JWKS cache + local verify; identity-svc is the only issuer.', example: 'Gateway rejects invalid JWT with 401 + error envelope.' },
      { name: 'Correlation-id injection', problem: 'Cross-service debugging requires a thread.', solution: 'Inject X-Correlation-Id if missing; propagate as OTel baggage.', example: 'Every downstream span has it as an attribute.' },
      { name: 'Per-tenant rate-limit', problem: 'IP-only rate limit punishes legit shared NATs.', solution: 'Bucket by (tenant_id, IP); tune per tenant tier.', example: 'Token bucket with burst 20, sustained 100 rpm.' },
      { name: 'Idempotency middleware', problem: 'At-least-once + retries = duplicates.', solution: 'Idempotency-Key → cached response for 24h.', example: 'Redis-backed; keyed by (tenant, key).' },
      { name: 'Request/response transform', problem: 'Backends evolve; clients shouldn\'t.', solution: 'Adapter layer rewrites headers / shapes when contracts change.', example: 'Used during v1→v2 transition windows.' },
      { name: 'Admin path isolation', problem: 'Admin traffic shouldn\'t compete with users.', solution: '/api/v1/admin/* routes to dedicated bucket + elevated scope.', example: 'Separate metrics + alerts from user path.' },
      { name: 'Static response (health)', problem: 'Noisy probes shouldn\'t hit services.', solution: 'Gateway replies to /health directly.', example: 'Reduces load; 200 OK text/plain.' },
      { name: 'Canary routing', problem: 'Gradual rollout of new backend versions.', solution: 'Header-based routing (X-Canary: true) + weighted routing.', example: 'Used with Istio VS for dual-layer canary.' },
    ],
  },
  // -------------------------------------------------- Load Balancer
  {
    id: 'load-balancer',
    title: 'Load Balancer',
    blurb: 'Where traffic decides where to go. Cloud LB at edge, mesh LB inside.',
    docsUrl: 'https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/load-balancing-overview',
    docsLabel: 'LB overview',
    rows: [
      { name: 'Round-robin', problem: 'Simple, fair for homogeneous pods.', solution: 'Default in most LBs; cycles pods in order.', example: 'Envoy default when all pods equally weighted.' },
      { name: 'Least-connections', problem: 'Long-lived connections pile up on one pod.', solution: 'Send new request to pod with fewest active.', example: 'Better for SSE / WebSocket endpoints.' },
      { name: 'IP hash / session affinity', problem: 'Sticky sessions for stateful UX.', solution: 'Hash client IP → consistent pod.', example: 'Rarely used — we keep sessions in Redis instead.' },
      { name: 'Weighted round-robin', problem: 'Canary rollouts need weighted traffic.', solution: 'Assign weights per subset; gradually shift.', example: 'Istio DR subsets + VS weights.' },
      { name: 'Outlier ejection', problem: 'Bad pod keeps getting traffic until K8s evicts.', solution: 'Eject on N consecutive 5xxs for M seconds.', example: 'Istio DestinationRule outlierDetection.' },
      { name: 'Active-passive failover', problem: 'Hot standby for critical services.', solution: 'Primary pool + failover pool; flip on primary failure.', example: 'Pattern for future multi-region DR.' },
      { name: 'Anycast / geo-routing', problem: 'Global latency.', solution: 'DNS returns nearest PoP.', example: 'Edge CDN tier; closest of global PoPs.' },
      { name: 'Layer-4 vs Layer-7', problem: 'L4 is faster; L7 supports routing rules.', solution: 'L4 for raw TCP (Redis, PG); L7 for HTTP.', example: 'Internal LB L4; external edge L7.' },
    ],
  },
  // -------------------------------------------------- CDN
  {
    id: 'cdn',
    title: 'CDN / Edge',
    blurb: 'Compress latency at the edge; keep policy at the gateway.',
    docsUrl: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching',
    docsLabel: 'MDN — HTTP Caching',
    rows: [
      { name: 'Static-asset caching', problem: 'Assets re-fetched from origin waste bandwidth.', solution: 'Cache-Control: public, max-age + immutable fingerprints.', example: '/assets/* cached at edge; purged on deploy.' },
      { name: 'Dynamic bypass', problem: 'Caching personalized content leaks it.', solution: 'Cache-Control: private, no-store on /api/*.', example: 'Edge proxies /api/* without caching.' },
      { name: 'Conditional validators', problem: 'Cached copy may still be stale.', solution: 'ETag + If-None-Match; 304 saves body transfer.', example: 'Origin returns ETag; NGINX revalidates.' },
      { name: 'Vary header discipline', problem: 'Cache serves English to Spanish requester.', solution: 'Vary: Accept-Language / Accept-Encoding when relevant.', example: 'Explicit Vary avoided unless required (cache-key explosion).' },
      { name: 'HSTS + preload', problem: 'First request can downgrade to HTTP.', solution: 'Strict-Transport-Security header + hstspreload.org.', example: 'HSTS: max-age=31536000; includeSubDomains; preload.' },
      { name: 'Subresource integrity', problem: 'Compromised CDN delivers tampered JS.', solution: 'SRI hash in <script> tags.', example: 'Set for any third-party script included.' },
      { name: 'Purge on deploy', problem: 'New asset version not visible for TTL.', solution: 'CI triggers purge via edge API after rollout.', example: 'Purge by cache-tag on every deploy.' },
      { name: 'Upload bypass', problem: 'Large POST bodies double-buffered at edge = memory blow.', solution: 'proxy_request_buffering off for /upload.', example: 'NGINX streams uploads straight to MinIO pre-signed URL.' },
    ],
  },
];
