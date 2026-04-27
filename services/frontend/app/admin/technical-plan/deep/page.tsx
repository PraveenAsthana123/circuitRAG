'use client';

/**
 * Technical plan lens: BRD-to-code translation. Walks one feature
 * through every phase of the master template — from business
 * outcome to shipped code with drills. Emphasis on §0 BRD, §1
 * Problem/Context, §11 ADR, §9 Logical steps.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'brd-to-code-walkthrough',
    title: '1. BRD-to-code: a worked example (technical plan lens)',
    status: 'shipped',
    coreConcept: 'A technical plan converts a 1-page BRD into a 6-week shipping roadmap with explicit ADRs, a drill list, and a rollback plan. This page walks one real feature — "audit-grade tenant isolation" — through every phase.',
    oneLiner: 'Technical plan = BRD + ADRs + drill list + rollback. Anything less is a ticket, not a plan.',
    businessContext: 'We need to ship audit-grade tenant isolation in a multi-tenant RAG SaaS where one tenant\'s data leaking to another is a contract-breaking event. The technical plan converts that business need into 6 weeks of shipping work.',
    fiveW: {
      what: 'A doc that translates business outcome → architecture decisions → code changes → drill suite → rollback. Reviewed by tech lead, security, and EM before work starts.',
      why: 'Without a plan, the work fragments into tickets that don\'t add up to the outcome. Without explicit ADRs, decisions reverse mid-stream. Without drills, we don\'t know if the outcome shipped.',
      where: 'docs/plans/<feature>.md per major feature. Linked from quarterly roadmap. Updated as ADRs land.',
      when: 'Anytime business asks for an outcome that takes ≥ 2 weeks or touches ≥ 2 services.',
      who: 'Tech lead drafts. Architect reviews ADRs. Security reviews threat model. EM reviews scope + risk. Engineers consume.',
    },
    interview30s: 'I write technical plans as five sections: BRD restated, ADRs proposed, code change list, drill list, rollback plan. The BRD section restates the business outcome in our language. ADRs name the decisions we\'re making and why. Code changes list every PR with owner and reviewer. Drills list the negative-assertion tests that prove the outcome shipped. Rollback names the kill-switch and the data-recovery path. The plan is reviewed before any code lands. Without this, we ship tickets that don\'t add up.',
    coreBuildingBlocks: [
      '§0 BRD — restated in engineering language',
      'Architecture diagram — HLD + LLD + Network Flow',
      'ADRs — irreversible decisions with reasons + tradeoffs',
      'Code change list — every PR with owner + reviewer',
      'Drill list — negative-assertion tests proving outcome',
      'Rollback plan — kill-switch + data-recovery path',
      'Acceptance criteria — measurable signals',
    ],
    architectureRelevance: {
      backend: 'Plan names: schemas to migrate, endpoints to add, repositories to refactor, middleware to insert.',
      rag: 'Plan names: chunking strategy changes, embedding model upgrades, eval dataset additions, hallucination thresholds.',
      ai: 'Plan names: prompt versions, model selections, guardrails, decision audit format, cost ceiling.',
      microservices: 'Plan names: services touched, contracts changed, breakers added, mesh policies updated.',
    },
    flowchart: `flowchart LR
  BRD[BRD] --> RESTATE[Restate in eng language]
  RESTATE --> ADR[ADRs proposed]
  ADR --> ARCH[Architecture diagrams]
  ARCH --> CODE[Code change list]
  CODE --> DRILL[Drill list]
  DRILL --> ROLL[Rollback plan]
  ROLL --> REV[Tech lead + security + EM review]
  REV -->|approved| SHIP[Ship in PR sequence]
  REV -->|changes| ADR
  SHIP --> VERIFY[Drills green + acceptance met]`,
    sequence: `sequenceDiagram
  autonumber
  participant Biz as Business
  participant TL as Tech lead
  participant Arch as Architect
  participant Sec as Security
  participant EM as Eng manager
  participant Eng as Engineer
  Biz->>TL: BRD
  TL->>TL: draft technical plan
  TL->>Arch: review ADRs
  TL->>Sec: review threat model
  TL->>EM: review scope + risk
  Arch-->>TL: ADR feedback
  Sec-->>TL: security feedback
  EM-->>TL: scope feedback
  TL->>Eng: prioritized PRs
  Eng->>Eng: ship + drills green
  Eng-->>TL: outcome verified`,
    coreLayers: [
      { layer: 'BRD', responsibility: 'Restated in eng language. KPIs, scope, users, risks.' },
      { layer: 'Architecture', responsibility: 'HLD diagram + Network Flow + LLD per affected service.' },
      { layer: 'ADRs', responsibility: 'Each irreversible decision with reason + tradeoff + alternatives considered.' },
      { layer: 'Code changes', responsibility: 'Every PR named with owner + reviewer + dependency order.' },
      { layer: 'Drills', responsibility: 'Negative-assertion tests per outcome. Proves the outcome AND prevents regression.' },
      { layer: 'Rollback', responsibility: 'Kill-switch documented. Data-recovery path tested. Forward + reverse migrations paired.' },
      { layer: 'Acceptance', responsibility: 'Measurable signals: drill green count, p95 latency, error rate, cost per request.' },
    ],
    problem: 'Without a plan, work fragments into tickets that don\'t add up. ADRs are made implicitly. Drills are afterthoughts. Rollback is improvised under stress.',
    whyThisApproach: 'Five-section plan front-loads the thinking. Reviews catch wrong-shape decisions early. Drills prove the outcome shipped. Rollback turns "panic" into "execute".',
    whenToUse: [
      'Any feature taking ≥ 2 weeks',
      'Touching ≥ 2 services',
      'Schema migration in production',
      'Breaking change to consumer contracts',
      'Compliance-relevant feature',
    ],
    whenNotToUse: [
      'Single-PR refactor — overkill',
      'Bug fix with obvious cause — drill discipline alone suffices',
      'Throwaway prototype',
    ],
    input: 'BRD + current architecture + risk register + team capacity',
    process: [
      'Restate BRD in engineering language; name KPIs',
      'Draft architecture diagrams: HLD + Network Flow + LLD',
      'Propose ADRs for irreversible decisions; name tradeoffs',
      'List code changes: PRs with owner, reviewer, dependency order',
      'List drills: one per outcome assertion, all with negative assertions',
      'Document rollback: kill-switch, forward + reverse migration, data recovery',
      'Review with tech lead + architect + security + EM',
      'Ship PRs in dependency order; close plan when drills + acceptance green',
    ],
    output: 'A reviewed plan doc + a closed plan with all drills green + KPI evidence. Plan archived as ADR reference for future work.',
    alternatives: [
      { name: 'Pure Jira tickets', tradeoff: 'Easy to start; no architectural thinking; ADRs implicit; rollback improvised' },
      { name: 'Design doc only (no drill list)', tradeoff: 'Architecture clear; outcome proof missing; regression detection weak' },
      { name: 'Drill-first (no plan)', tradeoff: 'Outcomes pinned; architecture drift; ADRs missing; tradeoffs hidden' },
      { name: 'Big upfront design (waterfall)', tradeoff: 'Comprehensive; reality drifts; reviews stale before code lands' },
    ],
    challenges: [
      'Plan goes stale mid-execution — review cadence required',
      'ADRs argued about; tradeoffs litigated; consensus elusive',
      'Drill list grows; CI time grows; balance needed',
      'Rollback rarely tested; first failure surprises everyone',
      'Acceptance criteria fuzzy; "done" disputed',
    ],
    edgeCases: [
      { case: 'Business priority shifts mid-plan', solution: 'Re-review plan with EM; either adjust scope or descope; never silently drift' },
      { case: 'ADR turns out wrong after week 3', solution: 'New ADR superseding the old; document why; accept sunk cost' },
      { case: 'Drill flakes intermittently', solution: 'Investigate root cause; never quarantine; either fix or remove (never silent skip)' },
      { case: 'Rollback path fails in dry-run', solution: 'Block rollout; fix recovery path first; document in ADR' },
    ],
    failureModes: [
      { mode: 'Plan exists but isn\'t reviewed', detect: 'No reviewer signoff comment in plan doc', recover: 'Block PR merges until plan reviewed' },
      { mode: 'Drills written but not run in CI', detect: 'CI badge missing on plan-related PRs', recover: 'Required check enforcement' },
      { mode: 'Rollback only documented (not tested)', detect: 'No dry-run timestamp in plan', recover: 'Quarterly rollback drill per major feature' },
      { mode: 'Acceptance criteria moved post-hoc', detect: 'KPI in plan diverges from KPI claimed shipped', recover: 'Audit closure + retro' },
    ],
    monitoring: [
      'Plan staleness (days since last update)',
      'Drill green ratio per plan',
      'Rollback dry-run timestamp per major feature',
      'Time-to-ship vs plan estimate',
    ],
    testing: [
      'Plan review: tech lead + architect + security + EM signoff in doc',
      'Drill list: each drill has negative assertion + runs in CI',
      'Rollback dry-run: scheduled per major feature, evidence in plan',
      'Acceptance test: KPI measured pre + post + delta documented',
    ],
    security: [
      'Threat model section in plan, reviewed by security',
      'Sensitive features: pen-test before rollout',
      'Audit chain integrity: drill verifies hash-chain unbroken',
      'PII handling: explicit in plan, redact_pii enforcement drilled',
    ],
    scaling: [
      'Plan template scales: same shape for 1-week and 6-month features',
      'ADR count grows with team size; index + search important',
      'Drill suite grows; parallelize in CI; quarantine policy STRICT (never silent skip)',
    ],
    maturity: {
      mvp: 'Plan doc per major feature; reviewed informally',
      production: 'Plan template enforced; ADRs in repo; drill list required; rollback dry-run',
      enterprise: 'Plan + ADR repo with search + tag taxonomy; quarterly rollback drill per service; compliance audit reads ADRs',
    },
    limitations: [
      'Technical plan is a tool, not a substitute for judgment',
      'Plans capture intent; reality drifts; review cadence is what makes them real',
      'A bad plan is worse than no plan — keep it tight, named, reviewed',
    ],
    projectFit: [
      'docs/plans/<feature>.md — per-feature plans',
      'docs/scenarios/phase-*.md — phase-level execution captured',
      'docs/learning/engineering-process-and-review.md — process doc',
      'mcp/tests/drill_*.py — drills referenced from plans',
      '~/.claude/policies/drill-testing-pattern.md — drill discipline',
    ],
    interviewLine: 'A technical plan converts a 1-page BRD into a 6-week roadmap with ADRs, drills, and a rollback plan. Reviewed by tech lead, architect, security, and EM before any code lands.',
    implementationSteps: [
      { step: 'Restate BRD in eng terms', logic: 'Outcome + KPIs translated; ambiguities flagged BEFORE code.' },
      { step: 'Diagram set: HLD + LLD + Network', logic: 'Three views; reviewers find gaps before bugs.' },
      { step: 'ADR list with reversibility', logic: 'Each irreversible decision has alternatives + cost.' },
      { step: 'Code change list with PRs + owners', logic: 'Dependency order explicit; parallel-safe PRs identified.' },
      { step: 'Drill list with negative assertions', logic: 'Each invariant has a test that fails closed if regressed (§43).' },
      { step: 'Rollback plan + kill switch', logic: 'Paired forward/reverse migrations; rehearsed in staging.' },
      { step: 'Review board: TL+Arch+Sec+EM', logic: 'Plan approved before code; closed when drills green + KPIs hit.' },
    ],
    codeExample: {
      language: 'markdown',
      code: `# Technical Plan: per-tenant Token CB (TP-2026-04)
Owners: ai-platform · Risk-link: RISK-007 · Cycle: 4 weeks

## §0 BRD restated
Stop tenants from blowing daily LLM budgets. Acceptance:
  - Token CB enforces daily cap per tenant
  - Breach returns 429 + Retry-After (next UTC midnight)
  - Drill verifies enforcement + audit row written

## §11 ADRs
ADR-052: Per-tenant daily cap stored in Postgres (not Redis-only)
  - Alternative: Redis with periodic snapshot (faster, less durable)
  - Decision: PG primary + Redis cache; durability > 5ms latency
  - Reversibility: medium (data migration if reversed)

## §8 Code change list (4 PRs)
PR-1: libs/py/documind_core/budget.py — TokenBudgetStore protocol
PR-2: services/inference-svc — middleware enforces cap
PR-3: migrations — daily_cost_log table + indexes
PR-4: docs/ + drill_token_cb.py

## §43 Drills (negative assertions)
drill_token_cb_enforced — exhaust budget, expect 429 + audit
drill_token_cb_resets_at_midnight — verify daily reset
drill_token_cb_per_tenant_isolation — tenant A breach ≠ tenant B blocked

## Rollback
Kill switch: feature_flag.token_cb=false → bypass middleware
Forward: 003_token_budget.up.sql; Reverse: 003.down.sql
Rehearsed in staging on 2026-04-15.

## KPIs measured
- 100% of tenant breaches return 429 (no silent overruns)
- Audit row exists for every breach
- p95 latency overhead < 3ms`,
    },
    realUseCase: 'Token CB feature shipped in 4 weeks against this exact plan. Review caught two issues: ADR-052 originally specced Redis-only; reviewers (architect + EM) flagged durability risk. Rollback plan originally lacked the staging rehearsal — added before approval. Drill caught a per-tenant isolation bug 2 days before launch (one tenant\'s breach was incrementing all tenants\' counters). Caught at PR-time, not production.',
    prosCons: {
      pros: [
        'Plan review surfaces gaps before implementation',
        'Drill list ensures invariants are testable',
        'Rollback plan tested in staging — not theoretical',
        'Review board distributes accountability + catches blind spots',
      ],
      cons: [
        '~3-5 days of EM/TL time per plan, up-front',
        'Slows scrappy work (counter: scrappy work doesn\'t need a plan)',
        'Plan can become outdated if not revised mid-flight',
      ],
    },
    comparison: {
      left: '"Just write the code" / ticket-driven work',
      right: 'Technical plan + review board + drills',
      rows: [
        { aspect: 'Surprise during impl', left: 'Found at PR or integration', right: 'Found at plan review' },
        { aspect: 'Rollback readiness', left: 'Theoretical or untested', right: 'Rehearsed in staging' },
        { aspect: 'Cross-team dependencies', left: 'Discovered when blocked', right: 'Mapped in code change list' },
        { aspect: 'Post-launch confidence', left: '"Hopefully works"', right: 'Drills + KPIs measured' },
      ],
    },
    solutions: [
      { problem: 'Half-shipped features stuck in PR loops', solution: 'Plan dependency order makes parallel-safe PRs explicit' },
      { problem: 'Untested rollback paths', solution: 'Staging rehearsal before plan approval' },
      { problem: 'Decisions reconstructed via Slack', solution: 'ADR list per plan; archived in /docs/adr/' },
      { problem: 'Acceptance criteria fuzzy', solution: 'KPIs from BRD restated; drills verify each' },
    ],
    bestPractices: {
      do: [
        'Plan reviewed by 4 lenses: TL + architect + security + EM',
        'Drill list includes at least one negative assertion (§43)',
        'Rollback rehearsed in staging before approval',
        'Code change list has dependency DAG + owners',
        'KPIs from BRD measured post-launch',
      ],
      avoid: [
        'Skipping the security review on "small" features',
        'Drills that test only happy paths',
        'Rollback as a plan section without staging rehearsal',
        'ADRs added after implementation (post-rationalization)',
      ],
      optimize: [
        'Plan template versioned — same shape every time',
        'Drill scaffolding shared via mcp/tests/templates/',
        'Cross-link plan ↔ ADR ↔ drill from a search index',
      ],
    },
    antiPatterns: [
      'Plan as marketing doc (no alternatives, no rollback)',
      'Single reviewer (loses lens diversity)',
      'No drills — "we tested manually"',
      'Rollback plan that\'s never been executed',
      'KPIs declared but never measured post-launch',
    ],
    testTypes: [
      'Plan review: 4-lens (TL+Arch+Sec+EM) signoff before approval',
      'Drill discipline: each invariant has a negative-assertion test',
      'Staging rollback rehearsal: forward + reverse migration tested',
      'Post-launch KPI measurement vs BRD targets',
    ],
    testScenarios: [
      { scenario: 'Plan review finds gap', expected: 'Plan revised; not approved until resolved' },
      { scenario: 'Drill fails in CI mid-implementation', expected: 'PR blocks; fix or revert before merge' },
      { scenario: 'Staging rollback rehearsal fails', expected: 'Plan paused; rollback fixed before approval' },
      { scenario: 'Post-launch KPI miss', expected: 'Plan re-opened; remediation tracked, not ignored' },
    ],
    testData: [
      { type: 'Plan template', example: 'Markdown w/ §0 BRD, §4 HLD, §11 ADRs, §8 PRs, §43 drills, Rollback, KPIs' },
      { type: 'Drill scaffold', example: '# RESOURCES + ✓/✗ steps + ALL N STEPS PASSED tail' },
      { type: 'Rollback rehearsal log', example: 'Staging trace + screenshots + timestamps' },
    ],
    debuggingChecklist: [
      'Plan slipping? Compare PR list to actual; find blocked dependencies',
      'Drill failing? Read assertion message — it names the invariant',
      'Rollback nervous? Re-rehearse in staging, not in prod',
      'KPI miss? Map to which §0 acceptance criterion missed',
    ],
    productionIssues: [
      { issue: 'Per-tenant Token CB shipped but enforcement was global', rootCause: 'Drill tested "exhaust → 429" but not "tenant A breach ≠ tenant B blocked". Negative isolation assertion was missing.' },
      { issue: 'Migration rolled back at 3am; data corruption', rootCause: 'Reverse migration was written but never rehearsed in staging; column-rename order was wrong.' },
      { issue: 'Feature shipped, KPI not measured', rootCause: 'Plan closed at code-merge, not at KPI measurement. KPIs slipped a quarter before anyone noticed.' },
    ],
    performance: [
      'Plan write: ~1-2 days for the EM/TL',
      'Plan review: ~4 hours total across the 4 lenses',
      'Drill write: ~30 min per invariant',
      'Staging rollback rehearsal: ~1-2 hours including data restore',
    ],
    costConsiderations: [
      'EM/TL time: ~10% of cycle for the plan + reviews',
      'Tooling: free — markdown + git + CI + staging env',
      'ROI: prevents one rollback emergency per quarter',
    ],
    observability: [
      'Plan velocity: time from approval to KPI-measured closure',
      'Drill coverage: % of invariants with negative-assertion drill',
      'Rollback readiness: % of plans with rehearsed rollback before approval',
      'Post-launch KPI hit rate: % of plans where BRD KPIs achieved',
    ],
    metrics: [
      { name: 'plan_approval_to_kpi_measured_days{plan_id}', example: 'Histogram; target p95 ≤ cycle length' },
      { name: 'plan_drills_negative_count{plan_id}', example: 'Counter; target ≥ 1 per plan (§43)' },
      { name: 'plan_rollback_rehearsed_total{}', example: 'Ratio to plan_approved_total should be 1.0' },
      { name: 'plan_kpi_achievement_rate{quarter}', example: 'Gauge; target ≥ 0.85' },
    ],
    tradeoffs: [
      { decision: 'Plan length', tradeoff: 'Too short = gaps; too long = nobody reads it' },
      { decision: 'Review board size', tradeoff: '4 lenses catches more but takes longer to schedule' },
      { decision: 'Drill rigor', tradeoff: 'More drills = more confidence but slower iteration' },
      { decision: 'Rollback rehearsal frequency', tradeoff: 'Every plan = thorough; sample = risk' },
    ],
    decisionMatrix: [
      { option: 'Full technical plan (this)', whenToUse: '≥ 2-week feature, multi-team, regulated, irreversible' },
      { option: 'Lightweight 1-page', whenToUse: '< 1 week, single team, reversible' },
      { option: 'No plan / ticket-driven', whenToUse: 'Bug fix, single-PR, well-understood domain' },
    ],
    starStory: {
      situation: 'Per-tenant Token CB feature: 4-week target, blocking 3 customer accounts that had threatened cancellation due to runaway costs.',
      task: 'Ship in 4 weeks with zero per-tenant isolation bugs and a rehearsed rollback.',
      action: 'Wrote the plan; review caught durability risk in ADR-052 and missing negative-assertion drill for tenant isolation. Added drill_token_cb_per_tenant_isolation. Rehearsed rollback in staging week 3. Drill caught the isolation bug week 4 day 2.',
      result: 'Shipped on time. Zero rollback events. KPIs hit (100% breaches → 429, p95 < 3ms overhead). Plan template adopted by sister teams.',
    },
    interviewTraps: [
      'Saying "we have a plan template" without saying who reviews it',
      'Drill list with no negative assertions',
      'Rollback plan that\'s only a paragraph (not rehearsed)',
      'KPIs from BRD that nobody measures post-launch',
      'ADRs added retroactively to look thorough',
    ],
    finalScript: 'A technical plan has five sections. BRD restated in our language with KPIs. Architecture diagrams: HLD, Network Flow, LLD per service. ADRs for every irreversible decision with explicit tradeoffs. Code change list with PRs, owners, reviewers, dependency order. Drill list — negative-assertion tests proving the outcome. Rollback plan: kill-switch, paired forward and reverse migrations, data-recovery path tested. Reviewed by tech lead, architect, security, and EM before any code lands. Closed when all drills green and acceptance KPIs measured. Without this, work fragments into tickets that don\'t add up. With it, the team builds in parallel against a shared shape and verifies the outcome objectively.',
  },
];

export default function TechnicalPlanDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Technical Plan — Deep Dive</h1>
        <p className="design-areas-sub">
          BRD-to-code: a worked example. Covers the full lifecycle from business outcome
          to shipped feature with drills + rollback. Emphasis on §0 BRD, §1 Problem/Context,
          §11 ADR, §9 Logical steps. Use when scoping any ≥ 2-week feature.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
