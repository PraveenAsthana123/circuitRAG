# Phase 6 — MCP + Agentic Scenarios

**Status:** Specified — ZERO code yet. Biggest execution gap.

---

## 1. Filesystem layout to build

```
mcp/
├── client.py              # agent-side MCP client (tool discovery, invocation, idempotency)
├── schema/
│   └── tool_schema.json   # shared MCP tool contract (JSON Schema)
├── server_itsm.py         # server #1 — create/update tickets
├── server_hr.py           # server #2 — leave + policy lookup
├── server_finance.py      # server #3 — expense submission
└── tests/
    └── test_tool_orchestration.py
```

Tool permission matrix: `governance.mcp_tool_permissions` — (tenant, role, tool) → allow/deny. Every MCP call logs to `governance.audit_log`.

## 2. Agentic scenario catalog (13)

### A. Knowledge + reasoning
| # | Scenario | Flow |
| --- | --- | --- |
| 1 | Multi-step research agent | retrieve → graph-expand → refine query → synthesize |
| 2 | Self-refining RAG agent | detect low confidence → re-query with refined prompt |
| 3 | Comparative analysis | multi-source retrieval → structured comparison output |

### B. Action-oriented (highest business value)
| # | Scenario | Flow |
| --- | --- | --- |
| 4 | IT helpdesk | retrieve policy (RAG) → MCP: create ticket in ITSM |
| 5 | Finance / expense | validate rules → MCP: submit expense |
| 6 | HR workflow | HR Q&A → MCP: submit leave request |

### C. Multi-agent collaboration
| # | Scenario | Flow |
| --- | --- | --- |
| 7 | Planner + Executor | Planner breaks task → Retriever fetches → Executor acts → Validator checks |
| 8 | Debate / Verification | Multiple agents generate → critic → consolidator |

### D. Autonomous loops
| # | Scenario | Flow |
| --- | --- | --- |
| 9 | Iterative tool agent | plan → call tool → observe → re-plan (Agent-Loop CB caps depth) |
| 10 | Monitoring agent | watches logs/metrics → triggers MCP remediation |

### E. Enterprise control
| # | Scenario | Flow |
| --- | --- | --- |
| 11 | Governance agent | checks compliance, blocks unsafe output |
| 12 | Cost optimization agent | tracks tokens, dynamically switches models |
| 13 | Incident response agent | detects failure → triggers fallback → notifies |

## 3. MCP scenario catalog (14)

### A. Tool invocation
- **1 Create ticket** — agent → MCP client → ITSM → ticket ID.
- **2 Query database** — agent → MCP → SQL / warehouse → structured data.
- **3 File access** — agent → MCP → SharePoint / S3 → document.

### B. Data enrichment
- **4 External API enrichment** — weather / stock / pricing → enrich answer.
- **5 Real-time lookup** — live system data merged with historical RAG.

### C. Workflow execution
- **6 Multi-step workflow** — create → approve → update.
- **7 Approval flow** — MCP triggers approval → waits on human → resumes.

### D. Async / event-driven
- **8 Async job submission** — submit → job ID → poll status.
- **9 Event-triggered action** — Kafka event → MCP → downstream system.

### E. Security / governance
- **10 Permission enforcement** — MCP validates role before executing.
- **11 Audit logging** — every MCP call logged in `governance.audit_log`.

### F. Failure & resilience
- **12 MCP circuit breaker** — MCP OPEN → draft-only fallback.
- **13 Retry + idempotency** — safe retries via `Idempotency-Key` header.

### G. Multi-tool
- **14 Tool orchestration** — DB + API + workflow tools combined by orchestrator.

## 4. MCP trust boundary

| Boundary | Risk | Required control |
| --- | --- | --- |
| Agent → MCP server | Tool misuse | Allowlisted tools per (tenant, role) |
| MCP server → enterprise system | Real-world action | Scoped credentials, never shared |
| User → action request | Unauthorized action | RBAC/ABAC at gateway |
| Agent memory → tool call | Prompt-injection carryover | Sanitize agent state |
| Tool result → model context | Poisoned output | Validate result before appending to context |
| Eval agent → prod tool | Accidental real action | **Block write tools from eval traffic** |

## 5. Agent loop controls (non-negotiable)

| Control | Why |
| --- | --- |
| `max_iterations` | Prevent infinite loops |
| `max_tool_calls` | Prevent runaway execution |
| `max_cost_per_task` | Control token / tool spend |
| `max_time_per_task` | Protect SLA |
| Tool allowlist | Prevent unsafe execution |
| `Idempotency-Key` per action | Avoid duplicate side effects |
| Approval gate | High-risk workflow control |
| Audit every action | Compliance evidence |

Enforced by `AgentLoopCircuitBreaker` in `libs/py/documind_core/breakers.py`.

## 6. MCP + circuit breaker

| Failure | Breaker behavior | User-safe fallback |
| --- | --- | --- |
| MCP server down | MCP CB OPEN | Draft action only |
| Enterprise API slow | Timeout + CB | Queue action |
| Tool returns 5xx | Retry with idempotency | Stop after retry limit |
| Tool result invalid | Block continuation | Ask user to verify |
| Approval system down | Fail closed | No high-risk action |
| Audit unavailable | Block regulated action | Allow read-only Q&A |

## 7. MCP + Kafka integration

| Scenario | Kafka topic |
| --- | --- |
| Long-running tool action | `mcp.tool.requested.v1` |
| Tool completion | `mcp.tool.completed.v1` |
| Tool failure | `mcp.tool.failed.v1` |
| Human approval needed | `approval.requested.v1` |
| Retry action | `mcp.tool.retry.v1` |
| DLQ | `mcp.tool.dlq.v1` |
| Audit of every MCP call | `audit.event.v1` |

## 8. Exit criteria

- [ ] `mcp/client.py` + at least one `mcp/server_*.py` working end-to-end in docker-compose.
- [ ] `mcp/schema/tool_schema.json` validated in CI.
- [ ] `governance.mcp_tool_permissions` populated for the demo tenant.
- [ ] Agent-Loop CB integration test: deliberate infinite-loop prompt → CB opens at N iterations → HITL queue entry created.
- [ ] Happy-path demo: "create a ticket for the HR policy I just retrieved" — end-to-end with ticket ID returned.
- [ ] Failure demo: kill MCP server mid-flow → draft persisted in `governance.hitl_queue`; agent returns "queued, not submitted".

## 9. Brutal checklist

| Question | Required |
| --- | --- |
| Can MCP tools be listed and permissioned? | Yes |
| Can agent execute only allowlisted tools? | Yes |
| Can high-risk actions require approval? | Yes |
| Can duplicate tool actions be prevented? | Yes — idempotency key |
| Can MCP failure degrade safely? | Yes — draft-only fallback |
| Can tool result be validated before using it? | Yes |
| Can all actions be audited? | Yes |
| Can eval traffic be blocked from prod tools? | Yes — separate tool namespace |
