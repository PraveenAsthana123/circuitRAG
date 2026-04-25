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
