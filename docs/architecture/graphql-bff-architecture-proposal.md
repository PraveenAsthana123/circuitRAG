# GraphQL BFF Architecture Proposal

This document proposes the safest GraphQL architecture for this repo.

The recommended model is:

- GraphQL as a BFF
- read-side aggregation only at first
- existing REST services remain authoritative

## 1. Proposed shape

```text
Frontend
  -> GraphQL BFF
      -> existing gateway-safe service clients
          -> ingestion-svc
          -> retrieval-svc
          -> inference-svc
          -> governance/admin read endpoints
```

Writes remain:

```text
Frontend
  -> REST command endpoints
      -> gateway
      -> services
      -> MCP / drafts / replay / audit
```

## 2. Why BFF is the right pattern

This repo already has clear service boundaries and command workflows. Replacing them with GraphQL would create unnecessary complexity.

A BFF helps because it:

- reshapes data for frontend screens
- reduces over-fetching
- keeps service contracts stable underneath
- avoids polluting command paths with resolver-side side effects

## 3. Suggested BFF responsibilities

The GraphQL BFF should own:

- frontend read aggregation
- screen-specific response shaping
- joining multiple read models
- field selection for UI needs

The GraphQL BFF should not own:

- business workflow orchestration
- tool execution
- replay logic
- uploads
- side-effect-heavy mutations

## 4. Good first schema areas

### Query types
- `healthOverview`
- `toolStats`
- `promptRegistry`
- `documents`
- `document(id)`
- `traceLinks(correlationId)`
- `draftBacklogSummary`

### Avoid at first
- `callTool(...)`
- `resolveDraft(...)`
- `uploadDocument(...)`
- `runAgentAction(...)`

## 5. Resolver design guidance

- prefer one resolver per aggregated read use case
- avoid N+1 fan-out
- use backend service clients with correlation propagation
- preserve tenant/auth context
- keep resolvers thin
- push business logic to existing services

## 6. Auth and governance

The BFF must:

- preserve tenant context
- preserve correlation IDs
- enforce same auth model as current frontend
- not bypass service-layer policy
- not expose hidden internal fields by convenience

## 7. Observability requirements

GraphQL adds a new layer, so it must be observable.

Track:

- query name
- resolver latency
- downstream fan-out count
- auth denial counts
- field/resolver failures
- correlation ID propagation

## 8. Rollout plan

### Phase 1
- stand up GraphQL BFF
- add read-only health and documents queries

### Phase 2
- add admin/operator aggregated views
- add prompt/eval registry read queries

### Phase 3
- decide whether any low-risk mutations are justified

## 9. Bottom line

GraphQL should be introduced here only as a frontend query layer.

That keeps:

- REST for commands
- MCP for tool execution
- workers for replay
- GraphQL for read composition

This is the cleanest architecture for the repo as it exists today.
