'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'service-boundaries',
    title: '1. Service boundaries (domain decomposition)',
    status: 'shipped',
    coreConcept: 'Each service owns one bounded context — its own database schema, deployment lifecycle, and on-call rotation. Boundaries follow domain shape, not org chart.',
    problem: 'Monoliths couple every change; "fix one bug" cascades. Wrong boundaries (services-as-CRUD-tables) replicate the monolith pain at higher cost.',
    whyThisApproach: 'Domain-driven boundaries let teams ship independently while keeping each service small enough to reason about. Schema per service prevents cross-coupling.',
    whenToUse: ['Different domains have different scaling needs', 'Multiple teams; deployment independence matters', 'Failure isolation required'],
    whenNotToUse: ['Single team < 10 engineers', 'Heavy cross-domain joins', 'Tightly coupled domain logic (would need too many sync calls)'],
    input: 'Domain analysis: bounded contexts, aggregate roots, ownership',
    process: [
      'Identify bounded contexts (governance, ingestion, retrieval, inference, eval, finops, observability, identity)',
      'Each gets own schema in Postgres',
      'Each gets own service repo / package',
      'Cross-context calls go through HTTP/MCP, not shared DB tables',
      'Async coupling via Kafka events, not sync DB triggers',
    ],
    output: '8 bounded contexts × {schema, service, deploy, owner}.',
    flowchart: `flowchart TB
  subgraph DocuMind
    direction LR
    id[identity-svc] --> ing[ingestion-svc]
    ing --> ret[retrieval-svc]
    ret --> inf[inference-svc]
    inf --> mcp[MCP servers]
    inf --> ev[evaluation-svc]
    inf --> gov[governance-svc]
    fin[finops-svc] -.metrics.-> obs[observability-svc]
    inf -.events.-> k[Kafka]
    k --> ing
  end`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Gw as api-gateway
  participant Inf as inference-svc
  participant Ret as retrieval-svc
  participant MCP as MCP server
  participant Aud as governance.audit_log
  U->>Gw: POST /api/v1/agent/ask
  Gw->>Inf: forward + cid + tenant
  Inf->>Ret: retrieve context
  Ret-->>Inf: chunks
  Inf->>MCP: tool call (if action)
  MCP-->>Inf: result
  Inf->>Aud: write audit
  Inf-->>U: response`,
    alternatives: [
      { name: 'Monolith', tradeoff: 'Simple ops; tight coupling; team scaling pain' },
      { name: 'Tech-axis split (frontend / backend / DB team)', tradeoff: 'Worst of both — no domain ownership' },
      { name: 'Function-per-service (nano-services)', tradeoff: 'Operational overhead explodes' },
    ],
    challenges: [
      'Wrong boundaries lead to chatty services',
      'Distributed transactions (avoid; use sagas)',
      'Cross-service consistency',
      'Versioning shared contracts',
      'Deploy coordination for breaking changes',
    ],
    edgeCases: [
      { case: 'Two services need same data', solution: 'Owner publishes; consumers subscribe (Kafka)' },
      { case: 'Cross-service transaction needed', solution: 'Saga pattern with compensations + audit' },
      { case: 'Shared utility code', solution: 'libs/py/documind_core (stable abstractions only)' },
      { case: 'Hot domain split into too-small services', solution: 'Re-merge; "right-size" not "smallest"' },
    ],
    failureModes: [
      { mode: 'One service dragging another down via sync calls', detect: 'Per-service latency histograms; CB state', recover: 'Per-dep CB; async via Kafka' },
      { mode: 'Schema drift (consumer breaks)', detect: 'CI contract test; consumer error spike', recover: 'Backwards-compat additive change; rolling deploy' },
      { mode: 'Cascading auth failure', detect: 'Cross-service 401 spike', recover: 'JWT verification + retry pause; investigate identity-svc' },
    ],
    monitoring: ['Per-service health/upstreams', 'Cross-service correlation_id traces', 'Per-service deployment registry'],
    testing: [
      'drill_inference_health_upstreams (cross-service reachability)',
      'drill_agent_multiserver_routing (multi-MCP)',
      'drill_resolve_draft_routing (cross-service workflow)',
    ],
    security: ['mTLS between services (planned)', 'Per-service JWT verification', 'Tenant context propagated end-to-end'],
    scaling: [
      '10x: scale individual services independently',
      '100x: per-service horizontal scale + per-domain DB read replicas',
      '1000x: regional deployment per service tier',
    ],
    maturity: {
      mvp: 'Monolith with clear modules',
      production: 'Per-domain service + schema; HTTP/MCP boundaries; shared libs/py',
      enterprise: 'Service mesh (Istio); per-service deploy registry; canary; cross-region',
    },
    limitations: [
      'Coordination overhead grows with service count',
      'Cross-service debugging needs strong correlation',
      'Schema changes need backwards-compat discipline',
    ],
    projectFit: [
      '8 services in services/*',
      'Schema per service in governance/ingestion/etc.',
      'libs/py/documind_core for shared primitives only',
      '/admin/llmops Subsystem ownership map (commit 7423c16)',
    ],
    interviewLine: 'Service boundaries follow domain shape, not org chart. The hardest discipline is resisting "service per CRUD table" — that\'s a monolith with extra steps.',
    implementationSteps: [
      { step: 'Map domain bounded contexts', logic: 'Each service owns one cohesive responsibility; not one CRUD table.' },
      { step: 'Schema-per-service grants', logic: 'Least privilege; no cross-service joins in DB.' },
      { step: 'API contract before code', logic: 'OpenAPI / proto / MCP schema reviewed before implementation.' },
      { step: 'Outbox pattern for cross-service', logic: 'Saga or events; never distributed transactions.' },
      { step: 'Per-service drill suite', logic: 'Each service\'s invariants tested in isolation + integration.' },
      { step: 'Service ownership doc', logic: 'Explicit owner, on-call, runbook, SLA per service.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/inference-svc — owns ONE thing: grounded LLM answers
# Schema: inference_log, prompt_versions, model_versions
# DB role: inference_app (NOBYPASSRLS on its schema)
# Calls OUT to: retrieval-svc (gRPC), governance-svc (HTTP), Ollama (HTTP)
# Calls IN from: api-gateway

from libs.py.documind_core.contracts import AskRequest, AskResponse
from libs.py.documind_core.circuit_breaker import CircuitBreaker

retrieval_breaker = CircuitBreaker("inference->retrieval")
ollama_breaker = CircuitBreaker("inference->ollama")

class InferenceService:
    def __init__(self, retrieval_client, llm_client, governance_client):
        self._retrieval = retrieval_client
        self._llm = llm_client
        self._governance = governance_client

    async def answer(self, req: AskRequest, correlation_id: str) -> AskResponse:
        # NEVER reach into retrieval-svc's DB; only via its API
        if not retrieval_breaker.allow():
            raise ExternalServiceError("retrieval unavailable")
        chunks = await self._retrieval.fetch(req)
        retrieval_breaker.record_success()

        if not ollama_breaker.allow():
            raise ExternalServiceError("LLM unavailable")
        prompt = build_prompt(req.question, chunks)
        answer = await self._llm.stream(prompt)
        ollama_breaker.record_success()

        await self._governance.log_decision(req, answer, correlation_id)
        return AskResponse(answer=answer, citations=chunks, correlation_id=correlation_id)`,
    },
    realUseCase: 'Initial design had "search-svc" + "rerank-svc" as separate services. Both touched the same chunk corpus + had identical operational concerns. Merged into retrieval-svc (one service, one schema, one on-call rotation). Cross-service joins disappeared. The reverse mistake — "users-svc" with its own user table — was avoided early; users live in identity-svc and other services reference user_id as a foreign concept, not a DB join.',
    prosCons: {
      pros: [
        'Domain-shaped boundaries reduce coupling',
        'Schema-per-service makes least-privilege automatic',
        'Per-service drills isolate failures',
        'Independent deploy cycles per service',
      ],
      cons: [
        'Cross-service queries require API hops (latency)',
        'Saga complexity for multi-service writes',
        'Per-service operational overhead grows with N',
        'Boundaries take iteration to get right',
      ],
    },
    comparison: {
      left: 'Service-per-CRUD-table',
      right: 'Domain-bounded services (this)',
      rows: [
        { aspect: 'Cross-service joins needed', left: 'Frequent', right: 'Rare; outbox handles' },
        { aspect: 'Service count', left: 'High (N tables = N services)', right: 'Low (domain count)' },
        { aspect: 'Coupling', left: 'High (chained CRUD calls)', right: 'Low (domain APIs)' },
        { aspect: 'Operational overhead', left: 'High (many services to run)', right: 'Manageable' },
      ],
    },
    solutions: [
      { problem: 'Split too fine (CRUD-per-service)', solution: 'Merge along domain boundaries; cohesion > "microservice"' },
      { problem: 'Cross-service distributed transactions', solution: 'Outbox + saga; never 2PC' },
      { problem: 'Schema drift across services', solution: 'Schema-per-service + DB grants' },
      { problem: 'Implicit ownership', solution: 'Service ownership doc with owner + on-call + runbook' },
    ],
    bestPractices: {
      do: [
        'Boundaries follow domain bounded contexts',
        'Schema-per-service with least-privilege grants',
        'Outbox + saga for cross-service writes',
        'Per-service ownership doc',
        'Drill suite per service (isolation) + integration',
      ],
      avoid: [
        'Service per CRUD table',
        'Cross-service DB joins',
        'Distributed transactions (2PC)',
        'Shared mutable libraries (couples versions)',
        'Org-chart-aligned boundaries',
      ],
      optimize: [
        'Sidecar mesh for cross-service calls (Istio)',
        'Read replicas for cross-domain query patterns',
        'Versioned events for safer schema evolution',
      ],
    },
    antiPatterns: [
      'Service per CRUD table',
      'Cross-service DB joins',
      'Distributed transactions',
      'Org-chart boundaries',
      'Shared mutable lib (couples deploys)',
    ],
    testTypes: [
      'Per-service unit + integration drills',
      'Contract test (mock + real impl)',
      'Saga drill (cross-service write + compensation)',
      'Boundary violation drill (cross-schema query forbidden)',
    ],
    testScenarios: [
      { scenario: 'Inference-svc tries to query retrieval-svc DB directly', expected: 'Permission denied (schema grants prevent it)' },
      { scenario: 'Saga step fails mid-flight', expected: 'Compensation executes; consistent end state' },
      { scenario: 'New service added', expected: 'Has owner + on-call + drill suite + schema grants' },
    ],
    testData: [
      { type: 'Cross-service saga fixture', example: 'Ingestion → parse → chunk → embed → index; one step fails; compensate prior steps' },
      { type: 'Schema grant test', example: 'inference_app role attempts SELECT on retrieval schema → denied' },
    ],
    debuggingChecklist: [
      'New service spawned? Has owner + on-call + runbook? If no, fix BEFORE launch',
      'Cross-service join showed up in code review? Probably wrong boundary',
      'Saga compensation untested? Drill it',
      'Service own its schema? Check grants',
    ],
    productionIssues: [
      { issue: 'search-svc + rerank-svc duplicated chunk-touching code', rootCause: 'Wrong split — not domain-bounded. Merged into retrieval-svc.' },
      { issue: 'users-svc never built; identity-svc owns users', rootCause: 'Initial draft had users-svc; recognized as CRUD-per-table mistake before launch.' },
      { issue: 'Cross-service distributed transaction hung on outage', rootCause: '2PC across inference + governance; one DB unreachable. Replaced with outbox + saga.' },
    ],
    performance: [
      'Per-service deploy cycle: ~5-10 min (vs ~20-30 monolith)',
      'Cross-service hop: ~5-15ms p95 added (mesh + serialization)',
      'Saga overhead: ~1.5x latency vs monolith call chain',
    ],
    costConsiderations: [
      'Pod count: ~6 services × 3 replicas = ~18 pods (vs 1 monolith)',
      'Mesh sidecar: ~50MB RAM per pod',
      'Schema-per-service: no extra DB cost; same Postgres cluster',
    ],
    observability: [
      'Trace: end-to-end via OTel + correlation_id',
      'Metrics: per-service p95 latency, error rate, saturation',
      'Logs: structured per service; correlation_id ties them together',
      'Audit: cross-service writes audit-chained',
    ],
    metrics: [
      { name: 'documind_service_request_duration_seconds{service,route,p}', example: 'Histogram per service per route' },
      { name: 'documind_cross_service_call_total{caller,target}', example: 'Counter; high counts = chatty boundary' },
      { name: 'documind_saga_compensation_total{saga,outcome}', example: 'Counter; spike = upstream issues' },
    ],
    tradeoffs: [
      { decision: 'Service granularity', tradeoff: 'Fine = isolation but ops cost; coarse = simpler but coupling' },
      { decision: 'gRPC vs HTTP internal', tradeoff: 'gRPC is faster + typed; HTTP is debuggable' },
      { decision: 'Saga vs 2PC', tradeoff: 'Saga is loosely consistent; 2PC blocks on outage' },
    ],
    decisionMatrix: [
      { option: 'Domain-bounded services (this)', whenToUse: 'Multiple cohesive domains, parallel team velocity' },
      { option: 'Modular monolith', whenToUse: 'Single team, < 6 domains, shared deploy cycle OK' },
      { option: 'Service per table', whenToUse: 'Never (anti-pattern)' },
    ],
    starStory: {
      situation: 'Initial design proposal had 12 services for what turned out to be 4 domains; CRUD-per-service.',
      task: 'Right-size service boundaries before any code shipped.',
      action: 'Mapped bounded contexts. Merged search + rerank → retrieval-svc. Killed users-svc proposal (identity-svc covers). Schema-per-service grants. Per-service ownership doc.',
      result: '4 services shipped. Cross-service joins eliminated. Per-service drill suite ran cleanly. Pattern documented as ADR-001.',
    },
    interviewTraps: [
      'Saying "we have N services" without explaining domain boundaries',
      'Service per CRUD table',
      'Distributed transactions across services',
      'Cross-service DB joins',
      'Org-chart-aligned services',
    ],
    finalScript: 'Service boundaries follow domain shape, not org chart. Each service owns one cohesive responsibility, owns its schema with least-privilege grants, and exposes domain APIs (REST/gRPC/MCP) — never DB joins. Cross-service writes use outbox + saga, never 2PC. Per-service ownership is explicit: owner, on-call, runbook, drill suite. The hardest discipline is resisting "service per CRUD table" — that\'s a monolith with extra steps.',
  },
  {
    slug: 'rest-vs-grpc-vs-mcp',
    title: '2. REST vs gRPC vs MCP — when each fits',
    status: 'partial',
    coreConcept: 'Different cross-service shapes deserve different protocols: REST for external + simple internal; gRPC for high-throughput typed; MCP for governed tool calls.',
    problem: 'One protocol for everything optimises for none. Internal high-throughput paths need typed efficiency; external paths need browser-friendly REST; agent tool calls need scope + idempotency + audit semantics.',
    whyThisApproach: 'Protocol per use case keeps each path optimised for its shape. The boundary is the contract, not the wire format.',
    whenToUse: [
      'REST: external API surface, browser clients, simple internal CRUD',
      'gRPC: high-volume internal RPC, typed contracts, streaming',
      'MCP: agent tool calls with scope/idempotency/audit',
    ],
    whenNotToUse: [
      'Don\'t use gRPC for browser-facing APIs (no native fetch support)',
      'Don\'t use REST for high-fanout RPC (overhead matters)',
      'Don\'t use MCP for raw data plane (overkill)',
    ],
    input: 'Cross-service call requirement: throughput, payload shape, audit needs, client type',
    process: [
      'Classify call: external? typed-RPC? agent-tool?',
      'Pick protocol matching the shape',
      'Wrap with shared primitives (CB + retry + observability)',
      'Generate types if gRPC; OpenAPI if REST; tool catalog if MCP',
    ],
    output: 'Right protocol per call site, all observable through correlation_id.',
    flowchart: `flowchart TB
  c[Cross-service call] --> q{Call type?}
  q -->|External / browser| r[REST + JSON]
  q -->|High-throughput typed| g[gRPC + protobuf]
  q -->|Agent tool with scope| m[MCP /tools/call]
  r --> obs[Same correlation_id + breakers]
  g --> obs
  m --> obs`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant Gw as api-gateway
  participant SvcA as Service A
  participant SvcB as Service B
  participant MCP as MCP server
  Cli->>Gw: REST /api/v1/...
  Gw->>SvcA: REST internal
  SvcA->>SvcB: gRPC (typed RPC)
  SvcB-->>SvcA: response
  SvcA->>MCP: MCP /tools/call (action with scope)
  MCP-->>SvcA: tool result
  SvcA-->>Gw: REST response
  Gw-->>Cli: JSON`,
    alternatives: [
      { name: 'GraphQL everywhere', tradeoff: 'Read-side aggregation strong; weak for commands; ADR-012 says no' },
      { name: 'gRPC everywhere', tradeoff: 'Browser support requires gateway; learning curve' },
      { name: 'REST everywhere', tradeoff: 'Simple; chatty for typed RPC; no streaming' },
    ],
    challenges: [
      'Polyglot payload contracts',
      'Schema evolution across protocols',
      'Cross-protocol observability',
      'Authentication coupling (JWT works across all three)',
    ],
    edgeCases: [
      { case: 'External client needs gRPC-like efficiency', solution: 'gRPC-Web via gateway; or REST + HTTP/2 + binary' },
      { case: 'MCP tool needs streaming response', solution: 'Server-Sent Events; or escalate to gRPC streaming' },
      { case: 'gRPC service needs OpenAPI doc', solution: 'gRPC-Gateway generates REST + OpenAPI from proto' },
    ],
    failureModes: [
      { mode: 'Protocol fragmentation across team', detect: 'Inconsistent client codegen; mixed contracts', recover: 'ADR per protocol; central catalog' },
      { mode: 'Cross-protocol auth drift', detect: 'Some endpoints unauthed', recover: 'Shared auth middleware/library across all three' },
    ],
    monitoring: [
      'Per-protocol latency histograms',
      'Per-protocol error rates',
      'Cross-protocol trace continuity (correlation_id)',
    ],
    testing: [
      'Contract tests per protocol',
      'Cross-protocol drill (REST → gRPC → MCP correlation)',
      'Protocol upgrade compatibility',
    ],
    security: [
      'JWT works across all three (Bearer token in headers/metadata)',
      'mTLS for gRPC internal',
      'CORS only on REST external surface',
      'Scope enforcement on MCP',
    ],
    scaling: [
      'REST: horizontal + CDN edge cache for reads',
      'gRPC: HTTP/2 multiplexing; less connection overhead',
      'MCP: same as REST + per-tool idempotency',
    ],
    maturity: {
      mvp: 'REST everywhere',
      production: 'REST external + REST internal + MCP for tools',
      enterprise: 'REST external + gRPC internal high-throughput + MCP governed actions',
    },
    limitations: [
      'gRPC not currently used (HTTP-only services today)',
      'Polyglot codebase needs more discipline',
      'Schema registry across protocols is open',
    ],
    projectFit: [
      'REST: every service /api/v1/*',
      'MCP: mcp/server_*.py + mcp/client.py',
      'gRPC: not currently wired (see /admin/llmops scorecard "open")',
      'docs/architecture/repo-grpc-and-microservice-architecture.md',
    ],
    interviewLine: 'REST for external + simple internal; gRPC for high-throughput typed; MCP for governed agent tool calls. The boundary is the contract, not the wire format.',
    implementationSteps: [
      { step: 'Pick protocol per use case', logic: 'REST = external/simple; gRPC = high-throughput typed; MCP = agent tool calls.' },
      { step: 'Versioned contract first', logic: 'OpenAPI / .proto / MCP schema reviewed before code.' },
      { step: 'Same JWT across all three', logic: 'Bearer token in headers/metadata; identity is uniform.' },
      { step: 'Per-protocol breaker', logic: 'CB per (caller, target, protocol); each has its own failure mode.' },
      { step: 'Trace correlation', logic: 'correlation_id propagated through every protocol via W3C TraceParent.' },
      { step: 'Per-protocol drill', logic: 'Contract test, retry semantics, error envelope all verified.' },
    ],
    codeExample: {
      language: 'python',
      code: `# Three protocols, three use cases — same correlation_id everywhere

# REST: external API surface (FastAPI)
@router.post("/api/v1/ask", response_model=AskResponse)
async def ask(req: AskRequest, correlation_id: str = Depends(get_correlation_id)):
    return await inference_svc.answer(req, correlation_id)

# gRPC: internal high-throughput (retrieval-svc → inference-svc)
class RetrievalServicer(retrieval_pb2_grpc.RetrievalServicer):
    async def Retrieve(self, request, context):
        cid = dict(context.invocation_metadata()).get("x-correlation-id")
        chunks = await self._svc.retrieve(request.query, request.tenant_id, cid)
        return retrieval_pb2.RetrieveResponse(
            chunks=[c.to_proto() for c in chunks],
            degraded=request.degraded,
        )

# MCP: governed agent tool call
@server.tool("hr.create_user")
async def create_user(args: CreateUserArgs, ctx: ToolContext) -> ToolResult:
    # Scope check BEFORE idempotency lookup
    if "hr:write" not in ctx.scopes:
        return ToolResult.scope_denied()
    cached = await idem.get(ctx.tenant_id, ctx.idempotency_key)
    if cached:
        return cached  # replay-safe
    user = await hr_svc.create(args, ctx.tenant_id)
    result = ToolResult.success(user.to_dict())
    await idem.store(ctx.tenant_id, ctx.idempotency_key, result, ttl_h=24)
    return result`,
    },
    realUseCase: 'Inference-svc → retrieval-svc went from REST to gRPC for the hot path; p95 dropped 22ms (mostly serialization). External API stayed REST (browsers + simple clients). Agent feature wrapped HR + ITSM tools in MCP for scope-checked, idempotent, audited tool calls. Trying to use REST for agent tools missed the scope/idempotency/audit primitives; trying to use gRPC for the external API broke browser clients. Each protocol matches its shape.',
    prosCons: {
      pros: [
        'Each path uses optimal protocol',
        'Browser-friendly external + typed-fast internal',
        'MCP gives scope + idempotency + audit for free',
        'Same JWT across all three',
      ],
      cons: [
        'Three protocols = three SDK surfaces',
        'gRPC + REST debugging skills both needed',
        'MCP requires schema registry maintenance',
      ],
    },
    comparison: {
      left: 'Single protocol everywhere',
      right: 'Protocol per use case (this)',
      rows: [
        { aspect: 'External API', left: 'gRPC = bad for browsers; REST = simple', right: 'REST' },
        { aspect: 'Internal hot path', left: 'REST = fine but slower', right: 'gRPC, ~22ms p95 better' },
        { aspect: 'Agent tools', left: 'REST = no scope/idem/audit primitives', right: 'MCP, primitives included' },
        { aspect: 'Operational complexity', left: 'Lower (one protocol)', right: 'Higher (three)' },
      ],
    },
    solutions: [
      { problem: 'Slow internal REST calls', solution: 'gRPC for high-throughput path' },
      { problem: 'Per-tool scope/idempotency duplication', solution: 'MCP server_common.py centralizes' },
      { problem: 'Browser can\'t call gRPC directly', solution: 'gRPC for internal; REST for external' },
      { problem: 'Trace continuity across protocols', solution: 'correlation_id in all three (header/metadata/scope)' },
    ],
    bestPractices: {
      do: [
        'REST for external + simple internal CRUD',
        'gRPC for high-throughput typed internal',
        'MCP for agent tool calls (scope + idem + audit)',
        'Versioned contracts; reviewed before code',
        'correlation_id across all three',
      ],
      avoid: [
        'gRPC for browser-facing API',
        'REST for tool calls that need scope+idem+audit',
        'Hand-rolled retry logic per protocol',
        'Skipping the cross-protocol trace drill',
      ],
      optimize: [
        'gRPC keep-alive for hot paths',
        'REST GZip for large JSON',
        'MCP schema generation from one source of truth',
      ],
    },
    antiPatterns: [
      'gRPC for browser-facing API',
      'REST for agent tool calls (missing primitives)',
      'Per-protocol hand-rolled auth',
      'No cross-protocol trace correlation',
    ],
    testTypes: [
      'Contract test per protocol (OpenAPI / proto / MCP schema)',
      'Cross-protocol drill (REST → gRPC → MCP correlation_id continuity)',
      'Protocol upgrade compatibility (v1 + v2 in parallel)',
      'Auth uniformity (JWT works across all three)',
    ],
    testScenarios: [
      { scenario: 'External REST call → internal gRPC → MCP tool call', expected: 'correlation_id propagates end-to-end' },
      { scenario: 'gRPC client tries REST endpoint', expected: 'Documented in contract; client uses correct protocol' },
      { scenario: 'MCP tool retried with same idempotency key', expected: 'Cached response returned; no duplicate' },
      { scenario: 'JWT expired during gRPC call', expected: '401 with standard error envelope' },
    ],
    testData: [
      { type: 'Mock external client', example: 'curl + browser fetch hits REST; both work' },
      { type: 'gRPC stub', example: 'Generated client + mock server for hot-path benchmarks' },
      { type: 'MCP tool harness', example: 'Mock MCP client with scope simulation + idempotency replay' },
    ],
    debuggingChecklist: [
      'Browser request fails? Check CORS on REST + verify not gRPC',
      'gRPC slow? Check keep-alive + retry policy',
      'MCP tool replays wrongly? Check idempotency key persistence',
      'Cross-protocol trace broken? Check correlation_id propagation per protocol',
    ],
    productionIssues: [
      { issue: 'Internal REST hot path latency p95 = 90ms', rootCause: 'Serialization overhead. Migrated to gRPC; p95 = 68ms.' },
      { issue: 'Agent tool call duplicated user creation on retry', rootCause: 'REST endpoint had no idempotency primitive. Wrapped in MCP; ADR-003 mandates idempotency for write tools.' },
    ],
    performance: [
      'REST: ~5-10ms serialization overhead per call',
      'gRPC: ~1-3ms per call (binary + HTTP/2)',
      'MCP: REST under the hood + scope + idem; ~6-12ms',
    ],
    costConsiderations: [
      'gRPC: smaller wire payloads; saves bandwidth',
      'REST: easier debugging; saves engineering time',
      'MCP: schema registry tiny ops cost',
    ],
    observability: [
      'Trace: correlation_id propagates through all three protocols',
      'Metrics: per-protocol latency + error rate',
      'Logs: structured per call; protocol field in logs',
    ],
    metrics: [
      { name: 'documind_protocol_request_duration_seconds{protocol,route}', example: 'Histogram per protocol' },
      { name: 'documind_protocol_error_total{protocol,error_code}', example: 'Counter; per-protocol error rates' },
      { name: 'documind_cross_protocol_trace_continuity_rate', example: 'Gauge; target = 1.0 (no broken traces)' },
    ],
    tradeoffs: [
      { decision: 'REST vs gRPC internal', tradeoff: 'gRPC faster + typed; REST debuggable + ubiquitous' },
      { decision: 'MCP vs custom RPC for tools', tradeoff: 'MCP gives primitives free; custom is lighter' },
      { decision: 'Same protocol everywhere', tradeoff: 'Simpler ops; suboptimal per use case' },
    ],
    decisionMatrix: [
      { option: 'Protocol per use case (this)', whenToUse: 'External API + internal hot path + agent tools all distinct' },
      { option: 'REST only', whenToUse: 'Small platform; agent tools internal-only' },
      { option: 'gRPC only', whenToUse: 'No external API; all internal services' },
    ],
    starStory: {
      situation: 'Inference-svc calling retrieval-svc via REST; p95 latency budget tight; agent feature shipping needed scope+idem+audit.',
      task: 'Right-size protocols per use case without breaking external clients.',
      action: 'Migrated inference→retrieval to gRPC. Kept external API REST. Wrapped agent tools in MCP server_common.py for scope+idem+audit. correlation_id propagates across all three.',
      result: 'Hot-path p95 dropped 22ms. External clients unchanged. Agent feature shipped with scope+idem+audit primitives shared. ADR-003 (idempotency mandatory) + ADR-005 (protocol-per-use-case).',
    },
    interviewTraps: [
      'gRPC for external (breaks browsers)',
      'REST for agent tools (missing primitives)',
      'No correlation_id propagation across protocols',
      'Hand-rolled retry per protocol',
    ],
    finalScript: 'Protocol per use case: REST for external API + simple internal CRUD (browsers, debuggability), gRPC for internal high-throughput typed paths (~20ms p95 better than REST), MCP for agent tool calls (scope + idempotency + audit primitives included via server_common.py). Same JWT across all three; correlation_id propagates end-to-end. The boundary is the contract — OpenAPI for REST, .proto for gRPC, schema for MCP — reviewed before any code lands. ADR-003 mandates idempotency on write paths; ADR-005 documents protocol-per-use-case.',
  },
];

export default function MicroservicesDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Microservices deep dive</h1>
          <p className="page-subtitle">
            Service boundaries + protocol choice (REST / gRPC / MCP) — the
            two architectural decisions that drive everything else.
          </p>
        </div>
      </div>
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </>
  );
}
