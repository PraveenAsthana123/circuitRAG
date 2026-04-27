'use client';

/**
 * C4 model — extended for AI systems (7 levels).
 *
 * Standard C4: System Context → Containers → Components → Code.
 * AI extension: + Governance → Observability → Lifecycle.
 *
 * The extension exists because production AI systems carry risks
 * (hallucination, cost runaway, model drift, regulatory exposure)
 * that traditional 4-level C4 doesn't address. Each level here is
 * a topic with its own Mermaid diagram and master-template content.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // LEVEL 1 — SYSTEM CONTEXT
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'level-1-system-context',
    title: '1. Level 1 — System Context (business + AI ecosystem)',
    status: 'shipped',
    coreConcept: 'Highest-level abstraction. Shows the AI system as a single box, the people who use it, and the external systems it depends on (LLM providers, data sources, governance). Trust boundaries are explicit.',
    oneLiner: 'Level 1 = who uses the AI system, what feeds it, where the trust boundaries are.',
    businessContext: 'Stakeholders + compliance + leadership want to see "where does AI fit in our business and what does it touch". This level is the business + AI ecosystem map — single diagram, no implementation detail.',
    fiveW: {
      what: 'A System Context diagram: the AI system as ONE box, its actors (users, admins, ops), its external systems (CRM, ERP, LLM provider, data sources), and explicit trust boundaries (public vs internal, AI-vendor boundary).',
      why: 'Without this map, ambient assumptions creep in: "we\'re sending PII to OpenAI?", "is the LLM call internal?", "who approves high-risk outputs?". Level 1 forces those assumptions onto a diagram everyone agrees on.',
      where: 'In the BRD/SAD before any architecture work. Reviewed by product + security + compliance + leadership.',
      when: 'Day 1 of any AI build. Updated when scope changes (new actor, new external system, new trust boundary).',
      who: 'Architect drafts; security + compliance review the trust boundaries; product owns the actor definitions.',
    },
    interview30s: 'At Level 1 of the C4 model I draw a single System Context: the AI system as one box, its actors (end users, admins, oncall), the external systems it integrates with (CRM, ERP, LLM provider, data sources), and explicit trust boundaries — public vs internal data, the AI-vendor boundary, the human-in-the-loop approval boundary. AI-specific additions to traditional C4 at this level: explicit LLM-provider boundary so legal can see what data crosses it; data-source classification so compliance can see what feeds the model; human-approval points so governance can see where high-risk outputs are gated.',
    hld: `flowchart TB
  subgraph users[Users + Admins]
    EU[End User]
    AD[Admin / Ops]
  end
  subgraph aiSystem[AI System SCOPE]
    AIB[Enterprise AI Assistant]
  end
  subgraph external[External systems]
    LLM[LLM Provider OpenAI Bedrock]
    DS[Data Sources docs PDFs DB]
    CRM[CRM ERP]
    GOV[Governance Audit Compliance]
  end
  EU -->|ask question| AIB
  AD -->|monitor approve| AIB
  AIB -->|prompt + completion| LLM
  AIB -->|read for grounding| DS
  AIB -->|read or write actions| CRM
  AIB -->|decision audit| GOV
  classDef trust fill:#fef3c7,stroke:#b45309,stroke-width:2px
  class LLM,CRM,GOV trust`,
    networkFlow: `flowchart LR
  C[Client] -->|HTTPS + JWT| GW[AI System edge]
  GW -.->|TLS + signed JWT| LLM[LLM Provider]
  GW -.->|read-only IAM| DS[Data Sources]
  GW -.->|signed audit row| GOV[Governance]`,
    flowchart: `flowchart LR
  Q[Business question] --> A1[Identify actors]
  A1 --> A2[Identify external systems]
  A2 --> A3[Mark trust boundaries]
  A3 --> A4[List AI-specific additions]
  A4 --> O[Approved Level 1 diagram]`,
    sequence: `sequenceDiagram
  participant U as End User
  participant AI as AI System
  participant LLM as LLM Provider
  participant GOV as Governance
  U->>AI: ask question
  AI->>LLM: prompt
  LLM-->>AI: completion
  AI->>GOV: decision audit
  AI-->>U: response`,
    coreLayers: [
      { layer: 'Actors', responsibility: 'End user + admin + ops + compliance + product. Each role explicit.' },
      { layer: 'AI system box', responsibility: 'Single box at this level — internals hidden until Level 2.' },
      { layer: 'External systems', responsibility: 'LLM provider + data sources + CRM/ERP + governance audit.' },
      { layer: 'Trust boundaries', responsibility: 'Lines between public/internal, vendor/in-house, human-approved/auto.' },
    ],
    lld: `flowchart LR
  EU[End User] --> AIB[AI System]
  AD[Admin] --> AIB
  AIB --> LLM[LLM provider]
  AIB --> DS[Data sources]
  AIB --> CRM[CRM ERP]
  AIB --> GOV[Governance]`,
    problem: 'Without a Level 1 diagram, AI scope creeps and trust boundaries become assumptions: "we\'re NOT sending PII to OpenAI right?" — answered too late.',
    whyThisApproach: 'Forcing the System Context onto a single page surfaces every external boundary BEFORE implementation. Cheaper to fix at this level than at Level 4.',
    whenToUse: ['Day 1 of any AI build', 'Scope review with leadership', 'Compliance / legal review', 'Cross-team alignment'],
    whenNotToUse: ['Mid-implementation iteration (use lower levels)', 'Single-developer hackathon'],
    input: 'Business goal + initial actor list + external system list',
    process: ['Identify actors', 'Identify external systems', 'Mark trust boundaries', 'Add AI-specific layers (LLM provider, data sources, HITL)', 'Review with security + product'],
    output: 'A single agreed System Context diagram + actor catalog + trust boundary list',
    alternatives: [
      { name: 'Free-form box-and-arrow drawing', tradeoff: 'Easy; lacks taxonomy + reviewer alignment' },
      { name: 'UML deployment diagram', tradeoff: 'Detailed; too much for "where does AI fit"' },
      { name: 'C4 Level 1 (this)', tradeoff: 'Standard taxonomy + business clarity + trust boundaries' },
    ],
    challenges: ['Stakeholders want detail at this level (resist; defer to L2)', 'Trust boundaries get hand-waved', 'AI-specific actors forgotten (vendor, audit)'],
    edgeCases: [
      { case: 'Vendor LLM is also a SaaS product the user already uses', solution: 'Two boxes: vendor-as-LLM and vendor-as-SaaS; different boundaries' },
      { case: 'Same internal team owns both AI and one of the external systems', solution: 'Still draw external — boundary is contractual, not org' },
    ],
    failureModes: [
      { mode: 'Trust boundary missed at L1 surfaces at compliance review', detect: 'Late legal pushback', recover: 'Add boundary; re-eval scope' },
    ],
    monitoring: ['Diagram lives in BRD/SAD; updated on scope change', 'Reviewed quarterly with compliance'],
    testing: ['Walk through diagram with 4 lenses (TL+Arch+Sec+Compliance) before approval'],
    security: ['Trust boundaries map to security review checkpoints', 'Vendor boundaries flag DPA / DPIA needs'],
    scaling: ['Diagram doesn\'t scale — stays at one page; L2+ handle scale'],
    maturity: { mvp: 'Hand-drawn on whiteboard', production: 'Mermaid in repo, reviewed quarterly', enterprise: 'Lives alongside ADR + risk register; CI checks for stale references' },
    limitations: ['No implementation detail (intentional)', 'Single-page constraint forces simplification'],
    projectFit: ['docs/architecture/system-context.md', '/admin/architect/deep — companion'],
    interviewLine: 'At Level 1 I define trust boundaries, AI usage scope, and human interaction points — critical for governance.',
    implementationSteps: [
      { step: 'List actors', logic: 'End user, admin, oncall, compliance officer.' },
      { step: 'List external systems', logic: 'LLM provider, data sources, downstream CRM/ERP, governance.' },
      { step: 'Mark trust boundaries', logic: 'Public vs internal, vendor vs in-house, auto vs human-approved.' },
      { step: 'Add AI-specific layers', logic: 'LLM-provider boundary, HITL approval, audit chain endpoint.' },
      { step: 'Review with 4 lenses', logic: 'TL + Arch + Sec + Compliance signoff.' },
      { step: 'Lock + version', logic: 'Diagram in repo; updated on scope change only.' },
    ],
    codeExample: { language: 'mermaid', code: `flowchart TB
  EU[End User] --> AIB[AI System]
  AD[Admin] --> AIB
  AIB -->|prompt| LLM[LLM Provider]
  AIB -->|read| DS[Data Sources]
  AIB -->|read write| CRM[CRM ERP]
  AIB -->|audit| GOV[Governance]
  classDef trust fill:#fef3c7,stroke:#b45309,stroke-width:2px
  class LLM,CRM,GOV trust` },
    realUseCase: 'AI assistant project: stakeholder thought "data stays in our cloud." Level 1 diagram revealed an OpenAI box outside the trust boundary; legal flagged + DPA was added. Caught at L1, $0 cost; caught after launch, would have been a breach disclosure.',
    prosCons: {
      pros: ['Standard taxonomy reviewers recognize', 'Forces trust boundaries explicit', 'AI-specific extensions named (LLM provider, HITL)'],
      cons: ['Non-technical readers still need explanation', 'Diagram drift if not updated on scope changes'],
    },
    comparison: { left: 'No L1 diagram', right: 'L1 diagram with trust boundaries (this)', rows: [
      { aspect: 'Compliance alignment', left: 'Late', right: 'Up-front' },
      { aspect: 'Vendor boundary visibility', left: 'Hidden', right: 'Marked' },
      { aspect: 'Stakeholder alignment', left: 'Verbal', right: 'Diagram-backed' },
    ] },
    solutions: [
      { problem: 'Vendor PII exposure unclear', solution: 'Trust boundary on LLM-provider box' },
      { problem: 'Compliance approval late', solution: 'Review L1 with compliance Day 1' },
    ],
    bestPractices: { do: ['Single page', 'AI-specific actors visible', 'Trust boundaries explicit', 'Versioned in repo'], avoid: ['Implementation detail at L1', 'Skipping the LLM-provider box', 'Hand-waved boundaries'], optimize: ['Mermaid for git-diffability', 'Cross-link to ADR + risk register'] },
    antiPatterns: ['Hidden vendor boundary', 'L1 with implementation detail', 'No HITL approval shown'],
    testTypes: ['4-lens review (TL+Arch+Sec+Compliance)', 'Stale-diagram CI check'],
    testScenarios: [
      { scenario: 'Adding new external CRM', expected: 'L1 diagram updated; compliance re-reviews' },
      { scenario: 'LLM vendor swap', expected: 'Trust boundary re-evaluated; DPA refreshed' },
    ],
    testData: [{ type: 'Sample L1 diagrams', example: 'Reference set of approved L1 from past projects' }],
    debuggingChecklist: ['Compliance pushback? Check L1 trust boundaries first', 'Stakeholder confused about scope? L1 is the missing artifact'],
    productionIssues: [
      { issue: 'PII sent to LLM provider undetected', rootCause: 'No trust boundary on L1; assumption drifted into code.' },
    ],
    performance: ['L1 review: ~1 hour with 4 lenses', 'Diagram update: ~30 min on scope change'],
    costConsiderations: ['Free — markdown + Mermaid + git', 'ROI: prevents one compliance incident'],
    observability: ['Diagram version in repo + last-reviewed date in front-matter'],
    metrics: [{ name: 'l1_diagram_freshness_days', example: 'Gauge; alert > 90 days since last review' }],
    tradeoffs: [
      { decision: 'Detail level', tradeoff: 'More detail = useful but bleeds into L2; less = abstract' },
      { decision: 'Trust boundary granularity', tradeoff: 'Too granular = noise; too coarse = compliance gaps' },
    ],
    decisionMatrix: [
      { option: 'C4 L1 (this)', whenToUse: 'Any AI build with stakeholder review' },
      { option: 'Free-form drawing', whenToUse: 'Solo prototype only' },
    ],
    starStory: {
      situation: 'Customer onboarding kicked off; team had no L1 diagram; compliance review at week 6 surfaced PII-to-vendor concern.',
      task: 'Create L1; close compliance gap before launch.',
      action: 'Drafted L1 in Mermaid; added LLM-provider trust boundary; legal added DPA; compliance signed off.',
      result: 'Launch on time. L1 became Day-1 deliverable for subsequent projects.',
    },
    interviewTraps: ['No trust boundaries', 'L1 with implementation detail', 'Skipping the AI-specific extensions'],
    finalScript: 'Level 1 of C4 is the System Context — single box for the AI system, actors around it, external systems it touches, trust boundaries explicit. AI-specific extensions: LLM-provider boundary, data-source classification, human-in-the-loop approval points, governance audit endpoint. Reviewed Day 1 by tech lead + architect + security + compliance. Lives in repo as Mermaid; updated on scope change. Catches vendor-data, compliance, and HITL gaps cheap — at this level fixing them is a diagram edit, not a re-architecture.',
  },

  // ═══════════════════════════════════════════════════════════════
  // LEVEL 2 — CONTAINERS
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'level-2-containers',
    title: '2. Level 2 — Containers (deployable units)',
    status: 'shipped',
    coreConcept: 'Zoom into the AI system. Show deployable building blocks: frontend, gateway, backend services, AI-specific containers (RAG, evaluation, guardrail, agent orchestrator, policy engine, observability). Each is independently deployable.',
    oneLiner: 'Level 2 = the deployable architecture; AI services SEPARATE from backend.',
    businessContext: 'The most common L2 mistake is collapsing AI logic into the backend service. AI workloads have different ops profiles (GPU, cost, drift, evaluation cadence) and must be containerized separately to evolve independently.',
    fiveW: {
      what: 'A Container diagram: each deployable unit (frontend, gateway, backend, RAG service, evaluation service, guardrail service, agent orchestrator, policy engine, observability stack, vector DB, application DB).',
      why: 'AI services need separate scaling, separate cost monitoring, separate eval gates, separate deployment cycles.',
      where: 'After L1 sign-off, before any service implementation.',
      when: 'Re-drawn when a new AI capability lands (new vector DB, new agent, new evaluator).',
      who: 'Architect + tech leads of each service team.',
    },
    interview30s: 'At Level 2 I separate AI into its own containers — RAG service, evaluation service, guardrail service, agent orchestrator, policy engine. Each is a deployable unit with its own SLA, cost budget, and eval cadence. The traditional C4 mistake people make at this level is folding AI into the backend container; that creates blast-radius coupling and prevents independent eval gates. The AI-specific containers I always add: prompt service, evaluation service, guardrail service, agent orchestrator, and policy engine.',
    hld: `flowchart TB
  FE[Frontend React]
  GW[API Gateway Kong]
  BE[Backend Service FastAPI]
  RAG[RAG Service]
  EVAL[Evaluation Service]
  GR[Guardrail Service]
  AGENT[Agent Orchestrator]
  POL[Policy Engine]
  OBS[Observability OpenTelemetry]
  VDB[(Vector DB Pinecone)]
  PG[(Postgres)]
  LLM[LLM Provider]
  FE --> GW
  GW --> BE
  BE --> RAG
  BE --> AGENT
  RAG --> VDB
  RAG --> LLM
  AGENT --> RAG
  AGENT --> EVAL
  RAG --> GR
  AGENT --> GR
  GR --> POL
  BE --> PG
  RAG -.-> OBS
  AGENT -.-> OBS
  GR -.-> OBS`,
    networkFlow: `flowchart LR
  C[Client] -->|HTTPS| GW
  GW -->|HTTP| BE
  BE -->|gRPC| RAG[RAG svc]
  RAG -->|REST| LLM[LLM provider]
  RAG -->|gRPC| VDB[(Vector DB)]`,
    flowchart: `flowchart LR
  Q[L1 approved] --> S1[Identify deployable units]
  S1 --> S2[Add AI-specific containers]
  S2 --> S3[Define inter-container protocols]
  S3 --> S4[Mark cost + scale + eval cadence per container]
  S4 --> O[Approved Level 2]`,
    sequence: `sequenceDiagram
  participant FE as Frontend
  participant GW as Gateway
  participant BE as Backend
  participant RAG as RAG svc
  participant GR as Guardrail
  FE->>GW: ask
  GW->>BE: forward
  BE->>RAG: retrieve+generate
  RAG->>GR: validate
  GR-->>RAG: ok
  RAG-->>BE: response
  BE-->>FE: stream`,
    coreLayers: [
      { layer: 'Edge', responsibility: 'Frontend + gateway. JWT decode, rate-limit, CORS.' },
      { layer: 'Backend', responsibility: 'Domain APIs that aren\'t AI; user mgmt, billing.' },
      { layer: 'AI services', responsibility: 'RAG + evaluation + guardrail + agent orchestrator + policy.' },
      { layer: 'Stores', responsibility: 'Vector DB + application DB; separated.' },
      { layer: 'Observability', responsibility: 'OpenTelemetry + log/metric/trace pipelines.' },
    ],
    lld: `flowchart LR
  BE[Backend] --> RAG[RAG svc]
  RAG --> GR[Guardrail]
  RAG --> EVAL[Evaluator]
  RAG --> POL[Policy]`,
    problem: 'AI inside backend = single deploy cadence + shared blast radius + no independent eval. Fails at scale.',
    whyThisApproach: 'AI containers carry different ops needs (GPU, eval cadence, cost monitoring). Independence is required, not optional.',
    whenToUse: ['Production AI systems', 'Multi-team AI builds', 'Anything past hackathon'],
    whenNotToUse: ['Internal tool with single AI call'],
    input: 'L1 diagram + non-functional requirements (scale, cost, latency, eval cadence)',
    process: ['Identify deployable units', 'Add AI-specific containers', 'Define inter-container protocols', 'Mark cost + scale + eval cadence per container', 'Review with ops + security'],
    output: 'L2 diagram + per-container metadata (tech, scaling, cost, eval cadence)',
    alternatives: [
      { name: 'Monolith with AI inline', tradeoff: 'Faster to start; impossible to scale or eval independently' },
      { name: 'Microservices everywhere', tradeoff: 'Right for AI; ops cost grows' },
      { name: 'C4 L2 with AI-extracted (this)', tradeoff: 'Best balance; standard taxonomy' },
    ],
    challenges: ['Resisting the "merge AI into backend" temptation', 'Defining inter-service protocols early', 'Ops cost of running 8+ containers'],
    edgeCases: [
      { case: 'Tiny prototype, only 1 AI feature', solution: 'Still extract — easier to grow; harder to split later' },
      { case: 'Two AI features sharing 90% logic', solution: 'One container, two routes; not two containers' },
    ],
    failureModes: [
      { mode: 'AI inside backend, eval can\'t run independently', detect: 'Eval cadence forced to backend deploy cadence', recover: 'Extract AI service' },
    ],
    monitoring: ['Per-container SLOs', 'Per-container cost', 'Per-container eval cadence'],
    testing: ['Container contract tests', 'Cross-container integration drills'],
    security: ['Per-container IAM', 'Network policies between containers', 'Secrets per container'],
    scaling: ['Each container scales independently', 'AI containers often need GPU; backend doesn\'t'],
    maturity: { mvp: '2-3 containers; AI inline', production: '8+ containers with AI extracted', enterprise: 'Per-tenant AI containers + multi-region' },
    limitations: ['Doesn\'t show internal component structure (use L3)', 'Container choices imply tech (Pinecone vs FAISS) — pin in ADR'],
    projectFit: ['docker-compose.yml + k8s manifests reflect L2', 'Per-container README + ownership doc'],
    interviewLine: 'AI separated from backend = different scale + cost + eval cadence. Most common C4 L2 mistake is folding AI into backend.',
    implementationSteps: [
      { step: 'Identify deployable units', logic: 'Frontend, gateway, backend, AI services, stores, observability.' },
      { step: 'Add AI-specific containers', logic: 'RAG, evaluation, guardrail, agent orchestrator, policy engine — separate from backend.' },
      { step: 'Define inter-container protocols', logic: 'gRPC for hot path; REST for slow; events for async.' },
      { step: 'Per-container metadata', logic: 'Tech + scaling + cost budget + eval cadence + ownership.' },
      { step: 'Review with ops + security', logic: 'Per-container IAM + network policies signed off.' },
    ],
    codeExample: { language: 'mermaid', code: `flowchart TB
  FE[Frontend] --> GW[API Gateway]
  GW --> BE[Backend FastAPI]
  BE --> RAG[RAG svc]
  BE --> AGENT[Agent Orchestrator]
  RAG --> EVAL[Evaluation]
  RAG --> GR[Guardrail]
  GR --> POL[Policy Engine]
  RAG --> VDB[(Vector DB)]
  RAG --> LLM[LLM Provider]
  BE --> PG[(Postgres)]` },
    realUseCase: 'Initial L2 had AI inside backend. First eval gate required a backend deploy — slowed iteration. Refactored to extract RAG + evaluation as separate containers; eval cadence dropped from weekly (backend deploy) to per-PR (eval-svc deploy). Cost monitoring became per-tenant per-AI-call instead of mixed.',
    prosCons: {
      pros: ['Independent scale + cost + eval cadence', 'Per-container blast radius', 'AI ops profile different from backend'],
      cons: ['8+ containers = ops surface', 'Inter-container protocol overhead', 'More CI/CD pipelines'],
    },
    comparison: { left: 'AI inline in backend', right: 'AI as separate containers (this)', rows: [
      { aspect: 'Eval cadence', left: 'Tied to backend deploy', right: 'Per-PR' },
      { aspect: 'Cost monitoring', left: 'Mixed', right: 'Per-AI-service' },
      { aspect: 'Scale strategy', left: 'Whole backend scales', right: 'AI containers scale separately' },
      { aspect: 'Ops surface', left: 'Smaller', right: 'Larger but manageable' },
    ] },
    solutions: [
      { problem: 'Eval gate forced into backend deploy', solution: 'Extract evaluation as its own container' },
      { problem: 'GPU sharing between unrelated services', solution: 'Per-container GPU quota + scheduling' },
      { problem: 'Cost attribution mixed', solution: 'Per-container OTel + cost dashboards' },
    ],
    bestPractices: { do: ['AI extracted as separate containers', 'Per-container ownership doc', 'Inter-container protocols pinned in contracts', 'Per-container SLOs + cost'], avoid: ['AI inline in backend', 'Shared GPU pool without quota', 'Container-per-feature (over-extraction)'], optimize: ['gRPC for hot paths', 'Sidecar pattern for guardrails', 'Per-tenant container variants if isolation matters'] },
    antiPatterns: ['AI inline', 'No evaluation container', 'No guardrail container', 'Shared LLM client across all services'],
    testTypes: ['Container contract tests', 'Cross-container integration drills', 'Per-container chaos tests'],
    testScenarios: [
      { scenario: 'Backend deploy', expected: 'AI containers unaffected (separate cadence)' },
      { scenario: 'New evaluation rule', expected: 'eval-svc deploy only; no backend touch' },
      { scenario: 'GPU shortage', expected: 'AI containers throttle; backend keeps serving' },
    ],
    testData: [{ type: 'L2 reference architectures', example: 'Approved per-domain L2 set' }],
    debuggingChecklist: ['Slow eval cadence? Eval not extracted as separate container', 'Cost attribution unclear? Containers not separated', 'Single bad deploy = AI down? AI not extracted'],
    productionIssues: [
      { issue: 'AI eval cadence stuck at weekly because of backend deploy cycle', rootCause: 'AI inline; eval coupled. Extracted to eval-svc; cadence per-PR.' },
    ],
    performance: ['Inter-container hop: ~5-15ms p95 (gRPC + mesh sidecar)', 'Per-container scale: independent; AI containers commonly GPU + horizontal'],
    costConsiderations: ['Per-container cost monitoring (CPU + GPU + tokens)', 'Container count vs ops cost — 8+ is OK; 30+ is not'],
    observability: ['Per-container OTel traces', 'Per-container metrics + dashboards', 'Per-container audit chain'],
    metrics: [
      { name: 'container_request_duration_seconds{container}', example: 'Histogram per container per route' },
      { name: 'container_cost_usd_per_day{container,tenant}', example: 'Gauge for cost attribution' },
    ],
    tradeoffs: [
      { decision: 'AI extracted vs inline', tradeoff: 'Extracted: independent scale + ops cost; inline: simpler but coupled' },
      { decision: 'Container count', tradeoff: 'More = better isolation; ops cost grows' },
    ],
    decisionMatrix: [
      { option: 'AI extracted (this)', whenToUse: 'Production AI; multi-team' },
      { option: 'AI inline', whenToUse: 'Hackathon only' },
    ],
    starStory: {
      situation: 'Initial AI build had RAG inline in backend; eval gate ran on backend deploy cycle (weekly).',
      task: 'Get eval to run per-PR.',
      action: 'Extracted RAG + evaluation as separate containers. Inter-container gRPC. Per-container CI.',
      result: 'Eval cadence weekly → per-PR. Cost attribution per-AI-call. Pattern in ADR-005.',
    },
    interviewTraps: ['AI inline', 'No evaluation/guardrail containers', 'Shared LLM client'],
    finalScript: 'Level 2 of C4 is the Container diagram. Standard containers — frontend, gateway, backend, stores, observability. AI-specific containers I always add — RAG service, evaluation service, guardrail service, agent orchestrator, policy engine. Each deployable independently with its own SLA, cost budget, and eval cadence. The biggest trap is folding AI into backend — that couples eval cadence to backend deploys and mixes cost attribution.',
  },

  // ═══════════════════════════════════════════════════════════════
  // LEVEL 3 — COMPONENTS
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'level-3-components',
    title: '3. Level 3 — Components (inside the AI container)',
    status: 'shipped',
    coreConcept: 'Zoom inside the AI service. Show internal components: pre-processor, retriever, re-ranker, context builder, prompt builder, LLM client, output parser, guardrail, evaluator. Plus advanced: cache, token manager, context manager, circuit breaker.',
    oneLiner: 'Level 3 = the RAG / agent / safety pipeline; where latency, cost, and accuracy are optimized.',
    businessContext: 'L3 is where ops decisions become concrete: caching, token budgets, fallback logic, evaluator hooks. Without this level, the AI service is a black box; with it, you can target specific components for optimization or hardening.',
    fiveW: {
      what: 'A Component diagram inside the RAG service: pre-processor → retriever → re-ranker → context builder → prompt builder → LLM client → output parser → guardrail → evaluator. Sidecar components: cache, token manager, context manager, circuit breaker.',
      why: 'Each component has its own latency, cost, and failure mode. Without naming them, you can\'t target the bottleneck.',
      where: 'After L2 sign-off; per-AI-service.',
      when: 'When optimizing or hardening a specific AI service.',
      who: 'Service owner + AI engineers.',
    },
    interview30s: 'Inside the RAG service at Level 3 I name nine core components: pre-processor for query rewriting, retriever for semantic search, re-ranker for precision, context builder for prompt assembly, prompt builder for the templated input, LLM client for the model call, output parser for structured response, guardrail for safety, evaluator for quality. Then four sidecar components that determine production economics: cache layer, token manager, context manager, circuit breaker. Naming them lets us target each one — caching the retrieve step alone often delivers 30%+ cost reduction.',
    hld: `flowchart LR
  Q[Query] --> PRE[Pre-Processor]
  PRE --> RET[Retriever]
  RET --> RR[Re-Ranker]
  RR --> CTX[Context Builder]
  CTX --> PB[Prompt Builder]
  PB --> LLM[LLM Client]
  LLM --> OP[Output Parser]
  OP --> GR[Guardrail]
  GR --> EV[Evaluator]
  EV --> R[Response]
  CACHE[Cache] -.-> RET
  TM[Token Manager] -.-> LLM
  CM[Context Manager] -.-> CTX
  CB[Circuit Breaker] -.-> LLM`,
    networkFlow: `flowchart LR
  In[Request] --> RAG[RAG container]
  RAG --> VDB[(Vector DB)]
  RAG --> LLM[LLM provider]
  RAG --> Cache[(Redis cache)]`,
    flowchart: `flowchart LR
  S[L2 RAG box] --> S1[List 9 core components]
  S1 --> S2[Add 4 sidecars cache token context CB]
  S2 --> S3[Mark per-component latency cost]
  S3 --> O[Approved L3]`,
    sequence: `sequenceDiagram
  participant Q as Query
  participant PRE as Pre-Processor
  participant RET as Retriever
  participant RR as Re-Ranker
  participant LLM as LLM Client
  participant GR as Guardrail
  Q->>PRE: rewrite expand
  PRE->>RET: search
  RET->>RR: top-K
  RR->>LLM: prompt with chunks
  LLM->>GR: stream response
  GR-->>Q: validated answer`,
    coreLayers: [
      { layer: 'Pre-process', responsibility: 'Query rewrite, expansion, intent classification, HyDE.' },
      { layer: 'Retrieve', responsibility: 'Vector + graph + keyword fusion.' },
      { layer: 'Rank', responsibility: 'Cross-encoder rerank top-20 → top-5.' },
      { layer: 'Build', responsibility: 'Context + prompt assembly with token budget.' },
      { layer: 'Generate', responsibility: 'LLM client with breaker + token manager.' },
      { layer: 'Validate', responsibility: 'Output parser + guardrail + evaluator.' },
    ],
    lld: `flowchart LR
  PRE --> RET
  RET --> CACHE
  CACHE --> RR
  RR --> CTX
  CTX --> CM
  CM --> PB
  PB --> LLM
  LLM --> CB
  CB --> OP
  OP --> GR
  GR --> EV`,
    problem: 'Without component naming, the AI service is a black box. Optimizations target the wrong layer.',
    whyThisApproach: 'Each component has measurable latency + cost + failure rate. Optimizing the WHOLE service is wasted effort; optimizing one named component pays back fast.',
    whenToUse: ['Production RAG / agent service tuning', 'AI service runbook authoring', 'Onboarding new engineers'],
    whenNotToUse: ['Pre-MVP prototype'],
    input: 'L2 container box',
    process: ['List 9 core components', 'Add 4 sidecars', 'Mark per-component latency + cost', 'Define interfaces + retry semantics'],
    output: 'L3 component diagram + per-component metrics + per-component runbook',
    alternatives: [
      { name: 'Black-box AI service', tradeoff: 'Easy; no optimization handle' },
      { name: 'Functional decomposition without names', tradeoff: 'Half-work; review-unfriendly' },
      { name: 'C4 L3 with sidecars (this)', tradeoff: 'Standard + ops-tractable' },
    ],
    challenges: ['Component boundary discipline (resist micro-splits)', 'Per-component metrics overhead', 'Sidecar coordination'],
    edgeCases: [
      { case: 'Component sometimes called twice (retry)', solution: 'Idempotency at component boundary; CB tracks retries' },
      { case: 'Two components share state (e.g., cache key)', solution: 'Make state explicit in interface; shared module' },
    ],
    failureModes: [
      { mode: 'LLM client times out', detect: 'CB opens', recover: 'Fallback response or skip-rerank' },
      { mode: 'Retriever returns empty', detect: 'No chunks found', recover: 'Refusal training output' },
    ],
    monitoring: ['Per-component p95 latency', 'Per-component error rate', 'Cache hit ratio', 'Token-per-component'],
    testing: ['Per-component unit tests', 'Cross-component integration', 'Component-fault drill'],
    security: ['Per-component IAM (some need outbound LLM, some don\'t)', 'Component-level audit logs'],
    scaling: ['Each component scales independently', 'Cache often the cheapest scale lever', 'GPU components on dedicated pool'],
    maturity: { mvp: '5-6 components; no sidecars', production: '9 core + 4 sidecar', enterprise: 'Per-tenant component variants' },
    limitations: ['Doesn\'t show code (Level 4)', 'Component graph evolves with capabilities'],
    projectFit: ['services/rag-svc/app/components/ — directory mirrors L3', 'Per-component README + tests'],
    interviewLine: 'L3 is where latency, cost, and accuracy are optimized. The 4 sidecar components — cache, token manager, context manager, circuit breaker — determine production economics.',
    implementationSteps: [
      { step: '9 core components', logic: 'Pre-processor, retriever, ranker, context, prompt, LLM, parser, guardrail, evaluator.' },
      { step: '4 sidecars', logic: 'Cache, token manager, context manager, circuit breaker.' },
      { step: 'Per-component metrics', logic: 'Latency p95, error rate, cost.' },
      { step: 'Interface contracts', logic: 'Input/output schema + retry semantics per component.' },
      { step: 'Runbook per component', logic: 'How to debug each in isolation.' },
    ],
    codeExample: { language: 'mermaid', code: `flowchart LR
  Q --> PRE[Pre-Processor]
  PRE --> RET[Retriever]
  RET --> RR[Re-Ranker]
  RR --> CTX[Context Builder]
  CTX --> PB[Prompt Builder]
  PB --> LLM[LLM Client]
  LLM --> OP[Output Parser]
  OP --> GR[Guardrail]
  GR --> EV[Evaluator]
  CACHE -.-> RET
  TM[Token Mgr] -.-> LLM
  CB[Circuit Breaker] -.-> LLM` },
    realUseCase: 'p95 latency stuck at 1.2s. L3 component breakdown: retriever 80ms, rerank 120ms, LLM 900ms (dominant). Cached LLM responses by query_hash + embedding_version → 35% cache hit → p95 dropped to 720ms. Without L3 component naming, the team had been optimizing the retriever (already fast).',
    prosCons: {
      pros: ['Optimization-targetable', 'Failure isolation', 'Per-component runbooks', 'Sidecars surface ops levers'],
      cons: ['9+4 = 13 components to monitor', 'Boundary discipline required'],
    },
    comparison: { left: 'Black-box AI service', right: 'Named L3 components (this)', rows: [
      { aspect: 'Optimization target', left: 'Whole service', right: 'Specific component' },
      { aspect: 'Failure attribution', left: '"AI service slow"', right: '"LLM client p95"' },
      { aspect: 'Onboarding speed', left: 'Slow', right: 'Component-by-component' },
    ] },
    solutions: [
      { problem: 'p95 latency too high', solution: 'L3 component breakdown identifies bottleneck' },
      { problem: 'LLM cost spike', solution: 'Token manager + cache sidecar' },
      { problem: 'LLM provider outage', solution: 'Circuit breaker sidecar + fallback' },
    ],
    bestPractices: { do: ['Name 9 core + 4 sidecars', 'Per-component metrics', 'Interface contracts', 'Per-component runbooks'], avoid: ['Black-box service', 'Skipping sidecars (especially circuit breaker)', 'Shared state across components'], optimize: ['Cache hit ratio first lever', 'Quantize cross-encoder', 'Per-tenant token budget'] },
    antiPatterns: ['No circuit breaker', 'No cache layer', 'No evaluator', 'Components without contracts'],
    testTypes: ['Per-component unit', 'Cross-component integration', 'Per-component fault injection'],
    testScenarios: [
      { scenario: 'LLM timeout', expected: 'CB opens; fallback returns; degraded response with disclaimer' },
      { scenario: 'Vector DB slow', expected: 'Cache hit on hot queries reduces load' },
      { scenario: 'Token budget exhausted', expected: 'Token manager throttles; new requests rejected' },
    ],
    testData: [{ type: 'Per-component test fixtures', example: 'Each component has an isolated test harness' }],
    debuggingChecklist: ['Slow service? L3 component breakdown', 'Specific failure? Per-component log', 'Cost spike? Token manager metrics'],
    productionIssues: [
      { issue: 'p95 latency stuck at 1.2s', rootCause: 'Optimizing wrong component without L3 naming.' },
      { issue: 'LLM provider outage took down RAG', rootCause: 'No CB sidecar.' },
    ],
    performance: ['Per-component p95: pre-processor 50ms, retriever 80ms, rerank 30ms, LLM 600-900ms', 'Cache hit path: 10-20ms total'],
    costConsiderations: ['LLM dominates cost; token manager + cache sidecar primary levers', 'Cross-encoder GPU per-query'],
    observability: ['Per-component OTel spans', 'Per-component metrics dashboard', 'Audit chain across components'],
    metrics: [
      { name: 'rag_component_duration_seconds{component,p}', example: 'Histogram per component per percentile' },
      { name: 'rag_component_error_total{component,reason}', example: 'Counter; per-component error attribution' },
      { name: 'rag_cache_hit_ratio', example: 'Gauge; target ≥ 0.30' },
    ],
    tradeoffs: [
      { decision: 'Component count', tradeoff: 'More = optimization handles + monitoring overhead' },
      { decision: 'Cache TTL', tradeoff: 'Long = better hit rate; staleness risk' },
      { decision: 'Cross-encoder vs no rerank', tradeoff: '+precision vs +latency' },
    ],
    decisionMatrix: [
      { option: 'L3 with sidecars (this)', whenToUse: 'Production AI service' },
      { option: 'Black-box', whenToUse: 'Prototype only' },
    ],
    starStory: {
      situation: 'AI service p95 1.2s; team optimized retriever for 3 weeks with no improvement.',
      task: 'Identify the actual bottleneck.',
      action: 'Drew L3 with per-component metrics. LLM dominated at 900ms. Added cache sidecar keyed by (query_hash, embedding_version).',
      result: '35% cache hit; p95 dropped to 720ms. Pattern adopted; L3 reviews quarterly per service.',
    },
    interviewTraps: ['No circuit breaker sidecar', 'No cache', 'No evaluator', 'Components without contracts'],
    finalScript: 'Level 3 of C4 zooms inside the AI container. Nine core components: pre-processor, retriever, re-ranker, context builder, prompt builder, LLM client, output parser, guardrail, evaluator. Four sidecars: cache, token manager, context manager, circuit breaker. Each with its own latency, cost, and failure mode. This is where production economics are decided — caching the retrieve step alone often delivers 30%+ cost reduction, and the circuit breaker is what keeps an LLM provider outage from cascading into a full-system outage.',
  },

  // ═══════════════════════════════════════════════════════════════
  // LEVEL 4 — CODE
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'level-4-code',
    title: '4. Level 4 — Code (implementation per component)',
    status: 'shipped',
    coreConcept: 'The most detailed level — actual code per component. Class diagrams, method signatures, schema validators. Often optional and IDE-generated, but necessary for code-review-level understanding.',
    oneLiner: 'Level 4 = how each L3 component is implemented in code.',
    businessContext: 'L4 is where DDD + strict typing + JSON-schema validation + structured error handling live. Each component name from L3 maps to a class/module name. Reviewers can grep.',
    fiveW: {
      what: 'Per-component code: classes, methods, validators, error types. Often shown as a UML class diagram or annotated code snippet.',
      why: 'L1-L3 are abstractions; the bug lives in code. L4 is the bridge between architecture and implementation.',
      where: 'In the service repo. Auto-generated where possible (IDE class browsers + AsyncAPI).',
      when: 'Component-by-component during implementation; updated when interfaces change.',
      who: 'Engineers implementing the component.',
    },
    interview30s: 'Level 4 of C4 is the code itself — usually optional in standard C4 because IDEs can show class structure, but for AI services I always pin the L3-to-code mapping: each named component (Retriever, PromptBuilder, LLMClient, etc.) is a class with strict types, JSON schema validation on inputs, and a defined error taxonomy. Mandatory practices at this level: DDD-aligned structure, no raw dict in service code, JSON schema on every external boundary, structured exceptions mapped to HTTP, full request tracing.',
    hld: `flowchart LR
  RAGSvc[RAGPipeline class] --> Retr[Retriever class]
  RAGSvc --> Rerank[ReRanker class]
  RAGSvc --> Builder[ContextBuilder class]
  RAGSvc --> Prompt[PromptBuilder class]
  RAGSvc --> LLM[LLMClient class]
  RAGSvc --> Parser[OutputParser class]
  RAGSvc --> Guard[Guardrail class]
  RAGSvc --> Eval[Evaluator class]`,
    networkFlow: `flowchart LR
  HTTP[HTTP request] --> Router[Pydantic validate]
  Router --> Service[Service class]
  Service --> Repo[Repository class]
  Repo --> DB[(Postgres)]`,
    flowchart: `flowchart LR
  L3[L3 components] --> Map[Map to classes]
  Map --> Types[Strict types]
  Types --> Schema[JSON schema validators]
  Schema --> Errors[Error taxonomy]
  Errors --> Code[Implemented]`,
    sequence: `sequenceDiagram
  participant R as Router
  participant S as Service
  participant LLM as LLMClient
  R->>S: AskRequest validated
  S->>LLM: generate
  LLM-->>S: response
  S-->>R: AskResponse validated`,
    coreLayers: [
      { layer: 'Router', responsibility: 'HTTP-only. Pydantic validate request/response. No business logic.' },
      { layer: 'Service', responsibility: 'Class with constructor injection. Domain logic.' },
      { layer: 'Component', responsibility: 'One L3-named class per component (Retriever, etc.).' },
      { layer: 'Repository', responsibility: 'All SQL here. tenant_connection() at boundary.' },
      { layer: 'Schema', responsibility: 'Pydantic models for every boundary. No raw dict.' },
    ],
    lld: `flowchart LR
  RAGPipeline -->|run| Retriever
  RAGPipeline -->|run| ReRanker
  RAGPipeline -->|run| LLMClient
  Retriever -->|search| QdrantClient
  LLMClient -->|generate| LLMProvider`,
    problem: 'Without L4 mapping, L3 components become folklore. Engineers reinvent the wheel per service.',
    whyThisApproach: 'L4 pins L3 names to class names. Code review references L3 directly: "the Guardrail class isn\'t enforcing the citation deadline."',
    whenToUse: ['During implementation', 'Code review', 'Onboarding'],
    whenNotToUse: ['Architecture-only documents', 'Pre-implementation phases'],
    input: 'L3 component diagram',
    process: ['Map L3 component names → class names', 'Define class interfaces with strict types', 'JSON schema validators on boundaries', 'Error taxonomy + handlers', 'Full structured logging'],
    output: 'Implemented service code with L3-to-L4 traceability',
    alternatives: [
      { name: 'Skip L4 (let IDE show)', tradeoff: 'Saves time; loses traceability for non-IDE readers' },
      { name: 'Full UML class diagrams', tradeoff: 'Comprehensive; high maintenance overhead' },
      { name: 'Annotated key snippets (this)', tradeoff: 'Best balance; reviewers can grep' },
    ],
    challenges: ['Keeping L4 in sync with code drift', 'Reviewer fatigue if too detailed', 'Class names changing breaks L3 traceability'],
    edgeCases: [
      { case: 'Component is split across multiple files', solution: 'Module-level marker + cross-link' },
      { case: 'Component is a vendor library wrapper', solution: 'Wrapper class still gets L4 entry' },
    ],
    failureModes: [
      { mode: 'L4 drifts from L3 names', detect: 'Code review confusion', recover: 'Quarterly cross-link audit' },
    ],
    monitoring: ['L4 doc freshness vs commit history', 'Component-class-name parity'],
    testing: ['Unit tests per class', 'Schema validation tests', 'Error-handler tests'],
    security: ['Pydantic strict mode prevents shape attacks', 'Per-class IAM where applicable'],
    scaling: ['L4 doesn\'t scale per se; class structure must support horizontal'],
    maturity: { mvp: 'L4 omitted', production: 'Per-component class + JSON schema + error taxonomy', enterprise: 'L4 doc + IDE class browser + auto-generated diagrams' },
    limitations: ['Optional in standard C4', 'High maintenance if hand-maintained'],
    projectFit: ['services/*/app/components/<name>.py — file per L3 component', 'README per service maps L3 → file'],
    interviewLine: 'L4 pins L3 component names to class names. Reviewers can grep "Guardrail" and find the file.',
    implementationSteps: [
      { step: 'L3 component → class', logic: 'One class per L3 box. Name parity required.' },
      { step: 'Strict types', logic: 'Pydantic v2 + Annotated. No raw dict.' },
      { step: 'JSON schema validators', logic: 'Every external boundary validated.' },
      { step: 'Error taxonomy', logic: 'AppError hierarchy mapped to HTTP via error_handlers.' },
      { step: 'Structured logging', logic: 'correlation_id + tenant_id on every log line.' },
    ],
    codeExample: { language: 'python', code: `# services/rag-svc/app/pipeline.py — L4 maps to L3 component names
from libs.py.documind_core.exceptions import ExternalServiceError

class Retriever:
    def __init__(self, qdrant_client, breaker):
        self._client = qdrant_client
        self._breaker = breaker
    async def search(self, query: str, tenant_id: str, top_k: int = 20) -> list[Chunk]:
        if not self._breaker.allow():
            raise ExternalServiceError("retriever unavailable")
        ...

class ReRanker:
    async def rank(self, query: str, chunks: list[Chunk]) -> list[RerankedChunk]:
        ...

class PromptBuilder:
    def build(self, context: list[Chunk], query: str) -> str:
        ...

class LLMClient:
    async def generate(self, prompt: str) -> AsyncIterator[str]:
        ...

class Guardrail:
    def validate(self, response: str) -> ValidationResult:
        ...

class RAGPipeline:
    """Orchestrates L3 components in order. Each step is a class call."""
    def __init__(self, retriever, reranker, builder, llm, parser, guardrail, evaluator):
        self._retriever = retriever
        self._reranker = reranker
        self._builder = builder
        self._llm = llm
        self._parser = parser
        self._guardrail = guardrail
        self._evaluator = evaluator

    async def run(self, query: str, tenant_id: str) -> AskResponse:
        chunks = await self._retriever.search(query, tenant_id)
        ranked = await self._reranker.rank(query, chunks)
        prompt = self._builder.build(ranked, query)
        response = ""
        async for token in self._llm.generate(prompt):
            response += token
        parsed = self._parser.parse(response)
        validated = self._guardrail.validate(parsed)
        await self._evaluator.score(query, validated)
        return validated` },
    realUseCase: 'L4 doc lived next to code with L3 → file mapping. New engineer ramped in 1 week (vs 4 weeks before doc existed). Code review comments referenced L3 names ("the Guardrail step is missing the citation-deadline check") — clear + actionable.',
    prosCons: {
      pros: ['L3-to-code traceability', 'Onboarding speed', 'Code review precision'],
      cons: ['Maintenance overhead if hand-written', 'Drifts without discipline'],
    },
    comparison: { left: 'No L4 mapping', right: 'L3 → class mapping (this)', rows: [
      { aspect: 'Onboarding time', left: '4 weeks', right: '1 week' },
      { aspect: 'Review precision', left: '"Make AI faster"', right: '"Optimize Retriever class"' },
      { aspect: 'Reviewer hand-off', left: 'Tribal', right: 'Doc-backed' },
    ] },
    solutions: [
      { problem: 'L3 names not in code', solution: 'Class-name parity rule + lint check' },
      { problem: 'JSON shape drift at boundary', solution: 'Pydantic strict mode + schema tests' },
      { problem: 'Generic 500 errors', solution: 'AppError taxonomy + error_handlers' },
    ],
    bestPractices: { do: ['One class per L3 component', 'Pydantic at every boundary', 'AppError taxonomy', 'Structured logging', 'README maps L3 → file'], avoid: ['Class names diverging from L3', 'Raw dict at boundaries', 'Catch-all 500 handlers'], optimize: ['Auto-generate class browser', 'Lint check for L3-name parity'] },
    antiPatterns: ['Classes named differently from L3', 'No JSON schema validators', 'Generic exceptions', 'Module mixing component + sidecar'],
    testTypes: ['Per-class unit', 'Schema validation', 'Error-handler', 'Integration cross-component'],
    testScenarios: [
      { scenario: 'Invalid request shape', expected: '422 with field-level error from Pydantic' },
      { scenario: 'Retriever raises ExternalServiceError', expected: 'Mapped to 503 with error_code' },
      { scenario: 'LLMClient cancellation', expected: 'Cleanup + structured log' },
    ],
    testData: [{ type: 'Component fixtures', example: 'One fixture file per class' }],
    debuggingChecklist: ['Where does this fail? Find class by L3 name; grep file', 'Schema 422? Compare request to Pydantic model'],
    productionIssues: [
      { issue: 'New engineer took 4 weeks to ramp', rootCause: 'No L4 mapping; tribal knowledge.' },
      { issue: 'Generic 500 hid root cause for hours', rootCause: 'No AppError taxonomy; catch-all.' },
    ],
    performance: ['Pydantic validation: ~0.5ms per round trip', 'Class instantiation: negligible'],
    costConsiderations: ['Documentation time vs reviewer time saved'],
    observability: ['Per-class log namespace', 'Structured logging with correlation_id', 'Class-level metrics where useful'],
    metrics: [
      { name: 'class_invocation_total{class,outcome}', example: 'Counter per class for outcome attribution' },
      { name: 'pydantic_validation_failures_total{model,field}', example: 'Counter; spike means bad client' },
    ],
    tradeoffs: [
      { decision: 'L4 detail level', tradeoff: 'Full UML = comprehensive + high maint; key snippets = lighter' },
      { decision: 'Auto-generated vs hand-written', tradeoff: 'Auto = fresh; less narrative' },
    ],
    decisionMatrix: [
      { option: 'L3 → class mapping (this)', whenToUse: 'Production code; multi-team' },
      { option: 'Skip L4', whenToUse: 'Solo small project' },
    ],
    starStory: {
      situation: 'New engineer stalled for 4 weeks reading code without an L3 → class map.',
      task: 'Cut ramp time.',
      action: 'Wrote L4 doc mapping each L3 component to its file. Class-name parity rule. Lint check.',
      result: 'Ramp time 4 weeks → 1 week. Code review comments referenced L3 names directly.',
    },
    interviewTraps: ['L4 omitted entirely', 'Class names diverge from L3', 'No JSON schema validators', 'Generic exceptions'],
    finalScript: 'Level 4 of C4 is code. In standard C4 it\'s optional and IDE-generated, but for AI services I always pin the L3-to-code mapping: each named component is a class with strict types, JSON schema validation on inputs, AppError taxonomy mapped to HTTP, structured logging with correlation_id. Reviewers can grep "Guardrail" and find the file. The discipline pays off in onboarding speed and code review precision — review comments reference L3 names directly, not vague "make AI better".',
  },

  // ═══════════════════════════════════════════════════════════════
  // LEVEL 5 — GOVERNANCE (AI extension)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'level-5-governance',
    title: '5. Level 5 — Governance (AI extension to standard C4)',
    status: 'shipped',
    coreConcept: 'AI-specific extension to standard 4-level C4. Policy engine + audit logs + risk classification + approval workflow. Not in classic C4 because it predates AI risks (hallucination, model drift, regulatory exposure).',
    oneLiner: 'Level 5 = policies + risk + approvals; the layer that makes AI deployable in regulated environments.',
    businessContext: 'AI systems shipped without governance fail compliance review or generate liability. Level 5 explicitly maps policy engine → risk classifier → approval workflow → audit chain. Required for EU AI Act, HIPAA, SOC2.',
    fiveW: {
      what: 'A governance diagram: policy engine + audit logs + risk classifier + approval workflow + HITL routing.',
      why: 'AI risk classes (low/medium/high) drive different controls. Without explicit governance, "high-risk" outputs go through the same path as "low-risk" — regulatory exposure.',
      where: 'Per-AI-system; tied to compliance review.',
      when: 'Day 1 for regulated industries; mid-project for others.',
      who: 'Compliance + AI lead + security.',
    },
    interview30s: 'Governance is the AI-specific extension to standard C4. Three pillars: policy engine, risk classifier, approval workflow. Policy engine encodes rules — no PII, approved-models-only, no harmful content. Risk classifier scores each output low/medium/high based on data sensitivity + decision impact. Approval workflow routes high-risk outputs to human-in-the-loop before delivery. Plus a hash-chained audit log of every decision with prompt version + model version + chunks + output + final action. Without this layer, AI ships hopes; with it, AI ships invariants.',
    hld: `flowchart TB
  IN[AI Output] --> POL[Policy Engine]
  POL --> RC[Risk Classifier]
  RC -->|low| OUT[Auto-deliver]
  RC -->|medium| AL[Audit log + deliver]
  RC -->|high| HITL[Human Review]
  HITL -->|approved| OUT
  HITL -->|rejected| RJ[Reject + audit]
  POL -.-> AL
  RC -.-> AL`,
    networkFlow: `flowchart LR
  AI[AI Output] -->|HTTP| POL[Policy svc]
  POL -->|deny or allow| RT[Router]
  RT --> Audit[(Audit chain DB)]`,
    flowchart: `flowchart LR
  S[Output ready] --> S1[Policy check]
  S1 --> S2[Risk classify]
  S2 -->|high| S3[HITL queue]
  S2 -->|low or med| S4[Auto deliver]
  S3 --> S4
  S4 --> S5[Audit chain write]`,
    sequence: `sequenceDiagram
  participant AI as AI svc
  participant POL as Policy
  participant RC as Risk
  participant H as Human
  AI->>POL: output
  POL-->>AI: passes
  AI->>RC: classify
  RC-->>AI: high risk
  AI->>H: queue for approval
  H-->>AI: approved
  AI-->>User: deliver`,
    coreLayers: [
      { layer: 'Policy', responsibility: 'Declarative rules: no PII, approved models, no harmful content.' },
      { layer: 'Risk classifier', responsibility: 'Score output low/medium/high based on data sensitivity + impact.' },
      { layer: 'Approval', responsibility: 'HITL routing for high-risk; auto for low.' },
      { layer: 'Audit', responsibility: 'Hash-chained log of every decision per tenant.' },
    ],
    lld: `flowchart LR
  POL[Policy] -->|allow| RC[Risk]
  POL -->|deny| RJ[Reject + audit]
  RC -->|high| HITL
  RC -->|low or med| OUT
  HITL --> OUT
  OUT --> Audit`,
    problem: 'Standard C4 has no governance layer. AI systems built without one fail compliance review.',
    whyThisApproach: 'Risk-based routing is the regulatory baseline (EU AI Act Art. 6-15). Per-tenant policy + audit chain is what auditors verify.',
    whenToUse: ['Regulated industries (HIPAA, SOC2, EU AI Act)', 'Customer-facing AI', 'Anything generating actions vs. just text'],
    whenNotToUse: ['Internal-only research prototype'],
    input: 'AI output + tenant context + risk metadata',
    process: ['Policy check', 'Risk classify', 'HITL routing if high-risk', 'Audit chain write', 'Deliver or reject'],
    output: 'Delivered output + audit row + risk score + approver (if HITL)',
    alternatives: [
      { name: 'No governance', tradeoff: 'Fast; fails compliance' },
      { name: 'Vendor governance (e.g., Lakera)', tradeoff: 'Faster start; vendor lock-in' },
      { name: 'In-house policy + audit (this)', tradeoff: 'Best fit + ops cost' },
    ],
    challenges: ['Risk threshold tuning', 'HITL queue latency', 'Policy rule maintenance'],
    edgeCases: [
      { case: 'Borderline risk score', solution: 'Sample for HITL; track confidence trend' },
      { case: 'HITL approver unavailable', solution: 'Fallback policy: queue or auto-reject' },
    ],
    failureModes: [
      { mode: 'Policy engine down', detect: '/health/upstreams red', recover: 'Fail-closed (reject all) or fall back to last-known policy' },
      { mode: 'Audit chain broken', detect: 'drill_audit_seal red', recover: 'Investigation + re-seal' },
    ],
    monitoring: ['Risk distribution per tenant', 'HITL queue depth + age', 'Policy denial rate', 'Audit chain integrity'],
    testing: ['Drill: high-risk output queued for HITL', 'Drill: policy denial fails closed', 'Drill: audit chain seal verifies'],
    security: ['Policy rules in git + signed', 'Audit chain HMAC per tenant', 'HITL approver auth + audit'],
    scaling: ['Policy eval: ~10-30ms p95', 'Audit chain write: async ~10ms', 'HITL queue: human-bounded'],
    maturity: { mvp: 'No governance', production: 'Policy + risk + audit', enterprise: 'Per-tenant policy + multi-region audit + automated compliance reports' },
    limitations: ['Doesn\'t prevent base-model issues (hallucination, bias)', 'HITL latency is human-bounded'],
    projectFit: ['governance-svc/ — policy + risk + audit', '/admin/guardrails/deep — runtime guardrails (input/output)', '/admin/rbac/deep — access control'],
    interviewLine: 'Governance is the AI-specific extension to standard C4. Without it, AI ships hopes; with it, AI ships invariants.',
    implementationSteps: [
      { step: 'Policy engine', logic: 'Declarative rules in git; canary deploy; per-tenant override.' },
      { step: 'Risk classifier', logic: 'Score low/medium/high based on data sensitivity + decision impact.' },
      { step: 'Approval workflow', logic: 'HITL for high; auto for low; medium logged + delivered.' },
      { step: 'Audit chain', logic: 'Hash-chained per tenant; tamper-evident.' },
      { step: 'Compliance reports', logic: 'Generated from audit chain on-demand.' },
    ],
    codeExample: { language: 'python', code: `# governance-svc/app/policy.py
from enum import Enum

class Risk(Enum): LOW = 0; MEDIUM = 1; HIGH = 2

class GovernanceLayer:
    def __init__(self, policy, classifier, hitl_queue, audit):
        self._policy = policy
        self._classifier = classifier
        self._hitl = hitl_queue
        self._audit = audit

    async def gate(self, output: AIOutput, tenant_id: str, request_id: str):
        # 1. Policy check
        verdict = await self._policy.evaluate(output, tenant_id)
        if verdict.deny:
            await self._audit.write(tenant_id, request_id, "policy_deny", verdict.reason)
            raise PolicyDenied(verdict.reason)

        # 2. Risk classify
        risk = await self._classifier.classify(output, tenant_id)

        # 3. Route by risk
        if risk == Risk.HIGH:
            approval = await self._hitl.enqueue_and_wait(output, tenant_id, request_id)
            if not approval.approved:
                await self._audit.write(tenant_id, request_id, "hitl_reject", approval.reason)
                raise OutputRejected(approval.reason)

        # 4. Audit chain write (medium + low)
        await self._audit.write(tenant_id, request_id, "delivered", {"risk": risk.name})
        return output` },
    realUseCase: 'Compliance customer required EU AI Act readiness. Policy engine encoded their rules; risk classifier flagged 8% of outputs as high-risk; HITL queue averaged 4-min approval. Audit chain produced compliance reports on demand. Without governance layer, customer would not have signed.',
    prosCons: {
      pros: ['Regulatory readiness', 'Risk-proportional controls', 'Tamper-evident audit'],
      cons: ['HITL latency for high-risk', 'Policy maintenance ops cost', 'Audit storage growth'],
    },
    comparison: { left: 'No governance', right: 'Policy + risk + HITL + audit (this)', rows: [
      { aspect: 'Compliance readiness', left: 'Fails review', right: 'Passes EU AI Act / SOC2' },
      { aspect: 'High-risk routing', left: 'Same as low-risk', right: 'HITL queue' },
      { aspect: 'Audit reconstruction', left: 'Slack archeology', right: 'Hash-chained per tenant' },
    ] },
    solutions: [
      { problem: 'Compliance review failed', solution: 'Add policy + risk + audit' },
      { problem: 'High-risk outputs delivered without review', solution: 'HITL routing on classifier' },
      { problem: 'Audit reconstruction broken', solution: 'Hash chain per tenant' },
    ],
    bestPractices: { do: ['Policy in git', 'Per-tenant risk thresholds', 'HITL with SLA', 'Hash-chained audit', 'Compliance reports on-demand'], avoid: ['Hardcoded policy in service code', 'Same controls across risk classes', 'No audit chain'], optimize: ['Cache policy decisions', 'Async audit writes (within TTL)', 'Per-tenant HITL pools'] },
    antiPatterns: ['No risk classifier', 'No HITL', 'No audit chain', 'Same policy across tenants'],
    testTypes: ['Drill: high-risk → HITL', 'Drill: policy denial fails closed', 'Drill: audit chain seal', 'Drill: compliance report generation'],
    testScenarios: [
      { scenario: 'Output classified high-risk', expected: 'HITL queue + 4-min SLA' },
      { scenario: 'Policy denies', expected: 'Output blocked + audit row' },
      { scenario: 'Audit chain broken', expected: 'drill red; investigation triggered' },
    ],
    testData: [{ type: 'Risk-score golden set', example: '500 (output, expected risk class) pairs' }],
    debuggingChecklist: ['HITL queue depth high? Approver capacity', 'Policy spike? Threshold tune', 'Audit gap? Async write failure'],
    productionIssues: [
      { issue: 'Audit gap of 12 minutes', rootCause: 'Audit DB timeout 50ms; bursty writes dropped. Fail-closed semantics added.' },
      { issue: 'High-risk output delivered without review', rootCause: 'Risk threshold too loose; tightened.' },
    ],
    performance: ['Policy eval: ~10-30ms p95', 'Risk classify: ~50ms p95', 'HITL: human-bounded (minutes)', 'Audit write: async ~10ms'],
    costConsiderations: ['HITL approver hours = dominant cost for high-risk-heavy workloads', 'Audit storage: ~1KB per row × retention'],
    observability: ['Per-tenant risk distribution', 'HITL queue depth + age', 'Policy denial rate trend', 'Audit chain integrity gauge'],
    metrics: [
      { name: 'governance_risk_distribution{tenant,class}', example: 'Counter per risk class per tenant' },
      { name: 'governance_hitl_queue_age_seconds{p}', example: 'Histogram; alert if p95 > SLA' },
      { name: 'governance_policy_denial_rate{tenant}', example: 'Gauge; sustained spike = attack or threshold drift' },
    ],
    tradeoffs: [
      { decision: 'Risk threshold tightness', tradeoff: 'Tight: more HITL load; loose: regulatory risk' },
      { decision: 'HITL SLA', tradeoff: 'Tighter SLA = more approvers; looser = user latency' },
    ],
    decisionMatrix: [
      { option: 'Full governance layer (this)', whenToUse: 'Regulated + customer-facing' },
      { option: 'Audit-only', whenToUse: 'Internal tools' },
      { option: 'No governance', whenToUse: 'Research prototype only' },
    ],
    starStory: {
      situation: 'Compliance customer required EU AI Act readiness; original system had no governance layer.',
      task: 'Pass compliance review without re-architecting the entire system.',
      action: 'Added governance-svc with policy + risk + HITL + hash-chained audit. Per-tenant rules. drill_governance_audit_seal in CI.',
      result: 'Customer signed. EU AI Act audit passed first attempt. ADR-008 documents the layer.',
    },
    interviewTraps: ['No risk classifier', 'No HITL routing', 'No audit chain', 'Hardcoded policy'],
    finalScript: 'Governance is the AI-specific extension to standard C4. Three pillars: policy engine, risk classifier, approval workflow. Policy encodes rules (no PII, approved models). Risk classifier scores outputs low/medium/high. Approval routes high-risk to HITL. Plus a hash-chained audit log of every decision. The regulatory baseline (EU AI Act Art. 6-15) requires risk-based routing — without governance, AI ships hopes, with it AI ships invariants.',
  },

  // ═══════════════════════════════════════════════════════════════
  // LEVEL 6 — OBSERVABILITY (AI extension)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'level-6-observability',
    title: '6. Level 6 — Observability (AI extension)',
    status: 'shipped',
    coreConcept: 'AI-specific extension. Track everything that determines AI behavior + cost: prompt versions, model versions, retrieved chunks, tokens in/out, latency per component, hallucination rate, drift. Without this, AI is a black box.',
    oneLiner: 'Level 6 = track prompt + response + tokens + latency + failures; AI is a black box without it.',
    businessContext: 'AI cost runs away invisibly without observability. Hallucination rate drift is invisible without sampling. Customer regression is invisible without per-tenant tracking. Level 6 is non-negotiable for production AI.',
    fiveW: {
      what: 'Per-request: prompt version, model version, chunks retrieved, tokens in/out, cost, latency per component, output, confidence, override. Per-tenant: drift trend, hallucination rate, FinOps dashboard.',
      why: 'AI failures are silent. Drift is gradual. Cost is per-token. None of these surface without explicit tracking.',
      where: 'OpenTelemetry + Prometheus + structured logs.',
      when: 'Continuously; reviewed weekly.',
      who: 'AI ops + SRE + FinOps.',
    },
    interview30s: 'Observability for AI tracks five dimensions: prompts (input + version), responses (output + tokens + cost), latency (per L3 component), failures (with root cause), drift (sampled comparison vs golden set). Each dimension has its own dashboard + alerts. Without observability AI is a black box; you can\'t debug, can\'t optimize cost, can\'t catch drift, can\'t prove compliance. Per-tenant dashboards make it possible to answer "is customer X seeing degradation" — without that breakdown the answer is always "we don\'t know yet".',
    hld: `flowchart TB
  AI[AI svc] -->|trace| OTel[OpenTelemetry]
  AI -->|log| Logs[(Structured logs)]
  AI -->|metric| Prom[(Prometheus)]
  OTel --> Tempo[(Tempo or Jaeger)]
  Logs --> Loki[(Loki)]
  Prom --> Graf[Grafana dashboards]
  Tempo --> Graf
  Loki --> Graf
  Graf --> Alert[Alerts]`,
    networkFlow: `flowchart LR
  Svc[AI svc] -->|OTLP| Coll[Collector]
  Coll --> Tempo
  Coll --> Prom
  Coll --> Loki`,
    flowchart: `flowchart LR
  Q[AI request] --> S1[Trace per request]
  S1 --> S2[Log per component]
  S2 --> S3[Metric per outcome]
  S3 --> S4[Aggregate per tenant]
  S4 --> S5[Dashboard + alert]`,
    sequence: `sequenceDiagram
  participant AI as AI svc
  participant OT as OTel collector
  participant P as Prometheus
  participant G as Grafana
  AI->>OT: span + metric + log
  OT->>P: metrics
  G->>P: query
  G-->>User: dashboard`,
    coreLayers: [
      { layer: 'Trace', responsibility: 'Per-request span tree; correlation_id propagated.' },
      { layer: 'Log', responsibility: 'Structured JSON; no raw PII.' },
      { layer: 'Metric', responsibility: 'Per-component p95 + error rate + cost.' },
      { layer: 'Audit', responsibility: 'Decision-grade record per request_id (overlap with L5).' },
      { layer: 'Drift', responsibility: 'Sampled comparison vs golden; weekly report.' },
    ],
    lld: `flowchart LR
  AI[AI svc] --> Tracer
  Tracer --> Span[OTel span]
  AI --> Logger
  Logger --> JSON[Structured log]
  AI --> Counter
  Counter --> Prom[Prometheus]`,
    problem: 'AI without observability fails silently. Cost runs away invisibly. Drift goes undetected.',
    whyThisApproach: 'Five-dimensional tracking (prompts + responses + latency + failures + drift) covers every silent failure mode. Per-tenant breakdown surfaces customer-specific issues.',
    whenToUse: ['Production AI systems', 'Customer-facing AI', 'Anything past hackathon'],
    whenNotToUse: ['Local dev only'],
    input: 'AI requests + responses + system events',
    process: ['Trace per request', 'Log per component', 'Metric per outcome', 'Aggregate per tenant', 'Drift sampling weekly'],
    output: 'Dashboards + alerts + drift reports + audit chain',
    alternatives: [
      { name: 'Logs only', tradeoff: 'Easy; no correlation' },
      { name: 'Vendor observability (Arize, W&B)', tradeoff: 'Faster start; per-call cost' },
      { name: 'Self-hosted OTel + Prom + Loki (this)', tradeoff: 'Full control + ops cost' },
    ],
    challenges: ['Sampling rate vs cost', 'Drift detection methodology', 'Per-tenant cardinality'],
    edgeCases: [
      { case: 'PII in logs', solution: 'redact_pii=True before log; sample shows only category + char_range' },
      { case: 'High-cardinality labels', solution: 'Sketch dataset structures (HLL); per-tenant ID hashing' },
    ],
    failureModes: [
      { mode: 'Trace pipeline backed up', detect: 'OTel collector queue depth', recover: 'Scale collector + drop sampling' },
      { mode: 'Drift undetected', detect: 'Weekly review missed', recover: 'Lower threshold + automated alert' },
    ],
    monitoring: ['Per-tenant cost', 'Per-component p95', 'Drift score weekly', 'Audit chain integrity'],
    testing: ['Drill: trace continuity end-to-end', 'Drill: drift detection on synthetic regression', 'Drill: PII not in logs'],
    security: ['No PII in logs', 'Trace IDs not auth tokens', 'Per-tenant log access'],
    scaling: ['OTel collector scales horizontally', 'Prom federation for multi-region', 'Log retention tiered by age'],
    maturity: { mvp: 'Stdout + basic metrics', production: 'OTel + Prom + Loki + per-tenant dashboards + drift sampling', enterprise: 'Multi-region + automated drift alerts + ML-based anomaly detection' },
    limitations: ['Sampling means some events lost', 'Drift detection is statistical, not exhaustive'],
    projectFit: ['observability stack in docker-compose', 'Per-service OTel SDK + structured logger', '/admin/llmops — operational health'],
    interviewLine: 'Observability for AI is non-negotiable. Without prompt + response + token + latency + failure tracking, AI ships hopes; with it, AI ships invariants.',
    implementationSteps: [
      { step: 'OTel SDK per service', logic: 'Spans + metrics + logs with correlation_id.' },
      { step: 'Per-component tracking', logic: 'L3 components → spans; per-component p95 + error.' },
      { step: 'Per-tenant aggregation', logic: 'Cost + drift + recall@K per tenant.' },
      { step: 'Drift sampling', logic: 'Weekly compare vs golden set; alert on regression.' },
      { step: 'Dashboards + alerts', logic: 'Per-component, per-tenant, FinOps.' },
    ],
    codeExample: { language: 'python', code: `# libs/py/documind_core/otel.py — instrumented AI request
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource

tracer = trace.get_tracer("rag-svc")
meter = metrics.get_meter("rag-svc")
request_duration = meter.create_histogram(
    "rag_request_duration_seconds", description="per-request latency",
)
token_counter = meter.create_counter(
    "rag_tokens_total", description="prompt+completion tokens",
)
cost_counter = meter.create_counter(
    "rag_cost_usd_total", description="USD cost per request",
)

async def ask(req: AskRequest, correlation_id: str) -> AskResponse:
    with tracer.start_as_current_span("ask") as span:
        span.set_attribute("tenant_id", req.tenant_id)
        span.set_attribute("correlation_id", correlation_id)
        span.set_attribute("prompt_version", settings.prompt_version)
        span.set_attribute("model_version", settings.model_version)

        with tracer.start_as_current_span("retrieve") as retrieve_span:
            chunks = await retriever.search(req.query, req.tenant_id)
            retrieve_span.set_attribute("chunks_found", len(chunks))

        with tracer.start_as_current_span("generate") as gen_span:
            response, tokens, cost = await llm.generate(prompt)
            gen_span.set_attribute("tokens.prompt", tokens.prompt)
            gen_span.set_attribute("tokens.completion", tokens.completion)
            token_counter.add(tokens.total, {"tenant": req.tenant_id})
            cost_counter.add(cost, {"tenant": req.tenant_id})

        request_duration.record(
            time.time() - start, {"tenant": req.tenant_id, "outcome": "success"},
        )
        return response` },
    realUseCase: 'Cost spike on tenant X invisible for 2 weeks until manual review found it. Added per-tenant cost dashboards + alert at 1.5× baseline. Next spike caught in 4 hours; tenant\'s admin alerted; usage pattern fixed. Without per-tenant breakdown, this would have been a surprise bill.',
    prosCons: {
      pros: ['Drift detection', 'Cost attribution', 'Per-component bottleneck identification', 'Compliance evidence'],
      cons: ['Sampling overhead (~1-3% per request)', 'Storage cost for traces + logs', 'High-cardinality labels'],
    },
    comparison: { left: 'Logs only', right: 'OTel + Prom + Loki + drift (this)', rows: [
      { aspect: 'Bottleneck identification', left: 'Manual', right: 'Per-component p95' },
      { aspect: 'Cost attribution', left: 'Aggregate', right: 'Per-tenant + per-feature' },
      { aspect: 'Drift detection', left: 'None', right: 'Weekly sampling' },
      { aspect: 'Compliance', left: 'Audit holes', right: 'Trace + audit composable' },
    ] },
    solutions: [
      { problem: 'Cost spike invisible', solution: 'Per-tenant cost dashboard + alert' },
      { problem: 'Drift undetected for weeks', solution: 'Weekly sampling vs golden set' },
      { problem: 'Bottleneck unclear', solution: 'Per-component p95' },
    ],
    bestPractices: { do: ['OTel everywhere', 'Per-tenant labels', 'Drift sampling weekly', 'Per-component p95', 'No PII in logs'], avoid: ['Logs only', 'No tenant breakdown', 'Skipping drift detection', 'Raw PII in spans'], optimize: ['Tail sampling for high-volume', 'Sketch sketches for cardinality', 'Tier log retention'] },
    antiPatterns: ['No tracing', 'No per-tenant dashboards', 'No drift detection', 'PII in logs'],
    testTypes: ['Drill: trace continuity', 'Drill: drift detected on synthetic regression', 'Drill: PII redaction enforced', 'Drill: cost attribution accurate'],
    testScenarios: [
      { scenario: 'Drift injected on golden set', expected: 'Drift score regresses; alert fires' },
      { scenario: 'PII in test prompt', expected: 'Logs contain category + range only' },
      { scenario: 'Per-tenant cost spike', expected: 'Alert fires within 5 min' },
    ],
    testData: [{ type: 'Drift fixture', example: 'Synthetic regression on golden set' }, { type: 'PII probe', example: 'Test prompts with embedded PII' }],
    debuggingChecklist: ['Slow request? Trace breakdown by L3 component', 'Cost spike? Per-tenant token dashboard', 'Drift? Weekly report'],
    productionIssues: [
      { issue: 'Tenant X cost spike invisible 2 weeks', rootCause: 'No per-tenant breakdown.' },
      { issue: 'Recall regression undetected', rootCause: 'Drift not sampled weekly; only on release.' },
    ],
    performance: ['OTel overhead: ~1-3% per request', 'Trace storage: ~5KB per request × retention', 'Per-tenant query: < 100ms in Grafana'],
    costConsiderations: ['Trace + log storage: ~$50-200/mo for medium scale', 'Drift compute: ~$50/mo'],
    observability: ['Self-monitoring: OTel collector queue depth + sampling rate'],
    metrics: [
      { name: 'rag_request_duration_seconds{tenant,component,p}', example: 'Histogram' },
      { name: 'rag_cost_usd_total{tenant,model}', example: 'Counter; FinOps dashboard' },
      { name: 'rag_drift_score{tenant,metric}', example: 'Gauge weekly; alert on regression' },
    ],
    tradeoffs: [
      { decision: 'Sampling rate', tradeoff: 'Higher = more accurate; more cost' },
      { decision: 'Retention', tradeoff: 'Long = compliance; storage cost' },
      { decision: 'Per-tenant labels', tradeoff: 'Granular = debugging; cardinality blowup' },
    ],
    decisionMatrix: [
      { option: 'OTel + Prom + Loki (this)', whenToUse: 'Production multi-tenant AI' },
      { option: 'Vendor (Arize, W&B)', whenToUse: 'Small team; pay per call' },
      { option: 'Logs only', whenToUse: 'Hackathon' },
    ],
    starStory: {
      situation: 'Tenant X cost spiked $4000/day invisibly for 2 weeks until manual review.',
      task: 'Get per-tenant visibility + alert before next spike.',
      action: 'Added per-tenant cost dashboard. Alert at 1.5× baseline. Drift sampling weekly.',
      result: 'Next spike caught in 4 hours. Tenant admin alerted; usage pattern fixed. Pattern in ADR-009.',
    },
    interviewTraps: ['Logs only', 'No per-tenant breakdown', 'No drift detection', 'PII in logs'],
    finalScript: 'Observability is the AI-specific extension to standard C4. Track everything that determines AI behavior + cost: prompts, responses, chunks retrieved, tokens, per-component latency, failures, drift. OTel for tracing, Prometheus for metrics, Loki for logs. Per-tenant dashboards. Drift sampling weekly. No PII in logs. Without observability, AI is a black box — you can\'t debug, can\'t optimize cost, can\'t catch drift, can\'t prove compliance. With it, AI is a measurable production system.',
  },

  // ═══════════════════════════════════════════════════════════════
  // LEVEL 7 — LIFECYCLE / CI-CD (AI extension)
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'level-7-lifecycle',
    title: '7. Level 7 — Lifecycle (CI/CD for AI)',
    status: 'shipped',
    coreConcept: 'AI-specific extension. Prompt → test → evaluate → score → approve → deploy → monitor → improve. Each stage has its own gate. Without lifecycle, prompt edits ship via git push.',
    oneLiner: 'Level 7 = the AI release pipeline; prompt edits + model swaps + retrieval-config changes all gated by eval.',
    businessContext: 'AI behavior changes on every prompt + model + retrieval edit. Without a lifecycle pipeline, regressions ship silently. Eval-gated CI/CD is what makes AI changes safe.',
    fiveW: {
      what: 'A pipeline: prompt versioning → eval harness → score → approval → canary → full deploy → monitor → improve. Each stage has SLA + gate.',
      why: 'Prompt edits change behavior immediately. Model swaps change recall. Retrieval config changes context. Without eval-gated CI/CD, regressions ship.',
      where: 'In CI (GitHub Actions / Jenkins) + the registry stack from L5/L6.',
      when: 'Every PR that touches behavior-changing artifacts.',
      who: 'AI engineers + SRE.',
    },
    interview30s: 'Lifecycle for AI is the eight-stage pipeline: prompt versioning in git → eval on golden set → score → approval (by AI lead + product) → canary 5% → monitor → full deploy → continuous improvement loop. Each stage has gates: eval below threshold blocks merge; canary regression triggers rollback; post-deploy monitoring feeds the next iteration. Without this, prompt edits are git pushes that change behavior immediately + invisibly. With it, every behavior-changing artifact is reversible + auditable + measurable.',
    hld: `flowchart LR
  PR[Prompt edit PR] --> CI[CI eval gate]
  CI -->|pass| App[Approval]
  CI -->|fail| Block
  App --> Canary[Canary 5 percent]
  Canary -->|pass| Full[Full deploy]
  Canary -->|fail| Rollback
  Full --> Mon[Monitor]
  Mon --> Improve[Next iteration]`,
    networkFlow: `flowchart LR
  Dev[Developer] --> Git[Git push]
  Git --> CI[CI runner]
  CI --> Reg[Registry]
  Reg --> Prod[Production]`,
    flowchart: `flowchart LR
  Q[Behavior change] --> S1[PR with version bump]
  S1 --> S2[CI eval]
  S2 -->|pass| S3[Approval]
  S2 -->|fail| Block[Block merge]
  S3 --> S4[Canary]
  S4 --> S5[Full deploy]
  S5 --> S6[Monitor]
  S6 --> S7[Next iteration]`,
    sequence: `sequenceDiagram
  participant Dev as Developer
  participant CI as CI
  participant Reg as Registry
  participant Prod as Production
  Dev->>CI: PR
  CI->>CI: eval golden set
  CI-->>Dev: pass
  Dev->>Reg: deploy canary
  Reg->>Prod: 5% traffic
  Prod-->>Reg: metrics
  Reg->>Prod: full rollout`,
    coreLayers: [
      { layer: 'Versioning', responsibility: 'Prompts + models + retrieval configs in git registry.' },
      { layer: 'Eval', responsibility: 'Golden set + held-out + production sample; gates merge.' },
      { layer: 'Approval', responsibility: 'AI lead + product sign off on score + canary plan.' },
      { layer: 'Canary', responsibility: '5% traffic; monitor key metrics; auto-rollback on regression.' },
      { layer: 'Monitor', responsibility: 'Post-deploy: drift, cost, recall, hallucination.' },
      { layer: 'Improve', responsibility: 'Feed monitor signals back to next iteration.' },
    ],
    lld: `flowchart LR
  PR --> Lint
  Lint --> Eval
  Eval --> Score
  Score --> Approve
  Approve --> Canary
  Canary --> Monitor
  Monitor --> Improve`,
    problem: 'Prompt edits ship via git push. Model swaps happen in registry. Retrieval changes happen in config. Each is a behavior change without a gate.',
    whyThisApproach: 'Eight-stage gated pipeline makes every change reversible + auditable + measurable. Canary catches regressions; monitor catches drift; improve closes the loop.',
    whenToUse: ['Production AI', 'Customer-facing systems', 'Regulated industries'],
    whenNotToUse: ['Solo experiments'],
    input: 'PR with version-bumped artifact',
    process: ['CI eval', 'Score', 'Approval', 'Canary', 'Monitor', 'Full deploy', 'Continuous improvement'],
    output: 'Deployed AI version + audit + metrics + improvement backlog',
    alternatives: [
      { name: 'Git push only', tradeoff: 'Fast; regressions ship silently' },
      { name: 'Manual eval', tradeoff: 'Catches some regressions; slow + biased' },
      { name: 'Eight-stage CI/CD (this)', tradeoff: 'Best safety + ops cost' },
    ],
    challenges: ['Eval golden set maintenance', 'Approval-gate latency', 'Canary metric stability'],
    edgeCases: [
      { case: 'Eval flaky on small sample', solution: 'Larger golden set; statistical confidence intervals' },
      { case: 'Approval blocked due to disagreement', solution: 'Documented decision criteria; escalation path' },
    ],
    failureModes: [
      { mode: 'Canary regression undetected', detect: 'Post-deploy metrics regression', recover: 'Tighten canary metric set + auto-rollback' },
      { mode: 'Eval drift over time', detect: 'Golden set scores trend down', recover: 'Refresh golden set quarterly' },
    ],
    monitoring: ['Eval pass rate per release', 'Canary regression rate', 'Time from PR to full deploy', 'Improvement loop velocity'],
    testing: ['Eval CI gate', 'Canary auto-rollback drill', 'Approval workflow drill'],
    security: ['Approver auth', 'Audit chain on every approval', 'Signed registry artifacts'],
    scaling: ['Eval parallelizable across golden set', 'Canary % per service', 'Multi-tenant canary support'],
    maturity: { mvp: 'Manual eval', production: '8-stage pipeline + canary + auto-rollback', enterprise: 'Multi-region canary + automated improvement loop + ML-based regression detection' },
    limitations: ['Golden set must be representative', 'Canary metric set must be sensitive', 'Improvement loop is manual'],
    projectFit: ['.github/workflows/ai-cicd.yml', 'Registry: prompts/, models/, retrieval-configs/', '/admin/llmops/deep — operational view'],
    interviewLine: 'Lifecycle for AI: prompt → test → evaluate → score → approve → deploy → monitor → improve. Without it, prompt edits are git pushes that change behavior silently.',
    implementationSteps: [
      { step: 'Versioning', logic: 'Prompts + models + retrieval configs in registry; semver.' },
      { step: 'CI eval gate', logic: 'Golden set + held-out + production sample; threshold-based pass/fail.' },
      { step: 'Approval workflow', logic: 'AI lead + product on each release.' },
      { step: 'Canary 5%', logic: 'Traffic split; key metrics monitored; auto-rollback on regression.' },
      { step: 'Full deploy', logic: 'Canary clean → ramp to 100%.' },
      { step: 'Monitor + improve', logic: 'Post-deploy signals feed next iteration backlog.' },
    ],
    codeExample: { language: 'yaml', code: `# .github/workflows/ai-cicd.yml — prompt + model release pipeline
name: AI CI/CD
on:
  pull_request:
    paths:
      - 'prompts/**'
      - 'configs/retrieval/**'
      - 'configs/models/**'

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run eval on golden set
        run: |
          python eval/run.py --golden=data/golden.jsonl
      - name: Score gate
        run: |
          score=$(jq .recall_at_10 eval/result.json)
          threshold=0.85
          if (( $(echo "$score < $threshold" | bc -l) )); then
            echo "Eval failed: $score < $threshold"
            exit 1
          fi

  approve:
    needs: eval
    runs-on: ubuntu-latest
    environment: ai-approval  # GitHub Environments require approver sign-off
    steps:
      - run: echo "Approval received"

  canary:
    needs: approve
    runs-on: ubuntu-latest
    steps:
      - name: Deploy canary 5%
        run: kubectl apply -f k8s/canary.yaml
      - name: Wait for canary metrics
        run: |
          sleep 600  # 10 min observation
          python check_canary_health.py || (kubectl rollback canary; exit 1)

  rollout:
    needs: canary
    runs-on: ubuntu-latest
    steps:
      - run: kubectl apply -f k8s/full-deploy.yaml` },
    realUseCase: 'Pre-pipeline: prompt edits shipped via PR merge directly to prod. Caught a 3pp recall regression weeks later by user complaint. Added eval gate + approval + canary. Next regression caught at PR; engineer revised prompt; re-eval passed; deployed cleanly. Zero silent regressions in 6 months.',
    prosCons: {
      pros: ['Eval gate catches regressions before prod', 'Canary auto-rollback on regression', 'Approval audit', 'Improvement loop closes'],
      cons: ['Pipeline adds latency to releases', 'Golden set maintenance', 'Approval-gate scheduling'],
    },
    comparison: { left: 'Git push to prod', right: '8-stage pipeline (this)', rows: [
      { aspect: 'Regression catch rate', left: 'After user complaint', right: 'At PR or canary' },
      { aspect: 'Rollback', left: 'Manual', right: 'Auto on canary regression' },
      { aspect: 'Audit trail', left: 'git log', right: 'Per-release approval + canary metrics' },
      { aspect: 'Improvement loop', left: 'Ad hoc', right: 'Monitor → backlog' },
    ] },
    solutions: [
      { problem: 'Silent regression', solution: 'Eval gate at PR' },
      { problem: 'Bad release in prod', solution: 'Canary auto-rollback' },
      { problem: 'No release audit', solution: 'Per-release approval + chain' },
    ],
    bestPractices: { do: ['Versioned artifacts in registry', 'Eval gate at PR', 'Approval workflow', 'Canary 5% with auto-rollback', 'Monitor post-deploy'], avoid: ['Git push to prod', 'Skipping eval', 'No canary', 'Manual rollback only'], optimize: ['Parallel eval', 'Per-tenant canary', 'Auto improvement-loop ticket creation'] },
    antiPatterns: ['No eval gate', 'No canary', 'No approval', 'No improvement loop'],
    testTypes: ['Drill: eval blocks merge on regression', 'Drill: canary auto-rollbacks', 'Drill: approval required'],
    testScenarios: [
      { scenario: 'Prompt edit reduces recall', expected: 'CI eval gate fails; merge blocked' },
      { scenario: 'Canary metrics regress', expected: 'Auto-rollback within 10 min' },
      { scenario: 'Approval missing', expected: 'Pipeline blocked at approval stage' },
    ],
    testData: [{ type: 'Eval golden set', example: '500 (input, expected) pairs per role' }],
    debuggingChecklist: ['Eval failing? Compare prompt diff + golden delta', 'Canary regressed? Check canary metrics', 'Pipeline stuck? Approval pending'],
    productionIssues: [
      { issue: 'Recall regression caught only by user complaint', rootCause: 'Eval gate not enforced; merged anyway. Hard CI gate added.' },
      { issue: 'Bad model rollout took 30 min to revert', rootCause: 'Manual rollback. Canary auto-rollback added.' },
    ],
    performance: ['CI eval: ~30s for 500-item golden set', 'Approval cycle: hours-days human-bounded', 'Canary observation: ~10 min'],
    costConsiderations: ['CI runtime: ~$0.05/run', 'Approver hours: dominant cost', 'Canary infra: ~5% of full deploy cost'],
    observability: ['CI pass rate', 'Canary auto-rollback rate', 'Time PR → full deploy', 'Improvement loop velocity'],
    metrics: [
      { name: 'ai_eval_pass_rate{period}', example: 'Gauge per release window' },
      { name: 'ai_canary_rollback_total', example: 'Counter; high = regression detection working' },
      { name: 'ai_release_lead_time_hours{p}', example: 'Histogram; trend per quarter' },
    ],
    tradeoffs: [
      { decision: 'Eval threshold tightness', tradeoff: 'Tight = catches regressions; blocks legitimate' },
      { decision: 'Canary % + duration', tradeoff: 'Smaller/shorter = fast; larger/longer = more confidence' },
      { decision: 'Approval rigor', tradeoff: 'Strict = audit; slows releases' },
    ],
    decisionMatrix: [
      { option: '8-stage pipeline (this)', whenToUse: 'Production AI; multi-team' },
      { option: 'Eval-only', whenToUse: 'Internal tools' },
      { option: 'Git push', whenToUse: 'Hackathon only' },
    ],
    starStory: {
      situation: 'Prompt edit caused 3pp recall regression caught only by user complaint after 2 weeks.',
      task: 'Make prompt edits eval-gated + canary-tested.',
      action: 'Built 8-stage pipeline: registry + CI eval + approval + canary + monitor. drill_ai_release_pipeline in CI.',
      result: 'Zero silent regressions in 6 months. Canary auto-rollback caught 2 bad releases without user impact. ADR-010.',
    },
    interviewTraps: ['No eval gate', 'No canary', 'No approval audit', 'No improvement loop'],
    finalScript: 'Lifecycle for AI is the eight-stage pipeline: prompt versioning → eval gate → score → approval → canary → monitor → full deploy → continuous improvement. Each stage has gates: eval blocks merge below threshold; canary auto-rollbacks on regression; post-deploy monitoring feeds the next iteration. Standard C4 has no lifecycle layer because it predates AI; without this, prompt edits ship via git push and regressions surface only via user complaints. With it, every behavior-changing artifact is reversible, auditable, measurable.',
  },
];

export default function C4ModelDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">C4 model — extended for AI systems (7 levels)</h1>
        <p className="design-areas-sub">
          Standard C4 has 4 levels (System Context → Containers → Components → Code).
          AI systems need 3 more — Governance, Observability, Lifecycle — because production
          AI carries risks (hallucination, model drift, regulatory exposure, cost runaway)
          that the original C4 doesn&apos;t address. Each level here is a topic with its own
          Mermaid diagram and master-template content.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
