'use client';

/**
 * CI/CD + TDD (deep dive).
 *
 * Two topics: CI/CD master pipeline (build once, fail-fast gates,
 * immutable artifacts, DevSecOps + AI eval gates), and the TDD
 * framework extended for microservices + AI (RGR cycle, F.I.R.S.T.,
 * contract tests, AI evaluation-based testing).
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — CI/CD master pipeline
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'cicd-master-pipeline',
    title: '1. CI/CD master pipeline — build once, fail-fast gates, DevSecOps + AI eval',
    status: 'shipped',
    coreConcept:
      'CI/CD is a control system, not a script. Code → Build → Test → Secure → Package → Release → Deploy → Verify → Observe → Rollback. Speed (fast feedback), safety (gates + scans), consistency (build once, same artifact to staging + prod), traceability (audit every step). For AI: add prompt + eval + safety + cost + latency gates before promote.',
    oneLiner: 'Build once. Fail fast. Sign and scan everything. Auto-rollback on metric breach.',
    businessContext:
      'A team rebuilds the Docker image per environment. Staging passes; prod 5xx burst. Root cause: different base image SHA. Fix: build once, immutable tag, same image deploys to all envs. CI/CD discipline saves the next outage.',
    fiveW: {
      what: 'Standardized pipeline that lints, tests, scans, builds once, signs, deploys with canary/blue-green, verifies, and auto-rolls back.',
      why: 'Manual deploy = drift. Drift = outage. Pipeline removes humans from the steady state path.',
      where: 'Every repo. Reusable workflows or platform abstractions.',
      when: 'Every PR (CI), every release (CD).',
      who: 'Platform team owns the pipeline; product teams use it.',
    },
    interview30s:
      'I design CI/CD as fast, secure, deterministic. CI fails fast on lint, unit, SAST, SCA, build. CD deploys via canary or blue-green with auto-rollback on metric breach. The artifact is immutable + signed + has SBOM. For AI I add eval gates: prompt regression tests, groundedness, safety, latency, token cost. Build once; same image staging + prod; SHA tagged.',
    hld: `flowchart LR
  Dev[Commit] --> CI[CI: lint + unit + SAST + SCA]
  CI --> Build[Build once + sign + SBOM]
  Build --> Reg[Registry immutable tag]
  Reg --> CDStg[CD: deploy staging]
  CDStg --> Smoke[Smoke + integration]
  Smoke --> CDProd[Canary or blue-green prod]
  CDProd --> Ver[Health + smoke + golden signals]
  Ver --> Promote{Pass?}
  Promote -- yes --> Full[Full rollout]
  Promote -- no --> RB[Auto rollback]`,
    flowchart: `flowchart TD
  Start[Commit] --> Pre[Pre-commit hooks: lint + secret scan]
  Pre --> Lint[CI lint]
  Lint --> Unit[Unit tests]
  Unit --> Sast[SAST + SCA]
  Sast --> Bld[Build Docker once]
  Bld --> Scan[Container scan]
  Scan --> Sig[Sign + SBOM]
  Sig --> Push[Push to registry]
  Push --> Stg[Deploy staging]
  Stg --> SmkS[Smoke + integration]
  SmkS --> Approve{Manual approval?}
  Approve -- if needed --> Cny[Canary prod]
  Approve -- auto --> Cny
  Cny --> Mon[Monitor 15-60 min]
  Mon --> Rollout{All green?}
  Rollout -- yes --> Full[Full rollout 100 percent]
  Rollout -- no --> Rb[Auto rollback]`,
    sequence: `sequenceDiagram
  participant Dev
  participant CI
  participant Reg as Registry
  participant CD
  participant Prod
  participant Mon as Monitor
  Dev->>CI: push commit
  CI->>CI: lint + unit + SAST + SCA
  CI->>CI: build image once
  CI->>Reg: push immutable tag
  CD->>Reg: pull tag
  CD->>Prod: canary 10 percent
  Prod-->>Mon: golden signals
  Mon-->>CD: pass or fail
  alt pass
    CD->>Prod: ramp to 100 percent
  else fail
    CD->>Prod: rollback
  end`,
    coreLayers: [
      { layer: 'Source', responsibility: 'Pre-commit hooks: format, lint, secret scan.' },
      { layer: 'CI', responsibility: 'Lint + unit + SAST + SCA + build + sign + SBOM.' },
      { layer: 'Registry', responsibility: 'Immutable tags. Vulnerability scan on push.' },
      { layer: 'CD', responsibility: 'Deploy staging → smoke → canary prod → verify → promote or rollback.' },
      { layer: 'Observability', responsibility: 'Metrics + logs + traces + DORA dashboards.' },
    ],
    lld: `classDiagram
  class Pipeline {
    +ci_jobs: Job[]
    +cd_jobs: Job[]
    +gates: Gate[]
    +artifact: Artifact
  }
  class Gate {
    +name
    +blocking
    +threshold
  }
  class Artifact {
    +sha
    +signature
    +sbom
    +scan_report`,
    coreBuildingBlocks: [
      'Pre-commit: format + secret scan',
      'CI gates: lint, unit, SAST, SCA, build (parallel where possible)',
      'Build once: same image to all environments',
      'Sign with cosign / Sigstore + SBOM (CycloneDX)',
      'CD: staging → canary → full rollout',
      'Auto-rollback triggers from metrics',
      'AI gates: prompt tests + eval + safety + latency + cost',
      'DORA metrics: deploy freq, lead time, change failure rate, MTTR',
    ],
    architectureRelevance: {
      backend: 'Pipeline shape applies to every service.',
      rag: 'Add eval + groundedness + safety gates before LLM promotes.',
      ai: 'Prompt + model + eval = first-class gates.',
      microservices: 'Build-once + immutable tag prevents drift across services.',
    },
    problem: 'Manual deploys drift. Different image per env. No rollback path. Slow CI → devs bypass.',
    whyThisApproach:
      'Pipeline removes humans from steady state. Same image everywhere. Auto-rollback turns "incident" into "blip".',
    whenToUse: [
      'Every production system',
      'Any code shipped to users',
      'Any AI feature with prompt/model changes',
    ],
    whenNotToUse: [
      'One-off scripts',
      'Local-only research',
      'Disposable demos',
    ],
    input: 'Commit + secrets + infra credentials + scan tool licenses.',
    process: [
      'Pre-commit: format + lint + secret scan',
      'CI: lint + unit + SAST + SCA in parallel',
      'Build Docker image once + scan + sign + SBOM',
      'Push immutable tag to registry',
      'Deploy staging + integration smoke',
      '(Optional) manual approval gate',
      'Canary or blue-green to prod',
      'Health checks + smoke + golden signals (15–60 min observation)',
      'Auto-promote on green; auto-rollback on breach',
    ],
    output: 'Deployed artifact + audit trail + DORA metric updates + (on failure) rollback record + RCA ticket.',
    implementationSteps: [
      { step: 'Add pre-commit hooks', logic: 'Gitleaks + ruff/eslint format. Stops 80% of style noise + secret leaks.' },
      { step: 'Parallelize CI', logic: 'lint + unit + SAST + SCA same matrix. Target < 10 min total.' },
      { step: 'Build once', logic: 'Single docker build → tag with $GIT_SHA → push.' },
      { step: 'Sign + SBOM', logic: 'cosign sign + cyclonedx generate. Required for SLSA L3.' },
      { step: 'Canary deploy', logic: 'Argo Rollouts: 10% → pause 5 min → 50% → pause 10 min → 100%.' },
      { step: 'Health + smoke', logic: '/health/ready before traffic; smoke covers golden user journey.' },
      { step: 'Auto-rollback', logic: 'Prom alert breach (5xx / p95 / AI eval drop) → flip back to previous tag.' },
      { step: 'AI eval gate', logic: 'Run regression eval set; promote only if score within delta.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# .github/workflows/ci-cd.yml — fast, secure, build-once
name: ci-cd
on:
  push:
    branches: [main]

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - name: Lint
        run: ruff check . && ruff format --check .
      - name: Unit tests + coverage
        run: pytest -q --cov=src --cov-fail-under=80
      - name: SAST
        run: bandit -r src/
      - name: SCA
        run: pip-audit -r requirements.txt
      - name: Build
        run: |
          docker build -t app:\${{ github.sha }} .
          trivy image app:\${{ github.sha }}
      - name: Sign + SBOM
        run: |
          cosign sign --yes registry/app:\${{ github.sha }}
          cyclonedx-py -i requirements.txt -o sbom.json
      - name: Push
        run: |
          docker tag app:\${{ github.sha }} registry/app:\${{ github.sha }}
          docker push registry/app:\${{ github.sha }}

  cd-staging:
    needs: ci
    runs-on: ubuntu-latest
    steps:
      - run: argocd app sync app-staging --prune

  ai-eval:
    needs: cd-staging
    runs-on: ubuntu-latest
    steps:
      - name: AI regression eval
        run: |
          python eval/regression.py --threshold 0.85
          # gates: groundedness, safety, latency, token cost

  cd-prod-canary:
    needs: ai-eval
    runs-on: ubuntu-latest
    steps:
      - run: argocd app sync app-prod --strategy canary
      - run: ./scripts/wait_for_canary_health.sh 600  # 10 min observe`,
    },
    realUseCase:
      'A team had 7 different images running in prod (bad rebuilds). Switched to build-once + SHA tag. Cut deploy variance to zero. DORA: deploy freq 1/wk → 5/day; change failure rate 18% → 4%; MTTR 6h → 12 min after auto-rollback added.',
    prosCons: {
      pros: [
        'Fast feedback (< 10 min CI)',
        'No drift between envs',
        'Auto-rollback bounds incident impact',
        'Audit trail comes free',
      ],
      cons: [
        'Initial setup is multi-week',
        'Platform team needed for shared workflow maintenance',
        'AI eval gates take time + resources',
      ],
    },
    limitations: [
      'Long CI = devs bypass (target < 10 min)',
      'Flaky tests poison trust in pipeline',
      'External services + dependencies may be CI rate-limited',
    ],
    comparison: {
      left: 'Ad-hoc deploy',
      right: 'CI/CD pipeline',
      rows: [
        { aspect: 'Drift', left: 'Frequent', right: 'Eliminated' },
        { aspect: 'MTTR', left: 'Hours', right: 'Minutes' },
        { aspect: 'Audit trail', left: 'Manual', right: 'Automatic' },
        { aspect: 'Confidence', left: 'Hopeful', right: 'Data-driven' },
        { aspect: 'AI eval', left: 'Manual', right: 'Gated automatically' },
      ],
    },
    challenges: [
      'CI duration creep — target < 10 min always',
      'Test flakiness — quarantine + fix, never disable silently',
      'AI eval determinism — use semantic + threshold, not exact match',
      'Secret rotation — pipeline must rotate without downtime',
      'Rollback safety on DB schema changes',
    ],
    edgeCases: [
      { case: 'Hotfix bypasses canary', solution: 'Hotfix branch goes through same pipeline + skip canary only on declared P0' },
      { case: 'Long-running migration', solution: 'Migration in own CI step before app deploy; rollback plan required' },
      { case: 'AI eval flakes', solution: 'Pin model version in CI; use semantic similarity + N retries' },
      { case: 'Canary metric noise', solution: 'Window average over 5 min; require 2/3 windows breach to rollback' },
    ],
    solutions: [
      { problem: 'Slow CI', solution: 'Parallelize + cache deps + smaller test layers' },
      { problem: 'Flaky tests', solution: 'Quarantine list + weekly fix budget' },
      { problem: 'Drift between envs', solution: 'Build once + immutable SHA tag' },
      { problem: 'Manual rollback too slow', solution: 'Auto-rollback on metric breach' },
      { problem: 'AI quality regression', solution: 'Eval gate with regression threshold' },
    ],
    bestPractices: {
      do: [
        'Build once + SHA tag',
        'Sign + SBOM every artifact',
        'Parallel CI < 10 min',
        'Canary or blue-green for prod',
        'Auto-rollback on breach',
        'AI eval gate before promote',
      ],
      avoid: [
        'Rebuilding per environment',
        'No rollback path',
        'Manual approval as default for steady state',
        'Skipping security gates',
      ],
      optimize: [
        'Cache deps + Docker layers',
        'Test sharding across runners',
        'Reusable workflows for shared steps',
      ],
    },
    antiPatterns: [
      'Friday deploys without on-call',
      '"It works on staging" rebuild for prod',
      'Long CI without parallelization',
      'No rollback playbook',
      'No AI eval — ship and pray',
    ],
    testing: ['Lint + unit + SAST + SCA + container scan', 'Smoke + integration in staging', 'AI eval regression', 'Canary metrics observation'],
    testTypes: ['Unit', 'Integration', 'Contract', 'Smoke', 'AI eval', 'Security', 'Performance'],
    testScenarios: [
      { scenario: 'CI < 10 min', expected: 'Fast feedback' },
      { scenario: 'Bad commit', expected: 'CI fails before merge' },
      { scenario: '5xx burst in canary', expected: 'Auto-rollback < 60s' },
      { scenario: 'AI eval drop > 5%', expected: 'Promote blocked' },
    ],
    testData: [
      { type: 'Sample fixtures', example: 'Real-shape test corpus checked in' },
      { type: 'AI eval set', example: '100+ regression queries with expected groundedness' },
    ],
    debuggingChecklist: [
      'CI duration trend rising?',
      'Image SHA matches across envs?',
      'Cosign verify before deploy?',
      'AI eval threshold tuned?',
      'Auto-rollback last triggered when?',
    ],
    productionIssues: [
      { issue: 'Different image SHA in prod vs staging', rootCause: 'Two builds; switch to build-once' },
      { issue: 'CI takes 25 min, devs bypass', rootCause: 'No parallelization; shard tests + cache deps' },
      { issue: 'AI promote despite eval drop', rootCause: 'Threshold too lax; tighten + alert on regression' },
    ],
    security: ['SAST + SCA on every PR', 'Secret scan pre-commit', 'Sign + SBOM every artifact', 'Cosign verify before deploy'],
    performance: ['CI < 10 min', 'CD < 30 min including canary', 'Rollback < 60s'],
    costConsiderations: [
      'Runner minutes — cache aggressively',
      'AI eval cost — pin small eval model',
      'Registry storage — retention policy on SHA tags',
    ],
    scaling: ['Reusable workflows', 'Shared platform pipelines', 'Per-repo overlay only for unique steps'],
    observability: ['DORA dashboards', 'CI duration histogram', 'Eval score over time', 'Rollback events'],
    metrics: [
      { name: 'deploy_frequency_per_day', example: '5' },
      { name: 'lead_time_minutes', example: '45' },
      { name: 'change_failure_rate_percent', example: '4' },
      { name: 'mttr_minutes', example: '12' },
      { name: 'ci_duration_p95_minutes', example: '8' },
      { name: 'ai_eval_score', example: '0.91' },
    ],
    failureModes: [
      { mode: 'CI flake', detect: 'Same test fails ≥ 3 times in 7 days', recover: 'Quarantine + fix budget' },
      { mode: 'Canary metric breach', detect: '5xx > 1% or p95 > 2× baseline', recover: 'Auto-rollback' },
      { mode: 'AI eval drop', detect: 'Regression score < threshold', recover: 'Block promote; investigate prompt/model change' },
      { mode: 'Registry outage', detect: 'Pull fails', recover: 'Mirror registry + cached pull' },
    ],
    tradeoffs: [
      { decision: 'Build once', tradeoff: 'Same artifact = predictable; constraint on env-specific config' },
      { decision: 'Auto-rollback aggressive', tradeoff: 'False positives possible; outweighed by faster MTTR' },
      { decision: 'AI eval in CI', tradeoff: 'Adds 2–5 min; saves user-visible regressions' },
    ],
    decisionMatrix: [
      { option: 'Trunk-based + main', whenToUse: 'Standard team; small batches' },
      { option: 'Release branch', whenToUse: 'Regulated systems with formal cutover' },
      { option: 'GitOps (ArgoCD/Flux)', whenToUse: 'K8s-native; declarative deploys' },
    ],
    starStory: {
      situation: 'Team had 7 different prod image SHAs from rebuilds. Random outages.',
      task: 'Eliminate drift; speed up deploys.',
      action: 'Migrated to build-once + SHA tag + cosign + Argo Rollouts canary + auto-rollback. Added AI eval gate.',
      result: 'Deploy freq 1/wk → 5/day. Change failure rate 18% → 4%. MTTR 6h → 12 min. DORA quartile elite.',
    },
    interviewTraps: [
      'Saying "we have CI" without DORA metrics',
      'No rollback path mentioned',
      'No AI eval gate for AI features',
      'Manual approval as steady state',
    ],
    finalScript:
      'Pipeline is a control system. Fast (< 10 min), safe (gates + scans), consistent (build once), traceable (signed + SBOM). For AI: eval + safety + cost + latency gates. Auto-rollback on metric breach. DORA elite is the target.',
    alternatives: [
      { name: 'Jenkins', tradeoff: 'Powerful + flexible; ops burden' },
      { name: 'GitHub Actions', tradeoff: 'Native to GH; vendor lock' },
      { name: 'GitLab CI', tradeoff: 'All-in-one; tighter integration' },
      { name: 'ArgoCD + GH Actions', tradeoff: 'GitOps + push CI; best of both' },
    ],
    monitoring: ['DORA dashboards', 'CI/CD success rate', 'Rollback events', 'Eval score trend'],
    maturity: {
      mvp: 'CI: lint + unit + build + push',
      production: 'Add SAST + SCA + canary + auto-rollback + DORA',
      enterprise: 'Add AI eval + SBOM + signing + multi-region + GitOps',
    },
    projectFit: ['Every production system', 'AI features', 'Regulated environments', 'Multi-team platforms'],
    interviewLine: 'Build once. Sign + SBOM. Canary + auto-rollback. AI eval gate. DORA elite.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — TDD framework (extended for microservices + AI)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'tdd-framework-ai',
    title: '2. TDD framework — RGR + F.I.R.S.T. + contract tests + AI evaluation tests',
    status: 'shipped',
    coreConcept:
      'TDD is a design tool, not a testing tool. Red → Green → Refactor forces specification before code. F.I.R.S.T. (Fast, Independent, Repeatable, Self-validating, Thorough) protects unit-test trust. For microservices, contract tests prevent API breakage. For AI, replace exact-match with evaluation-based testing: groundedness, semantic similarity, safety, cost, latency. Hard-to-test code = bad design — fix the code, not the test.',
    oneLiner: 'Red-Green-Refactor at unit level. Contract tests at service level. Evaluation tests at AI level.',
    businessContext:
      'A team adds AI without TDD; user reports "AI invents data". Without test discipline, no regression catches drift. Adding eval-based TDD turns each hallucination report into a permanent test case; quality stops drifting silently.',
    fiveW: {
      what: 'Test-driven design with three layers: unit (RGR + F.I.R.S.T.), contract (consumer-driven), and AI evaluation (semantic + safety).',
      why: 'Tests written first force you to design testable code; testable code is decoupled, has clear contracts, and has known failure modes.',
      where: 'Every PR. Every microservice boundary. Every AI feature.',
      when: 'Before code. Before merge. Before promote.',
      who: 'Every engineer. AI eval owned by ML/Quality team.',
    },
    interview30s:
      'TDD = design. RGR cycle: red defines behavior, green is minimal pass, refactor cleans up. F.I.R.S.T. keeps unit tests trustworthy. For microservices I add contract tests (Pact / consumer-driven). For AI I replace exact match with evaluation: groundedness from RAG context, semantic similarity, safety filters, latency + token cost gates. Hard-to-test code is a design smell — fix the code first.',
    hld: `flowchart LR
  Red[Red: failing test] --> Green[Green: minimal code]
  Green --> Refactor[Refactor: clean + SOLID]
  Refactor --> Red
  Refactor --> Pyramid{Test pyramid}
  Pyramid --> U[Unit many fast]
  Pyramid --> I[Integration medium]
  Pyramid --> E[E2E few]
  Pyramid --> A[AI eval]`,
    flowchart: `flowchart TD
  Want[Want feature] --> Red[Write failing test]
  Red --> Run1[Run; should fail]
  Run1 --> Green[Write minimal code]
  Green --> Run2[Run; should pass]
  Run2 --> Hard{Test hard?}
  Hard -- yes --> Design[Code is wrong; redesign]
  Hard -- no --> Refactor[Refactor]
  Refactor --> Done{Done?}
  Done -- no --> Red
  Done -- yes --> Commit[Commit + CI]`,
    sequence: `sequenceDiagram
  participant Dev
  participant Test
  participant Code
  participant CI
  Dev->>Test: write failing test
  Dev->>Code: minimal pass
  Code-->>Test: green
  Dev->>Code: refactor
  Code-->>Test: still green
  Dev->>CI: push
  CI->>CI: unit + contract + AI eval
  CI-->>Dev: pass or fail`,
    coreLayers: [
      { layer: 'Unit', responsibility: 'F.I.R.S.T. + 1 behavior per test. < 10ms each.' },
      { layer: 'Integration', responsibility: 'Real DB + cache via Testcontainers. Service boundary.' },
      { layer: 'Contract', responsibility: 'Consumer-driven (Pact). Schema + behavior compatibility.' },
      { layer: 'E2E', responsibility: 'Few. Critical golden path only.' },
      { layer: 'AI eval', responsibility: 'Groundedness + semantic + safety + cost + latency.' },
    ],
    lld: `classDiagram
  class TestSuite {
    +unit: Test[]
    +integration: Test[]
    +contract: PactTest[]
    +e2e: ScenarioTest[]
    +ai_eval: EvalTest[]
  }
  class EvalTest {
    +query
    +expected_groundedness
    +safety_check
    +max_latency_ms`,
    coreBuildingBlocks: [
      'Red-Green-Refactor cycle',
      'F.I.R.S.T. discipline (Fast, Independent, Repeatable, Self-validating, Thorough)',
      'One behavior per test',
      'Testcontainers for real-DB integration',
      'Pact / OpenAPI for contracts',
      'AI eval harness with regression set',
      'Mocks at service boundary only — never deep mocks',
    ],
    architectureRelevance: {
      backend: 'Standard RGR + F.I.R.S.T.',
      rag: 'AI eval tests gate every prompt/model change.',
      ai: 'Evaluation-based testing replaces exact match.',
      microservices: 'Contract tests protect API boundaries between services.',
    },
    problem:
      'Tests are written after code → tested for the implementation that exists, not the behavior intended. Or no tests at all → regressions ship silently.',
    whyThisApproach:
      'Tests-first force you to design testable code (= decoupled + small contracts). Hard-to-test code = bad design.',
    whenToUse: [
      'New code',
      'Bug fixes (write the failing test first)',
      'AI feature changes (eval first)',
      'API contract changes (contract test first)',
    ],
    whenNotToUse: [
      'Throwaway prototype',
      'Spike to learn an unknown',
      'Refactor with full coverage already',
    ],
    input: 'Behavior spec + test fixtures + (for AI) regression eval set.',
    process: [
      'Red: write the failing test for the smallest behavior',
      'Run: confirm it fails for the right reason',
      'Green: write the minimal code to pass',
      'Run: confirm green',
      'Refactor: clean + SOLID + dedup',
      'Run: still green',
      'Repeat for next behavior',
    ],
    output: 'Tested code + permanent regression suite + (for AI) eval baseline.',
    implementationSteps: [
      { step: 'Pick smallest behavior', logic: 'One assertion. One reason for the test to fail.' },
      { step: 'Write failing test', logic: 'Test name = behavior. e.g., test_calculate_discount_rounds_to_2dp.' },
      { step: 'Run + confirm red', logic: 'If green by accident, the test is wrong.' },
      { step: 'Minimal pass', logic: 'Don\'t add features the test doesn\'t cover.' },
      { step: 'Run + confirm green', logic: 'Lock the behavior.' },
      { step: 'Refactor', logic: 'Tests give you the safety net to clean up.' },
      { step: 'Add F.I.R.S.T. check', logic: 'Fast (< 10ms), Independent (no order), Repeatable, Self-validating, Thorough.' },
      { step: 'Contract or eval layer', logic: 'For service boundaries: Pact. For AI: eval set.' },
    ],
    codeExample: {
      language: 'python',
      code: `# Unit (RGR + F.I.R.S.T.)
def test_calculate_discount_applies_percent():
    # Red first; Green after impl; Refactor with safety net
    assert calculate_discount(100, 10) == 90

def test_calculate_discount_rejects_negative_percent():
    with pytest.raises(ValueError):
        calculate_discount(100, -10)

# Integration (Testcontainers)
from testcontainers.postgres import PostgresContainer

def test_user_repo_round_trip():
    with PostgresContainer("postgres:15") as pg:
        repo = UserRepository(pg.get_connection_url())
        repo.save(User(id="u1", email="a@b.com"))
        assert repo.find("u1").email == "a@b.com"

# Contract (Pact-style consumer-driven)
def test_payment_service_charge_contract():
    pact.given("user has card")\\
        .upon_receiving("a charge request")\\
        .with_request("POST", "/charge", body={"amount": 100})\\
        .will_respond_with(200, body={"status": "ok", "tx_id": Like("tx_x")})

# AI evaluation test
def test_rag_answer_grounded_in_context():
    query = "What is the refund policy?"
    response = rag.answer(query)
    # Semantic match (not exact)
    assert similarity(response.text, expected_summary) > 0.8
    # Groundedness: every claim must trace to context
    assert all(c.source in response.citations for c in extract_claims(response.text))
    # Safety
    assert not contains_unsafe(response.text)
    # Latency + cost gates
    assert response.latency_ms < 2000
    assert response.cost_tokens < 1500`,
    },
    realUseCase:
      'A team retrofitted TDD onto an AI feature. First eval test: "answer must cite context". Caught silent hallucination immediately. Six months later catalog has 200+ eval tests; AI quality stable across 4 model upgrades.',
    prosCons: {
      pros: [
        'Forces good design (testable = decoupled)',
        'Refactor with safety net',
        'AI quality stops drifting silently',
        'Permanent regression catalog',
      ],
      cons: [
        'Initial slowdown until habit forms',
        'Bad tests are worse than no tests',
        'AI eval set takes effort to curate',
      ],
    },
    limitations: [
      'TDD doesn\'t replace exploratory testing',
      'AI eval can\'t catch fully novel failure modes',
      'Contract tests need both producer + consumer to adopt',
    ],
    comparison: {
      left: 'Test-after',
      right: 'TDD',
      rows: [
        { aspect: 'Design feedback', left: 'Late', right: 'Immediate' },
        { aspect: 'Test quality', left: 'Tests existing impl', right: 'Tests intended behavior' },
        { aspect: 'Refactor safety', left: 'Risky', right: 'Confident' },
        { aspect: 'Coverage', left: 'Incidental', right: 'Behavior-driven' },
      ],
    },
    challenges: [
      'AI non-determinism vs exact-match assertions',
      'Test data freshness for integration',
      'Pact / contract maintenance across teams',
      'Quarantining flakes without forgetting them',
    ],
    edgeCases: [
      { case: 'Hard to test = bad design', solution: 'Stop. Redesign. The test is telling you something.' },
      { case: 'AI eval flake', solution: 'Pin model version + use semantic threshold + N retries' },
      { case: 'Long test (> 1s)', solution: 'Move to integration suite; unit must be < 10ms' },
      { case: 'Test depends on DB state', solution: 'Reset DB per test (Testcontainers + transaction rollback)' },
    ],
    solutions: [
      { problem: 'Slow unit tests', solution: 'Mock external deps; pure functions where possible' },
      { problem: 'Flaky tests', solution: 'Quarantine + fix budget; never disable silently' },
      { problem: 'Contract breakage', solution: 'Consumer-driven Pact in CI; producer must run consumer\'s tests' },
      { problem: 'AI quality drift', solution: 'Eval set in CI; threshold gate before promote' },
    ],
    bestPractices: {
      do: [
        'Red before Green always',
        'One behavior per test',
        'F.I.R.S.T. enforced',
        'Contract tests for every API',
        'AI eval set grows with every regression',
        'Refactor with safety net',
      ],
      avoid: [
        'Multi-assert tests',
        'Order-dependent tests',
        'Mocking what you don\'t own (mock at boundaries)',
        'AI exact-match assertions',
      ],
      optimize: [
        'Test sharding in CI',
        'Cached fixtures',
        'Parallel test runners',
      ],
    },
    antiPatterns: [
      '"Tests will come later"',
      'Single huge test (test_everything)',
      'Mocking your own code (test the mock, not the code)',
      'AI tests with exact match',
      'No contract tests on microservices',
    ],
    testing: ['Unit + integration + contract + E2E + AI eval', 'Coverage trend non-decreasing'],
    testTypes: ['Unit', 'Integration (Testcontainers)', 'Contract (Pact / OpenAPI)', 'E2E', 'AI eval'],
    testScenarios: [
      { scenario: 'Unit test runs in < 10ms', expected: 'F.I.R.S.T. passes' },
      { scenario: 'API consumer breaks contract', expected: 'CI fails before merge' },
      { scenario: 'AI eval below threshold', expected: 'Promote blocked' },
      { scenario: 'Coverage drops', expected: 'CI fails' },
    ],
    testData: [
      { type: 'Unit fixtures', example: 'Pure inputs, no DB' },
      { type: 'Integration fixtures', example: 'Testcontainers seeded data' },
      { type: 'AI eval set', example: '100+ regression queries with expected groundedness' },
    ],
    debuggingChecklist: [
      'Test failed for the right reason?',
      'Test < 10ms?',
      'Test independent of others?',
      'AI eval threshold tuned?',
      'Contract test in both producer + consumer CI?',
    ],
    productionIssues: [
      { issue: 'Same regression every release', rootCause: 'No regression test added when first found' },
      { issue: 'AI hallucination shipped', rootCause: 'No eval gate or threshold too lax' },
      { issue: 'Microservice broke client', rootCause: 'No contract test; producer changed schema' },
    ],
    security: ['Mock secrets in tests', 'Never run tests with prod creds', 'Sanitize fixture data'],
    performance: ['Unit suite < 1 min', 'Integration < 5 min', 'AI eval < 5 min', 'Total CI < 10 min'],
    costConsiderations: [
      'AI eval uses tokens — pin small model + cache',
      'Testcontainers cold start — reuse via session-scoped fixtures',
    ],
    scaling: ['Test sharding', 'Parallel runners', 'Per-service eval sets vs shared'],
    observability: ['Test pass rate trend', 'Coverage trend', 'AI eval score trend', 'Flake rate per test'],
    metrics: [
      { name: 'unit_suite_seconds', example: '45' },
      { name: 'coverage_percent', example: '84' },
      { name: 'ai_eval_score', example: '0.91' },
      { name: 'flake_rate_percent', example: '0.3' },
      { name: 'contract_tests_count', example: '47' },
    ],
    failureModes: [
      { mode: 'Flake', detect: 'Same test fails ≥ 3× in 7 days', recover: 'Quarantine + fix budget; never silent disable' },
      { mode: 'AI eval drop', detect: 'Score < threshold', recover: 'Block promote; investigate prompt/model change' },
      { mode: 'Contract break', detect: 'Consumer test fails on producer change', recover: 'Block merge; producer updates contract' },
      { mode: 'Coverage drop > 1%', detect: 'CI fail', recover: 'Add tests for changed code' },
    ],
    tradeoffs: [
      { decision: 'TDD over test-after', tradeoff: 'Initial slowdown; design quality + refactor safety' },
      { decision: 'Mocks at boundaries only', tradeoff: 'More integration tests; better signal' },
      { decision: 'AI eval gate', tradeoff: 'CI time + cost; quality control' },
    ],
    decisionMatrix: [
      { option: 'TDD strict', whenToUse: 'New features + bug fixes + AI changes' },
      { option: 'Test-after with high coverage', whenToUse: 'Hot path bug fix in legacy with no tests yet' },
      { option: 'Exploratory only', whenToUse: 'Spike or research code, throwaway' },
    ],
    starStory: {
      situation: 'Team retrofitted TDD on existing AI feature. First eval test caught silent hallucination next deploy.',
      task: 'Establish AI eval discipline + contract tests for microservices.',
      action: 'Built eval set with regression queries + Pact contracts on 4 service boundaries + CI gates for both.',
      result: 'AI quality stable across 4 model upgrades. Two microservice schema breakages caught pre-merge by contract tests. Coverage 60% → 84%.',
    },
    interviewTraps: [
      'Saying "we test" without RGR cycle mention',
      'AI tests with exact match',
      'No contract tests on microservices',
      'Mocking own code',
    ],
    finalScript:
      'TDD is design. RGR + F.I.R.S.T. at unit level. Contract tests for service boundaries. Evaluation-based for AI. Hard-to-test = bad design. Each regression becomes a permanent test.',
    alternatives: [
      { name: 'Test-after', tradeoff: 'Faster initial feel; tests existing impl, not behavior' },
      { name: 'BDD (Cucumber)', tradeoff: 'Stakeholder-readable; ceremony cost' },
      { name: 'Property-based (Hypothesis)', tradeoff: 'Finds edges TDD misses; slower' },
    ],
    monitoring: ['Coverage trend', 'Flake rate', 'AI eval score', 'Contract test pass rate'],
    maturity: {
      mvp: 'Unit + integration TDD',
      production: 'Add contract tests + AI eval',
      enterprise: 'Add property-based + chaos drills + eval set in CI for every model change',
    },
    projectFit: ['Every codebase', 'Microservices', 'AI features', 'Refactor work'],
    interviewLine: 'RGR + F.I.R.S.T. unit. Contract for services. Evaluation for AI. Hard-to-test = bad design.',
  },
];

export default function CICDDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">CI/CD + TDD (deep dive)</h1>
        <p className="design-areas-sub">
          CI/CD master pipeline (build once, fail-fast gates, immutable artifacts,
          DevSecOps + AI eval gates) and the TDD framework extended for microservices
          + AI (Red-Green-Refactor, F.I.R.S.T. discipline, contract tests for service
          boundaries, evaluation-based testing for AI features).
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
