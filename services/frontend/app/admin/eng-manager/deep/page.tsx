'use client';

/**
 * Engineering manager lens: roadmap planning, risk register, OKR
 * alignment, hiring + retention, and operational health. Emphasis on
 * §0 BRD, §11 ADR, §32 Trade-offs, §35 Interview traps, §37 STAR.
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
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
    implementationSteps: [
      { step: 'Quarterly roadmap', logic: '8–12 weeks of work, OKR-linked; no rolling 12-month wishlist.' },
      { step: 'Risk register', logic: 'Drift, hallucination, vendor, regulatory — owner + mitigation + kill-switch threshold each.' },
      { step: 'ADR log', logic: 'Append-only; decision + alternatives + reversibility cost on every irreversible call.' },
      { step: 'Staffing → roadmap + risk', logic: 'Hires map to roadmap commitments AND unmitigated risks; not reactive headcount.' },
      { step: 'On-call rotation + runbooks', logic: 'Per-service runbooks; postmortems per P0/P1; weekly review of paging volume.' },
      { step: 'Quarterly reconciliation', logic: 'Reject new work that pushes unmitigated risk past budget.' },
      { step: 'Compliance cadence', logic: 'EU AI Act / SOC2 / GDPR review quarterly; not a yearly fire drill.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# .eng/roadmap-2026-q2.yml — example artifact
quarter: 2026-Q2
team: ai-platform
owner: eng-manager-name
okr: "Reduce per-tenant LLM cost 30% while holding recall@10 above 92%"

commitments:
  - id: ROAD-101
    title: "Cross-encoder rerank cache"
    impact: "12-18% cost reduction"
    eng_weeks: 4
    risk_link: RISK-007
    status: in_flight
  - id: ROAD-102
    title: "Embedding model upgrade to v3"
    impact: "+2pp recall@10"
    eng_weeks: 6
    risk_link: RISK-002
    blocks: [eval-svc-shadow-index]
    status: planning

# .eng/risks-2026-q2.yml
risks:
  - id: RISK-002
    name: "Model drift on embedding upgrade"
    owner: ai-platform
    mitigation: "Shadow index + eval gate + feature flag"
    kill_switch: "Recall regression > 2pp on golden set"
    status: monitored
  - id: RISK-007
    name: "Per-tenant token cost runaway"
    owner: finops + ai-platform
    mitigation: "Token CB with daily budget; tier-aware routing"
    kill_switch: "Daily cost per tenant > 1.5x baseline for 3 days"
    status: monitored

# docs/adr/0042-cache-rerank-by-query-hash.md (excerpt)
# Status: accepted | Date: 2026-04-22 | Reversibility: low
# Decision: Cache cross-encoder rerank scores keyed by
# (query_hash, embedding_version) with 1h TTL.
# Alternatives: no cache (current); cache by document_id (no, rerank is query-conditional)
# Why now: §3 of ROAD-101; risk-linked to RISK-007.`,
    },
    realUseCase: 'Q2 plan: ship rerank cache (12-18% cost reduction) + embedding v3 upgrade (+2pp recall). Budget allowed both, but ADR for embedding upgrade flagged: drift risk requires shadow index, which needs eval-svc work first. Roadmap re-sequenced — eval-svc shadow-index in Q1 catch-up, embedding upgrade pushed to early Q3. No surprise outage. The previous quarter\'s "ship and see" approach caused a recall regression that took 5 days to detect.',
    prosCons: {
      pros: [
        'Three artifacts make implicit knowledge explicit + transferable',
        'Risk register makes "we should have known" impossible after the fact',
        'ADR log lets new joiners reconstruct decisions without tribal knowledge',
        'Quarterly reconciliation prevents scope-creep beyond risk budget',
      ],
      cons: [
        'Up-front overhead — ~4 hours/week for the EM',
        'Risk register reviews can become checkbox theater if not enforced',
        'ADRs slow rapid prototyping (counter: prototypes don\'t need ADRs)',
      ],
    },
    comparison: {
      left: '"Trust me" leadership / implicit decisions',
      right: 'Three-artifact discipline (roadmap + risk + ADR)',
      rows: [
        { aspect: 'New-joiner ramp', left: '6–8 weeks of tribal knowledge', right: '2 weeks of doc reading' },
        { aspect: 'Decision reconstruction', left: 'Slack archeology', right: 'Searchable ADR log' },
        { aspect: 'Risk surprise rate', left: '"We didn\'t see that coming"', right: 'Risk register has it' },
        { aspect: 'Scope creep', left: 'Constant re-prioritization', right: 'Quarterly reconciliation, locked plan' },
        { aspect: 'Burnout', left: 'High — implicit ownership', right: 'Lower — owners + cadence explicit' },
      ],
    },
    solutions: [
      { problem: 'Implicit knowledge = single point of failure', solution: 'ADR log + risk register make decisions transferable' },
      { problem: 'Scope creep destroys quarterly plans', solution: 'Quarterly reconciliation gate; new work fights for ROAD-X slot' },
      { problem: 'Hiring is reactive', solution: 'Headcount maps to risk register + roadmap, not "we need more"' },
      { problem: 'Postmortems vanish into Slack', solution: 'Postmortem template + index in /docs/postmortems/' },
      { problem: 'Compliance becomes annual fire drill', solution: 'Quarterly compliance review tied to roadmap reconciliation' },
    ],
    bestPractices: {
      do: [
        'Roadmap items link to risk register IDs',
        'ADR for every irreversible decision',
        'Postmortem within 48h of P0/P1',
        'Risk register reviewed monthly; quarterly with leadership',
        'On-call rotation balanced; nobody on > 25% of weeks',
        'Headcount asks include the roadmap and risk evidence',
      ],
      avoid: [
        'Roadmaps without OKR linkage (won\'t survive priority shifts)',
        'Risk register that hasn\'t been touched in 90 days',
        'ADRs as marketing material (decision + alternatives + cost only)',
        'Implicit on-call ownership (everyone = nobody)',
      ],
      optimize: [
        'Roadmap → Risk → ADR cross-referenced (graph view in eng portal)',
        'Postmortem action items tracked to closure (not just "filed")',
        'Quarterly compliance + risk review on the same cadence (1 prep cycle)',
      ],
    },
    antiPatterns: [
      'Rolling 12-month roadmap that never gets locked',
      'Risk register existed at company founding; never updated',
      'ADRs only for "big" decisions (the small ones bite later)',
      'Hiring before roadmap + risk are agreed (causes mismatch)',
      'On-call ownership floats by week (degraded knowledge transfer)',
    ],
    testTypes: [
      'Quarterly roadmap reconciliation review (process check)',
      'Risk register monthly walkthrough (does each risk still apply?)',
      'ADR audit per quarter (sample 5 random decisions; can a junior reconstruct?)',
      'Postmortem closure rate (action items completed within agreed window)',
    ],
    testScenarios: [
      { scenario: 'New senior IC joins mid-quarter', expected: 'Reads roadmap + risks + ADR index; contributes by week 2' },
      { scenario: 'Production drift incident', expected: 'Risk register entry exists; mitigation invoked; postmortem within 48h' },
      { scenario: 'Quarterly leadership review', expected: 'EM presents roadmap + risk delta + ADR highlights; no surprises' },
    ],
    testData: [
      { type: 'Roadmap template', example: 'YAML schema with id, title, impact, eng_weeks, risk_link, status, blocks' },
      { type: 'Risk register schema', example: 'YAML with id, name, owner, mitigation, kill_switch, status, last_review_date' },
      { type: 'ADR template', example: 'Markdown: status, date, reversibility, decision, alternatives, why-now, links' },
    ],
    debuggingChecklist: [
      'Roadmap slip? Compare commitments to actuals; flag risks that grew',
      'Surprise incident? Was a risk register entry stale or missing?',
      'Hiring blocked? Mismatch between requested skill and roadmap+risk evidence',
      'Postmortem actions stuck? Owner unclear or no follow-up cadence',
      'New-joiner slow ramp? ADR log probably has gaps',
    ],
    productionIssues: [
      { issue: 'Embedding upgrade caused 18pp recall drop', rootCause: 'Roadmap had upgrade scheduled but no ADR linked it to RISK-002. Shadow-index work was on backlog, never sequenced before the upgrade.' },
      { issue: '6 months of cost growth went un-flagged', rootCause: 'RISK-007 entry existed but kill-switch threshold was never set. Mitigation existed in code but wasn\'t monitored.' },
      { issue: 'Senior IC quit citing "fire drills every quarter"', rootCause: 'Compliance treated as annual; Q4 always had 6 weeks piled on top of roadmap. Quarterly cadence would have spread the load.' },
    ],
    performance: [
      'Roadmap planning cycle: ~2 weeks of EM time per quarter (front-loaded)',
      'Risk register monthly review: ~1 hour with platform leads',
      'ADR write-up per decision: ~30 min for the author, ~10 min for review',
      'Postmortem: ~2-4 hours within 48h of incident',
    ],
    costConsiderations: [
      'EM time: ~4 hours/week sustained for the three artifacts',
      'Tooling: free — markdown + YAML + git; no special platform needed',
      'ROI: prevents one P0 outage per year ≫ time spent',
    ],
    observability: [
      'Roadmap progress: shipped vs committed per quarter (target ≥ 80%)',
      'Risk register health: % of risks with last_review_date < 30 days',
      'ADR coverage: % of irreversible decisions with linked ADR',
      'Postmortem closure: % of action items completed within window',
      'On-call balance: max % of weeks any one engineer is primary (target ≤ 25%)',
    ],
    metrics: [
      { name: 'roadmap_completion_rate{quarter}', example: 'Gauge; target ≥ 0.8' },
      { name: 'risk_register_stale_entries{}', example: 'Counter; alert if any entry > 30 days since last review' },
      { name: 'adr_coverage_rate{}', example: 'Gauge; target = 1.0 for irreversible decisions' },
      { name: 'postmortem_action_closure_rate{quarter}', example: 'Gauge; target ≥ 0.9 within agreed window' },
    ],
    tradeoffs: [
      { decision: 'Roadmap detail level', tradeoff: 'Too granular = brittle; too vague = unaccountable' },
      { decision: 'Risk register completeness', tradeoff: 'Every conceivable risk = noise; only obvious risks = surprises' },
      { decision: 'ADR threshold for "irreversible"', tradeoff: 'Too low = ADR fatigue; too high = decisions go untracked' },
      { decision: 'On-call rotation size', tradeoff: 'Wide = light load but stale knowledge; narrow = expert response but burnout' },
    ],
    decisionMatrix: [
      { option: 'Three-artifact discipline (this)', whenToUse: 'Team ≥ 5, multi-quarter roadmap, regulated/compliant domain' },
      { option: 'Quarterly OKRs only', whenToUse: 'Team < 5, single product, low regulatory burden' },
      { option: 'Trust-me leadership', whenToUse: 'Founder-led pre-PMF prototype phase only' },
    ],
    starStory: {
      situation: 'New AI platform team at a regulated SaaS — 8 engineers, 3 product surfaces, EU AI Act readiness deadline 9 months out.',
      task: 'Get the team operational + compliant + sustainably-paced without a 6-month "discovery phase".',
      action: 'Established the three artifacts in week 1: roadmap (Q1: foundation; Q2: first ship; Q3: hardening), risk register (drift, vendor, compliance, on-call), ADR template. Hired against roadmap — 2 senior IC + 1 SRE. Set quarterly reconciliation cadence. EU AI Act review quarterly, not annual. Postmortem template before the first incident.',
      result: 'EU AI Act readiness on time. Zero P0s in first year. New-joiner ramp dropped from 8 weeks to 2.5. Pattern adopted by sister teams. EM cited in promo as "the model for AI eng leadership".',
    },
    interviewTraps: [
      'Saying "we have OKRs" without saying who owns them or how they\'re reviewed',
      'Risk register as a one-time exercise, not a living document',
      'ADRs that read like sales pitches (no alternatives = not a real decision record)',
      'Hiring "to be safe" without roadmap + risk evidence',
      'Compliance as annual project (creates Q4 burnout cycle)',
      'Postmortems without action-item closure tracking',
    ],
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
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/jad/deep', label: 'JAD → BRD → backlog', why: 'JAD outputs feed eng-manager backlog + risk register; mini-JAD on every new constraint' },
          { href: '/admin/architect/deep', label: 'Architect collaboration', why: 'em + architect co-own ARB cadence and ADR throughput; architect signs the design, em sequences the work' },
          { href: '/admin/cicd/deep', label: 'DORA metrics tracked here', why: 'deploy frequency + lead time + change failure rate + MTTR — em-level KPIs derived from CI/CD' },
          { href: '/admin/post-release/deep', label: 'Incident management + RCA', why: 'em owns blameless postmortems + on-call rotation health; PDV + outage catalog feed em risk register' },
          { href: '/admin/checklist/deep', label: 'Production-readiness gate', why: 'em is one of the three pair-signers (lead + on-call + compliance); em escalates hard-stop overrides' },
        ]}
      />
    </div>
  );
}
