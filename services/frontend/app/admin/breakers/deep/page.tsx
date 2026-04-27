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
    implementationSteps: [
      { step: 'State machine', logic: 'closed → open (N fails) → half_open (recovery_timeout) → closed (probe success).' },
      { step: 'Tunable per name', logic: 'threshold + recovery_timeout + half_open_max_calls per dependency.' },
      { step: 'Observable state', logic: 'Prometheus gauge per breaker; alert if open > N minutes.' },
      { step: 'Probe coordination', logic: 'half_open allows limited concurrent probes; one success → closed.' },
      { step: 'Operator dashboard', logic: 'Real-time breaker state visualisation in /admin/breakers.' },
      { step: 'Force-closed escape hatch', logic: 'Admin manual override for stuck CB after config fix.' },
      { step: 'Drill state machine', logic: '4-step drill: closed → open → half_open → closed transitions all asserted.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/circuit_breaker.py — generic state machine
import time
from enum import Enum
from threading import Lock

class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5,
                 recovery_timeout: float = 30.0,
                 half_open_max_calls: int = 3):
        self.name = name
        self._threshold = threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max_calls
        self._state = State.CLOSED
        self._failures = 0
        self._half_open_calls = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._state == State.CLOSED:
                return True
            if self._state == State.OPEN:
                if (time.time() - (self._opened_at or 0)) >= self._recovery_timeout:
                    self._state = State.HALF_OPEN
                    self._half_open_calls = 0
                    return True
                return False  # fast-fail
            # HALF_OPEN
            if self._half_open_calls < self._half_open_max:
                self._half_open_calls += 1
                return True
            return False

    def record_success(self):
        with self._lock:
            self._failures = 0
            if self._state == State.HALF_OPEN:
                self._state = State.CLOSED
                breaker_state.labels(name=self.name).set(0)

    def record_failure(self):
        with self._lock:
            self._failures += 1
            if self._state == State.HALF_OPEN:
                self._state = State.OPEN
                self._opened_at = time.time()
                breaker_state.labels(name=self.name).set(2)
            elif self._state == State.CLOSED and self._failures >= self._threshold:
                self._state = State.OPEN
                self._opened_at = time.time()
                breaker_state.labels(name=self.name).set(2)

    @property
    def state(self) -> State:
        return self._state`,
    },
    realUseCase: 'Qdrant pod OOM-killed during a traffic spike. Without the breaker, every retrieval-svc call would have piled up on the dead transport, exhausted the asyncpg pool, and taken inference-svc down too. The breaker opened after 5 fails (~2s of timeouts), fast-failed for 30s, then probed in half_open. New Qdrant pod came up; probe succeeded; breaker closed. Total user-visible impact: ~30s of degraded responses with degraded=true honestly returned.',
    prosCons: {
      pros: [
        'Fast-fail prevents cascading failure',
        'State observable via gauge; alerting trivial',
        'Tunable per-dependency thresholds',
        'Half-open auto-recovery; no manual intervention',
      ],
      cons: [
        'Per-process state — multi-replica view fragmented',
        'Threshold tuning needs production data',
        'Probe storms possible if half_open_max too high',
        'Slow-not-failing deps need timeout discipline',
      ],
    },
    comparison: {
      left: 'Plain retry with backoff',
      right: 'Circuit breaker (this)',
      rows: [
        { aspect: 'Fast-fail on outage', left: 'Never — every call retries', right: 'Immediate while open' },
        { aspect: 'Operator visibility', left: 'Logs only', right: 'Per-name gauge + alerts' },
        { aspect: 'Auto-recovery', left: 'N/A', right: 'half_open probe' },
        { aspect: 'Storm prevention', left: 'Backoff helps but doesn\'t prevent', right: 'Open state caps load' },
      ],
    },
    solutions: [
      { problem: 'Cascading failure from one slow dep', solution: 'CB opens, fast-fails, contains blast radius' },
      { problem: 'Retry storm during outage', solution: 'allow() returns false while open' },
      { problem: 'Stuck-open after config fix', solution: 'Force-closed admin endpoint + alert' },
      { problem: 'Slow-not-failing dep', solution: 'Per-call timeout; treat timeout as CB failure' },
    ],
    bestPractices: {
      do: [
        'One breaker per (caller, target) pair',
        'Tune threshold + recovery_timeout per dep',
        'Wrap retries inside allow() — never bypass',
        'Gauge per breaker; alert on open > N min',
        'Drill state machine transitions',
      ],
      avoid: [
        'Single global CB across all deps',
        'Bypassing CB for "important" calls',
        'Hardcoded thresholds across deps',
        'Half-open with no probe limit',
      ],
      optimize: [
        'Cluster-wide state via Redis (ADR-016)',
        'Per-tenant breakers for blast radius isolation',
        'Auto-tuning thresholds from observed p95',
      ],
    },
    antiPatterns: [
      'No CB at all (cascading failure)',
      'Single global CB (one bad dep kills everything)',
      'Retry that bypasses allow()',
      'No timeout on calls (slow dep never trips CB)',
      'No alerting on open state',
    ],
    testTypes: [
      'Drill: closed → open after N consecutive failures',
      'Drill: open → half_open after recovery_timeout',
      'Drill: half_open → closed on probe success',
      'Drill: half_open → open on probe failure',
      'Drill: gauge correctness (state observable)',
    ],
    testScenarios: [
      { scenario: '5 consecutive failures', expected: 'Breaker transitions closed → open' },
      { scenario: 'Wait recovery_timeout + 1s', expected: 'Next allow() returns true (half_open)' },
      { scenario: 'Probe call succeeds', expected: 'Breaker → closed, gauge=0' },
      { scenario: 'Probe call fails', expected: 'Breaker → open immediately, gauge=2' },
    ],
    testData: [
      { type: 'Stub dependency', example: 'Toggleable failure mode for drill_breaker_transitions' },
      { type: 'Threshold sweep fixture', example: '5/10/20 failures × 30/60s recovery × measure trip latency' },
    ],
    debuggingChecklist: [
      'CB never opens? Threshold too high or fail-record path broken',
      'CB stuck open? recovery_timeout elapsed but probe path broken',
      'CB flapping? Threshold too low; tighten or add hysteresis',
      'Gauge reads wrong? breaker_state.labels not updated on transition',
    ],
    productionIssues: [
      { issue: 'Multi-replica replicas had divergent CB state', rootCause: 'Per-process state; one replica saw failures, others didn\'t. ADR-016 plans Redis-coordinated state.' },
      { issue: 'CB never tripped despite consistent failures', rootCause: 'Retries bypassed allow() — went directly to dependency; failures recorded but threshold never breached because of stale counter.' },
    ],
    performance: [
      'allow(): O(1), ~0.5μs (lock + state check)',
      'record_failure / record_success: O(1) + lock',
      'No I/O; pure in-process state machine',
    ],
    costConsiderations: [
      'Compute: negligible',
      'Gauge cardinality: 1 series per breaker name',
      'Cluster-wide state (Redis): ~$10/mo for shared infra',
    ],
    observability: [
      'Trace: per-call breaker decision + state',
      'Metrics: breaker_state{name}, transitions_total{from,to,name}',
      'Logs: structured on every transition with reason',
      'Audit: not required (non-sensitive)',
    ],
    metrics: [
      { name: 'documind_circuit_breaker_state{name}', example: 'Gauge: 0=closed, 1=half, 2=open; alert if open > 5min' },
      { name: 'documind_circuit_breaker_failures{name}', example: 'Counter; spike means upstream dep is failing' },
      { name: 'documind_circuit_breaker_transitions_total{from,to,name}', example: 'Counter; flapping = oscillation' },
    ],
    tradeoffs: [
      { decision: 'Per-process vs cluster-wide state', tradeoff: 'Process is simple; cluster is consistent but adds Redis dep' },
      { decision: 'Threshold tightness', tradeoff: 'Tight = fast-fail but more flapping; loose = stable but slower trip' },
      { decision: 'half_open_max_calls', tradeoff: 'High = faster recovery; low = avoids probe storm' },
    ],
    decisionMatrix: [
      { option: 'Generic CB (this)', whenToUse: 'Any external dep; simple state needed' },
      { option: 'Hystrix-style bulkhead', whenToUse: 'Need concurrency limits + thread isolation' },
      { option: 'Service-mesh CB (Istio)', whenToUse: 'Operator-managed; per-route granularity' },
    ],
    starStory: {
      situation: 'Initial impl had per-call try/except + retries; one slow Qdrant pod cascaded into a 30-min platform outage.',
      task: 'Fast-fail without manual intervention; observable state for ops.',
      action: 'Wrote CircuitBreaker class with closed/open/half_open. Wrapped all retrieval transports. Added per-name Prometheus gauge. drill_breaker_transitions locks state machine.',
      result: 'Next Qdrant outage: 30s degraded responses, no platform-wide cascade. Pattern unified in ADR-002 across 3 services.',
    },
    interviewTraps: [
      'Saying "we use circuit breakers" without specifying per-(caller,target) granularity',
      'Bypassing allow() for "important" calls',
      'No timeout — slow dep never trips CB',
      'No alerting on open state — operators don\'t know',
    ],
    finalScript: 'A circuit breaker is the smallest piece of code that turns a hard dependency into a soft one. State machine: closed → open after N consecutive failures, open → half_open after recovery_timeout, half_open → closed on probe success or back to open on probe failure. One breaker per (caller, target) pair, tuned per dependency, observable via Prometheus gauge, alerted on extended open state. Retries go THROUGH allow(), never around. Per-process state today; cluster-wide via Redis is ADR-016. Drill verifies all four state-machine transitions.',
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
    implementationSteps: [
      { step: 'Spawn parallel calls', logic: 'vector_breaker, graph_breaker, cache — all in flight simultaneously.' },
      { step: 'Each path gates on its own CB', logic: 'allow()? per transport; fast-fail if open.' },
      { step: 'Aggregate from healthy paths', logic: 'Reciprocal-rank fuse vector + graph + cache results.' },
      { step: 'Mark response degraded', logic: 'If ANY transport breaker was open, set degraded=True.' },
      { step: 'Caller honors degraded flag', logic: 'inference-svc adds "partial answer" disclaimer.' },
      { step: 'Audit per request_id', logic: 'Log which transports were available + final degraded state.' },
      { step: 'Drill the degraded envelope', logic: 'Kill one transport; assert chunks returned + degraded=true.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/inference-svc/app/services/hybrid_retriever.py
from libs.py.documind_core.circuit_breaker import CircuitBreaker

vector_breaker = CircuitBreaker("qdrant_transport", threshold=5, recovery_timeout=30)
graph_breaker = CircuitBreaker("neo4j_transport", threshold=5, recovery_timeout=30)

@dataclass
class RetrieveResponse:
    chunks: list[Chunk]
    degraded: bool  # True = partial coverage; agent must disclaim
    sources_used: list[str]

async def hybrid_retrieve(query: str, tenant_id: str) -> RetrieveResponse:
    sources = []
    chunks = []
    degraded = False

    # Vector path
    if vector_breaker.allow():
        try:
            v_chunks = await qdrant.search(query, tenant_id, top_k=20)
            sources.append("vector")
            chunks.extend(v_chunks)
            vector_breaker.record_success()
        except Exception:
            vector_breaker.record_failure()
            degraded = True
    else:
        degraded = True  # CB open — vector path skipped

    # Graph path
    if graph_breaker.allow():
        try:
            g_chunks = await neo4j.traverse(query, tenant_id, depth=2)
            sources.append("graph")
            chunks.extend(g_chunks)
            graph_breaker.record_success()
        except Exception:
            graph_breaker.record_failure()
            degraded = True
    else:
        degraded = True

    # Cache always tried
    c_chunks = await redis_cache.lookup(query, tenant_id)
    if c_chunks:
        sources.append("cache")
        chunks.extend(c_chunks)

    fused = reciprocal_rank_fuse(chunks)[:5]
    return RetrieveResponse(chunks=fused, degraded=degraded, sources_used=sources)`,
    },
    realUseCase: 'Neo4j upgrade caused a 2-minute outage. Without per-transport CBs, every retrieval would have piled up on Neo4j. With them: graph_breaker opened after ~5s, vector + cache served alone, responses returned with degraded=true. Inference-svc added "partial answer (graph context unavailable)" disclaimer to user. Total user-facing impact: 2 min of explicitly-degraded answers vs full outage.',
    prosCons: {
      pros: [
        'Per-transport blast radius isolation',
        'Graceful degradation vs full outage',
        'degraded=true contract makes partial answers honest',
        'Healthy transports unaffected by one broken peer',
      ],
      cons: [
        'Aggregation must handle missing-source case',
        'degraded flag must propagate through inference-svc honestly',
        'Per-transport tuning needed (different latency profiles)',
      ],
    },
    comparison: {
      left: 'Single global retrieval CB',
      right: 'Per-transport CBs (this)',
      rows: [
        { aspect: 'One transport down', left: 'Whole retrieval path opens', right: 'Only that transport\'s path skipped' },
        { aspect: 'Aggregation honesty', left: 'Implicit — caller can\'t tell', right: 'Explicit degraded=true' },
        { aspect: 'Recovery granularity', left: 'All-or-nothing', right: 'Per-transport independent' },
        { aspect: 'User experience', left: '503 retry', right: '"Partial answer" disclaimer' },
      ],
    },
    solutions: [
      { problem: 'One transport drags total latency', solution: 'Per-transport CB fast-fails the slow one' },
      { problem: 'Silent quality degradation', solution: 'degraded=true on response envelope' },
      { problem: 'Cascading retrieval failure', solution: 'Per-transport blast radius = one transport' },
    ],
    bestPractices: {
      do: [
        'One CB per transport (not per service)',
        'degraded=true on partial coverage',
        'Inference-svc honors degraded flag with disclaimer',
        'Per-transport timeout treated as failure',
      ],
      avoid: [
        'Single global retrieval CB',
        'Dropping the degraded flag from inference response',
        'Letting one transport drag total latency without timeout',
      ],
      optimize: [
        'Parallel-fetch from all healthy transports',
        'Cache fills gaps when transport CBs open',
        'Per-transport quality scoring for graceful weighting',
      ],
    },
    antiPatterns: [
      'Single CB for all retrieval transports',
      'Dropping degraded flag at inference layer',
      'No timeout on slow transports',
      'Letting CB-open path silently return empty',
    ],
    testTypes: [
      'Drill: kill Qdrant → vector_breaker opens, graph + cache serve',
      'Drill: degraded=true returned when ANY transport unavailable',
      'Drill: all transports up → degraded=false',
      'Drill: all transports down → empty chunks + degraded=true',
    ],
    testScenarios: [
      { scenario: 'Qdrant healthy, Neo4j down', expected: 'chunks from vector + cache; degraded=true' },
      { scenario: 'All transports healthy', expected: 'chunks from all; degraded=false' },
      { scenario: 'Both Qdrant + Neo4j open', expected: 'chunks from cache only; degraded=true' },
      { scenario: 'All open including cache', expected: 'empty chunks; degraded=true; agent says "no info"' },
    ],
    testData: [
      { type: 'Toxiproxy fixture', example: 'In front of Qdrant; toggleable failure mode' },
      { type: 'Multi-source corpus', example: 'Same query findable in vector + graph + cache; coverage measurable' },
    ],
    debuggingChecklist: [
      'degraded=false but answer wrong? Verify all transports actually hit',
      'Inference-svc not disclaiming? degraded flag dropped between retrieval + inference',
      'CB never opens for a transport? Per-transport timeout missing',
    ],
    productionIssues: [
      { issue: 'Inference response missed degraded disclaimer', rootCause: 'New inference-svc version dropped the field. Drill caught at PR.' },
      { issue: 'All retrievals returned degraded=true', rootCause: 'Toxiproxy left enabled in staging; vector_breaker opened in prod by misconfig.' },
    ],
    performance: [
      'Parallel fan-out: latency = max(vector, graph, cache) ~ 80ms p95',
      'CB-open path: ~5ms (immediate fast-fail)',
      'Aggregation: ~10ms (reciprocal rank fuse top-20)',
    ],
    costConsiderations: [
      'No additional cost beyond underlying transports',
      'CB state: per-process; cluster-wide is ADR-016',
    ],
    observability: [
      'Trace: per-request transport decisions + outcomes',
      'Metrics: per-transport breaker state, degraded response rate',
      'Logs: structured with sources_used + degraded flag',
    ],
    metrics: [
      { name: 'documind_retrieval_degraded_total{tenant}', example: 'Counter; rate spike means transport problem' },
      { name: 'documind_circuit_breaker_state{name="qdrant_transport"}', example: 'Gauge; alert if open > 5min' },
      { name: 'documind_circuit_breaker_state{name="neo4j_transport"}', example: 'Gauge; same alerting' },
      { name: 'documind_retrieval_sources_used{source}', example: 'Counter; per-source coverage tracking' },
    ],
    tradeoffs: [
      { decision: 'Per-transport CB granularity', tradeoff: 'Independent recovery; more CBs to monitor' },
      { decision: 'degraded contract', tradeoff: 'Honest partial answers; clients must handle the flag' },
      { decision: 'Cache as backstop', tradeoff: 'Coverage gap filler; stale-on-write risk' },
    ],
    decisionMatrix: [
      { option: 'Per-transport CB (this)', whenToUse: 'Multi-backend retrieval; graceful degradation needed' },
      { option: 'Single retrieval CB', whenToUse: 'Tightly-coupled deps; one fail = all should fail' },
      { option: 'No CB', whenToUse: 'Single dep with fast timeout' },
    ],
    starStory: {
      situation: 'Neo4j upgrade caused a 2-minute outage; without per-transport CBs, retrieval would have stalled fully.',
      task: 'Graceful degradation that honestly tells users when context is partial.',
      action: 'Implemented vector_breaker + graph_breaker. Added degraded=true contract to RetrieveResponse. Inference-svc honors flag with "partial answer" disclaimer. drill_retrieval_transport_breaker locks the discipline.',
      result: 'Next Neo4j hiccup: vector + cache served, degraded=true, users got partial answers (with disclaimer). Zero pages. ADR-008 documents the contract.',
    },
    interviewTraps: [
      'Single-CB-fits-all retrieval (one transport down kills everything)',
      'Dropping the degraded flag at inference (silent quality regression)',
      'No per-transport timeout (slow path never trips CB)',
    ],
    finalScript: 'Per-transport circuit breakers turn a brittle multi-backend retrieval into graceful degradation. Vector and graph each get their own breaker. When one opens, the other transports + cache continue serving. The response carries degraded=true on its envelope, and inference-svc honors that by adding a "partial answer" disclaimer. ADR-008 binds this contract; drill_retrieval_transport_breaker proves it. The user sees "partial answer" instead of "503 retry" — and that\'s the difference between an enterprise tool and a demo.',
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
