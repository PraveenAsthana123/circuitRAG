'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'generic-cb',
    title: '1. Generic Circuit Breaker',
    status: 'shipped',
    coreConcept: 'A state machine (closed → open → half_open → closed) wrapping any external dependency, fast-failing while open so cascading failures don\'t take the whole system down.',
    problem: 'External dependencies fail. Without a breaker, every caller times out, exhausts pools, and amplifies the outage into a self-DoS.',
    whyThisApproach: 'Closed/open/half_open states give explicit fail-fast + probe behaviour, observable per-name, with thresholds tunable per dependency.',
    whenToUse: ['Every external HTTP / DB / queue dependency', 'Anywhere retry storms can amplify outages', 'Unhealthy dep detection without manual intervention'],
    whenNotToUse: ['Single-process in-memory ops (no failure mode)', 'Local computation', 'Sub-millisecond hot loops (CB overhead matters)'],
    input: 'name + threshold + recovery_timeout + half_open_max_calls',
    process: [
      'allow() → check state; if open, fast-fail',
      'On call success: record_success → reset failure counter; if half_open → closed',
      'On call failure: record_failure → increment counter; threshold breach → open',
      'After recovery_timeout in open: transition to half_open',
      'half_open: limited probes; success → closed, failure → open',
    ],
    output: 'Allow/deny decision + observable state + Prometheus gauge.',
    flowchart: `flowchart LR
  c[CLOSED] -->|N consecutive fails| o[OPEN]
  o -->|recovery_timeout elapsed| h[HALF_OPEN]
  h -->|probe success| c
  h -->|probe failure| o
  o -.allow false.-> r[Caller fast-fails]
  c -.allow true.-> p[Caller proceeds]
  h -.limited probes.-> p`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Caller
  participant CB as CircuitBreaker
  participant Dep as Dependency
  Cli->>CB: allow()?
  CB-->>Cli: true (CLOSED)
  Cli->>Dep: call
  Dep-->>Cli: error
  Cli->>CB: record_failure
  CB->>CB: failures += 1; if >= threshold: state=OPEN
  Note over Cli,CB: ... time passes; recovery_timeout elapsed ...
  Cli->>CB: allow()?
  CB-->>Cli: true (HALF_OPEN, probe slot)
  Cli->>Dep: call
  Dep-->>Cli: success
  Cli->>CB: record_success
  CB->>CB: state=CLOSED`,
    alternatives: [
      { name: 'Plain retry with backoff', tradeoff: 'No fast-fail; storms during outages; no operator visibility' },
      { name: 'Hystrix-style bulkhead', tradeoff: 'More features (concurrency limits); heavier; JVM-centric' },
      { name: 'Service-mesh CB (Istio)', tradeoff: 'Operator-controlled; less granular per-call; mesh prerequisite' },
    ],
    challenges: [
      'Threshold tuning per dependency',
      'Half-open probe coordination across replicas',
      'Per-process state — multi-replica fragmentation',
      'Differentiating transient vs persistent failure',
    ],
    edgeCases: [
      { case: 'Single bad replica trips CB across whole fleet', solution: 'Per-instance breaker; investigate replica health separately' },
      { case: 'CB stuck open due to permanent config issue', solution: 'Manual force-closed via admin; alert if open > N minutes' },
      { case: 'Retries fighting CB (counted as fresh attempts)', solution: 'Retry MUST go through allow(); never bypass' },
      { case: 'Slow-but-not-failing dep', solution: 'Add timeout; treat timeout as failure for CB purposes' },
    ],
    failureModes: [
      { mode: 'CB never opens', detect: 'failure_count rising but state=closed', recover: 'Threshold mistuned; lower or check fail-record path' },
      { mode: 'CB never closes', detect: 'state=half_open or open for > recovery × 2', recover: 'Probe path broken; investigate' },
      { mode: 'Per-process state diverges', detect: 'Some replicas open, others closed for same dep', recover: 'Cluster-wide state via Redis (ADR-016 planned)' },
    ],
    monitoring: [
      'documind_circuit_breaker_state{name} (0=closed,1=half,2=open)',
      'documind_circuit_breaker_failures{name}',
      'transition counter per (from→to)',
      '/admin Operator Dashboard breakers panel',
    ],
    testing: [
      'drill_breaker_transitions (4 steps closed→open→half→closed)',
      'drill_multi_breaker_visibility (per-namespace state on dashboard)',
      'drill_prometheus_breakers (gauge correctness)',
    ],
    security: ['Breaker state is non-sensitive', 'Per-tenant breakers if blast radius matters', 'No PII in breaker labels'],
    scaling: [
      '10x: per-process is fine for single-instance services',
      '100x: shared state via Redis for consistent multi-replica view',
      'Cost driver: gauge cardinality (one series per breaker name)',
    ],
    maturity: {
      mvp: 'Per-call try/except retry — no breaker yet',
      production: 'CircuitBreaker class with closed/open/half_open + Prometheus gauge',
      enterprise: 'Cluster-coordinated state (Redis); per-tenant breakers; rich operator dashboard',
    },
    limitations: [
      'Per-process state in current impl',
      'Threshold is global per breaker (not per-tenant)',
      'No automated tuning from observed traffic',
    ],
    projectFit: [
      'libs/py/documind_core/circuit_breaker.py — unified CB',
      'ADR-002 — single canonical CircuitBreaker (post unification)',
      'breaker_state gauge in /admin dashboard',
      'drill_breaker_transitions locks state machine',
    ],
    interviewLine: 'A circuit breaker is the smallest piece of code that turns a hard dependency into a soft one. Without it, one slow upstream takes down the whole platform.',
  },
  {
    slug: 'transport-cb',
    title: '2. Transport CB (Qdrant + Neo4j)',
    status: 'shipped',
    coreConcept: 'Per-backend breaker around the retrieval transports — Qdrant + Neo4j — so a misbehaving vector or graph backend doesn\'t cascade to the whole RAG path.',
    problem: 'RAG retrieval calls multiple backends (vector + graph + cache). Without per-backend breakers, one slow backend drags total latency past the user\'s budget; without fast-fail, the slow backend becomes a self-amplifying problem.',
    whyThisApproach: 'Per-transport breakers fail fast on the bad backend while letting healthy ones serve. The retrieval layer marks the response degraded=True so callers know.',
    whenToUse: ['RAG retrieval with multiple parallel transports', 'Hybrid search (vector + graph)', 'Any service with N independent dependency paths'],
    whenNotToUse: ['Single-dependency services (one breaker is enough)', 'Tightly coupled deps where one failing means all should fail'],
    input: 'Query + tenant + retrieval config',
    process: [
      'Spawn parallel calls: vector_breaker + graph_breaker + cache',
      'Each path independently fast-fails if its breaker is open',
      'Collect results from healthy paths',
      'Mark response degraded=True if ANY transport breaker was open',
      'Caller sees explicit degradation signal',
    ],
    output: 'RetrieveResponse(chunks, degraded=bool) — degraded=True means partial coverage.',
    flowchart: `flowchart LR
  q[Query] --> v{vector_breaker allow?}
  q --> g{graph_breaker allow?}
  q --> c[Cache lookup]
  v -->|yes| vc[Qdrant ANN search]
  v -->|no| vd[Skip vector path]
  g -->|yes| gc[Neo4j traversal]
  g -->|no| gd[Skip graph path]
  vc --> agg[Aggregate]
  vd --> agg
  gc --> agg
  gd --> agg
  c --> agg
  agg --> r[Return chunks + degraded=if-any-skipped]`,
    sequence: `sequenceDiagram
  autonumber
  participant Inf as inference-svc
  participant Ret as retrieval-svc
  participant VB as vector_breaker
  participant Q as Qdrant
  participant GB as graph_breaker
  participant N as Neo4j
  Inf->>Ret: retrieve(query, tenant)
  Ret->>VB: allow()?
  VB-->>Ret: yes
  Ret->>Q: ANN search
  Q-->>Ret: chunks
  Ret->>GB: allow()?
  GB-->>Ret: no (open)
  Note over Ret: Skip graph path, mark degraded
  Ret-->>Inf: chunks + degraded=true
  Inf->>Inf: assemble prompt with available context
  Inf-->>Inf: response includes degradation note`,
    alternatives: [
      { name: 'Single global retrieval CB', tradeoff: 'One bad backend kills all paths; loses parallel benefit' },
      { name: 'No CB, just timeout', tradeoff: 'Slow path drags total latency; no fast-fail' },
      { name: 'Service mesh CB only', tradeoff: 'Mesh-level granularity; harder to tie to RetrieveResponse contract' },
    ],
    challenges: [
      'Per-transport threshold tuning',
      'Communicating "degraded" honestly to user',
      'Avoiding silent quality degradation',
    ],
    edgeCases: [
      { case: 'All transports open simultaneously', solution: 'Return empty chunks with degraded=true; agent assembles "no info" answer' },
      { case: 'Cache hot but vector cold-broken', solution: 'Cache fills the gap; user sees no degradation' },
      { case: 'Neo4j slow but not failing', solution: 'Per-call timeout treated as CB failure' },
    ],
    failureModes: [
      { mode: 'Transport breaker stuck open', detect: 'breaker_state{name=qdrant_transport}=open > 5min', recover: 'Manual probe or restart retrieval-svc' },
      { mode: 'Degraded flag dropped', detect: 'drill_retrieval_degraded_envelope red', recover: 'Revert; restore degraded=true contract' },
    ],
    monitoring: [
      'breaker_state per transport (vector, graph)',
      'retrieval-svc degraded response rate',
      'Per-transport latency histogram',
    ],
    testing: [
      'drill_retrieval_transport_breaker (kill transport → CB opens)',
      'drill_retrieval_degraded_envelope (degraded=true on partial coverage)',
    ],
    security: ['Breaker scope per transport, not per tenant', 'No leakage across transports'],
    scaling: ['Already parallel; CB is local; scales linearly with retrieval-svc replicas'],
    maturity: {
      mvp: 'Single combined retrieval call; no per-transport CB',
      production: 'Per-transport breakers + degraded envelope (this commit)',
      enterprise: 'Per-tenant transport CB + cluster-coordinated state',
    },
    limitations: [
      'Local breaker state per replica',
      'No automated transport-quality scoring',
    ],
    projectFit: [
      'services/inference-svc/app/services/hybrid_retriever.py — vector_breaker + graph_breaker',
      'ADR-008 — transport breakers',
      'drill_retrieval_transport_breaker',
      'drill_retrieval_degraded_envelope',
    ],
    interviewLine: 'Per-transport breakers turn a brittle fan-out into a graceful degradation. The user sees "partial answer" instead of "503 retry" — and that\'s the difference between an enterprise tool and a demo.',
  },
];

export default function BreakersDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Circuit Breakers deep dive</h1>
          <p className="page-subtitle">
            Generic state-machine CB + per-transport CB for RAG retrieval — both
            explained through the universal 20-dimension framework.
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
