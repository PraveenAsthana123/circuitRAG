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
];

export default function TechleadDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Tech Lead — Deep Dive</h1>
        <p className="design-areas-sub">
          The tech lead lens: cross-team API contract design, idempotency, deprecation policy.
          Emphasis on §10 LLD, §17 Solutions, §21 Best practices, §24 Production issues. Use
          when leading multi-team features or reviewing PRs that touch service boundaries.
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
