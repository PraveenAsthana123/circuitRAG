'use client';

/**
 * LLMOps deep-dive — interview-grade explanations for each LLMOps
 * capability per the user's 8-lens template:
 *
 *   1. Core concept (one sentence)
 *   2. 5W (what / why / who / when / where)
 *   3. Input → Process → Output
 *   4. Flowchart (mermaid)
 *   5. Sequence diagram (mermaid)
 *   6. Challenges + Solutions
 *   7. Edge cases + Solutions
 *   8. Limitations + Interview line
 *
 * Each capability also lists current state (shipped / partial / open)
 * and "next evolution" so the page reads as a coherent maturity story.
 *
 * Static content. Mermaid diagrams render same-origin via the
 * self-hosted /mermaid.min.js asset (commit f9ea6fc).
 */

import Mermaid from '../../../../components/Mermaid';
import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic as MasterTopic } from '../../../../components/UniversalDeepDive';

const LLMOPS_MASTER_SUMMARY: MasterTopic = {
  slug: 'llmops-platform-summary',
  title: 'LLMOps platform — master interview brief',
  status: 'shipped',
  coreConcept: 'LLMOps is the operational discipline that turns LLM-based systems from demos into production: model + prompt + retrieval + agent versioning, drift detection, cost gating, and audit traceability.',
  oneLiner: 'LLMOps = MLOps + AI-specific governance (prompt versioning, hallucination, agent budgets, decision audit).',
  businessContext: 'Multi-tenant SaaS RAG/agent platform must version everything that changes behavior (prompt, model, retrieval, rules), gate with evals, monitor drift + cost + fairness, and reconstruct any decision after the fact.',
  fiveW: {
    what: 'Prompt registry, model registry, retrieval-config registry, eval harness, cost log, decision audit, agent kill-switch, drift monitor.',
    why: 'AI behavior changes on prompt/model/retrieval/rule edits — without versioning + eval gates, regressions ship silently.',
    where: 'governance-svc (prompts/models/audit), eval-svc (eval harness), inference-svc (cost log), agent-svc (kill-switch).',
    when: 'Every change to prompt/model/retrieval/rules; every customer request; every billing cycle.',
    who: 'AI platform engineers + ML engineers own LLMOps; SRE owns drift + cost dashboards; compliance owns audit chain.',
  },
  interview30s: 'LLMOps is MLOps for LLM-based systems. Version every behavior-changing artifact: prompts, models, retrieval configs, business rules, agent tool policies. Gate every change on eval (golden set + held-out). Log every decision: input + retrieved chunks + prompt version + model version + output + confidence + cost + override. Monitor drift weekly, cost per request, hallucination rate, fairness gap. Provide an agent kill-switch (depth + cost + time). Reconstruct any decision via correlation_id. Without LLMOps, AI features ship hopes; with it, they ship invariants.',
  hld: `flowchart TB
  PROMPT[Prompt registry] --> INF[inference-svc]
  MODEL[Model registry] --> INF
  RETR[Retrieval config] --> RET[retrieval-svc]
  RULES[Rule engine] --> AG[agent-svc]
  INF --> AUDIT[Decision audit]
  AG --> AUDIT
  AUDIT --> REC[Reconstruction view]
  EVAL[Eval harness] --> CI[CI gate]
  COST[Cost log] --> FIN[FinOps dashboard]
  DRIFT[Drift monitor] --> ALERT[Alert]`,
  networkFlow: `flowchart LR
  Cli[Client] -->|HTTPS| GW[api-gateway]
  GW --> INF[inference-svc]
  INF -->|prompt_version + model_version| GOV[governance-svc]
  GOV -->|hash-chained audit| PG[(Postgres)]
  INF -->|cost log| FIN[FinOps]`,
  flowchart: `flowchart LR
  R[Request] --> RetR[Retrieve chunks]
  RetR --> P[Build prompt: prompt_v + chunks]
  P --> M[LLM: model_v + temperature]
  M --> O[Output + cost + confidence]
  O --> AUD[Decision audit row]
  AUD --> REC[Reconstruction by correlation_id]`,
  sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant Inf as inference-svc
  participant Reg as Registry
  participant LLM
  participant Aud as governance-svc
  Cli->>Inf: ask
  Inf->>Reg: get prompt_v + model_v
  Reg-->>Inf: pinned versions
  Inf->>LLM: prompt + model
  LLM-->>Inf: tokens + cost
  Inf->>Aud: decision audit row
  Aud-->>Inf: ack
  Inf-->>Cli: response`,
  coreLayers: [
    { layer: 'Versioning', responsibility: 'Prompt + model + retrieval config + rules each in registry; pinned per-tenant.' },
    { layer: 'Eval', responsibility: 'Golden set + held-out + production sample; gates every release.' },
    { layer: 'Cost & FinOps', responsibility: 'Per-request token + USD log; per-tenant budget; alert on overrun.' },
    { layer: 'Drift', responsibility: 'Embedding drift + recall drift + hallucination rate weekly review.' },
    { layer: 'Audit', responsibility: 'Hash-chained per-tenant decision log; reconstructible by correlation_id.' },
    { layer: 'Agent control', responsibility: 'Kill-switch (depth + cost + time); per-call OPA scope.' },
  ],
  lld: `flowchart LR
  PromptReg[Prompt registry] --> Pinned[(prompt_v=v3.2)]
  ModelReg[Model registry] --> Pinned2[(model_v=mistral-7b-v0.2)]
  Pinned --> InfAudit[Audit row]
  Pinned2 --> InfAudit
  Cost[Cost calc] --> InfAudit
  Confidence[Confidence calc] --> InfAudit
  InfAudit --> Chain[(hash chain per tenant)]`,
  problem: 'AI features without LLMOps regress silently on every prompt/model edit, blow budgets without warning, hallucinate without detection, and become unauditable post-incident.',
  whyThisApproach: 'Version everything that changes behavior + eval-gate every change + log every decision = a decision system, not a prompt-engineering hobby.',
  whenToUse: ['Production AI features', 'Multi-tenant LLM platforms', 'Regulated domains', 'Anywhere reproducibility matters'],
  whenNotToUse: ['Personal hackathon', 'Pre-PMF prototype'],
  input: 'Prompt edit / model swap / retrieval-config change / rule update / per-request user query',
  process: ['Registry pin per tenant', 'Eval gate on change', 'Per-request decision audit', 'Drift + cost monitor', 'Reconstruction by correlation_id'],
  output: 'Versioned + evaluated + audited AI decisions; per-incident reconstruction',
  alternatives: [
    { name: 'Hardcoded prompt + model in service code', tradeoff: 'Simple; behavior changes invisible' },
    { name: 'Vendor LLMOps (Weights & Biases, Arize)', tradeoff: 'Faster to start; vendor lock-in + cost per call' },
    { name: 'Self-hosted (this)', tradeoff: 'Full control + audit; ops cost' },
  ],
  challenges: ['Prompt drift detection', 'Model upgrade without recall regression', 'Cost gate without UX hit', 'Hallucination measurement'],
  edgeCases: [
    { case: 'Prompt edit ships without eval', solution: 'CI gate forbids merges without eval pass' },
    { case: 'Model upgrade silent recall drop', solution: 'Shadow index + canary + recall regression alert' },
    { case: 'Cost spike on hot tenant', solution: 'Token CB throttle + alert tenant admin' },
  ],
  failureModes: [
    { mode: 'Audit chain broken', detect: 'drill_audit_seal red', recover: 'Investigate write path; restore from chain' },
    { mode: 'Drift undetected', detect: 'Weekly drift review missed', recover: 'Lower threshold; add automated alert' },
  ],
  monitoring: ['Per-prompt-version success rate', 'Per-model recall + hallucination', 'Cost per tenant per day', 'Audit chain seal verification'],
  testing: ['Drill: prompt change without eval is blocked', 'Drill: audit chain seal verifies', 'Drill: cost overrun returns 429', 'Eval: golden set pass'],
  security: ['Per-tenant prompt isolation', 'Audit chain HMAC per tenant', 'Decision logs scope-checked'],
  scaling: ['Registry: small Postgres tables', 'Audit: partition by tenant_id + month', 'Drift compute: scheduled cron'],
  maturity: { mvp: 'Inline prompts + no audit', production: 'Registry + eval + audit + drift + cost', enterprise: 'Multi-region audit + advanced drift detection + per-tenant policy' },
  limitations: ['Drift detection is sampled (not exhaustive)', 'Cost log latency 1-2 min', 'Hallucination measure heuristic'],
  projectFit: ['governance-svc/ — registries + audit', 'eval-svc/ — eval harness + golden sets', 'libs/py/documind_core/cost.py — cost log', 'mcp/tests/drill_*_audit.py — audit drills'],
  interviewLine: 'LLMOps treats every prompt edit, model swap, and retrieval-config change as a behavior-changing release that demands versioning + eval gate + decision audit.',
  implementationSteps: [
    { step: 'Registry per artifact', logic: 'Prompts + models + retrieval configs + rules; each versioned and pinnable per tenant.' },
    { step: 'Eval harness gates change', logic: 'Golden set + held-out + production sample; CI gate.' },
    { step: 'Decision audit per request', logic: 'correlation_id + prompt_v + model_v + output + cost + confidence + override.' },
    { step: 'Hash-chained per-tenant log', logic: 'Tamper-evident; verified by drill_audit_seal weekly.' },
    { step: 'Drift + cost dashboards', logic: 'Per-tenant per-day; alert on threshold breach.' },
    { step: 'Agent kill-switch + per-call scope', logic: 'Depth + cost + time bounds; OPA scope check per tool.' },
  ],
  codeExample: {
    language: 'python',
    code: `# services/governance-svc/app/registry.py — prompt + model registry
from dataclasses import dataclass
from datetime import datetime

@dataclass
class PromptVersion:
    id: str
    template: str
    version: str  # e.g., "v3.2"
    model_compat: list[str]
    eval_score: float | None
    deployed_at: datetime
    deployed_by: str

class PromptRegistry:
    async def get_pinned(self, tenant_id: str, role: str) -> PromptVersion:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT * FROM prompts
                   WHERE tenant_id = $1 AND role = $2 AND is_pinned
                   ORDER BY deployed_at DESC LIMIT 1""",
                tenant_id, role,
            )
            return PromptVersion(**dict(row))

    async def deploy(self, prompt: PromptVersion, eval_result: EvalResult, actor_id: str):
        if eval_result.score < self._min_eval_score:
            raise EvalGateFailed(f"score {eval_result.score} < {self._min_eval_score}")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO prompts (id, template, version, eval_score, deployed_at, deployed_by) VALUES (...)",
                    prompt.id, prompt.template, prompt.version, eval_result.score, datetime.utcnow(), actor_id,
                )
                await audit_chain_write(
                    conn, tenant_id=prompt.tenant_id, actor_id=actor_id,
                    action="prompt_deployed",
                    payload={"prompt_id": prompt.id, "version": prompt.version, "eval_score": eval_result.score},
                )`,
  },
  realUseCase: 'A prompt edit was rolling out; eval ran on golden set + caught a 3pp regression on factual-accuracy. CI gate blocked merge. Engineer revised prompt; re-eval passed; deployment proceeded. Without the gate, the regression would have been visible only in production hallucination rate weeks later.',
  prosCons: {
    pros: ['Behavior changes are reversible + auditable', 'Eval gate catches regressions BEFORE production', 'Decision audit enables post-incident reconstruction', 'Cost gating prevents runaway bills'],
    cons: ['Up-front investment (registry + eval + audit infra)', 'Eval golden sets need maintenance', 'Drift detection requires sampling discipline'],
  },
  comparison: {
    left: 'Hardcoded prompts + manual model swap',
    right: 'LLMOps with registry + eval + audit (this)',
    rows: [
      { aspect: 'Prompt change tracking', left: 'git log only', right: 'Registry + eval gate + audit row' },
      { aspect: 'Model upgrade safety', left: 'Hope', right: 'Shadow index + canary + recall' },
      { aspect: 'Cost predictability', left: 'Surprise bills', right: 'Token CB + per-tenant cap' },
      { aspect: 'Post-incident reconstruction', left: 'Slack archeology', right: 'correlation_id audit chain' },
    ],
  },
  solutions: [
    { problem: 'Prompt regression ships silently', solution: 'Registry + eval gate' },
    { problem: 'Model upgrade recall drop', solution: 'Shadow index + canary + alert' },
    { problem: 'Cost runaway', solution: 'Token CB + per-tenant budget' },
    { problem: 'Audit reconstruction lost', solution: 'correlation_id + hash-chained per-tenant log' },
  ],
  bestPractices: {
    do: ['Version every behavior-changing artifact', 'Eval gate every change', 'Decision audit per request', 'Hash-chained per-tenant log', 'Drift dashboards weekly'],
    avoid: ['Hardcoded prompts in code', 'Model swap without canary', 'Skipping eval gate', 'Silent cost overruns', 'No audit chain'],
    optimize: ['Per-tenant registry pinning', 'Eval automation in CI', 'Streaming cost log', 'Drift sampling targeted to risky tenants'],
  },
  antiPatterns: ['Hardcoded prompts', 'No eval gate', 'No decision audit', 'Silent cost overruns', 'Unsigned audit logs'],
  testTypes: ['Drill: prompt change blocked without eval', 'Drill: model upgrade canary', 'Drill: cost overrun returns 429', 'Drill: audit seal verifies', 'Eval: golden set + held-out per release'],
  testScenarios: [
    { scenario: 'Prompt edit reduces eval score', expected: 'CI gate blocks merge' },
    { scenario: 'Model swap silent recall regression', expected: 'Shadow index + canary catches; alert' },
    { scenario: 'Tenant exceeds daily token budget', expected: '429 + Retry-After; admin alerted' },
    { scenario: 'Audit chain broken', expected: 'drill_audit_seal red; investigation triggered' },
  ],
  testData: [
    { type: 'Eval golden set', example: '500 (input, expected) pairs per role; recall + factual + tone scored' },
    { type: 'Cost overrun fixture', example: 'Mock requests + cost log + budget config' },
    { type: 'Audit chain seed', example: 'Sealed window per tenant; verifier must accept' },
  ],
  debuggingChecklist: [
    'Decision unreproducible? correlation_id missing OR audit row missing',
    'Eval regression? Compare prompt diff + golden set delta',
    'Cost spike? Per-tenant cost log + Token CB state',
    'Drift undetected? Drift threshold + sampling cadence',
  ],
  productionIssues: [
    { issue: 'Prompt regression caught only in prod hallucination rate', rootCause: 'Eval gate not enforcing min score; merged anyway. Threshold + CI gate now hard.' },
    { issue: 'Audit chain gap of 12 minutes', rootCause: 'Audit DB write timeout 50ms; bursty writes silently dropped. Fail-closed semantics added.' },
    { issue: 'Tenant blew $400 in tokens overnight', rootCause: 'Token CB existed but feature flag off in prod. Flag turned on + drill ensures enforcement.' },
  ],
  performance: ['Registry lookup: ~10ms p95 (Redis cached)', 'Audit write: async ~10ms; doesn\'t block', 'Eval run: ~30-60s for 500-item golden set'],
  costConsiderations: ['Registry storage: small PG tables', 'Audit storage: ~500 bytes/row × retention', 'Eval compute: dominant cost on heavy golden sets'],
  observability: ['Trace: per-request prompt_v + model_v + cost + confidence', 'Metrics: prompt_eval_score, model_recall, cost_per_tenant', 'Audit: hash-chained per tenant; verified weekly'],
  metrics: [
    { name: 'documind_prompt_eval_score{prompt_id,version}', example: 'Gauge per release; alert on regression' },
    { name: 'documind_decision_audit_writes_total{tenant,outcome}', example: 'Counter; outcome=success|failure' },
    { name: 'documind_cost_per_tenant_per_day_usd', example: 'Gauge; alert on threshold breach' },
    { name: 'documind_drift_score{tenant,metric}', example: 'Gauge weekly; alert if drift > threshold' },
  ],
  tradeoffs: [
    { decision: 'Self-host vs vendor LLMOps', tradeoff: 'Self-host: full control; vendor: fast start' },
    { decision: 'Eval coverage', tradeoff: 'Big golden set: better; expensive' },
    { decision: 'Audit retention', tradeoff: 'Long: compliance; storage' },
  ],
  decisionMatrix: [
    { option: 'Self-hosted LLMOps (this)', whenToUse: 'Production multi-tenant AI; regulated' },
    { option: 'Vendor LLMOps (Arize, W&B)', whenToUse: 'Small team, willing to pay per call' },
    { option: 'Spreadsheet tracking', whenToUse: 'Hackathon only' },
  ],
  starStory: {
    situation: 'Pre-LLMOps: prompt edits shipped via git; recall regressions caught only in production weeks later.',
    task: 'Make every behavior change reversible + auditable.',
    action: 'Built prompt registry + eval harness + decision audit + hash-chained per-tenant log + Token CB + drift dashboards.',
    result: 'Zero silent regressions in 6 months. EU AI Act audit passed. Pattern documented as ADR-008/009/010.',
  },
  interviewTraps: ['Hardcoded prompts in service code', 'No eval gate', 'No decision audit', 'Silent cost overruns'],
  finalScript: 'LLMOps is the operational discipline behind production AI. Version every prompt + model + retrieval config + rule. Eval-gate every change with golden set + held-out. Decision-audit every request with correlation_id, prompt_v, model_v, output, cost, confidence, override. Hash-chain audit per tenant. Drift + cost dashboards weekly. Agent kill-switch on depth + cost + time. With LLMOps, AI ships invariants; without it, AI ships hopes.',
};

type Bullet = string;

interface FiveW {
  what: string;
  why: string;
  who: string;
  when: string;
  where: string;
}

interface Capability {
  slug: string;
  title: string;
  status: 'shipped' | 'partial' | 'open';
  coreConcept: string;
  fiveW: FiveW;
  input: string;
  process: string[];
  output: string;
  flowchart: string;
  sequence: string;
  challenges: Bullet[];
  solutions: Bullet[];
  edgeCases: Bullet[];
  edgeCaseSolutions: Bullet[];
  limitations: Bullet[];
  nextEvolution: Bullet[];
  interviewLine: string;
}

const CAPABILITIES: Capability[] = [
  // ---- 1. Prompt registry ----
  {
    slug: 'prompt-registry',
    title: '1. Prompt registry',
    status: 'shipped',
    coreConcept: 'Prompt registry is the control layer for prompt versions, status, and runtime selection — prompts are governed runtime assets, not strings in code.',
    fiveW: {
      what: 'Stored registry of prompt templates, versions, status (draft/active/archived/deprecated), and runtime config (model, temperature, max_tokens).',
      why: 'Prompts change model behaviour. Without versioned governance, rollback is manual, debugging is opaque, and audit becomes guesswork.',
      who: 'AI engineers (author), platform engineers (lifecycle), operators (runtime visibility), reviewers (approval).',
      when: 'At prompt creation, lifecycle transition (draft → active → archived), and on every inference request that resolves an active prompt.',
      where: 'governance.prompts table; resolved at runtime by inference-svc; visible on /admin (Prompt registry panel).',
    },
    input: 'name + version + template + model + temperature + max_tokens + status',
    process: [
      'Save prompt row in governance.prompts',
      'Mark one or more versions as active (A/B supported)',
      'Inference request resolves active prompt by name',
      'Prompt + model executed; audit + metrics emitted',
    ],
    output: 'Controlled prompt execution with version traceability, lifecycle state, and operator visibility into what is live RIGHT NOW.',
    flowchart: `flowchart LR
  a[Admin defines prompt] --> b[Store in governance.prompts]
  b --> c[Mark version status]
  c --> d[Inference request arrives]
  d --> e[Resolve active prompt]
  e --> f[Execute with model]
  f --> g[Emit audit + metrics]
  g --> h[Operator sees on /admin]`,
    sequence: `sequenceDiagram
  autonumber
  participant Adm as Admin
  participant DB as governance.prompts
  participant Inf as inference-svc
  participant LLM as Model
  participant Aud as Audit
  Adm->>DB: create prompt v1, status=draft
  Adm->>DB: status=active
  Inf->>DB: list_active(name)
  DB-->>Inf: row {template, model, max_tokens}
  Inf->>LLM: execute(template, model)
  LLM-->>Inf: completion
  Inf->>Aud: write(prompt_version, correlation_id)`,
    challenges: [
      'Prompt changes silently shift system behaviour',
      'Hardcoded prompts are unreviewable + unauditable',
      'Multiple active versions create rollout confusion',
      'Rollback is often manual + slow',
      'Model + prompt coupling becomes messy without explicit fields',
    ],
    solutions: [
      'Registry table with version + status enum',
      'Active-state CHECK constraint (drill: drill_prompt_registry.py)',
      'Per-row model + tuning fields',
      'Audit row records prompt_version on every call',
      '/admin surfaces what is currently active',
    ],
    edgeCases: [
      'Two prompt versions accidentally active for same name (A/B)',
      'Prompt exists but template malformed',
      'Model referenced is unavailable on the serving backend',
      'Archived prompt still referenced by an in-flight request',
      'New prompt version degrades answer quality after rollout',
    ],
    edgeCaseSolutions: [
      'Multi-active is intentional for A/B — drill locks both surface in /health/prompts',
      'Validate template at activation time + on cold start',
      'Fail-closed to last-known-good prompt + structured log',
      'Block archived/deprecated prompts at runtime; allow grace window',
      'Route prompt changes through evaluation regression gate before activation',
    ],
    limitations: [
      'Registry alone does not prove prompt quality',
      'No experiment history → weak change-impact analysis',
      'No owner field → weaker accountability',
      'No one-click rollback → slower incident recovery',
    ],
    nextEvolution: [
      'Add `owner` column + approval workflow surface',
      'Persist prompt-experiment join: (prompt_version, eval_run_id, baseline_metrics)',
      'One-click rollback: pin "last_known_good" version, swap-active button',
      'Prompt diff view between versions',
    ],
    interviewLine: 'Prompts are not embedded in code paths. They are versioned runtime assets with lifecycle state — that gives us traceability and safer iteration.',
  },

  // ---- 2. Offline evaluation + regression gate ----
  {
    slug: 'evaluation',
    title: '2. Offline evaluation + regression gate',
    status: 'shipped',
    coreConcept: 'Offline evaluation is the AI equivalent of release-quality testing — pre-rollout quality validation with regression gating.',
    fiveW: {
      what: 'Run benchmark datapoints against candidate prompt/model config, compute metrics, compare to baseline, gate rollout.',
      why: 'Prevent quality regressions before production traffic sees them.',
      who: 'AI engineer (submit run), platform owner (set thresholds), release approver (interpret pass/fail).',
      when: 'Before each rollout; after major prompt/model changes; in CI for prompt PRs.',
      where: 'evaluation-svc /api/v1/evaluation/run + /api/v1/evaluation/regression-gate.',
    },
    input: 'evaluation dataset, candidate config, baseline metrics, per-metric tolerances',
    process: [
      'Run evaluation on datapoints',
      'Compute precision_at_k, recall, mrr, ndcg, faithfulness, answer_relevance',
      'Compare candidate vs baseline per metric',
      'Apply tolerance rule: pass = (delta >= -tolerance) for ALL metrics',
    ],
    output: 'Pass/fail decision + per-metric deltas + actionable list of failed_metrics for the post-mortem.',
    flowchart: `flowchart LR
  a[Eval dataset] --> b[Candidate prompt/model]
  b --> c[Run /evaluation/run]
  c --> d[Compute metrics]
  d --> e[/regression-gate: candidate vs baseline/]
  e -->|pass| f[Rollout proceeds]
  e -->|fail| g[Block + report failed_metrics]`,
    sequence: `sequenceDiagram
  autonumber
  participant Eng as Engineer
  participant Eval as evaluation-svc
  participant Inf as Inference path
  participant Gate as Regression gate
  Eng->>Eval: POST /api/v1/evaluation/run
  Eval->>Inf: execute candidate on datapoints
  Inf-->>Eval: per-datapoint scores
  Eval-->>Eng: metrics aggregate
  Eng->>Gate: POST /regression-gate {current, baseline, tolerance}
  Gate->>Gate: per-metric delta vs -tolerance
  Gate-->>Eng: passed=true/false + deltas + failed_metrics`,
    challenges: [
      'AI output is probabilistic — single runs noisy',
      'Metrics can be incomplete proxies for true quality',
      'Datasets get stale relative to production query distribution',
      'One metric improving while another regresses',
      'Regression definition is domain-specific',
    ],
    solutions: [
      'Multi-metric evaluation (6 metrics computed per run)',
      'Per-metric tolerance — operators tune per use case',
      'Baseline is caller-supplied (eval-svc stays stateless)',
      'failed_metrics is a list — reviewers see WHICH dimension regressed',
      'Drill `drill_eval_regression_gate` locks 5 negatives including improvement-never-fails',
    ],
    edgeCases: [
      'Candidate improves precision but hurts faithfulness',
      'Eval dataset is too small (high variance)',
      'Benchmark unrepresentative of production query distribution',
      'Model temperature randomness causes inconsistent results across runs',
      'Prompt passes offline but fails on real user queries',
    ],
    edgeCaseSolutions: [
      'Operator sets faithfulness tolerance tighter than precision',
      'Require minimum n on dataset; reject sparse runs',
      'Refresh benchmark sets quarterly; mix in sampled prod queries',
      'Run 3x and use median; track variance as a separate metric',
      'Pair offline eval with online monitoring + feedback capture',
    ],
    limitations: [
      'Offline eval cannot fully predict real-world behaviour',
      'No persistent run history → weak reproducibility',
      'No dataset-to-run lineage → trust in baseline degrades over time',
      'Baseline supplied per-call → no central registry of "the" baseline',
    ],
    nextEvolution: [
      'Persist eval_run rows: (run_id, dataset_version, prompt_version, model_version, metrics)',
      'Dataset registry with version pins',
      'Champion vs challenger workflow with promotion criteria',
      'Online aggregation: compare offline eval against rolling production metrics',
    ],
    interviewLine: 'Regression gating is the AI equivalent of a release-quality test. We block rollouts when ANY metric drops past tolerance — improvements never fail the gate.',
  },

  // ---- 3. Audit + correlation IDs ----
  {
    slug: 'audit',
    title: '3. Audit trail + correlation IDs',
    status: 'shipped',
    coreConcept: 'Correlation ID is the spine connecting frontend errors, backend traces, MCP tool calls, and audit events into one debuggable story.',
    fiveW: {
      what: 'Per-request UUID propagated through every layer + tamper-evident audit log per tenant.',
      why: 'Trust, debugging, compliance, forensics. Distributed systems fragment evidence; correlation reconnects it.',
      who: 'Operators (incident reconstruction), security (forensics), compliance (evidence), AI engineers (debugging).',
      when: 'Every request (correlation_id always); every sensitive action (audit row mandatory or fail-closed).',
      where: 'CorrelationIdMiddleware (ingress) → service logs → MCP tool calls → governance.audit_log (hash-chained per tenant).',
    },
    input: 'request with tenant_id (header) + actor (JWT sub) + optional correlation_id (we generate if absent)',
    process: [
      'Middleware assigns/propagates correlation_id',
      'Every log/span/audit row carries it',
      'MCP tool calls forward it to downstream',
      'Audit row is hash-chained (previous_hash → entry_hash) per tenant',
      '/api/v1/admin/trace/{cid}?tenant_id= reconstructs end-to-end',
    ],
    output: 'Attributable, traceable execution history. One correlation_id → all logs + traces + audit + drafts that touched the request.',
    flowchart: `flowchart LR
  a[Request enters gateway] --> b[Correlation ID assigned]
  b --> c[Service handles request]
  c --> d[MCP tool call inherits cid]
  c --> e[Audit row written]
  d --> f[Tool server logs cid]
  e --> g[Hash-chained per tenant]
  c --> h[OTel span with cid attribute]
  g --> i[/admin/trace/cid lookup]`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant Gw as Gateway
  participant Svc as Service
  participant MCP as MCP tool
  participant Aud as audit_log
  participant Op as Operator
  Cli->>Gw: request
  Gw->>Svc: forward + cid
  Svc->>MCP: tool call + cid
  MCP-->>Svc: result
  Svc->>Aud: write {tenant, actor, action, cid, prev_hash, entry_hash}
  Op->>Svc: GET /admin/trace/cid?tenant_id=
  Svc-->>Op: audit_rows + draft_rows + jaeger_url`,
    challenges: [
      'Distributed systems fragment evidence',
      'Logs alone are insufficient — no shape, no contract',
      'Cross-service debugging is slow without shared IDs',
      'Audit can become noisy or incomplete',
      'Tenant boundaries must hold even for operators',
    ],
    solutions: [
      'Correlation_id propagated by middleware + MCPClient',
      'Audit hash-chain (drill: drill_audit_seal, drill_audit_verifier)',
      'fail_closed per-call governance posture (ADR-004)',
      '/admin/trace/{cid}?tenant_id= surfaces audit + drafts',
      'RLS on audit_log forces per-tenant lookup',
    ],
    edgeCases: [
      'Missing correlation_id from upstream',
      'One service drops header propagation',
      'Replayed action gets new context incorrectly',
      'Audit write fails after action succeeded',
      'Cross-tenant leakage in audit lookup',
    ],
    edgeCaseSolutions: [
      'Gateway generates cid if absent (uuid4)',
      'Middleware re-attaches cid on every outbound HTTP/MCP call',
      'Replay preserves original correlation_id + actor metadata',
      'fail_closed=true blocks the action; counter `documind_audit_write_failures_total` alerts',
      'tenant_id query-param required on /admin/trace; drill locks it (step 6a wrong-tenant returns zero rows)',
    ],
    limitations: [
      'Audit proves events happened, NOT that decisions were semantically correct',
      'Correlation enables traceability, not quality',
      'Compliance reporting may need separate evidence surfaces',
      'Hash chain detects tampering, not omissions before insertion',
    ],
    nextEvolution: [
      'Compliance-report endpoint that compiles audit for a date range',
      'Tighter UI: click a span in Jaeger → jump to /admin/trace/cid',
      'Audit retention policy (ADR-017 planned)',
      'Privileged-role + cross-tenant trace lookup with explicit scope',
    ],
    interviewLine: 'Correlation ID is the spine of the system. It lets us connect frontend errors, backend traces, MCP actions, and audit events into one debuggable story — without it, distributed debugging is anecdote, not evidence.',
  },

  // ---- 4. Draft fallback + HITL + replay ----
  {
    slug: 'draft-fallback',
    title: '4. Draft fallback + HITL + replay',
    status: 'shipped',
    coreConcept: 'Draft fallback converts dependency failures into governed pending state instead of losing user intent.',
    fiveW: {
      what: 'When tool execution fails (breaker open, downstream down, scope reject), persist a Draft row + return degraded response. Operators or workers replay later.',
      why: 'Resilience, intent preservation, audit-grade incident handling.',
      who: 'End user (sees degraded), operator (resolves/rejects), replay worker (auto-retries), audit (every transition).',
      when: 'On any tool-call failure during agent.ask: breaker open, downstream timeout, dependency 5xx.',
      where: 'governance.action_drafts + DraftReplayWorker; resolve/reject endpoints on inference-svc.',
    },
    input: 'user agent.ask request → agent detects tool intent → tool call attempted',
    process: [
      'Scope precheck (block if INSUFFICIENT_SCOPE)',
      'Try MCP tool call',
      'On success: complete + audit',
      'On failure: persist Draft (pending) + return degraded response',
      'DraftReplayWorker sweeps pending drafts on interval',
      'Auto-rejects after N consecutive failures (ADR-009)',
    ],
    output: 'Action succeeds now OR safe pending Draft for review OR rejected action with audit trail. Intent is preserved either way.',
    flowchart: `flowchart LR
  a[User action request] --> b[Agent detects tool intent]
  b --> c[Scope check]
  c -->|denied| z[403 + audit]
  c -->|allowed| d[MCP tool call]
  d -->|success| e[Complete + audit]
  d -->|failure| f[Persist Draft]
  f --> g[Operator review]
  f --> h[Replay worker sweep]
  g -->|resolve| i[Replay tool call]
  g -->|reject| j[Mark rejected + audit]
  h -->|N consecutive fails| j
  i -->|success| k[Mark replayed + audit]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Inf as inference-svc
  participant MCP as MCP client
  participant Tool as Tool server
  participant DS as draft_store
  participant W as Replay worker
  U->>Inf: agent.ask "submit leave"
  Inf->>MCP: hr.leave_request(...)
  MCP->>Tool: POST /tools/call
  Tool-->>MCP: ConnectError (breaker)
  MCP->>DS: insert Draft (pending)
  MCP-->>Inf: degraded response
  Inf-->>U: "saved as pending draft"
  W->>DS: list_pending(tenant)
  W->>Tool: replay
  Tool-->>W: 200
  W->>DS: status=replayed + audit`,
    challenges: [
      'Downstream tools fail intermittently',
      'Users still expect intent preservation',
      'Retries can cause duplicate side effects',
      'Human review queues backlog',
      'Replay attribution can be misleading',
    ],
    solutions: [
      'Draft state machine enforced by DB CHECK (migration 006)',
      'Idempotency keys via governance.mcp_idempotency (ADR-003)',
      'Service-token sub as actor_id during replay (ADR-007)',
      'Auto-reject after N consecutive failures',
      'Per-namespace bailout to prevent thundering-herd',
    ],
    edgeCases: [
      'Tool succeeded remotely but local response timed out',
      'Replay runs twice',
      'Draft becomes stale (business context changed)',
      'Operator resolves wrong draft',
      'Dependency recovers; backlog spikes overwhelm tool',
    ],
    edgeCaseSolutions: [
      'Idempotency key — second call returns cached response',
      'CAS-guarded mark_replayed (state transition fails if not pending)',
      'Stale-draft validation before execution (check arguments still valid)',
      'Explicit actor attribution + correlation_id on resolve',
      'Replay worker backpressure + bounded sweep size',
    ],
    limitations: [
      'Fallback preserves intent, NOT guaranteed completion',
      'Human review introduces latency',
      'Semantic correctness still hard to verify automatically',
      'Large draft backlogs become operational risk',
    ],
    nextEvolution: [
      'Richer review UI with diff against current state',
      'Semantic correctness scoring on resolve',
      'Approval workflow for sensitive draft tools',
      'Trace → draft pivot in admin (already partial via /admin/trace)',
    ],
    interviewLine: 'We convert dependency failures into governed pending state instead of losing the action. That is the difference between a demo and an enterprise workflow system.',
  },

  // ---- 5. RAG data lifecycle ----
  {
    slug: 'rag-lifecycle',
    title: '5. RAG data lifecycle',
    status: 'partial',
    coreConcept: 'RAG quality depends on data lifecycle discipline (ingest → parse → chunk → embed → index → retrieve), not just model quality.',
    fiveW: {
      what: 'End-to-end pipeline that turns source documents into queryable retrieval context.',
      why: 'Answer quality is downstream of retrieval quality. The model is only as good as the context we feed it.',
      who: 'ingestion-svc (pipeline), retrieval-svc (query), inference-svc (assembly), data team (corpus quality).',
      when: 'At corpus update time (ingest) and query time (retrieve).',
      where: 'ingestion-svc → Postgres (metadata) → Qdrant (vectors) → retrieval-svc → inference-svc.',
    },
    input: 'raw document or corpus source (PDF / DOCX / HTML / Markdown / etc.)',
    process: [
      'Parse + clean (boilerplate removal, OCR fallback for scanned PDFs)',
      'Chunk with token-aware policy (256-1024 tokens, 10-20% overlap)',
      'Embed via configured embedding model',
      'Index in Qdrant with tenant + document metadata',
      'Query: vector + graph + cache hybrid retrieval',
      'Rerank top-K; assemble prompt context',
    ],
    output: 'Grounded answer context the model uses to generate cited responses.',
    flowchart: `flowchart LR
  a[Document source] --> b[Parse + clean]
  b --> c[Chunk]
  c --> d[Embed]
  d --> e[Qdrant index]
  f[User query] --> g[Embed query]
  g --> h[Retrieve top-K from Qdrant]
  h --> i[Optional rerank]
  i --> j[Assemble prompt context]
  j --> k[Inference generates grounded answer]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Ing as ingestion-svc
  participant Parse as Parser+Chunker
  participant Emb as Embedder
  participant Q as Qdrant
  participant Ret as retrieval-svc
  participant Inf as inference-svc
  U->>Ing: upload document
  Ing->>Parse: extract + chunk
  Parse->>Emb: chunks
  Emb->>Q: store embeddings
  U->>Inf: ask question
  Inf->>Ret: query
  Ret->>Q: vector search
  Q-->>Ret: top-K chunks
  Ret-->>Inf: context
  Inf->>Inf: assemble prompt + generate
  Inf-->>U: answer + citations`,
    challenges: [
      'Bad source quality leads to bad retrieval',
      'Chunking strategy affects relevance per use case',
      'Embedding model changes silently shift recall',
      'Mixed file types are hard to normalize',
      'Provenance is often weak',
    ],
    solutions: [
      'Token-aware chunker (per-doc-type policy)',
      'Citation grounding (GuardrailChecker rejects hallucinated citations)',
      'Per-tenant Qdrant collections (drill: drill_retrieval_tenant_isolation)',
      'Document state machine through ingest stages',
      'Transport breakers around Qdrant + Neo4j (ADR-008)',
    ],
    edgeCases: [
      'Document contains repeated boilerplate (TOC, headers)',
      'Scanned PDF needs OCR; OCR is noisy',
      'Wrong chunk size fragments paragraphs',
      'Embedding model changes but index not rebuilt',
      'Same file ingested multiple times',
    ],
    edgeCaseSolutions: [
      'Boilerplate removal heuristics; quarantine bad chunks',
      'OCR fallback with confidence threshold; quarantine low-confidence pages',
      'Token-aware chunking with overlap; tune per doc type',
      'Version embedding + index; rebuild on model bump',
      'Dedupe by content hash; corpus snapshot versioning',
    ],
    limitations: [
      'Operational ingestion ≠ governed dataset management',
      'No chunk version registry → weak reproducibility',
      'No embedding registry → hard-to-explain retrieval drift',
      'Retrieval quality still depends on source quality',
    ],
    nextEvolution: [
      'Dataset registry (governance.datasets) with version pins',
      'Chunk version tracking',
      'Embedding model registry with index-coupling enforcement',
      'Retrieval-quality span attributes (relevance + groundedness per call)',
    ],
    interviewLine: 'The RAG path can work operationally long before it becomes reproducible and governable. We have the runtime; the registry layer is the next maturity step.',
  },

  // ---- 6. Observability ----
  {
    slug: 'observability',
    title: '6. Observability',
    status: 'partial',
    coreConcept: 'Operational observability is strong when you can explain latency, failure, degradation, and recovery with evidence — not just CPU/RAM.',
    fiveW: {
      what: 'OTel traces + Prometheus metrics + structured logs + admin dashboards, all keyed by correlation_id.',
      why: 'AI systems need more than infra metrics. Latency, tokens, errors, tool outcomes, and quality all matter.',
      who: 'On-call (alerts), operators (dashboards), AI engineers (debugging), security (forensics).',
      when: 'Continuously — every request, every tool call, every guardrail check.',
      where: 'libs/py/documind_core/observability.py + Prometheus exporters + admin dashboard.',
    },
    input: 'requests, tool calls, inference runs, guardrail checks, failures',
    process: [
      'Emit token counters (per model, per kind)',
      'Emit latency histograms (per tool, per upstream)',
      'Emit error counters (audit failures, scope denials)',
      'Wrap key paths in OTel spans with attributes (actor, outcome, guardrail.passed)',
      'Surface as /admin dashboards (breakers, tools, prompts, upstreams, client errors)',
    ],
    output: 'Latency + error + token + partial quality visibility, all pivotable by correlation_id.',
    flowchart: `flowchart LR
  a[Request/tool/inference] --> b[OTel span + attrs]
  a --> c[Prom counters/histograms]
  a --> d[Structured log]
  b --> e[Jaeger]
  c --> f[Prometheus]
  d --> g[Loki/grep]
  e --> h[/admin trace lookup/]
  f --> h
  g --> h`,
    sequence: `sequenceDiagram
  autonumber
  participant Req as Request
  participant Inf as inference-svc
  participant OTel as OTel exporter
  participant Prom as Prometheus
  participant UI as /admin
  Req->>Inf: agent.ask
  Inf->>OTel: span "agent.ask" + cid + tenant
  Inf->>Prom: counter inc / histogram observe
  Inf->>OTel: child span "guardrail.check" + passed/violations
  UI->>Inf: GET /health/tools
  Inf-->>UI: per-tool calls/latency/denials
  UI->>OTel: link to Jaeger by cid`,
    challenges: [
      'AI systems need more than infra metrics',
      'Frontend and backend errors disconnected',
      'Traces can be noisy at scale',
      'Operators need actionable, not decorative, dashboards',
      'Cardinality discipline matters (per ADR-010)',
    ],
    solutions: [
      'Token counter + latency histogram + scope-denial counter shipped',
      'Client-error reporter pipes browser errors into backend ring buffer',
      'OTel attributes (actor.id, outcome, guardrail.*) for queryability',
      'No tenant_id on Prom labels — bounded cardinality',
      'Per-route admin panels with 5s refresh',
    ],
    edgeCases: [
      'High latency with no hard errors',
      'Prompt works but citations are wrong',
      'Frontend shows failure while backend succeeded',
      'Tool call degrades intermittently',
      'Trace sampling hides the interesting request',
    ],
    edgeCaseSolutions: [
      'Track degraded-mode states explicitly (degraded=True envelope)',
      'Guardrail span attrs surface citation/violation evidence',
      'Client-error reporter correlates with backend traces by cid',
      'Per-tool monitoring panel shows degraded vs ok counts',
      'Adjust sampling for /agent/ask + critical paths (force sample)',
    ],
    limitations: [
      'Observability shows symptoms without root-cause intelligence',
      'No feedback capture → no user-perceived quality measure',
      'No per-run cost accounting → limited optimization insight',
      'Sampling tradeoffs constrain visibility',
    ],
    nextEvolution: [
      'Per-run cost tracking (token-cost × call_count → $/tenant)',
      'Feedback capture: thumbs-up/down → online quality metric',
      'Retrieval-quality span attributes (relevance score, citation match)',
      'Prompt-version trace filters in admin/trace lookup',
    ],
    interviewLine: 'Operational observability is strong when you can explain latency, failure, degradation, and recovery with evidence. Infra metrics alone are necessary but not sufficient for AI.',
  },

  // ---- 7. Model management (open / partial gap) ----
  {
    slug: 'model-management',
    title: '7. Model management',
    status: 'partial',
    coreConcept: 'Model management means treating models as governed deployable assets — registry + lifecycle + rollout — not strings in config.',
    fiveW: {
      what: 'Registry of model versions, metadata (model card), lifecycle state (candidate/active/deprecated), serving profile.',
      why: 'Safer upgrades, explicit rollback targets, cost/latency control.',
      who: 'AI platform team (register), release owner (promote), on-call (rollback).',
      when: 'Onboarding, evaluation, rollout, incident response.',
      where: 'Currently: per-prompt-row model column. Target: separate models registry.',
    },
    input: 'model name + version + serving config + task suitability + cost/latency profile',
    process: [
      'Register model metadata',
      'Run evaluation against benchmark dataset',
      'Mark candidate vs active per task',
      'Route runtime traffic',
      'Monitor cost/latency/quality',
      'Rollback to previous active on regression',
    ],
    output: 'Controlled model inventory with explainable runtime selection and safe rollback.',
    flowchart: `flowchart LR
  a[Model candidate] --> b[Register metadata]
  b --> c[Evaluate]
  c -->|pass| d[Mark active for task]
  c -->|fail| e[Reject candidate]
  d --> f[Route traffic]
  f --> g[Monitor cost/latency/quality]
  g -->|regression| h[Rollback to previous active]`,
    sequence: `sequenceDiagram
  autonumber
  participant Eng as AI engineer
  participant Reg as Model registry
  participant Eval as Evaluation
  participant Op as Operator
  participant Srv as Serving layer
  participant Mon as Monitoring
  Eng->>Reg: register model v2
  Eval->>Reg: attach quality results
  Op->>Srv: activate v2 for task=summary
  Srv->>Eng: route summary calls to v2
  Mon->>Op: detect regression
  Op->>Reg: pin v1 as rollback target
  Op->>Srv: rollback to v1`,
    challenges: [
      'Model string in config is not enough',
      'Upgrades change quality + cost + latency simultaneously',
      'No registry → weak rollback discipline',
      'Different task types need different models',
      'Local (Ollama) vs hosted model behaviour differs',
    ],
    solutions: [
      'Currently: model lives per-prompt-row in governance.prompts.model',
      '/admin/llmops surfaces model presence (partial)',
      'Token + latency metrics are per-model (label cardinality bounded)',
      'Drill `drill_inference_token_metric` locks per-model counter',
    ],
    edgeCases: [
      'Model version exists in registry but missing on serving backend',
      'Quantized variant behaves differently from full',
      'Long-context model is too expensive for high-volume queries',
      'Same prompt performs differently across models',
      'Embedding model mismatch with stored Qdrant index',
    ],
    edgeCaseSolutions: [
      'Startup verification: list serving inventory + cross-check registry',
      'Explicit variant metadata (quantized/full)',
      'Cost/latency-aware routing per task',
      'Evaluate the (prompt, model) pair, not the prompt alone',
      'Coupling check: embedding_model_version pinned to index_version',
    ],
    limitations: [
      'Registry improves control, not quality by itself',
      'Model selection without experiment tracking stays weak',
      'No cost-aware router → overpay risk',
      'No champion/challenger flow yet',
    ],
    nextEvolution: [
      'governance.models table with lifecycle state',
      'Model card: metadata + quality + cost + safety',
      'Champion/challenger registry with traffic-split rules',
      'Rollback target column on every active row',
      'SLM vs LLM routing (next item)',
    ],
    interviewLine: 'Prompt governance is ahead of model governance in this system. Models are still configuration-attached rather than first-class registry-managed assets — that gap is the next maturity step.',
  },

  // ---- 8. Experiment tracking (open) ----
  {
    slug: 'experiment-tracking',
    title: '8. Experiment tracking',
    status: 'open',
    coreConcept: 'Experiment tracking is the memory of the AI system — every evaluation run becomes reproducible, comparable, and auditable.',
    fiveW: {
      what: 'Persistent registry of (run_id, dataset_version, prompt_version, model_version, params, metrics, decision).',
      why: 'Without it, teams forget what produced a "good" result; reproducibility is anecdotal.',
      who: 'AI engineer (submit), reviewer (compare), platform team (promote).',
      when: 'Every evaluation run; every champion/challenger decision.',
      where: 'Not yet implemented — would live alongside evaluation-svc as governance.eval_runs (planned ADR-014).',
    },
    input: 'dataset version, prompt version, model version, params, baseline reference',
    process: [
      'Execute run',
      'Persist (run_id, all versions, params, metrics, timestamp)',
      'Compare runs (current vs baseline, candidate vs champion)',
      'Decision history: which run was promoted to champion + when + by whom',
    ],
    output: 'Experiment history → reproducibility, lineage, defensible promotion decisions.',
    flowchart: `flowchart LR
  a[Submit run] --> b[Persist run_id + versions + params]
  b --> c[Execute eval]
  c --> d[Store metrics]
  d --> e[Compare vs baseline]
  e --> f[Compare vs champion]
  f -->|promote| g[Update champion pointer]
  f -->|reject| h[Archive run]`,
    sequence: `sequenceDiagram
  autonumber
  participant Eng as Engineer
  participant Reg as Run registry
  participant Eval as evaluation-svc
  participant Inf as Inference path
  participant Ch as Champion pointer
  Eng->>Reg: create run (dataset_v, prompt_v, model_v, params)
  Reg->>Eval: execute
  Eval->>Inf: run datapoints
  Inf-->>Eval: per-datapoint
  Eval->>Reg: store metrics
  Eng->>Reg: compare run R1 vs R0 (champion)
  Reg-->>Eng: deltas
  Eng->>Ch: promote R1 if all gates pass`,
    challenges: [
      'Hard to compare runs without persistent metadata',
      'Prompt × model × dataset combinations explode quickly',
      'Teams forget what produced a "good" result',
      'No run history → weak reproducibility',
      'Variance from model randomness obscures real differences',
    ],
    solutions: [
      'Persist run_id with FULL version pin (dataset + prompt + model + params)',
      'Repeated runs for variance-sensitive cases (median + variance)',
      'Decision rules that balance quality + cost + latency',
      'Champion/challenger workflow with explicit promotion audit',
      'Immutable dataset snapshots referenced by run_id',
    ],
    edgeCases: [
      'Same run config gives different result due to randomness',
      'Dataset changed but run appears comparable',
      'Metrics improved only because sample changed',
      'Cost improved but quality dropped (multi-objective conflict)',
      'Two runs accidentally promoted as champion simultaneously',
    ],
    edgeCaseSolutions: [
      'Repeated runs (n=3) + variance metric',
      'Dataset version pin enforced on every run',
      'Sample-stratified comparison for fair deltas',
      'Multi-metric rule (block on any regression past tolerance)',
      'CHECK constraint on champion pointer (one active per task)',
    ],
    limitations: [
      'Experiment tracking adds infrastructure complexity',
      'Without good datasets it becomes false precision',
      'Comparing runs is only useful if metrics are meaningful',
      'Storage of historic eval data grows quickly',
    ],
    nextEvolution: [
      'governance.eval_runs table (proposed ADR-014)',
      'UI: run-comparison view, promotion-history panel',
      'Linkage: prompt_version → eval_runs that touched it',
      'Cost-per-run tracking',
    ],
    interviewLine: 'Experiment tracking is the memory of the AI system. Today we have evaluation but no run registry — every champion decision is anecdotal until that registry exists.',
  },

  // ---- 9. Deployment + serving (open / partial) ----
  {
    slug: 'deployment',
    title: '9. Deployment + serving',
    status: 'partial',
    coreConcept: 'Serving maturity is not just uptime — it is controlled rollout (canary/blue-green/shadow) and fast rollback.',
    fiveW: {
      what: 'Deployment registry: build_id, config version, env target, traffic-split rules, rollback artifact.',
      why: 'AI changes are runtime-risky; stale builds break clients (the user just hit this — port 3000 chunk drift).',
      who: 'Release engineer, on-call, platform team.',
      when: 'Every deploy; every config change; every incident response.',
      where: 'Currently: /app-meta/build-info shows running build identity. Full registry not yet implemented.',
    },
    input: 'build artifact (frontend BUILD_ID, backend container tag), serving config, env target',
    process: [
      'Deploy artifact to target env',
      'Record version + config hash',
      'Optionally route partial traffic (canary/blue-green/shadow)',
      'Monitor target health',
      'Rollback to previous version on regression',
    ],
    output: 'Active deployment identity per env, safer rollout, version-aware operations.',
    flowchart: `flowchart LR
  a[Build artifact] --> b[Deploy to target env]
  b --> c[Record build_id + config]
  c --> d{Rollout strategy}
  d -->|full| e[All traffic]
  d -->|canary| f[10% of traffic]
  d -->|shadow| g[Mirror traffic, no response]
  e --> h[Monitor]
  f --> h
  g --> h
  h -->|regression| i[Rollback to previous]`,
    sequence: `sequenceDiagram
  autonumber
  participant Eng as Release eng
  participant CI as CI
  participant Reg as Deployment registry
  participant Srv as Serving
  participant Mon as Monitoring
  participant On as On-call
  Eng->>CI: tag release v2
  CI->>Reg: register build_id + commit_sha
  Eng->>Srv: deploy v2 (canary 10%)
  Srv->>Mon: emit health
  Mon->>On: alert on canary regression
  On->>Reg: pin v1 as rollback target
  On->>Srv: rollback (revert traffic split)`,
    challenges: [
      'AI changes are runtime-risky',
      'Stale builds break clients (literal incident: port 3000 chunk drift)',
      'Config drift across envs',
      'Model/prompt rollout needs traffic control',
      'Rollback artifacts often go missing',
    ],
    solutions: [
      '/app-meta/build-info exposes build_id (commit f9ea6fc)',
      'Build identity panels on /admin and /admin/client-errors',
      'Frontend chunk-load auto-recovery (commit 51f9e93)',
      'NEXT_DIST_DIR separates dev/prod artifacts (no collision)',
      'Drill `drill_frontend_build_info` locks build-id surface',
    ],
    edgeCases: [
      'Frontend serves stale chunks',
      'Build version + running process mismatch',
      'Serving config updated without eval approval',
      'Rollback artifact unavailable',
      'One tenant affected; others healthy',
    ],
    edgeCaseSolutions: [
      'Self-hosted mermaid (no CDN drift)',
      'build-info readable on /admin, refreshed every 5s',
      'Eval-gate before serving-config rollout (manual today)',
      'Keep N previous artifacts (operational policy, not yet automated)',
      'Tenant-aware routing + per-tenant metrics',
    ],
    limitations: [
      'No deployment registry → slower incident response',
      'No canary/shadow → rollout risk higher than necessary',
      'Visibility alone does not prevent bad releases',
      'No automated rollback artifact retention',
    ],
    nextEvolution: [
      'governance.deployments table',
      'Canary/blue-green via gateway weights',
      'Shadow traffic for new model versions',
      'Tenant-targeted rollout',
    ],
    interviewLine: 'Serving maturity is not just uptime; it is controlled rollout and fast rollback. We have build-identity visibility now — the next layer is the deployment registry that backs canary and shadow flows.',
  },

  // ---- 10. SLM vs LLM routing (open) ----
  {
    slug: 'slm-vs-llm-routing',
    title: '10. SLM vs LLM routing',
    status: 'open',
    coreConcept: 'A cost-efficient platform routes by task complexity, not by habit — SLMs for cheap/fast/simple, LLMs for complex reasoning.',
    fiveW: {
      what: 'Per-request decision: use a small model, large model, or fallback model based on task type + cost ceiling + quality target.',
      why: 'Large models cost more; small models miss complex tasks. Routing by task is the cheapest reliability gain.',
      who: 'Platform team (policy), AI engineer (per-task tuning).',
      when: 'Every inference request that has multiple model options.',
      where: 'Not yet implemented. Would live in inference-svc agent path.',
    },
    input: 'task type, latency budget, quality target, cost ceiling, request payload',
    process: [
      'Classify request (intent: simple Q&A, complex reasoning, multi-step agent)',
      'Look up routing policy for task',
      'Choose primary model (SLM or LLM)',
      'Optionally escalate to LLM on low-confidence SLM output',
      'Track cost + quality per model class',
    ],
    output: 'Efficient routing → lower inference cost AND better task specialization.',
    flowchart: `flowchart LR
  a[Request arrives] --> b[Classify task]
  b -->|simple| c[Route to SLM]
  b -->|complex| d[Route to LLM]
  c --> e{Confidence high?}
  e -->|yes| f[Return SLM answer]
  e -->|no| d
  d --> g[Return LLM answer]
  f --> h[Track cost/quality per model]
  g --> h`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Inf as inference-svc
  participant Cls as Task classifier
  participant SLM as Small model
  participant LLM as Large model
  participant Mon as Cost+quality tracker
  U->>Inf: ask "summarize this paragraph"
  Inf->>Cls: classify task
  Cls-->>Inf: simple (high confidence)
  Inf->>SLM: route
  SLM-->>Inf: answer + confidence=0.85
  Inf-->>U: answer
  Inf->>Mon: cost=$0.001, kind=SLM
  Note over Inf: For "explain X with proof", route to LLM`,
    challenges: [
      'Large models cost more',
      'Small models may miss complex tasks',
      'Different tasks need different tradeoffs',
      'Teams default to one model out of habit',
      'Task classification is itself a hard problem',
    ],
    solutions: [
      'Define routing policy per task type (config, not code)',
      'Use SLM for cheap/fast/simple paths; LLM for complex',
      'Confidence-based escalation (SLM unsure → retry LLM)',
      'Add fallback model registry',
      'Track cost and output quality per model class',
    ],
    edgeCases: [
      'Simple-looking request actually needs deep reasoning',
      'Small model returns fast but wrong',
      'High-traffic surge blows up large-model cost',
      'Fallback model produces incompatible output style',
      'Task classifier itself is wrong',
    ],
    edgeCaseSolutions: [
      'Confidence-based escalation: SLM low-conf → retry on LLM',
      'Quality-threshold routing (post-hoc reroute on low score)',
      'Cost ceilings with graceful degradation',
      'Normalize output contract across model classes',
      'Default to LLM when classifier confidence is low',
    ],
    limitations: [
      'Routing adds complexity to the agent path',
      'Confidence scoring is itself imperfect',
      'Task classification can be wrong',
      'Output normalization is non-trivial',
    ],
    nextEvolution: [
      'Routing policy table per task type',
      'Confidence-based escalation in agent flow',
      'Per-model-class cost tracking on /admin',
      'Quality-threshold fallback rule',
    ],
    interviewLine: 'A cost-efficient platform routes by task, not by habit. Today the system can call models; it does not yet have a formal routing policy between SLM and LLM classes — that is the next iteration.',
  },
];

function statusBadgeClass(status: Capability['status']): string {
  if (status === 'shipped') return 'badge badge-active';
  if (status === 'partial') return 'badge badge-parsing';
  return 'badge badge-failed';
}

function CapabilitySection({ cap }: { cap: Capability }) {
  return (
    <article id={cap.slug} className="card" style={{ marginBottom: 32 }}>
      <header style={{ marginBottom: 16 }}>
        <h2 className="section-title" style={{ marginBottom: 8 }}>
          {cap.title}{' '}
          <span className={statusBadgeClass(cap.status)}>{cap.status}</span>
        </h2>
        <p style={{ fontStyle: 'italic', color: '#374151' }}>
          {cap.coreConcept}
        </p>
      </header>

      <div style={{ marginBottom: 16 }}>
        <strong>5W</strong>
        <table className="table" style={{ marginTop: 6 }}>
          <tbody>
            <tr><td style={{ width: 100 }}><strong>What</strong></td><td>{cap.fiveW.what}</td></tr>
            <tr><td><strong>Why</strong></td><td>{cap.fiveW.why}</td></tr>
            <tr><td><strong>Who</strong></td><td>{cap.fiveW.who}</td></tr>
            <tr><td><strong>When</strong></td><td>{cap.fiveW.when}</td></tr>
            <tr><td><strong>Where</strong></td><td>{cap.fiveW.where}</td></tr>
          </tbody>
        </table>
      </div>

      <div style={{ marginBottom: 16 }}>
        <strong>Input → Process → Output</strong>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr 1fr', gap: 12, marginTop: 6 }}>
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <div className="field-help">Input</div>
            <div>{cap.input}</div>
          </div>
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <div className="field-help">Process</div>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {cap.process.map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </div>
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <div className="field-help">Output</div>
            <div>{cap.output}</div>
          </div>
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <strong>Flowchart</strong>
        <Mermaid chart={cap.flowchart} />
      </div>

      <div style={{ marginBottom: 16 }}>
        <strong>Sequence diagram</strong>
        <Mermaid chart={cap.sequence} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
        <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
          <strong>Challenges</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {cap.challenges.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#dcfce7' }}>
          <strong>Solutions</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {cap.solutions.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
          <strong>Edge cases</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {cap.edgeCases.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#dcfce7' }}>
          <strong>Edge-case solutions</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {cap.edgeCaseSolutions.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <strong>Limitations</strong>
        <ul style={{ marginTop: 6, paddingLeft: 18 }}>
          {cap.limitations.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </div>

      <div style={{ marginBottom: 16 }}>
        <strong>Next evolution</strong>
        <ul style={{ marginTop: 6, paddingLeft: 18 }}>
          {cap.nextEvolution.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      </div>

      <div
        className="card"
        style={{ padding: 12, backgroundColor: '#dbeafe', borderColor: '#1e3a8a' }}
      >
        <strong>Interview line</strong>
        <p style={{ margin: '6px 0 0 0', fontStyle: 'italic' }}>
          &ldquo;{cap.interviewLine}&rdquo;
        </p>
      </div>
    </article>
  );
}

export default function LlmopsDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">LLMOps deep dive — interview-grade explanations</h1>
          <p className="page-subtitle">
            Each capability uses the 8-lens template: core concept · 5W ·
            input→process→output · flowchart · sequence · challenges +
            solutions · edge cases + solutions · limitations · next
            evolution · interview line.
          </p>
        </div>
      </div>

      {/* Master template summary — UniversalDeepDive view of the page theme */}
      <UniversalDeepDive t={LLMOPS_MASTER_SUMMARY} />

      {/* Table of contents — quick jumps. */}
      <div className="card">
        <strong>Capabilities ({CAPABILITIES.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18, columnCount: 2, columnGap: 24 }}>
          {CAPABILITIES.map((c) => (
            <li key={c.slug}>
              <a href={`#${c.slug}`} style={{ color: '#1e3a8a' }}>
                {c.title}
              </a>{' '}
              <span className={statusBadgeClass(c.status)}>{c.status}</span>
            </li>
          ))}
        </ul>
      </div>

      {CAPABILITIES.map((cap) => (
        <CapabilitySection key={cap.slug} cap={cap} />
      ))}

      <div className="card" style={{ backgroundColor: '#f3f4f6' }}>
        <strong>Final senior-level summary</strong>
        <p style={{ marginTop: 8, fontStyle: 'italic' }}>
          &ldquo;The system is strongest in prompt governance, resilience,
          auditability, and regression control. Runtime execution is
          well-structured: requests resolve prompts, retrieve context, call
          models, and safely degrade into draft-and-replay workflows when
          tool execution fails. Observability and correlation are also
          strong. The main maturity gap is LLMOps asset management:
          datasets, models, experiments, and deployments are not yet fully
          treated as first-class versioned registries.&rdquo;
        </p>
      </div>
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/tracing/deep#trace-draft-audit-linkage', label: 'Trace → draft → audit by request_id', why: 'AI decision audit row keyed by request_id; baggage propagates request_id across every hop' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Hard-stop #6 (untested AI)', why: 'no eval gate green = NO-GO regardless of other green; LLMOps eval registry IS the gate' },
          { href: '/admin/security/deep#owasp-stride-ai-threats', label: 'OWASP A11–A15 (AI threats)', why: 'prompt injection / output handling / model theft / excessive agency — guardrails enforce' },
          { href: '/admin/post-release/deep#pdv-monitoring', label: 'AI signals during PDV', why: 'eval drop / hallucination burst / token cost spike — auto-rollback or flag-disable triggers' },
          { href: '/admin/cicd/deep#cicd-master-pipeline', label: 'AI eval gate in CI/CD', why: 'regression eval set + threshold blocks promote; prompt + model versioned in registry' },
        ]}
      />
    </>
  );
}
