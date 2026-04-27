'use client';

/**
 * ADR — Architecture Decision Record (deep dive).
 *
 * "C4 tells what the system looks like. ADR tells why we chose
 * this design." This page covers the standard ADR template, the
 * status lifecycle, a worked AI-SDLC example, and the catalog of
 * 10 ADRs every AI engineering team should write.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — ADR FUNDAMENTALS
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'adr-fundamentals',
    title: '1. ADR fundamentals — what, why, when',
    status: 'shipped',
    coreConcept: 'An Architecture Decision Record captures WHY a design choice was made. Append-only, indexed, searchable. C4 explains structure; ADR explains reasoning.',
    oneLiner: 'ADR = the why behind the what. C4 + ADR together = a reconstructible architecture.',
    businessContext: 'Six months after a decision, the engineers who made it have moved on or forgotten. Without ADRs, "why is this Postgres + Qdrant instead of just Pinecone?" is unanswerable. New joiners reinvent or revisit decisions every quarter.',
    fiveW: {
      what: 'A markdown document per architectural decision: status, context, decision, alternatives, consequences, impact, review date.',
      why: 'Decisions decay into folklore without explicit recording. ADRs make decisions auditable + reversible + reviewable.',
      where: 'docs/adr/NNNN-title.md in the repo. Reviewed by architect + tech lead + security + EM.',
      when: 'EVERY irreversible decision. Decision = "we chose X over Y" with a measurable impact.',
      who: 'Drafted by the proposer; reviewed by the 4-lens board (TL+Arch+Sec+EM).',
    },
    interview30s: 'An Architecture Decision Record captures WHY we chose a design. Standard template: status (Proposed/Accepted/Rejected/Deprecated/Superseded), context (the problem + constraints), decision (what we chose + why), alternatives considered (table with rejection reasons), consequences (positive + negative), impact (security/cost/scalability/ops/team-skill), review date. ADRs are append-only — never edit; supersede instead. Reviewed by tech lead + architect + security + engineering manager. Without ADRs, decisions decay into folklore in 6 months and new joiners revisit them quarterly.',
    hld: `flowchart TB
  Proposed --> Accepted
  Proposed --> Rejected
  Accepted --> Deprecated
  Accepted --> Superseded
  Superseded -.->|points to| New[New ADR]`,
    networkFlow: `flowchart LR
  Dev[Engineer] --> PR[PR with ADR]
  PR --> Review[4-lens review]
  Review -->|approve| Merge[Merge + index]
  Review -->|reject| Revise`,
    flowchart: `flowchart LR
  Q[Decision needed] --> S1[Draft ADR]
  S1 --> S2[List alternatives]
  S2 --> S3[Capture consequences + impact]
  S3 --> S4[4-lens review]
  S4 --> O[Accepted + indexed]`,
    sequence: `sequenceDiagram
  participant E as Engineer
  participant TL as Tech Lead
  participant A as Architect
  participant S as Security
  participant EM as Eng Mgr
  E->>TL: PR with ADR draft
  TL->>A: review architecture
  TL->>S: review security impact
  TL->>EM: review process impact
  A-->>E: comments
  S-->>E: comments
  EM-->>E: comments
  E-->>TL: revised
  TL-->>E: approved + merged`,
    coreLayers: [
      { layer: 'Status', responsibility: 'Lifecycle: Proposed → Accepted → (Deprecated | Superseded).' },
      { layer: 'Context', responsibility: 'The problem + constraints + business pressure that forced the decision.' },
      { layer: 'Decision', responsibility: 'What we chose; why this option won.' },
      { layer: 'Alternatives', responsibility: 'Table of options + pros + cons + rejection reasons.' },
      { layer: 'Consequences', responsibility: 'Positive + negative; what changes.' },
      { layer: 'Impact', responsibility: 'Per-area: security, cost, scalability, ops, team skill.' },
      { layer: 'Review date', responsibility: 'When to revisit; defaults to quarterly.' },
    ],
    lld: `flowchart LR
  ADR[ADR doc] --> Idx[/docs/adr/index.md]
  ADR --> Tag[Tags by area]
  ADR --> Linked[Cross-link to C4 levels]`,
    problem: 'Decisions decay into folklore. New joiners revisit. Reviewers can\'t reconstruct WHY a choice was made.',
    whyThisApproach: 'Append-only markdown in the repo + 4-lens review + status lifecycle + impact table = decisions that survive team rotation.',
    whenToUse: ['Every irreversible decision', 'Cross-team architectural choice', 'Tool/vendor selection', 'Pattern adoption (CQRS, event sourcing, etc.)'],
    whenNotToUse: ['Reversible commit-level choices', 'Per-feature implementation detail (LLD)'],
    input: 'A decision needing rationale + alternatives',
    process: ['Draft', 'List alternatives', 'Consequences + impact', '4-lens review', 'Accept + index'],
    output: 'A merged ADR + index entry + cross-link from any docs that depend on the decision',
    alternatives: [
      { name: 'Slack threads + email', tradeoff: 'Easy; rotted within a quarter' },
      { name: 'Confluence / wiki ADRs', tradeoff: 'Searchable; not in repo so drift from code' },
      { name: 'Markdown ADRs in repo (this)', tradeoff: 'Co-located with code; PR-reviewable' },
    ],
    challenges: ['ADR fatigue if every PR tries one', 'Stale ADRs (no quarterly review)', 'Authoring discipline (alternatives often skipped)'],
    edgeCases: [
      { case: 'Decision changes mid-flight', solution: 'Supersede the old ADR with a new one; the old retains history' },
      { case: 'Two ADRs conflict', solution: 'Newer wins; older marked Deprecated; cross-link explicit' },
    ],
    failureModes: [
      { mode: 'ADR drift from code', detect: 'Code references ADR-005 but ADR-005 says different', recover: 'Audit + supersede + re-link' },
    ],
    monitoring: ['ADR count + status distribution', 'Stale ADRs (review date elapsed)', 'ADRs per quarter authored'],
    testing: ['ADR template lint', 'Cross-link integrity check (does the ADR exist?)', 'Quarterly ADR audit by EM'],
    security: ['Security reviewer signs every ADR', 'PII in ADR forbidden (ADRs may be public)'],
    scaling: ['Index by tag + decision domain', 'Sub-folders per service if monorepo', 'Search via grep or static-site generator'],
    maturity: { mvp: 'Slack archeology', production: 'Markdown ADRs in repo + 4-lens review + index', enterprise: 'ADR registry + tag taxonomy + automated freshness alerts + linked to risk register' },
    limitations: ['Markdown isn\'t semantic — search relies on tag discipline', 'Reviewers may rubber-stamp without engaging'],
    projectFit: ['docs/adr/0001-...md ... 0050-...md', 'docs/adr/index.md — TOC by status', 'CI lint check for required sections'],
    interviewLine: 'C4 diagrams explain the system structure. ADRs explain the reasoning. Both are required; neither replaces the other.',
    implementationSteps: [
      { step: 'Adopt template', logic: 'Status, context, decision, alternatives, consequences, impact, review date.' },
      { step: 'Number monotonically', logic: 'ADR-NNNN; never reuse a number.' },
      { step: '4-lens review board', logic: 'TL + Arch + Sec + EM signoff.' },
      { step: 'Status lifecycle', logic: 'Proposed → Accepted → (Deprecated | Superseded).' },
      { step: 'Cross-link from C4', logic: 'L2/L3 diagrams reference ADR by number.' },
      { step: 'Quarterly review', logic: 'EM walks through expired ADRs; mark stale or refresh.' },
    ],
    codeExample: { language: 'markdown', code: `# ADR-NNNN: <Decision Title>

## Status
Proposed | Accepted | Rejected | Deprecated | Superseded

## Date
2026-04-27

## Context
What problem are we solving?
What constraints exist?
What business or technical pressure caused this decision?

## Decision
What did we choose?
Why did we choose it?

## Alternatives Considered
| Option | Pros | Cons | Rejection Reason |
|---|---|---|---|
| Option A | ... | ... | ... |
| Option B | ... | ... | ... |

## Consequences
### Positive
- Benefit 1
- Benefit 2

### Negative
- Trade-off 1
- Risk 1

## Impact
| Area | Impact |
|---|---|
| Security | ... |
| Cost | ... |
| Scalability | ... |
| Operations | ... |
| Team skill | ... |

## Review Date
2026-07-27` },
    realUseCase: 'A team without ADRs spent a sprint debating "why are we using Postgres + Qdrant instead of just Pinecone?" — a decision that was made 8 months prior. After adopting ADR discipline: ADR-002 documents the choice (FORCE RLS for tenant isolation, hybrid retrieval needs graph + vector). Question now answerable in 30 seconds.',
    prosCons: {
      pros: ['Reconstructible decisions', '4-lens review distributes accountability', 'Append-only history', 'Co-located with code'],
      cons: ['Authoring overhead', 'Stale ADRs without discipline', 'Reviewer rubber-stamping risk'],
    },
    comparison: { left: 'No ADRs (Slack archeology)', right: 'Markdown ADRs in repo (this)', rows: [
      { aspect: 'Decision reconstruction', left: 'Days', right: 'Seconds (grep)' },
      { aspect: 'New joiner ramp', left: '4-8 weeks', right: '1-2 weeks' },
      { aspect: 'Decision conflicts', left: 'Rediscovered', right: 'Cross-linked + superseded' },
      { aspect: 'Compliance evidence', left: 'None', right: 'PR + ADR + reviewer' },
    ] },
    solutions: [
      { problem: 'Slack archeology', solution: 'ADRs in repo + grep' },
      { problem: 'Decision drift', solution: 'Quarterly audit + supersede' },
      { problem: 'Reviewer fatigue', solution: '4-lens rotation + ADR template lint' },
    ],
    bestPractices: { do: ['Standard template enforced', 'List alternatives + rejection reasons', '4-lens review', 'Cross-link to C4', 'Quarterly review'], avoid: ['Editing accepted ADRs (supersede instead)', 'Skipping alternatives section', 'Slack-only decisions'], optimize: ['Static-site index (mkdocs)', 'Tag taxonomy', 'CI lint for required sections'] },
    antiPatterns: ['No alternatives listed', 'Editing ADRs in place', 'No review date', 'No 4-lens review'],
    testTypes: ['ADR template lint (CI)', 'Cross-link integrity (grep)', 'Quarterly review walkthrough'],
    testScenarios: [
      { scenario: 'New ADR PR opened', expected: '4-lens reviewers tagged; CI runs template lint' },
      { scenario: 'Decision changes', expected: 'Old ADR marked Superseded; new ADR cross-links it' },
      { scenario: 'ADR expires (review date elapsed)', expected: 'EM walks through; refreshes or deprecates' },
    ],
    testData: [{ type: 'Reference ADR set', example: 'docs/adr/0001-0010 covering common AI-SDLC decisions' }],
    debuggingChecklist: ['Decision unclear? Grep ADR by tag', 'Stale design? Check ADR review date', 'Cross-link broken? CI lint catches it'],
    productionIssues: [
      { issue: 'Team rebuilt a feature already built', rootCause: 'No ADR; original decision lived in Slack. Adopted ADR discipline.' },
      { issue: 'Compliance audit failed because no decision rationale on file', rootCause: 'Decisions in heads only. ADRs added retroactively.' },
    ],
    performance: ['ADR write: ~30-60 min for the proposer', 'ADR review: ~1 hour for the 4-lens board', 'Quarterly audit: ~2 hours per service'],
    costConsiderations: ['Free — markdown + git', 'EM/TL time: ~5% of cycle for review + audit'],
    observability: ['ADR count + status', 'Stale-ADR alerts', 'Per-quarter authored count'],
    metrics: [
      { name: 'adr_total{status}', example: 'Counter; status distribution' },
      { name: 'adr_stale_count', example: 'Gauge; alert if > 0 (review date elapsed)' },
      { name: 'adr_authored_per_quarter', example: 'Counter; trend' },
    ],
    tradeoffs: [
      { decision: 'Granularity', tradeoff: 'Per-decision = thorough; per-feature = ADR fatigue' },
      { decision: 'Review board size', tradeoff: '4 lenses = comprehensive; 1 = fast' },
      { decision: 'Repo vs wiki', tradeoff: 'Repo = co-located; wiki = easier to search non-engineers' },
    ],
    decisionMatrix: [
      { option: 'Markdown ADRs in repo (this)', whenToUse: 'Most teams' },
      { option: 'Confluence', whenToUse: 'Non-engineers need to read' },
      { option: 'No ADRs', whenToUse: 'Solo project; pre-PMF prototype' },
    ],
    starStory: {
      situation: 'Team kept revisiting "why Postgres + Qdrant instead of just Pinecone?" every 6 months.',
      task: 'Make decisions reconstructible.',
      action: 'Adopted ADR template. Wrote ADR-002 documenting the rationale (FORCE RLS + hybrid retrieval). 4-lens review board.',
      result: 'Question answerable in 30 seconds via grep. New joiner ramp dropped from 8 weeks to 2.',
    },
    interviewTraps: ['ADRs without alternatives section', 'Editing in place instead of superseding', 'No review board', 'No quarterly audit'],
    finalScript: 'C4 explains structure; ADRs explain reasoning. Standard template: status, context, decision, alternatives considered with rejection reasons, consequences (positive + negative), impact (security/cost/scalability/ops/team-skill), review date. Append-only — never edit; supersede instead. Reviewed by 4-lens board: tech lead + architect + security + engineering manager. Cross-linked from C4 levels. Quarterly review by EM. Without ADRs decisions decay into folklore in 6 months and new joiners revisit them quarterly; with ADRs decisions are reconstructible in seconds.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — WORKED EXAMPLE
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'adr-001-ai-assisted-dev',
    title: '2. ADR-001 worked example — AI-Assisted Development with Human Review Gates',
    status: 'shipped',
    coreConcept: 'A complete worked ADR. Engineering team wants AI coding tools but must mitigate hallucinated APIs, security holes, weak design, licensing risk. Decision: AI-assisted with plan-first + small PRs + human review + tests + security scan + traceability labels.',
    oneLiner: 'ADR-001 — AI-assisted development with human review gates: balanced speed + control.',
    businessContext: 'Engineering wants velocity from Copilot/Cursor/etc. Security + compliance worry about leaked secrets, hallucinated APIs, license violations, and review responsibility. ADR-001 captures the balanced policy.',
    fiveW: {
      what: 'ADR-001 documents the policy: AI-assisted, NOT autonomous. Required gates: plan-first workflow, small PRs, human review, test execution, security scan (SAST/SCA/secrets), AI-traceability labels.',
      why: 'Without this ADR, engineering and security would re-litigate the policy quarterly.',
      where: 'docs/adr/0001-ai-assisted-development.md',
      when: 'Day 1 of any engineering team adopting AI tools.',
      who: 'CTO + EM + security lead.',
    },
    interview30s: 'ADR-001 in our repo documents AI-assisted development policy. Status: Accepted. Context: team wants AI coding tool velocity but AI generates code with hallucinated APIs, security holes, licensing risk. Decision: AI-assisted, NOT autonomous; six required gates: plan-first workflow, small PRs (≤300 lines), human review, test execution, security scan (SAST/SCA/secrets), AI-traceability labels on PRs that contain AI-generated code. Alternatives rejected: no AI (too restrictive, lose velocity); fully autonomous AI (not enterprise-safe, accountability gap). Impact: Security gate adds SAST/SCA/secrets scan; cost adds AI tool + token budget; quality requires test coverage increase; compliance requires AI-traceability label on every AI-touched PR.',
    hld: `flowchart TB
  Dev[Developer + AI tool] --> Plan[Plan first]
  Plan --> SmallPR[Small PR ≤300 lines]
  SmallPR --> Tests[Tests execute]
  Tests --> Sec[SAST + SCA + secrets scan]
  Sec --> Review[Human review]
  Review --> Label[AI-traceability label]
  Label --> Merge`,
    networkFlow: `flowchart LR
  AItool[AI tool Copilot or Cursor] -->|suggestions| Dev[Developer]
  Dev -->|PR| GitHub
  GitHub -->|CI| Pipeline[Plan + tests + sec + review]`,
    flowchart: `flowchart LR
  Q[Want AI velocity] --> Concern[Security cost compliance]
  Concern --> Decide[ADR-001]
  Decide --> Gate1[Plan-first]
  Decide --> Gate2[Small PR]
  Decide --> Gate3[Human review]
  Decide --> Gate4[Tests]
  Decide --> Gate5[Security scan]
  Decide --> Gate6[AI label]`,
    sequence: `sequenceDiagram
  participant D as Dev
  participant AI as AI tool
  participant CI as CI
  participant R as Reviewer
  D->>AI: prompt for code
  AI-->>D: suggestion
  D->>D: review + adapt
  D->>CI: PR with AI-label
  CI->>CI: tests + SAST + SCA + secrets
  CI-->>R: ready for human review
  R-->>D: approve or comments
  D->>CI: merge`,
    coreLayers: [
      { layer: 'Plan-first', responsibility: 'Plan written before code; AI suggests within plan scope.' },
      { layer: 'Small PRs', responsibility: 'Cap ≤ 300 lines; reviewer can actually read.' },
      { layer: 'Human review', responsibility: 'Engineer reviews every AI line; named accountable.' },
      { layer: 'Tests', responsibility: 'CI runs unit + integration; AI must produce passing.' },
      { layer: 'Security scan', responsibility: 'SAST + SCA + secrets scan blocks merge on findings.' },
      { layer: 'AI traceability', responsibility: 'PR label "ai-assisted" + commit footer noting tool used.' },
    ],
    lld: `flowchart LR
  PR[AI-touched PR] --> Lint[Template lint]
  Lint --> Test[Test gate]
  Test --> SAST[SAST scan]
  SAST --> SCA[SCA scan]
  SCA --> Secrets[Secrets scan]
  Secrets --> Review[Human review]
  Review --> Merge`,
    problem: 'AI tools accelerate development but introduce hallucinated APIs, security holes, license violations, and accountability gaps.',
    whyThisApproach: 'Six gates compose: plan-first prevents spec drift; small PRs make review feasible; tests catch hallucinated APIs; security scan catches injected risks; human review owns accountability; AI label enables traceability + compliance.',
    whenToUse: ['Any engineering team adopting AI tools', 'Regulated environments', 'Customer-facing code'],
    whenNotToUse: ['Solo experimental projects', 'Fully isolated research environment'],
    input: 'AI-tool adoption proposal',
    process: ['Plan-first', 'Small PR', 'Tests pass', 'Security scan pass', 'Human review approve', 'AI label applied', 'Merge'],
    output: 'Merged code + traceability label + audit chain',
    alternatives: [
      { name: 'No AI', tradeoff: 'Lowest risk; lost velocity; rejected as too restrictive' },
      { name: 'Fully autonomous AI', tradeoff: 'Highest velocity; no accountability; rejected as not enterprise-safe' },
      { name: 'AI with governance (this)', tradeoff: 'Balanced speed + control; needs process discipline; selected' },
    ],
    challenges: ['Plan-first discipline (devs skip)', 'AI label compliance', 'Tests for AI-generated code (coverage drift)'],
    edgeCases: [
      { case: 'AI generates a hallucinated API call', solution: 'Test gate catches at CI; reviewer rejects' },
      { case: 'AI suggests code with embedded secret', solution: 'Secrets-scan gate blocks merge' },
      { case: 'AI generates GPL-licensed code', solution: 'SCA scan flags; reviewer reverts' },
    ],
    failureModes: [
      { mode: 'AI label missing on AI-touched PR', detect: 'Audit grep on commits', recover: 'Retroactive labeling + reviewer education' },
      { mode: 'Plan skipped', detect: 'PR description has no plan reference', recover: 'PR rejected; require revision' },
    ],
    monitoring: ['AI-labeled PR count', 'Security-scan finding rate', 'Reviewer turnaround time', 'Test coverage trend'],
    testing: ['Drill: hallucinated API → test gate catches', 'Drill: secret in AI suggestion → secrets gate catches', 'Drill: GPL code → SCA gate catches'],
    security: ['SAST + SCA + secrets on every AI-touched PR', 'No PII in AI prompts (telemetry data redacted)', 'Approved-models list per ADR-008'],
    scaling: ['AI label automated via PR template', 'Security gates run in parallel', 'Per-team AI tool budget'],
    maturity: { mvp: 'AI tools allowed without governance', production: '6 gates enforced; ADR-001 in repo', enterprise: 'AI usage telemetry + per-team budget + compliance reports' },
    limitations: ['Doesn\'t prevent AI bias in design choices (humans still own)', 'Adds CI time per PR'],
    projectFit: ['docs/adr/0001-ai-assisted-development.md', 'AGENTS.md — repo-level AI instructions', '.github/workflows/ai-pr.yml — gates', '/admin/architect/deep — system view'],
    interviewLine: 'AI-assisted development is balanced speed + control. Six gates: plan-first, small PRs, human review, tests, security scan, AI traceability. Without ADR-001 the policy gets re-litigated quarterly.',
    implementationSteps: [
      { step: 'Adopt template', logic: 'Standard ADR template applied to ADR-001.' },
      { step: 'Six gates in CI', logic: 'Each gate is a CI job; PR cannot merge without all green.' },
      { step: 'AGENTS.md', logic: 'Repo-level AI tool instructions; ADR-002 codifies.' },
      { step: 'AI label automation', logic: 'PR template includes "AI-assisted: y/n"; CI lint enforces.' },
      { step: 'Quarterly review', logic: 'EM reviews AI-PR rate + finding rate; refreshes policy.' },
    ],
    codeExample: { language: 'markdown', code: `# ADR-001: Use AI-Assisted Development with Human Review Gates

## Status
Accepted

## Date
2026-04-27

## Context
The engineering team wants to improve delivery speed using AI coding
tools (Copilot, Cursor, etc.). However, AI-generated code may
introduce security issues, weak design choices, hallucinated APIs,
licensing risks, and hidden defects.

## Decision
AI-assisted development is allowed, but every AI-generated change
must follow:
  1. Plan-first workflow
  2. Small pull requests (≤300 lines)
  3. Human review
  4. Test execution
  5. Security scanning (SAST + SCA + secrets)
  6. AI-traceability label

## Alternatives Considered
| Option | Pros | Cons | Rejection Reason |
|---|---|---|---|
| No AI usage | Lowest AI risk | Slower delivery | Too restrictive |
| Fully autonomous AI coding | Fast delivery | High risk | Not enterprise-safe |
| AI with human governance | Balanced speed + control | Needs process discipline | Selected |

## Consequences
### Positive
- Faster development
- Better boilerplate generation
- Improved consistency
- Improved developer productivity

### Negative
- More review responsibility
- Need AI governance
- Possible over-reliance on tools
- Additional audit overhead

## Impact
| Area | Impact |
|---|---|
| Security | Requires SAST, SCA, secrets scanning |
| Cost | AI tool + token cost added |
| Quality | Test coverage must increase |
| Compliance | AI usage must be traceable |
| Operations | AI-related incidents need RCA |

## Review Date
2026-07-27` },
    realUseCase: 'Team adopted Cursor; first 4 weeks shipped 30% more PRs but 3 incidents (hallucinated API in prod, leaked test secret, GPL code). Wrote ADR-001 with 6 gates. Next quarter: same velocity, zero AI-attributable incidents.',
    prosCons: {
      pros: ['Captured balanced policy in writing', '6 gates compose to cover the main risks', 'Reviewable + auditable', 'Compliance-ready'],
      cons: ['Added CI time per PR', 'Plan-first discipline required', 'Quarterly refresh ops cost'],
    },
    comparison: { left: 'No policy / informal AI use', right: 'ADR-001 with 6 gates (this)', rows: [
      { aspect: 'Velocity gain', left: '30%', right: '30%' },
      { aspect: 'AI-attributable incidents', left: '3 per quarter', right: '0 per quarter' },
      { aspect: 'Compliance traceability', left: 'None', right: 'AI label + audit' },
      { aspect: 'Reviewer accountability', left: 'Diffuse', right: 'Named per PR' },
    ] },
    solutions: [
      { problem: 'Hallucinated API in prod', solution: 'Test gate catches' },
      { problem: 'Secret leaked in code', solution: 'Secrets-scan gate' },
      { problem: 'GPL code merged', solution: 'SCA scan + review' },
    ],
    bestPractices: { do: ['ADR in repo + cross-linked', '6 gates enforced in CI', 'AI label on every AI-touched PR', 'Quarterly review'], avoid: ['Implicit policy (verbal only)', 'Skipping any of the 6 gates', 'No AI label'], optimize: ['AI label automation', 'Security gates parallel', 'Per-team AI tool budget'] },
    antiPatterns: ['No ADR for AI policy', 'Fully autonomous AI', 'Skipping security scans on AI PRs'],
    testTypes: ['CI gate drill', 'Secrets-scan drill', 'SCA license drill', 'AI label compliance audit'],
    testScenarios: [
      { scenario: 'PR has AI-generated code', expected: 'AI label applied; all 6 gates run' },
      { scenario: 'AI suggested a secret', expected: 'Secrets gate blocks merge' },
      { scenario: 'AI suggested GPL code', expected: 'SCA gate flags' },
    ],
    testData: [{ type: 'AI-PR fixture set', example: 'Sample PRs with various AI-generated content for gate testing' }],
    debuggingChecklist: ['AI incident in prod? Check PR for label + gates', 'Audit gap? Grep for unlabeled AI commits'],
    productionIssues: [
      { issue: 'Hallucinated API call merged', rootCause: 'No test gate; AI suggestion not validated.' },
      { issue: 'Test API secret leaked', rootCause: 'No secrets scan on AI PR.' },
    ],
    performance: ['CI overhead: ~3-5 min per AI PR (scans run parallel)', 'Reviewer time: ~30 min per AI PR'],
    costConsiderations: ['AI tool cost: ~$30-50/dev/mo', 'CI compute: marginal', 'Reviewer hours: ROI from velocity gain'],
    observability: ['AI-labeled PR count', 'Security-scan finding rate per AI vs non-AI', 'Reviewer turnaround time'],
    metrics: [
      { name: 'ai_pr_total{labeled}', example: 'Counter; labeled-vs-unlabeled split' },
      { name: 'ai_pr_security_findings_total{tool,scan_type}', example: 'Counter; per-tool, per-scan-type' },
      { name: 'ai_pr_review_duration_seconds{p}', example: 'Histogram; trend per quarter' },
    ],
    tradeoffs: [
      { decision: 'Gate count', tradeoff: 'More gates = safer; longer CI' },
      { decision: 'PR size cap', tradeoff: 'Smaller = reviewable; more PRs to manage' },
    ],
    decisionMatrix: [
      { option: '6 gates (this)', whenToUse: 'Production engineering with AI tools' },
      { option: 'No AI', whenToUse: 'Highly regulated; willing to lose velocity' },
      { option: 'Autonomous AI', whenToUse: 'Never — accountability gap' },
    ],
    starStory: {
      situation: 'Team adopted AI coding tools; first quarter had 3 AI-attributable incidents.',
      task: 'Capture policy + close incident path without losing velocity.',
      action: 'Wrote ADR-001 with 6 gates: plan-first, small PRs, human review, tests, security scan, AI label. Enforced in CI.',
      result: 'Same velocity gain (30%); zero AI-attributable incidents next quarter. Pattern adopted across 4 sister teams.',
    },
    interviewTraps: ['No ADR for AI policy', 'Skipping security scans', 'No AI traceability label', 'Fully autonomous AI'],
    finalScript: 'ADR-001 in our repo documents AI-assisted development. Six required gates: plan-first workflow, small PRs ≤300 lines, human review, test execution, security scan (SAST+SCA+secrets), AI-traceability label. Alternatives rejected: no AI (too restrictive); fully autonomous AI (no accountability). Result: same velocity gain (~30%), zero AI-attributable incidents per quarter. Without this ADR the policy gets re-litigated every quarter and incidents reoccur.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 3 — ADR CATALOG FOR AI-SDLC
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'adr-catalog-ai-sdlc',
    title: '3. ADR catalog for AI-SDLC — the 10 ADRs every team needs',
    status: 'shipped',
    coreConcept: 'A reference set of 10 ADRs that cover the full AI-SDLC: development policy, repo conventions, test discipline, governance, observability, resilience.',
    oneLiner: 'These 10 ADRs cover: AI dev policy, AGENTS.md, TDD, test protection, DDD, eval, guardrails, prompt versioning, observability, circuit breakers.',
    businessContext: 'Without a standard catalog, teams reinvent ADR topics. The 10-ADR baseline is the "minimum viable governance" set for production AI engineering.',
    fiveW: {
      what: 'Reference catalog: ADR-001 through ADR-010 covering the full AI-SDLC.',
      why: 'Every AI team makes these decisions; standardizing the catalog accelerates new-team setup.',
      where: 'docs/adr/0001-...md through 0010-...md',
      when: 'Day 1 of any new AI team.',
      who: 'AI lead + EM + security review.',
    },
    interview30s: 'Ten ADRs every AI engineering team should write: ADR-001 AI-assisted development with human review; ADR-002 AGENTS.md as repo-level AI instruction file; ADR-003 enforce TDD for AI-generated code; ADR-004 protect tests from AI modification; ADR-005 use DDD folder structure; ADR-006 add AI evaluation pipeline; ADR-007 add guardrail service; ADR-008 add prompt versioning; ADR-009 add AI observability; ADR-010 use circuit breaker for LLM and tool calls. Together they cover development policy, repo conventions, test discipline, governance, observability, and resilience — the minimum viable governance for production AI engineering.',
    hld: `flowchart TB
  ADR1[ADR-001 AI-assisted dev]
  ADR2[ADR-002 AGENTS.md]
  ADR3[ADR-003 TDD enforced]
  ADR4[ADR-004 Test protection]
  ADR5[ADR-005 DDD folders]
  ADR6[ADR-006 Eval pipeline]
  ADR7[ADR-007 Guardrail svc]
  ADR8[ADR-008 Prompt versioning]
  ADR9[ADR-009 Observability]
  ADR10[ADR-010 Circuit breaker]
  ADR1 --> ADR2 --> ADR3 --> ADR4
  ADR5 --> ADR6 --> ADR7 --> ADR8
  ADR8 --> ADR9 --> ADR10`,
    networkFlow: `flowchart LR
  Repo[Repo] --> ADRs[docs/adr/]
  ADRs --> Idx[Index]
  ADRs --> CI[CI gates reference ADRs]`,
    flowchart: `flowchart LR
  Q[New AI team] --> S1[Adopt 10 ADRs]
  S1 --> S2[Customize per project]
  S2 --> S3[CI gates enforce]
  S3 --> O[Production-ready governance]`,
    sequence: `sequenceDiagram
  participant T as New team
  participant Cat as ADR catalog
  T->>Cat: copy 10 ADRs
  T->>T: customize context
  T->>T: 4-lens review
  T->>T: enforce in CI`,
    coreLayers: [
      { layer: 'Development policy', responsibility: 'ADR-001 + ADR-002 + ADR-003 + ADR-004.' },
      { layer: 'Code structure', responsibility: 'ADR-005 (DDD folders).' },
      { layer: 'AI quality', responsibility: 'ADR-006 (eval) + ADR-007 (guardrail) + ADR-008 (prompt versioning).' },
      { layer: 'Operations', responsibility: 'ADR-009 (observability) + ADR-010 (circuit breaker).' },
    ],
    lld: `flowchart LR
  ADR1 -.refs.-> /admin/architect/deep
  ADR6 -.refs.-> /admin/llmops
  ADR7 -.refs.-> /admin/guardrails/deep
  ADR9 -.refs.-> /admin/llmops
  ADR10 -.refs.-> /admin/breakers/deep`,
    problem: 'Teams reinvent ADR topics. Some skip observability, some skip guardrails. Production gaps emerge.',
    whyThisApproach: 'A standard 10-ADR catalog covers the full AI-SDLC. Customizing the context per team is faster than writing each from scratch.',
    whenToUse: ['Any new AI engineering team', 'Existing team without ADR discipline', 'Compliance audit prep'],
    whenNotToUse: ['Hackathon prototype'],
    input: 'New AI team setup',
    process: ['Copy 10 ADR templates', 'Customize context per project', '4-lens review', 'Enforce in CI'],
    output: '10 accepted ADRs + CI gates + onboarding doc',
    alternatives: [
      { name: 'No ADRs', tradeoff: 'Fast; production gaps' },
      { name: 'Per-project bespoke ADRs', tradeoff: 'Custom; reinvent every team' },
      { name: 'Standard 10-ADR catalog (this)', tradeoff: 'Fast adoption + production-ready' },
    ],
    challenges: ['Customization without losing the standard', 'Keeping 10 fresh', 'CI gate maintenance'],
    edgeCases: [
      { case: 'Team needs an 11th ADR', solution: 'Add as ADR-011 in their repo; consider promoting to catalog' },
      { case: 'ADR-X conflicts with team culture', solution: 'Customize context; if hard rejection, document in their repo' },
    ],
    failureModes: [
      { mode: 'Teams skip ADRs they don\'t understand', detect: 'New-team audit', recover: 'Onboarding session walks each ADR' },
    ],
    monitoring: ['ADR adoption rate per team', 'CI gate enforcement rate'],
    testing: ['Cross-team adoption audit', 'Per-ADR drill (where applicable)'],
    security: ['ADR-007 (guardrail) + ADR-009 (observability) provide compliance evidence'],
    scaling: ['Catalog scales by adding ADRs (carefully)', 'Per-team customization on common base'],
    maturity: { mvp: '0-3 ADRs', production: '10 ADRs adopted + CI', enterprise: 'Catalog versioned; cross-team adoption tracked' },
    limitations: ['10 is opinionated — may need 8 or 12 for some teams', 'Customization required'],
    projectFit: ['~/.claude/policies/ai-sdlc-adr-catalog.md (proposed)', 'Per-team docs/adr/'],
    interviewLine: 'Ten ADRs cover the full AI-SDLC: dev policy, repo conventions, TDD, test protection, DDD, eval, guardrails, prompt versioning, observability, circuit breakers.',
    implementationSteps: [
      { step: 'Adopt template per ADR', logic: 'Copy 10 ADR docs from catalog.' },
      { step: 'Customize context', logic: 'Per-team specifics (tech stack, scale).' },
      { step: '4-lens review', logic: 'TL+Arch+Sec+EM signoff per ADR.' },
      { step: 'CI enforcement', logic: 'Each ADR has a CI gate (template lint, test gate, etc.).' },
      { step: 'Onboarding', logic: 'New engineers walked through 10 ADRs Day 1.' },
    ],
    codeExample: { language: 'markdown', code: `# ADR catalog for AI-SDLC

| ADR | Decision | CI Gate |
|---|---|---|
| ADR-001 | AI-assisted dev with human review | 6-gate pipeline |
| ADR-002 | AGENTS.md as repo-level AI instruction | Lint check |
| ADR-003 | Enforce TDD for AI-generated code | Coverage gate |
| ADR-004 | Protect tests from AI modification | Path-based reviewer requirement |
| ADR-005 | Use DDD folder structure | Lint structure |
| ADR-006 | Add AI evaluation pipeline | Eval gate at PR |
| ADR-007 | Add guardrail service | Required deploy |
| ADR-008 | Add prompt versioning | Registry CI |
| ADR-009 | Add AI observability | OTel SDK required |
| ADR-010 | Use circuit breaker for LLM/tool calls | Drill in CI |

## Adoption checklist
- [ ] All 10 ADRs in docs/adr/
- [ ] 4-lens review on each
- [ ] CI gates wired
- [ ] Onboarding doc references catalog
- [ ] Quarterly review by EM` },
    realUseCase: 'New AI team copied catalog Day 1; first quarter shipped 3 features without any of the typical "we forgot to add a guardrail / eval / circuit breaker" rework. Productivity gain ~25% vs sister team that wrote ADRs from scratch.',
    prosCons: {
      pros: ['Fast adoption', 'Covers full AI-SDLC', 'Cross-team learning', 'CI gates baked in'],
      cons: ['Opinionated (may not fit all teams)', 'Customization still required', 'Catalog refresh cost'],
    },
    comparison: { left: 'Per-project bespoke ADRs', right: '10-ADR catalog (this)', rows: [
      { aspect: 'Time to first ADR', left: 'Days', right: 'Hours' },
      { aspect: 'Coverage gaps', left: 'Common', right: 'Rare' },
      { aspect: 'Cross-team learning', left: 'Tribal', right: 'Catalog-mediated' },
    ] },
    solutions: [
      { problem: 'Team skipped guardrail discipline', solution: 'Catalog includes ADR-007' },
      { problem: 'Team skipped eval', solution: 'Catalog includes ADR-006' },
      { problem: 'Team forgot circuit breaker on LLM', solution: 'Catalog includes ADR-010' },
    ],
    bestPractices: { do: ['Copy + customize', '4-lens review per ADR', 'CI gates', 'Quarterly catalog refresh'], avoid: ['Skipping ADRs because "we don\'t need it"', 'Bespoke without catalog reference'], optimize: ['Catalog refresh quarterly', 'Cross-team adoption tracking'] },
    antiPatterns: ['No ADRs', 'Catalog ignored', 'Skipping ADR-006/007/009/010 (the AI-specific ones)'],
    testTypes: ['Per-ADR drill', 'Adoption audit', 'CI gate enforcement'],
    testScenarios: [
      { scenario: 'New team Day 1', expected: 'Catalog copied; 4-lens review scheduled' },
      { scenario: 'CI gate misses an ADR', expected: 'Audit catches; gate added retroactively' },
      { scenario: 'Catalog updates', expected: 'Teams notified; refresh cycle' },
    ],
    testData: [{ type: 'Reference 10 ADRs', example: 'Sample customized ADRs from past projects' }],
    debuggingChecklist: ['Production gap? Map to which ADR is missing', 'Compliance audit fail? Catalog adoption gap'],
    productionIssues: [
      { issue: 'AI feature shipped without guardrails', rootCause: 'ADR-007 not adopted; catalog reference missed.' },
      { issue: 'LLM provider outage cascaded', rootCause: 'ADR-010 not adopted; no circuit breaker.' },
    ],
    performance: ['Catalog adoption: ~1-2 days for new team', 'Per-ADR review: ~1 hour'],
    costConsiderations: ['Free — markdown + CI', 'Catalog refresh: ~quarterly EM time'],
    observability: ['Per-team ADR adoption rate', 'Per-ADR CI gate enforcement', 'Catalog freshness'],
    metrics: [
      { name: 'adr_catalog_adoption_rate{team}', example: 'Gauge; target = 1.0' },
      { name: 'adr_ci_gate_enforcement_rate{adr}', example: 'Gauge per ADR; target = 1.0' },
    ],
    tradeoffs: [
      { decision: 'Catalog size', tradeoff: '10 = manageable; 20 = comprehensive but heavier' },
      { decision: 'Customization vs standardization', tradeoff: 'Custom = better fit; standard = cross-team learning' },
    ],
    decisionMatrix: [
      { option: '10-ADR catalog (this)', whenToUse: 'New AI team; existing team without discipline' },
      { option: 'Bespoke ADRs', whenToUse: 'Highly specialized domain' },
    ],
    starStory: {
      situation: 'Sister team without catalog spent 2 quarters building production AI without guardrails or circuit breakers — 4 outages.',
      task: 'Standardize the missing pieces.',
      action: 'Adopted 10-ADR catalog. Wrote ADR-007 (guardrails), ADR-010 (circuit breaker), backfilled ADR-006 (eval).',
      result: 'Outage rate dropped 75%. Pattern adopted as enterprise-wide AI-SDLC baseline.',
    },
    interviewTraps: ['No catalog reference', 'Skipping the AI-specific ADRs (006/007/009/010)', 'Bespoke without standard'],
    finalScript: 'Ten ADRs cover the full AI-SDLC: dev policy + AGENTS.md + TDD + test protection + DDD folders + eval pipeline + guardrail service + prompt versioning + observability + circuit breaker. Together they\'re the minimum viable governance for production AI engineering. Each is reviewed by a 4-lens board (TL+Arch+Sec+EM) and enforced via CI gates. Without this catalog teams ship features missing the AI-specific ADRs (006/007/009/010) and discover the gap during outages or compliance reviews.',
  },
];

export default function ADRDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">ADR — Architecture Decision Record (deep dive)</h1>
        <p className="design-areas-sub">
          C4 explains structure; ADRs explain reasoning. Standard template, the 4-lens
          review board, status lifecycle, plus the 10-ADR catalog every AI engineering
          team should adopt for full AI-SDLC governance.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
