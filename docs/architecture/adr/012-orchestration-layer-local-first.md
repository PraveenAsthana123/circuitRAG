# ADR-012: Orchestration stays local; defer external frameworks

## Status

Accepted — design decision recorded in this commit, no code change.

## Context

The agentic-orchestration ecosystem has many adjacent tools:

* **Paperclip** — control plane for teams of agents; goal/task
  orchestration; org-style hierarchy; budget tracking; manager UI.
* **OpenClaw** — heavy-autonomy A2A coordination.
* **LangGraph / AutoGen** — agent workflow frameworks.
* **Flowise** — visual workflow builder.
* **CrewAI** — multi-agent role orchestration.
* **Vapi** — voice-agent platform.

The temptation, especially at "AI OS" scope, is to adopt one of these
frameworks as the orchestration layer and reduce this repo to "the
backend the framework calls." That's a category mistake. Each of these
tools owns a different layer:

* This repo owns the **execution + governance + retrieval + control-
  plane substrate**: MCP, drafts, replay, breakers, audit, RLS, RAG.
* Paperclip-class tools own a **management/visibility layer above** an
  execution substrate.
* LangGraph-class frameworks own a **workflow shape**, not a substrate.
* MCP itself is a **contract** for tool/action boundary, not a
  framework.

The reviewer's "brutal architecture truth" framing: do not treat
these as the same layer.

## Decision

Orchestration stays local — `services/inference-svc/app/services/
agent.py` and `app/agents/multi_hop_agent.py` — until the existing
control-plane surfaces are mature. Defer external orchestration
frameworks.

Specifically:

* **Use now (load-bearing):** MCP for tool/action contract;
  CircuitBreaker for resilience; AuditWriter for governance trail;
  PostgresIdempotencyStore for retry safety; per-tenant audit chain.
* **Use now (light):** LangGraph-style workflow *thinking* in code,
  not the framework dependency.
* **Consider later (manager UX):** Paperclip as a higher-level agent
  manager / business-facing dashboard. Useful AFTER:
  * the operator admin dashboard is mature (commit `83fca90` is
    v1; backlog age, replay queue, audit-failure rate need to land
    before a manager UI is more than decoration);
  * eval pipeline exists (no point managing agents whose quality
    you can't measure);
  * Langfuse-class AI observability is wired (see ADR-014 future).
* **Consider later (multi-agent):** AutoGen / CrewAI when the
  single-agent + MCP loop demonstrably hits a wall. Today it does
  not.
* **Defer until justified:** OpenClaw, A2A-heavy autonomy. These
  add governance complexity (multi-agent action attribution, cross-
  agent audit) that this repo's foundation isn't ready to support.
  Adopting them before governance is mature creates the silent-
  failure modes the audit chain was built to prevent.
* **Defer until justified:** Flowise / visual builders. The repo's
  developer experience is code-first; visual-builder ergonomics
  serve a different user (citizen developer) than the current
  audience (platform engineers).

## Consequences

* The orchestration code stays in `services/inference-svc/`. PRs
  that propose adding a framework dependency get reviewed against
  this ADR.
* When a framework IS adopted, the criterion is "we hit a
  documented wall in single-agent + MCP" — not "the framework is
  newer." Future ADR will record the wall + the choice.
* MCP's contract is the integration seam. Any future external
  orchestrator (Paperclip, AutoGen) integrates by *calling MCP
  tools*, not by replacing the MCP server. The audit + breaker +
  draft path stays load-bearing regardless of who's driving.
* The reviewer's "brutal stack" recommendation is preserved
  literally:
    * Use now: MCP, LangGraph-style workflow thinking, Langfuse/
      Phoenix (observability, future ADR).
    * Consider later: Paperclip as management UI / control layer.
    * Do not prioritize yet: OpenClaw / A2A-heavy autonomy.
