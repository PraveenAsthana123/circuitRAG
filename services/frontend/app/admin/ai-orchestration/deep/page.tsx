'use client';

/**
 * AI orchestration architecture: three-layer model.
 *   Policy (rules) → Manager (Paperclip) → Workers (OpenClaw) → External
 *
 * Each layer is a distinct topic with its own master-template entry.
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ---- 1. Policy Layer ----
  {
    slug: 'policy-layer',
    title: '1. Policy Layer (Polisa) — control + compliance',
    status: 'shipped',
    coreConcept: 'The non-negotiable runtime gate that decides what the AI system can and cannot do. Implemented as Open Policy Agent (OPA) for authorization rules, Guardrails AI for output validation, and Presidio for PII protection. Sits ABOVE the manager layer — every request passes through it before any agent acts.',
    oneLiner: 'Policy = rules + governance; without it, agents become uncontrollable risk.',
    businessContext: 'Multi-agent AI systems with execution authority touch real-world side effects (APIs, payments, customer data). One unchecked agent action = compliance breach + reputation damage. Policy layer is the structural answer.',
    fiveW: {
      what: 'A set of declarative rules + runtime enforcers: OPA evaluates per-request authorization, Guardrails AI validates inputs/outputs, Presidio masks PII before storage or external send.',
      why: 'Rule-based gating is the only auditable defense against agent runaway. Allows enterprise adoption by giving compliance teams a single control plane.',
      where: 'Sits between API Gateway and the Manager (Paperclip) layer. Every request, every agent action, every external call passes through.',
      when: 'Always for production AI with execution authority. Mandatory for regulated tiers (HIPAA, SOC2, EU AI Act).',
      who: 'Security + compliance + AI safety team owns. Each manager + worker layer consumes; each agent invocation is gated.',
    },
    interview30s: 'The policy layer is the non-negotiable runtime gate. OPA enforces authorization (which agents can call which tools), Guardrails AI validates outputs (no PII leakage, no toxic content, no jailbreak), Presidio masks data before storage. Every request from Paperclip to OpenClaw passes through. The discipline: rules are declarative (Rego, YAML), versioned, audited per decision. Without this, agents own the platform\'s behavior — which is unsafe.',
    coreBuildingBlocks: [
      'OPA (Open Policy Agent) — Rego policies; per-request authorization',
      'Guardrails AI — input + output validators (PII, toxicity, jailbreak)',
      'Presidio (Microsoft) — PII detection + redaction (regex + NER)',
      'Decision audit — every allow/deny logged with policy_version + correlation_id',
      'Rule registry — versioned policies in Postgres or git',
      'Sidecar deployment — OPA runs alongside service for low-latency eval',
    ],
    architectureRelevance: {
      backend: 'API gateway calls OPA before forwarding to manager. <5ms eval typical for sidecar OPA. Decision is allow / deny / require-approval.',
      rag: 'Pre-LLM input guardrails (PII mask, prompt-injection detect). Post-LLM output guardrails (toxicity, citation-deadline, forbidden-pattern).',
      ai: 'Every agent action gated. Tool-call permissions in Rego. Cost ceilings. HITL escalation paths.',
      microservices: 'Each service queries OPA before privileged ops. Audit chain hash-chained per tenant.',
    },
    hld: `flowchart TB
  USR[User] --> AGW[API Gateway]
  AGW --> POL[Policy Layer]
  subgraph polblock["Policy enforcers"]
    OPA[("OPA — Rego rules")]
    GR[("Guardrails AI — in/out")]
    PRE[("Presidio — PII")]
  end
  POL --> OPA
  POL --> GR
  POL --> PRE
  POL -->|allow| MGR[Manager: Paperclip]
  POL -->|deny + audit| BLK[403 + audit log]
  MGR --> WRK[Workers: OpenClaw]
  WRK --> POL
  POL --> EXT[External APIs]`,
    networkFlow: `flowchart LR
  C[Client] --> AGW[API Gateway]
  AGW -->|HTTPS X-Tenant-ID| POL[Policy sidecar]
  POL -->|gRPC eval Rego| OPA[OPA]
  POL -->|HTTP validate| GR[Guardrails AI]
  POL -->|HTTP redact| PRE[Presidio]
  POL -->|allow forward| MGR[Manager service]
  MGR -->|tool call| POL
  POL -->|allow + redact| WRK[Worker pool]`,
    flowchart: `flowchart LR
  REQ[Request + tenant + actor] --> P1[Policy lookup]
  P1 --> A{Authorized}
  A -->|no| D1[403 + audit]
  A -->|yes| G[Guardrails check]
  G -->|fail| D2[Block + audit]
  G -->|pass| R[Redact PII]
  R --> M[Forward to Manager]
  M --> RES[Response]
  RES --> G2[Output guardrails]
  G2 -->|fail| D3[Interrupt + audit]
  G2 -->|pass| OUT[Return to user]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant GW as Gateway
  participant POL as Policy
  participant MGR as Paperclip
  participant WRK as OpenClaw
  participant Aud as Audit
  U->>GW: request
  GW->>POL: evaluate
  POL->>POL: OPA + Guardrails + Presidio
  alt allowed
    POL->>MGR: forward + redacted
    MGR->>WRK: assign task
    WRK->>POL: tool-call eval
    POL-->>WRK: allow OR deny
    WRK-->>MGR: result
    MGR-->>U: response
  else denied
    POL->>Aud: log deny + reason
    POL-->>U: 403
  end`,
    coreLayers: [
      { layer: 'OPA layer', responsibility: 'Authorization rules in Rego. Per-tenant + per-feature. Sidecar deployment for <5ms eval.' },
      { layer: 'Guardrails layer', responsibility: 'Input + output validators. Prompt-injection, PII, toxicity, hallucination, citation-deadline.' },
      { layer: 'Presidio layer', responsibility: 'PII detection + redaction. Regex + NER. Per-tenant + per-jurisdiction policy.' },
      { layer: 'Audit layer', responsibility: 'Hash-chained decision log per tenant. Every allow + deny captured.' },
      { layer: 'Rule registry', responsibility: 'Versioned policies in git. Reviewed by security + compliance.' },
    ],
    problem: 'Without runtime policy, multi-agent AI systems own their own behavior — agents can call wrong APIs, leak PII, exceed cost budgets, run infinite loops. Single point of failure if app-layer is the only check.',
    whyThisApproach: 'Declarative policies are auditable. Sidecar deployment keeps latency bounded. Three-layer defense (auth + content + data) covers the AI failure surface.',
    whenToUse: ['Production AI with execution authority', 'Multi-agent systems', 'Regulated tenants', 'Customer-facing AI features'],
    whenNotToUse: ['Read-only AI tools', 'Internal dev playgrounds', 'Synthetic data generation only'],
    input: 'Request + actor (user/agent) + target action + context (tenant, scope, payload)',
    process: [
      'OPA evaluates Rego rules → allow / deny / require-approval',
      'On allow: input guardrails (PII mask, prompt-injection detect)',
      'Forward to manager / worker',
      'On response: output guardrails (toxicity, hallucination, citation)',
      'Persist decision audit row with policy_version + correlation_id',
    ],
    output: 'Allowed-and-redacted request OR denial with reason. Audit row written either way.',
    alternatives: [
      { name: 'Hand-coded if-else policies', tradeoff: 'No abstraction; coupled to app code; not auditable' },
      { name: 'AWS IAM only', tradeoff: 'Vendor lock; cant express AI-specific (PII, toxicity)' },
      { name: 'Cedar (AWS)', tradeoff: 'Newer; less mature ecosystem; cleaner DSL than Rego' },
      { name: 'Built-in framework guardrails (NeMo)', tradeoff: 'Easier; less portable; weaker for non-LLM rules' },
    ],
    challenges: [
      'Rule conflicts at scale',
      'Latency overhead per request',
      'Policy version drift',
      'Over-restriction blocking valid requests',
      'Audit chain integrity at high QPS',
    ],
    edgeCases: [
      { case: 'OPA sidecar down', solution: 'Fail-closed: reject all privileged ops; alert SRE; degraded mode for non-privileged' },
      { case: 'Conflicting tenant + feature policies', solution: 'Explicit precedence: deny-overrides-allow; document in ADR' },
      { case: 'Guardrail false positive blocks valid query', solution: 'Per-tenant override + audit row with justification' },
      { case: 'New regulation lands mid-quarter', solution: 'Add policy + version bump; deploy via canary; monitor decision shift' },
    ],
    failureModes: [
      { mode: 'Policy bypass via hot path optimization', detect: 'Drill: hits hot path with deny rule, expects 403', recover: 'Revert; restore middleware chain' },
      { mode: 'Audit chain breaks (decision not logged)', detect: 'Hash-chain integrity drill', recover: 'Recompute chain; investigate gap' },
      { mode: 'OPA evaluation latency spike', detect: 'p99 OPA eval > 50ms', recover: 'Profile rules; cache common decisions; scale sidecar' },
    ],
    monitoring: ['OPA eval latency p50/p99', 'Per-policy allow / deny rate', 'Guardrail false-positive rate', 'Audit chain integrity'],
    testing: ['Drill: undersized actor → 403', 'Drill: PII probe → masked', 'Drill: prompt-injection → blocked', 'Drill: audit chain unbroken under load'],
    security: ['Policy versions signed in git', 'Audit hash-chained per tenant', 'PII never persisted unredacted', 'OPA bundle integrity verified at load'],
    scaling: ['Sidecar OPA per service pod', 'Cache common decisions in Redis', 'Batch audit writes via Kafka outbox'],
    maturity: {
      mvp: 'Hand-coded if-else gates; manual policy doc',
      production: 'OPA sidecar + Guardrails + Presidio + audit chain + drills',
      enterprise: 'Multi-tenant policy registry + dashboard + sampled review + tabletop exercises',
    },
    limitations: [
      'Rule-based systems miss novel attack vectors',
      'Latency overhead per request real',
      'Policy authoring requires expertise',
      'False positives erode trust',
    ],
    projectFit: [
      '/admin/guardrails/deep — input + output guardrails',
      '/admin/pii/deep — Presidio integration',
      '/admin/rbac/deep — three-layer authorization',
      'mcp/tests/drill_policy_*.py — per-rule drills',
    ],
    interviewLine: 'Policy is the non-negotiable runtime gate. OPA + Guardrails + Presidio combined. Without it, the AI system owns its own behavior — which is risk.',
    implementationSteps: [
      { step: 'OPA sidecar', logic: 'Per-request authorization via Rego rules; sub-10ms eval.' },
      { step: 'Guardrails AI', logic: 'Input/output validation: prompt-injection, PII, toxicity, citation-deadline.' },
      { step: 'Presidio PII masker', logic: 'Pre-storage + pre-external-send PII redaction.' },
      { step: 'Hash-chained audit', logic: 'Every decision logged per tenant; tamper-evident.' },
      { step: 'Version-pinned rules', logic: 'Rego + Guardrails configs in git; canary-deployed.' },
      { step: 'Drill known attacks', logic: 'OWASP LLM Top 10 + custom corpora; each must be caught.' },
    ],
    codeExample: {
      language: 'rego',
      code: `# policy/agent_actions.rego — declarative tool-call authorization
package documind.agent

# Default deny
default allow = false

# Allow if scope present + not in business-hours sensitive ops
allow {
    input.action == "hr.create_user"
    "hr:write" in input.actor.scopes
    input.tenant_id == input.actor.tenant_id
    not sensitive_op_outside_hours
}

allow {
    input.action == "doc.read"
    "docs:read" in input.actor.scopes
    input.resource.tenant_id == input.actor.tenant_id
}

# Sensitive ops gated to business hours UTC
sensitive_op_outside_hours {
    input.action in {"hr.create_user", "ops.purge_tenant"}
    h := time.clock([time.now_ns(), "UTC"])[0]
    h < 9
}

sensitive_op_outside_hours {
    input.action in {"hr.create_user", "ops.purge_tenant"}
    h := time.clock([time.now_ns(), "UTC"])[0]
    h >= 18
}

# Audit: log every decision (allow OR deny)
audit_log[entry] {
    entry := {
        "decision": allow,
        "action": input.action,
        "actor": input.actor.id,
        "reason": rationale,
    }
}`,
    },
    realUseCase: 'Customer onboarded with strict compliance: no agent action outside 9-18 UTC, all PII pre-masked, every decision audited. OPA Rego rules enforced time check; Guardrails AI rejected 3 prompt-injection attempts week 1; Presidio masked patient names before LLM saw them. Hash-chained audit verified by drill_policy_seal weekly. Without policy layer, customer would not have signed.',
    prosCons: {
      pros: ['Declarative rules in version control', 'Sub-50ms decision latency', 'Tamper-evident audit', 'Independent of model/agent code'],
      cons: ['Rego learning curve', 'Sidecar adds operational surface', 'Rule conflicts need careful diff'],
    },
    comparison: {
      left: 'Hardcoded policy in service code',
      right: 'OPA + Guardrails + Presidio (this)',
      rows: [
        { aspect: 'Rule changes', left: 'Service redeploy', right: 'Rego push, no service deploy' },
        { aspect: 'Auditability', left: 'Mixed with code', right: 'Hash-chained per tenant' },
        { aspect: 'Cross-team review', left: 'Code review', right: 'Security + compliance review Rego' },
        { aspect: 'Latency', left: '< 1ms (in-process)', right: '~10-50ms (sidecar)' },
      ],
    },
    solutions: [
      { problem: 'Compliance demanding declarative rules', solution: 'OPA Rego in git; canary-deployed' },
      { problem: 'Prompt injection reaching LLM', solution: 'Guardrails AI input validator' },
      { problem: 'PII leaking to external services', solution: 'Presidio at egress' },
      { problem: 'Audit reconstruction post-incident', solution: 'Hash-chained per-tenant log' },
    ],
    bestPractices: {
      do: ['Version-pin all rules', 'Canary deploy policy changes', 'Drill OWASP LLM Top 10', 'Hash-chain audit per tenant'],
      avoid: ['Hardcoded policy in service code', 'Skipping the audit hash chain', 'Deploying policy without canary'],
      optimize: ['Rule cache per tenant for hot path', 'Sidecar pool with health checks'],
    },
    antiPatterns: ['Hardcoded policy', 'No audit chain', 'No drill', 'Service-side PII masking only'],
    testTypes: ['Drill OWASP LLM Top 10 against Guardrails', 'Drill OPA rules per scope/role', 'Drill Presidio PII recall', 'Drill audit chain seal'],
    testScenarios: [
      { scenario: 'Out-of-hours sensitive op', expected: 'OPA denies; audit row written' },
      { scenario: 'Prompt injection in user query', expected: 'Guardrails blocks; user sees friendly error' },
      { scenario: 'PII in payload to external service', expected: 'Presidio masks before egress' },
      { scenario: 'Audit chain broken', expected: 'drill_policy_seal red; investigation triggered' },
    ],
    testData: [
      { type: 'OPA rule fixture', example: 'Rego + input fixtures × allow/deny labels' },
      { type: 'Guardrails attack corpus', example: 'OWASP LLM Top 10 + custom red-team set' },
      { type: 'Presidio golden set', example: '500 docs with labeled PII; recall ≥ 99%' },
    ],
    debuggingChecklist: [
      'OPA always denying? Check default allow and rule logic',
      'Guardrails false-positive? Threshold tune; per-tenant override',
      'Presidio missing PII? Custom recognizer for domain terms',
      'Audit chain failing? Hash mismatch; investigate write path',
    ],
    productionIssues: [
      { issue: 'OPA rule rolled out broke all writes', rootCause: 'No canary; hot push. Added canary stage + smoke test.' },
      { issue: 'Guardrails blocked legitimate medical query', rootCause: 'Toxicity threshold too tight. Per-tenant override added.' },
    ],
    performance: ['OPA decision: ~5-15ms p95', 'Guardrails: ~20-50ms p95', 'Presidio: ~10-30ms p95', 'Audit write: async ~10ms'],
    costConsiderations: ['Sidecar compute: shared across services', 'OPA + Guardrails open-source', 'Presidio open-source'],
    observability: ['Trace per decision; metrics per rule', 'Audit hash-chain verified weekly', 'Policy version in every audit row'],
    metrics: [
      { name: 'documind_policy_decision_total{rule,outcome}', example: 'Counter; spike on deny may indicate attack' },
      { name: 'documind_guardrail_block_total{rule,tenant}', example: 'Counter; per-tenant attack visibility' },
      { name: 'documind_policy_eval_latency_seconds{component}', example: 'Histogram p95 < 50ms' },
    ],
    tradeoffs: [
      { decision: 'Rego vs hardcoded', tradeoff: 'Rego: declarative + reviewable; learning curve' },
      { decision: 'Sidecar vs in-process', tradeoff: 'Sidecar: independent deploy; more latency' },
    ],
    decisionMatrix: [
      { option: 'OPA + Guardrails + Presidio (this)', whenToUse: 'Multi-tenant SaaS with compliance + agent features' },
      { option: 'Hardcoded policy', whenToUse: 'Internal tool; trusted users; simple shape' },
    ],
    starStory: {
      situation: 'Compliance-bound customer required declarative policy + per-decision audit + PII masking before sign.',
      task: 'Stand up policy layer that supports per-tenant variations + zero-downtime rule updates.',
      action: 'Deployed OPA + Guardrails + Presidio sidecars. Rules in git. Canary stage. Hash-chained audit per tenant. drill_policy_owasp_llm + drill_policy_pii_recall + drill_policy_audit_seal in CI.',
      result: 'Customer signed. Zero policy-layer P0 in 6 months. Pattern adopted by 2 other compliance customers.',
    },
    interviewTraps: ['Hardcoded policy in service code', 'No audit hash chain', 'No canary on rule deploys', 'Skipping the OWASP drill'],
    finalScript: 'Policy is the layer that turns AI into something an enterprise can adopt. OPA enforces per-request authorization via declarative Rego rules. Guardrails AI validates inputs (prompt-injection, PII) and outputs (toxicity, hallucination, citation-deadline). Presidio masks PII before storage or external send. All three are sidecar-deployed for sub-50ms eval. Every decision writes a hash-chained audit row per tenant. Rules are version-pinned in git, reviewed by security + compliance, deployed via canary. Without this, the manager (Paperclip) and workers (OpenClaw) own the platform\'s behavior. With it, agents have hands but the brain is steerable.',
  },

  // ---- 2. Paperclip (Manager) ----
  {
    slug: 'paperclip-manager',
    title: '2. Paperclip — AI manager (orchestration layer)',
    status: 'partial',
    coreConcept: 'The orchestration brain. Decomposes user goals into tasks, assigns to agent workers, tracks cost + progress, manages multi-agent coordination. Plans but does not execute — execution is delegated to OpenClaw workers.',
    oneLiner: 'Paperclip = brain (manager); breaks tasks; coordinates workers; tracks cost. NEVER executes alone.',
    businessContext: 'Complex AI tasks (multi-step research, multi-source data fusion, agent-driven workflows) need decomposition + coordination. Without a manager layer, every request is a one-shot LLM call without state — fragile + opaque.',
    fiveW: {
      what: 'A planner + scheduler + cost-tracker for multi-agent task execution. Receives goals, decomposes into subtasks, assigns to workers, aggregates results.',
      why: 'Multi-step tasks need state + coordination + budget. Single-shot LLM calls miss this; manual task graphs miss the LLM\'s decomposition skill.',
      where: 'Sits below Policy layer, above worker pool. Each tenant has its own manager instance (or shared with isolation).',
      when: 'Multi-step user goals; agent-driven workflows; tasks with budget ceilings; cross-system orchestration.',
      who: 'AI/ML team owns Paperclip prompts. Platform owns runtime. Each consuming feature defines its goal schema.',
    },
    interview30s: 'Paperclip is the manager layer. It receives a user goal, breaks it into subtasks via an LLM-based planner, assigns each to an OpenClaw worker, aggregates results, and tracks token + cost + time budget. The non-negotiable discipline is the kill-switch: max-depth, max-wall-clock, max-cost. Without these, agent loops run unbounded. Every decision (decompose, assign, retry, abort) writes a decision audit row.',
    coreBuildingBlocks: [
      'Goal schema — Pydantic model for incoming user goals',
      'Planner — LLM-driven task decomposition',
      'Scheduler — assigns subtasks to OpenClaw workers',
      'Cost tracker — tokens + USD + wall-clock per task',
      'State machine — task: pending → planning → assigned → running → done | failed | aborted',
      'Kill-switch — max-depth + max-cost + max-time enforced via Agent CB',
      'Result aggregator — merges worker outputs into final response',
    ],
    architectureRelevance: {
      backend: 'FastAPI service with /goal endpoint. Pydantic schema validates input. asyncpg persists task state.',
      rag: 'Decomposes a "research X across sources" goal into per-source retrieval tasks; aggregates with citation merge.',
      ai: 'LLM-driven decomposition is itself bounded by Cognitive CB. Decomposition prompt is versioned in registry.',
      microservices: 'manager-svc + worker-pool-svc deployed separately. mTLS between. Per-tenant rate-limit at gateway.',
    },
    hld: `flowchart TB
  USR[User goal] --> POL[Policy layer]
  POL --> MGR[manager-svc Paperclip]
  subgraph mblock["Paperclip components"]
    PLAN[Planner LLM]
    SCH[Scheduler]
    COST[Cost tracker]
    AGG[Aggregator]
  end
  MGR --> PLAN
  PLAN --> SCH
  SCH --> WRK[Worker pool OpenClaw]
  WRK --> AGG
  AGG --> COST
  COST --> MGR
  MGR --> RES[Final response]`,
    flowchart: `flowchart LR
  G[Goal + budget] --> P[Plan via LLM]
  P --> T[Task graph]
  T --> S[Schedule subtasks]
  S --> W[Workers execute]
  W --> R[Results back]
  R --> A{Budget OK and done}
  A -->|yes| AGR[Aggregate response]
  A -->|no| LOOP[Refine plan or abort]
  LOOP --> S`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant POL as Policy
  participant MGR as Paperclip
  participant LLM as Planner LLM
  participant W as Worker pool
  U->>POL: goal
  POL->>MGR: forward
  MGR->>LLM: decompose
  LLM-->>MGR: task graph
  loop per subtask
    MGR->>W: assign + budget
    W-->>MGR: result + cost
  end
  MGR->>MGR: aggregate
  MGR-->>U: response + total cost`,
    coreLayers: [
      { layer: 'Goal layer', responsibility: 'Pydantic schema for incoming goals; tenant + actor + budget + deadline.' },
      { layer: 'Planner layer', responsibility: 'LLM-driven decomposition. Prompt versioned. Output validated against task schema.' },
      { layer: 'Scheduler layer', responsibility: 'Assigns tasks to OpenClaw workers. Tracks dependencies, parallelism, retries.' },
      { layer: 'Cost layer', responsibility: 'Tokens + USD + wall-clock per task. Aggregated into goal-level budget.' },
      { layer: 'Kill-switch', responsibility: 'Agent CB: max-depth, max-cost, max-time. Hard-stop on breach.' },
      { layer: 'Audit layer', responsibility: 'Every plan / assign / retry / abort decision logged with correlation_id.' },
    ],
    problem: 'Single-shot LLM calls miss multi-step state, cost tracking, and coordination. Manual orchestration misses LLM\'s decomposition skill.',
    whyThisApproach: 'LLM-driven planning is fast and flexible. Explicit cost + budget keeps agents bounded. Worker delegation keeps the manager itself simple.',
    whenToUse: ['Multi-step user goals', 'Cross-source research', 'Agent-driven workflows', 'Budget-constrained tasks'],
    whenNotToUse: ['Single-shot Q&A', 'Pure retrieval-only RAG', 'Cost-extreme low-latency paths'],
    input: 'User goal + budget (token + USD + wall-clock) + tenant + actor',
    process: [
      'Validate goal schema',
      'Plan via LLM (decompose into task graph)',
      'Schedule subtasks to OpenClaw workers',
      'Track cost + time per subtask',
      'Aggregate results; refine if needed',
      'Return final response with cost breakdown',
    ],
    output: 'Final response + cost breakdown + decision audit chain.',
    alternatives: [
      { name: 'LangChain agents', tradeoff: 'Easier; opinionated; weaker on cost tracking + governance' },
      { name: 'AutoGPT-style loops', tradeoff: 'Fully autonomous; harder to bound; security risk' },
      { name: 'Hand-coded task graphs', tradeoff: 'Predictable; loses LLM decomposition; brittle on novel goals' },
      { name: 'CrewAI', tradeoff: 'Multi-agent native; younger ecosystem' },
    ],
    challenges: [
      'Task decomposition quality',
      'Agent coordination failure',
      'Cost tracking accuracy at scale',
      'Conflicting tasks between workers',
      'Infinite loops in plan refinement',
    ],
    edgeCases: [
      { case: 'Planner generates infinite-loop graph', solution: 'Agent CB max-depth + max-time hard-stop' },
      { case: 'Two workers conflict on shared resource', solution: 'Distributed lock + retry with backoff' },
      { case: 'Budget exceeded mid-task', solution: 'Soft-throttle (cheaper model); hard-block at ceiling' },
      { case: 'Worker dies mid-execution', solution: 'Saga compensation; replay from last checkpoint' },
    ],
    failureModes: [
      { mode: 'Planner prompt regression', detect: 'Decomposition quality drops on benchmark', recover: 'Roll back prompt version; re-eval' },
      { mode: 'Cost overrun on hot tenant', detect: 'Token CB throttle/block events', recover: 'Tier-aware budget + alert tenant admin' },
      { mode: 'State machine drift', detect: 'Drill: invalid transition rejected', recover: 'Restore from event-sourced log' },
    ],
    monitoring: ['Per-goal latency p95', 'Per-goal token + USD cost', 'Decomposition quality (sampled review)', 'Worker assignment fan-out', 'Agent CB open events'],
    testing: ['Drill: budget exceeded → hard block', 'Drill: max-depth breach → abort', 'Drill: worker death → saga compensates', 'Eval: decomposition quality on benchmark goals'],
    security: ['Goal schema validated; reject unknown fields', 'Per-tenant rate-limit + budget', 'No raw PII in plan prompts (Presidio mask first)', 'Audit chain hash-chained'],
    scaling: ['Stateless manager; horizontal scale', 'State in Postgres + Redis cache', 'Worker pool independently scaled'],
    maturity: {
      mvp: 'Single goal type; hand-tuned decomposition prompt',
      production: 'Multi-goal + budget + Agent CB + decision audit',
      enterprise: 'Per-tenant goal registry + decomposition eval + cost dashboard',
    },
    limitations: [
      'Early-stage ecosystem',
      'Decomposition quality depends on LLM',
      'Coordination overhead at high parallelism',
    ],
    projectFit: [
      'manager-svc / app/services/planner.py',
      'libs/py/documind_core/breakers.py — Agent-Loop CB',
      'governance.task_audit — decision chain',
      'mcp/tests/drill_paperclip_*.py — manager drills',
    ],
    interviewLine: 'Paperclip is the manager layer — plans but does not execute. The kill-switch (max-depth, max-cost, max-time) is non-negotiable. Without it, agent loops run unbounded.',
    implementationSteps: [
      { step: 'Receive goal', logic: 'User goal + tenant_id + correlation_id; create plan_id.' },
      { step: 'LLM planner decomposes', logic: 'Goal → task graph; nodes are tool calls or sub-goals.' },
      { step: 'Assign tasks to workers', logic: 'Per-task scope check; route to OpenClaw worker.' },
      { step: 'Track cost + depth + time', logic: 'Agent CB enforces max_depth + max_cost + max_wall_clock.' },
      { step: 'Event-sourced state', logic: 'pending → planning → running → done | failed | aborted.' },
      { step: 'Aggregate + return', logic: 'Worker results combined; final answer + citations + cost.' },
      { step: 'Hard-stop on kill-switch', logic: 'Breach → audit + abort; no silent overrun.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/agent-svc/app/paperclip.py — manager with kill-switch
from libs.py.documind_core.agent_cb import AgentCircuitBreaker
from libs.py.documind_core.audit import audit_chain_write

class Paperclip:
    def __init__(self, planner, dispatcher, audit, max_depth=8,
                 max_cost_usd=2.0, max_wall_clock_s=120):
        self._planner = planner
        self._dispatcher = dispatcher
        self._audit = audit
        self._cb = AgentCircuitBreaker(
            max_depth=max_depth,
            max_cost_usd=max_cost_usd,
            max_wall_clock_s=max_wall_clock_s,
        )

    async def execute(self, goal: str, tenant_id: str, correlation_id: str):
        plan_id = uuid.uuid4().hex
        await self._set_state(plan_id, "planning")
        plan = await self._planner.decompose(goal, tenant_id)
        await self._set_state(plan_id, "running")

        results = []
        for task in plan.tasks:
            self._cb.check()  # raises AgentBudgetExhausted if breached
            try:
                r = await self._dispatcher.dispatch(task, tenant_id, correlation_id)
                self._cb.record(cost_usd=r.cost_usd, depth=task.depth)
                results.append(r)
            except AgentBudgetExhausted:
                await self._set_state(plan_id, "aborted")
                await audit_chain_write(
                    tenant_id=tenant_id,
                    actor_id="paperclip",
                    action="agent_aborted_budget",
                    payload={"plan_id": plan_id, "reason": "budget"},
                )
                raise

        await self._set_state(plan_id, "done")
        return aggregate(results)`,
    },
    realUseCase: 'Customer asked agent: "summarize my last 5 incidents and create a postmortem doc". Planner decomposed: incident-list (1 tool call) → fetch-incidents-detail (5 calls) → write-postmortem (1 LLM call). Agent CB tracked depth (1+5+1=7, under max_depth=8) and cost ($0.45, under $2). All worked. Without kill-switch, an LLM that misinterpreted "summarize all incidents" could have looped through 1000 incidents and burned $50.',
    prosCons: {
      pros: ['Kill-switch makes agent loops bounded', 'Event-sourced state enables replay', 'Per-task scope check prevents privilege creep', 'Cost tracking integrates with Token CB'],
      cons: ['Planner LLM cost adds to per-request total', 'State machine complexity', 'Aggregation logic per task type'],
    },
    comparison: {
      left: 'Naive ReAct agent loop',
      right: 'Paperclip with kill-switch (this)',
      rows: [
        { aspect: 'Loop bound', left: 'Soft (max iterations)', right: 'Hard (depth + cost + time)' },
        { aspect: 'State recovery', left: 'Lost on crash', right: 'Event-sourced replay' },
        { aspect: 'Cost predictability', left: 'Surprise', right: 'Bounded by max_cost' },
        { aspect: 'Audit', left: 'Logs only', right: 'Hash-chained per decision' },
      ],
    },
    solutions: [
      { problem: 'Agent infinite loop', solution: 'Agent CB max_depth + max_wall_clock' },
      { problem: 'Cost runaway', solution: 'Agent CB max_cost_usd; hard-stop on breach' },
      { problem: 'Crash mid-execution', solution: 'Event-sourced state; replay from last checkpoint' },
      { problem: 'Worker conflict on shared resource', solution: 'Distributed lock + retry with backoff' },
    ],
    bestPractices: {
      do: ['Kill-switch always (depth + cost + time)', 'Event-sourced state for replay', 'Per-task scope check', 'Audit every decision', 'Drill kill-switch enforcement'],
      avoid: ['Naive ReAct loop without budget', 'In-memory state (lost on crash)', 'Per-call scope decisions skipped', 'Silent overruns'],
      optimize: ['Cache planner output for repeated goals', 'Batched worker dispatch where independent', 'Tiered model routing (cheaper for simple steps)'],
    },
    antiPatterns: ['No kill-switch', 'In-memory state', 'No per-task scope check', 'Silent budget overruns', 'No drill on agent loop'],
    testTypes: ['Drill: agent forced to loop → CB hard-stops', 'Drill: cost breach → abort + audit', 'Drill: state replay after crash', 'Drill: per-task scope check enforced'],
    testScenarios: [
      { scenario: 'Agent reaches max_depth=8', expected: 'CB hard-stops; state=aborted; audit row' },
      { scenario: 'Cost reaches max_cost_usd=2', expected: 'Same: hard-stop + audit + 429 to user' },
      { scenario: 'Wall-clock max_wall_clock_s=120', expected: 'Same' },
      { scenario: 'Crash mid-plan', expected: 'Replay from event-sourced state; idempotent' },
    ],
    testData: [
      { type: 'Loop trigger fixture', example: 'Mock tool that always returns "call yourself again"' },
      { type: 'Cost-runaway fixture', example: 'Tool that returns large outputs requiring expensive LLM' },
      { type: 'Crash recovery fixture', example: 'Kill paperclip mid-plan; verify replay' },
    ],
    debuggingChecklist: [
      'Agent stuck? Check CB state + depth/cost/time counters',
      'Plan replay broken? Event log integrity',
      'Worker conflict? Distributed lock granularity',
      'Cost off? Token tracking per task',
    ],
    productionIssues: [
      { issue: 'Agent ran 8h burning $400', rootCause: 'Kill-switch existed but feature flag off in prod for "demo"' },
      { issue: 'Plan replay corrupted', rootCause: 'Event log non-idempotent; same event replayed twice. Added idempotency key per event.' },
    ],
    performance: ['Plan decompose: ~1-3s LLM call', 'Per-task dispatch: ~50-200ms', 'State transition: ~10ms PG write', 'CB check: O(1) ~0.5μs'],
    costConsiderations: ['Planner LLM: ~$0.01-0.05 per plan', 'Worker calls: variable', 'State storage: small per plan'],
    observability: ['Trace per plan with all task hops', 'Metrics: agent_aborted{reason}, plan_cost_usd{tenant}', 'Logs: structured per state transition'],
    metrics: [
      { name: 'documind_agent_aborted_total{tenant,reason}', example: 'Counter; reason=budget|depth|time|crash' },
      { name: 'documind_plan_cost_usd{tenant,p}', example: 'Histogram; p95 trend per tenant' },
      { name: 'documind_plan_state_seconds{tenant,from,to}', example: 'Histogram; transition latency' },
    ],
    tradeoffs: [
      { decision: 'Kill-switch tightness', tradeoff: 'Tight = bounded + may abort legitimate; loose = costly' },
      { decision: 'Event-sourced vs in-memory', tradeoff: 'Sourced: replay; in-memory: faster but lossy' },
    ],
    decisionMatrix: [
      { option: 'Paperclip with kill-switch (this)', whenToUse: 'Agent features in production' },
      { option: 'Naive ReAct', whenToUse: 'Demo / hackathon' },
    ],
    starStory: {
      situation: 'First agent feature in production; week 1 had a $400 token bill from one stuck loop.',
      task: 'Make agent loops bounded + auditable + recoverable.',
      action: 'Wrote Agent CB with depth + cost + time. Event-sourced plan state. Per-task scope check + audit. drill_paperclip_kill_switch in CI.',
      result: 'Zero billing surprises since. Agent feature scaled to 5 customers. Pattern documented as ADR-009.',
    },
    interviewTraps: ['No kill-switch', 'In-memory state', 'Silent budget overruns', 'No per-task scope check'],
    finalScript: 'Paperclip is the orchestration brain. It receives a user goal, decomposes via an LLM planner into a task graph, assigns subtasks to OpenClaw workers, tracks token + USD + wall-clock cost, and aggregates results into a final response. The state machine is event-sourced: pending → planning → assigned → running → done | failed | aborted. The kill-switch is non-negotiable — Agent Circuit Breaker enforces max-depth, max-cost, max-wall-clock; on breach, hard-stop with audit. Every decision is logged with correlation_id. Deployed stateless; state in Postgres with Redis cache. Without the kill-switch, agent loops run unbounded; with it, the system is bounded + auditable.',
  },

  // ---- 3. OpenClaw (Workers) ----
  {
    slug: 'openclaw-workers',
    title: '3. OpenClaw — execution agents (worker layer)',
    status: 'partial',
    coreConcept: 'The hands that touch real systems. Calls APIs, runs scripts, executes workflows. Always wrapped in policy + sandbox + audit. NEVER trusted to act unilaterally.',
    oneLiner: 'OpenClaw = hands (workers); executes real-world actions; only safe when wrapped with policy + sandbox + audit.',
    businessContext: 'Manager layer plans; somebody has to execute. OpenClaw workers are the execution arm — they call external APIs, send messages, mutate data. Without sandboxing they are the highest-risk component.',
    fiveW: {
      what: 'A pool of execution agents that perform tool calls, API requests, file operations, database writes. Each action is policy-gated + audited.',
      why: 'Plans without execution are useless; execution without policy is unsafe. Workers are the place where AI hits real-world side effects.',
      where: 'Worker pool deployed in isolated namespace with restricted network egress + filesystem. Each worker takes one subtask at a time.',
      when: 'Always for any AI feature with execution authority. Mandatory pairing with Policy + Manager.',
      who: 'AI safety team owns sandboxing. Tool authors define per-tool permissions. Each subtask audited.',
    },
    interview30s: 'OpenClaw workers execute the actual side effects — API calls, DB writes, file operations. The discipline is layered: per-tool policy in OPA, per-call timeout, per-worker resource limits, per-action audit row. Workers run in restricted namespaces with egress allowlists. The non-negotiable test is a drill that pumps known bad inputs (wrong API, wrong tenant, oversized payload) and asserts each is rejected.',
    coreBuildingBlocks: [
      'Worker pool — restricted namespace; egress allowlist',
      'Tool registry — declared tools with input/output schemas + permissions',
      'Per-call sandbox — timeout, memory, network restriction',
      'Per-action audit — tool + input + output + actor + correlation_id',
      'Idempotency keys — safe retry on transient failure',
      'Rollback hooks — for compensable actions (saga step)',
    ],
    architectureRelevance: {
      backend: 'Workers are FastAPI services or sidecars. Each tool call goes through MCPClient with tenant_id required.',
      rag: 'Retrieval workers query Qdrant + Neo4j; rerank worker calls cross-encoder; citation worker resolves chunk → doc.',
      ai: 'LLM call workers go through Token CB. Cognitive CB on stream. Forbidden-pattern signal.',
      microservices: 'Workers stateless; assigned via Kafka task topic; results via Kafka result topic.',
    },
    hld: `flowchart TB
  MGR[Paperclip Manager] --> Q1[Task queue Kafka]
  Q1 --> POOL[OpenClaw worker pool]
  subgraph workers["Worker pool"]
    W1[Worker 1]
    W2[Worker 2]
    WN[Worker N]
  end
  POOL --> W1
  POOL --> W2
  POOL --> WN
  W1 --> POL[Per-call policy]
  W2 --> POL
  WN --> POL
  POL --> EXT[External APIs]
  W1 --> Q2[Result queue]
  W2 --> Q2
  WN --> Q2
  Q2 --> MGR`,
    flowchart: `flowchart LR
  T[Subtask + budget] --> A[Pick worker]
  A --> P[Per-call policy check]
  P -->|allow| E[Execute tool]
  P -->|deny| F[Fail + audit]
  E --> R{Result}
  R -->|success| AUD[Audit + return]
  R -->|fail| RT{Retry budget}
  RT -->|yes| E
  RT -->|no| ROLL[Rollback compensate]`,
    sequence: `sequenceDiagram
  autonumber
  participant MGR as Paperclip
  participant Q as Task queue
  participant W as Worker
  participant POL as Policy
  participant EXT as External API
  participant Aud as Audit
  MGR->>Q: enqueue subtask
  Q->>W: assign
  W->>POL: pre-call eval
  alt allowed
    W->>EXT: tool call with timeout
    EXT-->>W: result
    W->>Aud: log success
    W-->>MGR: result
  else denied
    W->>Aud: log denied
    W-->>MGR: error denied
  end`,
    coreLayers: [
      { layer: 'Pool layer', responsibility: 'Stateless worker replicas in restricted namespace. Auto-scale by queue depth.' },
      { layer: 'Tool registry', responsibility: 'Declared tools with input/output schemas + per-tool permissions in OPA.' },
      { layer: 'Sandbox layer', responsibility: 'Per-call timeout, memory cap, network egress allowlist, filesystem isolation.' },
      { layer: 'Idempotency layer', responsibility: 'X-Idempotency-Key on writes; persist 24h; replay on duplicate.' },
      { layer: 'Compensation layer', responsibility: 'Per-action rollback hook for saga compensation on partial failure.' },
      { layer: 'Audit layer', responsibility: 'Every tool call: input, output, actor, correlation_id, latency, cost.' },
    ],
    problem: 'Plans are theoretical. Real-world side effects need execution. Without sandboxing, workers can call wrong APIs, leak data, exceed budgets.',
    whyThisApproach: 'Stateless pool scales horizontally. Per-call policy gating + sandbox + audit gives defense in depth. Idempotency makes retries safe.',
    whenToUse: ['Multi-step agent workflows', 'Tool-using AI features', 'Any AI with external API access', 'Compensable transactional flows'],
    whenNotToUse: ['Pure read-only Q&A', 'Synthetic data tests', 'No-side-effect summarization'],
    input: 'Subtask (tool + args + budget) + correlation_id from manager',
    process: [
      'Pick worker from pool (queue-based)',
      'Per-call policy eval (OPA + Guardrails)',
      'Execute tool with timeout + sandbox',
      'On success: log audit row; return result',
      'On failure: retry within budget OR rollback via compensation',
    ],
    output: 'Tool result OR error envelope. Audit row per call.',
    alternatives: [
      { name: 'LangChain tools', tradeoff: 'Easier; weaker on per-call policy gating + audit' },
      { name: 'AutoGen agents', tradeoff: 'Multi-agent native; harder to bound execution' },
      { name: 'Hand-coded tool functions', tradeoff: 'Predictable; loses agent flexibility' },
      { name: 'AWS Step Functions + Lambda', tradeoff: 'Managed; vendor lock; weak AI-specific governance' },
    ],
    challenges: [
      'Safe execution at scale',
      'API failure handling',
      'State management across retries',
      'Tool permission proliferation',
      'Sandbox escape if config drifts',
    ],
    edgeCases: [
      { case: 'Worker calls wrong API endpoint', solution: 'Tool registry validates URL allowlist; OPA denies unknown' },
      { case: 'External API returns malformed response', solution: 'Pydantic validates; raise ExternalServiceError; saga compensates' },
      { case: 'Sandbox escape attempt', solution: 'gVisor / firecracker isolation; egress allowlist; alert on policy violation' },
      { case: 'Two workers race on same resource', solution: 'Distributed lock; idempotency key; one succeeds, one no-ops' },
    ],
    failureModes: [
      { mode: 'Worker calls deprecated API', detect: 'Tool registry version check', recover: 'Block deploy; update registry; re-deploy' },
      { mode: 'Idempotency store down', detect: 'Cache write failure', recover: 'Fail-closed: reject writes; alert' },
      { mode: 'Compensation hook missing', detect: 'Drill: forced failure leaves dirty state', recover: 'Add compensation; replay from log' },
    ],
    monitoring: ['Per-tool latency p95', 'Per-tool error rate', 'Sandbox violation events', 'Idempotency replay rate', 'Worker queue depth'],
    testing: ['Drill: wrong API endpoint blocked', 'Drill: oversized payload rejected', 'Drill: sandbox egress allowlist holds', 'Drill: idempotency replay returns cached'],
    security: ['Per-tool OPA policy', 'Sandbox isolation (gVisor / firecracker)', 'Network egress allowlist', 'No PII in audit details without redact_pii'],
    scaling: ['Stateless pool; auto-scale on queue depth', 'Per-tool circuit breaker', 'Backpressure via queue length'],
    maturity: {
      mvp: 'Single-worker; in-process execution',
      production: 'Pool + sandbox + per-call policy + audit + idempotency',
      enterprise: 'Multi-region pool + tool registry dashboard + automated permission review',
    },
    limitations: [
      'Security risk if sandbox config drifts',
      'Hard to debug across distributed workers',
      'Tool registry maintenance overhead',
    ],
    projectFit: [
      '/admin/mcp/deep — MCPClient/MCPServer wrappers',
      '/admin/breakers/deep — Agent-Loop CB',
      'libs/py/documind_core/idempotency.py',
      'mcp/tests/drill_openclaw_*.py — worker drills',
    ],
    interviewLine: 'OpenClaw workers are the hands. They execute real-world actions but only safe when wrapped with per-call policy + sandbox + audit. Stateless pool; auto-scale on queue depth.',
    implementationSteps: [
      { step: 'Sandboxed execution', logic: 'Restricted namespace + egress allowlist + memory cap + fs isolation.' },
      { step: 'Per-call OPA check', logic: 'Tool action + actor scope + tenant validated before execution.' },
      { step: 'Idempotency on write', logic: 'X-Idempotency-Key persisted; retry returns cached.' },
      { step: 'Audit row per call', logic: 'Input + output + actor + correlation_id + outcome.' },
      { step: 'Compensation hooks', logic: 'Saga rollback path defined per write tool.' },
      { step: 'Stateless pool + autoscale', logic: 'Queue depth driven; no per-worker state.' },
      { step: 'Drill: bad inputs rejected', logic: 'Wrong API / wrong tenant / oversized payload all blocked.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/agent-svc/app/openclaw_worker.py — sandboxed execution
from libs.py.documind_core.exceptions import ScopeDeniedError, IdempotencyConflict

class OpenClawWorker:
    def __init__(self, policy_client, idem_store, audit, sandbox):
        self._policy = policy_client
        self._idem = idem_store
        self._audit = audit
        self._sandbox = sandbox  # restricted namespace + egress allowlist

    async def execute(self, task: Task, ctx: TaskContext) -> ToolResult:
        # 1. Per-call OPA scope check
        decision = await self._policy.allow({
            "action": task.tool_name,
            "actor": {"id": ctx.actor_id, "scopes": ctx.scopes, "tenant_id": ctx.tenant_id},
            "resource": task.resource,
        })
        if not decision.allow:
            await self._audit.log_denial(task, ctx, reason=decision.rationale)
            raise ScopeDeniedError(decision.rationale)

        # 2. Idempotency on write
        if task.is_write and ctx.idempotency_key:
            cached = await self._idem.get(ctx.tenant_id, ctx.idempotency_key)
            if cached:
                if cached.payload_hash == task.payload_hash():
                    return cached.result
                raise IdempotencyConflict(ctx.idempotency_key)

        # 3. Sandboxed execution
        async with self._sandbox.scope(
            mem_mb=512, wall_clock_s=30,
            egress_allowlist=task.tool_egress_allowlist,
        ):
            try:
                result = await dispatch_tool(task)
            except Exception as e:
                await self._audit.log_failure(task, ctx, error=str(e))
                if task.compensation:
                    await task.compensation.execute(ctx)
                raise

        # 4. Persist idempotency + audit
        if task.is_write and ctx.idempotency_key:
            await self._idem.store(ctx.tenant_id, ctx.idempotency_key, task, result, ttl_h=24)
        await self._audit.log_success(task, ctx, result)
        return result`,
    },
    realUseCase: 'Agent task: "create JIRA ticket for incident X". OpenClaw worker: OPA check ("itsm:write" present + tenant matches), idempotency lookup (not seen), sandboxed call to JIRA with egress allowlist (only jira.com:443), audit row written. Same task replayed: idempotency hit, cached response returned, no duplicate ticket. Without sandbox, a malformed tool call could have hit any API; without idempotency, retry would have duplicated tickets.',
    prosCons: {
      pros: ['Sandbox bounds blast radius', 'Per-call OPA check prevents privilege creep', 'Idempotency prevents duplicate writes', 'Stateless pool auto-scales', 'Compensation enables saga rollback'],
      cons: ['Sandbox config per tool type', 'Per-call OPA adds latency (~10-30ms)', 'Compensation logic must be written + tested per tool'],
    },
    comparison: {
      left: 'Direct tool calls in agent code',
      right: 'OpenClaw sandboxed worker (this)',
      rows: [
        { aspect: 'Egress control', left: 'None — agent can call anywhere', right: 'Per-tool allowlist' },
        { aspect: 'Per-call scope check', left: 'In agent (mixed with logic)', right: 'OPA sidecar (declarative)' },
        { aspect: 'Idempotency', left: 'Per-tool ad hoc', right: 'Standard X-Idempotency-Key' },
        { aspect: 'Compensation', left: 'Often missing', right: 'Mandatory for writes' },
        { aspect: 'Auditability', left: 'Mixed', right: 'Per-call hash-chained' },
      ],
    },
    solutions: [
      { problem: 'Worker calls wrong API', solution: 'Sandbox egress allowlist per tool' },
      { problem: 'Privilege creep across tools', solution: 'Per-call OPA scope check' },
      { problem: 'Duplicate writes on retry', solution: 'X-Idempotency-Key + 24h replay store' },
      { problem: 'Partial-failure orphan state', solution: 'Compensation hooks per write tool' },
    ],
    bestPractices: {
      do: ['Sandbox every worker', 'Per-call OPA scope check', 'X-Idempotency-Key on writes', 'Compensation for write tools', 'Audit per call'],
      avoid: ['Workers without sandbox', 'Skipping per-call scope check', 'Per-tool ad-hoc idempotency', 'Missing compensation on writes'],
      optimize: ['Pool warm workers (avoid cold start)', 'Cache scope decisions per JWT', 'Async audit batch flush'],
    },
    antiPatterns: ['Worker without sandbox', 'No per-call scope check', 'Missing idempotency', 'No compensation', 'Stateful workers'],
    testTypes: ['Drill: wrong API call → sandbox blocks egress', 'Drill: wrong tenant → OPA denies', 'Drill: oversized payload → sandbox kills', 'Drill: idempotency replay → cached result', 'Drill: compensation runs on write failure'],
    testScenarios: [
      { scenario: 'Worker tries to call disallowed API', expected: 'Sandbox blocks; audit row noting denial' },
      { scenario: 'Worker called with wrong tenant_id', expected: 'OPA denies; ScopeDeniedError; audit row' },
      { scenario: 'Same idempotency key + payload', expected: 'Cached response returned; no duplicate' },
      { scenario: 'Write tool fails mid-execution', expected: 'Compensation runs; saga rolls back' },
    ],
    testData: [
      { type: 'Bad-egress fixture', example: 'Tool config that tries to call evil.example.com' },
      { type: 'Cross-tenant probe', example: 'JWT for tenant A used to call tool for tenant B' },
      { type: 'Idempotency replay fixture', example: 'Same key + same payload sent twice; verify cached' },
      { type: 'Compensation fixture', example: 'Write tool that fails after partial state; verify rollback' },
    ],
    debuggingChecklist: [
      'Worker stuck? Sandbox memory or wall-clock breach',
      'Tool denied? Compare task scopes to OPA rule',
      'Idempotency mismatch? Payload hash drift; check store TTL',
      'Compensation didn\'t run? Verify write tool registers it',
    ],
    productionIssues: [
      { issue: 'Tool stormed an external API + got rate-limited', rootCause: 'Per-tool concurrency limit missing. Added bounded semaphore per tool name.' },
      { issue: 'Saga compensation orphaned mid-flight on worker crash', rootCause: 'Compensation log not idempotent. Added compensation_id + replay safe path.' },
    ],
    performance: ['Per-call OPA: ~10-30ms p95', 'Sandbox spinup: ~50-200ms (warm pool)', 'Tool dispatch: variable per tool', 'Audit write: async ~10ms'],
    costConsiderations: ['Sandbox compute: shared pool', 'Idempotency store: ~1KB × keys/day × 24h', 'Compensation testing: ops time per write tool'],
    observability: ['Trace: per-call with task + scopes + outcome', 'Metrics: tool_call_total{tool,outcome}, sandbox_blocks_total', 'Audit: hash-chained per tenant'],
    metrics: [
      { name: 'documind_tool_call_total{tool,outcome}', example: 'Counter; per-tool success/fail rate' },
      { name: 'documind_sandbox_blocks_total{reason}', example: 'Counter; egress|memory|time blocks' },
      { name: 'documind_compensation_runs_total{tool,outcome}', example: 'Counter; spike means write-tool failures' },
      { name: 'documind_idempotency_replay_total{outcome}', example: 'Counter; hit ratio' },
    ],
    tradeoffs: [
      { decision: 'Sandbox tightness', tradeoff: 'Tight = bounded; tools may break legitimate calls' },
      { decision: 'OPA per-call vs cached', tradeoff: 'Per-call: fresh; cached: faster' },
      { decision: 'Idempotency store TTL', tradeoff: 'Long: more retry-safe; storage cost' },
    ],
    decisionMatrix: [
      { option: 'OpenClaw sandboxed worker (this)', whenToUse: 'Agent features touching external systems' },
      { option: 'Direct tool calls in agent code', whenToUse: 'Demo / hackathon / single-user tool' },
    ],
    starStory: {
      situation: 'Agent feature shipped without sandboxing; first month had 2 incidents of tools calling wrong APIs.',
      task: 'Standardize worker execution: sandbox + OPA + idempotency + audit.',
      action: 'Built OpenClawWorker class. Per-call OPA scope check. Sandbox with egress allowlist + memory cap + wall-clock. X-Idempotency-Key on writes. Compensation hooks. drill_openclaw_bad_egress + drill_openclaw_idempotency in CI.',
      result: 'Zero "tool called wrong API" incidents since. Pattern adopted across 8 worker types. ADR-010 documents the contract.',
    },
    interviewTraps: ['No sandbox', 'No per-call scope check', 'Missing idempotency on writes', 'No compensation hooks', 'Stateful workers'],
    finalScript: 'OpenClaw workers are the execution arm. They run in a restricted namespace with egress allowlists, per-call timeouts, memory caps, and filesystem isolation. Each tool call passes through OPA for per-tool permission check, executes with budget, and writes an audit row with input + output + actor + correlation_id. Writes use X-Idempotency-Key for safe retry. Compensation hooks enable saga rollback on partial failure. The pool is stateless; auto-scaled on queue depth. Without sandboxing, workers can call wrong APIs and leak data; with it, they are bounded + auditable. The non-negotiable test is a drill that pumps known bad inputs — wrong API, wrong tenant, oversized payload — and asserts each is rejected before reaching the external system.',
  },
];

export default function AiOrchestrationDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">AI Orchestration — Deep Dive</h1>
        <p className="design-areas-sub">
          Three-layer architecture for multi-agent AI systems:
          <strong> Policy (rules) → Manager (Paperclip) → Workers (OpenClaw)</strong>.
          Each layer is independently bounded; combined they ship enterprise-grade AI.
        </p>
        <p className="design-areas-sub" style={{ fontStyle: 'italic' }}>
          🧠 Brain (Paperclip) plans · ✋ Hands (OpenClaw) execute · 🛡️ Rules (Policy) gate.
          Without all three: only Paperclip = no execution; only OpenClaw = unsafe; without
          policy = uncontrollable risk.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/guardrails/deep', label: 'Guardrails (in/out/behavior)', why: 'OPA + Presidio + safety filter form the policy layer of orchestration; uncontrolled = uncontrollable risk' },
          { href: '/admin/llmops/deep', label: 'LLMOps (prompt + model + eval registry)', why: 'orchestrator routes via versioned prompt + model; cost dashboards observable per orchestration step' },
          { href: '/admin/tracing/deep', label: 'Baggage across orchestrator', why: 'planner → workers chain carries baggage.tenant_id; one Jaeger query covers the full plan + tool calls' },
          { href: '/admin/security/deep#owasp-stride-ai-threats', label: 'A15 excessive agency', why: 'tool-call permission boundaries + scope-grant log = the excessive-agency control' },
          { href: '/admin/checklist/deep#lifecycle-checklist', label: '§10 AI checklist row', why: 'orchestrator goes through the same eval gate + cost budget + fallback model rules as any AI feature' },
        ]}
      />
    </div>
  );
}
