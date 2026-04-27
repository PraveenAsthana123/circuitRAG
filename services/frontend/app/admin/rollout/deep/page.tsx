'use client';

/**
 * Deployment + rollback + health probes (deep dive).
 *
 * Two topics: rollback strategy across application + database + AI +
 * infrastructure (blue-green / canary / feature flags / DB
 * expand-contract / model rollback / IaC); and Kubernetes health
 * probes (startup/liveness/readiness) with the discipline that
 * keeps services up under deployment churn.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — ROLLBACK STRATEGY
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'rollback-strategy',
    title: '1. Rollback strategy — app + DB + AI + infra (blue-green / canary / feature flags)',
    status: 'shipped',
    coreConcept: 'Rollback covers FOUR layers: application (blue-green / canary / feature flags), database (expand → migrate → contract), AI (model + prompt versioning + fallback), infrastructure (Terraform state). Each layer has a different rollback discipline.',
    oneLiner: 'Rollback must be instant + safe + automated + tested + data-consistent. App rollback is easy; DB and AI rollback are HARD.',
    businessContext: 'Slow rollback escalates every incident. Unsafe rollback corrupts data. Without rollback discipline, every deploy is a risk; with it, deploys become routine.',
    fiveW: {
      what: 'Layered rollback: blue-green for atomic app swap, canary for staged rollout, feature flags for instant code-path disable, expand-contract for DB schema changes, model + prompt registry for AI, Terraform state versioning for infra.',
      why: 'Each layer\'s rollback is fundamentally different. Code rollback is just pointing at old image; DB rollback can corrupt data; AI rollback needs model registry; infra rollback needs state management.',
      where: 'CI/CD pipeline + IaC + model registry.',
      when: 'Day 1 of any production system.',
      who: 'SRE + DevOps + AI ops + engineers per layer.',
    },
    interview30s: 'A robust rollback strategy is not just about reverting code. It includes application, database, infrastructure, and AI components. App: blue-green or canary deployment with feature flags for instant disable. DB: backward-compatible expand → migrate → contract; up + down migrations both required + tested. AI: model + prompt versioned in registry; fallback to previous version; disable feature flag if hallucination spikes. Infra: Terraform state versioned; tested rollback. The discipline: rollback must be instant + safe + automated + tested in staging quarterly. App rollback is easy; DB and AI rollback are HARD — 80% of incidents stem from these.',
    hld: `flowchart TB
  Deploy[New deploy] --> BG[Blue-Green or Canary]
  BG --> Mon[Health monitor]
  Mon -->|healthy| Promote[Full rollout]
  Mon -->|fail| RollbackApp[App rollback]
  Promote --> DBOK[DB compat verified]
  DBOK -->|safe| Done
  DBOK -->|broken| RollbackDB[DB rollback HARD]
  AI[AI model deploy] --> AIMon[Eval gate]
  AIMon -->|fail| RollbackAI[Model registry switch]`,
    networkFlow: `flowchart LR
  Traffic[Traffic] -->|100%| Blue[Blue current]
  Traffic -.->|0%| Green[Green new]
  CI[CI deploy Green] --> Switch[Atomic switch]
  Switch --> Traffic2[Traffic 100% Green]
  Rollback -.-> Traffic`,
    flowchart: `flowchart LR
  Q[Issue detected] --> S1[Identify layer app DB AI infra]
  S1 -->|app| BGSwap[Blue-Green swap or canary halt]
  S1 -->|DB| ExpandContract[Already backward compat]
  S1 -->|AI| ModelSwap[Model registry switch]
  S1 -->|infra| TFState[Terraform state revert]
  BGSwap --> Verify
  ExpandContract --> Verify
  ModelSwap --> Verify
  TFState --> Verify`,
    sequence: `sequenceDiagram
  participant Mon as Monitor
  participant CI
  participant LB as Load Balancer
  participant Old as Old Version
  participant New as New Version
  Mon->>Mon: detect anomaly
  Mon->>CI: trigger rollback
  CI->>LB: switch to old version
  LB->>Old: route 100% traffic
  CI->>New: scale down
  CI-->>Mon: rollback complete < 60s`,
    coreLayers: [
      { layer: 'Application', responsibility: 'Blue-green / canary / feature flags. Atomic deploy + instant rollback.' },
      { layer: 'Database', responsibility: 'Expand → migrate → contract. Backward-compat changes. Up + down migrations.' },
      { layer: 'AI', responsibility: 'Model + prompt registry. Versioned. Eval gate. Fallback to previous.' },
      { layer: 'Infrastructure', responsibility: 'Terraform state versioned. Tested rollback path.' },
      { layer: 'Observability', responsibility: 'Auto-rollback triggers from health metrics + AI accuracy + cost.' },
    ],
    lld: `flowchart LR
  Mon[Health metrics] --> Trigger[Auto-rollback trigger]
  Trigger --> App[Switch traffic]
  Trigger --> Flag[Disable feature flag]
  Trigger --> Model[Model registry rollback]
  All --> Audit[Rollback audit chain]`,
    problem: 'Slow rollback escalates incidents. Data-corrupting rollback is worse than the original incident. AI rollback often forgotten.',
    whyThisApproach: 'Layered discipline matches each layer\'s rollback shape. Auto-triggers from observability remove human latency. Tested rollback (quarterly) prevents "we never tried this" surprises.',
    whenToUse: ['Every production deploy', 'Customer-facing systems', 'Anything with state'],
    whenNotToUse: ['Solo prototype'],
    input: 'New deploy + health metrics + rollback policy',
    process: ['Deploy via blue-green or canary', 'Monitor health/AI/cost metrics', 'Auto-trigger if breach', 'Switch traffic / disable flag / rollback model', 'Audit chain entry'],
    output: 'Stable previous version + rollback audit + RCA',
    alternatives: [
      { name: 'In-place deploy + manual rollback', tradeoff: 'Simple; slow; risky' },
      { name: 'Blue-green only', tradeoff: 'Atomic app; doesn\'t cover DB/AI' },
      { name: 'Layered (this)', tradeoff: 'Comprehensive; ops cost' },
    ],
    challenges: ['Backward-compat DB changes (expand-contract discipline)', 'Stateful sessions across rollback', 'AI model rollback often missed', 'Quarterly rollback drill discipline'],
    edgeCases: [
      { case: 'New version added required DB column', solution: 'Expand-only deploy first; app code uses both old + new path; contract later' },
      { case: 'In-flight requests during switch', solution: 'Drain old version + 30s grace + finish in-flight' },
      { case: 'AI model regressed in accuracy', solution: 'Model registry rollback + disable feature flag if persistent' },
    ],
    failureModes: [
      { mode: 'Rollback to vulnerable version', detect: 'CVE check at rollback', recover: 'Roll-forward with patch' },
      { mode: 'Stateful app loses sessions', detect: 'User reports', recover: 'Migrate sessions to Redis; stateless going forward' },
      { mode: 'DB rollback corrupts data', detect: 'Data validation post-rollback', recover: 'Restore from backup; never roll back DB without expand-contract' },
    ],
    monitoring: ['Auto-rollback trigger rate', 'Mean time to rollback (MTR)', 'Rollback drill pass rate quarterly', 'Per-layer rollback success'],
    testing: ['Drill: blue-green swap end-to-end', 'Drill: canary halt mid-rollout', 'Drill: feature flag disable', 'Drill: DB expand-contract reversibility', 'Drill: AI model fallback'],
    security: ['Rollback to NON-vulnerable version (CVE re-check)', 'Audit every rollback', 'Track rollback to past-secure baseline'],
    scaling: ['Per-region rollback (multi-region)', 'Per-tenant rollback (per-tenant feature flags)', 'Drain + grace at scale'],
    maturity: { mvp: 'Manual deploy + manual rollback', production: 'Blue-green + canary + feature flags + DB expand-contract + AI registry + auto-rollback', enterprise: 'Per-tenant rollback + multi-region drain + automated quarterly drill + chaos engineering' },
    limitations: ['Stateful systems make rollback hard', 'DB rollback is not free even with expand-contract', 'AI rollback needs model registry infra'],
    projectFit: ['.github/workflows/deploy.yml', 'k8s/blue-green.yaml', 'feature-flags.yml', 'migrations/<NNNN>_expand.sql + <NNNN>_contract.sql', '/admin/architect/deep — system view'],
    interviewLine: 'Rollback covers four layers: app (blue-green / canary / flags), DB (expand-contract), AI (model registry), infra (TF state). App rollback is easy; DB and AI rollback are HARD.',
    implementationSteps: [
      { step: 'App: blue-green or canary', logic: 'Atomic deploy + instant rollback via traffic swap or feature flag.' },
      { step: 'DB: expand → migrate → contract', logic: 'Backward-compat first; remove old after app rollout stable.' },
      { step: 'AI: registry + fallback', logic: 'Model + prompt versioned; eval gate; fallback to v-1 on regression.' },
      { step: 'Infra: TF state versioned', logic: 'IaC rollback path tested in staging.' },
      { step: 'Auto-trigger on metrics', logic: 'Error rate / latency / AI accuracy / cost breach → automatic rollback.' },
      { step: 'Quarterly drill', logic: 'Rehearse rollback per layer in staging.' },
    ],
    codeExample: { language: 'yaml', code: `# k8s — blue-green with auto-rollback
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: rag-svc
spec:
  replicas: 5
  strategy:
    blueGreen:
      activeService: rag-svc-active
      previewService: rag-svc-preview
      autoPromotionEnabled: false  # manual or metric-gated
      previewReplicaCount: 5
      prePromotionAnalysis:
        templates:
          - templateName: error-rate-and-latency
        args:
          - name: service
            value: rag-svc-preview
  selector:
    matchLabels: { app: rag-svc }
  template:
    spec:
      containers:
        - name: rag-svc
          image: rag-svc:\${VERSION}

---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: error-rate-and-latency
spec:
  args:
    - name: service
  metrics:
    - name: error-rate
      successCondition: result < 0.01
      provider:
        prometheus:
          query: |
            sum(rate(http_requests_total{service="{{args.service}}",status=~"5.."}[5m]))
            / sum(rate(http_requests_total{service="{{args.service}}"}[5m]))
    - name: p95-latency
      successCondition: result < 2
      provider:
        prometheus:
          query: |
            histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service="{{args.service}}"}[5m])) by (le))
    - name: ai-accuracy
      successCondition: result > 0.85
      provider:
        prometheus:
          query: 'rag_eval_accuracy{service="{{args.service}}"}'

# DB migration: expand → contract pattern
# migrations/0042_add_field.up.sql (EXPAND — backward compat)
ALTER TABLE chunks ADD COLUMN embedding_v2 VECTOR(1024) NULL;

# migrations/0042_add_field.down.sql (rollback)
ALTER TABLE chunks DROP COLUMN embedding_v2;

# After v2 deployed + stable for N days:
# migrations/0050_drop_old.up.sql (CONTRACT — remove old)
ALTER TABLE chunks DROP COLUMN embedding_v1;` },
    realUseCase: 'Pre-strategy: 4 incidents per quarter where rollback took 30+ min and 1 caused data corruption. Adopted layered strategy: Argo Rollouts blue-green, expand-contract for all DB changes, model registry with fallback, Terraform state versioning. Next quarter: 12 auto-rollbacks (caught regressions before users); MTR 47s; zero data corruption; quarterly drill in staging.',
    prosCons: {
      pros: ['Auto-rollback < 1 min', 'Zero data corruption (expand-contract)', 'AI regression caught + reversed', 'Tested in staging quarterly'],
      cons: ['Multi-layer ops cost', 'Expand-contract takes 2 deploys', 'Feature flag tech debt if not cleaned'],
    },
    comparison: { left: 'In-place + manual rollback', right: 'Layered + auto-rollback (this)', rows: [
      { aspect: 'MTR', left: '30+ min', right: '< 1 min' },
      { aspect: 'Data corruption risk', left: 'Real', right: 'Eliminated (expand-contract)' },
      { aspect: 'AI rollback', left: 'Forgotten', right: 'Registry + fallback' },
      { aspect: 'Drill rehearsal', left: 'Never', right: 'Quarterly' },
    ] },
    solutions: [
      { problem: 'Slow rollback', solution: 'Blue-green or canary + auto-trigger' },
      { problem: 'DB corruption on rollback', solution: 'Expand-contract; never break compat' },
      { problem: 'AI regression undetected', solution: 'Eval gate + model registry + fallback' },
      { problem: 'Lost sessions', solution: 'Stateless apps; sessions in Redis' },
    ],
    bestPractices: { do: ['Blue-green or canary always', 'Expand-contract DB', 'Model + prompt registry', 'Auto-rollback on metrics', 'Quarterly drill', 'Audit every rollback'], avoid: ['In-place deploys', 'Breaking DB changes in single deploy', 'Stateful local sessions', 'No drill rehearsal'], optimize: ['Per-tenant feature flags', 'Multi-region drain', 'Automated chaos drills'] },
    antiPatterns: ['Manual rollback only', 'No DB compat discipline', 'No AI rollback path', 'Stateful local sessions'],
    testTypes: ['Blue-green swap drill', 'DB expand-contract reversibility', 'Feature flag disable drill', 'AI model fallback drill', 'Multi-layer chaos drill'],
    testScenarios: [
      { scenario: 'Error rate > 1% post-deploy', expected: 'Auto-rollback < 60s' },
      { scenario: 'AI accuracy drops > 5pp', expected: 'Model registry fallback + flag disable' },
      { scenario: 'DB migration breaks app', expected: 'Should NOT happen via expand-contract; if did, restore from backup' },
      { scenario: 'Quarterly drill', expected: 'All 4 layers exercised in staging' },
    ],
    testData: [
      { type: 'Synthetic regression set', example: 'Inject errors / latency / hallucination to trigger rollback' },
      { type: 'Migration test fixtures', example: 'Up + down migrations; data preserved on rollback' },
    ],
    debuggingChecklist: ['Slow rollback? Auto-trigger config + traffic switch', 'Data corrupt? DB compat broken; restore', 'AI regression? Model registry + eval gate', 'Drill never run? Schedule quarterly'],
    productionIssues: [
      { issue: 'Rollback corrupted user data', rootCause: 'DB schema change without expand-contract. Adopted discipline.' },
      { issue: 'AI feature regressed for 2 weeks unnoticed', rootCause: 'No eval gate; no model registry. Added both.' },
      { issue: 'Rollback drill never run; emergency rollback failed', rootCause: 'No drill cadence. Quarterly drill scheduled.' },
    ],
    performance: ['Auto-rollback trigger: ~10-30s', 'Traffic switch: ~1-5s', 'Drain in-flight: ~30s grace', 'Total MTR: < 60s typical'],
    costConsiderations: ['Blue-green = 2x infra during transition', 'Canary = marginal extra', 'Drill compute: quarterly day in staging'],
    observability: ['Per-deploy auto-rollback triggers', 'MTR per incident', 'Drill pass rate quarterly', 'Rollback audit chain'],
    metrics: [
      { name: 'rollback_trigger_total{reason}', example: 'Counter; reason=error_rate|latency|ai_accuracy|manual' },
      { name: 'rollback_mtr_seconds{p}', example: 'Histogram; target p95 < 60s' },
      { name: 'rollback_drill_pass_rate{quarter}', example: 'Gauge; target = 1.0' },
    ],
    tradeoffs: [
      { decision: 'Blue-green vs canary', tradeoff: 'BG = atomic; canary = staged + lower risk' },
      { decision: 'Auto-rollback strictness', tradeoff: 'Strict = fast revert + flap risk; loose = stable + slow detect' },
      { decision: 'Drill cadence', tradeoff: 'Frequent = drift-resilient; cost' },
    ],
    decisionMatrix: [
      { option: 'Layered (this)', whenToUse: 'Production' },
      { option: 'Blue-green only', whenToUse: 'Stateless app, simple DB' },
      { option: 'In-place + manual', whenToUse: 'Hackathon prototype' },
    ],
    starStory: {
      situation: 'Rollback once corrupted user data; team avoided rollback after that, instead fixing forward — slower MTR.',
      task: 'Make rollback safe + fast.',
      action: 'Adopted layered: blue-green + expand-contract + AI registry + TF state. Auto-rollback on metrics. Quarterly drill.',
      result: 'MTR 30 min → 47s. Zero corruption. 12 auto-rollbacks next quarter caught regressions invisibly.',
    },
    interviewTraps: ['Manual rollback only', 'Breaking DB changes', 'No AI rollback path', 'No drill'],
    finalScript: 'A robust rollback strategy is not just about reverting code — it includes application, database, infrastructure, and AI components. App: blue-green or canary deployment with feature flags for instant disable. DB: backward-compatible expand → migrate → contract; up + down migrations both required + tested. AI: model + prompt versioned in registry; fallback to previous; eval gate. Infra: Terraform state versioned. Auto-rollback triggers from observability metrics. Quarterly drill in staging. The discipline: rollback must be instant + safe + automated + tested. App rollback is easy; DB and AI rollback are HARD — and that\'s where 80% of incidents stem from.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — KUBERNETES HEALTH PROBES
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'k8s-health-probes',
    title: '2. Kubernetes health probes — startup / liveness / readiness discipline',
    status: 'shipped',
    coreConcept: 'Three probes answer different lifecycle questions: startup = "can the app finish booting?", liveness = "should K8s restart me?", readiness = "should K8s send traffic to me?". Mixing them causes restart storms.',
    oneLiner: 'Liveness restarts. Readiness routes traffic. Startup protects slow boot. Mixing them = restart storm.',
    businessContext: 'Wrong probe config takes services down during DB blips, prevents slow-startup AI services from booting, or routes traffic to broken pods. Each probe has a precise role.',
    fiveW: {
      what: 'Three Kubernetes probes: startupProbe (boot tolerance), livenessProbe (process health → restart), readinessProbe (dependency health → traffic).',
      why: 'Mixing them causes outages. DB check in liveness = restart storm during DB blip. No readiness = broken pods get traffic. No startup = slow-boot apps killed.',
      where: 'Per-pod in K8s deployment YAML.',
      when: 'Day 1 of any K8s workload.',
      who: 'SRE + DevOps + service owner.',
    },
    interview30s: 'Three probes for three lifecycle questions. Startup probe protects slow initialization (model load, cache warm, schema migration). Liveness probe is a DUMB check — only internal process health; if it fails, K8s restarts. Readiness probe is a SMART check — verifies dependencies (DB, cache, vector DB, model loaded); if it fails, K8s removes pod from traffic but does NOT restart. The classic mistake is putting DB check in liveness — DB blip cascades into restart storm. For AI services, startup tolerance must accommodate model load (often 30-90s); readiness should check vector DB + model + risk engine.',
    hld: `flowchart TB
  Pod[Pod starting] --> Startup[Startup probe]
  Startup -->|pass| Live[Liveness ongoing]
  Startup -->|fail many| Restart[Restart pod]
  Live -->|fail| Restart
  Live -->|pass| Ready[Readiness ongoing]
  Ready -->|pass| Traffic[Receives traffic]
  Ready -->|fail| Drain[Removed from traffic]
  Drain -.recover.-> Ready`,
    networkFlow: `flowchart LR
  K8s[K8s control plane] -->|HTTP| Pod
  Pod --> StartupEP[/health/startup]
  Pod --> LiveEP[/health/live]
  Pod --> ReadyEP[/health/ready]
  ReadyEP --> Deps[Dependency checks]
  Deps --> DB
  Deps --> Cache
  Deps --> Model[Model loaded]`,
    flowchart: `flowchart LR
  Q[New pod] --> Boot[Startup phase]
  Boot --> Live[Liveness ongoing]
  Live --> Ready[Readiness ongoing]
  Ready -->|true| Serving
  Ready -->|false| Drain
  Live -->|false| Restart
  Boot -->|never finishes| RestartStartup`,
    sequence: `sequenceDiagram
  participant K as Kubelet
  participant App
  K->>App: GET /health/startup
  App-->>K: 503 starting
  K->>App: retry every 10s
  App-->>K: 200 started
  K->>App: GET /health/live
  App-->>K: 200 alive
  K->>App: GET /health/ready
  App->>App: check DB cache model
  App-->>K: 200 ready
  K->>App: route traffic`,
    coreLayers: [
      { layer: 'Startup probe', responsibility: 'App finished booting? Higher failureThreshold; protects slow init.' },
      { layer: 'Liveness probe', responsibility: 'Process alive + responsive? DUMB check; restart on fail.' },
      { layer: 'Readiness probe', responsibility: 'Dependencies ready? SMART check; remove from traffic on fail.' },
      { layer: 'Graceful shutdown', responsibility: 'SIGTERM → readiness=false → finish in-flight → exit before grace.' },
      { layer: 'Sidecar option', responsibility: 'Independent health checker for critical services.' },
    ],
    lld: `flowchart LR
  StartupReq[Startup HTTP] --> Flag[startup_complete flag]
  LiveReq[Liveness HTTP] --> Process[Process alive check]
  ReadyReq[Readiness HTTP] --> DepCheck[DB cache model checks]
  DepCheck -->|all ok| Ready
  DepCheck -->|any fail| NotReady`,
    problem: 'Mixed probe semantics cause outages: DB check in liveness restarts pods during DB blip; no readiness routes traffic to broken pods; no startup kills slow-boot AI.',
    whyThisApproach: 'Three separate endpoints encode three lifecycle questions. Each has a distinct failure response.',
    whenToUse: ['Every K8s workload', 'Especially AI services with slow boot'],
    whenNotToUse: ['Bare-metal non-orchestrated'],
    input: 'Deployment YAML + app endpoints',
    process: ['Implement /health/startup with boot flag', '/health/live with process check only', '/health/ready with dependency checks', 'YAML probe config tuned per service', 'Graceful shutdown SIGTERM handler'],
    output: 'Stable pod lifecycle + zero restart storms',
    alternatives: [
      { name: 'Single /health endpoint for all', tradeoff: 'Simple; mixes semantics; restart storms' },
      { name: 'Three endpoints (this)', tradeoff: 'Best practice; ops disciplined' },
      { name: 'Sidecar health checker', tradeoff: 'Independent; complexity' },
    ],
    challenges: ['Tuning failureThreshold + periodSeconds per service', 'Graceful shutdown discipline', 'Slow-boot AI tolerance'],
    edgeCases: [
      { case: 'AI model takes 90s to load', solution: 'startupProbe failureThreshold=30 + periodSeconds=10 = 5min tolerance' },
      { case: 'DB has 30s blip', solution: 'Readiness drains traffic; liveness STAYS GREEN (DON\'T restart)' },
      { case: 'App webserver hangs', solution: 'Liveness fails → restart' },
    ],
    failureModes: [
      { mode: 'DB check in liveness causes restart storm', detect: 'Restart count spike during DB issues', recover: 'Move DB check to readiness only' },
      { mode: 'No readiness; broken pods receive traffic', detect: 'Errors on freshly-started pods', recover: 'Add readiness with dep checks' },
      { mode: 'No startup; slow-boot AI killed', detect: 'CrashLoopBackOff on first deploy', recover: 'Add startup probe with tolerance' },
    ],
    monitoring: ['Pod restart count', 'Readiness flap rate', 'Per-probe failure rate', 'Time to ready post-deploy'],
    testing: ['Drill: DB blip → readiness drains, liveness stays green, no restart', 'Drill: app hang → liveness fails + restart', 'Drill: slow boot → startup tolerance accommodates', 'Drill: graceful shutdown finishes in-flight'],
    security: ['Probe endpoints unauthenticated (Kubelet local)', 'No PII in probe response', 'Rate-limit if exposed'],
    scaling: ['Per-replica probe', 'Sidecar option for critical services', 'Cross-AZ readiness consistency'],
    maturity: { mvp: 'Single /health endpoint', production: 'Three probes + graceful shutdown', enterprise: 'Sidecar health + cross-AZ readiness + automated probe-tuning' },
    limitations: ['Probe latency overhead per pod', 'False-fail risk if too strict'],
    projectFit: ['k8s/<service>-deployment.yaml', 'app/health.py — three endpoints', 'docs/runbooks/health-probes.md'],
    interviewLine: 'Liveness decides restart, readiness decides traffic, startup protects slow boot. Mixing them causes restart storms.',
    implementationSteps: [
      { step: 'Three endpoints', logic: '/health/startup, /health/live, /health/ready.' },
      { step: 'Startup boot flag', logic: 'Set startup_complete=True after init; protects slow load.' },
      { step: 'Liveness DUMB check', logic: 'Only internal process health. NO DB / external checks.' },
      { step: 'Readiness SMART check', logic: 'DB + cache + model + dependencies. Drain on fail.' },
      { step: 'Graceful shutdown', logic: 'SIGTERM → readiness=false → finish in-flight → exit.' },
      { step: 'YAML config', logic: 'failureThreshold + periodSeconds tuned per service.' },
      { step: 'AI service tolerance', logic: 'Startup probe accommodates model load (30-90s).' },
    ],
    codeExample: { language: 'yaml', code: `# k8s/rag-svc.yaml — three probes done right
apiVersion: apps/v1
kind: Deployment
metadata: { name: rag-svc }
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
      - name: rag-svc
        image: rag-svc:latest
        ports: [{ containerPort: 8080 }]

        # Startup: protect slow boot (model load 30-90s)
        startupProbe:
          httpGet: { path: /health/startup, port: 8080 }
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 30        # 30 × 10s = 5min tolerance

        # Liveness: DUMB process check; restart on fail
        livenessProbe:
          httpGet: { path: /health/live, port: 8080 }
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3         # only restart if 3 in a row fail
          # NEVER put DB or external checks here

        # Readiness: SMART dependency check; drain on fail
        readinessProbe:
          httpGet: { path: /health/ready, port: 8080 }
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 2         # drain after 2 consecutive fails

---
# FastAPI implementation:
# app/health.py
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

app = FastAPI()
startup_complete = False
shutdown_started = False

@app.on_event("startup")
async def boot():
    global startup_complete
    await load_model()        # 30-90s
    await warm_cache()
    startup_complete = True

@app.get("/health/startup")
def startup():
    if startup_complete: return {"status": "started"}
    return JSONResponse(status_code=503, content={"status": "starting"})

@app.get("/health/live")
def live():
    # DUMB: only process check; no external deps
    return {"status": "alive"}

@app.get("/health/ready")
async def ready():
    if shutdown_started:
        return JSONResponse(status_code=503, content={"status": "draining"})
    # SMART: check actual dependencies
    deps = {
        "db": await check_db(),
        "vector_db": await check_qdrant(),
        "model_loaded": model_is_ready(),
        "cache": await check_redis(),
    }
    if all(deps.values()):
        return {"status": "ready", "deps": deps}
    return JSONResponse(status_code=503, content={"status": "not_ready", "deps": deps})

# Graceful shutdown — SIGTERM handler
import signal
def graceful_shutdown(signum, frame):
    global shutdown_started
    shutdown_started = True   # readiness now returns 503; K8s drains
    # Then app finishes in-flight requests + exits
signal.signal(signal.SIGTERM, graceful_shutdown)` },
    realUseCase: 'AI service with single /health endpoint that did DB check. DB had a 30s blip → all replicas restarted simultaneously → 5-min total outage. Migrated to three-probe pattern: liveness only checks process, readiness drains on DB blip but pods stay alive. Next DB blip: readiness drained traffic for 30s, no restarts, recovered cleanly.',
    prosCons: {
      pros: ['No restart storms during dep blips', 'Slow-boot AI accommodated', 'Broken pods don\'t receive traffic', 'Graceful shutdown'],
      cons: ['Three endpoints to maintain', 'Probe tuning per service', 'Graceful-shutdown discipline'],
    },
    comparison: { left: 'Single /health endpoint', right: 'Three probes (this)', rows: [
      { aspect: 'Restart storms', left: 'Common', right: 'Eliminated' },
      { aspect: 'Slow boot tolerance', left: 'No', right: 'Startup probe' },
      { aspect: 'Dependency-based traffic', left: 'No', right: 'Readiness drains' },
      { aspect: 'Graceful shutdown', left: 'Manual', right: 'SIGTERM → readiness=false' },
    ] },
    solutions: [
      { problem: 'Restart storm on DB blip', solution: 'Move DB check to readiness only' },
      { problem: 'Slow AI boot kills pod', solution: 'Startup probe with 5min tolerance' },
      { problem: 'Broken pod gets traffic', solution: 'Readiness with dep checks' },
      { problem: 'In-flight requests dropped', solution: 'Graceful shutdown + drain' },
    ],
    bestPractices: { do: ['Three separate endpoints', 'Liveness DUMB (no deps)', 'Readiness SMART (deps)', 'Startup tolerance for slow boot', 'Graceful shutdown SIGTERM'], avoid: ['DB check in liveness', 'Single /health endpoint', 'No startup probe on slow services', 'No graceful shutdown'], optimize: ['Sidecar health checker for critical services', 'Cached dep check (1-2s)', 'Cross-AZ readiness consistency'] },
    antiPatterns: ['Single endpoint for all probes', 'DB in liveness', 'No readiness', 'No graceful shutdown'],
    testTypes: ['DB blip drill', 'Slow boot drill', 'App hang drill', 'Graceful shutdown drill', 'Sidecar drill'],
    testScenarios: [
      { scenario: 'DB 30s blip', expected: 'Readiness drains; liveness stays green; no restart' },
      { scenario: 'AI model takes 60s to load', expected: 'Startup probe tolerates; ready when complete' },
      { scenario: 'Pod webserver hangs', expected: 'Liveness fails → restart' },
      { scenario: 'SIGTERM received', expected: 'Readiness=false → drain → in-flight done → exit' },
    ],
    testData: [
      { type: 'Synthetic dep failure fixture', example: 'Toxiproxy on DB or Vector DB' },
      { type: 'Slow-boot AI fixture', example: 'Model load delay simulation' },
    ],
    debuggingChecklist: ['Restart loop? Check liveness for external deps', 'Pod never ready? Startup tolerance + readiness deps', 'Lost in-flight? SIGTERM handler + grace period'],
    productionIssues: [
      { issue: 'DB blip caused 5-min outage', rootCause: 'DB check in liveness; restart storm. Migrated to three-probe.' },
      { issue: 'AI service CrashLoopBackOff on first deploy', rootCause: 'No startup probe; default kill at 30s. Added startup with 5min tolerance.' },
      { issue: 'Lost ~50 in-flight requests on every deploy', rootCause: 'No graceful shutdown. SIGTERM handler added.' },
    ],
    performance: ['Probe overhead: ~1-5ms p95 each', 'Startup boot: 30-90s for AI services', 'Graceful drain: 30s grace'],
    costConsiderations: ['Negligible compute', 'Sidecar option: ~50MB RAM per pod'],
    observability: ['Pod restart count', 'Readiness flap', 'Per-probe failure rate', 'Time to ready'],
    metrics: [
      { name: 'pod_restart_total{reason}', example: 'Counter; spike = liveness misconfig' },
      { name: 'pod_readiness_flap_total{pod}', example: 'Counter; high = readiness too strict' },
      { name: 'pod_time_to_ready_seconds', example: 'Histogram; trend per deploy' },
    ],
    tradeoffs: [
      { decision: 'Liveness strictness', tradeoff: 'Strict = catches hangs; restart storm risk' },
      { decision: 'Readiness deps', tradeoff: 'More deps = accurate; flap risk' },
      { decision: 'Startup tolerance', tradeoff: 'High = slow-boot OK; mask issues' },
    ],
    decisionMatrix: [
      { option: 'Three probes (this)', whenToUse: 'All K8s workloads' },
      { option: 'Sidecar health', whenToUse: 'Critical services + complex hangs' },
    ],
    starStory: {
      situation: 'Single /health endpoint with DB check; DB blip caused 5-min outage from restart storm.',
      task: 'Eliminate restart storms.',
      action: 'Three-probe pattern: liveness DUMB process check, readiness SMART dep check, startup tolerance for AI model load. Graceful shutdown SIGTERM handler.',
      result: 'Next DB blip: readiness drained, no restarts, cleaned up in 30s. Pattern adopted across 12 services.',
    },
    interviewTraps: ['DB check in liveness', 'Single /health endpoint', 'No startup probe', 'No graceful shutdown'],
    finalScript: 'I separate startup, liveness, and readiness endpoints because they answer different lifecycle questions. Liveness should trigger restart only when the app is broken — DUMB check, only internal process health, never DB or external deps. Readiness should control traffic based on dependency health — SMART check, drains pod from load balancer if DB or vector DB unreachable, does NOT restart. Startup should protect slow initialization with higher failureThreshold. For AI services with 30-90s model load, startup tolerance is critical. Graceful shutdown via SIGTERM handler sets readiness=false and finishes in-flight requests before exit. The most common mistake — DB check in liveness — turns a DB blip into a restart storm.',
  },
];

export default function RolloutDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Deployment + rollback + health probes (deep dive)</h1>
        <p className="design-areas-sub">
          Layered rollback discipline (app + DB + AI + infra) with blue-green / canary /
          feature flags / expand-contract / model registry. Plus Kubernetes three-probe
          pattern (startup / liveness / readiness) — the discipline that prevents
          restart storms during dependency blips and accommodates slow-boot AI services.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
