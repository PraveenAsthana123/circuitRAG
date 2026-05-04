# Full-Stack Architecture — PolisAI + Paperclip + Council + OpenClaw

> Canonical architecture decision. Supersedes the loose layering in
> [ADR-012](adr/012-orchestration-layer-local-first.md) by adding
> **PolisAI** (the policy layer), positioning **Paperclip** explicitly
> as sandbox-only, naming the **5-role Agent Council**, and reserving
> the **OpenClaw** layer for heavy-autonomy A2A coordination.

## The 11-layer request path

```
User / Business App
   ↓
1.  API Gateway                  [services/api-gateway/]
       SSO | RBAC | Rate Limit | Tenant Check
   ↓
2.  Agent Router                 [TODO — not yet built]
       Intent Classification | Risk Classification
   ↓
3.  PolisAI / Policy Layer       [scripts/policy_check.py + config/policies/]
       PII | Compliance | Ethical AI | Allowed Tools | Human Approval
   ↓
4.  Agent Council                [scripts/local_council.py]
       Planner | Retriever | Risk | Evaluator | Writer
   ↓
5.  Agent Execution Layer        [services/agent-orchestrator-svc/]
       LangGraph | (CrewAI / AutoGen as future swap-ins)
   ↓
6.  Paperclip Sandbox Layer      [scripts/paperclip_manager.py — Stage 1]
       Autonomous research loop ONLY.
       Goal → Plan → Execute → Evaluate → Improve
       NOT for production-mutation. Drill-locked: no write authority.
   ↓
7.  MCP Tool Layer               [mcp/server_*.py — 8 servers]
       Databricks | APIs | Vector DB | Neo4j | CRM | ERP | Search
   ↓
8.  RAG + Data Layer             [services/retrieval-svc/ + ingestion-svc/]
       LangChain | (LlamaIndex / Haystack as swap-ins)
       Vector DB (Qdrant) | Knowledge Graph (Neo4j) | Lakehouse
   ↓
9.  Governance + Evaluation      [TODO — none installed]
       Guardrails AI | Ragas | Giskard | Lakera | Rebuff
   ↓
10. Observability                [Langfuse + OTel + Jaeger + Prom + Grafana]
       Langfuse | (MLflow swap-in) | OpenTelemetry
   ↓
11. OpenClaw                     [TODO — heavy-autonomy A2A coordination]
```

## Placement table — what each layer guarantees

| Component       | Placement                  | Guarantee                                           | §-policy |
|-----------------|---------------------------|-----------------------------------------------------|----------|
| **PolisAI**     | Before agent execution    | Default-deny law/policy gate                       | §38 §42 §47 §48.4 |
| **Agent Council** | Decision layer (pre-exec) | Prevents single-agent bad decisions                | §40 §47  |
| **LangGraph**   | Execution layer            | Stateful production workflows                       | §47      |
| **MCP**         | Tool access                | Standard contract for tool/data calls               | §50      |
| **RAG**         | Knowledge                  | Grounds answers in enterprise data                  | §39 §45  |
| **Paperclip**   | Sandbox ONLY               | Autonomous research; **not for production-mutation** | §42 §43  |
| **Guardrails / Ragas / Giskard** | Evaluation       | Hallucination, safety, quality checks              | §39 §48  |
| **Langfuse / OTel** | Observability         | Traces, cost, scores, failures                     | §47.6    |
| **OpenClaw**    | Heavy-autonomy A2A         | Multi-agent delegation across services              | §40      |

## What's shipped vs what's missing

| Layer | Component | Status | Path |
|-------|-----------|--------|------|
| 1     | API Gateway | ✅ shipped | [services/api-gateway/](../../services/api-gateway/) |
| 2     | Intent + Risk classifier | ❌ missing | — |
| 3     | PolisAI policy engine | ✅ Stage-1 (drill 8/8) | [scripts/policy_check.py](../../scripts/policy_check.py) |
| 3     | Policy file (8 default-deny rules) | ✅ shipped | [config/policies/agent_dispatch.json](../../config/policies/agent_dispatch.json) |
| 3     | OPA + Rego (Stage-2 swap) | ⚠️ pending — Tier 6 #6.1 | — |
| 4     | Agent Council (4-role: AUTHOR/REVIEWER/ADVISOR/RESEARCHER) | ✅ shipped | [scripts/local_council.py](../../scripts/local_council.py) |
| 4     | 5-role council (Planner/Retriever/Risk/Evaluator/Writer) | ⚠️ rename or alias needed | — |
| 5     | LangGraph DAG | ✅ shipped | [services/agent-orchestrator-svc/app/langgraph_flow.py](../../services/agent-orchestrator-svc/app/langgraph_flow.py) |
| 6     | Paperclip Stage-1 (read-only aggregator) | ✅ shipped | [scripts/paperclip_manager.py](../../scripts/paperclip_manager.py) |
| 6     | Paperclip Stage-2 (propose-only loop) | ⚠️ pending | — |
| 6     | Paperclip Stage-3 (full Goal→Plan→Execute→Evaluate→Improve) | ⚠️ pending | — |
| 7     | MCP tool servers (8) | ✅ shipped | [mcp/server_*.py](../../mcp/) |
| 8     | RAG + retrieval | ✅ shipped | [services/retrieval-svc/](../../services/retrieval-svc/) |
| 8     | Vector DB (Qdrant 1.11) | ✅ shipped | docker-compose.yml |
| 8     | Knowledge graph (Neo4j 5.21) | ✅ shipped | docker-compose.yml |
| 9     | Guardrails AI | ❌ missing | — |
| 9     | Ragas / DeepEval | ❌ missing — Tier 6 #6.2 | — |
| 9     | Giskard | ❌ missing | — |
| 9     | Lakera + Rebuff (prompt injection defense) | ❌ missing | — |
| 10    | Langfuse | ✅ shipped | docker-compose.yml |
| 10    | OpenTelemetry | ✅ shipped | docker-compose.yml |
| 10    | MLflow | ❌ not used (Langfuse covers LLM obs) | — |
| 11    | OpenClaw A2A coordinator | ❌ missing — see ADR-012 §3 | — |

