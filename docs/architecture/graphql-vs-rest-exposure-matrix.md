# GraphQL vs REST Exposure Matrix

This matrix shows what should be exposed through GraphQL and what should remain REST in this repo.

## 1. Decision rules

### Prefer GraphQL when
- the use case is read-heavy
- the UI needs custom-shaped responses
- multiple backend reads must be composed
- frontend round trips are becoming wasteful

### Prefer REST when
- the path is command-oriented
- the path has important side effects
- the path triggers async workflows
- idempotency and explicit state transition matter
- the API is already simple and operational

## 2. Exposure matrix

| Capability | Best exposure | Why |
|---|---|---|
| admin health overview | GraphQL | composed read view |
| breaker state summary | GraphQL | read aggregation for dashboard |
| tool stats and denials | GraphQL | good dashboard query surface |
| prompt registry | GraphQL | read-heavy, UI-shaped |
| evaluation summary | GraphQL | read-heavy, aggregated |
| document list | GraphQL or REST | GraphQL helps if UI needs custom projection; REST is fine if simple |
| document detail with chunks | GraphQL | natural composed read |
| trace-link debug view | GraphQL | screen-shaped read aggregation |
| upload document | REST | explicit command + file handling |
| delete document | REST | explicit side effect |
| ask question | REST | already coherent and latency-sensitive |
| ask + MCP action | REST | command + workflow path |
| MCP tool execution | REST | explicit command boundary |
| create draft on degradation | internal REST/workflow | not a frontend GraphQL concern |
| replay draft | REST | explicit state transition |
| admin resolve/reject draft | REST | command semantics must stay explicit |
| webhooks | REST | ingress command/event path |
| health probe endpoints | REST | simple operational path |

## 3. Practical recommendation

### Put in GraphQL first
- `healthOverview`
- `toolStats`
- `documents`
- `document`
- `promptRegistry`
- `traceLinks`

### Keep in REST
- uploads
- mutations with side effects
- tool calls
- replay
- webhook entrypoints
- health/readiness probes

## 4. Bottom line

GraphQL belongs in this repo as a read-model layer if it is added at all.

REST should remain the main exposure model for:

- commands
- workflows
- side effects
- operational endpoints
