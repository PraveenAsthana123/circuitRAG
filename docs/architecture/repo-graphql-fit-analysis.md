# Repo-Specific GraphQL Fit Analysis

This document evaluates whether GraphQL helps this repo and, if so, where.

The short answer is:

- GraphQL is a selective fit
- it is most useful as a read-side aggregation layer
- it is not a good replacement for the repo's core command and workflow architecture

## 1. Current repo shape

The repo is currently organized around:

- service-owned REST/HTTP routes
- a gateway that reverse proxies user-facing HTTP traffic
- workflow-heavy backend behavior
- MCP tool execution
- draft fallback and replay
- auditability and governance
- health and operator endpoints

This matters because GraphQL is strongest when:

- frontend read composition is painful
- data is distributed across services
- the UI needs custom-shaped queries

GraphQL is weaker when the system is primarily:

- command oriented
- side-effect heavy
- workflow and state-transition heavy
- replay and recovery heavy

That second category describes a large part of this repo.

## 2. Where GraphQL fits well

GraphQL fits best in this repo where the main problem is read composition.

### Strong-fit areas
- admin and operator dashboards
- aggregated health views
- tool and breaker status views
- prompt registry and evaluation views
- document detail views that join metadata, chunks, and state
- frontend query shaping for read-heavy screens

### Why it helps
- fewer frontend round trips
- less over-fetching and under-fetching
- one query per screen instead of many ad hoc calls
- cleaner frontend code for read-heavy views
- easier UI-specific aggregation

## 3. Where GraphQL is a poor fit

GraphQL is a weak fit for this repo's command and workflow paths.

### Weak-fit areas
- MCP tool calls
- draft creation and replay actions
- uploads
- webhook-style ingress
- async workflow triggers
- recovery and replay paths
- health probes that are already simple and operational

### Why it hurts here
- command semantics become less explicit
- resolver complexity hides side effects
- tracing and auth become more complex
- field-level governance becomes harder
- workflow and replay semantics become less obvious

## 4. Repo-specific decision

The best decision for this repo is:

- keep the core services REST
- keep MCP/action flows REST
- keep uploads and async workflows REST
- optionally add GraphQL as a frontend BFF for read-side composition

## 5. Best candidate screens for GraphQL

If GraphQL is added, it should begin with screens that are clearly read-heavy.

### Best first candidates
- admin dashboard
- operator health overview
- prompt and evaluation registry
- document explorer
- trace-link or debug views

### Bad first candidates
- ask + action mutation paths
- draft replay mutations
- upload flow
- tool execution endpoints

## 6. Main risks of adding GraphQL

- schema ownership overhead
- resolver fan-out hiding expensive calls
- auth/scope enforcement at field level
- more complicated caching
- more complicated observability
- another public contract to maintain

## 7. Best adoption strategy

If GraphQL is added:

1. keep it read-only first
2. make it a BFF layer, not a service rewrite
3. back it by existing REST endpoints and service clients
4. keep explicit command paths in REST
5. instrument resolver fan-out carefully

## 8. Bottom line

GraphQL can improve this repo, but only in the read-composition layer.

It should not replace:

- REST service APIs
- MCP command flows
- replay and recovery workflows
- upload and background workflow triggers

That is the honest repo-specific answer.