## Why the layer ordering matters

**PolisAI MUST come before Agent Council**, not after. If policy fires
*after* agents have already planned and decided, you get a "we already
generated the answer; now decide if we're allowed to" anti-pattern that
leaks compute and risks data exposure. Policy gates the actor + tool +
scope BEFORE the council fires.

**Paperclip MUST be after Agent Execution, in sandbox**. The Goal →
Plan → Execute → Evaluate → Improve loop is a *meta-agent* that orbits
the production execution path; it's not in the request critical path.
A Paperclip loop that mutates production state without going through
PolisAI + Council has no audit row — that's a §38 / §48.4 violation
waiting to happen.

**OpenClaw is the OPPOSITE of Paperclip**. Paperclip = sandbox,
read-only-by-contract, manager-layer visibility. OpenClaw = heavy
autonomy, full A2A delegation, agents-driving-agents. They share one
thing: both go through PolisAI first.

## Sandbox-only contract for Paperclip

Stage-1 enforces sandbox-only via four drill-locked invariants:

1. **No write-style function names** in the source (regex-prevented).
   No `def push_*`, `def dispatch_*`, `def write_*`, `def update_*`,
   `def mutate_*`, `def delete_*`. Aggregators only.
2. **No outbound HTTP imports** — `httpx`, `requests`, `aiohttp`,
   `urllib3`, `urllib.request` are all absent. Offline-runnable.
3. **Write verbs refused** — `push`, `dispatch`, `assign`, `escalate`,
   `apply`, `merge`, `deploy`, `rollback`, `promote` all return a
   §42-cited refusal payload with exit code 2.
4. **Snapshot does not mutate `.loop/`** — drill verifies worktree
   byte-identical before and after a snapshot run.

Stage-2 (propose-only) and Stage-3 (gated delegation) compose on top
of this contract — never by relaxing it. If Stage-2 needs to write
state, it goes through PolisAI + MCP scope tokens, not by adding
`def write_*` to Paperclip.

## OpenClaw — the missing piece

OpenClaw is the layer that lets agents delegate to other agents
across services. The A2A protocol needs:

1. **Agent registry** — capability + scope tokens per agent
   ([services/agent-orchestrator-svc/app/agent_registry.py](../../services/agent-orchestrator-svc/app/agent_registry.py)
   has the foundation).
2. **Dispatch contract** — message envelope with `requesting_agent`,
   `target_agent`, `task`, `scopes_required`, `correlation_id`.
3. **Policy check on dispatch** — every A2A call goes through PolisAI
   first; if `requesting_agent` doesn't have `delegate:<target_agent>`
   scope, denied.
4. **Audit row** — every dispatch (allow + deny) in `.loop/openclaw_audit.jsonl`
   per §38 / §48.4.

OpenClaw Stage-1 = the dispatch contract + drill, with `Policy → MCP`
as the actual delegation path. Stage-2 = full multi-agent task graph.

## Composes with

- [ADR-012 — orchestration layer local-first](adr/012-orchestration-layer-local-first.md) — refined here
- [§38 decision audit](../../CLAUDE.md#38-mandatory--ai-production-governance-every-project)
- [§42 gated operations](../../CLAUDE.md#42-global-operational-autonomy--all-bash-commands-approved)
- [§43 drill discipline](../../CLAUDE.md#43-mandatory--drill-testing-pattern-every-project)
- [§47 architecture & design patterns](../../CLAUDE.md#47-mandatory--architecture--design-patterns-every-system)
- [§48.4 audit row schema](../../CLAUDE.md#48-mandatory--ai-explainability--interpretability-every-ai-feature)
- [Paperclip Stage-1 commit `3fb3679`](../../scripts/paperclip_manager.py)
- [PolisAI Stage-1 commit (this iteration)](../../scripts/policy_check.py)
