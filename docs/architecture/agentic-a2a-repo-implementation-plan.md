# Repo-Specific Implementation Plan — Agentic Orchestrator + Advisory Board + A2A

This plan adapts the generic multi-agent architecture to the current DocuMind repo.

It assumes we want:

- one bounded orchestration service
- MCP-backed tool execution
- reviewer and advisor agents
- auditability
- human approval for risky actions
- no uncontrolled agent-to-agent chatter

## 1. Existing repo pieces to reuse

### Shared Python core

Reuse:

- [libs/py/documind_core/agent_board.py](/mnt/deepa/rag/libs/py/documind_core/agent_board.py)
- [libs/py/documind_core/audit.py](/mnt/deepa/rag/libs/py/documind_core/audit.py)
- [libs/py/documind_core/observability.py](/mnt/deepa/rag/libs/py/documind_core/observability.py)
- [libs/py/documind_core/middleware.py](/mnt/deepa/rag/libs/py/documind_core/middleware.py)
- [libs/py/documind_core/circuit_breaker.py](/mnt/deepa/rag/libs/py/documind_core/circuit_breaker.py)

Why:

- `agent_board.py` already models `author -> reviewer -> advisor`
- audit and observability patterns are already standardized
- baggage propagation is already part of the repo contract

### MCP layer

Reuse:

- [mcp/client.py](/mnt/deepa/rag/mcp/client.py)
- [mcp/drafts.py](/mnt/deepa/rag/mcp/drafts.py)
- [mcp/server_common.py](/mnt/deepa/rag/mcp/server_common.py)

Why:

- the repo already has scoped tool execution
- idempotency and draft fallback already exist
- MCP is already the correct tool boundary for external actions

### Existing multi-agent example

Reuse as pattern source:

- [services/sidecar-advisor/council.py](/mnt/deepa/rag/services/sidecar-advisor/council.py)
- [services/sidecar-advisor/agents](/mnt/deepa/rag/services/sidecar-advisor/agents)

Why:

- it already shows specialized agents
- it already composes `AgentBoard`
- it already fits the repo’s review/advice style

## 2. Recommended service boundary

Add one new service:

- `services/agent-orchestrator-svc`

Responsibility:

- receive tasks
- classify risk
- orchestrate manager/worker/reviewer/advisor flow
- call MCP tools via `MCPClient`
- persist task state
- emit audit rows
- request human approval when needed

Do not put this inside:

- `inference-svc`
- `retrieval-svc`
- `governance-svc`

Reason:

- orchestration has a different scaling and failure model
- it is a control-plane concern, not pure inference

## 3. Recommended first version

### Phase 1

Implement:

- FastAPI API
- in-memory task store
- LangGraph workflow
- one manager
- one worker
- one reviewer
- one advisor board step
- optional human approval endpoint

Skip:

- parallel worker fan-out
- durable DB persistence
- full metrics dashboard
- multi-tenant quotas

### Phase 2

Add:

- Postgres task store
- audit row persistence
- MCP drafts + replay
- per-role tool allowlists
- cost budget
- timeout policy

### Phase 3

Add:

- multiple worker types
- dedicated advisor board
- approval queues
- replay worker
- operator UI

## 4. Service-to-service placement

```text
Client/UI
 -> api-gateway
 -> agent-orchestrator-svc
 -> retrieval-svc / inference-svc
 -> mcp/* servers
 -> governance-svc
```

### What each current service does in the new flow

- `api-gateway`
  - auth
  - correlation ID
  - rate limiting

- `agent-orchestrator-svc`
  - planning
  - execution routing
  - review
  - advisory board
  - approval state

- `retrieval-svc`
  - retrieval-only tasks

- `inference-svc`
  - answer generation tasks
  - possibly delegated substeps

- `governance-svc`
  - action drafts
  - audit log
  - approvals

- `mcp/*`
  - external side effects

## 5. Data model to add

Minimum tables when moving beyond in-memory:

### `agent_tasks`

- `task_id`
- `tenant_id`
- `goal`
- `status`
- `risk_level`
- `requires_human_approval`
- `approved_by`
- `created_at`
- `updated_at`

### `agent_task_steps`

- `task_id`
- `step_id`
- `role`
- `agent_name`
- `message_type`
- `input_json`
- `output_json`
- `confidence`
- `status`
- `started_at`
- `finished_at`

### `agent_task_artifacts`

- `task_id`
- `artifact_id`
- `artifact_type`
- `payload_json`
- `created_at`

You can also piggyback on:

- governance audit log
- action drafts

instead of inventing a separate audit subsystem.

## 6. API surface

Recommended endpoints:

### `POST /api/v1/agentic/tasks`

Create and execute a task.

### `GET /api/v1/agentic/tasks/{task_id}`

Inspect current state.

### `POST /api/v1/agentic/tasks/{task_id}/approve`

Human approval.

### `POST /api/v1/agentic/tasks/{task_id}/reject`

Human rejection.

### `GET /api/v1/agentic/tasks/{task_id}/events`

Audit/event trail.

## 7. Policy rules

Minimum policy:

- manager cannot self-approve
- worker cannot approve own result
- reviewer cannot execute tool side effects
- destructive tool calls require HITL
- low-confidence output requires advisory review
- repeated retries require escalation

## 8. LangGraph fit in this repo

LangGraph is a good fit for:

- bounded state transitions
- retry loops
- conditional routing
- human approval pauses

It is not needed for:

- simple single-agent inference calls

## 9. MCP fit in this repo

MCP should be the only tool/action boundary for:

- HR
- ITSM
- drills
- future external action systems

That keeps:

- scope enforcement
- idempotency
- draft fallback
- auditability

in one place.

## 10. Observability contract

Every task should emit:

- correlation ID
- trace ID
- tenant baggage
- task ID
- step ID
- role
- agent name
- outcome
- latency
- approval state

## 11. Recommended rollout order

1. create `agent-orchestrator-svc`
2. add in-memory API + LangGraph workflow
3. wire one MCP-backed worker
4. add reviewer
5. add advisory board
6. add approval endpoint
7. add durable task store
8. add audit persistence
9. add dashboards + alerts

## 12. Hard rules

- no free-form A2A messaging
- no direct worker-to-worker side effects without orchestrator state transition
- no destructive MCP calls without policy check
- no production rollout without audit trail
- no “agent magic” outside explicit state machine nodes
