'use client';

/**
 * Production readiness master checklist (deep dive).
 *
 * Two topics: lifecycle gate (design → build → test → deploy) and the
 * governance + operations gate (FinOps, DevEx, debt, incidents). Each
 * row maps to a specific deep-dive page that owns the implementation.
 * The 6 hard-stop conditions form the GO / NO-GO rule.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — Lifecycle checklist (Design → Build → Test → Deploy)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'lifecycle-checklist',
    title: '1. Lifecycle checklist — design → build → test → deploy (sections 1–10)',
    status: 'shipped',
    coreConcept:
      'A checklist is not a doc; it is the unambiguous answer to "is this production-ready?". Every row maps to a deep-dive page that owns the implementation. If any row is unticked, the answer is no — regardless of how the team feels. The lifecycle half (design / coding / testing / CI-CD / security / observability / deployment / AI) covers what gets built and how it ships.',
    oneLiner: 'Each row maps to a deep-dive that owns it. Unticked = not production-ready. No exceptions.',
    businessContext:
      'A team thinks "we are ready". Auditor / operator / new hire arrives and asks: "where is your rollback plan / threat model / load test result / AI eval baseline?". Without a checklist, answers are scattered across Slack threads. With this checklist + every row linked to its deep-dive, the answer is one URL.',
    fiveW: {
      what: 'A 17-section checklist where every row references a deep-dive page proving how that row is met in this project.',
      why: 'Production-readiness is not a feeling; it is an evidence trail. The checklist forces evidence.',
      where: 'Pre-release gate + audit prep + new-hire onboarding + interview talking points.',
      when: 'Before every release. Before SOC 2 / ISO audit. Before exec demos.',
      who: 'Tech lead + architect + on-call + compliance owner.',
    },
    interview30s:
      'I run a single 17-section checklist. Every row maps to a deep-dive page that owns the implementation: C4 → c4-model/deep, ADR → adr/deep, baggage → tracing/deep, rollback → rollout/deep, etc. If any row is unticked, the system is not production-ready — regardless of how it feels. Six conditions are hard stops: security issue, no rollback, no monitoring, breaking change, no tracing, untested AI. Any of those = do not release.',
    hld: `flowchart LR
  Req[Release ready?] --> CL[17-section checklist]
  CL --> Arch[Architecture - C4 ADR JAD]
  CL --> Code[Coding - SOLID PEP8 def-prog]
  CL --> Test[Testing - TDD contract AI eval]
  CL --> CI[CI-CD - build once gates AI eval]
  CL --> Sec[Security - OWASP STRIDE SOC2]
  CL --> Obs[Observability - tracing baggage logs]
  CL --> Dep[Deploy - canary BG flags]
  CL --> AI[AI - model-prompt-eval-cost]
  Arch --> All
  Code --> All
  Test --> All
  CI --> All
  Sec --> All
  Obs --> All
  Dep --> All
  AI --> All
  All[All ticked?] --> GoNoGo{GO / NO-GO}
  GoNoGo -- yes --> Ship[Ship]
  GoNoGo -- no --> Block[Block release]`,
    flowchart: `flowchart TD
  Start[Pre-release] --> S1[1 Architecture - C4 + ADR]
  S1 --> S2[2 Distributed systems - tracing + baggage]
  S2 --> S3[3 Microservices - SRP + circuit breaker]
  S3 --> S4[4 Coding - SOLID + defensive]
  S4 --> S5[5 Testing - TDD + contract + AI eval]
  S5 --> S6[6 CI-CD - build once + canary]
  S6 --> S7[7 Security - OWASP + STRIDE]
  S7 --> S8[8 Observability - golden + AI signals]
  S8 --> S9[9 Deploy - probes + rollback]
  S9 --> S10[10 AI - model + prompt + eval + cost]
  S10 --> Stop{Hard stop violated?}
  Stop -- yes --> Block[Block release]
  Stop -- no --> Pass[Continue to topic 2]`,
    sequence: `sequenceDiagram
  participant Lead as Tech lead
  participant CL as Checklist
  participant DD as Deep-dive pages
  participant Audit as Auditor
  Lead->>CL: open checklist
  CL->>DD: link to c4-model adr tracing rollout etc
  DD-->>Lead: evidence per row
  Lead->>CL: tick rows
  Audit->>CL: open same checklist
  CL-->>Audit: same evidence trail no scramble`,
    coreLayers: [
      { layer: 'Architecture', responsibility: 'C4 + ADR + JAD evidence — every locked decision documented.' },
      { layer: 'Distributed systems', responsibility: 'baggage propagation + trace→draft→audit linkage.' },
      { layer: 'Microservices', responsibility: 'SRP + DB per service + circuit breaker + API versioning.' },
      { layer: 'Coding', responsibility: 'SOLID + 17-factor + defensive programming + DB query discipline.' },
      { layer: 'Testing', responsibility: 'TDD + F.I.R.S.T. + contract + AI eval.' },
      { layer: 'CI/CD', responsibility: 'build once + fail fast + DevSecOps + AI eval gate.' },
      { layer: 'Security', responsibility: 'OWASP A11–A15 + STRIDE per container + DevSecOps + SOC2.' },
      { layer: 'Observability', responsibility: 'golden + AI signals + smoke + rollback decision matrix.' },
      { layer: 'Deployment', responsibility: 'strategy fit + immutable artifact + 4-layer rollback + 3-probe.' },
      { layer: 'AI / RAG', responsibility: 'model + prompt registry + eval + guardrails + cost.' },
    ],
    lld: `classDiagram
  class Checklist {
    +sections: Section[]
    +hard_stops: HardStop[]
    +verify(release) GoNoGo
  }
  class Section {
    +rows: Row[]
    +deep_dive_url
    +ticked() bool
  }
  class Row {
    +description
    +evidence_url
    +ticked
  }
  class HardStop {
    +trigger
    +block_release: bool`,
    coreBuildingBlocks: [
      'Section 1 — Architecture & Design (C4 + ADR + system thinking) — see [c4-model/deep](/admin/c4-model/deep) + [adr/deep](/admin/adr/deep) + [jad/deep](/admin/jad/deep)',
      'Section 2 — Distributed systems (correlation_id + baggage + Jaeger) — see [tracing/deep](/admin/tracing/deep)',
      'Section 3 — Microservices (SRP + DB-per-service + circuit breaker + API versioning) — see [principles/deep](/admin/principles/deep) + [microservices/deep](/admin/microservices/deep)',
      'Section 4 — Coding & quality (SOLID + 17-factor + defensive + DB optimized) — see [principles/deep](/admin/principles/deep)',
      'Section 5 — Testing strategy (TDD + F.I.R.S.T. + contract + AI eval) — see [cicd/deep#tdd-framework-ai](/admin/cicd/deep#tdd-framework-ai)',
      'Section 6 — CI/CD pipeline (build once + canary + auto-rollback + AI gate) — see [cicd/deep](/admin/cicd/deep)',
      'Section 7 — Security (OWASP A11–A15 + STRIDE + DevSecOps + SOC2) — see [security/deep](/admin/security/deep)',
      'Section 8 — Observability (golden + AI signals + smoke + rollback matrix) — see [post-release/deep](/admin/post-release/deep)',
      'Section 9 — Deployment (probes + 4-layer rollback + flags) — see [rollout/deep](/admin/rollout/deep)',
      'Section 10 — AI / RAG (model + prompt registry + eval + cost + guardrails) — see [rag/deep](/admin/rag/deep) + [llmops/deep](/admin/llmops/deep) + [fine-tuning/deep](/admin/fine-tuning/deep)',
    ],
    architectureRelevance: {
      backend: 'Sections 1–9 apply universally.',
      rag: 'Section 2 (baggage) + Section 10 (AI) are critical; cost monitoring becomes a release-gate metric.',
      ai: 'Section 10 is the entire AI surface; eval gate + model registry rollback path tested = hard requirement.',
      microservices: 'Section 3 + Section 2 + Section 9 form the core: bounded context, baggage, 3-probe.',
    },
    problem:
      'Releases ship with "looks fine" rather than "evidence-backed". Audits are 2-week panic projects. New hires take 3 months to learn the unwritten gate. On-call inherits unknown-readiness systems.',
    whyThisApproach:
      'A checklist with cross-linked deep-dives turns folklore into evidence. Every row → page → drill → commit. Audit prep becomes "open the checklist".',
    whenToUse: [
      'Every release (production gate)',
      'SOC 2 / ISO 27001 audit prep',
      'New-hire onboarding (compressed learning)',
      'Tech lead interview (talking points)',
      'Pre-incident readiness review',
    ],
    whenNotToUse: [
      'Throwaway prototype',
      'Internal demo with no users',
      'Research notebook',
    ],
    input: 'Release artifact + 17 sections + each row\'s linked deep-dive + audit team review.',
    process: [
      'Open checklist before release',
      'For each section: open the linked deep-dive, find evidence',
      'Tick rows where evidence exists; flag rows where it does not',
      'For unticked rows: build the missing evidence OR delay release',
      'Run hard-stop check (6 conditions in topic 2)',
      'Sign off: tech lead + architect + on-call + compliance',
      'Release',
    ],
    output: 'Signed checklist (PDF / PR comment / Jira) + green light to release OR a punch list of missing evidence.',
    implementationSteps: [
      { step: 'Section 1 Architecture', logic: 'C4 L1–L7 diagrams up to date (especially L7 lifecycle); ADRs filed for every locked decision in this release; JAD trail documented.' },
      { step: 'Section 2 Tracing', logic: 'CompositePropagator(TraceContext + Baggage); HTTPXClientInstrumentor; baggage_set at edge; logs pull baggage_get_all; Jaeger filterable by tenant_id.' },
      { step: 'Section 3 Microservices', logic: 'SRP + bounded context; DB per service; circuit breaker on every external call; API versioned; contract tests in CI.' },
      { step: 'Section 4 Coding', logic: 'SOLID + 17-factor + DDD folders; type hints; lint zero warnings; no N+1; indexes on WHERE/ORDER BY columns.' },
      { step: 'Section 5 Testing', logic: 'TDD discipline (RGR); F.I.R.S.T. unit suite; contract via Pact; AI eval set + threshold gate.' },
      { step: 'Section 6 CI/CD', logic: 'Build once + immutable SHA tag + cosign + SBOM; canary or blue-green; auto-rollback on metric breach.' },
      { step: 'Section 7 Security', logic: 'OWASP A1–A15 (incl. AI threats); STRIDE per L2 container; DevSecOps shift-left gates; SOC 2 IAM controls mapped.' },
      { step: 'Section 8 Observability', logic: 'Structured JSON logs + baggage; Prometheus metrics (p95 / 5xx / saturation / token cost); Jaeger; alerts wired to rollback matrix.' },
      { step: 'Section 9 Deployment', logic: 'Strategy fit by risk; 3-probe pattern; expand-contract DB; rollback drill in last quarter.' },
      { step: 'Section 10 AI / RAG', logic: 'Model + prompt registry; regression eval set + threshold; safety guardrails; PII removed pre-ingestion; token cost dashboards + budget alerts.' },
    ],
    codeExample: {
      language: 'markdown',
      code: `# Pre-release checklist — sections 1–10
# Tick each row; link evidence URL.

## §1 Architecture
- [ ] C4 L1–L7 diagrams updated (link)
- [ ] ADRs filed for locked decisions in this release (link)
- [ ] JAD trail / BRD updated if scope changed (link)

## §2 Distributed systems / tracing
- [ ] CompositePropagator(TraceContext + Baggage) wired in server_common
- [ ] baggage_set("tenant_id", ...) in auth middleware
- [ ] HTTPXClientInstrumentor enabled
- [ ] Logs include baggage fields
- [ ] Jaeger trace filterable by baggage.tenant_id

## §3 Microservices
- [ ] One service = one bounded context
- [ ] DB per service (no cross-service DB access)
- [ ] Circuit breaker on every external call
- [ ] API versioned (URL or header)
- [ ] Contract tests green in CI

## §4 Coding
- [ ] Linter zero warnings
- [ ] Type hints (mypy strict)
- [ ] No catch-all exceptions
- [ ] No N+1 queries
- [ ] Indexes on WHERE / ORDER BY columns

## §5 Testing
- [ ] Unit suite < 1 min, F.I.R.S.T. honored
- [ ] Integration via Testcontainers
- [ ] Contract tests (Pact)
- [ ] AI eval set + threshold gate (if AI feature)

## §6 CI/CD
- [ ] CI < 10 min
- [ ] Build once + SHA tag + cosign + SBOM
- [ ] Canary or blue-green deploy
- [ ] Auto-rollback on golden signal breach

## §7 Security
- [ ] OWASP A1–A15 reviewed (incl AI A11–A15)
- [ ] STRIDE table per new L2 container
- [ ] No secrets in code (Vault / KMS only)
- [ ] DevSecOps gates green (SAST + SCA + secret scan)
- [ ] Container image scanned + signed

## §8 Observability
- [ ] Structured JSON logs + baggage fields
- [ ] Golden signals dashboard
- [ ] AI signals (LLM p95, token cost, eval, hallucination)
- [ ] Synthetic monitor on critical journey
- [ ] Alerts mapped to rollback matrix

## §9 Deployment
- [ ] /health/startup, /health/live, /health/ready wired
- [ ] DB expand-contract (no DROP / RENAME this release)
- [ ] Feature flag for new feature (default OFF)
- [ ] Rollback drill in last quarter

## §10 AI / RAG (if applicable)
- [ ] Model in registry with rollback path tested
- [ ] Prompt versioned in registry
- [ ] Regression eval set + threshold gate
- [ ] PII removed pre-ingestion
- [ ] Output guardrail (safety + format)
- [ ] Token cost budget + alert
- [ ] Fallback model defined`,
    },
    realUseCase:
      'Team adopted checklist before SOC 2 prep. Audit prep "10-page security narrative" replaced with "open the checklist; every row linked to evidence". Audit timeline: 2 weeks → 4 hours of staff interviews. Auditor comment: "this is the cleanest evidence trail we have seen this year".',
    prosCons: {
      pros: [
        'Audit prep collapses from weeks to hours',
        'New-hire onboarding has a single map',
        'Release decisions become evidence-driven',
        'Interview answers come pre-structured',
      ],
      cons: [
        'Requires every deep-dive to be maintained',
        'Tick-discipline depends on tech lead culture',
        'Cross-references rot if pages move',
      ],
    },
    limitations: [
      'A checklist is necessary but not sufficient — needs culture',
      'Some rows depend on AI eval set quality (which can rot)',
      'Audit-friendly ≠ user-friendly — different artifacts',
    ],
    comparison: {
      left: '"Looks fine" gate',
      right: 'Evidence-backed checklist',
      rows: [
        { aspect: 'Audit prep time', left: '2 weeks panic', right: '4 hours' },
        { aspect: 'New-hire ramp', left: '3 months tribal', right: '3 weeks via deep-dives' },
        { aspect: 'Release decision', left: 'Vibes', right: 'Tick-rate' },
        { aspect: 'Incident review', left: 'Surprise gaps', right: 'Known unticked rows' },
      ],
    },
    challenges: [
      'Keeping cross-links from rotting (pages move)',
      'Sustaining tick discipline under release pressure',
      'AI eval set freshness',
      'New rows added when new threats emerge',
    ],
    edgeCases: [
      { case: 'Row unticked but release urgent', solution: 'Document as "accepted risk" in ADR; cap risk window; revisit post-release' },
      { case: 'AI feature added mid-release', solution: 'Section 10 mini-review; eval set baseline before promote' },
      { case: 'Auditor asks for evidence not on checklist', solution: 'Add row + deep-dive; checklist evolves' },
    ],
    solutions: [
      { problem: 'Audit panic', solution: 'Checklist + linked deep-dives = pre-built evidence trail' },
      { problem: 'New-hire long ramp', solution: 'Single map of every architectural surface' },
      { problem: 'Release feels-based', solution: 'Tick-rate + hard-stop check' },
      { problem: 'Page rot', solution: 'Quarterly cross-link review' },
    ],
    bestPractices: {
      do: [
        'Tick honestly (not aspirationally)',
        'Link every row to its deep-dive',
        'Treat unticked = "do not ship"',
        'Add rows when new threats / patterns emerge',
        'Quarterly cross-link review',
      ],
      avoid: [
        'Tick all rows for the demo',
        'Long-form text instead of links',
        'Letting deep-dives rot',
        'Skipping rows because "we have always done X"',
      ],
      optimize: [
        'Auto-generate checklist from deep-dive index',
        'CI bot comments tick-rate on PRs',
        'Link to last incident that motivated each row',
      ],
    },
    antiPatterns: [
      'Aspirational ticking',
      'Checklist without linked evidence',
      'Skipping security or AI sections "because team knows it"',
      'Treating it as a "doc" instead of a release gate',
    ],
    testing: ['Drill: open checklist; verify every link returns 200', 'Audit dry-run: pick 3 rows; reconstruct evidence', 'New-hire test: can a new engineer find the source of any row?'],
    testTypes: ['Drill', 'Dry-run audit', 'Onboarding test'],
    testScenarios: [
      { scenario: 'All sections green + no hard stop', expected: 'Release approved' },
      { scenario: '1 hard stop violated (e.g., no rollback)', expected: 'Release blocked' },
      { scenario: '3 yellow rows (unsigned but non-blocking)', expected: 'ADR for accepted risks; release approved with cap' },
      { scenario: 'New AI feature', expected: 'Section 10 fully ticked or release blocked' },
    ],
    testData: [
      { type: 'Real release example', example: 'v2.4 release: 17/17 sections ticked; 0 hard stops; signed by lead+architect+on-call' },
      { type: 'Negative example', example: 'v2.5: skipped section 8 (no synthetic monitor); release blocked → added monitor → re-checked' },
    ],
    debuggingChecklist: [
      'Every row has a deep-dive link?',
      'Links return 200?',
      'Hard-stop conditions documented in topic 2?',
      'Sign-off captured per release?',
      'Quarterly cross-link review scheduled?',
    ],
    productionIssues: [
      { issue: 'Checklist ticked but incident', rootCause: 'Aspirational ticking; tighten honesty + link evidence per row' },
      { issue: 'Release blocked unfairly', rootCause: 'Row not relevant to this change; document scope + carry-over to next release' },
      { issue: 'Auditor finds gap not on checklist', rootCause: 'Add row + new deep-dive page' },
    ],
    security: ['Checklist itself is internal-only', 'Audit log who signed off + when'],
    performance: ['Pre-release review: 30 min for routine; 2 h for major'],
    costConsiderations: [
      'Initial cost: time to author every deep-dive page',
      'Recurring cost: quarterly review',
      'Saving: weeks of audit prep + new-hire time',
    ],
    scaling: ['Per-team checklists with shared core sections', 'Auto-generated tick-rate dashboard'],
    observability: ['Tick-rate per release', 'Hard-stop hit count', 'Evidence link health (404 alert)'],
    metrics: [
      { name: 'tick_rate_percent', example: '100' },
      { name: 'hard_stop_hits_per_quarter', example: '0' },
      { name: 'audit_prep_hours', example: '4' },
      { name: 'broken_evidence_links', example: '0' },
    ],
    failureModes: [
      { mode: 'Aspirational ticking', detect: 'Incident rate vs tick rate diverge', recover: 'Honesty culture + paired sign-off' },
      { mode: 'Cross-link rot', detect: '404 monitor on checklist links', recover: 'Quarterly review + link redirect map' },
      { mode: 'Audit-only checklist', detect: 'Tick-rate spikes only at audit time', recover: 'Embed in PR template + release process' },
    ],
    tradeoffs: [
      { decision: 'Comprehensive vs lean', tradeoff: 'Comprehensive = audit-ready; lean = faster review' },
      { decision: 'Auto-generated vs hand-curated', tradeoff: 'Auto stays in sync; hand has narrative' },
    ],
    decisionMatrix: [
      { option: 'No checklist', whenToUse: 'Throwaway code only' },
      { option: 'Lightweight checklist', whenToUse: 'Pre-MVP startup' },
      { option: 'Full 17-section', whenToUse: 'Production AI / multi-tenant SaaS / regulated' },
    ],
    starStory: {
      situation: 'SOC 2 audit prep started 2 weeks before scheduled audit; team scrambled.',
      task: 'Build evidence trail without burning out team.',
      action: 'Stood up the 17-section checklist with every row linking to a deep-dive page. Each page already had drill + commit history + ADR cross-refs. Auditor walked through checklist row-by-row.',
      result: 'Audit completed in 4 hours of staff interviews vs 2 weeks of slide prep. Zero findings on technical controls. Auditor commented: "cleanest evidence trail we have seen this year". Re-used for next year with quarterly refresh.',
    },
    interviewTraps: [
      'Saying "we are production-ready" without naming the gate',
      'No mention of hard-stop conditions',
      'No cross-link to evidence',
      'Aspirational ticking story',
    ],
    finalScript:
      'I run a 17-section checklist. Every row maps to a deep-dive page that owns the implementation; every deep-dive has a drill + ADR + commit history. Six conditions are hard stops: security, no rollback, no monitoring, breaking change, no tracing, untested AI. Any of those = block. Audit prep: 4 hours; new-hire ramp: weeks not months.',
    alternatives: [
      { name: 'Vibes-based gate', tradeoff: 'Fast; opaque; audit panic' },
      { name: 'Long-form policy doc', tradeoff: 'Comprehensive; nobody reads it' },
      { name: 'Tool-driven (Jira / Backstage)', tradeoff: 'Auto-tracked; rigid; less narrative' },
      { name: 'This: linked checklist + deep-dives', tradeoff: 'Best of both; requires page maintenance' },
    ],
    monitoring: ['Tick-rate per release dashboard', 'Hard-stop hit alerts', 'Evidence-link 404 monitor'],
    maturity: {
      mvp: '5-section checklist + sign-off',
      production: 'Full 17-section + linked deep-dives + hard stops',
      enterprise: 'Auto-tick dashboard + per-team variants + quarterly cross-link review',
    },
    projectFit: ['Production AI', 'Multi-tenant SaaS', 'Regulated workloads', 'Audit-bound'],
    interviewLine: 'Every row → deep-dive. Six hard stops. Audit in hours, not weeks.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — Governance + Ops checklist + GO/NO-GO hard stops
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'governance-ops-checklist',
    title: '2. Governance + ops checklist (sections 11–17) + the 6 hard-stop GO / NO-GO rule',
    status: 'shipped',
    coreConcept:
      'The lifecycle half (sections 1–10) tells you "is the build ready". The governance + ops half (sections 11–17) tells you "is the system you operate ready" — governance, FinOps, DevEx, technical evolution, debt, and incident response. Plus the hard-stop rule: 6 conditions that block release regardless of how green sections 1–10 look. Hard stops exist because some failures are catastrophic — security breach, data loss via no rollback, blind ops via no monitoring, customer breakage via breaking change, debug-impossible via no tracing, AI quality drift via untested promote.',
    oneLiner: 'Sections 11–17 = the system you operate. Six hard stops = the failures you cannot recover from. Any hard stop hit = block.',
    businessContext:
      'Team passes lifecycle checklist; ships; chaos in week 2 because: cost runs 3× projection (no FinOps), on-call burnt out (no incident response plan), new hire takes 3 months (no DevEx), tech debt compounds (no register). Sections 11–17 prevent the slow-burn failures that lifecycle alone misses.',
    fiveW: {
      what: 'Sections 11–17 covering governance, documentation, FinOps, DevEx, evolution, debt, incidents — plus the 6 hard-stop conditions.',
      why: 'Lifecycle quality alone is not operational quality. A great release that nobody can operate is still a failure.',
      where: 'Pre-release review + quarterly health check + post-incident retrospective.',
      when: 'Every release + quarterly + post-incident.',
      who: 'Tech lead + on-call lead + finance partner + compliance + new-hire mentor.',
    },
    interview30s:
      'Lifecycle quality alone fails on operational gaps. Sections 11–17 cover governance (ARB + tech radar), documentation (runbooks + why), FinOps (tagging + budgets), DevEx (< 1h local setup), evolution (deprecation + strangler), debt (20% capacity), and incidents (RCA + blameless). Six hard-stop conditions block release even if other sections are green: security issue, no rollback, no monitoring, breaking change, no tracing, untested AI. Any one = do not ship.',
    hld: `flowchart LR
  S11[11 Governance] --> All
  S12[12 Documentation] --> All
  S13[13 FinOps] --> All
  S14[14 DevEx] --> All
  S15[15 Evolution] --> All
  S16[16 Debt] --> All
  S17[17 Incidents] --> All
  All[Sections green?] --> HardStop{Hard stops}
  HardStop -- any hit --> Block[BLOCK release]
  HardStop -- none --> Ship[Ship + monitor]`,
    flowchart: `flowchart TD
  Start[Pre-release section 11-17] --> S11[Governance - ARB + tech radar + audit]
  S11 --> S12[Documentation - runbook + why]
  S12 --> S13[FinOps - tagging + budgets + autoscale]
  S13 --> S14[DevEx - local setup + golden path]
  S14 --> S15[Evolution - deprecation + strangler]
  S15 --> S16[Debt - 20 percent capacity + register]
  S16 --> S17[Incidents - on-call + RCA + blameless]
  S17 --> HS[Hard-stop check]
  HS --> H1{Security issue?}
  H1 -- yes --> Block[BLOCK]
  H1 -- no --> H2{No rollback?}
  H2 -- yes --> Block
  H2 -- no --> H3{No monitoring?}
  H3 -- yes --> Block
  H3 -- no --> H4{Breaking change?}
  H4 -- yes --> Block
  H4 -- no --> H5{No tracing?}
  H5 -- yes --> Block
  H5 -- no --> H6{Untested AI?}
  H6 -- yes --> Block
  H6 -- no --> Ship[GO]`,
    sequence: `sequenceDiagram
  participant Lead
  participant Sections as 11 to 17
  participant HS as Hard stops
  participant Result
  Lead->>Sections: review 11-17
  Sections-->>Lead: tick rate
  Lead->>HS: 6 hard-stop check
  HS-->>Result: any hit then BLOCK else GO
  Note over Lead,Result: signed: lead + on-call + compliance`,
    coreLayers: [
      { layer: 'Governance', responsibility: 'ARB + Tech Radar + audit logs (12 mo) + version-controlled policies.' },
      { layer: 'Documentation', responsibility: 'README per service + auto API docs + runbook + WHY documented.' },
      { layer: 'FinOps', responsibility: 'Resource tagging + per-service cost + autoscaling + idle removal + right-sizing.' },
      { layer: 'DevEx', responsibility: '< 1h local setup + Docker/devcontainer + golden path + service template + portal.' },
      { layer: 'Evolution', responsibility: 'Tech radar enforced + deprecation policy + strangler + ACL + flags.' },
      { layer: 'Debt', responsibility: '20% capacity reserved + visible register + planned refactor windows.' },
      { layer: 'Incidents', responsibility: 'Golden signals + synthetic + on-call + IR plan + RCA + blameless postmortem.' },
      { layer: 'Hard stops', responsibility: 'Six conditions any of which blocks regardless of other tick-rates.' },
    ],
    lld: `classDiagram
  class HardStops {
    +security_issue: bool
    +no_rollback: bool
    +no_monitoring: bool
    +breaking_change: bool
    +no_tracing: bool
    +untested_ai: bool
    +any_hit() bool
  }
  class Decision {
    +tick_rate
    +hard_stops
    +verdict() GoNoGo
  }
  HardStops --> Decision`,
    coreBuildingBlocks: [
      'Section 11 — Governance (ARB + tech radar + audit retention) — see [security/deep#cloud-soc2-iam](/admin/security/deep#cloud-soc2-iam)',
      'Section 12 — Documentation (README + auto API docs + runbook + ADRs) — see [adr/deep](/admin/adr/deep)',
      'Section 13 — FinOps (tagging + budgets + autoscale + cost dashboards)',
      'Section 14 — DevEx (devcontainer + golden path + service chassis)',
      'Section 15 — Evolution (tech radar + deprecation + strangler + ACL + feature flags)',
      'Section 16 — Debt (20% capacity + register + scheduled refactor)',
      'Section 17 — Incidents (golden signals + on-call + RCA + blameless postmortem) — see [post-release/deep](/admin/post-release/deep)',
      'Hard stops × 6: security / no-rollback / no-monitoring / breaking-change / no-tracing / untested-AI',
    ],
    architectureRelevance: {
      backend: 'All 7 sections apply.',
      rag: 'FinOps especially critical (token cost) + AI hard-stop (untested AI).',
      ai: 'Hard-stop "untested AI" = eval gate before promote; non-negotiable.',
      microservices: 'DevEx + Evolution sections compound; per-service onboarding cost adds up.',
    },
    problem:
      'Lifecycle-green release fails operationally. Cost runaway, on-call burnout, new-hire stalls, debt compounds. Hard-stop-violated release = catastrophic incident.',
    whyThisApproach:
      'Operational quality is structural, not aspirational. Hard stops codify the failures from which recovery is most expensive.',
    whenToUse: [
      'Every release (ops gate)',
      'Quarterly system health check',
      'Post-incident review',
      'Pre-audit prep',
    ],
    whenNotToUse: [
      'Throwaway prototype',
      'Pre-MVP exploration',
    ],
    input: 'Sections 11–17 evidence + 6 hard-stop check + sign-off.',
    process: [
      'Review section 11 — governance (ARB minutes, tech radar version, audit log retention)',
      'Review 12 — documentation (every service has README + runbook; "why" documented)',
      'Review 13 — FinOps (tagging applied; per-service cost visible; autoscale on)',
      'Review 14 — DevEx (new-hire test: < 1h local setup)',
      'Review 15 — evolution (deprecation policy enforced; strangler in flight if any)',
      'Review 16 — debt (register visible; 20% capacity reserved this sprint)',
      'Review 17 — incidents (on-call rotation defined; IR plan tested in last quarter)',
      'Run 6 hard-stop check: any hit = BLOCK',
      'Sign-off + GO/NO-GO',
    ],
    output: 'Signed sections 11–17 + hard-stop check result + GO/NO-GO verdict.',
    implementationSteps: [
      { step: '§11 Governance', logic: 'ARB reviews ADRs cross-team; Tech Radar Adopt/Trial/Assess/Hold; audit log ≥ 12 months; SOC 2 / ISO controls mapped.' },
      { step: '§12 Documentation', logic: 'Every service has README + runbook; API docs auto-generated; architecture diagrams in same repo as code; "why" documented (not just "what").' },
      { step: '§13 FinOps', logic: 'Tagging mandatory (team / env / cost_center); per-service cost dashboard; autoscale at ~60% (headroom); idle dev/QA off-hours.' },
      { step: '§14 DevEx', logic: 'Local setup < 1 hour (devcontainer / make up); golden path documented; service template available; central portal (Backstage).' },
      { step: '§15 Evolution', logic: 'Tech radar enforced via templates + lint; APIs N-1 supported with 90-180 day deprecation; strangler for legacy migration; ACL around messy externals.' },
      { step: '§16 Debt', logic: '20% sprint capacity reserved; debt register on Jira board; refactor windows planned (not ad-hoc); definition-of-done = no new critical issues.' },
      { step: '§17 Incidents', logic: 'Golden signals tracked; synthetic monitor on critical journey; on-call rotation defined; IR plan tested quarterly; RCA via 5 Whys; blameless postmortems → permanent regression test.' },
      { step: 'Hard stop check', logic: 'security issue / no rollback / no monitoring / breaking change / no tracing / untested AI — any hit = BLOCK regardless of other tick-rates.' },
    ],
    codeExample: {
      language: 'markdown',
      code: `# Pre-release checklist — sections 11–17 + GO/NO-GO

## §11 Governance
- [ ] ARB reviewed all ADRs in this release
- [ ] Tech Radar version current (Adopt/Trial/Assess/Hold)
- [ ] Audit log retention ≥ 12 months verified
- [ ] SOC 2 / ISO controls mapped to this release's changes

## §12 Documentation
- [ ] Every changed service has README + runbook updated
- [ ] API docs auto-generated + published
- [ ] Architecture diagrams updated (especially C4 L7 lifecycle)
- [ ] "Why" documented in ADR + commit messages

## §13 FinOps
- [ ] Resource tags applied (team / env / cost_center)
- [ ] Per-service cost dashboard reviewed
- [ ] Autoscaling configured (~60% trigger)
- [ ] Idle dev/QA scheduled to shut off-hours

## §14 DevEx
- [ ] New hire can run local stack in < 1 hour
- [ ] Devcontainer / docker compose works on day 1
- [ ] Golden path docs current
- [ ] Service template version current

## §15 Evolution
- [ ] Tech radar respected (no Hold-tier dependencies introduced)
- [ ] Deprecation policy enforced (N-1 APIs supported)
- [ ] Strangler / ACL flagged if legacy migration in flight
- [ ] Feature flag for new behavior (default OFF)

## §16 Tech Debt
- [ ] 20% sprint capacity reserved this sprint
- [ ] Debt register reviewed
- [ ] Refactor windows scheduled (not ad-hoc)
- [ ] No new critical issues added by this release

## §17 Incidents
- [ ] Golden signals dashboard live
- [ ] Synthetic monitor on critical journey
- [ ] On-call rotation defined for this week
- [ ] IR plan tested in last quarter (drill record)
- [ ] RCA template ready (5 Whys + blameless)


## ⛔ HARD STOPS (any hit → BLOCK release)

| # | Hard stop | Check |
|---|-----------|-------|
| 1 | Security issue | OWASP / SAST / SCA / secret scan: any high open? |
| 2 | No rollback | Rollback path tested in staging this quarter? |
| 3 | No monitoring | Golden signals + synthetic monitor live? |
| 4 | Breaking change | API / DB / contract back-compat verified? |
| 5 | No tracing | CompositePropagator + baggage wired + verified? |
| 6 | Untested AI | Eval gate green within delta of baseline? |

## Sign-off
- Tech lead: __________ date __________
- On-call lead: __________ date __________
- Compliance / security: __________ date __________

VERDICT:  [ ] GO    [ ] NO-GO`,
    },
    realUseCase:
      'Team passed sections 1–10 (lifecycle) but flagged hard-stop #5 (no tracing — baggage was missing). Release blocked one day. Wired baggage + drill + deep-dive. Re-run: all 6 hard stops clear; sections 1–17 ticked. Released. Three weeks later when the cross-service incident hit, baggage propagation made root-cause analysis 90 sec instead of 30 min — directly attributable to the hard-stop catch.',
    prosCons: {
      pros: [
        'Catches operational failures lifecycle alone misses',
        'Hard stops codify "do not recover from" failures',
        'Sign-off is paired (lead + on-call + compliance)',
        'Audit-ready: 7 ops sections + 6 hard stops = 13 evidence points',
      ],
      cons: [
        'Adds review time per release',
        'Quarterly drills cost engineering hours',
        'Hard stops can feel rigid for routine changes',
      ],
    },
    limitations: [
      'Hard stops are necessary but not exhaustive — novel failures emerge',
      'Tick-rate is a proxy, not certainty',
      'Some sections (DevEx, debt) are slow-burn — not directly release-gated',
    ],
    comparison: {
      left: 'Lifecycle-only checklist',
      right: 'Lifecycle + Ops + Hard stops',
      rows: [
        { aspect: 'Catches build issues', left: 'Yes', right: 'Yes' },
        { aspect: 'Catches operational issues', left: 'No', right: 'Yes' },
        { aspect: 'Catches catastrophic failure modes', left: 'Maybe', right: 'Yes (hard stops)' },
        { aspect: 'Audit readiness', left: 'Partial', right: 'Full' },
        { aspect: 'Sustainable on-call', left: 'No (burnout risk)', right: 'Yes (§17 covers it)' },
      ],
    },
    challenges: [
      'Hard-stop fatigue if too many releases hit them',
      'Section 16 (debt) hardest to enforce under release pressure',
      'Section 14 (DevEx) easy to defer ("we will fix it next sprint")',
      'Cost dashboards lag actual spend by hours',
    ],
    edgeCases: [
      { case: 'Hard stop hit on hotfix for a P0', solution: 'Document in ADR; define risk window; revisit within 24h post-release' },
      { case: 'No tracing on internal-only service', solution: 'Hard stop applies if it touches user request path; internal-only async OK if logged' },
      { case: 'AI feature behind flag at 0%', solution: 'Eval gate still applies before flag flips; do not skip' },
    ],
    solutions: [
      { problem: 'Cost runaway', solution: '§13 tagging + per-service dashboard + alert' },
      { problem: 'On-call burnout', solution: '§17 IR plan + drill + rotation + blameless culture' },
      { problem: 'New-hire stall', solution: '§14 < 1h local setup + golden path' },
      { problem: 'Debt compound', solution: '§16 20% capacity + register + scheduled refactor' },
      { problem: 'Catastrophic release', solution: 'Hard-stop check before sign-off' },
    ],
    bestPractices: {
      do: [
        '20% capacity for §16 debt — protected',
        'Quarterly IR drill for §17',
        'Per-service cost alert for §13',
        'Tick honestly + hard-stop check pre sign-off',
        'Pair sign-off (lead + on-call + compliance)',
      ],
      avoid: [
        'Skip §16 because release pressure',
        'Defer §14 DevEx investment indefinitely',
        'Hard stops as guidelines (they are blockers)',
        'Single sign-off (no pair check)',
      ],
      optimize: [
        'Auto-tick where signals are machine-checkable (cost, autoscale, monitor live)',
        'Hard-stop dashboard',
        'Drill calendar visible',
      ],
    },
    antiPatterns: [
      'Hard stops downgraded to "warnings"',
      'Section 16 debt-register exists but never groomed',
      'On-call rotation but no drill',
      '"We have monitoring" without verifying alerts fire',
    ],
    testing: ['Drill: hard-stop #5 (baggage); set up service with no propagator; verify checklist blocks', 'Quarterly IR drill', 'Audit dry-run on sections 11-17'],
    testTypes: ['Drill', 'IR drill (chaos)', 'Audit dry-run'],
    testScenarios: [
      { scenario: 'All 17 sections green + 0 hard stops', expected: 'GO' },
      { scenario: 'Section 14 yellow (DevEx degraded) but no hard stop', expected: 'GO with ADR + follow-up' },
      { scenario: '1 hard stop hit (no tracing)', expected: 'NO-GO regardless of other green' },
      { scenario: 'Untested AI hard stop', expected: 'NO-GO until eval gate green' },
    ],
    testData: [
      { type: 'Real release record', example: 'v2.5: hard-stop #5 caught; release delayed 1 day; baggage drill added permanently' },
      { type: 'Counterexample', example: 'v2.4 (pre-checklist): shipped with no rollback drill; quarterly review revealed; backfilled' },
    ],
    debuggingChecklist: [
      'Sections 11–17 all reviewed?',
      '6 hard stops checked individually?',
      'Pair sign-off captured?',
      'ADR for accepted risks?',
      'Drill schedule current?',
    ],
    productionIssues: [
      { issue: 'Cost spike after release', rootCause: '§13 dashboard reviewed at sign-off but autoscale config wrong; verify autoscale params not just "configured"' },
      { issue: 'On-call burnout in week 2', rootCause: '§17 IR plan exists but no drill in last quarter; calendar drill quarterly' },
      { issue: 'Hard-stop bypass via "trust me"', rootCause: 'Pair sign-off compromised; require compliance signature on hard-stop overrides' },
    ],
    security: ['Sign-off audit trail', 'Hard-stop overrides require compliance sig', 'Quarterly hard-stop hit-rate review'],
    performance: ['Pre-release ops review: 30 min routine, 1 h major', 'Hard-stop check: 5 min'],
    costConsiderations: [
      'Quarterly IR drill cost: ~1 day eng time',
      'DevEx investment compounds (saves new-hire weeks)',
      'Debt 20% capacity = direct opportunity cost; saves rewrite cost later',
    ],
    scaling: ['Per-team variants of §11–17', 'Auto-checked rows (cost, autoscale, monitor)', 'Hard-stop dashboard'],
    observability: ['Hard-stop hit-rate per quarter', 'Tick-rate dashboard', 'Drill calendar adherence'],
    metrics: [
      { name: 'hard_stop_hits_per_quarter', example: '1' },
      { name: 'release_with_full_signoff_percent', example: '100' },
      { name: 'ir_drill_adherence_percent', example: '100 (quarterly)' },
      { name: 'tech_debt_capacity_percent_actual', example: '18 (target 20)' },
      { name: 'devex_local_setup_minutes_p95', example: '52' },
    ],
    failureModes: [
      { mode: 'Hard stop overridden', detect: 'Audit log of overrides', recover: 'Require compliance + post-mortem on every override' },
      { mode: 'Drill cadence slips', detect: 'Quarterly review', recover: 'Auto-calendar + hard-stop metric on missed drill' },
      { mode: 'Section 16 ignored', detect: 'Capacity report', recover: 'Make 20% sprint allocation visible in standup' },
    ],
    tradeoffs: [
      { decision: 'Strict hard stops', tradeoff: 'Blocks some routine releases; saves catastrophic ones' },
      { decision: 'Pair sign-off', tradeoff: 'Slower release; catches single-point-of-trust failures' },
      { decision: '20% debt capacity', tradeoff: 'Slower feature velocity short term; massive saving long term' },
    ],
    decisionMatrix: [
      { option: 'No ops checklist', whenToUse: 'Pre-MVP only' },
      { option: 'Sections 11-17 only', whenToUse: 'Established team adding ops discipline' },
      { option: 'Sections 1-17 + hard stops', whenToUse: 'Production AI / regulated / multi-tenant SaaS' },
    ],
    starStory: {
      situation: 'New release passed lifecycle (sections 1–10) but failed hard-stop #5 (no tracing baggage). Release lead wanted to ship anyway.',
      task: 'Apply discipline; establish that hard stops are real blockers.',
      action: 'Blocked release. Wired CompositePropagator + baggage + drill + deep-dive. Re-ran checklist; all 6 hard stops clear. Shipped one day late.',
      result: 'Three weeks later cross-service incident hit; baggage propagation made root cause obvious in 90 sec vs 30 min. Direct attribution: the one-day delay paid for itself many times over. Hard stops accepted as real blockers across team.',
    },
    interviewTraps: [
      'Citing only the lifecycle checklist',
      'No mention of hard stops',
      'No mention of pair sign-off',
      'Skipping §16 debt or §17 incidents',
    ],
    finalScript:
      'Sections 11–17 cover what happens after build: governance, docs, FinOps, DevEx, evolution, debt, incidents. Six hard stops codify catastrophic failure modes — security, no rollback, no monitoring, breaking change, no tracing, untested AI. Pair sign-off (lead + on-call + compliance). Hard stops are real blockers; overrides require compliance signature + post-mortem.',
    alternatives: [
      { name: 'Lifecycle only (1–10)', tradeoff: 'Misses operational + catastrophic failure modes' },
      { name: 'Vibes-based ops gate', tradeoff: 'Fast; opaque; on-call burnout risk' },
      { name: 'This: 11–17 + hard stops', tradeoff: 'Slower review; sustainable system' },
    ],
    monitoring: ['Hard-stop hit rate', 'Tick-rate per release', 'Drill adherence', 'Sign-off completeness'],
    maturity: {
      mvp: '5 hard stops + pair sign-off',
      production: 'Full sections 11–17 + 6 hard stops + quarterly drill',
      enterprise: 'Auto-checked rows + per-team variants + drill calendar enforcement',
    },
    projectFit: ['Production AI', 'Regulated SaaS', 'Multi-tenant', 'Audit-bound'],
    interviewLine: 'Lifecycle is build readiness. 11–17 is system readiness. Six hard stops are non-negotiable.',
  },
];

export default function ChecklistDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Production readiness master checklist (deep dive)</h1>
        <p className="design-areas-sub">
          The unifying release gate. Two halves: the lifecycle checklist
          (sections 1–10: design → build → test → deploy → AI) and the
          governance + ops checklist (sections 11–17: governance, docs, FinOps,
          DevEx, evolution, debt, incidents). Six hard-stop conditions block
          release regardless of how green other sections look. Every row links
          to the deep-dive page that owns the implementation evidence.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
