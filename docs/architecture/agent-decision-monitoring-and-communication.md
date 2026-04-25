# Agent Decision, Monitoring, And Communication

This note explains:

- who decides to create an agent
- how an agent is created in this repo
- why the system uses an agent
- how the agent is monitored
- how communication is tracked across the system

Relevant code:

- [services/inference-svc/app/services/agent.py](/mnt/deepa/rag/services/inference-svc/app/services/agent.py)
- [services/inference-svc/app/agents/multi_hop_agent.py](/mnt/deepa/rag/services/inference-svc/app/agents/multi_hop_agent.py)
- [mcp/client.py](/mnt/deepa/rag/mcp/client.py)
- [mcp/server_common.py](/mnt/deepa/rag/mcp/server_common.py)

## 1. Who Decides To Create An Agent

The short answer is:

- engineers and system architects decide at design time
- application code decides which agent path runs at request time

MCP does not create the agent.
The agent is part of the inference and orchestration layer.

In this repo, the decision to use agents is encoded in the inference service:

- `AgentService`
- `MultiHopRagAgent`

Those are explicit application choices made by the team.

## 2. Why The System Uses An Agent

An agent is useful when the system must do more than a single model call.

In this repo, the agent is needed because the system may need to:

- retrieve context first
- generate a grounded answer
- detect action intent
- choose a tool namespace
- enforce scope before action
- call MCP tools
- degrade into draft fallback on failure
- replay later

Without those steps, the system could be much simpler.

The agent exists because the workflow is:

- multi-step
- policy-sensitive
- tool-aware
- failure-aware

## 3. How The Agent Is Created

There are two levels of creation.

### Design-time creation

Engineers create agent classes and wire them into services.

Examples:

- `AgentService` for answer plus action flow
- `MultiHopRagAgent` for multi-step retrieval flow

This includes wiring:

- retrieval clients
- model clients
- MCP clients
- breakers
- prompts
- schemas

### Runtime invocation

At runtime, the application calls the agent flow for a request.

That means:

1. a user request reaches the inference layer
2. the service chooses the agent path
3. the agent executes the workflow

So the agent is not spontaneously created by the platform.
It is a coded workflow object that the app invokes.

## 4. Agent Flow In This Repo

The main request-time flow is:

```text
User
  -> API Gateway
  -> inference-svc
      -> AgentService
          -> RAG answer path
          -> optional MCP tool path
          -> degraded fallback if needed
          -> response
```

The multi-hop retrieval flow is:

```text
User question
  -> MultiHopRagAgent
  -> plan sub-questions
  -> retrieve multiple hops
  -> synthesize final answer
  -> stop on breaker or budget if needed
```

## 5. How The Agent Is Monitored

The agent is monitored through the same observability surfaces as the rest of the system, plus workflow-specific metrics.

### Main monitoring channels

- logs
- traces
- metrics
- breaker state
- audit events
- draft and replay state

### Useful agent metrics

- request count
- action-selected count
- scope-denied count
- degraded count
- replay count
- multi-hop stop reason
- token-budget breaker trips
- loop or time breaker trips
- latency

### Repo-specific monitoring sources

- Prometheus-style counters and gauges
- OpenTelemetry traces
- breaker metrics from `documind_core`
- MCP tool-call counters
- audit events for sensitive transitions

## 6. How Communication Is Tracked

Communication is tracked using shared request metadata and observability context.

### Core tracking fields

- `correlation_id`
- `tenant_id`
- `idempotency_key`
- `actor_type`
- `actor_id`
- `tool`
- `draft_id`

### Communication flow

```text
Frontend or caller
  -> gateway
  -> inference service
  -> agent
  -> MCP client
  -> MCP server
  -> draft or audit store
  -> replay worker or operator
```

The same context should travel across that path.

## 7. How Tracking Works In Practice

The important pattern is:

1. request gets a correlation ID
2. gateway forwards it
3. agent uses it
4. MCP client sends it as `X-Correlation-Id`
5. MCP server logs and traces with it
6. draft and audit rows store it
7. replay reuses the original context where appropriate

This is how operators can connect:

- the original user request
- the tool invocation
- the degraded draft
- the replayed completion
- the audit evidence

## 8. Why This Matters

Without clear agent monitoring and communication tracking:

- actions become hard to explain
- failures become hard to debug
- replays become operationally confusing
- governance becomes weaker

With clear tracking:

- operators can reconstruct what happened
- denials and degraded paths are visible
- replay is traceable
- sensitive actions are auditable

## 9. Bottom Line

In this repo:

- people decide to use agents at architecture time
- code invokes the agent at runtime
- MCP is the governed action layer, not the agent itself
- monitoring comes from metrics, traces, breakers, drafts, and audit
- communication is tracked using correlation IDs, tenant context, idempotency keys, and audit metadata

That is the correct mental model for this system.
