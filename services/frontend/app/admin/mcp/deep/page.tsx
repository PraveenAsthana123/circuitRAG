'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'mcp-server',
    title: '1. MCP server (per-namespace tool host)',
    status: 'shipped',
    coreConcept: 'Each MCP server hosts a namespaced set of tools (hr.*, itsm.*, drill.*) behind a uniform /tools/list + /tools/call HTTP contract — scoped, idempotent, observable.',
    oneLiner: 'MCP server = one tool-call boundary; shared scope + idempotency + audit + OTel; adding a namespace is dispatch code, not a security review.',
    businessContext: 'Multi-tenant SaaS with executable AI features (action drafts, HR actions, ITSM tickets, drill runs) needs a uniform tool-call surface — without it every namespace reinvents auth, idempotency, audit, and observability, and one missed primitive is a leak or a duplicate-action.',
    fiveW: {
      what: 'A FastAPI server hosting a namespaced family of tools (hr.create_user, itsm.open_ticket, drill.run, ...) behind a uniform /tools/list + /tools/call HTTP contract. Built on shared mcp/server_common.py.',
      why: 'Every namespace gets identical scope enforcement (JWT + required_scopes), idempotency (Postgres-backed replay), audit (hash-chained), and observability (per-tool histograms + counters) for free.',
      where: 'mcp/server_hr.py, mcp/server_itsm.py, mcp/server_drills.py, mcp/server_finance.py. Each ships its own dispatch table; shared common handles the cross-cutting concerns.',
      when: 'Adding a domain-bounded tool family — HR actions, ITSM tickets, drill runs, finance ops. Default surface for any agent-callable action.',
      who: 'Platform team owns server_common.py + drills. Each domain team owns its namespace dispatch. Security reviews scope changes.',
    },
    interview30s: 'MCP server is one tool-call boundary with shared scope, idempotency, audit, and observability. Each namespace (HR, ITSM, drill, finance) inherits identical primitives via mcp/server_common.py. Three non-negotiable disciplines: scope check BEFORE idempotency lookup (so a leaked key can\'t bypass scope), Postgres-backed idempotency (durable across restarts; ADR-003), per-tool latency histograms with denial counters. The drill that gates this is drill_mcp_server_scope: 8 steps verify scope + idempotency interaction. Adding a new namespace is 50 lines of dispatch code, not a security review — that\'s the win.',
    coreBuildingBlocks: [
      'server_common.py — handle_tool_call wraps every dispatch',
      'enforce_scope — JWT validation + required_scopes intersection',
      'PostgresIdempotencyStore — durable across restart (governance.mcp_idempotency)',
      'OTel span attributes — actor, outcome, namespace, tool',
      'Per-tool counters — tool_calls_total{namespace,tool,outcome}',
      'Per-tool histogram — tool_call_duration_seconds',
      'Audit chain — hash-chained per tenant via fail_closed write',
      'Error envelope — standard {detail, error_code, correlation_id}',
    ],
    architectureRelevance: {
      backend: 'FastAPI lifespan loads JWT public key + idempotency store + audit writer. Each namespace is a separate process; Istio mesh enforces mTLS.',
      rag: 'Drill MCP namespace runs retrieval/eval drills as tool calls. Inference-svc invokes via MCPClient with tenant_id required.',
      ai: 'Agent-loop sequences tool calls via MCPClient. Each action drafted first; drill_mcp_server_scope ensures scope cannot be bypassed.',
      microservices: 'Per-namespace server = blast-radius isolation. HR namespace failure does not affect ITSM. Mesh routes by namespace.',
    },
    hld: `flowchart TB
  subgraph clients[Clients]
    AG[Agent / inference-svc]
    SDK[Direct API caller]
  end
  subgraph mesh[Istio mesh - mTLS strict]
    HR[("server_hr.py - hr.*")]
    ITSM[("server_itsm.py - itsm.*")]
    DRILL[("server_drills.py - drill.*")]
    FIN[("server_finance.py - finance.*")]
  end
  subgraph common[Shared layer]
    SC[("server_common.py - handle_tool_call")]
    SCOPE[("enforce_scope")]
    IDEM[("Postgres idempotency store")]
    OT[("OTel + Prometheus")]
    AUD[("Audit writer hash-chained")]
  end
  AG --> HR
  AG --> ITSM
  AG --> DRILL
  SDK --> FIN
  HR --> SC
  ITSM --> SC
  DRILL --> SC
  FIN --> SC
  SC --> SCOPE
  SC --> IDEM
  SC --> OT
  SC --> AUD`,
    networkFlow: `flowchart LR
  C[Client agent] --> AGW["api-gateway - JWT + tenant_id"]
  AGW -->|HTTPS X-Tenant-ID + Idempotency-Key| MCP["mcp/server_<ns>.py"]
  MCP -->|enforce_scope| KEY[(JWT public key store)]
  MCP -->|lookup_or_register| PG[(Postgres mcp_idempotency)]
  MCP -->|dispatch| H[Tool handler]
  H -->|fail_closed write| AUD[(audit_log)]
  MCP -->|metrics + spans| OBS[(Prometheus + Jaeger)]`,
    coreLayers: [
      { layer: 'Transport', responsibility: 'FastAPI + uvicorn. mTLS strict via Istio sidecar. POST /tools/list, POST /tools/call.' },
      { layer: 'Scope layer', responsibility: 'enforce_scope decorator. JWT validate via shared key store; intersect claims.roles vs tool.required_scopes.' },
      { layer: 'Idempotency layer', responsibility: 'PostgresIdempotencyStore. State machine: new / in_progress / done / conflict. Durable across restart.' },
      { layer: 'Dispatch layer', responsibility: 'Per-namespace dispatch table maps tool name → handler function. Type-validated args via Pydantic.' },
      { layer: 'Audit layer', responsibility: 'fail_closed write per call (ADR-004). Hash-chained per tenant. Includes actor + correlation_id.' },
      { layer: 'Observability layer', responsibility: 'Per-tool latency histogram + outcome counters. OTel span with attributes. /api/v1/health/tools surface.' },
      { layer: 'Error layer', responsibility: 'Typed error envelope: {detail, error_code, correlation_id}. 401 / 403 / 404 / 409 / 503.' },
    ],
    lld: `flowchart LR
  subgraph srv[server_common.py handle_tool_call]
    AUTH[enforce_scope]
    LOOK[lookup_or_register]
    DISP[dispatch handler]
    FIN[finalize idempotency]
    METR[record metrics]
    AUD[audit write]
  end
  subgraph pg[Postgres mcp_idempotency]
    KEY[idempotency_key + tenant_id - PK]
    STATE[state - new / in_progress / done / conflict]
    RESP[response_blob]
    HASH[fingerprint_hash]
  end
  AUTH --> LOOK
  LOOK --> KEY
  LOOK --> STATE
  STATE --> DISP
  DISP --> FIN
  FIN --> RESP
  FIN --> METR
  METR --> AUD`,
    problem: 'Without a standard tool-call boundary, every "agent → tool" path becomes ad-hoc HTTP, ad-hoc auth, ad-hoc retry. Each namespace ends up reinventing the same primitives.',
    whyThisApproach: 'A shared server_common.py gives every namespace identical scope enforcement, idempotency, OTel attributes, and metrics for free. Adding a new namespace is 50 lines of dispatch code, not a security review.',
    whenToUse: ['Domain-bounded tool sets (HR, ITSM, finance)', 'Action surfaces that need scope + audit', 'Async-replayable workflows'],
    whenNotToUse: ['Pure read endpoints — REST is fine', 'High-throughput data plane', 'Tiny single-tool services'],
    input: 'POST /tools/call {name, arguments, tenant_id, correlation_id} + Bearer JWT + optional Idempotency-Key',
    process: [
      'enforce_scope: validate JWT, intersect roles vs tool.required_scopes',
      'Bump scope-denial counter on reject',
      'Idempotency lookup (done/in_progress/conflict/new)',
      'Dispatch to namespace handler',
      'Record latency histogram + outcome counter',
      'Emit OTel span with actor + outcome attributes',
    ],
    output: '200 with tool result + idempotency-replay flag, OR typed error envelope (401/403/404/409/202).',
    flowchart: `flowchart LR
  a[POST /tools/call] --> b{Auth required?}
  b -->|yes| c[enforce_scope]
  c -->|fail| d[401/403 + denial counter]
  c -->|pass| e{Tool exists?}
  e -->|no| f[404]
  e -->|yes| g{Idempotency hit?}
  g -->|done| h[Return cached + outcome=replay]
  g -->|in_progress| i[202]
  g -->|conflict| j[409]
  g -->|new| k[Dispatch handler]
  k --> l[Latency histogram]
  l --> m[200 + finalize idempotency]`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant Srv as MCP server
  participant Idem as Idempotency store
  participant H as Tool handler
  participant Aud as Audit
  Cli->>Srv: POST /tools/call + JWT + Idempotency-Key
  Srv->>Srv: enforce_scope (claims + required_scopes)
  Srv->>Idem: lookup_or_register(key, fingerprint)
  Idem-->>Srv: state=new
  Srv->>H: dispatch(req, key, cid)
  H-->>Srv: result
  Srv->>Idem: finalize(key, response)
  Srv->>Aud: write {actor, action, cid}
  Srv-->>Cli: 200 + result`,
    alternatives: [
      { name: 'Direct REST per service', tradeoff: 'No shared scope/idempotency/OTel; reinvented per service' },
      { name: 'gRPC tool services', tradeoff: 'Stronger contract; harder to bridge to LLM agent loops; no MCP ecosystem' },
      { name: 'Function-calling via vendor LLM API', tradeoff: 'Vendor-locked; opaque; no operator visibility' },
      { name: 'Plain Lambda/Cloud Function per tool', tradeoff: 'Easy to start; no shared governance; cold-start cost' },
    ],
    challenges: [
      'Tool name + scope drift across namespaces',
      'Inconsistent error contracts',
      'Non-idempotent action design',
      'Weak observability without per-tool metrics',
      'Replay semantics easy to break',
    ],
    edgeCases: [
      { case: 'Scope reject with idempotency key', solution: 'Scope check BEFORE cache lookup so leaked key cannot bypass scope (drill_mcp_server_scope step 8)' },
      { case: 'Long-running tool exceeds client timeout', solution: 'Idempotency cache returns 202 in_progress; client retries with same key' },
      { case: 'Same key, different payload', solution: '409 conflict (drill_idempotency_durable)' },
      { case: 'Replay after MCP restart', solution: 'PostgresIdempotencyStore — durable across restarts (ADR-003)' },
    ],
    failureModes: [
      { mode: 'Tool handler raises', detect: 'tool_calls_total{outcome=error} spike', recover: 'Idempotency row marked failed; not retried by replay; alert' },
      { mode: 'Idempotency DB unreachable', detect: 'Scope-pass but lookup_or_register fails', recover: 'Fail-closed: 503; agent path falls back to draft' },
      { mode: 'JWT public key drift', detect: 'INVALID_TOKEN counter spike across tenants', recover: 'Rotate or unify key; restart MCP servers' },
    ],
    monitoring: [
      'documind_mcp_tool_calls_total{namespace,tool,outcome}',
      'documind_mcp_tool_call_duration_seconds (histogram)',
      'documind_mcp_scope_denials_total{namespace,tool,reason}',
      '/api/v1/health/tools (admin dashboard panel)',
    ],
    testing: [
      'drill_mcp_server_scope (8 steps, scope + idempotency interaction)',
      'drill_mcp_per_tool_telemetry (latency + denial counter)',
      'drill_scope_denial_actor_attribution (no leak on 401)',
      'drill_idempotency_durable (Postgres-backed replay)',
    ],
    security: [
      'JWT verification with strict claim validation (ADR-006)',
      'required_scopes per tool, intersected with claims.roles',
      'Tenant_id propagated through every call',
      'fail_closed audit per call (ADR-004)',
      'Actor attribution in 403 response detail (commit 307cbc9)',
    ],
    scaling: [
      '10x: stateless server, scale horizontally',
      '100x: per-namespace deployment for blast-radius isolation',
      'Idempotency DB is the bottleneck — partition by tenant_id',
    ],
    maturity: {
      mvp: 'Single namespace, no auth',
      production: 'Per-namespace server, JWT + scopes, OTel, in-memory idempotency',
      enterprise: 'Postgres-backed idempotency, per-tool latency histograms, scope-denial alerts, audit fail_closed',
    },
    limitations: [
      'Client-side latency includes idempotency lookup',
      'Replay semantics depend on caller-supplied keys',
      'Per-process breaker state (ADR-016 planned for cluster-wide)',
    ],
    projectFit: [
      'mcp/server_common.py — handle_tool_call (shared)',
      'mcp/server_hr.py + server_itsm.py + server_drills.py',
      'governance.mcp_idempotency (migration 007)',
      'commit 598ca9a — per-tool latency + denial telemetry',
    ],
    interviewLine: 'MCP gives us one tool-call boundary with shared scope, idempotency, audit, and observability. The hardest discipline is making every tool truly idempotent — without that, replay corrupts state.',
    implementationSteps: [
      { step: '1', logic: 'Define the tool registry: tool_name + required_scopes + handler + Pydantic input/output schemas.' },
      { step: '2', logic: 'Wire mcp/server_common.py: handle_tool_call orchestrates auth + idempotency + dispatch + audit.' },
      { step: '3', logic: 'enforce_scope: JWT validate via shared public key; intersect claims.roles vs tool.required_scopes; deny BEFORE idempotency lookup.' },
      { step: '4', logic: 'PostgresIdempotencyStore: lookup_or_register(key, fingerprint) returns state; finalize(key, response) on success.' },
      { step: '5', logic: 'Dispatch to namespace handler; type-validate args; record outcome.' },
      { step: '6', logic: 'Per-tool histogram + counter; OTel span with namespace + tool + outcome attributes.' },
      { step: '7', logic: 'fail_closed audit write — hash-chained per tenant. Block 200 if audit write fails.' },
      { step: '8', logic: 'Drills: scope + idempotency interaction (8 steps), per-tool telemetry, scope-denial actor attribution, durable replay.' },
    ],
    codeExample: {
      language: 'python',
      code: `# mcp/server_common.py (excerpt)
