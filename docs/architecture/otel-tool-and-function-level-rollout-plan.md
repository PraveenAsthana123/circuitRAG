# OpenTelemetry Tool And Function-Level Rollout Plan

This note is the step-by-step plan for adding deeper OTel coverage to this repo.

It assumes:

- service-level Python instrumentation already exists in important places
- Go-service and gateway coverage are still weak
- tool-level and function-level spans need explicit rollout

## 1. Rollout Principles

Use these rules:

- instrument the highest-value paths first
- prefer a few meaningful spans over many noisy spans
- instrument failure paths, not only happy paths
- preserve trace propagation across service and worker boundaries
- do not claim “fully implemented” until dashboards and drills confirm usefulness

## 2. Step 1: Fix The Gateway Gap

### Goal

Make the gateway a real trace root for the distributed system.

### Tasks

- initialize OTel in `api-gateway`
- add inbound HTTP instrumentation
- propagate trace context downstream
- record route and auth failure behavior

### Done when

- gateway spans appear for incoming requests
- traces continue into downstream services
- auth failures are visible in trace data

## 3. Step 2: Add Go-Service Base Coverage

### Targets

- `identity-svc`
- `governance-svc`
- `finops-svc`
- `observability-svc`

### Tasks

- add startup OTel init
- add inbound request spans
- add key outbound client spans if present

### Done when

- each service emits traces on its main request paths

## 4. Step 3: Add Agent-Level Spans

### Targets

- `AgentService`
- `MultiHopRagAgent`

### Suggested spans

- `agent.ask`
- `agent.intent_detect`
- `agent.scope_check`
- `agent.action_degraded`
- `agent.action_denied`
- `agent.multi_hop.plan`
- `agent.multi_hop.retrieve`
- `agent.multi_hop.synthesize`

### Done when

- operators can see why the agent answered, denied, or called a tool

## 5. Step 4: Add MCP Tool-Level Spans

### Targets

- `mcp/client.py`
- `mcp/server_common.py`
- per-server dispatch paths

### Suggested span or attribute areas

- tool name
- namespace
- scope outcome
- idempotency outcome
- degraded draft created
- replay hit
- dispatch duration

### Done when

- each tool call can be inspected as a real operational unit

## 6. Step 5: Add Replay And Draft Workflow Spans

### Targets

- draft creation
- replay
- replay rejection
- replay conflict

### Suggested spans

- `mcp.draft.persist`
- `mcp.draft.resolve`
- `mcp.draft.reject`
- `mcp.draft.mark_replayed`
- `mcp.draft.conflict`

### Done when

- trace view can explain draft lifecycle end to end

## 7. Step 6: Add Retrieval Decision Spans

### Targets

- vector search
- graph search
- rerank
- cache decision

### Suggested spans

- `retrieval.vector_search`
- `retrieval.graph_search`
- `retrieval.rerank`
- `retrieval.cache_lookup`

### Done when

- operators can see where retrieval time and decision cost come from

## 8. Step 7: Add Evaluation And Replay-Eval Spans

### Targets

- evaluation service
- replay evaluation
- regression gate

### Suggested spans

- `eval.run`
- `eval.metric.score`
- `eval.replay`
- `eval.regression_gate`

### Done when

- quality-review flows are as traceable as request flows

## 9. Step 8: Decide On Frontend Browser Tracing

### Decision question

Do you need browser-side traces for:

- user-perceived latency
- frontend route debugging
- browser-to-backend correlation

If yes:

- implement browser tracing explicitly
- limit noise
- ensure privacy discipline

If no:

- keep frontend trace linkage at correlation-ID and backend visibility level

## 10. Step 9: Add Verification

Instrumentation is not “done” just because spans were added.

Add verification through:

- drills
- trace-based checks
- dashboards
- release checklist items

### Verification questions

- does the span appear?
- does it carry useful attributes?
- does it appear on success and failure?
- does it create useful operator evidence?

## 11. Suggested Tracking Table

| Step | Component | Owner | Priority | Status | Verification |
|---|---|---|---|---|---|
| 1 | api-gateway |  | P0 | open | trace continuity check |
| 2 | Go services base |  | P1 | open | service health trace check |
| 3 | AgentService |  | P1 | open | ask + deny + degrade trace check |
| 4 | MCP tools |  | P1 | open | tool call trace and attributes |
| 5 | Draft/replay |  | P1 | open | replay and conflict trace drill |
| 6 | Retrieval decisions |  | P1 | open | vector/graph/rerank visibility |
| 7 | Evaluation |  | P2 | open | replay-eval and gate trace |
| 8 | Frontend tracing decision |  | P3 | open | explicit decision recorded |

## 12. Release Rule

Do not call tool/function-level OTel complete until:

- gateway trace root exists
- all critical services emit spans
- MCP and replay paths are visible
- failure paths are traceable
- dashboards and drill evidence exist

## 13. Bottom Line

The fastest path to real OTel maturity in this repo is:

1. fix the gateway and Go-service gap
2. add manual spans around MCP, agent, retrieval, and replay decisions
3. verify usefulness through drills and dashboards

That is how service-level tracing becomes real operational tracing.
