# Tool Reviews — Index

> Per `~/.claude/policies/brutal-tool-review.md`, every tool / agent / MCP server /
> shared library on the request hot path or holding production state must have a
> review file here.

## Reviewed tools

| Tool | File | Status | P0 count | P1 count |
|---|---|---|---|---|
| CircuitBreaker (the worked example) | [circuit-breaker.md](circuit-breaker.md) | ✅ shipped (was 5 P0; now 0 — see CB-A1..G commits) | 0 | 0 |
| LlmClient Protocol + Pool | [llm-client.md](llm-client.md) | 🔍 reviewed | 1 | 3 |
| StrategistAgent | [agents-strategist.md](agents-strategist.md) | 🔍 reviewed | 1 | 4 |
| ResearchAgent + mcp_research | [agent-research.md](agent-research.md) | 🔍 reviewed | 0 | 5 |
| TesterAgent + mcp_tests | [agent-tester.md](agent-tester.md) | 🔍 reviewed | 1 | 4 |
| DeployerAgent + mcp_deploy | [agent-deployer.md](agent-deployer.md) | 🔍 reviewed | 0 | 4 |
| ObserverAgent + mcp_observe | [agent-observer.md](agent-observer.md) | 🔍 reviewed | 0 | 3 |
| ReviewerAgent | [agent-reviewer.md](agent-reviewer.md) | 🔍 reviewed | 0 | 3 |
| ModelRouter | [model-router.md](model-router.md) | 🔍 reviewed | 0 | 2 |
| Idempotency module | [idempotency.md](idempotency.md) | 🔍 reviewed | 1 | 2 |
| Explainability module | [explainability.md](explainability.md) | 🔍 reviewed | 0 | 4 |
| MCP server stub pattern | [mcp-server-stub.md](mcp-server-stub.md) | 🔍 reviewed | 1 | 3 |
| InMemoryTaskStore | [in-memory-task-store.md](in-memory-task-store.md) | 🔍 reviewed | 1 | 1 |
| PostgresTaskStore | [postgres-task-store.md](postgres-task-store.md) | 🔍 reviewed | 1 | 3 |
| LangGraph DAG | [langgraph-flow.md](langgraph-flow.md) | 🔍 reviewed | 0 | 4 |

## Aggregate gap counts (post-CB fixes)

| Severity | Count across all reviewed tools |
|---|---|
| **P0 — will-break-prod** | **6** (mostly: timeouts, identity-boundary, idempotency-under-retry, memory-bounds) |
| **P1 — silent-degradation** | **41** (caching, retries, body-limits, slow-call detection across most agents) |
| **P2 — operational** | ~30 (mostly: operator overrides, dashboards, runbooks per tool) |
| **P3 — polish** | ~50 (callbacks, OTel, persistent state on non-CB tools) |

## How to read each review file

Each review uses the 40-row template from `_template.md`. Rows are grouped:
- **A (1-6)**: critical correctness — `✗` here means production-breaking
- **B (7-12)**: resilience — `✗` here means silent degradation
- **C (13-18)**: observability — `✗` here means incident-response gap
- **D (19-22)**: operator API — `✗` here means 3-AM-debugging gap
- **E (23-30)**: project-policy integration — `✗` here means audit / governance gap
- **F (31-40)**: cross-cutting — `✗` here means systemic gap

## How to add a new tool

```bash
cp _template.md <new-tool>.md
# walk all 40 rows; mark ✓/✗/n/a with justification
# add row to the table in this README
# open issues for every ✗ at P0/P1
```

## See also

- `~/.claude/policies/brutal-tool-review.md` — the methodology
- `_template.md` — the review template
- CLAUDE.md §43 — drill testing pattern (the lock mechanism)
- CLAUDE.md §47 — architecture surfaces
- CLAUDE.md §48 — explainability surfaces
