# Phase 6 — MCP + Agentic Scenarios

**Status:** Stub + execution plan. **No MCP code in the repo yet.** This is the single biggest gap from the brutal reviews.

## What must be built (in order)

1. `mcp/` package
   ```
   mcp/
     client.py           # agent-side MCP client
     schema/
       tool_schema.json  # MCP tool contract (shared)
     server_itsm.py      # first MCP server — create ticket
     server_hr.py        # second MCP server — leave request
     server_finance.py   # third — expense
   ```
2. Tool permission matrix in `governance.mcp_tool_permissions` — (tenant, role, tool) → allow/deny.
3. Agent-Loop CB integration when the agent calls MCP tools.
4. Audit row in `governance.audit_log` per MCP call — request + response + outcome.

## Agentic scenario catalog (13)

### A. Knowledge + reasoning
- **1 Multi-step research agent** — retrieve → graph expand → refine query → synthesize.
- **2 Self-refining RAG agent** — detect low confidence → re-query with refined prompt.
- **3 Comparative analysis agent** — multi-source retrieval → structured comparison output.

### B. Action-oriented (highest business value)
- **4 IT helpdesk agent** — retrieve policy (RAG) + MCP: create ticket in ITSM.
- **5 Finance / expense agent** — validate rules + MCP: submit expense.
- **6 HR workflow agent** — HR Q&A + MCP: submit leave request.

### C. Multi-agent collaboration
- **7 Planner + Executor** — Planner breaks task → Retriever fetches → Executor acts → Validator checks.
- **8 Debate / Verification** — multiple agents generate answers, one critiques, one consolidates.

### D. Autonomous loops
- **9 Iterative tool agent** — plan → call tool → observe → re-plan. **Max iterations REQUIRED (Agent-Loop CB).**
- **10 Monitoring agent** — watches logs/metrics → triggers remediation (triggers MCP tool).

### E. Enterprise control
- **11 Governance agent** — checks compliance, blocks unsafe output.
- **12 Cost optimization agent** — tracks tokens, dynamically switches models.
- **13 Incident response agent** — detects failure → triggers fallback → notifies.

## MCP scenario catalog (14)

### A. Tool invocation
- **1 Create ticket** — agent → MCP client → ITSM → ticket ID.
- **2 Query database** — agent → MCP → SQL / warehouse → structured data.
- **3 File access** — agent → MCP → SharePoint / S3 → document.

### B. Data enrichment
- **4 External API enrichment** — weather / stock / pricing → enriched answer.
- **5 Real-time lookup** — live system data merged with historical RAG.

### C. Workflow execution
- **6 Multi-step workflow** — create → approve → update.
- **7 Approval flow** — MCP triggers approval → waits on human → resumes.

### D. Async / event-driven
- **8 Async job submission** — submit → job ID → poll status.
- **9 Event-triggered action** — Kafka event → MCP → downstream system.

### E. Security / governance
- **10 Permission enforcement** — MCP validates role before executing.
- **11 Audit logging** — every MCP call logged in governance.audit_log.

### F. Failure & resilience
- **12 MCP circuit breaker** — MCP OPEN → draft-only fallback.
- **13 Retry + idempotency** — safe retries via Idempotency-Key header.

### G. Multi-tool
- **14 Tool orchestration** — DB + API + workflow tools combined by orchestrator.

## Phase-6 exit criteria

- [ ] `mcp/client.py` + at least one `mcp/server_*.py` working end-to-end in docker-compose.
- [ ] Tool schema JSON validated in CI.
- [ ] Permission matrix table populated for at least one tenant.
- [ ] Agent-Loop CB integration test: deliberate infinite-loop prompt → breaker opens at N iterations → HITL queue entry created.
- [ ] Happy path demo: "create a ticket for the HR policy I just retrieved" — end-to-end with ticket ID returned.
- [ ] Failure demo: kill MCP server mid-flow → draft persisted in `governance.hitl_queue`.
