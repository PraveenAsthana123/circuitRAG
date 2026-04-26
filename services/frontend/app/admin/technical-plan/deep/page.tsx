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
    interviewLine: 'A technical plan converts a 1-page BRD into a 6-week roadmap with ADRs, drills, and a rollback plan. Reviewed by tech lead, architect, security, and EM before any code lands. Without it, work fragments and the outcome doesn\'t ship. With it, the team builds in parallel and verifies the outcome objectively.',
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
