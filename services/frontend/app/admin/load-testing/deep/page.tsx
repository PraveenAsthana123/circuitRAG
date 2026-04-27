'use client';

/**
 * Load testing (deep dive).
 *
 * Three topics: k6 + JMeter multi-phase strategy; RAG / AI-specific
 * load testing + breakpoint analysis; performance tuning + outage
 * case study playbook.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — k6 + JMeter multi-phase
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'k6-jmeter-multi-phase',
    title: '1. k6 + JMeter — multi-phase load testing (smoke / load / stress / soak / spike)',
    status: 'shipped',
    coreConcept:
      'Load testing is a system validation exercise, not a single benchmark. Run it in five phases: smoke (sanity, 1–10 VU), load (target SLA, e.g. 500 VU), stress (1.5–2× target until failure), soak (24h endurance for memory leaks), spike (sudden 0→peak to test elasticity). k6 = developer-first JS scripting + Prometheus output; JMeter = enterprise GUI + protocol coverage (JDBC, JMS, gRPC). Use both: k6 in CI; JMeter for legacy + complex protocol tests.',
    oneLiner: 'Smoke → Load → Stress → Soak → Spike. k6 for code; JMeter for protocols.',
    businessContext:
      'A new release moves p95 from 300 ms to 1.2 s under 500 VU. Without phased load testing this only surfaces in production at peak hour. Phased testing catches it pre-deploy + reveals the breakpoint (VUs at which p95 violates SLA).',
    fiveW: {
      what: 'Five-phase load test methodology executed via k6 (scripted, CI-integrated) + JMeter (GUI, distributed, multi-protocol).',
      why: 'Single load test only proves "works at X". Phased testing proves "scales to Y, fails gracefully at Z, doesn\'t leak after W hours".',
      where: 'CI/CD (smoke + load) + dedicated load env (stress + soak + spike).',
      when: 'Pre-release (load + stress), monthly (soak), pre-Black-Friday (spike).',
      who: 'Performance engineer + SRE + dev team.',
    },
    interview30s:
      'I treat load testing as system validation, not just performance. I run smoke / load / stress / soak / spike against a prod-like env. k6 in CI for fast feedback; JMeter for complex protocol mixes. I capture p50/p95/p99, error rate, throughput, resource saturation. I correlate with traces + DB metrics to find the bottleneck — slow query, missing index, lock contention, GC pressure, network. Breakpoint = the VU count where SLA breaks. That number drives capacity planning.',
    hld: `flowchart LR
  A[CI smoke 10 VU] --> B[Load 500 VU 30 min]
  B --> C[Stress 0 to 2000 VU]
  C --> D[Soak 500 VU 24h]
  D --> E[Spike 0 to 1500 VU 60s]
  B --> M[Prometheus + Grafana]
  C --> M
  D --> M
  E --> M
  M --> R[Report breakpoint + SLA + leak]`,
    flowchart: `flowchart TD
  Start[Start load test] --> Smoke{Smoke pass?}
  Smoke -- no --> FailEarly[Fail CI early]
  Smoke -- yes --> Load[Load test target SLA]
  Load --> StressQ{Within SLA?}
  StressQ -- no --> Tune[Tune + rerun]
  StressQ -- yes --> Stress[Stress to breakpoint]
  Stress --> Soak[Soak 24h]
  Soak --> Leak{Memory growth?}
  Leak -- yes --> FixLeak[Fix leak]
  Leak -- no --> Spike[Spike test elasticity]
  Spike --> Report[Capacity + SLA report]`,
    sequence: `sequenceDiagram
  participant CI
  participant K6
  participant App
  participant Prom as Prometheus
  participant Graf as Grafana
  CI->>K6: trigger smoke 10 VU
  K6->>App: requests
  App-->>K6: 200 OK + latency
  K6->>Prom: push metrics
  CI->>K6: trigger load 500 VU
  K6->>App: ramp up
  App->>Prom: CPU, mem, queue depth
  Prom->>Graf: dashboards
  Graf-->>CI: breakpoint + p95`,
    coreLayers: [
      { layer: 'Generator', responsibility: 'k6 / JMeter / Locust nodes producing virtual users.' },
      { layer: 'Target', responsibility: 'Prod-like env: same instance type, network topology, DB size.' },
      { layer: 'Telemetry', responsibility: 'OTel traces + Prometheus + APM agent on every layer.' },
      { layer: 'Analysis', responsibility: 'Grafana + breakpoint + flame graphs + slow-query log.' },
      { layer: 'Report', responsibility: 'Capacity number + SLA pass/fail + tuning backlog.' },
    ],
    lld: `classDiagram
  class K6Script {
    +options: stages[]
    +default(http.get)
    +thresholds: p95 lt 500ms
  }
  class JMeterPlan {
    +ThreadGroup
    +HTTPRequest
    +Listeners
    +DistributedSlaves[]
  }
  class Telemetry {
    +Prometheus
    +Grafana
    +OTel`,
    coreBuildingBlocks: [
      'k6: virtual users, scenarios, executors (constant-vus, ramping-vus, constant-arrival-rate), thresholds',
      'JMeter: thread group, HTTP/JDBC/gRPC samplers, distributed master + slaves, listeners',
      'CI integration: smoke gate fails build if p95 violated; full suite nightly',
      'Prod-like env: same DB size, cache state, network latency, instance class',
      'Five phases: smoke, load, stress, soak, spike — each with its own pass criteria',
    ],
    architectureRelevance: {
      backend: 'Validates SLA + finds breakpoint per service.',
      rag: 'Critical: RAG has embedder + vector + LLM bottlenecks compounding.',
      ai: 'Token throughput, GPU sat, batch size all show up only under load.',
      microservices: 'Cascade failures + saturation + retry storms surface only under load.',
    },
    problem: 'Releases move performance silently. Production p95 spikes 4× under peak. No data on capacity, breakpoint, leaks.',
    whyThisApproach:
      'Phased testing separates SLA validation from capacity discovery from leak hunt from elasticity. One test cannot do all four.',
    whenToUse: [
      'Pre-release validation',
      'Capacity planning before scaling event',
      'Black Friday / launch day prep',
      'After major refactor or DB schema change',
    ],
    whenNotToUse: [
      'Greenfield with no prod traffic to model',
      'Static-only sites with CDN-only delivery',
      'Pure batch / cron systems (use throughput tests instead)',
    ],
    input: 'k6 script or JMeter plan + prod-like env + telemetry stack.',
    process: [
      'Phase 1: Smoke 1–10 VU → assert no errors',
      'Phase 2: Load 500 VU steady → assert p95 < 500 ms',
      'Phase 3: Stress 0→2000 VU ramp → find breakpoint',
      'Phase 4: Soak 500 VU 24h → assert no memory growth > 10%',
      'Phase 5: Spike 0→1500 VU in 60s → assert elasticity recovery < 60s',
      'Aggregate: capacity report + tuning backlog + go/no-go',
    ],
    output: 'Breakpoint VU count, p95/p99 per phase, leak detection result, elasticity recovery time, capacity plan.',
    implementationSteps: [
      { step: 'Pick scenarios', logic: 'Prod-traffic-shape: 70% read, 20% write, 10% admin. Real endpoints from access logs.' },
      { step: 'Write k6 script', logic: 'options.stages defines ramp; thresholds gate CI; tag requests for breakdown.' },
      { step: 'Set up prod-like env', logic: 'Same instance class, DB size, cache warm. No mocks. Same auth.' },
      { step: 'Wire telemetry', logic: 'k6 → Prom; app → OTel; DB → slow query log + pg_stat_statements.' },
      { step: 'Run phases sequentially', logic: 'Smoke gate first; never run stress before load passes.' },
      { step: 'Find breakpoint', logic: 'VU at which p95 > SLA OR error rate > 1% OR resource sat > 80%.' },
      { step: 'Soak overnight', logic: 'Heap growth, FD leaks, connection pool exhaustion only show after hours.' },
      { step: 'Spike test', logic: '0→peak in 60s mimics flash sale. HPA / autoscaler response measured.' },
    ],
    codeExample: {
      language: 'javascript',
      code: `// k6 multi-phase load test
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const latency = new Trend('rag_query_latency');

export const options = {
  scenarios: {
    smoke: {
      executor: 'constant-vus',
      vus: 10,
      duration: '1m',
      tags: { phase: 'smoke' },
    },
    load: {
      executor: 'ramping-vus',
      startVUs: 0,
      startTime: '1m',
      stages: [
        { duration: '5m', target: 500 },
        { duration: '20m', target: 500 },
        { duration: '5m', target: 0 },
      ],
      tags: { phase: 'load' },
    },
    stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      startTime: '32m',
      stages: [
        { duration: '5m', target: 500 },
        { duration: '5m', target: 1000 },
        { duration: '5m', target: 1500 },
        { duration: '5m', target: 2000 },
      ],
      tags: { phase: 'stress' },
    },
  },
  thresholds: {
    'http_req_duration{phase:load}': ['p(95)<500'],
    'http_req_failed{phase:load}': ['rate<0.01'],
    'http_req_duration{phase:stress}': ['p(99)<2000'],
  },
};

export default function () {
  const payload = JSON.stringify({
    query: 'What is rollout strategy?',
    top_k: 5,
  });
  const res = http.post(
    \`\${__ENV.API_URL}/api/v1/rag/query\`,
    payload,
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: \`Bearer \${__ENV.API_TOKEN}\`,
      },
    }
  );
  check(res, {
    'status 200': (r) => r.status === 200,
    'has answer': (r) => JSON.parse(r.body).answer !== undefined,
  });
  latency.add(res.timings.duration);
}`,
    },
    realUseCase:
      'A SaaS team upgrades vector DB. Smoke passes; load (500 VU) passes; stress reveals breakpoint at 1100 VU (was 1800 VU before). Root cause: new HNSW config has slower cold cache. Capacity plan adjusts replica count from 3 to 5 before launch.',
    prosCons: {
      pros: [
        'Catches regressions before prod',
        'Capacity plan grounded in data',
        'Reveals leaks impossible to find in unit tests',
      ],
      cons: [
        'Prod-like env is expensive',
        'Long feedback loop (24h soak)',
        'Test data + auth setup is complex',
      ],
    },
    limitations: [
      'Synthetic traffic ≠ real user diversity',
      'Cache warm state hard to reproduce',
      'Some failures only show at exact prod scale',
    ],
    comparison: {
      left: 'k6',
      right: 'JMeter',
      rows: [
        { aspect: 'Authoring', left: 'JS scripts', right: 'GUI + XML' },
        { aspect: 'Protocols', left: 'HTTP/gRPC/WS', right: 'HTTP/JDBC/JMS/SOAP/FTP/+' },
        { aspect: 'CI integration', left: 'Native Docker', right: 'Plugin-based' },
        { aspect: 'Distributed', left: 'k6 Cloud / Kubernetes', right: 'Master-slave native' },
        { aspect: 'Resource use', left: 'Lower (Go runtime)', right: 'Higher (JVM)' },
        { aspect: 'Learning curve', left: 'Low for devs', right: 'GUI helps non-devs' },
      ],
    },
    challenges: [
      'Test data freshness — stale data masks query plan changes',
      'Auth setup at scale — token refresh, cookie handling',
      'Distributed runs — clock skew, results aggregation, slave health',
      'Network from generator to target must not be the bottleneck',
    ],
    edgeCases: [
      { case: 'Generator CPU saturated', solution: 'Distribute load across N k6 nodes; verify generator < 70% CPU' },
      { case: 'NAT exhaustion (ports run out)', solution: 'Increase ephemeral port range + tune TIME_WAIT' },
      { case: 'Cache hit rate skews results', solution: 'Vary query parameters across VUs; warm cache before steady state' },
      { case: 'Auth token expires mid-test', solution: 'k6 setup() refreshes; share token via __ITER guard' },
    ],
    solutions: [
      { problem: 'Tests too slow to iterate', solution: 'Smoke in CI; full suite nightly; parallelize across regions' },
      { problem: 'Results not actionable', solution: 'Tag every request; break down by endpoint + phase + tenant' },
      { problem: 'Soak finds leaks too late', solution: 'Run soak weekly in staging; never gate release on weekly soak' },
      { problem: 'Capacity number drifts', solution: 'Re-run stress per release; track breakpoint VU as a metric' },
    ],
    bestPractices: {
      do: [
        'Use prod-like env (same instance class, DB size, cache size)',
        'Tag requests by phase + endpoint for breakdown',
        'Capture p50/p95/p99 — not just average',
        'Correlate with traces + DB slow query log',
        'Document breakpoint VU as a release metric',
      ],
      avoid: [
        'Running on dev laptop',
        'Ignoring cache warmup',
        'Single-phase "is it fast" check only',
        'Looking only at average latency',
      ],
      optimize: [
        'CI smoke gate (fast feedback)',
        'Distributed runs for > 5000 VU',
        'Prom + Grafana real-time dashboards during run',
        'Replay from prod traces for traffic shape',
      ],
    },
    antiPatterns: [
      'Load test on shared staging (other tests pollute)',
      'Generator on same network as DB (skews latency)',
      'No telemetry — black-box pass/fail only',
      'Marking "passed" without checking error rate',
    ],
    testing: ['Unit-test k6 scripts via dry run', 'Validate JMeter plan in non-GUI mode', 'Smoke before every full run'],
    testTypes: ['Smoke', 'Load', 'Stress', 'Soak', 'Spike', 'Volume', 'Endurance'],
    testScenarios: [
      { scenario: 'p95 < 500 ms at 500 VU', expected: 'Load phase passes' },
      { scenario: 'Breakpoint at 1500 VU', expected: 'Stress phase: VU at first SLA breach' },
      { scenario: 'No memory growth after 24h soak', expected: 'Heap stable within 10%' },
      { scenario: 'Recover within 60s after spike', expected: 'Spike phase: latency back to baseline' },
    ],
    testData: [
      { type: 'Realistic queries', example: 'Sample 1000 queries from prod access logs' },
      { type: 'Tenant mix', example: '70% small / 20% medium / 10% large tenants' },
      { type: 'Auth tokens', example: 'Pool of 100 service accounts' },
    ],
    debuggingChecklist: [
      'Generator CPU < 70%?',
      'Network from generator < 50% saturated?',
      'DB connection pool not exhausted?',
      'Auth tokens not throttled?',
      'Cache state representative?',
      'Telemetry actually capturing during run?',
    ],
    productionIssues: [
      { issue: 'Test passes but prod fails at same load', rootCause: 'Generator was the bottleneck or env not prod-like' },
      { issue: 'Random p99 spikes', rootCause: 'GC pauses, cold pod startup, or shared neighbor noise' },
      { issue: 'Cannot reproduce flake', rootCause: 'Cache warm state different; vary queries enough' },
    ],
    security: ['Use sandboxed env', 'Never load-test production directly', 'Rotate auth tokens', 'Mask PII in test data'],
    performance: [
      'k6 generator can do ~30k RPS per modest node',
      'JMeter ~5k RPS per slave (JVM heap)',
      'Distribute when single node CPU > 70%',
    ],
    costConsiderations: [
      'Prod-like env: $$$ for instance class match',
      'Soak 24h × replicas × phases gets expensive',
      'k6 Cloud / SaaS load gens for spikes',
    ],
    scaling: ['Horizontal: more k6 nodes / JMeter slaves', 'Vertical: bigger generator instance'],
    observability: ['Prometheus metrics from k6', 'Grafana dashboards live during run', 'OTel traces correlated by request id'],
    metrics: [
      { name: 'p95_latency_ms', example: '420' },
      { name: 'error_rate_percent', example: '0.3' },
      { name: 'requests_per_second', example: '6500' },
      { name: 'breakpoint_vu', example: '1500' },
      { name: 'memory_growth_24h_percent', example: '4' },
    ],
    failureModes: [
      { mode: 'Generator saturation', detect: 'CPU > 70% on generator', recover: 'Add nodes; redistribute scenarios' },
      { mode: 'Test target leak', detect: 'Heap growing during soak', recover: 'Profile; fix code; retest' },
      { mode: 'Connection pool exhaustion', detect: 'errors at high VU only', recover: 'Tune pool size + timeouts' },
      { mode: 'Auth throttle', detect: '429 responses cluster', recover: 'Spread tokens; retry with jitter' },
    ],
    tradeoffs: [
      { decision: 'k6 over JMeter for new', tradeoff: 'JS skill + lower memory; less protocol breadth' },
      { decision: 'Prod-like env always', tradeoff: 'Cost; but smaller env hides issues' },
      { decision: 'Smoke gate in CI', tradeoff: 'Slows CI by 2 min; catches 80% of regressions' },
    ],
    decisionMatrix: [
      { option: 'k6', whenToUse: 'New systems, dev-owned tests, CI integration' },
      { option: 'JMeter', whenToUse: 'Legacy systems, complex protocols (JDBC/JMS), GUI users' },
      { option: 'Locust', whenToUse: 'Python shops, custom logic, distributed' },
      { option: 'Gatling', whenToUse: 'Scala/JVM shops, long soaks' },
    ],
    starStory: {
      situation: 'A team upgraded their RAG vector DB right before Black Friday. No load test.',
      task: 'Validate capacity in 48 hours.',
      action: 'I added k6 multi-phase. Smoke passed; load (500 VU) passed; stress found breakpoint at 1100 VU vs 1800 VU prior. Root cause: HNSW cold cache. We added 2 replicas + warm-up step.',
      result: 'Black Friday peak hit 1400 VU; p95 stayed under 500 ms; zero incidents. Breakpoint became a release-gate metric.',
    },
    interviewTraps: [
      'Saying "we ran a load test" without phases — interviewer drills in',
      'Reporting average latency — should be p95/p99',
      'No mention of soak / leak hunt',
      'Generator on dev laptop — auto-disqualify',
    ],
    finalScript:
      'I run five phases: smoke, load, stress, soak, spike. k6 in CI; JMeter for protocol breadth. Prod-like env mandatory. I track p95/p99, error rate, breakpoint VU. I correlate with OTel + DB metrics to find the bottleneck. Breakpoint becomes a release-gate metric.',
    alternatives: [
      { name: 'Locust', tradeoff: 'Python; great DX; weaker reporting' },
      { name: 'Gatling', tradeoff: 'Scala; long-soak strong; JVM heavy' },
      { name: 'Artillery', tradeoff: 'Node.js; YAML config; CI-native' },
    ],
    monitoring: ['Prometheus during run', 'Grafana annotated with phase boundaries', 'OTel traces sampled at higher rate'],
    maturity: {
      mvp: 'k6 smoke + load only',
      production: 'All five phases + CI smoke gate + prod-like env',
      enterprise: 'Distributed + soak weekly + breakpoint tracked + chaos overlay',
    },
    projectFit: ['CI integration', 'Capacity planning', 'Pre-launch validation', 'Post-incident regression test'],
    interviewLine: 'Five phases. Prod-like env. Breakpoint VU as a release metric.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — RAG / AI-specific load testing
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'rag-ai-load-testing',
    title: '2. RAG + AI load testing — embedder, vector, LLM, breakpoint analysis',
    status: 'shipped',
    coreConcept:
      'AI / RAG systems have multiple stacked bottlenecks: embedder throughput (CPU/GPU), vector DB recall vs latency, LLM token rate, context-window memory pressure, prompt cache hit. Each has its own breakpoint. Standard HTTP load tests miss them. Test each layer in isolation, then end-to-end. Track tokens-per-second, vector p95, embedder QPS, LLM concurrency limit, cache hit rate.',
    oneLiner: 'Test embedder, vector, and LLM separately first. Then end-to-end. Each has its own breakpoint.',
    businessContext:
      'A RAG endpoint p95 jumps from 800 ms to 3.2 s at 200 concurrent users. End-to-end test only says "slow". Layer-by-layer load testing reveals: embedder fine, vector fine, LLM hit max concurrency. Fix: increase LLM replicas + queue.',
    fiveW: {
      what: 'Layered load test for AI: embedder, vector, LLM, end-to-end. Plus breakpoint analysis per layer.',
      why: 'Stacked latencies + each layer has different scaling characteristics. End-to-end alone hides the bottleneck.',
      where: 'Pre-launch + post-model-swap + capacity planning.',
      when: 'Any time embedder, vector index, LLM, or prompt changes.',
      who: 'AI infra + SRE + perf eng.',
    },
    interview30s:
      'AI systems have multiple bottlenecks. I test each layer separately first: embedder QPS, vector p95 at recall@10, LLM tokens/sec at concurrency. Then end-to-end with real query mix. I track tokens-per-second, prompt cache hit, context length distribution, GPU saturation, retry storms. Breakpoint = the load at which any layer breaches its SLA. I model cost in the report — tokens × concurrency × time.',
    hld: `flowchart LR
  Q[Query] --> E[Embedder]
  E --> V[Vector DB]
  V --> R[Reranker]
  R --> L[LLM]
  L --> A[Answer + citations]
  E --> M[Embedder QPS metric]
  V --> M2[Vector p95]
  L --> M3[LLM tok/s]`,
    flowchart: `flowchart TD
  Start[Load test start] --> Iso[Test layer in isolation]
  Iso --> EmbedTest[Embedder: 1000 QPS goal]
  Iso --> VecTest[Vector: p95 lt 50ms goal]
  Iso --> LlmTest[LLM: 20 concurrent goal]
  EmbedTest --> E2E[End-to-end test]
  VecTest --> E2E
  LlmTest --> E2E
  E2E --> Bp{Find weakest layer}
  Bp --> Fix[Scale weakest first]`,
    sequence: `sequenceDiagram
  participant Tester
  participant Embed
  participant Vec
  participant LLM
  Tester->>Embed: 1000 QPS isolated
  Embed-->>Tester: p95 + GPU sat
  Tester->>Vec: 1000 QPS isolated
  Vec-->>Tester: p95 + recall
  Tester->>LLM: 50 concurrent
  LLM-->>Tester: tok/s + queue depth
  Tester->>Tester: end-to-end 500 VU mix
  Note over Tester: weakest layer = bottleneck`,
    coreLayers: [
      { layer: 'Embedder', responsibility: 'Embed queries + docs. CPU or GPU. Batch-friendly.' },
      { layer: 'Vector DB', responsibility: 'k-NN search. Recall vs latency tradeoff.' },
      { layer: 'Reranker', responsibility: 'Cross-encoder. CPU/GPU. Top-k bottleneck.' },
      { layer: 'LLM', responsibility: 'Token generation. Concurrency limited.' },
      { layer: 'Cache', responsibility: 'Prompt + answer cache. Hit rate critical.' },
    ],
    lld: `classDiagram
  class RAGTest {
    +embedderQps()
    +vectorLatency()
    +llmConcurrency()
    +endToEnd()
  }
  class Metrics {
    +tokens_per_second
    +cache_hit_rate
    +ctx_len_p95
    +gpu_sat`,
    coreBuildingBlocks: [
      'Per-layer isolated test harness',
      'End-to-end harness with real query mix from access logs',
      'Token-level metrics: prompt_tok, completion_tok, total_tok per request',
      'Concurrency caps + queue depth per layer',
      'Breakpoint analysis: VU at which any layer breaches SLA',
    ],
    architectureRelevance: {
      backend: 'Same patterns; just more layers.',
      rag: 'Critical: this is THE RAG load test methodology.',
      ai: 'Tokens / cost / concurrency become first-class metrics.',
      microservices: 'Each layer is its own service; isolation = service-level test.',
    },
    problem:
      'End-to-end RAG load test says "slow". Doesn\'t say which layer. Scaling all layers wastes money. Scaling wrong one fixes nothing.',
    whyThisApproach:
      'Layered isolation finds the actual bottleneck. Cost = scale-only-the-bottleneck. Tokens are the new latency.',
    whenToUse: [
      'Any RAG / agent / chatbot system pre-launch',
      'After model upgrade (embedder or LLM)',
      'After vector DB tuning',
      'Before integrating an external LLM provider',
    ],
    whenNotToUse: [
      'Pure retrieval (no LLM) — vector test alone fine',
      'Pure embedding API — embedder test alone fine',
      'Static FAQ chatbot — basic HTTP test fine',
    ],
    input: 'Real query distribution from prod logs + auth + cache state.',
    process: [
      'Isolate embedder: 1000 QPS, measure GPU sat, batch utilization',
      'Isolate vector: 1000 QPS at top_k=5, measure p95 + recall',
      'Isolate LLM: ramp concurrency, measure tokens/sec + queue',
      'End-to-end: 500 VU with prod query mix',
      'Find weakest layer + breakpoint VU per layer',
      'Cost report: tokens × concurrency × duration',
    ],
    output:
      'Per-layer p95 + breakpoint, end-to-end p95, tokens/sec, cache hit rate, cost-per-1000-queries, scaling plan.',
    implementationSteps: [
      { step: 'Pull prod query mix', logic: 'Sample 1000 real queries; mix simple + complex + long-context.' },
      { step: 'Isolated embedder load', logic: 'Drive embedder service directly. GPU sat 80% target.' },
      { step: 'Isolated vector load', logic: 'Pre-warmed index. Vary top_k. Measure recall vs latency.' },
      { step: 'Isolated LLM load', logic: 'Hold prompts constant. Ramp concurrency until queue grows.' },
      { step: 'End-to-end load', logic: '500 VU; track per-layer span via OTel.' },
      { step: 'Breakpoint per layer', logic: 'VU at which span p95 > target.' },
      { step: 'Cost model', logic: 'tokens-per-query × queries-per-sec × $/1k tokens × duration.' },
    ],
    codeExample: {
      language: 'javascript',
      code: `// k6 layered RAG load test
import http from 'k6/http';
import { Trend, Counter } from 'k6/metrics';

const embedT = new Trend('embedder_latency');
const vecT = new Trend('vector_latency');
const llmT = new Trend('llm_latency');
const tokens = new Counter('total_tokens');

export const options = {
  scenarios: {
    embedder: {
      executor: 'constant-vus',
      vus: 200,
      duration: '5m',
      exec: 'embedderTest',
    },
    vector: {
      executor: 'constant-vus',
      vus: 200,
      duration: '5m',
      startTime: '5m',
      exec: 'vectorTest',
    },
    llm: {
      executor: 'ramping-vus',
      stages: [
        { duration: '5m', target: 50 },
        { duration: '5m', target: 100 },
      ],
      startTime: '10m',
      exec: 'llmTest',
    },
    endToEnd: {
      executor: 'constant-vus',
      vus: 500,
      duration: '15m',
      startTime: '20m',
      exec: 'e2eTest',
    },
  },
  thresholds: {
    embedder_latency: ['p(95)<100'],
    vector_latency: ['p(95)<50'],
    llm_latency: ['p(95)<2000'],
  },
};

const queries = JSON.parse(open('./prod_query_sample.json'));

export function embedderTest() {
  const q = queries[Math.floor(Math.random() * queries.length)];
  const r = http.post(\`\${__ENV.EMBED_URL}/embed\`, JSON.stringify({ text: q.text }));
  embedT.add(r.timings.duration);
}

export function vectorTest() {
  const r = http.post(\`\${__ENV.VEC_URL}/search\`, JSON.stringify({ vec: queries[0].vec, top_k: 5 }));
  vecT.add(r.timings.duration);
}

export function llmTest() {
  const r = http.post(\`\${__ENV.LLM_URL}/complete\`, JSON.stringify({ prompt: 'Constant prompt for concurrency test' }));
  llmT.add(r.timings.duration);
  tokens.add(JSON.parse(r.body).total_tokens || 0);
}

export function e2eTest() {
  const q = queries[Math.floor(Math.random() * queries.length)];
  http.post(\`\${__ENV.RAG_URL}/query\`, JSON.stringify({ query: q.text, top_k: 5 }));
}`,
    },
    realUseCase:
      'A team migrates from OpenAI to a self-hosted Llama 3. End-to-end test passes p95 < 2s at 500 VU. Layered test reveals: embedder fine, vector fine, LLM at 95% GPU sat with queue. Adding 2 LLM replicas brings p95 to 1.1s. They saved $40k/month vs scaling everything.',
    prosCons: {
      pros: [
        'Pinpoints actual bottleneck',
        'Saves cost vs scaling everything',
        'Surfaces token cost early',
      ],
      cons: [
        'More tests to author + maintain',
        'Requires layer-level access (not always available with managed APIs)',
        'Needs realistic query mix (not toy queries)',
      ],
    },
    limitations: [
      'Managed LLM providers hide internals (no GPU sat metric)',
      'Cache state is sticky — cold/warm gives different results',
      'Token mix changes per release (prompt template changes)',
    ],
    comparison: {
      left: 'End-to-end only',
      right: 'Layered + end-to-end',
      rows: [
        { aspect: 'Diagnoses bottleneck', left: 'Manual digging', right: 'Direct from test' },
        { aspect: 'Cost-aware', left: 'No', right: 'Per-layer cost' },
        { aspect: 'Authoring effort', left: 'Low', right: 'High' },
        { aspect: 'Catches regressions', left: 'Aggregate only', right: 'Per layer' },
      ],
    },
    challenges: [
      'Realistic query mix (long-tail vs common)',
      'Cache warm vs cold state',
      'GPU sat measurement on managed APIs',
      'Token counting consistency across providers',
      'Reranker often the silent bottleneck',
    ],
    edgeCases: [
      { case: 'Cold cache hit', solution: 'Warm cache via N preflight queries before steady state' },
      { case: 'Long context blow-up', solution: 'Test 90th percentile context length explicitly' },
      { case: 'Streaming responses', solution: 'Track time-to-first-token + tokens-per-second separately' },
      { case: 'Tenant isolation breach', solution: 'Run multi-tenant load with tenant_id mix; assert no cross-leak' },
    ],
    solutions: [
      { problem: 'End-to-end "slow" without layer info', solution: 'Layered isolation + per-span OTel breakdown' },
      { problem: 'Cost surprises after launch', solution: 'Token cost in load test report' },
      { problem: 'Recall regression after vector tuning', solution: 'Recall@k assertion in vector load test' },
      { problem: 'LLM provider rate limit hit', solution: 'Test with throttle headers; verify exponential backoff' },
    ],
    bestPractices: {
      do: [
        'Test layers in isolation first',
        'Use real query mix from prod logs',
        'Track tokens + cost as first-class metrics',
        'Measure cache hit rate during run',
        'Include long-context queries explicitly',
      ],
      avoid: [
        'Toy queries ("hello world")',
        'End-to-end-only testing',
        'Ignoring streaming time-to-first-token',
        'Skipping reranker test',
      ],
      optimize: [
        'Prompt cache before steady state',
        'Sample real queries from logs',
        'GPU saturation alerts during run',
      ],
    },
    antiPatterns: [
      '"It works at 10 QPS, ship it"',
      'No token / cost metric',
      'Hardcoded prompts (cache hits 100% — fake)',
      'No tenant isolation test',
    ],
    testing: ['Unit-test query mix sampling', 'Validate layer endpoints exist', 'Pre-flight smoke at 10 VU'],
    testTypes: ['Layered isolation', 'End-to-end mix', 'Long-context', 'Streaming', 'Multi-tenant'],
    testScenarios: [
      { scenario: 'Embedder p95 < 100ms at 1000 QPS', expected: 'Embedder layer passes' },
      { scenario: 'Vector p95 < 50ms at top_k=5', expected: 'Vector layer passes' },
      { scenario: 'LLM tokens/sec > 50 at 50 concurrent', expected: 'LLM layer passes' },
      { scenario: 'End-to-end p95 < 2s at 500 VU', expected: 'Composite passes' },
      { scenario: 'Cost < $0.05 per query', expected: 'Cost SLA met' },
    ],
    testData: [
      { type: 'Real query sample', example: '1000 queries from access logs, varied length' },
      { type: 'Tenant mix', example: 'Free tier + pro tier query patterns' },
      { type: 'Long-context corpus', example: '10% of queries needing full context window' },
    ],
    debuggingChecklist: [
      'GPU sat per layer logged?',
      'Token counts per request captured?',
      'Cache hit rate visible?',
      'OTel spans for embed / vector / rerank / LLM?',
      'Reranker measured separately?',
      'Streaming TTFT vs tokens/sec separated?',
    ],
    productionIssues: [
      { issue: 'p95 spikes randomly', rootCause: 'Cold pod startup or LLM provider 5xx burst' },
      { issue: 'Cost 3× projected', rootCause: 'Long-context queries dominate token use' },
      { issue: 'Recall drops at scale', rootCause: 'HNSW config too aggressive ef_search' },
    ],
    security: ['Test multi-tenant isolation', 'Mask PII in test queries', 'Rate-limit by tenant in test'],
    performance: [
      'Embedder: GPU > CPU for high QPS',
      'Vector: HNSW ef_search trades latency vs recall',
      'LLM: concurrency cap = the wall',
    ],
    costConsiderations: [
      'Token cost dominates compute cost',
      'Long context multiplies cost',
      'Streaming reduces TTFT but not total cost',
      'Cache hit rate is a cost lever',
    ],
    scaling: ['Horizontal LLM replicas', 'Vector index sharding', 'Embedder batch size tuning'],
    observability: ['OTel spans per layer', 'GPU sat / mem / queue', 'Token cost per request'],
    metrics: [
      { name: 'tokens_per_second', example: '120' },
      { name: 'cache_hit_rate_percent', example: '35' },
      { name: 'embedder_p95_ms', example: '85' },
      { name: 'vector_p95_ms', example: '38' },
      { name: 'llm_p95_ms', example: '1850' },
      { name: 'cost_per_1k_queries_usd', example: '4.20' },
    ],
    failureModes: [
      { mode: 'Embedder GPU OOM', detect: 'Memory > 90%', recover: 'Reduce batch size or scale replicas' },
      { mode: 'Vector index too cold', detect: 'p95 high in first minute only', recover: 'Warmup phase pre-test' },
      { mode: 'LLM rate limit', detect: '429 from provider', recover: 'Provider tier upgrade or retry-with-backoff' },
      { mode: 'Cache stampede', detect: 'p95 spike when cache TTL hits', recover: 'Stale-while-revalidate + jitter' },
    ],
    tradeoffs: [
      { decision: 'Layered + end-to-end', tradeoff: 'More test code; faster diagnosis' },
      { decision: 'Real queries vs synthetic', tradeoff: 'More signal; needs PII handling' },
      { decision: 'Test cost reporting', tradeoff: 'More work; saves bigger surprises' },
    ],
    decisionMatrix: [
      { option: 'End-to-end only', whenToUse: 'Tiny system, no AI bottleneck history' },
      { option: 'Layered + e2e', whenToUse: 'Any production AI system' },
      { option: 'Multi-tenant load', whenToUse: 'SaaS with shared inference' },
    ],
    starStory: {
      situation: 'Migrated from OpenAI to self-hosted Llama 3. End-to-end test passed but LLM was 95% GPU sat at 500 VU.',
      task: 'Find actual bottleneck; right-size infra.',
      action: 'I added layered load test. Embedder + vector were fine. LLM was the wall. Added 2 LLM replicas + queue with backpressure.',
      result: 'p95 dropped from 2.1s to 1.1s. Saved $40k/month vs scaling everything blindly.',
    },
    interviewTraps: [
      'Saying "we tested under load" without layer breakdown',
      'No token cost mentioned',
      'No cache hit rate captured',
      'Toy queries used',
    ],
    finalScript:
      'I test embedder, vector, LLM in isolation; then end-to-end with real query mix. Tokens + cost are first-class metrics. OTel spans per layer make the bottleneck obvious. Scale only the bottleneck; saves both money and engineering hours.',
    alternatives: [
      { name: 'k6 with custom modules', tradeoff: 'Tight CI; needs JS skill' },
      { name: 'Locust + LangChain hooks', tradeoff: 'Python-native; weaker reporting' },
      { name: 'LLM-eval frameworks (Ragas, TruLens)', tradeoff: 'Quality + load combined; less stress flexibility' },
    ],
    monitoring: ['OTel sampler at 100% during load test', 'GPU dashboards', 'Token cost dashboard'],
    maturity: {
      mvp: 'End-to-end + token count',
      production: 'Layered + cost report + tenant mix',
      enterprise: 'Continuous load in staging + breakpoint as release metric + chaos overlay',
    },
    projectFit: ['Pre-launch', 'Model swap', 'Vector index tuning', 'Capacity planning'],
    interviewLine: 'Test layers in isolation first. Tokens are the new latency. Cost is a release metric.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 3 — Performance tuning + outage playbook
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'performance-tuning-outage-playbook',
    title: '3. Performance tuning + outage playbook — Black Friday RAG case study',
    status: 'shipped',
    coreConcept:
      'Load testing finds bottlenecks; the playbook tells you what to do about them. Common bottlenecks: slow query (missing index), connection pool, GC pressure, lock contention, retry storms, cache stampedes, network sat. Tune in a specific order — DB → cache → app → infra. After each change, re-run load test; never tune blind. Outage post-mortems become preventive load test scenarios.',
    oneLiner: 'Load test finds it. Playbook fixes it. Tune DB → cache → app → infra. Always retest.',
    businessContext:
      'Black Friday rolls in. RAG endpoint p95 spikes from 800ms to 8s. Every minute = $X lost. Without a playbook, debugging takes hours. With a playbook, root cause + mitigation = minutes.',
    fiveW: {
      what: 'Standardized order of investigation + a library of past outages turned into load-test scenarios.',
      why: 'During an incident, time-to-mitigation > time-to-root-cause. Playbook reduces decision overhead.',
      where: 'Runbook + load test catalog + chaos game days.',
      when: 'During incidents + during quarterly chaos drills.',
      who: 'On-call + SRE + platform team.',
    },
    interview30s:
      'After load testing finds a bottleneck, I follow a tuning order: DB first (slow query, missing index, pool size), then cache (hit rate, TTL, stampede protection), then app (GC, thread pools, connection pools), then infra (HPA, network, DNS). I retest after each change. Past outages become permanent regression scenarios in the load test catalog. Black Friday + AI = expand the catalog with token-cost spikes + LLM provider 5xx storms.',
    hld: `flowchart LR
  Inc[Incident] --> P[Playbook]
  P --> DB[1 DB tuning]
  DB --> Ca[2 Cache tuning]
  Ca --> App[3 App tuning]
  App --> Inf[4 Infra tuning]
  Inf --> RT[Retest under load]
  RT --> Cat[Add to load catalog]`,
    flowchart: `flowchart TD
  Spike[p95 spike detected] --> Trace[Look at OTel traces]
  Trace --> WhereQ{Slowest span?}
  WhereQ -- DB --> DBPath[Check slow query log + index]
  WhereQ -- Cache --> CachePath[Check hit rate + stampede]
  WhereQ -- App --> AppPath[Check GC + thread pool]
  WhereQ -- LLM --> LLMPath[Check provider 5xx + queue]
  DBPath --> Mit[Mitigate]
  CachePath --> Mit
  AppPath --> Mit
  LLMPath --> Mit
  Mit --> Retest[Retest under load]
  Retest --> Cat[Add to permanent load catalog]`,
    sequence: `sequenceDiagram
  participant Op as On-call
  participant Run as Runbook
  participant Load as Load test
  Op->>Run: incident detected
  Run->>Op: check DB slow query first
  Op->>Op: find slow query
  Op->>Op: add index
  Run->>Load: rerun stress phase
  Load-->>Op: p95 back to baseline
  Op->>Run: add to catalog`,
    coreLayers: [
      { layer: 'Detect', responsibility: 'Alerts on p95, error rate, retry rate, queue depth.' },
      { layer: 'Diagnose', responsibility: 'OTel traces narrow to slowest span quickly.' },
      { layer: 'Mitigate', responsibility: 'Playbook: known-fix or rollback.' },
      { layer: 'Verify', responsibility: 'Re-run load test phase that originally caught it.' },
      { layer: 'Catalog', responsibility: 'Permanent regression scenario in load suite.' },
    ],
    lld: `classDiagram
  class Playbook {
    +order: [DB, Cache, App, Infra]
    +runbook(symptom): action
  }
  class Catalog {
    +scenarios: PastIncident[]
    +regressionTest(release)
  }
  class Drill {
    +quarterly_chaos`,
    coreBuildingBlocks: [
      'Tuning order: DB → cache → app → infra',
      'OTel traces with span breakdown per layer',
      'Slow query log + pg_stat_statements',
      'Cache hit / miss / stampede metrics',
      'Catalog of past incidents → load test scenarios',
      'Quarterly chaos drill schedule',
    ],
    architectureRelevance: {
      backend: 'Standard tuning order applies.',
      rag: 'Add LLM provider, vector recall, prompt cache to layers.',
      ai: 'Token cost spikes + GPU sat + provider 5xx are AI-specific outage patterns.',
      microservices: 'Cascade + retry storms + circuit breaker behavior measured.',
    },
    problem:
      'Incidents take hours to root-cause. Same outage repeats next quarter because no regression test was added.',
    whyThisApproach:
      'Order reduces decision fatigue. Catalog turns each incident into a permanent guard. Quarterly drills keep skills sharp.',
    whenToUse: [
      'Production system with paying users',
      'Any system with AI / external dependencies',
      'Pre-launch hardening',
    ],
    whenNotToUse: [
      'Internal tool with low traffic',
      'Pure dev environments',
    ],
    input: 'Incident telemetry + runbook + load test catalog.',
    process: [
      'Detect: alert fires (p95 / error rate / queue depth)',
      'Diagnose: open OTel trace; find slowest span',
      'Mitigate: apply playbook step matching span',
      'Verify: re-run load phase that caught it',
      'Catalog: add scenario to permanent load suite',
      'Drill: quarterly chaos exercise rotates scenarios',
    ],
    output: 'Mitigated incident + post-mortem + new load scenario + updated runbook.',
    implementationSteps: [
      { step: 'Build runbook', logic: 'Top 20 alerts mapped to top 20 mitigations.' },
      { step: 'Tag traces', logic: 'request_id + tenant_id + feature flag in every span.' },
      { step: 'Slow query log', logic: 'pg_stat_statements + alert on p95 query > 200ms.' },
      { step: 'Cache metrics', logic: 'Hit/miss/stampede + per-key TTL distribution.' },
      { step: 'Catalog past incidents', logic: 'Each post-mortem ends with a new k6 scenario.' },
      { step: 'Quarterly drill', logic: 'Inject failure; verify playbook works; update doc.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# runbook excerpt — RAG system
- alert: rag_p95_high
  expr: histogram_quantile(0.95, sum by (le) (rate(rag_query_duration_bucket[5m]))) > 2000
  for: 5m
  annotations:
    summary: "RAG p95 > 2s"
    playbook: |
      1. Open OTel trace for slow request_id
      2. Identify slowest span (embed / vector / rerank / llm)
      3. If LLM: check provider 5xx + tier rate limit
      4. If vector: check ef_search config + index health
      5. If embed: check GPU sat + batch size
      6. If DB: pg_stat_statements + slow query log
      7. After mitigation: rerun k6 stress; add scenario to catalog

- alert: token_cost_spike
  expr: rate(rag_tokens_total[5m]) > 100000
  for: 10m
  annotations:
    summary: "Token cost spike"
    playbook: |
      1. Find tenant_id with highest token rate
      2. Check for prompt-injection or context overflow
      3. Apply tenant rate limit
      4. Add k6 spike scenario for repeat`,
    },
    realUseCase:
      'Black Friday: RAG p95 jumped from 800ms to 6s at 14:02. Trace showed slowest span = LLM (5.4s). Playbook step: provider 5xx + rate limit. Confirmed via provider dashboard. Mitigation: switched to fallback model. p95 back to 1.2s by 14:11. Post-mortem added k6 scenario "LLM provider 5xx burst". Three months later same provider had outage; catalog test had already validated graceful failover; auto-mitigation kicked in; users never noticed.',
    prosCons: {
      pros: [
        'Reduces MTTR drastically',
        'Same incident never recurs unmitigated',
        'On-call rotation is sustainable',
      ],
      cons: [
        'Catalog requires discipline to maintain',
        'Drills cost engineering time',
        'Runbook drift if not reviewed',
      ],
    },
    limitations: [
      'Novel failures still need human investigation',
      'Catalog can grow stale if not pruned',
      'Drill quality depends on realism',
    ],
    comparison: {
      left: 'Reactive incident handling',
      right: 'Playbook + catalog',
      rows: [
        { aspect: 'MTTR', left: 'Hours', right: 'Minutes' },
        { aspect: 'Recurrence rate', left: 'High', right: 'Low' },
        { aspect: 'On-call burden', left: 'Burnout', right: 'Sustainable' },
        { aspect: 'Drill cadence', left: 'None', right: 'Quarterly' },
      ],
    },
    challenges: [
      'Keeping runbook in sync with system changes',
      'Realistic chaos injection without harming users',
      'Prioritizing which scenarios to catalog first',
      'Balancing drill cost with team capacity',
    ],
    edgeCases: [
      { case: 'Multiple alerts fire simultaneously', solution: 'Runbook prioritization: data-loss > availability > latency' },
      { case: 'Mitigation makes it worse', solution: 'Rollback step required in every playbook entry' },
      { case: 'Provider 5xx but our SLA is fine', solution: 'Customer comms even if SLA met (transparency)' },
    ],
    solutions: [
      { problem: 'Same outage every quarter', solution: 'Catalog scenario + regression in CI' },
      { problem: 'On-call burnout', solution: 'Playbook reduces decision load + drill rotation' },
      { problem: 'Slow root cause', solution: 'Tag everything with request_id + tenant_id from edge to LLM' },
      { problem: 'Untested mitigation', solution: 'Quarterly chaos drill validates + updates' },
    ],
    bestPractices: {
      do: [
        'One playbook entry per top alert',
        'Add a regression scenario after every incident',
        'Run quarterly chaos drills',
        'Keep tuning order: DB → cache → app → infra',
        'Tag traces with request_id + tenant_id',
      ],
      avoid: [
        'Tuning blind — always retest',
        'Letting runbook drift',
        'Skipping the catalog step',
        'No fallback path for LLM provider',
      ],
      optimize: [
        'Auto-rollback triggers on metric breach',
        'Auto-failover for LLM provider',
        'OTel sampling 100% during incident',
      ],
    },
    antiPatterns: [
      'Hero culture (one engineer always firefights)',
      'No post-mortem doc',
      'No regression test from incident',
      'Manually mitigating same alert third time',
    ],
    testing: ['Drill weekly in staging', 'Chaos quarterly', 'Catalog runs in CI weekly'],
    testTypes: ['Chaos drill', 'Regression replay', 'Failover verify', 'Provider 5xx burst'],
    testScenarios: [
      { scenario: 'LLM provider 5xx for 5 min', expected: 'Failover to fallback; users unaffected' },
      { scenario: 'Vector index hot rebuild', expected: 'Read fallback; recall slightly degraded; users see no error' },
      { scenario: 'Token cost spike (prompt injection)', expected: 'Tenant rate limit kicks; alert fires' },
      { scenario: 'Cache stampede on TTL', expected: 'Stale-while-revalidate prevents thundering herd' },
    ],
    testData: [
      { type: 'Real outage replays', example: 'Black Friday 2025 5xx burst' },
      { type: 'Synthetic chaos', example: 'tc qdisc netem latency injection' },
    ],
    debuggingChecklist: [
      'OTel sampling sufficient?',
      'request_id + tenant_id tagged everywhere?',
      'Slow query log enabled + monitored?',
      'Cache hit/miss/stampede tracked?',
      'Provider 5xx tracked separately?',
      'Auto-rollback triggers configured?',
    ],
    productionIssues: [
      { issue: 'p95 spike during peak', rootCause: 'LLM provider 5xx burst + no fallback' },
      { issue: 'Token cost 10× normal', rootCause: 'Prompt injection from one tenant' },
      { issue: 'Cache stampede on warm-up', rootCause: 'Same TTL on millions of keys; jitter missing' },
      { issue: 'Slow query log overflow', rootCause: 'Missing index on FK; pg_stat_statements full' },
    ],
    security: ['Drill access via break-glass + audit', 'Mask tenant data in chaos drill', 'Rate-limit playbook actions'],
    performance: [
      'OTel high sampling during incident',
      'Auto-rollback < 60s',
      'Failover < 30s',
    ],
    costConsiderations: [
      'Token cost spike alerts (saves real money)',
      'Auto-failover to cheaper model when premium fails',
      'Auto-scale-down after spike',
    ],
    scaling: ['Auto-rollback on breach', 'Auto-failover to fallback model', 'HPA on queue depth'],
    observability: ['OTel traces (sampled higher during incident)', 'Slow query log alerts', 'Provider health probes', 'Token cost dashboards'],
    metrics: [
      { name: 'mttr_minutes', example: '6' },
      { name: 'incident_recurrence_rate', example: '0.1' },
      { name: 'drill_pass_rate', example: '0.95' },
      { name: 'catalog_size', example: '47 scenarios' },
    ],
    failureModes: [
      { mode: 'LLM provider outage', detect: '5xx burst + p95 spike', recover: 'Auto-failover to fallback model' },
      { mode: 'Vector index corruption', detect: 'Recall drops + errors', recover: 'Read fallback from snapshot' },
      { mode: 'Token-cost runaway', detect: 'tokens/min metric breach', recover: 'Tenant rate limit + investigate prompt' },
      { mode: 'Cache stampede', detect: 'p95 spike on TTL boundary', recover: 'Stale-while-revalidate + jitter' },
    ],
    tradeoffs: [
      { decision: 'Quarterly chaos drill', tradeoff: 'Eng cost; saves bigger outages' },
      { decision: 'Auto-failover models', tradeoff: 'Quality may dip; availability stays' },
      { decision: 'Aggressive auto-rollback', tradeoff: 'Some false alarms; faster MTTR' },
    ],
    decisionMatrix: [
      { option: 'Manual playbook only', whenToUse: 'Small team, low traffic' },
      { option: 'Playbook + auto-rollback', whenToUse: 'Mid-size, paying users' },
      { option: 'Playbook + auto-failover + chaos drill', whenToUse: 'Enterprise, AI-dependent' },
    ],
    starStory: {
      situation: 'Black Friday 14:02. RAG p95 spiked from 800ms to 6s; revenue at risk.',
      task: 'Mitigate within 10 minutes; prevent recurrence.',
      action: 'I followed playbook: OTel trace → slow span = LLM → provider dashboard showed 5xx burst → I switched to fallback model. By 14:11 p95 back to 1.2s. Post-mortem added k6 scenario "LLM provider 5xx burst" + auto-failover trigger.',
      result: 'MTTR 9 minutes. Three months later same provider had a longer outage; auto-failover kicked silently; users never noticed. Catalog now has 47 scenarios; drill pass rate 95%.',
    },
    interviewTraps: [
      'No runbook = "we figure it out"',
      'No regression test from incidents',
      'No drill cadence',
      'No fallback for LLM provider',
    ],
    finalScript:
      'I run a tuning order: DB, cache, app, infra. Each incident becomes a permanent k6 scenario in the catalog. Quarterly chaos drills keep skills sharp. For AI systems I add LLM provider failover, token cost alerts, and prompt cache stampede protection. MTTR drops from hours to minutes.',
    alternatives: [
      { name: 'Reactive only', tradeoff: 'No drill cost; high MTTR; recurrence high' },
      { name: 'Auto-everything', tradeoff: 'Lower MTTR; false-positive risk; over-mitigation' },
      { name: 'Playbook + selective auto', tradeoff: 'Best balance; eng discipline required' },
    ],
    monitoring: ['Alert → playbook link', 'Catalog regression in CI weekly', 'Drill pass rate dashboard'],
    maturity: {
      mvp: 'Top-10 alert runbook',
      production: 'Full playbook + catalog + auto-rollback',
      enterprise: 'Auto-failover + quarterly chaos + catalog as CI gate',
    },
    projectFit: ['Production AI', 'High-traffic SaaS', 'Black Friday / launch prep', 'Post-incident hardening'],
    interviewLine: 'Playbook + catalog + drill. MTTR from hours to minutes. Same outage never recurs.',
  },
];

export default function LoadTestingDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Load testing (deep dive)</h1>
        <p className="design-areas-sub">
          k6 + JMeter five-phase methodology (smoke / load / stress / soak / spike).
          RAG / AI layered load testing — embedder, vector, LLM in isolation then
          end-to-end. Performance tuning order (DB → cache → app → infra) and the
          incident-playbook + catalog discipline that turns each post-mortem into a
          permanent k6 regression scenario.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
