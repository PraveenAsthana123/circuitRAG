'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'mcp-server',
    title: '1. MCP server (per-namespace tool host)',
    status: 'shipped',
    coreConcept: 'Each MCP server hosts a namespaced set of tools (hr.*, itsm.*, drill.*) behind a uniform /tools/list + /tools/call HTTP contract — scoped, idempotent, observable.',
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
