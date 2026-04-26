'use client';

/**
 * Tech lead lens: cross-team API contract design, code-review gates,
 * and how to ship a feature across multiple services without
 * coupling deploys. Emphasis on §10 LLD, §17 Solutions, §21 Best
 * practices, §24 Production issues, §26 Debugging checklist.
 */

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
    </div>
  );
}
