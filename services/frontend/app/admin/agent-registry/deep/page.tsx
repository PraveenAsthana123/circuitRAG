'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'agent-registry-orchestrator',
    title: '1. Agent registry (orchestrator agents — manager / worker / reviewer / advisor)',
    status: 'shipped',
    coreConcept: 'A canonical registry of agent roles in the agent-orchestrator service. Four shipped role classes — coder_executor (manager), worker, reviewer, security_advisor — each with a versioned prompt template, scope grant, idempotency key, and audit row schema. The registry IS the source-of-truth for which agents exist; LangGraph routes plan steps to roles by role_id.',
    problem: 'Without a central registry, agents accrete ad-hoc — different files, different audit shapes, different scope-grant patterns. Operators have no canonical answer to "which agents exist, what can each do, what does each log?" The first day of incident response wastes 30 minutes mapping the agent graph from code.',
    whyThisApproach: 'AgentRoleSpec dataclass is the typed registry: role_id + prompt_template_path + tool_grants + audit_schema. New agents add a row; orchestrator picks them up via DEFAULT_AGENT_SPECS. PR diff for "did we add a new agent?" is one file, one tuple entry. Auditors scan the registry, not the codebase.',
    whenToUse: ['Multi-agent orchestration with role-distinct responsibilities', 'Auditable agent fleets where role + scope + prompt versioning is required', 'Plan-step routing by role rather than function call', 'Onboarding (new engineer reads registry to learn agent landscape)'],
    whenNotToUse: ['Single-agent systems (registry overhead with no payoff)', 'Throwaway exploratory prompts (no governance bar)', 'Agents that change role mid-task (registry is per-role, not per-task)'],
    input: 'role_id + plan step + tool_grants + prompt_version',
    process: [
      'Orchestrator receives plan step with target role_id',
      'Look up role_id in DEFAULT_AGENT_SPECS → returns AgentRoleSpec',
      'Spec carries: prompt_template_path, allowed tools, audit schema, retry budget',
      'LangGraph instantiates the agent class (ManagerAgent / WorkerAgent / ReviewerAgent / SecurityAdvisor)',
      'Agent runs with the spec\'s scope; produces decision + audit row',
      'Audit row written via postgres_store with role_id + prompt_version captured',
    ],
    output: 'Per-step agent run with role-typed audit trail.',
    flowchart: `flowchart LR
  step[Plan step] --> reg[(AgentRoleSpec registry)]
  reg --> spec[AgentRoleSpec]
  spec --> cls{role_id?}
  cls -->|coder_executor| mgr[ManagerAgent]
  cls -->|worker| wkr[WorkerAgent]
  cls -->|reviewer| rev[ReviewerAgent]
  cls -->|security_advisor| sec[SecurityAdvisor]
  mgr --> audit[(audit row + role_id)]
  wkr --> audit
  rev --> audit
  sec --> audit`,
    sequence: `sequenceDiagram
  autonumber
  participant LG as LangGraph
  participant R as AgentRoleSpec registry
  participant A as Agent instance
  participant PG as Postgres audit
  LG->>R: lookup(role_id)
  R-->>LG: AgentRoleSpec(role, prompt_path, tools)
  LG->>A: new(spec)
  A->>A: render prompt + bind tools (scope-restricted)
  A->>A: run via Ollama / cloud LLM
  A-->>LG: AgentOutput(decision, evidence)
  LG->>PG: write audit (role_id, prompt_version, decision)`,
    alternatives: [
      { name: 'Ad-hoc agent classes', tradeoff: 'No registry; audit shapes drift; operator burden in incident response' },
      { name: 'Role-as-string only', tradeoff: 'Cheaper; no type safety; new agent ships without audit schema' },
      { name: 'Plugin-based agent loading', tradeoff: 'More flexible; harder to audit; opens scope-creep risk' },
    ],
    challenges: [
      'Registry vs reality drift (an agent class without a registry entry)',
      'Prompt template path conventions (versioned vs latest)',
      'Tool-grant precision (scope leak through tool inheritance)',
      'Schema evolution (new audit fields without breaking existing readers)',
    ],
    edgeCases: [
      { case: 'Agent class without registry entry', solution: 'CI step asserts every agents.py class is referenced from registry' },
      { case: 'Two roles share the same prompt template', solution: 'Allowed; registry shape is per-role, not per-prompt' },
      { case: 'Role removed but plan step still references it', solution: 'Orchestrator returns 404 for unknown role; plan blocked with explicit error' },
    ],
    failureModes: [
      { mode: 'Drift — new agent class without registry entry', detect: 'CI agent-class-vs-registry diff fails', recover: 'Add registry entry; PR template requires it' },
      { mode: 'Tool scope leak', detect: 'Audit row shows tool not in spec.tool_grants', recover: 'Tighten tool binding; drill_agent_tool_scope locks' },
      { mode: 'Prompt template missing on disk', detect: 'agent run fails with FileNotFoundError', recover: 'Drill drill_agent_registry_prompt_paths catches' },
    ],
    monitoring: [
      'documind_agent_runs_total{role_id, outcome}',
      'documind_agent_runtime_seconds{role_id} (histogram)',
      'documind_agent_tool_invocations_total{role_id, tool}',
      '/admin/agentic plan-step view per role',
    ],
    testing: [
      'drill_agent_registry_completeness (PLANNED — every class has a spec)',
      'drill_agent_prompt_path_resolves (every spec.prompt_template_path exists)',
      'drill_agent_tool_scope (audit row tool ∈ spec.tool_grants)',
    ],
    security: [
      'Scope grant is the identity of "what this agent can do"',
      'Tool binding inherits scope; never auto-grants beyond spec',
      'Audit row carries role_id + prompt_version + tool_invocations',
      'Role removal is breaking — supersede via new role, never drop',
    ],
    scaling: [
      '10x: 4-10 roles; in-memory registry; sub-ms lookup',
      '100x: per-tenant role customization (extend DEFAULT with overrides)',
      'Cost driver: per-role audit row volume; archive completed plans',
    ],
    maturity: {
      mvp: 'Single agent class with no registry',
      production: '4 shipped roles with AgentRoleSpec registry + audit row + scope grant',
      enterprise: 'Per-tenant custom roles + role-versioning + cross-role compatibility matrix + automatic registry-vs-code drift detection',
    },
    limitations: [
      'No drill yet enforces registry-vs-class completeness',
      'Per-tenant role customization is roadmap',
      'Manager / Worker / Reviewer / SecurityAdvisor are hardcoded class hierarchy',
    ],
    projectFit: [
      'services/agent-orchestrator-svc/app/agent_registry.py — DEFAULT_AGENT_SPECS tuple',
      'services/agent-orchestrator-svc/app/agents.py — ManagerAgent / WorkerAgent / ReviewerAgent / SecurityAdvisor classes',
      'services/agent-orchestrator-svc/app/langgraph_flow.py — registry lookup at plan-step dispatch',
      '/admin/agentic + /admin/ai-orchestration/deep — operator surfaces',
    ],
    interviewLine: 'Agent registry is the source-of-truth for which agents exist + what each can do. AgentRoleSpec dataclass with role_id + prompt + tool grants + audit schema. New agents add a tuple entry; auditors read the registry, not the codebase. The registry IS the governance surface.',
    implementationSteps: [
      { step: 'AgentRoleSpec dataclass', logic: 'role_id + prompt_template_path + tool_grants + audit_schema; typed registry.' },
      { step: 'DEFAULT_AGENT_SPECS tuple', logic: 'Canonical list of 4 shipped roles; CI asserts no class drift.' },
      { step: 'LangGraph dispatch', logic: 'Plan step has role_id; orchestrator looks up spec and instantiates class.' },
      { step: 'Tool scope binding', logic: 'Agent constructor restricts tools to spec.tool_grants only.' },
      { step: 'Audit row schema', logic: 'role_id + prompt_version + tool_invocations[] persisted per run.' },
      { step: 'Drill the registry', logic: 'Three drills: registry completeness, prompt-path resolution, tool-scope correctness.' },
      { step: 'Per-tenant customization', logic: 'Future: tenant_overrides extend DEFAULT_AGENT_SPECS without modifying defaults.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/agent-orchestrator-svc/app/agent_registry.py
from dataclasses import dataclass

@dataclass(frozen=True)
class AgentRoleSpec:
    role_id: str
    prompt_template_path: str
    tool_grants: frozenset[str]
    audit_schema_version: str

DEFAULT_AGENT_SPECS: tuple[AgentRoleSpec, ...] = (
    AgentRoleSpec(
        role_id="coder_executor",
        prompt_template_path="prompts/manager_v3.j2",
        tool_grants=frozenset({"plan_create", "plan_update", "step_dispatch"}),
        audit_schema_version="v1",
    ),
    AgentRoleSpec(
        role_id="reviewer",
        prompt_template_path="prompts/reviewer_v2.j2",
        tool_grants=frozenset({"diff_read", "comment_add"}),
        audit_schema_version="v1",
    ),
    AgentRoleSpec(
        role_id="advisor",
        prompt_template_path="prompts/advisor_v2.j2",
        tool_grants=frozenset({"search", "cite_add"}),
        audit_schema_version="v1",
    ),
    AgentRoleSpec(
        role_id="security_advisor",
        prompt_template_path="prompts/security_advisor_v1.j2",
        tool_grants=frozenset({"scan_diff", "cve_lookup"}),
        audit_schema_version="v1",
    ),
)

def lookup(role_id: str) -> AgentRoleSpec:
    for spec in DEFAULT_AGENT_SPECS:
        if spec.role_id == role_id:
            return spec
    raise KeyError(f"unknown role: {role_id}")`,
    },
    starStory: {
      situation: 'Agent classes were accreting in agents.py without a central registry. Audit shapes diverged; tool grants were implicit; new engineers spent the first week mapping the agent landscape from code.',
      task: 'Type-safe registry that names every role + bounds its scope + canonicalizes the audit schema.',
      action: 'Built AgentRoleSpec + DEFAULT_AGENT_SPECS in agent_registry.py. LangGraph dispatches by role_id. Audit row carries role_id + prompt_version. CI assertion (planned) catches class-without-spec drift.',
      result: 'New-engineer onboarding: read registry, understand agent landscape in 5 minutes. Auditors: registry is the source of truth, not codebase scan. Adding a role is one file change.',
    },
    interviewTraps: [
      'Role-as-string with no spec (no scope; no audit schema; drift)',
      'Plugin-based agent loading without registry assertion (security blast radius)',
      'Hardcoded role hierarchy instead of configurable specs (per-tenant customization impossible)',
    ],
    finalScript: 'Agent registry turns "what agents do we have?" from a code-spelunking task into a registry lookup. AgentRoleSpec + DEFAULT_AGENT_SPECS is one tuple of frozen dataclasses; new agents add a row; CI asserts class-vs-registry consistency. The registry IS the governance surface — auditors read it, scope grants are bounded by it, audit rows reference it.',
  },
  {
    slug: 'sidecar-council-roles',
    title: '2. Sidecar council roles (chair / authors / cross-reviewer)',
    status: 'shipped',
    coreConcept: 'The sidecar advisor runs a 3-author + 1-cross-reviewer + 1-chair council pattern for PR-review event types. Each role has a distinct prompt template; the chair synthesizes author + reviewer outputs into final advice. Council members are NOT the same registry as the orchestrator agents — sidecar council is per-event-type, ephemeral, citation-driven.',
    problem: 'Single-LLM PR review produces plausible but uncited advice. Multiple LLM calls in series (author → reviewer → chair) catch each other\'s mistakes; the chair sees both author proposals + cross-reviewer pushback before producing final advice. Citation discipline propagates through the council chain.',
    whyThisApproach: 'Council pattern (3+1+1) is the sidecar\'s answer to single-LLM hallucination. Authors propose independently → cross-reviewer challenges → chair synthesizes. Each role\'s output goes into the next role\'s prompt; final advice has audit trail of every council member\'s position. Latency cost (~5 LLM calls per event) bought back via reduced operator review time + higher acceptance rate.',
    whenToUse: ['PR review (canonical sidecar use case)', 'Code-quality advisory where multiple perspectives improve precision', 'Anywhere single-LLM hallucinations have observable cost', 'High-stakes decisions where citation chain matters'],
    whenNotToUse: ['Simple Q&A (overkill)', 'Cost-sensitive paths (5x LLM cost)', 'Latency-critical paths (sequential calls dominate)'],
    input: 'event_type + content (PR diff, paste) + retrieval set + chair model selection',
    process: [
      'Sidecar receives event with event_type=pr_review',
      'Spawn 3 authors in parallel — each with distinct prompt template + retrieval set',
      'Authors produce independent proposals (with citations)',
      'Cross-reviewer receives all 3 proposals + retrieval set; challenges weakest claims',
      'Chair receives proposals + reviewer pushback + retrieval set; synthesizes final advice',
      'Chair output written to events table with author + reviewer + chair audit chain',
      'Operator sees final advice + can drill into per-role positions',
    ],
    output: 'Council advice + per-role audit chain + citation set.',
    flowchart: `flowchart LR
  ev[event] --> spawn[Spawn council]
  spawn --> a1[Author 1]
  spawn --> a2[Author 2]
  spawn --> a3[Author 3]
  a1 --> cr[Cross-reviewer]
  a2 --> cr
  a3 --> cr
  cr --> chair[Chair]
  chair --> out[Final advice + chain]
  out --> db[(events.advice_json)]`,
    sequence: `sequenceDiagram
  autonumber
  participant E as Event
  participant SC as Sidecar
  participant LLM as LLM pool
  E->>SC: event_type=pr_review
  par 3 authors in parallel
    SC->>LLM: prompt(author_v2, content)
  and
    SC->>LLM: prompt(author_v2, content)
  and
    SC->>LLM: prompt(author_v2, content)
  end
  LLM-->>SC: 3 proposals
  SC->>LLM: prompt(reviewer_v2, proposals + retrieval)
  LLM-->>SC: pushback
  SC->>LLM: prompt(chair_v3, proposals + pushback + retrieval)
  LLM-->>SC: final advice
  SC->>SC: write events with author + reviewer + chair chain`,
    alternatives: [
      { name: 'Single LLM call', tradeoff: 'Cheap; no cross-checking; higher hallucination rate' },
      { name: 'Two-pass (proposer + critic)', tradeoff: 'Cheaper than full council; loses author-diversity signal' },
      { name: 'N-author with majority vote', tradeoff: 'No synthesis; ties on judgement-call advice' },
    ],
    challenges: [
      'Latency (5 sequential LLM calls dominate)',
      'Author-diversity (same author prompt 3 times produces correlated proposals)',
      'Chair model selection (cloud Kimi → local-chair fallback per 6831dee)',
      'Citation propagation through chain (lost cites at any role break the chain)',
    ],
    edgeCases: [
      { case: 'Chair model 404 (Ollama tag missing)', solution: 'Fallback to local-chair model (6831dee); council degraded but operational' },
      { case: 'One author returns malformed JSON', solution: 'Drop that author; cross-reviewer + chair proceed with N-1 proposals' },
      { case: 'Cross-reviewer agrees with all authors', solution: 'Pushback empty; chair sees that and confidence-weights' },
      { case: 'Chair output truncates citations', solution: 'Drill drill_sidecar_pr_review_council enforces citation continuity' },
    ],
    failureModes: [
      { mode: 'Council times out', detect: 'duration_s > timeout; advice never written', recover: 'Per-role timeout + fallback chair model; partial advice if chair runs' },
      { mode: 'Citation chain breaks', detect: 'chair advice cites chunks not in any author proposal', recover: 'drill_sidecar_pr_review_council fires; tighten chair prompt' },
      { mode: 'Cost spike', detect: 'documind_advisor_cost_usd above budget', recover: 'Drop one author; reduce retrieval set size; switch to cheaper model' },
    ],
    monitoring: [
      'agent_board_run outcome=ok|fail',
      'duration_s per council run',
      'authors_total / authors_failed / reviews_total / reviews_failed',
      'documind_advisor_council_cost_usd',
    ],
    testing: [
      'drill_sidecar_pr_review_council (the canonical council drill)',
      'drill_sidecar_advisor_record_rating (council output → events table)',
      'drill_sidecar_chair_fallback (Ollama 404 → local-chair recovery; 6831dee)',
    ],
    security: [
      'Each role\'s prompt is registered + versioned (no inline string composition)',
      'Council audit chain immutable (events table append; rating updates separate)',
      'No PII in role prompts (advisor.py redacts on input)',
      'Chair model selection logged per run (audit trail)',
    ],
    scaling: [
      '10x: ~5 events/s tolerable with 5-LLM-call council',
      '100x: parallelize authors to single LLM with batched API; reduce serial chair',
      'Cost driver: chair model (Kimi-cloud is most expensive); fallback path keeps ops alive when cloud unreachable',
    ],
    maturity: {
      mvp: 'Single-LLM PR review',
      production: '3-author + cross-reviewer + chair council with prompt registry + cost tracking + Ollama fallback',
      enterprise: 'Per-tenant council customization + multi-language council members + reviewer feedback loop',
    },
    limitations: [
      'Authors share prompt template (correlated proposals; diversity is partial)',
      'Cost ~5x single-LLM call',
      'Latency dominated by sequential chair step',
    ],
    projectFit: [
      'services/sidecar-advisor/advisor.py — council orchestration',
      'services/sidecar-advisor/prompts/ — author / reviewer / chair templates',
      'services/sidecar-advisor/memory.py — events.advice_json persists chain',
      '/admin/sidecar/deep — operator surface',
    ],
    interviewLine: 'The sidecar council is 3-author + 1-cross-reviewer + 1-chair. Each role has a distinct prompt; outputs flow author → reviewer → chair, citations propagate through the chain. Chair synthesizes; latency cost is bought back via lower hallucination rate + higher operator acceptance.',
    implementationSteps: [
      { step: 'Per-role prompt templates', logic: 'authors/v2 + reviewer/v2 + chair/v3; versioned in services/sidecar-advisor/prompts/' },
      { step: 'Parallel author dispatch', logic: 'asyncio.gather across 3 authors; survives 1 failure' },
      { step: 'Cross-reviewer step', logic: 'Receives all proposals + retrieval set; produces pushback' },
      { step: 'Chair synthesis', logic: 'Receives proposals + pushback + retrieval; produces final advice with citations' },
      { step: 'Audit chain persisted', logic: 'events.advice_json holds author / reviewer / chair outputs in order' },
      { step: 'Chair fallback on 404', logic: '6831dee — local-chair model when cloud Kimi tag returns 404' },
      { step: 'Drill the council', logic: 'drill_sidecar_pr_review_council exercises full chain; locks citation continuity' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/sidecar-advisor/advisor.py — council orchestration sketch
async def run_council(event_type: str, content: str,
                     retrieval: list[dict]) -> dict:
    if event_type != "pr_review":
        return await run_single(event_type, content, retrieval)

    # 3 authors in parallel
    author_proposals = await asyncio.gather(
        run_role("author", content, retrieval),
        run_role("author", content, retrieval),
        run_role("author", content, retrieval),
        return_exceptions=True,
    )
    proposals = [p for p in author_proposals if not isinstance(p, Exception)]

    # cross-reviewer pushback
    pushback = await run_role("reviewer", proposals, retrieval)

    # chair synthesis (fallback to local-chair on cloud 404)
    try:
        advice = await run_role("chair", (proposals, pushback, retrieval),
                                model="kimi-cloud")
    except OllamaModelNotFoundError:
        advice = await run_role("chair", (proposals, pushback, retrieval),
                                model="local-chair")

    return {
        "advice": advice,
        "chain": {
            "authors": proposals,
            "reviewer": pushback,
            "chair_model": advice.model_used,
        },
    }`,
    },
    starStory: {
      situation: 'Single-LLM PR review produced plausible advice but operators caught hallucinations weekly. Citation chains stopped at the LLM boundary.',
      task: 'Council pattern that crosses-checks proposals + propagates citations through a synthesis chain.',
      action: '3-author + cross-reviewer + chair council orchestrated in advisor.py. Per-role prompt registry. Audit chain persisted in events.advice_json. Chair fallback to local-chair when cloud 404.',
      result: 'Hallucination rate dropped; operator acceptance climbed; full audit chain available per event. drill_sidecar_pr_review_council locks the contract; drill_sidecar_chair_fallback locks the 404 path.',
    },
    interviewTraps: [
      'Single-LLM advisor as production design (hallucination rate is the bottleneck, not latency)',
      'No chair fallback (cloud 404 = full council outage)',
      'Citation lost between roles (chain breaks; advice ungrounded)',
    ],
    finalScript: 'Sidecar council = 3 authors + cross-reviewer + chair, each with versioned prompt + citation propagation. Latency cost ~5 LLM calls; bought back via lower hallucination + higher operator acceptance. The chair is the synthesis seam; if it 404s on cloud Kimi, local-chair takes over (6831dee). Drill catalog: drill_sidecar_pr_review_council + drill_sidecar_chair_fallback. Without the council pattern, advisor advice is plausible noise; with it, advice is citation-traceable + auditable.',
  },
];

export default function AgentRegistryDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Agent registry deep dive</h1>
          <p className="page-subtitle">
            Two registries — orchestrator agents (manager / worker / reviewer
            / security advisor) and sidecar council (chair / authors / cross-
            reviewer) — explained through the universal 20-dimension framework.
          </p>
        </div>
      </div>
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/agentic/control-plane', label: 'Agentic control plane', why: 'orchestrator agent registry IS the control-plane source-of-truth; this page details the schema' },
          { href: '/admin/sidecar/deep', label: 'Sidecar deep-dive', why: 'sidecar council pattern is the canonical use of this registry; both pages compose' },
          { href: '/admin/memory/deep', label: 'Memory deep-dive', why: 'agent runs persist via postgres_store + sidecar memory; registry IDs are the audit row keys' },
          { href: '/admin/output-eval/deep', label: 'Output evaluation', why: 'council citation chain IS the hallucination guardrail; this page details the council pattern' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'no role registry = no scope-grant audit; release blocked per §38' },
        ]}
      />
    </>
  );
}
