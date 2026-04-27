'use client';

/**
 * Post-release / deployment ops (deep dive).
 *
 * Two topics: deployment playbook (strategy fit, golden rules, AI
 * extensions), and post-deployment verification (golden signals +
 * smoke + rollback decision matrix + AI/RAG-specific signals).
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — Deployment playbook
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'deployment-playbook',
    title: '1. Deployment playbook — strategy fit + golden rules + AI extensions',
    status: 'shipped',
    coreConcept:
      'Deployments become boring when strategy fits risk + rules are non-negotiable + automation enforces them. Match strategy to risk: blue-green for critical (instant rollback, double cost), canary for unknown user-facing risk, rolling for low-risk internal, feature flags for everything. Golden rules: immutable artifacts, backward-compatible code + DB, health checks gate releases, no Friday deploys without on-call. AI adds eval gate + cost budget + fallback model.',
    oneLiner: 'Strategy fits risk. Golden rules are automation-enforced. AI adds eval + cost gate.',
    businessContext:
      'Team big-bang deploys to all instances on Friday afternoon. Saturday: rollback impossible because schema changed irreversibly. Two days down. Playbook would have caught: no DB expand-contract, no canary, no Friday guard, no rollback path.',
    fiveW: {
      what: 'Deployment strategy matrix + non-negotiable rules + post-deploy verification + AI-specific gates.',
      why: 'Releases are the highest-risk routine activity. Discipline turns release night into a non-event.',
      where: 'Every production system. Stricter for regulated / customer-facing.',
      when: 'Every release. Plus quarterly rollback drill in staging.',
      who: 'Release owner + dev + SRE + on-call. AI features add ML/Quality.',
    },
    interview30s:
      'I make deploys boring: strategy fits risk (blue-green for critical, canary for risky, rolling for low-risk, flags everywhere), golden rules enforced by CI (immutable artifacts, backward-compatible code + DB via expand-contract, health checks, no Friday deploys without on-call), and post-deploy verification with golden signals + auto-rollback. For AI I add eval gates, token budget, fallback model.',
    hld: `flowchart LR
  Risk[Assess risk] --> Strategy{Pick strategy}
  Strategy -- critical --> BG[Blue-green]
  Strategy -- unknown --> Cny[Canary]
  Strategy -- low-risk --> Roll[Rolling]
  Strategy -- always --> Flag[Feature flag]
  BG --> Deploy[Deploy with golden rules]
  Cny --> Deploy
  Roll --> Deploy
  Flag --> Deploy
  Deploy --> Verify[Post-deploy verification]
  Verify --> Promote[Promote or rollback]`,
    flowchart: `flowchart TD
  Start[Release ready] --> Pre[Pre-prod checklist]
  Pre --> Strat{Strategy fits risk?}
  Strat --> Build[Immutable artifact]
  Build --> Stg[Deploy staging]
  Stg --> Smoke[Smoke + integration]
  Smoke --> Approve{Manual approval?}
  Approve -- if needed --> Cny[Canary 10 percent]
  Approve -- auto --> Cny
  Cny --> Mon[Monitor 15-60 min]
  Mon --> Decide{Auto-promote OR rollback}
  Decide -- pass --> Full[100 percent]
  Decide -- fail --> Rb[Rollback]
  Rb --> RCA[Post-mortem]`,
    sequence: `sequenceDiagram
  participant Eng
  participant Pipeline
  participant Stg as Staging
  participant Prod
  participant Mon as Monitor
  Eng->>Pipeline: trigger deploy
  Pipeline->>Stg: deploy + smoke
  Stg-->>Pipeline: green
  Pipeline->>Prod: canary 10 percent
  Prod->>Mon: golden signals
  Mon-->>Pipeline: pass after 5 min
  Pipeline->>Prod: 50 percent
  Pipeline->>Prod: 100 percent
  Note over Eng,Prod: any breach: auto rollback`,
    coreLayers: [
      { layer: 'Strategy', responsibility: 'Match deploy method to risk class.' },
      { layer: 'Artifact', responsibility: 'Immutable, signed, SBOM, scanned.' },
      { layer: 'DB', responsibility: 'Expand-migrate-deploy-contract; never break compat.' },
      { layer: 'Health', responsibility: 'startup / liveness / readiness probes gate traffic.' },
      { layer: 'Verify', responsibility: 'Smoke + golden signals + AI eval before promote.' },
      { layer: 'Rollback', responsibility: 'Auto-trigger on metric breach; tested quarterly.' },
    ],
    lld: `classDiagram
  class Deployment {
    +strategy
    +artifact_sha
    +db_migrations
    +flags
    +rollback_path
  }
  class Strategy {
    <<abstract>>
    +deploy()
    +rollback()
  }
  class BlueGreen
  class Canary
  class Rolling
  Strategy <|-- BlueGreen
  Strategy <|-- Canary
  Strategy <|-- Rolling`,
    coreBuildingBlocks: [
      'Strategy matrix: blue-green / canary / rolling / flags',
      'Immutable artifact: build once + SHA tag + cosign + SBOM',
      'DB expand-migrate-deploy-contract (never DROP/RENAME in same release)',
      'Health probes: startup + liveness + readiness',
      'Feature flags: dark launch + gradual rollout + kill switch',
      'AI gates: eval + safety + token budget + fallback model',
      'Auto-rollback on metric breach',
      'Quarterly rollback drill in staging',
    ],
    architectureRelevance: {
      backend: 'Strategy matrix applies to every service.',
      rag: 'AI gates added (eval + cost + fallback).',
      ai: 'Model + prompt versioned in registry; rollback flips registry pointer.',
      microservices: 'Per-service strategy; dependent services need compatible deploy order.',
    },
    problem:
      'Big-bang Friday deploy → outage → no rollback path → DB schema irreversible → days down.',
    whyThisApproach:
      'Strategy matrix shrinks blast radius. Golden rules + automation prevent human shortcuts. AI gates close the new attack surface.',
    whenToUse: [
      'Every production system',
      'Every customer-facing change',
      'Every AI feature',
    ],
    whenNotToUse: [
      'Internal demo never seen by users',
      'Disposable research notebook',
    ],
    input: 'Release artifact + DB migration plan + flag config + rollback plan + observation window plan.',
    process: [
      'Pre-prod checklist (artifact, scans, BC, migrations, probes, flags, rollback, comms)',
      'Pick strategy by risk class',
      'Deploy staging + smoke + integration',
      '(Optional) manual approval',
      'Canary or blue-green prod',
      'Health checks gate traffic',
      'Observe 15–60 min',
      'Auto-promote OR auto-rollback',
      'On rollback: RCA + permanent regression scenario',
    ],
    output: 'Deployed release + audit trail + metrics + (on rollback) RCA + new regression test.',
    implementationSteps: [
      { step: 'Strategy decision tree', logic: 'Critical / unknown-risk / low-risk → blue-green / canary / rolling.' },
      { step: 'Immutable artifact', logic: 'Build once + SHA tag + cosign + SBOM.' },
      { step: 'DB expand-contract', logic: 'Add column nullable → backfill → app reads new → contract later.' },
      { step: 'Probes wired', logic: 'startup (slow boot), liveness (process), readiness (deps).' },
      { step: 'Flags', logic: 'Default OFF for new feature. Dark launch + 1% → 10% → 50% → 100%.' },
      { step: 'AI eval gate', logic: 'Regression set + threshold; block promote on drop.' },
      { step: 'Auto-rollback', logic: 'Argo Rollouts analysis: 5xx / p95 / AI score breach → flip back.' },
      { step: 'Drill quarterly', logic: 'Rehearse rollback per layer in staging.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# argo-rollouts-canary.yaml — canary with auto-analysis
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: rag-api
spec:
  replicas: 10
  strategy:
    canary:
      steps:
        - setWeight: 10
        - pause: { duration: 5m }
        - analysis:
            templates:
              - templateName: golden-signals
              - templateName: ai-eval
        - setWeight: 50
        - pause: { duration: 10m }
        - analysis:
            templates:
              - templateName: golden-signals
        - setWeight: 100
  selector:
    matchLabels: { app: rag-api }
  template:
    spec:
      containers:
        - name: api
          image: registry/rag-api:\${SHA}
          startupProbe:
            httpGet: { path: /health/startup, port: 8080 }
            failureThreshold: 30
            periodSeconds: 10
          livenessProbe:
            httpGet: { path: /health/live, port: 8080 }
            periodSeconds: 30
          readinessProbe:
            httpGet: { path: /health/ready, port: 8080 }
            periodSeconds: 10
---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata: { name: golden-signals }
spec:
  metrics:
    - name: error-rate
      successCondition: result < 0.01
      provider:
        prometheus:
          query: |
            sum(rate(http_requests_total{status=~"5.."}[5m])) /
            sum(rate(http_requests_total[5m]))
    - name: p95-latency
      successCondition: result < 2000
      provider:
        prometheus:
          query: histogram_quantile(0.95, rate(request_duration_bucket[5m]))`,
    },
    realUseCase:
      'Team migrated from in-place deploys to canary + flags + auto-rollback. Black Friday: a bad model promote + p95 spike caught at 12% canary, auto-rollback in 47s. Users never noticed. RCA added eval threshold + token budget alert.',
    prosCons: {
      pros: [
        'Boring deploys (the goal)',
        'MTTR drops from hours to minutes',
        'AI quality gated before users see it',
        'Audit trail comes free',
      ],
      cons: [
        'Strategy diversity adds platform complexity',
        'Flag sprawl if not pruned',
        'Quarterly drills cost engineering time',
      ],
    },
    limitations: [
      'Some failure modes only show at 100% (use load test pre-deploy)',
      'Cross-service dependencies require careful deploy order',
      'AI eval can\'t catch fully novel failure modes',
    ],
    comparison: {
      left: 'Big-bang deploy',
      right: 'Strategy + golden rules + AI gates',
      rows: [
        { aspect: 'Blast radius', left: 'Whole user base', right: '1–10% canary' },
        { aspect: 'MTTR', left: 'Hours', right: 'Minutes' },
        { aspect: 'Rollback', left: 'Manual + risky', right: 'Automatic' },
        { aspect: 'AI quality', left: 'Discovered by users', right: 'Caught pre-promote' },
        { aspect: 'Audit', left: 'Memory', right: 'Pipeline log' },
      ],
    },
    challenges: [
      'Flag sprawl — prune quarterly',
      'Cross-service compat — coordinate deploy order',
      'DB migration timing vs app deploy',
      'AI eval flakes vs real regression',
    ],
    edgeCases: [
      { case: 'Schema migration must run before app', solution: 'Migration job in pipeline; app deploy waits' },
      { case: 'Canary too small to detect issue', solution: 'Increase canary % or run longer observation' },
      { case: 'Provider 5xx during deploy', solution: 'Pause deploy + alert + check provider status' },
      { case: 'Rollback breaks because column dropped', solution: 'Never DROP in same release; expand-contract' },
    ],
    solutions: [
      { problem: 'Big-bang risk', solution: 'Canary or blue-green' },
      { problem: 'No rollback', solution: 'Auto-rollback triggers + tested drill' },
      { problem: 'DB irreversible', solution: 'Expand-migrate-deploy-contract' },
      { problem: 'AI quality drift', solution: 'Eval gate + threshold' },
      { problem: 'Cost surprise', solution: 'Token budget + alert' },
    ],
    bestPractices: {
      do: [
        'Match strategy to risk',
        'Immutable artifact + sign + SBOM',
        'Backward-compatible code + DB',
        'Health probes wired',
        'Feature flag every new feature',
        'Auto-rollback on breach',
        'AI eval gate',
        'Quarterly rollback drill',
      ],
      avoid: [
        'Friday deploys without on-call',
        'Big-bang without canary',
        'DROP / RENAME in same release',
        'Manual approval as default for low-risk',
        'No fallback model for AI',
      ],
      optimize: [
        'Auto-promote on green metrics',
        'Pre-warm caches before canary',
        'Parallel deploys for independent services',
      ],
    },
    antiPatterns: [
      'Hero deploys (one engineer always does it)',
      'No rollback rehearsal',
      'No AI eval — ship and watch',
      'Dropped column in same release as added column',
    ],
    testing: ['Pre-prod checklist', 'Smoke + integration in staging', 'AI eval regression', 'Quarterly rollback drill'],
    testTypes: ['Smoke', 'Integration', 'Contract', 'AI eval', 'Chaos drill'],
    testScenarios: [
      { scenario: 'Canary at 10% with 5xx burst', expected: 'Auto-rollback < 60s' },
      { scenario: 'AI eval drop > threshold', expected: 'Block promote' },
      { scenario: 'DB rollback after expand-only deploy', expected: 'App still works on previous version' },
      { scenario: 'Flag toggled OFF', expected: 'Feature disabled instantly without redeploy' },
    ],
    testData: [
      { type: 'Smoke fixtures', example: 'Top-5 user journeys auto-replayed' },
      { type: 'AI eval set', example: '100+ regression queries' },
    ],
    debuggingChecklist: [
      'Artifact SHA matches across envs?',
      'Probes returning healthy?',
      'DB migration applied first?',
      'Flag default OFF?',
      'AI eval threshold set?',
      'Rollback path tested in last quarter?',
    ],
    productionIssues: [
      { issue: 'Canary OK but full rollout fails', rootCause: 'Canary too small to surface; increase % or duration' },
      { issue: 'Rollback fails because DB changed', rootCause: 'Skipped expand-contract; do migrations in two releases' },
      { issue: 'AI quality drop missed', rootCause: 'Eval threshold too lax; tighten' },
    ],
    security: ['Sign artifact', 'Verify signature pre-deploy', 'Rotate secrets without downtime', 'Audit every deploy'],
    performance: ['Canary observation 5–10 min', 'Auto-rollback < 60s', 'Full rollout < 30 min'],
    costConsiderations: [
      'Blue-green = double infra during cutover',
      'Canary = small overhead during ramp',
      'Token budget for AI prevents cost spikes',
    ],
    scaling: ['Per-service strategy', 'Reusable Argo / Flagger templates', 'Platform team owns shared config'],
    observability: ['Argo Rollouts dashboard', 'Golden signals during deploy', 'AI eval score during canary', 'Rollback events'],
    metrics: [
      { name: 'deploy_success_rate', example: '0.96' },
      { name: 'rollback_count_per_week', example: '2' },
      { name: 'mttr_minutes', example: '6' },
      { name: 'change_failure_rate', example: '0.04' },
      { name: 'ai_eval_score_during_canary', example: '0.91' },
    ],
    failureModes: [
      { mode: 'Canary metric breach', detect: 'Prom alert', recover: 'Auto-rollback flip' },
      { mode: 'AI eval drop', detect: 'Eval CI step fails', recover: 'Block promote' },
      { mode: 'Provider 5xx during deploy', detect: 'Health probe fail', recover: 'Pause deploy + alert' },
      { mode: 'DB migration failure', detect: 'Migration job exit non-zero', recover: 'Run rollback migration' },
    ],
    tradeoffs: [
      { decision: 'Blue-green', tradeoff: 'Instant rollback; 2× infra during cutover' },
      { decision: 'Aggressive auto-rollback', tradeoff: 'False positives; faster MTTR' },
      { decision: 'Strict eval gate', tradeoff: 'Slower release cadence; AI quality maintained' },
    ],
    decisionMatrix: [
      { option: 'Blue-green', whenToUse: 'Critical systems; instant rollback needed' },
      { option: 'Canary', whenToUse: 'Unknown risk; user-facing feature' },
      { option: 'Rolling', whenToUse: 'Internal services; compatible changes' },
      { option: 'Flag-only', whenToUse: 'Code is live but feature OFF; gradual rollout' },
    ],
    starStory: {
      situation: 'Big-bang Friday deploy → Saturday outage → DB irreversible → days down.',
      task: 'Establish playbook + automation; never repeat.',
      action: 'Migrated to canary + Argo Rollouts + flags + expand-contract DB + auto-rollback + AI eval gate. Quarterly drill.',
      result: 'Black Friday: bad model caught at 12% canary, rollback in 47s. Users never noticed. MTTR 6h → 6 min. Change failure rate 18% → 4%.',
    },
    interviewTraps: [
      'No rollback path in story',
      'No DB expand-contract',
      'No AI eval gate',
      'No drill cadence',
    ],
    finalScript:
      'Strategy fits risk: blue-green / canary / rolling / flags. Golden rules: immutable, backward-compatible, health-checked, no Friday without on-call. AI: eval + cost + fallback. Auto-rollback. Quarterly drill.',
    alternatives: [
      { name: 'In-place rolling', tradeoff: 'Cheap; slower rollback' },
      { name: 'Blue-green', tradeoff: 'Instant rollback; 2× infra' },
      { name: 'Canary', tradeoff: 'Real user validation; longer rollout' },
      { name: 'Shadow deploy', tradeoff: 'Test on real traffic; no user impact' },
    ],
    monitoring: ['Argo dashboard', 'DORA metrics', 'Rollback events', 'AI eval score history'],
    maturity: {
      mvp: 'Rolling + flags',
      production: 'Canary + auto-rollback + AI eval',
      enterprise: 'Multi-region + GitOps + chaos drill + drill metric tracked',
    },
    projectFit: ['Every prod system', 'Customer-facing', 'AI features', 'Regulated workloads'],
    interviewLine: 'Strategy by risk. Golden rules. AI eval + cost. Auto-rollback. Drill quarterly.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — Post-deployment verification (PDV)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'pdv-monitoring',
    title: '2. Post-deployment verification — golden signals + AI signals + rollback decision matrix',
    status: 'shipped',
    coreConcept:
      'Deploy is not done when code is released; deploy is done when production proves it stable. Watch four golden signals (errors, latency, traffic, saturation) plus AI-specific signals (LLM latency, timeouts, token cost, retrieval latency, groundedness, hallucination reports, guardrail blocks). Smoke flows replay the critical user journey. Rollback decision matrix removes hesitation. Every finding becomes a permanent test or alert.',
    oneLiner: 'Deploy ≠ done. Production stability proves done. Watch golden + AI signals. Rollback decisions are pre-decided.',
    businessContext:
      'Team deploys; "looks fine"; users complain at 3 AM about slow chatbot. PDV would have caught: LLM p95 quietly doubled in canary; eval score dropped 8%. Rollback decision matrix would have triggered automatic flip.',
    fiveW: {
      what: 'Active verification phase: golden signals + AI signals + smoke flows + rollback decision matrix + feedback loop into tests.',
      why: 'Deploys without active verification are uncontrolled experiments on real users.',
      where: '15–60 min observation window during canary; longer for AI features.',
      when: 'Every release. Every flag flip.',
      who: 'Release owner + on-call + AI feature owner.',
    },
    interview30s:
      'PDV is the active phase after deploy. I watch golden signals — errors, latency, traffic, saturation — plus AI signals — LLM latency, token cost, groundedness, hallucination, guardrail blocks. Synthetic monitors replay the critical user journey. Rollback decisions are pre-decided in a matrix; we don\'t debate at 3 AM. Every finding becomes a permanent test or alert.',
    hld: `flowchart LR
  Deploy[Deploy] --> Health[Health probes pass]
  Health --> Smoke[Smoke + synthetic journey]
  Smoke --> Watch[Observe 15-60 min]
  Watch --> Sig{Signals OK?}
  Sig -- yes --> Promote[Promote 100 percent]
  Sig -- no --> Matrix{Rollback matrix}
  Matrix -- critical --> Rb[Rollback]
  Matrix -- AI quality --> Flag[Disable feature flag]
  Matrix -- cost --> Throttle[Throttle / fallback]
  Rb --> RCA[Post-mortem + new test]`,
    flowchart: `flowchart TD
  Start[Deploy live in canary] --> Smoke[Run smoke flows]
  Smoke --> Health[Health probe ready]
  Health --> Mon[Watch metrics 15-60 min]
  Mon --> Err{5xx less than 1 percent}
  Mon --> Lat{p95 within 2x baseline}
  Mon --> Tr{Traffic within 30 percent of baseline}
  Mon --> AI{AI eval within delta}
  Err -- pass --> All
  Lat -- pass --> All
  Tr -- pass --> All
  AI -- pass --> All
  All[All green] --> Prom[Promote]
  Err -- fail --> Rb[Rollback]
  Lat -- fail --> Rb
  AI -- fail --> Flag[Disable AI feature flag]`,
    sequence: `sequenceDiagram
  participant CD
  participant Prod
  participant Mon as Monitor
  participant Owner as Release owner
  CD->>Prod: canary 10 percent
  Prod->>Mon: golden signals
  Prod->>Mon: AI signals
  Mon->>Mon: window aggregate 5 min
  Mon-->>Owner: pass after 3 of 5 windows green
  Owner->>CD: promote
  alt breach
    Mon->>CD: trigger rollback
    CD->>Prod: flip to previous SHA
    Mon-->>Owner: rollback complete
  end`,
    coreLayers: [
      { layer: 'Health', responsibility: '/health/ready before traffic.' },
      { layer: 'Smoke', responsibility: 'Synthetic replay of critical journey.' },
      { layer: 'Golden signals', responsibility: 'Errors / latency / traffic / saturation.' },
      { layer: 'AI signals', responsibility: 'LLM latency / token cost / groundedness / safety blocks.' },
      { layer: 'Rollback matrix', responsibility: 'Pre-decided trigger → pre-decided action.' },
      { layer: 'Feedback', responsibility: 'Every finding → permanent test or alert.' },
    ],
    lld: `classDiagram
  class PDV {
    +health_probes
    +smoke_journey
    +golden_signals
    +ai_signals
    +rollback_matrix: Trigger to Action
    +feedback_loop()
  }
  class Trigger {
    +metric
    +threshold
    +window
  }
  class Action {
    +rollback
    +flag_disable
    +throttle
    +alert`,
    coreBuildingBlocks: [
      'Golden signals: errors / latency / traffic / saturation',
      'AI signals: LLM latency / timeout / token cost / retrieval latency / groundedness / hallucination / guardrail blocks',
      'Synthetic monitor: login → search → checkout (or AI: query → retrieve → generate → guardrail)',
      'Rollback decision matrix (pre-decided)',
      'Window aggregation (avoid single-spike noise)',
      'Feedback loop: finding → test or alert',
    ],
    architectureRelevance: {
      backend: 'Standard golden signals.',
      rag: 'Add LLM + retrieval + groundedness + token cost.',
      ai: 'Eval score + safety blocks during canary.',
      microservices: 'Cross-service trace correlation by request_id.',
    },
    problem:
      'Deploys "look fine" but users hit issues hours later. No active verification. No pre-decided rollback. Same regressions ship repeatedly.',
    whyThisApproach:
      'Active verification + pre-decided matrix + feedback loop. Deploy is not "done" until production proves it.',
    whenToUse: [
      'Every production release',
      'Every feature flag flip to a higher %',
      'Every AI prompt or model change',
    ],
    whenNotToUse: [
      'Internal demo with zero traffic',
      'Trivial typo fix in non-user content',
    ],
    input: 'Canary deploy + dashboards + rollback matrix + smoke journey definition.',
    process: [
      'Health probes pass before traffic',
      'Run smoke synthetic journey (must be green)',
      'Observe golden signals over 15–60 min',
      'For AI: observe groundedness + cost + safety blocks',
      'Aggregate over 5-min windows; require 2/3 green to promote',
      'On breach: consult rollback matrix; trigger pre-decided action',
      'Feedback: finding → permanent test or alert',
    ],
    output: 'Promote OR rollback decision + RCA (on rollback) + new regression test.',
    implementationSteps: [
      { step: 'Pick golden signals', logic: '5xx rate / p95 latency / traffic % / CPU+RAM saturation.' },
      { step: 'Pick AI signals', logic: 'LLM p95 / token rate / eval score / safety block rate.' },
      { step: 'Define smoke journey', logic: 'Critical path. Login → search → checkout. Replayed every minute.' },
      { step: 'Build rollback matrix', logic: 'Trigger × Action table; pre-decided.' },
      { step: 'Window aggregation', logic: '5-min windows; require 2/3 windows breach to act.' },
      { step: 'Auto-rollback wiring', logic: 'Argo Rollouts AnalysisTemplate or Flagger metric checks.' },
      { step: 'Feedback loop', logic: 'Post-mortem ends with a new test or alert; permanent.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# Prometheus alert rules — golden + AI signals
groups:
  - name: golden-signals
    rules:
      - alert: error_rate_high
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m])) /
          sum(rate(http_requests_total[5m])) > 0.01
        for: 5m
        annotations:
          rollback: "auto"
      - alert: latency_high
        expr: |
          histogram_quantile(0.95,
            rate(request_duration_bucket[5m])) > 2000
        for: 5m
        annotations:
          rollback: "auto"
      - alert: traffic_drop
        expr: |
          rate(http_requests_total[5m]) <
          rate(http_requests_total[5m] offset 1h) * 0.7
        for: 10m
        annotations:
          investigate: "manual"

  - name: ai-signals
    rules:
      - alert: llm_p95_high
        expr: histogram_quantile(0.95, rate(llm_duration_bucket[5m])) > 3000
        for: 5m
        annotations:
          rollback: "model fallback"
      - alert: token_cost_spike
        expr: rate(token_cost_usd[10m]) > 100
        for: 10m
        annotations:
          throttle: "tenant rate limit"
      - alert: ai_eval_drop
        expr: ai_eval_score < 0.85
        annotations:
          rollback: "block promote"
      - alert: hallucination_burst
        expr: rate(hallucination_reports[10m]) > 0.05
        annotations:
          flag_off: "disable feature"

# Synthetic monitor (k6 / Datadog / Grafana Synthetics)
# every 1 min: login → search → checkout
# every 1 min for AI: query → retrieve → generate → guardrail OK`,
    },
    realUseCase:
      'Team added PDV with rollback matrix. Black Friday: AI eval dropped 8% in canary, auto-rollback in 47s. Users never noticed. RCA found prompt template change; eval threshold tightened; new regression query added.',
    prosCons: {
      pros: [
        'Deploys become non-events',
        'MTTR minutes not hours',
        'AI quality stops drifting silently',
        'Findings turn into permanent guards',
      ],
      cons: [
        'Synthetic monitors cost money + maintenance',
        'Window tuning takes iteration',
        'AI eval set requires curation',
      ],
    },
    limitations: [
      'Novel failure modes still need human eyes',
      'Synthetic journey can\'t catch every user path',
      'AI eval can\'t catch all quality issues',
    ],
    comparison: {
      left: 'Deploy + hope',
      right: 'PDV + rollback matrix',
      rows: [
        { aspect: 'MTTR', left: 'Hours', right: 'Minutes' },
        { aspect: 'Decisions at 3 AM', left: 'Debated', right: 'Pre-decided' },
        { aspect: 'AI quality', left: 'User-discovered', right: 'Canary-caught' },
        { aspect: 'Feedback loop', left: 'Forgotten', right: 'Permanent test/alert' },
      ],
    },
    challenges: [
      'Window size tuning (too short = noisy; too long = late)',
      'AI eval flake vs real regression',
      'Synthetic monitor maintenance as UI changes',
      'Cross-service trace correlation',
    ],
    edgeCases: [
      { case: 'Single spike — not a real breach', solution: 'Window aggregation 2/3 windows required' },
      { case: 'Synthetic journey breaks because UI changed', solution: 'Auto-update from page object pattern + alert on synthetic flake' },
      { case: 'AI eval drops in flake', solution: 'Pin model version + N retries + semantic threshold' },
      { case: 'Provider 5xx during canary', solution: 'Pause + check provider; not a code issue' },
    ],
    solutions: [
      { problem: 'No rollback decision', solution: 'Pre-decided rollback matrix' },
      { problem: 'AI quality silent drift', solution: 'Eval gate + alert' },
      { problem: 'Repeated regressions', solution: 'Feedback loop: finding → permanent test' },
      { problem: 'Cost surprise', solution: 'Token cost alert + tenant rate limit' },
    ],
    bestPractices: {
      do: [
        'Pre-decide rollback matrix',
        'Synthetic monitor on critical journey',
        'Window aggregation, not single spike',
        'AI eval threshold gated',
        'Feedback loop: finding → test',
      ],
      avoid: [
        'Manual rollback debate at 3 AM',
        'Single-metric rollback triggers',
        'Synthetic journey on disposable flow',
        'Forgetting RCA → permanent test',
      ],
      optimize: [
        'Auto-rollback wiring in Argo / Flagger',
        'AI eval cached on stable inputs',
        'Smoke journey runs every 1 min',
      ],
    },
    antiPatterns: [
      'Deploy and walk away',
      'No rollback path documented',
      'No AI signals tracked',
      'Same regression every quarter',
    ],
    testing: ['Smoke journey continuous', 'Golden signals dashboards', 'AI eval CI', 'Quarterly chaos replay'],
    testTypes: ['Synthetic', 'Smoke', 'Golden signal', 'AI eval', 'Chaos replay'],
    testScenarios: [
      { scenario: '5xx > 1% for 5 min', expected: 'Auto-rollback' },
      { scenario: 'p95 > 2× baseline', expected: 'Auto-rollback' },
      { scenario: 'AI eval drop > threshold', expected: 'Block promote' },
      { scenario: 'Token cost spike', expected: 'Throttle + alert' },
      { scenario: 'Hallucination report burst', expected: 'Disable feature flag' },
    ],
    testData: [
      { type: 'Smoke fixtures', example: 'Critical journey replayed every 1 min' },
      { type: 'AI regression set', example: '100+ queries with expected groundedness' },
    ],
    debuggingChecklist: [
      'Window aggregation tuned?',
      'Smoke journey covers golden path?',
      'AI eval threshold tightened after last drift?',
      'Rollback matrix has every alert mapped?',
      'Last rollback drill = when?',
    ],
    productionIssues: [
      { issue: 'Slow degrade missed by alert', rootCause: 'Window too long; tighten' },
      { issue: 'Auto-rollback false positive', rootCause: 'Single spike triggered; require 2/3 windows' },
      { issue: 'AI hallucination user-discovered', rootCause: 'No eval gate or threshold too lax; tighten + add regression' },
    ],
    security: ['Synthetic monitor uses test account', 'Mask PII in logs', 'Rotate synthetic creds'],
    performance: ['Window 5 min', 'Auto-rollback < 60s', 'Smoke every 1 min'],
    costConsiderations: [
      'Synthetic monitor cost (test traffic)',
      'AI eval token cost (small model + cache)',
      'Auto-failover model = cost win on provider outage',
    ],
    scaling: ['Per-service dashboards', 'Shared rollback matrix template', 'Cross-service trace by request_id'],
    observability: ['Grafana dashboards', 'OTel traces', 'Argo Rollouts UI', 'AI eval over time'],
    metrics: [
      { name: 'rollback_count_per_week', example: '2' },
      { name: 'smoke_pass_rate', example: '0.99' },
      { name: 'ai_eval_score_canary', example: '0.91' },
      { name: 'mttr_minutes', example: '6' },
      { name: 'auto_rollback_count', example: '3 of 5' },
    ],
    failureModes: [
      { mode: '5xx burst', detect: 'Window aggregate > 1%', recover: 'Auto-rollback' },
      { mode: 'p95 spike', detect: 'Window aggregate > 2× baseline', recover: 'Auto-rollback' },
      { mode: 'AI eval drop', detect: 'Eval CI step fail', recover: 'Block promote' },
      { mode: 'Token cost spike', detect: 'Cost alert', recover: 'Tenant rate limit' },
      { mode: 'Hallucination burst', detect: 'User report rate', recover: 'Flag OFF' },
    ],
    tradeoffs: [
      { decision: 'Aggressive auto-rollback', tradeoff: 'False positives possible; faster MTTR' },
      { decision: 'Long observation window', tradeoff: 'More confidence; slower release' },
      { decision: 'Synthetic monitor', tradeoff: 'Cost; user-visible regressions caught' },
    ],
    decisionMatrix: [
      { option: 'Manual PDV', whenToUse: 'Small team, low traffic' },
      { option: 'Auto-rollback', whenToUse: 'High traffic, tight SLA' },
      { option: 'Auto + flag fallback', whenToUse: 'AI features with fallback model' },
    ],
    starStory: {
      situation: 'Team deploys; users complain at 3 AM about slow chatbot. No PDV; no rollback decision matrix.',
      task: 'Establish PDV + auto-rollback + AI signals.',
      action: 'Built dashboards + smoke + AI eval + rollback matrix wired to Argo. Black Friday: AI eval dropped 8% in canary; auto-rollback in 47s.',
      result: 'Users never noticed. MTTR 6h → 6 min. Change failure rate 18% → 4%. Five regressions in 6 months → permanent tests; never recurred.',
    },
    interviewTraps: [
      'No rollback decision matrix',
      'No AI signals',
      'No feedback loop into tests',
      'Single-metric trigger',
    ],
    finalScript:
      'Deploy ≠ done. Production stability proves done. Watch golden + AI signals. Pre-decide rollback matrix. Window aggregation, not single spike. Findings turn into permanent tests. MTTR drops from hours to minutes.',
    alternatives: [
      { name: 'Manual PDV', tradeoff: 'Cheap; slow MTTR' },
      { name: 'Auto-rollback', tradeoff: 'Fast MTTR; false-positive risk' },
      { name: 'Auto + flag fallback + rate limit', tradeoff: 'Best for AI; needs tuning' },
    ],
    monitoring: ['Grafana golden + AI', 'Argo Rollouts dashboard', 'AI eval trend', 'Rollback events log'],
    maturity: {
      mvp: 'Manual PDV + dashboard',
      production: 'Auto-rollback + smoke + rollback matrix',
      enterprise: 'Synthetic global + AI eval + per-tenant SLA + chaos replay quarterly',
    },
    projectFit: ['Every prod release', 'AI features', 'High-traffic SaaS', 'Regulated workloads'],
    interviewLine: 'Golden + AI signals. Pre-decided matrix. Window aggregate. Feedback into tests.',
  },
];

export default function PostReleaseDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Post-release / deployment ops (deep dive)</h1>
        <p className="design-areas-sub">
          Deployment playbook (strategy fit by risk class, immutable artifacts,
          golden rules, AI eval + cost gates) and post-deployment verification
          (golden signals + AI signals + smoke synthetic + rollback decision matrix
          + feedback loop turning every finding into a permanent test).
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
