# ADR-027: Agent framework — LangGraph + custom council; CrewAI / Agno / PraisonAI rejected

## Status

Accepted — 2026-05-07. Re-evaluation triggered when **either** condition
in §Consequences fires.

## Context

The platform's agentic surface uses **LangGraph 1.1.10** as the
workflow orchestrator + a **custom 4-role council** (researcher /
author / reviewer / advisor) wired through `mcp/server_*.py` for tool
invocation + `documind_core` for RBAC, idempotency, audit, OTel.

Three popular alternative agent frameworks were evaluated:

- **CrewAI**: hierarchical-agent framework with role-based delegation
- **Agno**: lightweight multi-agent framework
- **PraisonAI**: orchestration layer over CrewAI/Autogen

All three were **rejected** in `scripts/techstack_audit.py` per §56
(techstack-additions policy). This ADR documents the empirical reasoning
+ defines the explicit re-eval triggers that would re-open the question.

ADR-027 is filed because the matrix-truth doc (`tier1-matrix-truth.md`)
listed Agent Council as a 4-role-vs-5-role question (closed by iter-34's
aliasing layer). The question of "which agent FRAMEWORK" was answered
implicitly across iterations but never recorded as an ADR. This file
closes that gap so a future maintainer asking "why no CrewAI?" finds
a documented answer instead of a tribal-memory one.

### What CrewAI / Agno / PraisonAI would give us

- Built-in agent-role abstractions (Agent, Task, Crew)
- Hierarchical delegation patterns (manager → workers)
- Agent-to-agent natural-language handoffs
- Pre-built integrations with OpenAI / Anthropic / etc.

### What we already have via LangGraph + custom council

- **LangGraph DAG workflows**: explicit state machines with branching,
  retries, parallel nodes, durable execution. Verified at
  `services/agent-orchestrator-svc/app/langgraph_flow.py`.
- **Custom 4-role council** (researcher / author / reviewer / advisor)
  in `scripts/local_council.py` with Pydantic schema validation per
  §55.3 (CouncilProposal contract). 5-role aliases (Planner / Retriever /
  Risk / Evaluator / Writer) added in iter-34 — same model lanes.
- **MCP server fleet** (10+ servers as of iter-61) for tool invocation
  with shared RBAC + idempotency + audit per §47.
- **OpenClaw A2A** envelope contract for agent-to-agent dispatch with
  policy gating per §47.6 + ADR-025 (feature-flag-gated dual-write).
- **OPA/Rego** policy enforcement (drill_opa_approval_parity 9/9).
- **Reflection engine + human-review router** (iter-58/59) — closed
  feedback loop with empirical drift signals.
- **§38 governance audit** with claim-to-chunk citations (iter-57).

## Decision

**Stay with LangGraph + custom council. Reject CrewAI / Agno / PraisonAI.**

Empirical reasoning per §55.3 outcome-based contract:

| Concern | LangGraph + custom | CrewAI/Agno/PraisonAI |
|---|---|---|
| Schema validation per agent | ✅ Pydantic CouncilProposal | ⚠️ string-prompt-based |
| Per-step audit row | ✅ governance.audit_log | ⚠️ retrofitted |
| RBAC at tool boundary | ✅ MCP scope + JWT | ⚠️ wrap-around |
| Idempotency at tool call | ✅ Postgres-backed | ⚠️ retrofitted |
| OTel spans per role | ✅ via server_common | ⚠️ retrofitted |
| Pinned model routing | ✅ explicit per role | ⚠️ generic |
| Hallucination flag | ✅ citation linker (iter-57) | ⚠️ ad-hoc |
| Reflection-loop signal | ✅ drift engine (iter-58) | ⚠️ external |
| Rollback per workflow | ✅ Temporal-style replay | ⚠️ retrofitted |

Four of these (schema validation, RBAC, idempotency, OTel) are §38
governance MUSTs — without them we'd retrofit policy enforcement onto
a third-party framework, which §56 explicitly classifies as a higher
maintenance burden than building governance-first from primitives.

## Consequences

### Positive

- **Governance-first architecture preserved**: every primitive (RBAC,
  idempotency, audit, OTel, schema validation) is built into the
  council pattern, not bolted on.
- **No third-party agent-framework upgrade churn**: CrewAI/Agno/
  PraisonAI release frequently with breaking changes; staying on
  LangGraph + custom = fewer dependency-tree shocks.
- **Pinned-model routing**: each council role (researcher / author /
  reviewer / advisor) maps to an explicit Ollama model. CrewAI's
  agent-as-LLM-prompt abstraction obscures which model handles
  which step.
- **Local-first**: the council runs on local Ollama out-of-the-box;
  no API-key dependency for the default path.
