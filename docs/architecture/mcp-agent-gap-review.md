# MCP Agent Gap Review

This note reviews what still appears missing around the MCP plus agent architecture in this repo.

The goal is not to restate what already exists.
The goal is to identify the highest-value gaps between:

- current MCP and agent mechanics

and:

- a more complete enterprise-grade operator and governance experience

Relevant supporting docs:

- [docs/architecture/mcp-agent-architecture-and-monitoring.md](/mnt/deepa/rag/docs/architecture/mcp-agent-architecture-and-monitoring.md)
- [docs/architecture/agent-decision-monitoring-and-communication.md](/mnt/deepa/rag/docs/architecture/agent-decision-monitoring-and-communication.md)

## 1. What Is Already Strong

This repo already has unusually strong MCP and agent foundations:

- explicit `AgentService` orchestration
- MCP client and server separation
- scope-aware tool execution
- degraded draft fallback
- replay and rejection flows
- breaker protection
- audit integration
- OTel and Prometheus direction

The main missing areas are no longer basic mechanics.
They are:

- operator visibility
- governance productization
- tool-level operational ownership
- traceability UX

## 2. Main Missing Areas

## 2.1 Operator dashboard

The backend has the primitives, but the operator experience is still thin.

Needed:

- per-tool health
- breaker state
- pending draft counts
- oldest pending draft age
- replay success and failure counts
- scope-denial counts
- audit failure counts

Why it matters:

Without this, the system is technically observable but operationally hard to manage.

## 2.2 Per-tool monitoring views

The repo exports useful MCP metrics, but those signals are not yet gathered into strong per-tool views.

Needed:

- success, error, degraded, and replay rates by tool
- latency by tool
- denial rates by tool
- draft-creation rate by tool
- replay-resolution rate by tool

Why it matters:

Operators and service owners need to reason about tool health at the tool level, not only at the service level.

## 2.3 Trace to draft to audit linkage

The current architecture carries correlation and audit context, but it still appears too hard to navigate between them.

Needed:

- request trace linked to tool call
- tool call linked to draft row
- draft row linked to replay event
- replay linked to audit row

Why it matters:

The system is strongest when a failure or action can be reconstructed end to end without code archaeology.

## 2.4 Prompt and tool decision explainability

The repo can explain the mechanics better than it can explain the decision.

Needed:

- why this tool was chosen
- why this tool was denied
- why degraded mode happened
- why replay succeeded or failed
- separation between user-facing explanation and operator-facing explanation

Why it matters:

Enterprise AI systems are hard to trust when they can act but cannot explain their action path clearly.

## 2.5 Registry and version visibility

The MCP and agent path should be connected to stronger versioning and registry surfaces.

Needed:

- prompt version
- model version
- retrieval config version
- tool contract version where relevant
- recent-change visibility

Why it matters:

When a behavior changes, operators need to answer:

- what changed
- when it changed
- whether the change correlates with failures or regressions

## 2.6 Threshold-driven control

The repo already has pieces of this, but more of the decision policy should be explicit and operational.

Needed:

- low confidence -> clarify or HITL
- poor retrieval -> degrade or narrow response
- unsafe output -> block
- repeated tool failure -> breaker and draft path
- audit write failure -> visible alert or operational follow-up

Why it matters:

A strong control plane turns conditions into decisions, not just logs.

## 2.7 Feedback loop

The system still needs a tighter feedback loop from real tool and agent outcomes back into improvement.

Needed:

- operator correction capture
- failed or poor action review
- degraded-case review
- replay outcome review
- link from incidents to eval and regression assets

Why it matters:

Without this, the system is observable but not strongly self-improving.

## 2.8 Ownership model

Per-tool ownership still appears under-defined.

Needed:

- tool owner
- monitoring owner
- alert owner
- audit expectation owner
- replay-policy owner
- on-call owner

Why it matters:

Tool ecosystems drift when ownership is unclear.

## 3. Highest-Value Missing Items

If reduced to the most important gaps:

1. operator dashboard
2. per-tool monitoring views
3. trace -> draft -> audit linkage
4. prompt, model, and retrieval registry visibility
5. stronger threshold-based routing
6. feedback and improvement loop
7. clearer ownership matrix

## 4. Suggested Priority Order

### Phase 1

- operator dashboard ✓ shipped (`services/frontend/app/admin/page.tsx`,
  commit `96f5d4b`)
- per-tool monitoring views — **primitives shipped**:
  - `documind_mcp_tool_calls_total{namespace,tool,outcome}` (existing)
  - `documind_mcp_tool_call_duration_seconds{namespace,tool}` —
    histogram, this commit
  - `documind_mcp_scope_denials_total{namespace,tool,reason}` —
    counter (reason ∈ {NOT_AUTHENTICATED, INVALID_TOKEN,
    INSUFFICIENT_SCOPE, UNKNOWN}), this commit
  - drill: `mcp/tests/drill_mcp_per_tool_telemetry.py`

  Still missing (next iteration): admin-dashboard panel that
  surfaces these per-tool views as a UI; an aggregation endpoint
  that bundles `{calls, latency_p95, denials, last_outcome}` per
  registered tool so the panel can render with one fetch.

- draft and replay backlog visibility ✓ shipped
  (`documind_draft_pending_age_seconds`, `documind_draft_replay_total`,
  surfaced via `/api/v1/health/detailed`)

### Phase 2

- trace -> draft -> audit linkage
- better explanation of tool decisions and denials

### Phase 3

- prompt/model/retrieval registry visibility
- threshold-driven routing policy expansion

### Phase 4

- feedback loop productization
- tool and alert ownership formalization

## 5. Bottom Line

The MCP and agent architecture in this repo is already stronger than most early AI systems.

The missing work is now mostly about:

- making the system easier to operate
- making decisions easier to explain
- making failures easier to trace
- making ownership and governance more explicit

That is the next maturity step.
