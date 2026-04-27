'use client';

/**
 * JAD — Joint Application Design (deep dive).
 *
 * "JAD = WHAT + WHY (business consensus). C4 = HOW (architecture).
 * ADR = WHY (technical decisions)." This page covers the AI-extended
 * JAD framework: 4-day session structure, day-by-day questions, the
 * JAD → BRD → C4 → ADR delivery chain, and AI-specific extensions
 * (model selection, hallucination risk, data sensitivity, governance,
 * cost constraints).
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — JAD FUNDAMENTALS
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'jad-fundamentals',
    title: '1. JAD fundamentals — purpose, structure, AI extensions',
    status: 'shipped',
    coreConcept: 'JAD (Joint Application Design) is the multi-day session that aligns business + product + engineering + AI on requirements, risks, and constraints BEFORE any code is written. AI-extended JAD adds model selection, hallucination risk, data sensitivity, governance, cost.',
    oneLiner: 'JAD = WHAT + WHY. C4 = HOW. ADR = WHY (technical). All three together = enterprise delivery.',
    businessContext: 'Without JAD, requirements drift, stakeholders disagree, and AI-specific decisions (RAG vs ML, hallucination tolerance, HITL) get made implicitly. JAD forces explicit alignment in 4 days; downstream BRD/C4/ADR work cleanly off the JAD output.',
    fiveW: {
      what: 'A 4-day facilitated session aligning business + product + engineering + AI + security + sponsor on requirements, decisions, risks, and approvals. Outputs feed BRD/C4/ADR.',
      why: 'Misalignment caught at JAD costs hours; caught in code costs weeks; caught in production costs incidents.',
      where: 'Day 1 of any AI project; before any architectural commitment.',
      when: '4 consecutive days (or 4 sessions over 2 weeks).',
      who: 'Facilitator (you/TL) + Scribe + Business (PO) + Users + Architect + AI specialist + Security + Sponsor.',
    },
    interview30s: 'JAD is the multi-day session where business, engineering, and AI decisions converge. Standard C4-era JAD covered functional + non-functional requirements; AI-extended JAD adds five gold dimensions: model selection (RAG vs ML vs rule-based), hallucination risk + tolerance, data sensitivity (PII / PHI / public), governance + HITL approval, cost constraints (token budget, query latency). Four-day flow: Day 1 business discovery, Day 2 requirements + AI decisions, Day 3 architecture + risks, Day 4 validation + consensus. JAD output feeds BRD, C4, ADR as the unified delivery chain.',
    hld: `flowchart TB
  JAD[JAD session 4 days] --> BRD[Business Requirements Doc]
  JAD --> ScopeDoc[Scope statement]
  JAD --> RiskReg[Risk register]
  JAD --> Decisions[Decision log]
  BRD --> C4[C4 architecture]
  Decisions --> ADRs[ADR catalog]
  RiskReg --> Gov[Governance layer]
  C4 --> Code
  ADRs --> Code
  Gov --> Code
  Code --> Test --> Deploy`,
    networkFlow: `flowchart LR
  Stake[Stakeholders] --> JADRoom[JAD session]
  JADRoom --> Outputs[BRD + ScopeDoc + RiskReg + Decisions]
  Outputs --> Repo[Git repo docs/]`,
    flowchart: `flowchart LR
  D1[Day 1 Business Discovery] --> D2[Day 2 Requirements + AI]
  D2 --> D3[Day 3 Architecture + Risk]
  D3 --> D4[Day 4 Validation + Consensus]
  D4 --> Out[Approved deliverables]`,
    sequence: `sequenceDiagram
  participant FA as Facilitator
  participant PO as Product
  participant AR as Architect
  participant AI as AI Specialist
  participant SEC as Security
  participant SP as Sponsor
  FA->>PO: business discovery
  PO->>FA: pain + KPI
  FA->>AR: architecture options
  FA->>AI: model selection
  AI-->>FA: RAG vs ML decision
  FA->>SEC: data sensitivity + risk
  SEC-->>FA: HITL required
  FA->>SP: approval
  SP-->>FA: signed off`,
    coreLayers: [
      { layer: 'Day 1 — Business Discovery', responsibility: 'Problem + users + KPI + success metric.' },
      { layer: 'Day 2 — Requirements + AI Decisions', responsibility: 'Functional + non-functional + RAG/ML choice + accuracy targets + HITL.' },
      { layer: 'Day 3 — Architecture + Risk', responsibility: 'Latency + integrations + hallucination/PII/failure mitigations.' },
      { layer: 'Day 4 — Validation + Consensus', responsibility: 'Final review + sponsor signoff + action items.' },
      { layer: 'Outputs', responsibility: 'BRD + scope statement + risk register + decision log.' },
    ],
    lld: `flowchart LR
  D1[Day 1] --> Notes1[Business notes]
  D2[Day 2] --> Notes2[Requirements + AI]
  D3[Day 3] --> Notes3[Architecture + Risk]
  D4[Day 4] --> Notes4[Approval]
  Notes1 --> BRD
  Notes2 --> BRD
  Notes3 --> C4
  Notes3 --> ADR
  Notes4 --> Sponsor[Sponsor signoff]`,
    problem: 'Without JAD, requirements drift + stakeholders disagree + AI decisions made implicitly. Discovery happens in code, where it\'s expensive.',
    whyThisApproach: 'JAD compresses alignment into 4 days. AI-extended adds the 5 dimensions traditional JAD misses (model, hallucination, sensitivity, governance, cost).',
    whenToUse: ['Any AI project ≥ 2-week scope', 'Cross-team feature with multiple stakeholders', 'Anything requiring sponsor approval'],
    whenNotToUse: ['Solo prototype', 'Continuation of existing well-defined feature'],
    input: 'Project mandate from leadership + initial stakeholder list',
    process: ['Day 1 business discovery', 'Day 2 requirements + AI', 'Day 3 architecture + risk', 'Day 4 validation', 'Outputs to repo'],
    output: 'BRD + scope statement + risk register + decision log + sponsor approval',
    alternatives: [
      { name: 'Skip JAD; engineering decides', tradeoff: 'Fast; misses business + risk + AI alignment' },
      { name: 'Continuous discovery (no formal session)', tradeoff: 'Agile-ish; loses sponsor alignment' },
      { name: 'AI-extended JAD (this)', tradeoff: 'Best alignment + 4-day cost + needs facilitator skill' },
    ],
    challenges: ['Endless meetings without facilitator control', 'Vague requirements without structure', 'Missing AI specialist or security'],
    edgeCases: [
      { case: 'Sponsor unavailable for full 4 days', solution: 'Sponsor attends Day 1 + Day 4 minimum; delegate for Days 2-3' },
      { case: 'Disagreement between AI specialist and security', solution: 'Capture in decision log + escalate to sponsor + record as ADR conflict' },
    ],
    failureModes: [
      { mode: 'Facilitator drift; meeting becomes status update', detect: 'No decisions captured', recover: 'Strict timeboxing + scribe enforces decision-log discipline' },
      { mode: 'AI decisions deferred ("we\'ll figure out later")', detect: 'No model decision in Day 2 output', recover: 'Block Day 3 until Day 2 outputs are explicit' },
    ],
    monitoring: ['Per-day output completeness', 'Sponsor signoff before merge', 'Time from JAD to first commit'],
    testing: ['Drill: simulated JAD on a known case', 'Output completeness audit', 'Cross-link from BRD to JAD notes'],
    security: ['Security on-attendees Day 3 (architecture + risk) is mandatory', 'Data sensitivity + HITL must be explicit'],
    scaling: ['Larger projects: 6-day JAD; smaller: 2-day', 'Cross-team JADs need a delegated scribe per team'],
    maturity: { mvp: 'Ad-hoc kickoff meeting', production: '4-day AI-extended JAD with explicit outputs', enterprise: 'JAD template per project type + recorded artifacts + cross-project learning' },
    limitations: ['4 days is significant time investment', 'Facilitator skill is the limiting factor', 'AI specialist availability often the bottleneck'],
    projectFit: ['docs/jad/<project>/Day1-business.md ... Day4-validation.md', 'docs/jad/<project>/output/BRD.md', '/admin/architect/deep — system view post-JAD', '/admin/adr/deep — decisions captured as ADRs'],
    interviewLine: 'JAD is where business, engineering, and AI decisions converge. AI-extended JAD adds 5 dimensions traditional JAD misses: model selection, hallucination risk, data sensitivity, governance, cost.',
    implementationSteps: [
      { step: 'Pre-JAD prep', logic: 'Stakeholder list + draft agenda + facilitator + scribe identified.' },
      { step: 'Day 1 — Business', logic: 'Problem + users + KPI + success metric.' },
      { step: 'Day 2 — Requirements + AI', logic: 'Functional + non-functional + RAG/ML choice + accuracy + HITL.' },
      { step: 'Day 3 — Architecture + Risk', logic: 'Latency + integrations + hallucination + PII + failure mitigations.' },
      { step: 'Day 4 — Validation + Consensus', logic: 'Sponsor signoff + action items + output to repo.' },
      { step: 'Output to repo', logic: 'BRD + scope + risk register + decision log committed.' },
    ],
    codeExample: { language: 'markdown', code: `# JAD Document — Enterprise RAG Assistant

## 1. Executive Summary
- Business goal: 40% faster support resolution
- AI usage: RAG chatbot + agent actions
- Expected outcome: 30% deflection of L1 tickets

## 2. Scope & Objectives
- In: doc Q&A + agent-based actions
- Out: external customer data; legal advice
- Success: KPI met within 6 months

## 3. Stakeholders
| Role | Name | Responsibility |
|---|---|---|
| Sponsor | Director Eng | Final approval |
| PO | Support PM | Requirements |
| Architect | Tech Lead | System design |
| AI Specialist | ML Eng | Model + RAG decisions |
| Security | InfoSec | Risk + DPA |

## 4. Business Requirements
### Functional
- Answer doc-grounded queries with citations
- Trigger pre-approved agent actions

### Non-Functional
| Area | Requirement |
|---|---|
| Performance | p95 latency < 2s |
| Scalability | 50 RPS sustained |
| Security | No PII in LLM prompts |
| Compliance | SOC2 audit-ready |

## 5. AI-Specific Requirements (CRITICAL)
| Area | Requirement |
|---|---|
| Use Case | RAG + Agent |
| Risk Level | Medium (with HITL high-risk path) |
| Human-in-loop | Required for actions |
| Data Sensitivity | Internal + PII redacted |
| Explainability | Citations required |
| Accuracy target | 90% on golden set |

## 6. System Models
- C4 Level 1 (System Context) — to follow
- C4 Level 2 (Containers) — to follow
- Data Flow Diagram — to follow

## 7. Design Prototypes
- UI mockups linked
- API contract OpenAPI spec
- Sample outputs labeled

## 8. Data Requirements
| Type | Source | Format |
|---|---|---|
| Text | SharePoint | PDF |
| Structured | Postgres | SQL |

## 9. Constraints
- Budget: $5K/mo LLM
- Timeline: 12 weeks MVP
- Tech: Python + FastAPI
- Compliance: SOC2 + EU AI Act

## 10. Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Hallucination | High | Guardrail + RAG citations |
| PII leak | High | Presidio masking |
| LLM provider outage | Med | Circuit breaker + fallback |
| Cost runaway | Med | Token CB + per-tenant cap |

## 11. Action Items
| Task | Owner | Due | Status |
|---|---|---|---|
| Draft C4 L1 | Architect | D7 | open |
| Set up vector DB | ML Eng | D14 | open |

## 12. Deliverables
- BRD ✓
- HLD (C4) → in progress
- LLD → in progress
- ADRs → 5 identified
- Test Plan → drafted

## 13. Approval
| Role | Name | Signature |
|---|---|---|
| Sponsor | Director Eng | ✓ approved |
| Architect | Tech Lead | ✓ approved |
| Product | Support PM | ✓ approved |
| Security | InfoSec | ✓ approved |` },
    realUseCase: 'Enterprise RAG assistant: 4-day JAD captured 47 requirements + 12 risks + 5 ADRs to write + sponsor signoff. Without JAD, the previous similar project had 6 weeks of "wait, what about PII?" / "we need HITL?" / "did anyone budget for embeddings?" — burned 30% of the timeline. With JAD, those decisions came pre-loaded.',
    prosCons: {
      pros: ['Cross-stakeholder alignment in 4 days', 'AI-specific decisions made explicit', 'Outputs feed BRD/C4/ADR cleanly', 'Sponsor signoff up-front'],
      cons: ['4 days of stakeholder time', 'Facilitator skill required', 'AI specialist + security availability'],
    },
    comparison: { left: 'Skip JAD; engineering decides', right: 'AI-extended JAD (this)', rows: [
      { aspect: 'Discovery cost', left: 'Weeks in code', right: '4 days up-front' },
      { aspect: 'AI decisions', left: 'Implicit', right: 'Explicit ADRs' },
      { aspect: 'Sponsor alignment', left: 'Late', right: 'Up-front signoff' },
      { aspect: 'Risk coverage', left: 'Reactive', right: 'Proactive register' },
    ] },
    solutions: [
      { problem: 'AI decisions made implicitly', solution: 'Day 2 explicit decision log' },
      { problem: 'Risks discovered in production', solution: 'Day 3 risk register' },
      { problem: 'Sponsor surprise at launch', solution: 'Day 4 sponsor signoff' },
    ],
    bestPractices: { do: ['Strict facilitator timeboxing', 'Scribe captures decisions + action items', '4-lens attendance (PO + Arch + AI + Sec)', 'AI-specific dimensions explicit Day 2', 'Outputs to repo Day 4'], avoid: ['Endless meetings', 'No scribe', 'Missing AI specialist or security', 'Verbal-only decisions'], optimize: ['Pre-JAD prep doc', 'JAD template per project type', 'Recorded sessions for absent stakeholders'] },
    antiPatterns: ['No AI specialist in JAD', 'Skipping security review on Day 3', 'No sponsor signoff', 'Outputs not committed to repo'],
    testTypes: ['Pre-JAD prep audit', 'Per-day output completeness', 'Action-item tracking post-JAD'],
    testScenarios: [
      { scenario: 'Stakeholder absent for Day 1', expected: 'Day 1 outputs reviewed + signed by them async; not unblocked' },
      { scenario: 'AI decision deferred to Day 3', expected: 'Day 3 blocked; reschedule Day 2' },
      { scenario: 'Sponsor disagrees with risk acceptance', expected: 'Risk register flagged; escalate or replan' },
    ],
    testData: [{ type: 'JAD reference set', example: 'Past project JAD outputs as templates' }],
    debuggingChecklist: ['Vague requirements? Day 2 functional + AI questions skipped', 'Risk surprise? Day 3 risk register incomplete', 'Sponsor pushback? Day 4 signoff bypassed'],
    productionIssues: [
      { issue: 'Project shipped without HITL on high-risk actions', rootCause: 'Day 2 AI decisions deferred; HITL never explicit. JAD discipline reinforced.' },
      { issue: 'Cost spike Q2 because no token budget set', rootCause: 'Day 2 cost question skipped. Added to JAD template.' },
    ],
    performance: ['Pre-JAD prep: ~1-2 days', 'JAD execution: 4 days', 'Output to repo: ~1 day'],
    costConsiderations: ['Stakeholder time cost: ~4 days × N people', 'Facilitator + scribe: dedicated ~1 week', 'ROI: prevents weeks of mid-project rework'],
    observability: ['JAD output completeness checklist', 'Action-item closure rate', 'Time JAD → first commit'],
    metrics: [
      { name: 'jad_session_completeness_rate', example: 'Gauge; target = 1.0 (all 13 sections present)' },
      { name: 'jad_action_item_closure_rate{quarter}', example: 'Gauge; target ≥ 0.9' },
      { name: 'jad_time_to_first_commit_days', example: 'Histogram; trend per quarter' },
    ],
    tradeoffs: [
      { decision: 'Days', tradeoff: '4 = thorough; 2 = lighter; > 4 = stakeholder fatigue' },
      { decision: 'Stakeholder breadth', tradeoff: 'More = better alignment + scheduling cost' },
      { decision: 'Output rigor', tradeoff: 'Strict template = comprehensive; flexible = adapts to project' },
    ],
    decisionMatrix: [
      { option: 'AI-extended JAD (this)', whenToUse: 'Any AI project ≥ 2-week scope' },
      { option: 'Skip JAD', whenToUse: 'Continuation of well-defined feature' },
      { option: 'Standard JAD (no AI extensions)', whenToUse: 'Non-AI legacy project' },
    ],
    starStory: {
      situation: 'Previous AI project had 6 weeks of mid-build "we forgot..." cycles + 30% timeline burn.',
      task: 'Front-load the discovery to prevent rework.',
      action: 'Ran 4-day AI-extended JAD: business + AI decisions + architecture + risk + validation. 13-section output committed to repo Day 4.',
      result: 'Next project shipped on time; zero "we forgot" cycles. Pattern adopted as enterprise-wide standard.',
    },
    interviewTraps: ['No AI specialist', 'No security on Day 3', 'No sponsor signoff', 'Outputs verbal-only'],
    finalScript: 'I run JAD sessions in four phases: Day 1 business discovery (problem + users + KPI), Day 2 requirements + AI decisions (RAG vs ML + accuracy + HITL), Day 3 architecture + risk (latency + hallucination + PII + failure mitigations), Day 4 validation + consensus (sponsor signoff + action items). For AI systems I extend JAD to include model selection, hallucination risk, data sensitivity, governance, and cost constraints — the 5 dimensions traditional JAD misses. JAD output feeds BRD, C4, ADR as the unified delivery chain. Without JAD, AI decisions get made implicitly and discovered in production.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — DAY-BY-DAY EXECUTION
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'jad-day-by-day-execution',
    title: '2. JAD day-by-day — what to ask, what to extract',
    status: 'shipped',
    coreConcept: 'The questions that drive each JAD day. AI-specific questions are the gold: "do we need RAG or ML?", "what is acceptable accuracy?", "can system hallucinate?", "do we need human approval?".',
    oneLiner: 'Day 1 business + KPI; Day 2 requirements + AI gold; Day 3 architecture + risk; Day 4 validation.',
    businessContext: 'The wrong questions miss critical AI-specific decisions. The right questions extract the 5 gold dimensions in Day 2 + risk register in Day 3.',
    fiveW: {
      what: 'Per-day question script + expected outputs.',
      why: 'Without explicit questions, sessions drift; AI decisions get deferred; risks go unidentified.',
      where: 'Used by facilitator (TL) running JAD.',
      when: 'During the 4-day session.',
      who: 'Facilitator drives; scribe captures.',
    },
    interview30s: 'Day-by-day question framework: Day 1 business — "what problem are we solving, what is current pain, what is success metric?". Day 2 AI gold questions — "RAG or ML or rule-based?", "acceptable accuracy?", "can it hallucinate?", "is HITL required?". Day 3 risk questions — "what if AI is wrong, what if system is down, what data is sensitive?". Day 4 validation — "are requirements complete, any missing stakeholders, are risks acceptable, what is MVP scope?". Most facilitators ask functional questions only; AI gold questions are what separates senior from junior facilitation.',
    hld: `flowchart TB
  D1[Day 1 Business] --> Q1[Problem Pain KPI]
  D2[Day 2 Requirements + AI] --> Q2[RAG vs ML Accuracy HITL]
  D3[Day 3 Architecture + Risk] --> Q3[Latency Hallucination PII Failure]
  D4[Day 4 Validation] --> Q4[Complete? Risks accepted? MVP scope?]`,
    networkFlow: `flowchart LR
  FA[Facilitator] -->|asks| ST[Stakeholders]
  ST -->|answer| SC[Scribe]
  SC --> NB[Notebook]
  NB --> O[Outputs]`,
    flowchart: `flowchart LR
  S[Day starts] --> Open[Open with goal]
  Open --> Ask[Ask scripted questions]
  Ask --> Capture[Scribe captures answers]
  Capture --> Decide[Facilitate decisions]
  Decide --> Output[Day output committed]`,
    sequence: `sequenceDiagram
  participant F as Facilitator
  participant PO as Product
  participant AI as AI specialist
  F->>PO: what problem are we solving
  PO-->>F: manual doc search
  F->>PO: what is success metric
  PO-->>F: 40% faster resolution
  F->>AI: RAG or ML or rule-based
  AI-->>F: RAG fits dynamic content
  F->>AI: acceptable accuracy
  AI-->>F: 90 percent on golden`,
    coreLayers: [
      { layer: 'Day 1 questions', responsibility: 'Business: problem + pain + KPI. Users: who + decisions + impact.' },
      { layer: 'Day 2 functional', responsibility: 'What should system do + inputs + outputs.' },
      { layer: 'Day 2 AI-gold', responsibility: 'RAG vs ML + accuracy + hallucination + HITL.' },
      { layer: 'Day 3 architecture', responsibility: 'Real-time vs batch + latency + integrations.' },
      { layer: 'Day 3 risk', responsibility: 'Wrong-answer + downtime + sensitive-data scenarios.' },
      { layer: 'Day 4 validation', responsibility: 'Completeness + missing-stakeholders + risk-acceptance + MVP scope.' },
    ],
    lld: `flowchart LR
  Q[Question script] --> Capture[Scribe Q+A]
  Capture --> Decide[Facilitate decision]
  Decide --> Log[Decision log entry]
  Log --> Action[Action item if needed]`,
    problem: 'Vague questions get vague answers. AI-specific decisions deferred to "we\'ll figure out later" never get figured out.',
    whyThisApproach: 'Scripted per-day questions force completeness. AI-gold questions surface implicit assumptions before code.',
    whenToUse: ['Every JAD session', 'New facilitators learning', 'Cross-team alignment'],
    whenNotToUse: ['Continuation of existing well-scoped feature'],
    input: 'JAD agenda + stakeholder list',
    process: ['Open day with goal', 'Ask scripted questions', 'Scribe captures', 'Facilitate decisions', 'Output committed end of day'],
    output: 'Per-day decision log + action items + per-day output committed',
    alternatives: [
      { name: 'Free-form Q&A', tradeoff: 'Flexible; misses critical questions' },
      { name: 'Scripted questions (this)', tradeoff: 'Comprehensive; needs facilitator skill to adapt' },
      { name: 'Survey-only', tradeoff: 'Async; loses cross-stakeholder alignment' },
    ],
    challenges: ['Facilitator must ADAPT script when conversation diverges productively', 'AI specialist may not be available for full Day 2', 'Junior stakeholders defer to seniors'],
    edgeCases: [
      { case: 'Stakeholder gives non-answer', solution: 'Re-ask with concrete options; capture if no answer ("ACCURACY: TBD")' },
      { case: 'Disagreement mid-question', solution: 'Capture disagreement; defer resolution to Day 4 or escalate' },
    ],
    failureModes: [
      { mode: 'Questions skipped because "we know already"', detect: 'Day output incomplete', recover: 'Strict checklist; complete before next day' },
    ],
    monitoring: ['Per-day question coverage', 'Decision log completeness', 'Action-item tracking'],
    testing: ['Drill: simulated JAD with each day script run end-to-end'],
    security: ['Day 3 risk questions cover security explicitly', 'PII + sensitive-data questions have InfoSec sign-off'],
    scaling: ['Question scripts versioned per project type', 'Per-domain extensions (finance, health, legal)'],
    maturity: { mvp: 'Improvised questions', production: 'Scripted per-day with AI gold', enterprise: 'Per-domain script libraries + facilitator certification' },
    limitations: ['Scripts can become rigid; adaptation is the skill', 'AI gold questions need AI specialist present'],
    projectFit: ['docs/jad/scripts/Day1.md ... Day4.md', 'docs/jad/<project>/Day*-output.md'],
    interviewLine: 'AI gold questions in Day 2 are what separates senior facilitation from junior: RAG vs ML, accuracy threshold, hallucination tolerance, HITL.',
    implementationSteps: [
      { step: 'Day 1 — Business Discovery', logic: 'Problem + pain + KPI + users + decisions + failure impact.' },
      { step: 'Day 2 — Requirements + AI Gold', logic: 'Functional + AI-specific (RAG/ML/rule, accuracy, hallucination, HITL).' },
      { step: 'Day 3 — Architecture + Risk', logic: 'Latency + integrations + risk register (wrong/downtime/sensitive).' },
      { step: 'Day 4 — Validation + Consensus', logic: 'Completeness + missing stakeholders + risk acceptance + MVP scope.' },
      { step: 'Per-day output committed', logic: 'End of each day, output committed to repo before next day starts.' },
    ],
    codeExample: { language: 'markdown', code: `# JAD Day-by-Day Script

## DAY 1 — Business Discovery
### Business
- What problem are we solving?
- What is current pain?
- What is success metric?

### Users
- Who will use system?
- What decisions will they take?
- What is failure impact?

### Output template
| Area | Answer |
|---|---|
| Problem | <answer> |
| Users | <answer> |
| KPI | <answer> |

## DAY 2 — Requirements + AI Decisions
### Functional
- What should system do?
- What inputs?
- What outputs?

### AI-Specific (GOLD)
- Do we need RAG or ML or rule-based?
- What is acceptable accuracy?
- Can system hallucinate? Tolerance?
- Do we need human approval?

### Output template
| Area | Decision |
|---|---|
| Use Case | <RAG | ML | Rule | Hybrid> |
| Accuracy | <% on golden> |
| HITL | <required for X | optional> |

## DAY 3 — Architecture + Risk
### Architecture
- Real-time or batch?
- Latency expectation?
- Integration systems?

### Risk (CRITICAL)
- What if AI is wrong?
- What if system is down?
- What data is sensitive?

### Output template
| Risk | Mitigation |
|---|---|
| Hallucination | <Guardrail | RAG citations | HITL> |
| PII leak | <masking | classification> |
| Failure | <fallback | circuit breaker> |

## DAY 4 — Validation + Consensus
### Final
- Are requirements complete?
- Any missing stakeholders?
- Are risks acceptable?
- What is MVP scope?

### Output template
- Approved scope
- Approved architecture
- Approved risks
- Action items` },
    realUseCase: 'Enterprise RAG project Day 2: AI specialist asked "can system hallucinate?" Product said "no, never". Architect pushed back: "no LLM is 100%; what tolerance is acceptable?". Decided: 90% accuracy + citations + HITL on critical queries. Without those questions, "no hallucination" would have been impossible to deliver and the project would have failed compliance review.',
    prosCons: {
      pros: ['Comprehensive coverage', 'AI-specific decisions explicit', 'Risk register populated', 'Sponsor alignment'],
      cons: ['Script rigidity if facilitator inflexible', 'Time-consuming', 'Needs AI specialist + security present'],
    },
    comparison: { left: 'Free-form Q&A', right: 'Scripted day-by-day (this)', rows: [
      { aspect: 'AI decisions captured', left: 'Sometimes', right: 'Always' },
      { aspect: 'Risk register coverage', left: 'Partial', right: 'Comprehensive' },
      { aspect: 'Facilitator skill required', left: 'High', right: 'Moderate (script supports)' },
    ] },
    solutions: [
      { problem: 'AI decisions deferred', solution: 'Day 2 AI gold questions force explicit answers' },
      { problem: 'Risks discovered late', solution: 'Day 3 risk questions populate register' },
      { problem: 'Sponsor surprise', solution: 'Day 4 validation walks all outputs' },
    ],
    bestPractices: { do: ['Scripted questions per day', 'Adapt script when conversation diverges productively', 'Capture non-answers as "TBD" with owner', 'AI-gold questions Day 2 mandatory'], avoid: ['Skipping AI questions because "obvious"', 'Deferring decisions to "later"', 'No scribe'], optimize: ['Per-domain script extensions', 'Pre-JAD prep brief'] },
    antiPatterns: ['Free-form without script', 'Skipping AI gold questions', 'No risk questions Day 3', 'No validation Day 4'],
    testTypes: ['Drill: simulated JAD with full script', 'Per-day output completeness audit'],
    testScenarios: [
      { scenario: 'Stakeholder says "we don\'t want hallucination"', expected: 'Facilitator probes: "what tolerance is acceptable?"' },
      { scenario: 'No HITL preference stated', expected: 'Facilitator probes per-action: "is this auto or human-approved?"' },
      { scenario: 'AI specialist absent Day 2', expected: 'Day 2 paused; reschedule with AI specialist' },
    ],
    testData: [{ type: 'Reference JAD scripts', example: 'docs/jad/scripts/ — versioned per project type' }],
    debuggingChecklist: ['Output incomplete? Per-day question coverage', 'Decision unclear? Re-ask with concrete options', 'Disagreement? Capture + escalate'],
    productionIssues: [
      { issue: 'Project shipped without HITL on high-risk actions', rootCause: 'Day 2 HITL question skipped; assumption drifted into code.' },
      { issue: 'Compliance failed because no PII classification', rootCause: 'Day 3 risk question on "what data is sensitive" never asked.' },
    ],
    performance: ['Per-day duration: 6-8 hours', 'Per-question time: 5-15 min depending on depth'],
    costConsiderations: ['Stakeholder time × 4 days', 'Pre-JAD prep + post-JAD output capture'],
    observability: ['Question coverage per day', 'Decision log completeness', 'Action-item closure'],
    metrics: [
      { name: 'jad_question_coverage_rate{day}', example: 'Gauge per day; target = 1.0' },
      { name: 'jad_decision_log_entries_per_day', example: 'Counter; trend per project' },
    ],
    tradeoffs: [
      { decision: 'Script rigidity', tradeoff: 'Strict = complete; adaptive = flowing conversation' },
      { decision: 'AI gold question depth', tradeoff: 'Deep = comprehensive; shallow = faster' },
    ],
    decisionMatrix: [
      { option: 'Scripted day-by-day (this)', whenToUse: 'Standard AI projects' },
      { option: 'Free-form', whenToUse: 'Highly experienced facilitator + stakeholders' },
    ],
    starStory: {
      situation: 'Day 2: product said "no hallucination ever"; architect pushed back.',
      task: 'Get AI tolerance defined before code.',
      action: 'AI specialist explained no LLM is 100%; AI gold questions probed acceptable %. Decided 90% + citations + HITL on critical.',
      result: 'Project shipped meeting the 90% target. Compliance approved. Without AI-gold questions, "no hallucination" would have been impossible to deliver.',
    },
    interviewTraps: ['Skipping AI gold questions', 'No risk questions Day 3', 'Deferring decisions'],
    finalScript: 'JAD day-by-day execution: Day 1 business discovery — problem + pain + KPI + users + decisions + failure impact. Day 2 requirements + AI gold — RAG vs ML or rule-based, acceptable accuracy, hallucination tolerance, HITL requirement. Day 3 architecture + risk — real-time vs batch, latency, integrations, risk register (wrong-answer + downtime + sensitive-data). Day 4 validation + consensus — completeness, missing stakeholders, risk acceptance, MVP scope, sponsor signoff. The AI gold questions in Day 2 are what separates senior facilitation from junior; without them, AI decisions get made implicitly and surface as problems in production.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 3 — UNIFIED DELIVERY CHAIN
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'jad-adr-c4-unified-chain',
    title: '3. JAD → BRD → C4 → ADR — the unified delivery chain',
    status: 'shipped',
    coreConcept: 'JAD outputs feed BRD (requirements), C4 (architecture), ADR (decisions). Each artifact has a distinct purpose; together they form the enterprise delivery chain from business intent to deployed code.',
    oneLiner: 'JAD = WHAT + WHY (business). BRD = WHAT (formal). C4 = HOW. ADR = WHY (technical). All four together = enterprise delivery.',
    businessContext: 'Each artifact answers a different question: JAD aligns stakeholders, BRD captures requirements formally, C4 designs the system, ADR records technical decisions. Skipping any link breaks the chain.',
    fiveW: {
      what: 'A linked artifact chain: JAD outputs → BRD/scope/risks → C4 levels → ADR catalog → LLD → code.',
      why: 'Each artifact has a distinct audience + purpose. Chain ensures business intent reaches production code.',
      where: 'Per-project documentation tree.',
      when: 'New project; phase transitions.',
      who: 'JAD: facilitator. BRD: BA. C4: architect. ADR: TL + 4-lens. LLD: engineers.',
    },
    interview30s: 'JAD output is the entry to the unified delivery chain: requirements feed the BRD, scope feeds C4 Level 1, decisions feed the ADR catalog, risks feed the governance layer, data feeds the data model. From there: BRD informs C4 Level 2 containers, ADRs cross-reference C4 levels, C4 Level 4 maps to code, code maps to tests + deploy + observability. The chain is what makes business intent traceable to deployed code; skipping any link breaks the trace and creates either implementation drift (no JAD) or unreviewable decisions (no ADR) or undocumented architecture (no C4).',
    hld: `flowchart TB
  Stake[Stakeholders] --> JAD[JAD session]
  JAD --> BRD[BRD requirements]
  JAD --> Scope[Scope statement]
  JAD --> Risk[Risk register]
  JAD --> Dec[Decision log]
  BRD --> C4L1[C4 Level 1 Context]
  BRD --> C4L2[C4 Level 2 Containers]
  Dec --> ADRs[ADR catalog]
  C4L2 --> C4L3[Level 3 Components]
  C4L3 --> C4L4[Level 4 Code]
  ADRs -.cross-link.-> C4L2
  ADRs -.cross-link.-> C4L3
  C4L4 --> Code
  Risk --> Gov[Governance L5]
  Code --> Test --> Deploy --> Mon[Observability L6]
  Mon --> Improve[Lifecycle L7]`,
    networkFlow: `flowchart LR
  Repo[docs/] --> JADs[jad/]
  Repo --> BRDs[brd/]
  Repo --> ADRs[adr/]
  Repo --> Diagrams[c4/]
  Repo --> Plans[plans/]`,
    flowchart: `flowchart LR
  S[New project] --> J[Run JAD]
  J --> B[Write BRD]
  B --> C[Draw C4]
  C --> A[Write ADRs]
  A --> L[Write LLD]
  L --> Code[Implement]`,
    sequence: `sequenceDiagram
  participant JAD
  participant BRD
  participant C4
  participant ADR
  participant Code
  JAD->>BRD: requirements
  JAD->>ADR: decision log
  BRD->>C4: scope to L1
  BRD->>C4: NFRs to L2
  ADR->>C4: cross-link to L2/L3
  C4->>Code: L4 maps to classes
  ADR->>Code: ADR refs in code comments`,
    coreLayers: [
      { layer: 'JAD', responsibility: 'Stakeholder alignment + requirements + risks + decisions.' },
      { layer: 'BRD', responsibility: 'Formal requirements doc with KPIs + success criteria.' },
      { layer: 'C4 (4 + 3 levels)', responsibility: 'System architecture from context to code.' },
      { layer: 'ADR', responsibility: 'Technical decisions with rationale + alternatives.' },
      { layer: 'LLD', responsibility: 'Per-component low-level design.' },
      { layer: 'Code', responsibility: 'Implementation; cross-references all of the above.' },
    ],
    lld: `flowchart LR
  JAD --> BRD --> HLD[C4 L1+L2]
  HLD --> ADRs
  HLD --> LLD[C4 L3+L4]
  LLD --> Code
  ADRs -.refs.-> Code
  Risk[Risk reg] --> Gov[Governance]
  Gov --> Code`,
    problem: 'Without the chain, business intent is lost between JAD and code. Or JAD is skipped and engineering decides implicitly.',
    whyThisApproach: 'Each artifact has a distinct purpose + audience. Linked, they trace business intent → deployed code; broken, they leave gaps.',
    whenToUse: ['Every AI project', 'Cross-team feature', 'Regulated environment'],
    whenNotToUse: ['Solo prototype'],
    input: 'JAD outputs',
    process: ['JAD → BRD', 'BRD → C4 Level 1+2', 'Decisions → ADR catalog', 'C4 Level 3+4 → LLD', 'LLD → code', 'Code references all artifacts'],
    output: 'Linked artifact chain in repo with cross-references',
    alternatives: [
      { name: 'JAD only (skip BRD/C4/ADR)', tradeoff: 'Aligned stakeholders; no implementation guidance' },
      { name: 'C4 only (skip JAD/BRD/ADR)', tradeoff: 'Architecture without business intent or rationale' },
      { name: 'Full chain (this)', tradeoff: 'Comprehensive + ops cost' },
    ],
    challenges: ['Keeping chain links fresh', 'Cross-references rot if artifacts edited carelessly', 'Multiple owners (BA, architect, TL, engineers)'],
    edgeCases: [
      { case: 'Mid-project requirement change', solution: 'Update JAD addendum + BRD + cascade to C4 + ADR' },
      { case: 'ADR contradicts BRD', solution: 'Resolve in JAD addendum; one wins; cross-link explicit' },
    ],
    failureModes: [
      { mode: 'BRD updated; C4 not', detect: 'Audit cross-references', recover: 'C4 refresh + reviewer flag' },
      { mode: 'ADR conflicts with C4', detect: 'Architect review', recover: 'Supersede ADR or update C4' },
    ],
    monitoring: ['Per-artifact freshness', 'Cross-reference integrity (CI lint)', 'Per-project chain completeness'],
    testing: ['Cross-reference CI lint', 'Quarterly chain audit'],
    security: ['Each artifact has a security reviewer', 'Risk register propagates from JAD to governance'],
    scaling: ['Chain scales with project count; per-project subdir', 'Templates per project type accelerate'],
    maturity: { mvp: 'Ad-hoc artifacts', production: 'Linked chain in repo + cross-references', enterprise: 'Static-site index + automated freshness alerts + cross-project traceability' },
    limitations: ['Chain takes discipline to maintain', 'Stale cross-references mislead'],
    projectFit: ['docs/jad/<proj>/ + docs/brd/<proj>.md + docs/c4/<proj>/ + docs/adr/<proj>/ + docs/plans/<proj>.md'],
    interviewLine: 'JAD = stakeholder alignment. BRD = formal requirements. C4 = architecture. ADR = decisions. All four together = enterprise delivery; any one missing breaks the trace.',
    implementationSteps: [
      { step: 'JAD outputs to repo', logic: 'BRD draft + scope + risk register + decision log Day 4.' },
      { step: 'BRD finalize', logic: 'BA polishes BRD from JAD draft; PO signs.' },
      { step: 'C4 Level 1+2 from BRD', logic: 'Architect draws System Context + Containers.' },
      { step: 'ADRs from decision log', logic: 'TL writes ADR per decision; 4-lens review.' },
      { step: 'C4 Level 3+4 + LLD', logic: 'Per-service component + code mapping.' },
      { step: 'Code references chain', logic: 'Code comments link to ADR + C4 levels.' },
    ],
    codeExample: { language: 'markdown', code: `# Project Documentation Chain

docs/
├── jad/
│   └── ai-rag-assistant/
│       ├── Day1-business.md
│       ├── Day2-requirements.md
│       ├── Day3-architecture.md
│       └── Day4-validation.md
├── brd/
│   └── ai-rag-assistant.md           # Formalized from JAD outputs
├── c4/
│   └── ai-rag-assistant/
│       ├── L1-system-context.md      # Mermaid context diagram
│       ├── L2-containers.md          # Container architecture
│       ├── L3-components.md          # RAG pipeline + agent
│       └── L4-code-mapping.md        # Class structure
├── adr/
│   ├── 0001-ai-assisted-development.md
│   ├── 0002-rag-vs-fine-tuning.md
│   ├── 0003-postgres-rls-tenant-isolation.md
│   └── ...
└── plans/
    └── ai-rag-assistant-mvp.md       # Phased delivery plan

## Cross-references (CI lint enforces)
- BRD references JAD Day1+Day2 outputs
- C4 L1 references BRD scope
- C4 L2 references BRD NFRs + ADR-003 (PG choice)
- ADRs cross-link to relevant C4 levels
- Code comments include "see ADR-003" tags
- Plan references all of the above

## Freshness rule
All artifacts dated. If BRD changes, downstream chain refreshed
within 1 week. CI lint warns on stale cross-references.` },
    realUseCase: 'Cross-team RAG feature: 4-day JAD → BRD finalized week 2 → C4 Level 1+2 week 3 → ADRs (5 of them) week 3-4 → C4 Level 3+4 + LLD week 4-5 → code week 5+. Each artifact cross-referenced; new engineers ramped in 1 week reading the chain. Compared to sister project without chain (2 quarters later, multiple "wait, why did we choose Postgres?" cycles), chain version was 30% faster + zero compliance findings.',
    prosCons: {
      pros: ['Business intent traces to code', 'Cross-stakeholder alignment maintained', 'Reviewable + auditable + reconstructible', 'Onboarding speed'],
      cons: ['Discipline to maintain freshness', 'Multiple artifact owners', 'Cross-reference rot risk'],
    },
    comparison: { left: 'No chain (just code + Slack)', right: 'Full chain (this)', rows: [
      { aspect: 'Onboarding speed', left: '6-8 weeks', right: '1-2 weeks' },
      { aspect: 'Decision reconstruction', left: 'Slack archeology', right: 'ADR + C4 cross-link' },
      { aspect: 'Compliance evidence', left: 'Limited', right: 'Linked artifact trail' },
      { aspect: 'Mid-project pivot cost', left: 'High', right: 'Lower (chain refresh)' },
    ] },
    solutions: [
      { problem: 'Implementation drifts from intent', solution: 'BRD ↔ code via C4 cross-link' },
      { problem: 'Decisions in Slack only', solution: 'ADR catalog from decision log' },
      { problem: 'Stale architecture doc', solution: 'CI lint catches stale cross-references' },
    ],
    bestPractices: { do: ['Per-project subdir', 'Cross-references explicit', 'Quarterly chain audit', 'CI lint integrity check'], avoid: ['Skipping links in chain', 'Editing artifacts without updating cross-refs', 'Verbal decisions'], optimize: ['Static-site index (mkdocs)', 'Tag taxonomy', 'Auto-generated cross-link diagrams'] },
    antiPatterns: ['No JAD', 'No BRD (skipping to C4)', 'No ADR', 'Chain links not cross-referenced'],
    testTypes: ['Cross-reference integrity (CI lint)', 'Per-project chain completeness audit', 'Quarterly chain refresh'],
    testScenarios: [
      { scenario: 'Mid-project requirement change', expected: 'JAD addendum → BRD update → C4 refresh → new ADR if needed' },
      { scenario: 'New ADR added', expected: 'Cross-linked to relevant C4 level' },
      { scenario: 'C4 refactor', expected: 'BRD + ADR cross-refs updated; lint passes' },
    ],
    testData: [{ type: 'Reference chain', example: 'Past project chains as templates' }],
    debuggingChecklist: ['Audit fail? Chain link missing', 'New engineer slow? Chain incomplete', 'Decision unclear? Walk JAD → BRD → ADR → C4'],
    productionIssues: [
      { issue: 'Compliance audit failed; no decision trail', rootCause: 'Chain incomplete; ADR catalog never written.' },
      { issue: 'New engineer ramp 8 weeks', rootCause: 'No BRD or C4; tribal knowledge only.' },
    ],
    performance: ['Per-artifact write: hours-days', 'Per-artifact review: hours', 'Chain refresh on change: 1-3 days'],
    costConsiderations: ['BA + architect + TL + EM time', 'CI lint compute: marginal', 'ROI: prevents weeks of mid-project rework + compliance findings'],
    observability: ['Per-artifact freshness', 'Cross-reference integrity', 'Chain completeness per project'],
    metrics: [
      { name: 'doc_chain_completeness_rate{project}', example: 'Gauge; target = 1.0' },
      { name: 'doc_cross_reference_lint_failures', example: 'Counter; alert > 0' },
      { name: 'doc_chain_freshness_days{artifact_type}', example: 'Histogram; alert > 90' },
    ],
    tradeoffs: [
      { decision: 'Chain rigor', tradeoff: 'Strict = comprehensive; flexible = adapts to project' },
      { decision: 'Cross-reference granularity', tradeoff: 'Fine = reviewable; coarse = less maintenance' },
      { decision: 'Refresh cadence', tradeoff: 'Quarterly = manageable; monthly = strict but costly' },
    ],
    decisionMatrix: [
      { option: 'Full chain (this)', whenToUse: 'AI project ≥ 2-week scope, multi-team, regulated' },
      { option: 'JAD + BRD + C4 (no ADR)', whenToUse: 'Hackathon iteration' },
      { option: 'Code only', whenToUse: 'Solo experimental' },
    ],
    starStory: {
      situation: 'Two parallel AI projects: one with full chain, one without.',
      task: 'Compare onboarding speed + compliance readiness + mid-project pivot cost.',
      action: 'Tracked artifact production + cross-reference integrity for both. Quarterly review.',
      result: 'Chain project: onboarding 1-2 weeks, zero compliance findings, 30% faster. No-chain project: onboarding 6-8 weeks, 2 compliance findings, mid-project pivot cost 6 weeks.',
    },
    interviewTraps: ['No JAD (skip to code)', 'No ADR (decisions in Slack)', 'No C4 (no architecture doc)', 'Cross-references not maintained'],
    finalScript: 'JAD aligns stakeholders. BRD captures formal requirements. C4 designs the system across 7 levels (with AI extensions). ADRs record technical decisions with rationale. LLD designs per-component. Code implements + cross-references all of the above. Each artifact has a distinct purpose + audience; linked, they trace business intent to deployed code. Skipping any link breaks the trace and creates implementation drift (no JAD), unreviewable decisions (no ADR), or undocumented architecture (no C4). The chain is enterprise delivery; without it, AI projects ship hopes and discover problems in production.',
  },
];

export default function JADDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">JAD — Joint Application Design (deep dive)</h1>
        <p className="design-areas-sub">
          JAD = WHAT + WHY (business consensus). C4 = HOW (architecture). ADR = WHY
          (technical decisions). AI-extended JAD adds 5 dimensions traditional JAD
          misses — model selection, hallucination risk, data sensitivity, governance,
          cost. The 4-day session structure, day-by-day question script, and the
          unified JAD → BRD → C4 → ADR delivery chain.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