- **Reflection loop integrates natively**: iter-58's reflection engine
  reads `.loop/issue_audit.jsonl` written by the council itself; no
  cross-framework adapter needed.

### Negative

- **No agent-role abstractions out-of-the-box**: each new role
  requires Pydantic schema + prompt template + audit wiring. CrewAI
  would let `Agent(role='QA tester')` work in 5 lines.
- **No hierarchical delegation primitive**: managers/workers patterns
  must be hand-built. This will become a real cost when the council
  grows beyond ~7 roles.
- **No pre-built provider integrations**: every new LLM provider
  (OpenAI, Anthropic, Cohere, etc.) needs an adapter. langchain-ollama
  + langchain-xai cover Ollama + xAI; everything else is custom.
- **Operator learning curve**: a new engineer joining the platform
  has to learn LangGraph + the custom council pattern instead of a
  community-documented framework like CrewAI.

### Re-evaluation triggers (file ADR-NNN superseding this)

ADR-027 is **automatically re-opened** when **either** trigger fires:

1. **Council exceeds 7 roles**: when the council grows beyond
   researcher / author / reviewer / advisor + the 5-role aliases
   (Planner / Retriever / Risk / Evaluator / Writer = 4 underlying
   models), hierarchical delegation patterns become structural
   debt. CrewAI's manager/worker abstraction becomes worth the
   governance retrofit cost.
2. **Cross-organization agent collaboration**: if agents from
   different organizations (e.g. partner-tenant agents calling our
   agents) become a real use-case, multi-agent protocols like A2A
   (already scaffolded via OpenClaw) need a richer message-passing
   surface than the current envelope. A community framework with
   formalized agent-to-agent semantics may be cheaper than extending
   OpenClaw further.

When either trigger fires, file ADR-NNN superseding this one. The new
ADR must include: empirical comparison of governance-retrofit cost vs.
build-out cost, and explicit migration path for the existing 4-role
council.

## Alternatives considered

### A1. Adopt CrewAI as primary orchestrator (eager)
**Rejected**: 4 governance MUSTs (RBAC, idempotency, audit, OTel)
would be retrofitted; iter-27 already uninstalled crewai per §56's
rejected-verdict policy. Drill `drill_techstack_audit` step 5 locks
this.

### A2. Adopt Agno (lightweight alt to CrewAI)
**Rejected**: same governance-retrofit concerns. Agno's Stage-1
maturity makes it a moving target; LangGraph 1.1.10 has settled.
`drill_techstack_audit` rejected list includes Agno explicitly.

### A3. Adopt PraisonAI (orchestrator over CrewAI/Autogen)
**Rejected**: PraisonAI wraps CrewAI+Autogen; we'd inherit BOTH
governance gaps. PraisonAI is also early-stage relative to LangGraph.

### A4. Move to LangChain agents (full LangChain agent framework)
**Deferred**: LangChain agent framework has the same governance gaps
as CrewAI (string-prompt-based, retrofitted RBAC). We use langchain
ONLY for ChatXAI/ChatOllama wrappers in `scripts/chatxai_fallback.py`,
not for the agent orchestration layer. If LangChain adds first-class
governance hooks, re-evaluate.

### A5. Build agent framework from scratch (full custom)
**Rejected**: LangGraph already provides the workflow DAG / state /
retry primitives. Building those from scratch would be reinventing
LangGraph for no governance gain. The current shape — LangGraph +
custom council — is the right boundary.

## References

- `docs/architecture/adr/025-feature-flag-gated-dual-write.md`
  (§47.7 expand-phase; same iteration cadence the council follows)
- `docs/architecture/adr/026-mlflow-deliberate-not-now.md`
  (parallel deliberate-not-now decision; same re-eval-trigger pattern)
- `docs/architecture/tier1-matrix-truth.md` (matrix reconciliation
  showing LangGraph as primary; landed `981b06c`)
- `mcp/tests/drill_techstack_audit.py` (locks crewai/agno/praisonai
  rejected verdict; ALL 8 STEPS PASSED at iter-27)
- `mcp/tests/drill_council_5_role_aliasing.py` (locks the 5-role
  alias layer; ALL 7 STEPS PASSED at iter-34)
- `mcp/tests/drill_ai_integrations.py` (locks crewai NOT importable
  per §56; reconciled at iter-27 commit `3a56796`)
- iter-27 commit `3a56796` — uninstalled crewai per §56 rejected verdict
- iter-34 commit `4a89ec7` — 5-role aliasing layer over the 4-role council
- iter-58 commit `6259e14` — reflection engine reads council audit
- CLAUDE.md §38 (governance) + §47 (architecture) + §47.6 (security:
  governance-first) + §55.3 (outcome-based contract) + §56 (techstack
  additions: rejected = NOT installed)