async def handle_tool_call(req: ToolCallRequest, tools: dict[str, Tool], idem: IdempotencyStore, aud: AuditWriter) -> ToolCallResponse:
    # 1. Scope check FIRST — before idempotency lookup
    enforce_scope(req.jwt_claims, tools[req.name].required_scopes)

    # 2. Tool exists?
    tool = tools.get(req.name)
    if not tool:
        raise NotFoundError(f"tool {req.name}")

    # 3. Idempotency state machine
    state = await idem.lookup_or_register(
        key=req.idempotency_key,
        tenant_id=req.tenant_id,
        fingerprint=hash_args(req.arguments),
    )
    if state == "done":
        return await idem.replay(req.idempotency_key)
    if state == "in_progress":
        raise InProgressError()  # 202
    if state == "conflict":
        raise ConflictError()    # 409

    # 4. Dispatch + finalize
    try:
        result = await tool.handler(req.arguments, tenant=req.tenant_id, cid=req.correlation_id)
        await idem.finalize(req.idempotency_key, response=result)
        await aud.write(actor=req.jwt_claims.sub, action=req.name, cid=req.correlation_id, outcome="ok")
        return ToolCallResponse(result=result, replay=False)
    except Exception as e:
        await idem.mark_failed(req.idempotency_key, error=str(e))
        await aud.write(actor=req.jwt_claims.sub, action=req.name, cid=req.correlation_id, outcome="error")
        raise`,
    },
    realUseCase: 'Agent calls hr.create_user with name=Jane + idempotency key K. Network blip; agent retries with same key K. First call: state=new → dispatch → user created. Second call: state=done → return cached response. User created exactly once. Without Postgres-backed idempotency: in-memory store loses state on restart, second call duplicates the user. drill_idempotency_durable proves the discipline.',
    prosCons: {
      pros: [
        'Uniform tool-call surface across all namespaces',
        'Shared scope + idempotency + audit + OTel for free',
        'Adding a namespace is dispatch code, not security review',
        'Postgres-backed replay survives restart',
        'Per-tool latency histograms + denial counters',
        'Mesh-isolated blast radius per namespace',
      ],
      cons: [
        'Idempotency lookup adds latency on hot path',
        'Replay semantics depend on caller-supplied keys',
        'Per-process breaker state (cluster-wide planned)',
        'Audit write on hot path = potential bottleneck under burst',
        'Schema drift across namespaces requires governance',
      ],
    },
    comparison: {
      left: 'MCP server (this approach)',
      right: 'Direct REST per service',
      rows: [
        { aspect: 'Scope enforcement', left: 'Shared enforce_scope decorator', right: 'Reinvented per service' },
        { aspect: 'Idempotency', left: 'Postgres-backed durable replay', right: 'Often missing or in-memory' },
        { aspect: 'Audit chain', left: 'Hash-chained, fail_closed', right: 'Optional / inconsistent' },
        { aspect: 'Observability', left: 'Per-tool histograms + counters', right: 'Per-route, no per-tool granularity' },
        { aspect: 'Adding new tool', left: '~50 lines dispatch + scope row', right: 'Full route + auth + audit each time' },
        { aspect: 'When to pick', left: 'Agent-callable actions; tool family', right: 'Pure-read APIs; no replay' },
      ],
    },
    solutions: [
      { problem: 'Scope drift across namespaces', solution: 'Central tool registry; required_scopes reviewed; drill_mcp_server_scope catches drift' },
      { problem: 'Idempotency conflict on schema change', solution: 'Fingerprint includes schema version; new schema = new key namespace' },
      { problem: 'Long-running tool times out client', solution: 'Idempotency cache returns 202 in_progress; client retries with same key; eventual 200 done' },
      { problem: 'Audit DB unreachable', solution: 'fail_closed: tool call returns 503; no silent loss; ADR-004' },
      { problem: 'Tool handler bug corrupts state', solution: 'Mark idempotency row failed; not retried by replay; alert on outcome=error spike' },
    ],
    bestPractices: {
      do: [
        'Scope check BEFORE idempotency lookup (drill_mcp_server_scope step 8)',
        'Postgres-backed idempotency (durable across restart)',
        'fail_closed audit write per call',
        'Per-tool histogram + counter, not per-route',
        'Pydantic args validation; reject unknown fields',
        'Idempotency key required on write tools; optional on read',
      ],
      avoid: [
        'In-memory idempotency in production (loses state on restart)',
        'Scope check AFTER cache lookup (leaked key bypasses scope)',
        'Mutating audit_log without hash-chain re-link',
        'Per-route metrics (loses tool-level visibility)',
        'Tool handlers with non-idempotent side effects',
      ],
      optimize: [
        'Connection pool tuned for idempotency-store roundtrips',
        'Audit writes batched via Kafka outbox if hot',
        'Per-namespace deployment for blast-radius isolation',
        'Cache JWT public key with TTL + refresh',
        'Compile Pydantic schemas once at startup',
      ],
    },
    antiPatterns: [
      'Tool handlers with non-idempotent side effects — replay corrupts state',
      'Scope check AFTER idempotency lookup — leaked key bypasses scope',
      'In-memory idempotency in production — restart loses state',
      'Audit write on best-effort — fail_closed is the discipline',
      'Per-route metrics — loses per-tool granularity for cost/latency analysis',
      'Hand-rolled error envelope per namespace — clients break on drift',
    ],
    testTypes: [
      'Unit (handler logic, mocked dependencies)',
      'Integration with real Postgres + mocked JWT',
      'Drill — scope + idempotency interaction (real PG)',
      'Drill — per-tool telemetry (real Prometheus)',
      'Drill — actor attribution on 401 (no decoded claims leak)',
      'Performance — burst load with idempotency replay',
    ],
    testScenarios: [
      { scenario: 'Scope reject + idempotency key present', expected: '401/403, key never registered (step 8)' },
      { scenario: 'Same key + same payload', expected: 'replay; outcome=replay; tool not re-executed' },
      { scenario: 'Same key + different payload', expected: '409 conflict' },
      { scenario: 'In-progress key, second call', expected: '202 Accepted; client polls' },
      { scenario: 'Tool handler raises', expected: 'Idempotency marked failed; counter outcome=error' },
      { scenario: 'Audit DB down', expected: '503 fail_closed; no 200 returned' },
    ],
    testData: [
      { type: 'Valid', example: '{name: hr.create_user, args: {...}, tenant_id: UUID, correlation_id: UUID, idempotency_key: UUID}' },
      { type: 'Cross-tenant', example: 'JWT for tenant A, request for tenant B → 401' },
      { type: 'Boundary', example: '1MB args payload (Pydantic max accepted)' },
      { type: 'Extreme', example: '500 concurrent calls same key — only 1 dispatch; 499 replay' },
      { type: 'Invalid', example: 'Unknown tool name → 404; missing required field → 422' },
    ],
    debuggingChecklist: [
      'Did the JWT validate? (check INVALID_TOKEN counter)',
      'Did scope check pass? (scope_denials_total counter)',
      'What is the idempotency state? (SELECT FROM mcp_idempotency)',
      'Did the audit row get written? (SELECT FROM audit_log; check hash chain)',
      'What is the tool handler return? (OTel span + outcome attribute)',
      'Is the latency histogram populated? (Prometheus query)',
      'Is the namespace pod healthy? (/api/v1/health/tools)',
    ],
    productionIssues: [
      { issue: 'Duplicate user created on retry', rootCause: 'In-memory idempotency lost state on restart; should be Postgres-backed (ADR-003)' },
      { issue: 'Scope denial allowed valid request', rootCause: 'JWT public key drift across namespaces; not all servers reloaded' },
      { issue: '202 returned indefinitely', rootCause: 'Tool handler crashed; idempotency stuck in_progress; needs sweeper' },
      { issue: 'Audit chain hash mismatch', rootCause: 'Two writers raced on prev_hash; need FOR UPDATE serialize per tenant' },
      { issue: 'Per-tool latency invisible', rootCause: 'Metric label was per-route, not per-tool; updated to namespace + tool' },
    ],
    performance: [
      'p50 dispatch < 50ms (auth + lookup + handler)',
      'p99 < 500ms with simple handler',
      'Idempotency lookup ~5-15ms (PG roundtrip)',
      'Audit write ~3-10ms (PG roundtrip)',
      'Throughput: 200-500 calls/sec per pod',
    ],
    costConsiderations: [
      'Postgres connection pool sized for (tools × concurrency)',
      'Audit table grows with call volume — partition + retention',
      'Per-namespace pod overhead vs blast-radius isolation tradeoff',
      'Idempotency table grows; lifecycle for old keys (24h-7d typical)',
    ],
    observability: [
      'Per-tool latency histogram p50/p95/p99',
      'Per-tool outcome counter (ok/error/replay/scope_denied)',
      'Scope denial rate per (namespace, tool, reason)',
      'Idempotency state distribution (new/in_progress/done/conflict)',
      'Audit chain integrity drill green/red',
      '/api/v1/health/tools admin dashboard',
    ],
    metrics: [
      { name: 'documind_mcp_tool_calls_total{namespace,tool,outcome}', example: 'Per-tool call rate; alert on outcome=error spike' },
      { name: 'documind_mcp_tool_call_duration_seconds', example: 'p99 < 500ms target; alert > 2s' },
      { name: 'documind_mcp_scope_denials_total{namespace,tool,reason}', example: '0 expected on legit traffic; spike = JWT drift' },
      { name: 'documind_mcp_idempotency_state{state}', example: 'new ≫ done; in_progress should drain quickly' },
      { name: 'documind_mcp_audit_failures_total', example: '0 expected; non-zero = fail_closed firing' },
    ],
    tradeoffs: [
      { decision: 'Per-namespace pod vs shared MCP', tradeoff: 'Blast-radius isolation vs ops cost' },
      { decision: 'Postgres vs Redis idempotency', tradeoff: 'Durable across restart vs lower latency' },
      { decision: 'Scope check pre vs post idempotency', tradeoff: 'Pre = secure; post = slightly cheaper on hot replay (insecure)' },
      { decision: 'Audit fail_closed vs fail_open', tradeoff: 'Reliability of audit chain vs availability under audit-DB outage' },
      { decision: 'Synchronous vs async audit write', tradeoff: 'Hash-chain integrity vs latency' },
    ],
    decisionMatrix: [
      { option: 'MCP server (default)', whenToUse: 'Agent-callable actions; tool family with shared concerns' },
      { option: 'gRPC service', whenToUse: 'Strong-typed contract; not LLM-callable; high throughput' },
      { option: 'REST direct', whenToUse: 'Pure-read API; no replay needed; one-off endpoint' },
      { option: 'Vendor function-calling', whenToUse: 'Prototype; OpenAI/Anthropic native; vendor-locked' },
      { option: 'Cloud Functions per tool', whenToUse: 'Serverless; cold-start tolerant; no shared governance' },
    ],
    starStory: {
      situation: 'Production saw two duplicate HR onboarding records for the same user. Audit log showed two distinct request IDs but identical payloads, 30 seconds apart. Customer support flagged the user complaint within hours.',
      task: 'Find root cause; prevent recurrence; recover the corrupted state.',
      action: 'Pulled idempotency table — in-memory store had been deployed; pod rotation lost the key state, so the retried call hit a fresh store and created a second user. Migrated to PostgresIdempotencyStore (ADR-003): durable across restart, replay returns cached response. drill_idempotency_durable now runs in CI: insert key, restart MCP, replay → outcome=replay, no second dispatch. The drill catches any future regression.',
      result: 'Zero duplicate-action incidents in the year since. Two production rollouts of new namespaces each leveraged the durable store from day one — no in-memory tempting shortcut. The drill catches any future regression at PR review.',
    },
    interviewTraps: [
      'Treating MCP as just "another API" — the discipline is in the cross-cutting concerns',
      'Scope check AFTER idempotency lookup — leaked key bypasses scope (most common mistake)',
      'In-memory idempotency in prod — restart loses state silently',
      'Audit best-effort — fail_closed is non-negotiable',
      'Per-route metrics — loses per-tool visibility for cost + latency',
      'Hand-rolled error envelope per namespace — clients break on drift',
    ],
    finalScript: 'MCP server is one tool-call boundary with shared scope, idempotency, audit, and observability. Each namespace — HR, ITSM, drill, finance — inherits identical primitives via mcp/server_common.py. Three non-negotiable disciplines. First, scope check BEFORE idempotency lookup so a leaked key cannot bypass scope; drill_mcp_server_scope step 8 verifies. Second, Postgres-backed idempotency — durable across restart; ADR-003 mandates this; in-memory loses state and creates duplicates. Third, fail_closed audit write — hash-chained per tenant; ADR-004 requires it; if audit DB is down, return 503 not silent 200. Per-tool latency histograms and denial counters give us per-tool visibility, not just per-route. Adding a new namespace is 50 lines of dispatch code plus tool registry rows — not a security review. The drill is non-negotiable: scope reject with idempotency key present must NEVER register the key.',
  },
  {
    slug: 'mcp-client',
    title: '2. MCP client + breaker + draft fallback',
    status: 'shipped',
    coreConcept: 'The MCP client is the agent\'s gateway to tools — it wraps every call with a circuit breaker and converts dependency failures into governed pending state instead of losing user intent.',
    problem: 'Tool servers fail. The agent doing agent.ask cannot just propagate the failure to the user; the action might be half-done remotely or transient. Either way, intent must be preserved.',
    whyThisApproach: 'CircuitBreaker + DraftStore composed in a single client wrapper means every tool path inherits resilience — agent code stays a one-liner.',
    whenToUse: ['Every agent → MCP tool path', 'Sensitive actions where retry must be safe', 'Multi-MCP routing'],
    whenNotToUse: ['Pure read tool calls — no draft needed', 'Idempotent gets where retry is cheap'],
    input: 'tool name + arguments + tenant_id + correlation_id',
    process: [
      'CircuitBreaker.allow() — fast-fail if open',
      'POST /tools/call to namespace server',
      'On success: record_success, return result',
      'On failure: record_failure, persist Draft, return degraded envelope',
      'DraftReplayWorker sweeps + retries pending drafts',
      'Auto-reject after N consecutive failures (ADR-009)',
    ],
    output: 'ToolResult (success) OR ToolResult(degraded=True, draft_id=X) for replay later.',
    flowchart: `flowchart LR
  a[Agent calls tool] --> b{CB allow?}
  b -->|no| c[Persist draft + degraded envelope]
  b -->|yes| d[POST /tools/call]
  d -->|success| e[record_success + return]
  d -->|fail| f[record_failure]
  f --> g[Persist draft]
  g --> c
  c --> h[Replay worker sweep]
  h --> i[Tool call]
  i -->|success| j[Mark replayed + audit]
  i -->|N consecutive fail| k[Mark rejected + audit]`,
    sequence: `sequenceDiagram
  autonumber
  participant Ag as Agent
  participant CB as CircuitBreaker
  participant Cli as MCPClient
  participant Srv as MCP server
  participant DS as DraftStore
  participant W as Replay worker
  Ag->>Cli: call_tool(name, args)
  Cli->>CB: allow()?
  CB-->>Cli: yes
  Cli->>Srv: POST /tools/call
  Srv-->>Cli: ConnectError
  Cli->>CB: record_failure
  Cli->>DS: insert Draft (pending)
  Cli-->>Ag: degraded ToolResult
  W->>DS: list_pending(tenant)
  W->>Srv: replay
  Srv-->>W: 200
  W->>DS: status=replayed + audit`,
    alternatives: [
      { name: 'Naive retry loop', tradeoff: 'Loses intent on persistent failure; storms during incidents' },
      { name: 'Synchronous fail-fast', tradeoff: 'User gets error; intent lost; bad UX' },
      { name: 'Queue-based fire-and-forget', tradeoff: 'No immediate-success path; harder to observe' },
    ],
    challenges: [
      'CB threshold tuning per dependency',
      'Stale drafts after business context changes',
      'Replay attribution (who triggered the actual side effect)',
      'Backlog spikes after dependency recovers',
    ],
    edgeCases: [
      { case: 'Tool succeeded remotely but local response timed out', solution: 'Idempotency key — replay returns cached response (drill_idempotency_durable)' },
      { case: 'Replay runs twice', solution: 'CAS-guarded mark_replayed (drill_action_draft_state_constraint)' },
      { case: 'Draft becomes stale', solution: 'Worker validates arguments before re-execution; auto-reject if stale' },
      { case: 'Dependency recovers; backlog spike', solution: 'Worker backpressure + bounded sweep size (ADR-009)' },
    ],
    failureModes: [
      { mode: 'CB stuck open', detect: 'breaker_state gauge open > N minutes', recover: 'Manual half-open probe; investigate dependency' },
      { mode: 'Draft store unreachable', detect: 'documind_audit_write_failures_total spike', recover: 'fail_closed audit; queue rebuilds when DB returns' },
      { mode: 'Replay worker dies', detect: 'documind_draft_pending_age_seconds growing unbounded', recover: 'Worker restart; backlog drained on resume' },
    ],
    monitoring: [
      'documind_circuit_breaker_state{name}',
      'documind_draft_replay_total{namespace,outcome}',
      'documind_draft_pending_age_seconds{namespace}',
      '/admin Operator Dashboard panel',
    ],
    testing: [
      'drill_breaker_transitions (closed→open→half_open→closed)',
      'drill_worker_auto_reject (N failures → rejected)',
      'drill_worker_backlog_age (gauge correctness)',
      'drill_worker_cb_aware (skip when CB open)',
    ],
    security: [
      'Service-token actor_id during replay (ADR-007)',
      'Audit row for every state transition',
      'Tenant scoping on all draft queries',
      'fail_closed default for audit writes',
    ],
    scaling: [
      'Per-process CB state today; ADR-016 for cluster-wide',
      'Worker scales by tenant — one worker per tenant if hot',
      'Postgres draft table — partition by tenant if large',
    ],
    maturity: {
      mvp: 'In-process CB + in-memory drafts',
      production: 'PostgresDraftStore + ReplayWorker + auto-reject',
      enterprise: 'Cluster-wide CB state (Redis); per-tenant worker; richer review UI',
    },
    limitations: [
      'Fallback preserves intent, not guaranteed completion',
      'Human review introduces latency',
      'Per-process CB state means multi-replica view is fragmented',
    ],
    projectFit: [
      'mcp/client.py — MCPClient with breaker + draft path',
      'libs/py/documind_core/circuit_breaker.py — unified CB',
      'mcp/idempotency.py — IdempotencyStore protocol',
      'services/inference-svc/app/workers/draft_replay.py',
      'commit 880022e — auto-reject after N failures',
    ],
    interviewLine: 'We convert dependency failures into governed pending state instead of losing the action. CircuitBreaker fails fast; DraftStore preserves intent; ReplayWorker resolves async. The three together are the resilience system.',
  },
  {
    slug: 'mcp-feature',
    title: '3. MCP feature surface (what it gives operators)',
    status: 'shipped',
    coreConcept: 'MCP is the project\'s tool-call boundary: every agent-callable action goes through a single contract that ships scope enforcement, idempotency, audit, draft fallback, OTel traces, and per-tool metrics for free — domain teams write only dispatch code.',
    oneLiner: 'One contract. Six guarantees. Every namespace inherits them; no namespace re-implements them.',
    businessContext: 'Without a uniform tool-call boundary, every domain (HR, ITSM, drill, finance) ends up reinventing auth + idempotency + audit + observability — and one missed primitive becomes a leak, a duplicate, or an undetected outage. MCP collapses six cross-cutting concerns into a single shared layer.',
    fiveW: {
      what: 'A shared tool-call contract: POST /tools/list returns the namespace catalog (name + required_scopes + JSON schema); POST /tools/call executes one tool with JWT-checked scopes, Postgres-backed idempotency, hash-chained audit, OTel spans, Prometheus histograms, and HITL-draft fallback when a downstream is unavailable.',
      why: 'Six guarantees compose into one wire format. Domain teams cannot accidentally skip scope checks or audit writes — the shared layer enforces them before dispatch reaches the handler.',
      where: 'Surface lives in mcp/ at the repo root (deliberately decoupled from documind_core so the package is portable). Servers per namespace in mcp/server_<ns>.py; client in mcp/client.py.',
      when: 'Any agent-executable action: HR user creation, ITSM ticket open, drill run, finance op. The default path for "agent wants to do something" is "agent calls an MCP tool".',
      who: 'Platform team owns mcp/server_common.py + the contract. Domain teams own per-namespace dispatch tables. Security reviews scope-table changes.',
    },
    interview30s: 'MCP gives the agent layer six things in one wire format: scope-checked execution, durable idempotency, hash-chained audit, draft fallback when upstream is down, full OTel tracing, and per-tool Prometheus metrics. Adding a namespace is ~50 lines of dispatch code, not a security review. The contract is ~120 lines in server_common.handle_tool_call; everything else is namespace logic. The drill catalog (drill_tool_catalog_ttl, drill_mcp_server_scope, drill_mcp_idempotency_replay, drill_worker_cb_aware) locks each guarantee.',
    coreBuildingBlocks: [
      'Scope enforcement — JWT roles ∩ tool.required_scopes; deny → 403 with scope_required',
      'Idempotency — Postgres mcp_idempotency: new/in_progress/done/conflict states; dedupe by Idempotency-Key',
      'Audit — hash-chained governance.audit_log row per tool call; fail_closed on write failure',
      'Draft fallback — when CB on a downstream opens, persist a draft instead of failing the action',
      'OTel traces — every tool call is a span with namespace + tool + outcome attributes',
      'Per-tool metrics — tool_calls_total{ns,tool,outcome} + tool_call_duration_seconds histogram',
      'Tool catalog TTL — MCPClient caches /tools/list; CB-open serves stale catalog (drill_tool_catalog_ttl)',
      'Decoupling contract — mcp/ never imports documind_core; future standalone repo possible',
    ],
    architectureRelevance: {
      backend: 'mcp/server_common.py is the only place that knows about JWT public keys, idempotency table layout, audit chain hashing. Per-namespace servers stay narrow.',
      rag: 'Drill MCP namespace exposes drill.list / drill.run as tools; agents can run readonly drills as part of their plan.',
      ai: 'Agent loop sequences tool calls via MCPClient. Plan + tool sequence + per-call outcome lands in the decision audit row (§48).',
      microservices: 'Each namespace is a separate FastAPI process; Istio mTLS strict; HR outage cannot cascade to ITSM.',
    },
    hld: `flowchart TB
  subgraph features[Six guarantees per tool call]
    SC[Scope check]
    ID[Idempotency]
    AU[Audit chain]
    DF[Draft fallback]
    OT[OTel span]
    ME[Prom metrics]
  end
  subgraph contract[POST /tools/call]
    HC[handle_tool_call - server_common.py]
  end
  subgraph dispatch[Per-namespace dispatch]
    HR[hr.create_user]
    IT[itsm.open_ticket]
    DR[drill.run]
  end
  HC --> SC
  HC --> ID
  HC --> AU
  HC --> DF
  HC --> OT
  HC --> ME
  HC --> HR
  HC --> IT
  HC --> DR`,
    coreLayers: [
      { layer: 'Contract', responsibility: '/tools/list (catalog), /tools/call (execute). Wire format frozen; servers ship behaviour.' },
      { layer: 'Cross-cutting', responsibility: 'scope, idempotency, audit, draft fallback, OTel, metrics — all in server_common.py.' },
      { layer: 'Dispatch', responsibility: 'Per-namespace tool handlers; type-validated args via Pydantic; pure domain logic.' },
      { layer: 'Catalog cache', responsibility: 'MCPClient TTLs /tools/list per host; CB-open serves stale rather than failing list.' },
    ],
    problem: 'Every domain team would re-implement the same six primitives differently — guaranteeing drift, leaks, and undetected gaps.',
    whyThisApproach: 'A single contract layer makes every guarantee universal. Drills lock the contract; namespaces inherit, not re-implement.',
    whenToUse: ['Any agent-callable action with side effects', 'Multi-tenant SaaS where scope leaks have audit consequences', 'Systems where downstream outages must not lose user intent'],
    whenNotToUse: ['Pure-read operations with no side effects (use direct queries)', 'Single-process internal calls (no isolation gain)', 'Sub-millisecond hot loops (RPC overhead unacceptable)'],
    input: 'POST /tools/call { tool: "ns.action", args: {...}, idempotency_key?, tenant_id (header) }',
    process: [
      'Receive POST /tools/call with JWT + tenant header',
      'enforce_scope: validate JWT, intersect roles with tool.required_scopes',
      'lookup_or_register idempotency key → return cached if done',
      'OTel span starts; baggage propagates correlation_id',
      'Dispatch to namespace handler with validated args',
      'On handler success: hash-chained audit row + Prometheus increment + return result',
      'On downstream failure with CB open: persist draft + return draft_id (HITL path)',
    ],
    output: 'Tool result OR draft_id (HITL fallback) OR scope-deny envelope OR idempotent replay of prior result.',
    realUseCase: 'Agent plans 3 tool calls (hr.lookup_user → hr.update_user → itsm.open_ticket). All three go through MCP. HR namespace is healthy → first two execute. ITSM is degraded → CB opens → third call persists a draft. Operator sees the draft in HITL UI; decides approve/reject; ReplayWorker re-fires.',
    prosCons: {
      pros: ['Six guarantees universal across namespaces', 'New namespace = dispatch code only', 'Drill catalog locks every guarantee', 'Mesh isolation per namespace'],
      cons: ['One bug in server_common affects all namespaces', 'JWT public key rotation is centralized risk', 'Idempotency table is a shared write hotspot at scale'],
    },
    challenges: [
      'Scope changes require coordinated drill updates',
      'Idempotency table grows fast — needs partitioned retention',
      'Catalog TTL choice trades fresh-catalog vs CB-resilience (drill_tool_catalog_ttl pins both)',
    ],
    edgeCases: [
      { case: 'Stale catalog served while CB open', solution: 'drill_tool_catalog_ttl step 5: stale-serve under CB-open MUST NOT increment fetch_count' },
      { case: 'Idempotency key reused with different args', solution: 'state machine returns conflict; original result not overwritten' },
      { case: 'JWT signature verification fails', solution: 'Return generic 401 INVALID_TOKEN — never leak decoded claims (attacker-controlled input)' },
    ],
    testing: [
      'drill_tool_catalog_ttl — TTL respect + CB-open stale-serve',
      'drill_mcp_server_scope — scope-check happens BEFORE idempotency lookup (leaked key cannot bypass scope)',
      'drill_mcp_idempotency_replay — durable across server restart',
      'drill_audit_hash_chain — append-only chain integrity',
    ],
    failureModes: [
      { mode: 'Scope-deny burst', detect: 'tool_calls_total{outcome="scope_denied"} spike', recover: 'audit row per deny; investigate auth bypass attempt or stale scopes' },
      { mode: 'Idempotency table contention', detect: 'tool_call_duration p95 climbing', recover: 'partition by tenant; ADR-008 RLS already enforces tenant filter' },
      { mode: 'CB-open on namespace', detect: 'circuit_breaker_state{name="mcp_<ns>"} == 1', recover: 'drafts persist; ReplayWorker re-fires when CB closes' },
    ],
    security: ['Scope check BEFORE idempotency lookup', 'JWT failure never leaks claims', 'Audit chain hash-prevents tampering', 'Tenant_id from JWT, not request body'],
    scaling: ['Per-namespace process = per-namespace blast radius', 'Idempotency partition by tenant for hot tenants', 'OTel sampler tunable per namespace'],
    monitoring: ['tool_calls_total by ns/tool/outcome', 'tool_call_duration_seconds histogram', 'circuit_breaker_state per namespace', 'audit_log_writes_total / audit_log_chain_break_total'],
    alternatives: [
      { name: 'Direct REST per service', tradeoff: 'No uniform contract; every team re-implements primitives' },
      { name: 'gRPC + interceptors', tradeoff: 'Same shape; harder ecosystem (no Postman, harder for human-callable agents)' },
    ],
    maturity: {
      mvp: 'Single namespace + scope only',
      production: 'Six guarantees + drill catalog + draft fallback',
      enterprise: 'Multi-region with replicated idempotency table + cross-region audit chain reconciliation',
    },
    limitations: ['Wire format frozen; new guarantees need a v2 contract', 'Idempotency limited to ~24h retention by default'],
    projectFit: ['mcp/server_common.py (763 lines, six guarantees)', 'mcp/server_hr.py (255 lines)', 'mcp/server_itsm.py (241 lines)', 'mcp/server_drills.py (439 lines)', 'mcp/client.py (505 lines)'],
    interviewLine: 'MCP gives six guarantees in one wire format — scope, idempotency, audit, draft fallback, OTel, metrics. Domain teams add ~50 lines per namespace; the platform team owns the 763-line shared layer. Drills lock every guarantee; that\'s the gate.',
  },
  {
    slug: 'mcp-architect',
    title: '4. MCP architecture (where it sits in the system)',
    status: 'shipped',
    coreConcept: 'MCP sits between the agent orchestrator and the action surface — orchestrator is the planner, MCP servers are the workers. The boundary is enforced by Istio mTLS-strict, protected by JWT scopes, persisted by Postgres idempotency, and observable end-to-end by OTel baggage.',
    oneLiner: 'Planner ↔ MCP boundary = the project\'s "do something" gate. Everything that mutates external state crosses it.',
    businessContext: 'The architecture answers: where does an AI decision become a real-world side-effect? Without a clear boundary, agents either (a) call services directly and bypass governance, or (b) get blocked by ad-hoc auth in every service. MCP is the boundary; the planner knows about it; everything else stays naive.',
    fiveW: {
      what: 'A boundary layer between agentic decision-making (orchestrator + planner) and the side-effect surface (HR, ITSM, drills, finance). Realised as multiple FastAPI servers in mcp/, fronted by api-gateway, behind Istio mesh.',
      why: 'Agents reason; servers act. Mixing them creates audit gaps and policy ambiguity. Separation makes "what was decided" auditable separately from "what was done".',
      where: 'Sits behind api-gateway, in front of every domain service. Each namespace is its own pod; mesh routes by Host header.',
      when: 'Every action that mutates external state. Read-only RAG retrieval bypasses MCP (different surface); writes always traverse it.',
      who: 'Architect-of-record per ADR-016 (parallel-agent allocation). Each namespace has a domain owner per ADR-018 (three-way work allocation).',
    },
    interview30s: 'Architecture is layered: orchestrator + planner generate plans; MCPClient executes tool calls; per-namespace MCP servers dispatch. Cross-cutting (scope, idempotency, audit, OTel) lives in server_common.py — every namespace inherits identical primitives. The boundary is mTLS-strict mesh; JWT verifies the caller; tenant_id comes from JWT, not the body. Drills (drill_*.py) lock the boundary contract. ADR-016 names this as the parallel-agent boundary; ADR-018 names the work-allocation boundary.',
    hld: `flowchart TB
  subgraph user[User / agent]
    U[Operator UI / agent loop]
  end
  subgraph plane[Control plane]
    O[Agent orchestrator]
    P[Planner]
    M[MCPClient - mcp/client.py]
  end
  subgraph gw[Gateway + mesh]
    AGW[api-gateway]
    MESH[Istio mTLS strict]
  end
  subgraph mcp[MCP boundary]
    SC[server_common.py]
    HR[server_hr.py]
    IT[server_itsm.py]
    DR[server_drills.py]
  end
  subgraph state[Stateful backends]
    PG[(Postgres - audit + idempotency + drafts)]
    JW[(JWT public key store)]
    OB[(Jaeger + Prometheus)]
  end
  U --> O
  O --> P
  P --> M
  M --> AGW
  AGW --> MESH
  MESH --> HR
  MESH --> IT
  MESH --> DR
  HR --> SC
  IT --> SC
  DR --> SC
  SC --> PG
  SC --> JW
  SC --> OB`,
    networkFlow: `flowchart LR
  A[Agent loop] -->|HTTPS+JWT| GW[api-gateway :8080]
  GW -->|mTLS| MCP_HR[mcp_hr :8090]
  GW -->|mTLS| MCP_IT[mcp_itsm :8091]
  GW -->|mTLS| MCP_DR[mcp_drills :8092]
  MCP_HR --> PG_AUD[(audit_log)]
  MCP_HR --> PG_IDM[(mcp_idempotency)]
  MCP_HR --> PG_DR[(action_drafts)]
  MCP_HR --> JAE[(Jaeger collector)]
  MCP_HR --> PROM[(Prometheus textfile)]`,
    sequence: `sequenceDiagram
  autonumber
  participant Plan as Planner
  participant Cli as MCPClient
  participant GW as api-gateway
  participant Srv as mcp_<ns>
  participant Idem as Postgres idempotency
  participant Aud as Postgres audit_log
  participant H as Tool handler
  Plan->>Cli: call_tool(tool, args, tenant_id)
  Cli->>GW: POST /tools/call (JWT + Idempotency-Key)
  GW->>Srv: forward (mTLS)
  Srv->>Srv: enforce_scope(JWT, required_scopes)
  Srv->>Idem: lookup_or_register(key)
  alt cached done
    Idem-->>Srv: prior result
    Srv-->>Cli: 200 (idempotent replay)
  else new
    Srv->>H: dispatch(args)
    H-->>Srv: result
    Srv->>Aud: append hash-chained row
    Srv->>Idem: mark done(result)
    Srv-->>Cli: 200 result
  end`,
    coreLayers: [
      { layer: 'L1 Context', responsibility: 'Operator + agent loop on one side; HR/ITSM/finance backends on the other.' },
      { layer: 'L2 Container', responsibility: 'Per-namespace MCP server pod. mTLS strict ingress. Health probes (startup/liveness/readiness) per §47.8.' },
      { layer: 'L3 Component', responsibility: 'handle_tool_call → enforce_scope → idempotency → dispatch → audit → metrics.' },
      { layer: 'L5 Governance', responsibility: 'ADR-016 (parallel-agent boundary), ADR-008 (tenant isolation via RLS), §48 decision audit.' },
      { layer: 'L6 Observability', responsibility: 'OTel CompositePropagator pulls baggage; tool_calls_total + tool_call_duration; per-namespace dashboards.' },
      { layer: 'L7 Lifecycle', responsibility: 'Build → drill catalog green → canary deploy per namespace → rollback by registry per §47.7.' },
    ],
    problem: 'Without an explicit boundary, agent decisions and side-effects blur. Audit becomes ambiguous. Each domain reinvents auth.',
    whyThisApproach: 'Layering = decoupling. Planner is naive about idempotency; servers are naive about LLM context. Each layer optimizes for its job; the boundary is enforced.',
    whenToUse: ['Multi-namespace systems where each domain has different scopes', 'Audit-required environments (regulated, compliance)', 'When agent decisions need separating from execution for replay/rollback'],
    whenNotToUse: ['Single-domain systems (overkill — direct REST is fine)', 'Pure-read systems (no audit needed)', 'In-process function calls'],
    input: 'Agent intent (tool name, args, tenant context, correlation_id from baggage)',
    process: [
      'Planner emits tool sequence',
      'MCPClient batches calls; each is one /tools/call POST',
      'api-gateway validates JWT + tenant header, forwards via mesh',
      'MCP server enforces scope, deduplicates by Idempotency-Key, dispatches to handler',
      'Audit row appended with hash chain; metrics incremented; result returned',
      'On namespace CB-open: client persists draft, returns draft_id; ReplayWorker fires when CB closes',
    ],
    output: 'Per-call result OR draft_id; planner aggregates; decision audit row references all tool_call request_ids.',
    architectureRelevance: {
      backend: 'mcp/* is decoupled from documind_core (no imports), making it portable to a future standalone repo.',
      rag: 'Drill namespace runs evals as tool calls. Retrieval surface is read-only and bypasses MCP.',
      ai: '§48 decision audit row stores plan + tool_call request_ids; explainability traces back through MCP audit chain.',
      microservices: 'Per-namespace pod = per-namespace blast radius. ADR-016 names the boundary; mesh enforces mTLS.',
    },
    realUseCase: 'Operator asks agent to onboard a contractor. Plan: (1) hr.create_user, (2) hr.assign_role, (3) itsm.open_ticket, (4) hr.send_welcome. Steps 1-2 traverse mcp_hr; step 3 traverses mcp_itsm; step 4 traverses mcp_hr again. All four land hash-chained audit rows; the decision audit row references all four request_ids. If step 3 fails (mcp_itsm CB-open), step 3 becomes a draft; operator sees pending HITL approval.',
    prosCons: {
      pros: ['Clear boundary = clear audit', 'Per-namespace blast radius', 'Drills lock contracts', 'Replay/rollback via draft layer'],
      cons: ['Extra hop adds ~5-10ms latency', 'Operational surface = N pods (one per namespace)', 'Schema evolution requires coordinated changes'],
    },
    limitations: ['Wire format frozen — v2 contract required for new cross-cutting guarantees', 'Per-process scope cache means scope rotation is not instant'],
    challenges: ['Coordinating audit-chain hash across namespaces if cross-namespace transactions needed (currently each namespace has its own chain)', 'Tracing across MCP → downstream (handled by OTel baggage)'],
    edgeCases: [
      { case: 'Cross-namespace transaction', solution: 'Saga pattern via planner; each step is its own MCP call with compensating tool' },
      { case: 'Mesh split-brain (Istio control plane down)', solution: 'mTLS data plane fails closed; tool calls 503 cleanly; CB opens; drafts accumulate' },
    ],
    testing: ['drill_baggage_log_formatter — baggage propagates through MCP', 'drill_mcp_server_scope — scope-check ordering', 'drill_audit_hash_chain — chain integrity per namespace'],
    failureModes: [
      { mode: 'Mesh failure', detect: 'mTLS errors in api-gateway logs', recover: 'Istio rollback per L7; data plane retains last-known config briefly' },
      { mode: 'JWT key rotation lag', detect: '401 spike on previously-valid tokens', recover: 'JWKS refresh + dual-key window during rotation' },
    ],
    security: ['mTLS strict mesh = caller authenticated even without JWT', 'JWT roles intersected with tool.required_scopes', 'Tenant_id from JWT (claims), never from request body', 'Audit chain hash-prevents tampering'],
    scaling: ['Horizontal per namespace pod', 'Idempotency table partition by tenant', 'OTel sampler 10% in prod, 100% in canary'],
    monitoring: ['Per-namespace tool_calls_total', 'audit_log_chain_break_total (must stay 0)', 'mcp_<ns>_p95_latency_seconds', 'circuit_breaker_state per downstream'],
    alternatives: [
      { name: 'Direct mesh-to-service calls', tradeoff: 'Bypasses MCP guarantees; every service re-implements scope+idempotency+audit' },
      { name: 'Single mega-MCP server', tradeoff: 'No blast-radius isolation; one bug grounds all namespaces' },
    ],
    maturity: {
      mvp: 'One namespace + scope + idempotency',
      production: 'Per-namespace pods + audit chain + draft fallback',
      enterprise: 'Multi-region replicated audit + cross-region idempotency reconciliation',
    },
    projectFit: ['ADR-016 parallel-agent allocation', 'ADR-018 three-way work allocation', '§47.2 C4 7-level model', '§48 decision audit row format'],
    interviewLine: 'Architecture is layered: agents decide, MCP gates execution. The boundary is mTLS+JWT+scopes; per-namespace pods give blast-radius isolation; per-namespace audit chains give per-domain integrity. ADRs 016 and 018 name the boundary; drills lock the contract; ~50 lines of dispatch makes a new namespace.',
  },
  {
    slug: 'mcp-components',
    title: '5. Each MCP component (file-by-file)',
    status: 'shipped',
    coreConcept: 'mcp/ is seven files: a shared scaffolding, three namespace servers, a smart client, a draft store, and an idempotency layer. Total ~2850 lines. Each has one job and a drill.',
    oneLiner: 'Seven files. Seven jobs. Seven drills.',
    fiveW: {
      what: 'mcp/server_common.py (763 lines), mcp/client.py (505 lines), mcp/server_drills.py (439 lines), mcp/drafts.py (382 lines), mcp/idempotency.py (265 lines), mcp/server_hr.py (255 lines), mcp/server_itsm.py (241 lines).',
      why: 'Each file has a single responsibility. Adding a new namespace touches only one file (server_<ns>.py); changing cross-cutting touches only server_common.py.',
      where: 'mcp/ at repo root, deliberately decoupled from documind_core.',
      when: 'Always. Every commit that touches mcp/ ships a drill update.',
      who: 'Platform team owns server_common + client + drafts + idempotency. Domain teams own per-namespace servers.',
    },
    coreLayers: [
      { layer: 'mcp/server_common.py (763)', responsibility: 'Shared scaffolding: setup_server_otel (CompositePropagator + OTLP exporter), build_auth (JWT verifier), enforce_scope (JWT roles ∩ required_scopes), handle_tool_call (idempotency + dispatch + audit), error envelope. The single place that knows about cross-cutting concerns.' },
      { layer: 'mcp/client.py (505)', responsibility: 'MCPClient — async httpx client with circuit breaker (per-host), tool catalog cache (TTL + stale-serve under CB-open), draft fallback hook, baggage propagation, idempotency-key forwarding. Used by inference-svc, agent-orchestrator-svc, drill runner.' },
      { layer: 'mcp/idempotency.py (265)', responsibility: 'IdempotencyStore protocol + PostgresIdempotencyStore. State machine: new → in_progress → done | conflict. Postgres-backed (governance.mcp_idempotency). ADR-003.' },
      { layer: 'mcp/drafts.py (382)', responsibility: 'DraftStore protocol + PostgresDraftStore. Persists action drafts when downstream CB-open. State: pending → resolved | rejected. ReplayWorker (in inference-svc) re-fires on CB-close.' },
      { layer: 'mcp/server_hr.py (255)', responsibility: 'HR namespace dispatch. Tools: hr.create_user, hr.update_user, hr.assign_role, hr.lookup_user, hr.send_welcome. Calls into HR backend via internal API.' },
      { layer: 'mcp/server_itsm.py (241)', responsibility: 'ITSM namespace dispatch. Tools: itsm.open_ticket, itsm.update_ticket, itsm.assign_ticket, itsm.list_tickets. Backed by ServiceNow-equivalent.' },
      { layer: 'mcp/server_drills.py (439)', responsibility: 'Drill orchestration namespace. Tools: drill.list (scope drill:read), drill.run (scope drill:run). Wraps scripts/run_drills.py as MCP tools so agents can run readonly drills.' },
    ],
    coreBuildingBlocks: [
      'mcp/server_common.py — handle_tool_call, enforce_scope, setup_server_otel, build_auth, NoopCM',
      'mcp/client.py — MCPClient (async httpx, CB, catalog TTL, draft fallback, baggage)',
      'mcp/idempotency.py — IdempotencyStore protocol + PostgresIdempotencyStore',
      'mcp/drafts.py — DraftStore protocol + PostgresDraftStore + audit-row writer',
      'mcp/server_hr.py — hr.* dispatch table',
      'mcp/server_itsm.py — itsm.* dispatch table',
      'mcp/server_drills.py — drill.* dispatch table (drill.list / drill.run)',
    ],
    hld: `flowchart TB
  subgraph layer1[Shared scaffolding - 1 file]
    SC[server_common.py - 763 lines]
  end
  subgraph layer2[Smart client - 1 file]
    CL[client.py - 505 lines]
  end
  subgraph layer3[State protocols + adapters - 2 files]
    ID[idempotency.py - 265]
    DR[drafts.py - 382]
  end
  subgraph layer4[Per-namespace servers - 3 files]
    HR[server_hr.py - 255]
    IT[server_itsm.py - 241]
    DRS[server_drills.py - 439]
  end
  HR --> SC
  IT --> SC
  DRS --> SC
  SC --> ID
  SC --> DR
  CL --> SC
  CL --> ID
  CL --> DR`,
    interview30s: 'Seven files in mcp/. server_common.py is 763 lines and owns six guarantees. client.py is 505 lines and owns the smart-client semantics (CB, catalog TTL, draft fallback, baggage). idempotency.py + drafts.py (265+382) are the state protocols + Postgres adapters. server_hr / server_itsm / server_drills are three namespaces — each ~250 lines of dispatch. Total ~2850 lines for the entire MCP layer; adding a namespace is ~50 lines. Each file has a drill.',
    problem: 'Without per-file responsibility, "where do I add scope enforcement" or "where does a draft get written" becomes a code-archaeology question.',
    whyThisApproach: 'One file = one job. Drills are per-file. Reviewing a PR that touches mcp/server_hr.py only requires looking at one dispatch table; reviewing mcp/server_common.py requires the platform team because it changes cross-cutting behaviour.',
    whenToUse: ['Every time you write or review MCP code', 'Onboarding a new namespace owner', 'Investigating a tool-call failure (file boundary tells you which layer)'],
    whenNotToUse: ['Cross-namespace logic — coordinated; usually saga pattern in planner instead'],
    input: 'A maintenance task ("add tool X" / "fix audit bug") → file selection',
    process: [
      'Tool dispatch logic? → mcp/server_<ns>.py',
      'Cross-cutting (scope, audit, idempotency, OTel)? → mcp/server_common.py',
      'Client-side behaviour (CB, catalog cache, draft fallback)? → mcp/client.py',
      'State persistence change? → mcp/idempotency.py or mcp/drafts.py',
      'New namespace? → new mcp/server_<ns>.py + entry in run_drills.py resource tag',
    ],
    output: 'A PR scoped to the right file with a drill update.',
    realUseCase: 'Bug: scope-deny audit row missing tenant_id. File: mcp/server_common.py (audit row construction). Fix one line; update drill_audit_namespace_semantics; one file in PR. Bug: hr.create_user not idempotent. File: mcp/server_hr.py (dispatch); fix rare-args branch; idempotency.py untouched (its job is durable; HR\'s job is reproducible). Per-file separation makes both PRs clean.',
    challenges: [
      'server_common.py size (763 lines) — review burden if it grows beyond ~1000',
      'Per-namespace dispatch boilerplate — slight duplication; acceptable for blast-radius isolation',
      'Cross-file changes (e.g., new scope flow) require coordinated drill updates',
    ],
    edgeCases: [
      { case: 'New namespace forgets resource tag', solution: 'drill_drill_catalog_discipline catches it (per ADR-015 ratchet)' },
      { case: 'Cross-cutting change skips drill update', solution: 'Pre-commit hook + drill_runner_junit catches gap' },
    ],
    testing: [
      'drill_tool_catalog_ttl (mcp/client.py)',
      'drill_mcp_server_scope (mcp/server_common.py)',
      'drill_mcp_idempotency_replay (mcp/idempotency.py)',
      'drill_worker_cb_aware (mcp/client.py CB integration)',
      'drill_baggage_log_formatter (mcp/server_common.py OTel wiring)',
      'audit_frontend_link.py (uses MCP for /tools/list catalog reads)',
    ],
    failureModes: [
      { mode: 'server_common bug', detect: 'multiple namespace drills failing simultaneously', recover: 'rollback server_common; investigate; ship fix with drill update' },
      { mode: 'Per-namespace bug', detect: 'one namespace drill failing in isolation', recover: 'rollback that namespace pod; other namespaces unaffected' },
    ],
    security: ['server_common owns ALL JWT validation', 'Per-namespace files cannot bypass enforce_scope (linter could check)', 'Audit writer is fail_closed by default'],
    scaling: ['Per-namespace pods scale independently', 'server_common.py is in-process per pod (no shared state)', 'idempotency + drafts are Postgres — scale via partitioning'],
    monitoring: ['Per-file commit volume (high churn = re-think factoring)', 'Per-file drill execution time (regression budget)', 'Per-file PR-review time (file size proxy)'],
    alternatives: [
      { name: 'Single MCP file', tradeoff: 'Faster bootstrap, no blast-radius isolation, no per-domain ownership' },
      { name: 'One file per tool (instead of per namespace)', tradeoff: 'Too granular; loses dispatch-table benefits' },
    ],
    limitations: ['Boundary discipline is convention, not enforced — platform team must review server_common changes', 'No type-level enforcement that namespace files import only sanctioned utilities from server_common'],
    maturity: {
      mvp: 'One server file + client',
      production: 'Seven files, drills per file, ADR-016 boundary defined',
      enterprise: 'Same seven roles but multiple processes per role (sharded namespaces)',
    },
    projectFit: ['Mirrors the §47.2 C4 layered model at file level', 'ADR-016 parallel-agent allocation = file ownership', 'Drill-per-file = §43 pattern'],
    interviewLine: 'mcp/ is seven files, ~2850 lines, one job each, one drill each. Cross-cutting in server_common.py; smart client in client.py; durable state in idempotency.py + drafts.py; three namespace dispatch tables. Adding a namespace is ~50 lines + a drill. The file boundary IS the review boundary.',
  },
  {
    slug: 'mcp-flow',
    title: '6. End-to-end MCP flow (one tool call, every layer)',
    status: 'shipped',
    coreConcept: 'A single /tools/call traverses 11 distinct steps from agent intent to audit row. Every step is logged; every step has a failure mode; every step has a drill that locks behaviour.',
    oneLiner: 'Agent → MCPClient → gateway → server_common → enforce_scope → idempotency → dispatch → handler → audit → metrics → return.',
    interview30s: 'The flow has 11 steps. Agent decides → MCPClient adds Idempotency-Key + baggage → api-gateway validates JWT + tenant → mTLS to namespace pod → enforce_scope (JWT roles ∩ required_scopes) → idempotency lookup_or_register → if cached done, replay; else dispatch → handler executes → hash-chained audit append → Prometheus increment → response. CB-open at any downstream short-circuits to draft persist. Each step has a drill: scope ordering, idempotency replay, audit chain, baggage propagation, CB stale-serve, draft fallback. The flow is the contract; the drills are the gate.',
    sequence: `sequenceDiagram
  autonumber
  participant A as Agent loop
  participant Cli as MCPClient
  participant GW as api-gateway
  participant Srv as mcp_<ns> server
  participant SC as server_common
  participant SCO as enforce_scope
  participant Idem as PostgresIdempotencyStore
  participant H as Tool handler
  participant Aud as audit_log writer
  participant OT as OTel + Prom
  A->>Cli: call_tool(tool, args, tenant_id, idempotency_key)
  Cli->>Cli: check CB state for host
  alt CB closed or half-open
    Cli->>GW: POST /tools/call (JWT + Idem-Key + baggage)
    GW->>Srv: forward (mTLS)
    Srv->>SC: handle_tool_call
    SC->>SCO: validate JWT + intersect roles
    alt scope OK
      SCO-->>SC: pass
      SC->>Idem: lookup_or_register(idem-key)
      alt new
        Idem-->>SC: state=in_progress
        SC->>H: dispatch(args)
        H-->>SC: result
        SC->>Aud: append hash-chained row
        SC->>Idem: mark done(result)
        SC->>OT: span attrs + prom counter
        SC-->>GW: 200 result
      else cached done
        Idem-->>SC: prior result
        SC->>OT: span attrs (replayed)
        SC-->>GW: 200 (idempotent)
      end
    else scope deny
      SCO-->>SC: 403 scope_required
      SC->>Aud: append deny row
      SC-->>GW: 403 envelope
    end
    GW-->>Cli: response
    Cli-->>A: result OR 4xx
  else CB open
    Cli->>Cli: persist draft (via DraftStore)
    Cli-->>A: draft_id (HITL fallback)
  end`,
    flowchart: `flowchart LR
  s1[1. Agent intent] --> s2[2. MCPClient: CB check + Idem-Key + baggage]
  s2 -->|CB closed| s3[3. api-gateway: JWT + tenant header]
  s3 --> s4[4. mTLS to mcp_ns pod]
  s4 --> s5[5. server_common.handle_tool_call]
  s5 --> s6[6. enforce_scope]
  s6 -->|pass| s7[7. lookup_or_register idem-key]
  s7 -->|new| s8[8. dispatch to handler]
  s7 -->|cached| s11[11. replay prior result]
  s8 --> s9[9. handler returns]
  s9 --> s10[10. audit + metrics]
  s10 --> s11
  s2 -.->|CB open| sd[Draft persist + return draft_id]
  s6 -.->|deny| sde[403 + deny audit row]`,
    coreBuildingBlocks: [
      'Step 1 Agent: planner emits tool sequence',
      'Step 2 Client: CB check, generate Idempotency-Key, attach baggage',
      'Step 3 Gateway: JWT validation, tenant header forward',
      'Step 4 Mesh: mTLS strict to namespace pod',
      'Step 5 Server: handle_tool_call entrypoint',
      'Step 6 Scope: JWT roles ∩ tool.required_scopes',
      'Step 7 Idempotency: state machine new / in_progress / done',
      'Step 8 Dispatch: per-namespace handler with Pydantic-validated args',
      'Step 9 Handler: domain logic (HR/ITSM/drill)',
      'Step 10 Audit + metrics: hash-chained row, Prom counter, OTel span attrs',
      'Step 11 Return: result OR replayed result OR draft_id OR scope-deny envelope',
    ],
    coreLayers: [
      { layer: 'Step 1-2 (client)', responsibility: 'Intent + idempotency-key + circuit-breaker check + baggage propagation' },
      { layer: 'Step 3-4 (transport)', responsibility: 'JWT + mTLS + tenant header' },
      { layer: 'Step 5-7 (cross-cutting)', responsibility: 'Scope enforcement + idempotency state machine' },
      { layer: 'Step 8-9 (domain)', responsibility: 'Pydantic-validated dispatch + handler logic' },
      { layer: 'Step 10-11 (audit/return)', responsibility: 'Hash-chained audit + metrics + response' },
    ],
    architectureRelevance: {
      backend: 'Each step is a logged event tied to one correlation_id (baggage). 11 steps, 11 spans.',
      rag: 'Drill flow uses the SAME 11 steps; readonly drills exit at step 8 (handler returns drill outcome).',
      ai: '§48 decision audit row captures the 11-step flow per tool call; explainability traces back through audit chain.',
      microservices: 'Steps 3-4 cross network boundary (gateway + mesh). Steps 5-11 are intra-pod.',
    },
    problem: 'Without an explicit step-by-step contract, observability is hand-wavy and drills are incomplete.',
    whyThisApproach: '11 named steps means 11 named drills. Operators triaging a slow tool call jump straight to the step with the problem (e.g., step 7 latency spike = idempotency table contention).',
    whenToUse: ['Always. This is the only path for tool calls.'],
    whenNotToUse: ['Read-only RAG retrieval (separate surface)', 'Internal in-process calls (no MCP needed)'],
    input: 'Agent intent: { tool, args, tenant_id, idempotency_key, correlation_id (baggage) }',
    process: [
      'Steps 1-2: Client-side prep (CB check, Idempotency-Key, baggage)',
      'Steps 3-4: Transport (JWT, mTLS, tenant header)',
      'Steps 5-7: Cross-cutting (scope, idempotency state machine)',
      'Steps 8-9: Domain dispatch (Pydantic validation, handler)',
      'Steps 10-11: Audit + metrics + return',
    ],
    output: 'Tool result (step 11) OR idempotent replay (step 11 short-circuit) OR draft_id (CB-open at step 2) OR 403 (scope-deny at step 6)',
    realUseCase: 'Trace ID abc123 in Jaeger shows: span1=client-prep (step 1-2, 0.5ms), span2=api-gateway (step 3, 1ms), span3=mcp_hr (steps 4-11, 18ms). Inside span3: enforce_scope=0.3ms, idempotency_lookup=2ms (cache hit), dispatch=12ms (HR backend call), audit_write=2ms, prom_increment=0.5ms. Operator sees end-to-end latency of 19.5ms and knows the dispatch step is the dominant cost — exactly where to look for SLO regression.',
    edgeCases: [
      { case: 'Idempotency key reused on a step-9 failure', solution: 'State machine returns in_progress + 409 Conflict; client retries safely' },
      { case: 'Audit write fails (step 10)', solution: 'fail_closed = abort the response; client sees 5xx; better than uncaptured side-effect' },
      { case: 'Baggage missing (step 2)', solution: 'Server generates correlation_id; logs warn; trace tree still complete' },
    ],
    challenges: [
      'Maintaining step-level drill coverage as the contract evolves',
      'OTel sampling — high-volume tools may need per-tool sampler config to avoid cost explosion',
      'Idempotency-Key collision across tenants (mitigated by including tenant_id in the storage key)',
    ],
    testing: [
      'Step 2: drill_worker_cb_aware (CB-open behaviour)',
      'Step 6: drill_mcp_server_scope (scope ordering)',
      'Step 7: drill_mcp_idempotency_replay (state machine)',
      'Step 8-9: namespace-specific drills (drill_hr_create_user, etc.)',
      'Step 10: drill_audit_hash_chain (chain integrity)',
      'Step 2-11: drill_baggage_log_formatter (full trace propagation)',
    ],
    failureModes: [
      { mode: 'Step 2 CB open', detect: 'circuit_breaker_state{host=mcp_<ns>}=1', recover: 'draft persist; ReplayWorker fires when CB closes' },
      { mode: 'Step 6 scope deny burst', detect: 'tool_calls_total{outcome="scope_denied"} spike', recover: 'audit row per deny; investigate auth bypass attempt' },
      { mode: 'Step 7 idempotency contention', detect: 'tool_call_duration p95 climbing on writes', recover: 'partition idempotency table by tenant' },
      { mode: 'Step 10 audit chain break', detect: 'audit_log_chain_break_total > 0', recover: 'STOP all writes; reconcile chain; security incident' },
    ],
    security: ['Step 3 JWT validation = caller identity', 'Step 6 scope check BEFORE step 7 idempotency lookup (scope-bypass impossible)', 'Step 10 hash-chained audit = tamper-evident', 'Step 11 envelope never leaks decoded JWT claims on 401'],
    performance: [
      'Step 2 CB check is in-process (~5µs)',
      'Step 6 scope check is in-process JWT verify (~50µs after key cached)',
      'Step 7 idempotency is one Postgres roundtrip (~2ms)',
      'Step 10 audit write is one Postgres insert (~3ms)',
      'Step 8 handler dominates total latency in healthy state',
    ],
    scaling: ['Steps 5-11 are per-pod; scale horizontally', 'Step 7 + Step 10 are Postgres; partition by tenant for hot paths'],
    monitoring: [
      'Step-level OTel spans named mcp.tool:<step>',
      'tool_calls_total counter labelled by namespace + tool + outcome',
      'tool_call_duration_seconds histogram per step',
      'Step 11 outcome: success / replayed / draft / scope_denied / handler_error',
    ],
    alternatives: [
      { name: 'Async tool calls (kafka)', tradeoff: 'No synchronous result; agent loop must poll; more moving parts for the simple case' },
      { name: 'Batched /tools/call', tradeoff: 'Saves RTT; complicates partial failures + idempotency semantics' },
    ],
    maturity: {
      mvp: 'Steps 1, 5, 8, 11 (intent → server → handler → return)',
      production: 'All 11 steps + drills',
      enterprise: 'Step 4 multi-region routing; step 7 multi-region idempotency reconciliation',
    },
    limitations: ['Synchronous request-response by design — async batched tool calls are out of scope', 'Step 7 + Step 10 Postgres writes are the throughput ceiling for sustained load'],
    projectFit: ['§47.2 C4 sequence diagram (this flow IS the L3 component sequence)', '§43 drill catalog (one drill per step)', '§48 decision audit row captures the 11 steps'],
    interviewLine: 'A tool call is 11 named steps. Each step has a span, a metric, a failure mode, a drill. Step 6 (scope) runs BEFORE step 7 (idempotency) — leaked-key scope-bypass is impossible. Step 10 (audit) is fail_closed — uncaptured side-effects do not happen. The flow IS the contract; the drills ARE the gate.',
  },
];

export default function MCPDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">MCP deep dive — universal interview framework</h1>
          <p className="page-subtitle">
            Model Context Protocol — server (per-namespace tool host),
            client (breaker + draft fallback), feature surface, architecture,
            every component, end-to-end flow. Six topics through the
            universal interview framework.
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
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/tracing/deep', label: 'CompositePropagator + baggage', why: 'mcp/server_common wires the propagator + httpx auto-instrumentation; every MCP server inherits' },
          { href: '/admin/security/deep#owasp-stride-ai-threats', label: 'A15 excessive agency', why: 'tool-call scope check + scope-deny audit = the excessive-agency control; required_scopes per tool' },
          { href: '/admin/ai-orchestration/deep', label: 'MCP servers as workers', why: 'orchestrator (planner) → MCP servers (workers); plan + tool sequence audit row composes' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Drill discipline (§43)', why: 'every MCP server ships drill_*.py; commits without drill blocked; resource-tag scheduler' },
          { href: '/admin/post-release/deep', label: 'Scope-deny in PDV', why: 'scope-deny rate is a golden signal; spike triggers investigate (auth bypass attempt or stale scopes)' },
        ]}
      />
    </>
  );
}
