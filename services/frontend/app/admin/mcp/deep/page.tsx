'use client';

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
];

export default function MCPDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">MCP deep dive — universal interview framework</h1>
          <p className="page-subtitle">
            Model Context Protocol primitives — server (per-namespace tool host)
            + client (breaker + draft fallback) — explained through the
            20-dimension template.
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
