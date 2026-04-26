'use client';

/**
 * Engineering manager lens: roadmap planning, risk register, OKR
 * alignment, hiring + retention, and operational health. Emphasis on
 * §0 BRD, §11 ADR, §32 Trade-offs, §35 Interview traps, §37 STAR.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'roadmap-and-risk-planning',
    title: '1. Roadmap + risk planning for AI features (eng manager lens)',
    status: 'shipped',
    coreConcept: 'AI features have non-traditional risk profiles: model drift, hallucination, regulatory shifts, vendor lock-in. The eng manager owns the roadmap that converts these risks into ADRs, the risk register that names them explicitly, and the staffing plan that resources mitigation.',
    oneLiner: 'AI roadmaps live or die on the risk register. If you can\'t name the risks, you can\'t resource the mitigations.',
    businessContext: 'We need a 6-quarter roadmap for the RAG platform that converts business outcomes (compliance, revenue, retention) into engineering investments and is defensible against quarterly priorities.',
    fiveW: {
      what: 'A roadmap doc + risk register + staffing plan + on-call rotation. Linked to OKRs, reviewed quarterly, owned by the EM.',
      why: 'AI features fail in non-traditional ways: silent drift, hallucination on edge cases, regulatory drift (EU AI Act, NIST AI RMF). Without a risk register, mitigations stay implicit and underfunded.',
      where: 'Quarterly planning doc + ADR repo + on-call rotation calendar + dashboard showing risk burndown.',
      when: 'Quarterly planning cycle. Risks reviewed monthly. Roadmap rebased every 6 months on business plan.',
      who: 'EM owns. PM consumes. Tech leads contribute ADRs. Compliance + security review. CFO consumes for cost.',
    },
    interview30s: 'I run AI engineering by separating three artifacts: roadmap (what we ship + when), risk register (what can go wrong), and ADR log (decisions made and why). Risks are named explicitly: drift, hallucination, vendor lock-in, regulatory shift. Each has an owner, a mitigation, and a kill-switch threshold. Quarterly planning reconciles new business priorities against the risk register; we don\'t take work that increases unmitigated risk past the team\'s budget. The roadmap is a doc, not a Gantt chart — it explains why, not when.',
    coreBuildingBlocks: [
      'Roadmap doc — outcomes per quarter, OKR-linked',
      'Risk register — named risks, owners, mitigations, kill-switch thresholds',
      'ADR log — decisions made and why, append-only',
      'On-call rotation — 24/7 coverage with primary + secondary',
      'Hiring plan — tied to roadmap + risk staffing',
      'Vendor map — managed services in use, lock-in cost, alternatives',
      'Compliance map — regulations relevant, audits scheduled',
    ],
    architectureRelevance: {
      backend: 'Backend roadmap items: schema migrations, observability, breakers, cost controls — each needs an ADR.',
      rag: 'RAG roadmap: embedding model versions, eval dataset growth, hybrid retrieval tuning, hallucination dashboard.',
      ai: 'AI risk: drift detection, output guardrails (Cognitive CB), prompt versioning, model registry. Each is a roadmap item.',
      microservices: 'Service health = roadmap input: hot services that need refactor, services with high incident rate, services owned by 1 person (bus factor).',
    },
    flowchart: `flowchart LR
  BIZ[Business outcomes] --> OKR[OKRs]
  OKR --> ROAD[Roadmap doc]
  ROAD --> ADR[ADRs per decision]
  ADR --> EXEC[Engineering execution]
  RISK[Risk register] --> ROAD
  EXEC --> METRIC[Health metrics]
  METRIC --> RISK
  RISK -->|breach| ESC[Escalate to EM + CTO]`,
    sequence: `sequenceDiagram
  autonumber
  participant BIZ as Business
  participant EM as Eng manager
  participant TL as Tech lead
  participant SRE as SRE
  participant ENG as Engineer
  BIZ->>EM: quarterly priorities
  EM->>TL: ADR review for risky items
  TL->>EM: tradeoff analysis
  EM->>EM: update risk register
  EM->>ENG: prioritized backlog
  ENG->>SRE: ship feature with monitoring
  SRE->>EM: incident or risk breach
  EM->>BIZ: trade-off communication`,
    coreLayers: [
      { layer: 'Business outcomes', responsibility: 'Defined by leadership; eng manager translates to roadmap items.' },
      { layer: 'Roadmap', responsibility: 'Outcomes per quarter, OKR-linked, reviewed monthly. Updated when priorities shift.' },
      { layer: 'Risk register', responsibility: 'Named risks per system component. Each has owner, mitigation, kill-switch threshold.' },
      { layer: 'ADR log', responsibility: 'Append-only architecture decision records. New ADR for every irreversible decision.' },
      { layer: 'Staffing', responsibility: 'Headcount tied to roadmap + risk. Hiring + retention plan reviewed quarterly.' },
      { layer: 'On-call', responsibility: 'Primary + secondary rotation. Runbooks per service. Postmortems per incident.' },
      { layer: 'Compliance', responsibility: 'Regulations mapped to features. Audit calendar. Evidence collection automated.' },
    ],
    problem: 'Without a risk register, AI features ship with implicit risks (drift, hallucination, vendor lock-in) that aren\'t resourced. Quarterly priorities pile up unrelated work. Engineers burn out on implicit on-call.',
    whyThisApproach: 'Three artifacts (roadmap + risk + ADR) separate WHAT we ship, WHAT can go wrong, and WHY we chose. Each has an owner and a review cadence. Implicit becomes explicit.',
    whenToUse: [
      'AI / ML features in production',
      'Compliance-regulated environments (HIPAA, SOC2, EU AI Act)',
      'Multi-team collaboration on shared platform',
      '≥ 5 engineers — communication overhead requires structure',
    ],
    whenNotToUse: [
      '2-engineer prototype — overhead exceeds value',
      'Stable system with no AI components — simpler tooling works',
      'Single-team feature shop — informal kanban suffices',
    ],
    input: 'Business outcomes + system health metrics + regulatory landscape',
    process: [
      'Quarterly: review business plan + reconcile against risk register',
      'Monthly: review risk register + ADRs + on-call burden',
      'Weekly: review incidents, postmortems, hiring funnel',
      'Daily: standup at team level; EM consumes signals not blockers',
    ],
    output: 'A roadmap doc, risk register, ADR log, staffing plan — all reviewed on cadence, all with named owners.',
    alternatives: [
      { name: 'Pure backlog (Jira-only)', tradeoff: 'Easy to start; explicit risks become noise; ADRs missing; hard to defend priorities' },
      { name: 'OKR-only (no risk register)', tradeoff: 'Outcome-focused; risks linger in tribal knowledge; new joiners can\'t catch up' },
      { name: 'Quarterly OKR + ADR (no risk register)', tradeoff: 'Decisions documented; risks named only when they fire; reactive not proactive' },
      { name: 'PMI-style risk matrix only', tradeoff: 'Risk-focused; roadmap drift; ADRs missing; not engineer-friendly' },
    ],
    challenges: [
      'Risk register goes stale without monthly review discipline',
      'ADRs accumulate fast — index + search become important',
      'On-call burden invisible until burnout — tracked but not actioned',
      'Hiring lags risk emergence — long-tail',
      'Compliance shifts (EU AI Act) faster than roadmap horizon',
    ],
    edgeCases: [
      { case: 'New regulation lands mid-quarter (EU AI Act)', solution: 'Add risk to register; trigger ADR; reprioritize accordingly' },
      { case: 'Hallucination rate spikes in production', solution: 'Kill-switch threshold trips; pause new traffic to model; ADR on root cause' },
      { case: 'Vendor announces price hike or sunset', solution: 'Activate alternative path from vendor map; ADR on migration cost' },
      { case: 'Tech lead leaves team', solution: 'ADR ownership reassigned; bus-factor-1 risk fired; hiring + cross-training accelerated' },
    ],
    failureModes: [
      { mode: 'Risk register goes stale (not reviewed)', detect: 'Last-updated timestamp older than 30d', recover: 'Monthly cadence enforced; EM owns review' },
      { mode: 'ADRs missing for major decisions', detect: 'Audit catches decision with no doc', recover: 'Retroactive ADR + process correction' },
      { mode: 'On-call burnout (engineer attrition)', detect: 'Page count + after-hours response time + stay/leave conversations', recover: 'Rotation rebalance + paging hygiene + temp staff augmentation' },
      { mode: 'Roadmap drift (quarterly priorities ignore risks)', detect: 'New work added without risk-budget check', recover: 'Re-anchor on risk register; reset expectations with leadership' },
    ],
    monitoring: [
      'Roadmap velocity vs plan',
      'Risk register staleness (last review timestamp)',
      'ADR rate (new decisions documented per quarter)',
      'On-call: pages per week, MTTR, after-hours load per engineer',
      'Hiring funnel: candidates per stage, time-to-hire',
      'Attrition rate + exit reasons',
    ],
    testing: [
      'Quarterly roadmap review',
      'Monthly risk register review',
      'Postmortem per incident',
      'Tabletop exercise per major risk per year',
    ],
    security: [
      'Risk register stored in private repo with access control',
      'ADRs reviewed by security for relevant decisions',
      'Compliance map reviewed by legal',
      'On-call rotation has security primary',
    ],
    scaling: [
      '5 engineers: weekly 1:1 + monthly all-hands',
      '20 engineers: managers + tech leads + EM oversight',
      '50+ engineers: directors + tech debt budget + dedicated platform team',
    ],
    maturity: {
      mvp: 'Backlog + sprint planning. Risks tribal.',
      production: 'Roadmap + risk register + ADR + on-call. Quarterly reviews.',
      enterprise: 'Risk burndown dashboard + automated compliance evidence + cross-team OKR alignment + leadership-level incident review.',
    },
    limitations: [
      'EM lens omits per-feature LLD and code-level concerns — see /admin/techlead/deep',
      'Roadmap doc is a snapshot; reality drifts; review cadence is what makes it real',
      'Risk register can become bureaucratic — keep it short, named, owned',
    ],
    projectFit: [
      'docs/learning/engineering-process-and-review.md — process doc',
      'docs/scenarios/ — risk scenarios captured per phase',
      'mcp/tests/drill_*.py — test discipline that anchors quality',
      '/admin/llmops — operational health surface for the EM',
      '/admin/deep-dives — discoverability for new joiners',
    ],
    interviewLine: 'I run AI engineering with three artifacts: a roadmap that says what we ship, a risk register that says what can go wrong, and an ADR log that says why we chose. Each has an owner and a cadence. Without all three, implicit knowledge owns the team and burnout owns the schedule.',
    finalScript: 'I run AI engineering as three artifacts. The roadmap says what we ship per quarter, OKR-linked, defensible to leadership. The risk register names every non-traditional risk — drift, hallucination, vendor lock-in, regulatory drift — each with an owner, mitigation, and kill-switch threshold. The ADR log records every irreversible decision: append-only, indexed, searchable. Staffing maps to roadmap and risk; hiring isn\'t reactive. On-call is owned, runbooks per service, postmortems per incident. Quarterly we reconcile business priorities against the risk register; we don\'t take work that increases unmitigated risk past budget. Without these three, implicit owns the team and burnout owns the schedule.',
  },
];

export default function EngManagerDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Engineering Manager — Deep Dive</h1>
        <p className="design-areas-sub">
          The eng manager lens: roadmap, risk register, ADR log, staffing, on-call, compliance.
          Emphasis on §0 BRD, §11 ADR, §32 Trade-offs, §35 Interview traps. Use when planning
          quarterly priorities, defending headcount, or running the platform's operational health.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
