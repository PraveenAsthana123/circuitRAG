'use client';

/**
 * Tech lead lens: cross-team API contract design, code-review gates,
 * and how to ship a feature across multiple services without
 * coupling deploys. Emphasis on §10 LLD, §17 Solutions, §21 Best
 * practices, §24 Production issues, §26 Debugging checklist.
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'cross-team-api-contract',
    title: '1. Cross-team API contract design (tech lead lens)',
    status: 'shipped',
    coreConcept: 'When 3+ services participate in one feature, the API contract is the only artifact that lets each team ship independently. Owning the contract means versioning, deprecation policy, idempotency keys, and the discipline to evolve without breaking consumers.',
    oneLiner: 'API contract = the seam between teams. Get it right and parallel work ships; get it wrong and every PR is a merge negotiation.',
    businessContext: 'We need to roll out a multi-step feature (e.g. document ingestion → embedding → indexing → eval) across 4 services owned by 3 teams without forcing a coupled release.',
    fiveW: {
      what: 'A versioned, idempotent, schema-validated HTTP/gRPC interface between two services. Includes: URL versioning, request schema, response schema, error envelope, idempotency key, deprecation policy.',
      why: 'Without an explicit contract, every consumer becomes a coupling point. Schema drift = production incident. Without idempotency keys = duplicate writes on retry.',
      where: 'Every cross-team service boundary in DocuMind: ingestion-svc → eval-svc, retrieval-svc → inference-svc, gateway → all services.',
      when: 'Anytime ≥ 2 teams collaborate on one feature. The contract precedes the code.',
      who: 'Tech leads from each consuming team co-author. Platform owns versioning + tooling. SRE consumes for capacity planning.',
    },
    interview30s: 'When I lead a cross-team feature, I ship the contract first — versioned URL, Pydantic request/response schemas, error envelope with detail/error_code/correlation_id, idempotency key for write paths. Each team can then mock the contract, build in parallel, and integrate at the seam. Deprecation is policy-driven: support old + new for 2 release cycles, log deprecation warnings, then remove. The non-negotiable test is a contract test that runs against the mock AND the real implementation in CI.',
    coreBuildingBlocks: [
      'URL versioning: /api/v1/docs vs /api/v2/docs',
      'Request schemas: Pydantic models with strict validation',
      'Response schemas: SuccessResponse + PaginatedResponse + ErrorResponse',
      'Error envelope: {detail, error_code, correlation_id}',
      'Idempotency key: X-Idempotency-Key header, persisted 24h',
      'Deprecation: Sunset header + log warnings + 2-cycle support',
      'Contract tests: schema-validates against mock + real',
    ],
    architectureRelevance: {
      backend: 'FastAPI routes thin: HTTP only, no SQL, no business logic. Pydantic validates at boundary. response_model on every endpoint.',
      rag: 'Retrieval contract: query + tenant + top_k. Response: chunks + scores + degraded flag.',
      ai: 'Inference contract: prompt + chunks + tenant. Response: streaming SSE + citations + cost (tokens, USD).',
      microservices: 'Outbox + idempotency keys mean at-least-once delivery is safe. Saga compensates per-step. Circuit breaker per dependency.',
    },
    flowchart: `flowchart LR
  A[Client] --> B["POST /api/v1/docs"]
  B --> C{Idempotency-Key seen?}
  C -->|yes| D[Return cached response]
  C -->|no| E[Validate Pydantic request]
  E --> F[Service handler]
  F --> G[Repository]
  G --> H[(DB)]
  F --> I[Persist response by key]
  I --> J[Return SuccessResponse]
  J --> A`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant GW as Gateway
  participant Svc as Service
  participant IS as IdempotencyStore
  participant DB as DB
  Cli->>GW: POST /api/v1/docs + X-Idempotency-Key + body
  GW->>Svc: forward
  Svc->>IS: get cached(key)
  IS-->>Svc: nil OR cached response
  alt nil
    Svc->>DB: INSERT row
    DB-->>Svc: ok
    Svc->>IS: persist key + response
    Svc-->>Cli: 201 Created
  else cached
    Svc-->>Cli: cached 201 (replay)
  end`,
    coreLayers: [
      { layer: 'Versioning', responsibility: 'URL prefix /api/vN; deprecate by Sunset header; remove after 2 release cycles.' },
      { layer: 'Schema', responsibility: 'Pydantic request + response models. response_model= on every route. No raw dict returns.' },
      { layer: 'Error envelope', responsibility: '{detail: str, error_code: str, correlation_id: str}. AppError → mapped to HTTP via middleware.' },
      { layer: 'Idempotency', responsibility: 'X-Idempotency-Key header. IdempotencyStore persists first response 24h. Replay on duplicate.' },
      { layer: 'Contract tests', responsibility: 'Schema-validates against mock AND real impl. Runs in CI on every PR.' },
      { layer: 'Deprecation', responsibility: 'Sunset header + Deprecation header + warning log. Support old + new for 2 cycles.' },
    ],
    problem: 'Without a contract, every cross-team change is a merge negotiation. Schema drift surfaces as production incidents. At-least-once delivery duplicates writes.',
    whyThisApproach: 'Contract-first lets teams build in parallel against mocks. Idempotency makes retries safe. Versioning + deprecation lets old consumers stay alive while new ones land.',
    whenToUse: [
      'Any feature spanning ≥ 2 services',
      'Cross-team features (different repos / different release cycles)',
      'External-facing APIs',
      'Write paths exposed to retry (Kafka consumers, mobile clients)',
    ],
    whenNotToUse: [
      'Internal helpers within one service — overkill',
      'Read-only debug endpoints — keep them simple',
      'Throwaway prototype — just write the code',
    ],
    input: 'Client request with versioned URL + Pydantic-validated body + optional X-Idempotency-Key',
    process: [
      'Gateway: decode JWT, set correlation_id',
      'Middleware: validate Pydantic request body — reject 422 on schema fail',
      'Idempotency: check key in store, replay cached response if hit',
      'Handler: call repository / external service',
      'Persist: write idempotency key + response for 24h replay',
      'Return: response_model serialized JSON + standard headers',
    ],
    output: 'JSON response matching response_model schema; idempotency key cached; correlation_id flows through trace.',
    alternatives: [
      { name: 'GraphQL', tradeoff: 'Single endpoint; harder to version + cache; weaker idempotency primitives' },
      { name: 'gRPC', tradeoff: 'Binary + strong typing; harder to debug; weaker browser support' },
      { name: 'OpenAPI-generated clients', tradeoff: 'Auto-sync clients; spec drift if hand-edited; needs codegen pipeline' },
    ],
    challenges: [
      'Idempotency key collision when clients reuse keys',
      'Deprecation discipline — old endpoints linger past sunset date',
      'Contract tests skipped in CI when "tests are slow"',
      'Schema evolution — adding required field is breaking',
      'Error code proliferation — every team invents their own',
    ],
    edgeCases: [
      { case: 'Client retries with same idempotency key after partial success', solution: 'Replay cached response; never re-execute write' },
      { case: 'Deprecated endpoint still has traffic past Sunset date', solution: 'Add 410 Gone after grace period; track via metric' },
      { case: 'Client sends future-dated request schema (v2 to /api/v1)', solution: 'Validate against v1 schema; ignore unknown fields OR 422 on strict mode' },
      { case: 'Streaming response cut mid-way', solution: 'Idempotency key persists final response only on completion; client retries safely' },
    ],
    failureModes: [
      { mode: 'Idempotency store down', detect: 'Cache write failure metric', recover: 'Fail-closed: reject writes until restored, OR fail-open with alert (policy-driven)' },
      { mode: 'Schema validation hot-path bottleneck', detect: 'p95 spent in middleware', recover: 'Compile schemas once at startup; profile validators' },
      { mode: 'Contract test bypass', detect: 'CI badge missing on PR', recover: 'Required check enforced on main branch' },
    ],
    monitoring: [
      'Endpoint latency p50/p95/p99 per (route, version)',
      'Idempotency replay rate (high replay = client bug)',
      'Deprecation warning count per endpoint',
      'Schema validation failures (4xx breakdown)',
    ],
    testing: [
      'Contract test: schema validates against mock impl',
      'Contract test: schema validates against real impl',
      'Idempotency test: same key twice → same response, no double-write',
      'Deprecation test: Sunset header present on deprecated routes',
    ],
    security: [
      'JWT validated at gateway, claims trusted internally',
      'Pydantic strict mode: reject unknown fields',
      'Rate limit per (tenant, route) at gateway',
      'PII fields in error envelope are explicitly redacted',
    ],
    scaling: [
      'Idempotency store: Redis with TTL eviction',
      'Schema validation: compile once, reuse',
      'Contract tests in CI: parallelize across routes',
    ],
    maturity: {
      mvp: 'Pydantic models on every route + response_model + correlation_id',
      production: 'X-Idempotency-Key + deprecation policy + contract tests in CI',
      enterprise: 'OpenAPI auto-spec + client SDK generation + dashboard for deprecation tracking',
    },
    limitations: [
      'Tech-lead-lens omits per-team org dynamics (see /admin/eng-manager/deep)',
      'Concrete code lives in services/ — this is the contract layer above it',
    ],
    projectFit: [
      'libs/py/documind_core/exceptions.py — AppError taxonomy',
      'libs/py/documind_core/middleware.py — error_handlers + correlation_id',
      'libs/py/documind_core/idempotency.py — IdempotencyStore',
      'services/*/schemas/ — Pydantic request/response models',
      'mcp/tests/drill_*_contract.py — contract tests per service',
    ],
    interviewLine: 'I lead cross-team features by shipping the contract first: versioned URL, Pydantic schemas, error envelope, idempotency key. Teams build in parallel against the mock; integration is the last step, not the first. Deprecation is policy-driven: 2 cycles of dual-support, then removal. The contract is reviewed before any code.',
    implementationSteps: [
      { step: 'Pin URL version', logic: '/api/v1/<resource> — never re-version a live route; v2 is a NEW route mounted alongside.' },
      { step: 'Pydantic request/response', logic: 'One model per direction; required vs optional explicit; no raw dict in router or service.' },
      { step: 'Error envelope', logic: '{detail, error_code, correlation_id} on every 4xx/5xx; client maps error_code → UX message.' },
      { step: 'Idempotency key', logic: 'X-Idempotency-Key on POST/PUT; 24h TTL; replay returns cached response (not duplicate).' },
      { step: 'Mock server', logic: 'Generated from OpenAPI; clients build against mock day 1; integration day N.' },
      { step: 'Contract test in CI', logic: 'Same test runs against mock + real; gates merge; contract drift catches it.' },
      { step: 'Deprecation policy', logic: 'Sunset header, warning logs, 2-cycle dual-support, then removal — never sudden.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/inference-svc/app/routers/ask.py — contract-first router
from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from libs.py.documind_core.exceptions import IdempotencyConflict
from libs.py.documind_core.idempotency import IdempotencyStore

router = APIRouter(prefix="/api/v1", tags=["ask"])

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    tenant_id: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)

class Citation(BaseModel):
    chunk_id: str
    score: float
    excerpt: str

class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    correlation_id: str
    degraded: bool = False
    cost_tokens: int

class ErrorBody(BaseModel):
    detail: str
    error_code: str
    correlation_id: str

@router.post(
    "/ask",
    response_model=AskResponse,
    responses={
        409: {"model": ErrorBody, "description": "Idempotency key replay"},
        429: {"model": ErrorBody, "description": "Token budget exhausted"},
    },
)
async def ask(
    req: AskRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    correlation_id: str = Depends(get_correlation_id),
    idem: IdempotencyStore = Depends(get_idem_store),
    svc: InferenceService = Depends(get_inference_service),
) -> AskResponse:
    if x_idempotency_key:
        cached = await idem.get(req.tenant_id, x_idempotency_key)
        if cached and cached.payload_hash == req.payload_hash():
            return AskResponse(**cached.response)
        if cached:
            raise IdempotencyConflict(x_idempotency_key)
    result = await svc.answer(req, correlation_id=correlation_id)
    if x_idempotency_key:
        await idem.store(req.tenant_id, x_idempotency_key, req, result, ttl_h=24)
    return result`,
    },
    realUseCase: 'A multi-team RAG feature spanned ingestion-svc + retrieval-svc + inference-svc. Contract pinned in week 1: OpenAPI spec + Pydantic models + mock server + idempotency keys + Sunset header for the soon-deprecated /v0 path. Three teams built in parallel against the mock. Integration in week 4 was a 2-day exercise instead of a 2-week negotiation. Drill_contract_v1 ran in CI on every PR — caught a downstream team accidentally adding a required field that would have broken older clients.',
    prosCons: {
      pros: [
        'Teams build in parallel (mock from day 1)',
        'Contract drift caught at PR-time, not integration-time',
        'Idempotency keys make POST retries safe',
        'Versioned URL enables non-breaking evolution',
        'Error envelope makes client error UX uniform',
      ],
      cons: [
        'Front-loads design effort; feels slower at week 1',
        'Contract test maintenance overhead grows with surface area',
        'Idempotency store is one more dependency',
        'Deprecation policy requires discipline (don\'t skip dual-support)',
      ],
    },
    comparison: {
      left: 'Code-first / "we\'ll figure out the contract as we go"',
      right: 'Contract-first / spec + mock day 1',
      rows: [
        { aspect: 'Parallel team velocity', left: 'Teams blocked on each other', right: 'Teams build against mock independently' },
        { aspect: 'Contract drift detection', left: 'Found at integration', right: 'Found at PR via contract test' },
        { aspect: 'Breaking changes', left: 'Discovered when client breaks', right: 'Caught by versioning + Sunset' },
        { aspect: 'Idempotency', left: 'Handled per-endpoint ad hoc', right: 'Standard X-Idempotency-Key everywhere' },
        { aspect: 'Error handling', left: 'Strings, codes, sometimes objects', right: 'Uniform {detail, error_code, correlation_id}' },
      ],
    },
    solutions: [
      { problem: 'Cross-team merge negotiations', solution: 'Pin contract first; build against mock' },
      { problem: 'POST retry creates duplicates', solution: 'X-Idempotency-Key with 24h replay store' },
      { problem: 'Client misreads error reasons', solution: 'Standard error_code enum on error envelope' },
      { problem: 'Breaking change shipped accidentally', solution: 'Contract test in CI gates merge' },
      { problem: 'Old clients stuck on v0', solution: 'Sunset header + 2-cycle dual support + warning logs' },
    ],
    bestPractices: {
      do: [
        'Mock server from OpenAPI on day 1',
        'Pydantic models for every request/response',
        'X-Idempotency-Key on every write',
        'Standard error envelope on every 4xx/5xx',
        'Contract test runs against mock AND real impl',
        'Dual-support deprecations for ≥2 release cycles',
      ],
      avoid: [
        'Re-versioning a live route in place',
        'Returning raw dict from a router (use response_model)',
        'Per-endpoint ad-hoc idempotency strategies',
        'Breaking changes without Sunset header',
      ],
      optimize: [
        'Generate client SDK from OpenAPI (typed, no hand-written calls)',
        'Cache idempotency lookups in Redis (DB only on miss)',
        'Pact-style consumer-driven contract tests',
        'Field-level deprecation warnings via response header',
      ],
    },
    antiPatterns: [
      'Code-first with "we\'ll write the contract later" (never happens)',
      'Idempotency keys ignored on retry (duplicate writes)',
      'Per-endpoint custom error shapes',
      'Sudden field removal without Sunset',
      'Versioned URL but not versioned schema (silent breakage)',
    ],
    testTypes: [
      'Contract: OpenAPI schema validates request + response',
      'Idempotency drill: same key + same payload → same response',
      'Idempotency drill: same key + different payload → 409 conflict',
      'Deprecation: v0 returns Sunset header + warning log',
      'Error envelope: every 4xx/5xx matches {detail, error_code, correlation_id}',
    ],
    testScenarios: [
      { scenario: 'Same idempotency key + same payload retry', expected: 'Cached response returned (200), no duplicate side effect' },
      { scenario: 'Same idempotency key + different payload', expected: '409 Conflict with error_code=IDEMPOTENCY_PAYLOAD_MISMATCH' },
      { scenario: 'Missing required field in request', expected: '422 with detail listing the missing field' },
      { scenario: 'Token budget exhausted', expected: '429 + Retry-After header + standard error envelope' },
      { scenario: 'Call to /api/v0/ask after deprecation cycle', expected: 'Response includes Sunset header + warning' },
    ],
    testData: [
      { type: 'Idempotency replay fixture', example: 'Same key K + same hash H sent twice; second call returns cached' },
      { type: 'Cross-team mock harness', example: 'OpenAPI mock used by 3 client teams while server team builds real impl' },
      { type: 'Sunset migration set', example: 'Old client calls /v0; new client calls /v1; both run in parallel for 2 cycles' },
    ],
    debuggingChecklist: [
      'Idempotency replay returning wrong response? Check payload_hash matches; check store TTL',
      'Client sees 422? Print request body — check missing/extra fields against schema',
      'Contract test failing? Diff OpenAPI exported from app vs spec file',
      'Sunset header missing? Verify deprecation policy applied + middleware order',
      'Correlation ID empty? Middleware ordering — must run before router',
    ],
    productionIssues: [
      { issue: 'Webhook retry stormed and duplicated 1.2K user creations', rootCause: 'Endpoint accepted X-Idempotency-Key header but never persisted it; replay treated as new request.' },
      { issue: 'Mobile clients broke after a "non-breaking" enum addition', rootCause: 'Old clients did exhaustive switch on enum; new value triggered default = error path. Should have been a separate field.' },
      { issue: 'Cross-team integration in week 4 took 8 days', rootCause: 'Mock server diverged from real impl; contract test only ran against real impl. Both must be tested.' },
    ],
    performance: [
      'Idempotency lookup: Redis GET on hit (≤2ms p95), Postgres on miss (~10ms)',
      'Schema validation overhead: ~0.5ms p95 per Pydantic round-trip',
      'OpenAPI spec generation: cached at startup; ~50ms one-time',
    ],
    costConsiderations: [
      'Idempotency store size: ~1KB per key × 24h TTL × keys/day ≈ scales linearly',
      'Mock server hosting: ~$5/mo on a small EC2 or a free CI runner',
      'OpenAPI client SDK gen: free — saves N teams from hand-writing clients',
    ],
    observability: [
      'Trace: every request gets correlation_id propagated via response + log + audit',
      'Metrics: idempotency hit ratio, contract violation count, deprecation hit count',
      'Logs: structured with correlation_id; deprecation hits log at WARN with route + client info',
      'Headers: Sunset + Deprecation header on deprecated routes for client telemetry',
    ],
    metrics: [
      { name: 'documind_idempotency_replay_total{tenant,outcome}', example: 'Counter; outcome=hit/miss/conflict; alert if conflict rate > 1%' },
      { name: 'documind_contract_violation_total{route}', example: 'Counter; alert at any value > 0 (PR should have caught it)' },
      { name: 'documind_deprecated_route_hits_total{route}', example: 'Counter; informs deprecation timing — when does old traffic actually drop?' },
      { name: 'documind_request_validation_failures_total{route,field}', example: 'Counter; spike means a client is sending wrong shape' },
    ],
    tradeoffs: [
      { decision: 'Versioned URL vs versioned content type', tradeoff: 'URL is grep-able and easier to route; content-type is HTTP-pure but harder to debug' },
      { decision: 'Idempotency in DB vs Redis', tradeoff: 'DB is durable; Redis is fast — typically Redis with DB write-through' },
      { decision: 'Pydantic validation vs raw dict', tradeoff: 'Validation has 0.5ms cost; catches wrong shape at boundary, not deep in service' },
      { decision: 'OpenAPI mock vs hand-written stub', tradeoff: 'Generated mock is free + always in sync; hand-written can be richer but rots' },
    ],
    decisionMatrix: [
      { option: 'Code-first', whenToUse: 'Solo project, internal tool, < 100 LOC service' },
      { option: 'Contract-first (this)', whenToUse: 'Cross-team feature, public API, anything client SDKs depend on' },
      { option: 'API gateway as contract owner', whenToUse: 'Many small services where one team owns the gateway + contract surface' },
    ],
    starStory: {
      situation: 'Three teams (mobile, web, backend) shipped a real-time RAG feature with a hard launch date. The previous similar effort took 6 weeks; this had 4.',
      task: 'Cut integration-time-to-zero. Decouple team velocity from each other.',
      action: 'Wrote the OpenAPI spec + Pydantic models in week 1. Spun up a mock server from the spec. Wrote contract drill that runs against both mock + real impl. Defined error envelope + X-Idempotency-Key as standards. Mobile + web teams built against mock; backend team built real impl. Integration was 2 days of edge-case hardening, not 2 weeks of "what does this field mean?".',
      result: 'Shipped on time. Zero integration-day surprises. Pattern adopted by two more cross-team features. Contract drill became a CI standard.',
    },
    interviewTraps: [
      'Saying "we use idempotency keys" without specifying TTL or conflict behavior',
      'Versioning the URL but evolving the schema in place',
      'Custom error shapes per endpoint (clients can\'t write one error handler)',
      'No mock server — teams stall waiting for the real impl',
      'Sunset header set but no warning log + no dual-support window',
    ],
    finalScript: 'When I lead a cross-team feature, the contract precedes the code. URL gets a version (/api/v1). Request and response are Pydantic schemas. Error envelope is standard: detail + error_code + correlation_id. Write paths take an X-Idempotency-Key, persisted 24 hours so retries are safe. Deprecation has a policy: Sunset header + warning logs + 2-cycle dual-support before removal. CI runs contract tests against both the mock and the real implementation. With the contract pinned, teams build in parallel; integration is the last step. Without it, every PR becomes a merge negotiation.',
  },
  {
    slug: 'ultimate-tech-lead-master-checklist',
    title: '2. Ultimate tech lead master checklist (2026)',
    status: 'shipped',
    coreConcept: 'A strong tech lead does not release based on confidence or velocity. They release against an evidence-backed lifecycle checklist that covers architecture, tracing, microservices, coding quality, testing, security, deployment, observability, governance, FinOps, DevEx, technical evolution, debt, incident response, and AI-specific controls.',
    oneLiner: 'Tech lead quality = design discipline + release discipline + operational evidence.',
    businessContext: 'A project can look healthy in code review and still fail in production because rollback, tracing, tenant isolation, eval gates, or audit evidence were weak. The checklist forces the lead to prove readiness across the whole lifecycle instead of trusting intuition.',
    fiveW: {
      what: 'A 17-section tech lead release and governance checklist covering design, build, test, secure, deploy, observe, govern, evolve, and AI.',
      why: 'It converts production-readiness from opinion into evidence. It also gives one repeatable standard for audits, interviews, release gates, and onboarding.',
      where: 'Applied across architecture review, PR review, CI/CD sign-off, pre-release review, post-release follow-up, and audit preparation.',
      when: 'Before every production release, during major design reviews, before compliance audits, and whenever a new service or AI capability lands.',
      who: 'Tech lead owns it; architect, security, SRE/on-call, EM, and compliance review the parts they sign.',
    },
    interview30s: 'I use a full lifecycle tech lead checklist. It starts with C4, ADRs, trust boundaries, and API contracts. Then it enforces tracing, contract tests, CI/CD gates, rollback, OWASP and secrets handling, golden-signal observability, and AI-specific controls like model versioning, prompt versioning, eval thresholds, guardrails, and token-cost monitoring. My release rule is simple: if there is a security issue, no rollback, no monitoring, a breaking change, no tracing, or untested AI, we do not ship.',
    hld: `flowchart LR
  A[Architecture and design] --> B[Coding and tests]
  B --> C[CI/CD and security]
  C --> D[Deployment and observability]
  D --> E[Governance FinOps DevEx]
  E --> F[Tech evolution and debt]
  F --> G[Incident response and AI controls]
  G --> H{Hard stop clear?}
  H -->|yes| I[Release]
  H -->|no| J[Block release]`,
    networkFlow: `flowchart LR
  Dev[Engineer] --> PR[Pull request]
  PR --> CI[CI pipeline]
  CI --> Sec[Security gates]
  CI --> Test[Test + contract + eval]
  Sec --> Rel[Release manager / tech lead]
  Test --> Rel
  Rel --> Can[Canary or blue-green]
  Can --> Obs[Logs metrics traces alerts]
  Obs --> RC[Rollback or continue]`,
    flowchart: `flowchart TD
  Start[Ready to release?] --> S1[1 Architecture and design]
  S1 --> S2[2 Tracing and distributed systems]
  S2 --> S3[3 Microservices and integration]
  S3 --> S4[4 Coding and quality]
  S4 --> S5[5 Testing strategy]
  S5 --> S6[6 CI CD]
  S6 --> S7[7 Security]
  S7 --> S8[8 Observability]
  S8 --> S9[9 Deployment]
  S9 --> S10[10 AI RAG controls]
  S10 --> S11[11 Governance]
  S11 --> S12[12 Documentation]
  S12 --> S13[13 FinOps]
  S13 --> S14[14 DevEx]
  S14 --> S15[15 Technical evolution]
  S15 --> S16[16 Technical debt]
  S16 --> S17[17 Monitoring and incident response]
  S17 --> Stop{Any hard stop?}
  Stop -->|yes| Block[Do not release]
  Stop -->|no| Ship[Release]`,
    sequence: `sequenceDiagram
  participant TL as Tech lead
  participant Arch as Architect
  participant Sec as Security
  participant CI as CI/CD
  participant SRE as On-call/SRE
  participant Audit as Auditor
  TL->>Arch: review C4 ADR boundaries
  TL->>CI: run lint test contract eval build
  CI-->>TL: gate results
  TL->>Sec: confirm threats secrets OWASP
  TL->>SRE: verify rollout rollback and alerts
  SRE-->>TL: readiness status
  Audit->>TL: ask for evidence
  TL-->>Audit: checklist + linked artifacts`,
    coreLayers: [
      { layer: 'Architecture', responsibility: 'C4 context/container/component/code, ADRs, trust zones, system boundaries, API-first contracts.' },
      { layer: 'Distributed systems', responsibility: 'Correlation ID, trace ID, baggage propagation, end-to-end request visibility.' },
      { layer: 'Quality + testing', responsibility: 'Lint, typing, defensive programming, unit/integration/contract/E2E/AI eval.' },
      { layer: 'Delivery + security', responsibility: 'Build-once CI, canary or blue-green, feature flags, SAST/SCA/secrets, rollback automation.' },
      { layer: 'Operations + governance', responsibility: 'Golden signals, dashboards, audit logs, runbooks, FinOps, debt register, incident response.' },
      { layer: 'AI controls', responsibility: 'Model/prompt versioning, guardrails, PII removal, output validation, token/GPU cost monitoring.' },
    ],
    lld: `classDiagram
  class TechLeadChecklist {
    +architecture
    +tracing
    +microservices
    +coding
    +testing
    +ci_cd
    +security
    +observability
    +deployment
    +ai_controls
    +governance
    +finops
    +devex
    +technical_evolution
    +technical_debt
    +incident_response
    +releaseGate()
  }`,
    coreBuildingBlocks: [
      '1. Architecture and design — C4 + ADR + trust zones + separation of concerns',
      '2. Distributed systems and tracing — correlation_id + trace_id + baggage propagation',
      '3. Microservices and integration — domain boundaries + DB per service + async messaging + contract tests',
      '4. Coding and quality — lint + type hints + fail-fast + boundary validation + DB query review',
      '5. Testing strategy — unit + integration + contract + E2E + AI evaluation',
      '6. CI/CD pipeline — fail-fast CI + immutable artifacts + canary/blue-green + rollback',
      '7. Security — STRIDE + OWASP + secrets + encryption + container hardening',
      '8. Observability — structured logs + p95/p99 + tracing + dashboards + alerts',
      '9. Deployment — health probes + smoke tests + canary monitoring + rollback evidence',
      '10. AI / RAG — model registry + prompt registry + eval metrics + guardrails + cost',
      '11–17. Governance, documentation, FinOps, DevEx, tech evolution, debt, incident response',
    ],
    architectureRelevance: {
      backend: 'Covers contract-first APIs, idempotency, migrations, rollout, golden signals, and operational readiness.',
      rag: 'Adds evaluation sets, hallucination controls, prompt/model versioning, retrieval quality gates, and token-cost budgets.',
      ai: 'AI sections are non-optional once prompts or models ship: eval thresholds, guardrails, output validation, and cost telemetry become release gates.',
      microservices: 'Tracing, DB-per-service, contract tests, retries, breakers, rollback, and observability are the operational spine.',
    },
    problem: 'Tech leads often own delivery but lack one unified release standard. The result is partial readiness: code is merged, but tracing is weak, rollback is untested, or AI eval never became a gate.',
    whyThisApproach: 'A single checklist keeps design, delivery, and operations aligned. It gives one release language for engineers, architects, SRE, security, auditors, and interviewers.',
    whenToUse: [
      'Before production releases',
      'Architecture review and readiness review',
      'Compliance and SOC2/ISO evidence collection',
      'Interview answers for tech lead / staff roles',
      'Program-level health checks across multiple services',
    ],
    whenNotToUse: [
      'Throwaway spikes and notebooks',
      'One-off internal scripts with no operational footprint',
      'Features that will never be deployed to users',
    ],
    input: 'Architecture docs, ADRs, contracts, pipeline outputs, security scans, dashboards, runbooks, eval results, and deployment plans.',
    process: [
      'Review architecture and trust boundaries',
      'Validate tracing and contracts across services',
      'Check coding, testing, and CI/CD evidence',
      'Verify security, observability, deployment, and rollback',
      'Review governance, documentation, FinOps, DevEx, debt, and incident readiness',
      'Run AI-specific gates where applicable',
      'Apply hard-stop rule before release',
    ],
    output: 'A release decision with explicit evidence: go, block, or a list of missing controls to implement before ship.',
    implementationSteps: [
      { step: 'Lock architecture evidence', logic: 'C4 diagrams, ADRs, trust zones, backward-compatibility, tenant isolation, and API contracts are current.' },
      { step: 'Enforce request traceability', logic: 'correlation_id, trace_id, baggage, logs, and traces link one request end to end.' },
      { step: 'Gate code quality', logic: 'lint, typing, readable naming, fail-fast validation, query review, and idempotency are enforced in CI and review.' },
      { step: 'Gate testing', logic: 'unit, integration, contract, smoke, and AI evaluation tests exist and are green.' },
      { step: 'Gate release safety', logic: 'immutable artifact, canary/blue-green, feature flags, health probes, smoke tests, rollback automation.' },
      { step: 'Gate operations', logic: 'dashboards, alerts, golden signals, synthetic checks, on-call ownership, incident plan, runbooks.' },
      { step: 'Gate AI controls', logic: 'model and prompt versions tracked; guardrails, PII handling, output validation, and token-cost monitoring are live.' },
    ],
    codeExample: {
      language: 'markdown',
      code: `# Tech Lead GO / NO-GO
- [ ] C4 + ADR + trust boundaries updated
- [ ] Correlation ID, trace ID, baggage visible end to end
- [ ] Contract tests and AI eval tests green
- [ ] Canary/rollback path tested
- [ ] OWASP + secrets + image scans green
- [ ] Dashboards and alerts active
- [ ] Model/prompt/version + token-cost telemetry active

## Hard stop
- [ ] no security issue
- [ ] rollback exists and is tested
- [ ] monitoring exists
- [ ] no breaking change without migration path
- [ ] tracing is live
- [ ] AI is evaluated before release`,
    },
    realUseCase: 'A multi-service AI release looked ready at feature level, but the checklist blocked it because trace correlation stopped at the gateway, rollback had never been rehearsed, and the RAG answer-quality benchmark had no release threshold. Fixing those three gaps took two days and prevented a high-risk launch with no diagnostic path.',
    prosCons: {
      pros: [
        'One lifecycle standard across design, delivery, and operations',
        'Strong audit and interview artifact',
        'Makes release blockers explicit instead of political',
        'Brings AI controls into normal engineering governance',
      ],
      cons: [
        'Feels heavy if applied to tiny work',
        'Requires disciplined evidence linking, not just boxes checked',
        'Can turn into ceremony if owners do not enforce go/no-go honestly',
      ],
    },
    limitations: [
      'A checklist does not replace engineering judgment',
      'The checklist is only as strong as the evidence attached to each row',
      'Small teams may need a lighter-weight version for low-risk internal tools',
    ],
    comparison: {
      left: 'Ad hoc release confidence',
      right: 'Tech lead master checklist',
      rows: [
        { aspect: 'Release decision', left: 'Gut feel', right: 'Evidence-backed gate' },
        { aspect: 'Cross-team alignment', left: 'Slack threads and memory', right: 'Shared lifecycle standard' },
        { aspect: 'Audit readiness', left: 'Painful reconstruction', right: 'Prepared evidence trail' },
        { aspect: 'AI safety', left: 'Optional extra', right: 'Explicit release control' },
      ],
    },
    challenges: [
      'Keeping the checklist honest instead of aspirational',
      'Making evidence easy to find',
      'Preventing teams from treating AI controls as optional',
      'Balancing speed vs. rigor for low-risk changes',
    ],
    edgeCases: [
      { case: 'A tiny hotfix bypasses parts of the checklist', solution: 'Use a reduced emergency path, but never waive security, tracing, rollback, or monitoring.' },
      { case: 'A service is non-AI but depends on AI outputs', solution: 'It still inherits AI evaluation and guardrail readiness as an upstream dependency.' },
      { case: 'A legacy service cannot meet full standards yet', solution: 'Document exceptions with ADR + debt register + migration plan rather than pretending green.' },
    ],
    solutions: [
      { problem: 'Checklist becomes ceremony', solution: 'Attach concrete evidence URL or drill to every row; unticked rows block release.' },
      { problem: 'Ops controls drift after launch', solution: 'Review the same checklist in post-release and quarterly readiness reviews.' },
      { problem: 'AI quality is subjective', solution: 'Define eval datasets and explicit thresholds before launch.' },
    ],
    bestPractices: {
      do: [
        'Map each checklist row to a source of truth',
        'Use hard-stop rules with no social override',
        'Keep AI controls in the same checklist as backend controls',
        'Review checklist in design, release, and audit cycles',
      ],
      avoid: [
        'Green-box theater with no evidence',
        'Treating tracing or rollback as post-launch work',
        'Shipping AI without eval thresholds',
      ],
      optimize: [
        'Link deep dives, runbooks, dashboards, and ADRs directly',
        'Automate as many rows as possible in CI/CD',
        'Use the same checklist in interviews and audits to keep it sharp',
      ],
    },
    antiPatterns: [
      'Release because “the code looks done”',
      'No owner for dashboards or alerts',
      'Prompt and model changes with no version trail',
      'Contract tests and rollback drills existing only on paper',
    ],
    testing: [
      'Checklist review before release',
      'Unit/integration/contract/E2E suites',
      'AI evaluation set and regression thresholds',
      'Rollback and canary drills',
    ],
    testTypes: [
      'Unit tests',
      'Integration tests',
      'Contract tests',
      'Smoke and E2E tests',
      'Security scans',
      'AI evaluation tests',
    ],
    testScenarios: [
      { scenario: 'Breaking schema change proposed', expected: 'Blocked until compatibility and contract strategy are explicit.' },
      { scenario: 'Model or prompt changes without eval baseline', expected: 'Release blocked by AI hard stop.' },
      { scenario: 'Canary p95 breaches SLA', expected: 'Automatic rollback or manual rollback according to policy.' },
    ],
    testData: [
      { type: 'Golden AI eval set', example: 'Representative retrieval and answer dataset with accuracy and hallucination thresholds.' },
      { type: 'Release checklist artifact', example: 'PR comment or release doc linking each row to evidence.' },
    ],
    debuggingChecklist: [
      'If release debate is subjective, ask which checklist row has no evidence',
      'If a prod issue is hard to trace, verify correlation_id, trace_id, and baggage first',
      'If rollback is unsafe, check expand/contract migration plan and artifact immutability',
      'If AI quality is disputed, inspect eval set, threshold, and model/prompt version trail',
    ],
    productionIssues: [
      { issue: 'Feature launched with no trace continuity across services', rootCause: 'Tracing was assumed, not checked as a release gate.' },
      { issue: 'Prompt update caused answer quality drop in prod', rootCause: 'Prompt versioning existed informally but no eval threshold blocked release.' },
      { issue: 'Rollback failed during canary', rootCause: 'Rollback path was documented but never rehearsed.' },
    ],
    security: [
      'Threat modeling via STRIDE for new or changed boundaries',
      'Secrets only in Vault/KMS, never in image or repo',
      'OWASP controls and dependency scanning are release gates',
      'RBAC/ABAC and tenant isolation reviewed alongside API changes',
    ],
    performance: [
      'Track p95/p99, throughput, saturation, and queue depth before and during canary',
      'Review query plans and N+1 risks before release on large-path changes',
      'For AI, monitor latency by retrieval, prompt assembly, and generation separately',
    ],
    costConsiderations: [
      'Track cost per request and per feature, not just total cloud bill',
      'AI changes need token and GPU cost budgets before rollout',
      'Autoscaling and idle resource cleanup belong to normal release readiness',
    ],
    scaling: [
      'Checklist scales across services because it separates lifecycle sections by owner',
      'Use templates and central evidence links to keep larger organizations consistent',
      'Enterprise version adds ARB, tech radar, compliance mapping, and portal integration',
    ],
    observability: [
      'Structured logs include correlation and tenant context',
      'Golden signals and AI signals are dashboarded with owners',
      'Synthetic monitoring and on-call alert paths are part of readiness',
    ],
    metrics: [
      { name: 'release_gate_pass_rate', example: 'Percent of releases cleared without manual exception.' },
      { name: 'rollback_drill_recency_days', example: 'Days since last successful rollback rehearsal.' },
      { name: 'ai_eval_gate_pass_rate', example: 'Share of AI changes that pass benchmark threshold on first attempt.' },
    ],
    failureModes: [
      { mode: 'Checklist exists but no one enforces it', detect: 'Rows marked green with no linked evidence', recover: 'Require evidence URLs and named signers.' },
      { mode: 'Operations controls decay after launch', detect: 'Alerts silent or dashboards stale', recover: 'Run quarterly readiness review on the same checklist.' },
      { mode: 'AI ships without objective quality bar', detect: 'No eval set or undefined threshold', recover: 'Block release until baseline and gate exist.' },
    ],
    tradeoffs: [
      { decision: 'Single master checklist', tradeoff: 'Consistency is high, but small releases may need a lighter path.' },
      { decision: 'Hard-stop rule', tradeoff: 'Protects reliability, but can slow a release when teams are under pressure.' },
      { decision: 'AI in the same gate as backend', tradeoff: 'Better governance, but more upfront discipline is required.' },
    ],
    decisionMatrix: [
      { option: 'Use full checklist', whenToUse: 'Production releases, audits, multi-service changes, AI launches.' },
      { option: 'Use slimmed checklist', whenToUse: 'Low-risk internal changes with no user impact, but still keep hard-stop controls.' },
      { option: 'Do not use checklist', whenToUse: 'Throwaway experiments only.' },
    ],
    starStory: {
      situation: 'A platform team was moving fast, but every release review devolved into opinion and post-launch surprises.',
      task: 'Create a repeatable tech lead standard that covered architecture, delivery, operations, and AI controls.',
      action: 'Introduced one lifecycle checklist with hard stops, deep-dive evidence links, and explicit owners across architecture, CI/CD, security, observability, deployment, and AI.',
      result: 'Release reviews became faster, audit evidence was straightforward, and high-risk launches were blocked before production rather than debugged after.',
    },
    interviewTraps: [
      'Only talking about coding standards and ignoring rollout, tracing, or governance',
      'Treating AI controls as separate from normal engineering readiness',
      'Saying “we have monitoring” without naming dashboards, alerts, and owners',
      'Using a checklist with no hard-stop rule',
    ],
    finalScript: 'I use a full lifecycle tech lead checklist covering C4 architecture, ADRs, tracing, service boundaries, coding quality, test strategy, secure SDLC, CI/CD, observability, deployment, governance, FinOps, DevEx, technical evolution, debt, incident response, and AI controls. My go/no-go rule is explicit: if there is a security issue, no rollback, no monitoring, a breaking change, no tracing, or untested AI, we do not release. That keeps releases scalable, secure, observable, and economically controlled instead of relying on gut feel.',
    alternatives: [
      { name: 'Ad hoc release review', tradeoff: 'Fast at first, but error-prone and weak for audits.' },
      { name: 'Service-specific checklists only', tradeoff: 'Useful locally, but misses cross-cutting release controls.' },
      { name: 'Master tech lead checklist', tradeoff: 'Most rigorous and reusable; needs disciplined upkeep.' },
    ],
    monitoring: [
      'Checklist completion status per release',
      'Open exception count per section',
      'Hard-stop violations by team or service',
    ],
    maturity: {
      mvp: 'Basic release gate covering architecture, tests, security, rollback, and monitoring.',
      production: '17-section checklist with evidence links and explicit signers.',
      enterprise: 'Checklist tied to ARB, Tech Radar, audit controls, developer portal, and automated evidence collection.',
    },
    projectFit: [
      '/admin/checklist/deep',
      '/admin/c4-model/deep',
      '/admin/cicd/deep',
      '/admin/tracing/deep',
      '/admin/security/deep',
      '/admin/post-release/deep',
      '/admin/rollout/deep',
      '/admin/rag/deep',
      '/admin/llmops/deep',
    ],
    interviewLine: 'A tech lead checklist is useful only if it gates release. Mine does: architecture, tracing, contracts, CI/CD, security, observability, rollback, and AI evaluation are all explicit go/no-go controls.',
  },
];

export default function TechleadDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Tech Lead — Deep Dive</h1>
        <p className="design-areas-sub">
          The tech lead lens: cross-team API contract design, idempotency, deprecation policy,
          and the full release/readiness checklist a lead uses to ship safely. Emphasis on §10
          LLD, §17 Solutions, §21 Best practices, §24 Production issues, and explicit GO / NO-GO rules.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/checklist/deep', label: 'Production-readiness checklist', why: 'tech lead signs the checklist; 17 sections + 6 hard stops are pair-signed (lead + on-call + compliance)' },
          { href: '/admin/cicd/deep', label: 'CI/CD + TDD framework', why: 'tech lead owns CI gate config + TDD discipline; build-once + AI eval gates' },
          { href: '/admin/tracing/deep', label: 'Baggage + trace→draft→audit', why: 'tech lead enforces baggage_set in auth middleware so cross-service forensics works' },
          { href: '/admin/post-release/deep', label: 'PDV + rollback decision matrix', why: 'tech lead pre-decides rollback matrix; debate-free at 3 AM' },
          { href: '/admin/principles/deep', label: 'SOLID + 17-factor', why: 'tech lead enforces principles in code review; AI-generated code follows the same rules' },
        ]}
      />
    </div>
  );
}
