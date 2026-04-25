# MCP, Replay, Breaker, And Governance Scenario List

This document collects high-value repo-specific scenarios for the MCP,
draft replay, circuit breaker, auth, audit, and worker subsystems.

It is intended as a practical reference for:

- drill design
- regression planning
- workflow review
- design discussion
- operational scenario coverage

---

## MCP scenarios

- `hr.policy_lookup` happy path
- `hr.leave_request` happy path
- invalid tool name returns structured error
- malformed tool arguments rejected
- tool denied by scope
- auth missing vs auth invalid vs insufficient scope
- multi-server namespace routing picks correct MCP server
- tool catalog TTL refreshes after expiry
- tool catalog stale cache used safely during outage

---

## Draft and replay scenarios

- MCP server down -> draft persisted
- admin/operator resolves pending draft successfully
- worker replays pending draft successfully
- replay attempted on non-pending draft -> conflict/error
- duplicate replay attempts race on same draft
- degraded replay leaves draft pending
- no-server-for-namespace leaves draft pending
- replay attribution differs for operator vs worker vs service
- audit row written for `mcp_draft.created`
- audit row written for `mcp_draft.replayed`

---

## Circuit breaker scenarios

- repeated MCP failure opens breaker
- breaker open fast-rejects tool call
- breaker half-open probe succeeds and closes
- breaker half-open probe fails and reopens
- one namespace breaker opens while another stays healthy
- worker skips replay when breaker is open
- breaker metrics exported correctly
- breaker visibility appears in Prometheus, traces, and logs

---

## Audit and governance scenarios

- audit chain records state transitions
- audit attribution captures actor type correctly
- audit write failure is visible operationally
- scope denial creates audit entry
- tenant-scoped audit visibility works
- hash-chain verification succeeds
- admin action is distinguishable from worker replay

---

## Auth and tenant scenarios

- valid JWT sets tenant, user, and roles
- tenant header vs JWT tenant conflict handled correctly
- unauthenticated protected endpoint denied
- authenticated wrong-scope caller denied
- tenant-scoped draft not visible cross-tenant
- MCP auth forwarding preserves caller identity

---

## Worker scenarios

- worker polls pending drafts by tenant
- worker respects backoff
- worker handles namespace grouping correctly
- worker continues healthy namespaces while one namespace is degraded
- worker stats reflect replayed, errors, and skips
- worker restart resumes pending work safely

---

## API scenarios

- `/api/v1/drafts/{id}/resolve` happy path
- resolve returns 404 for missing draft
- resolve returns 409 for non-pending draft
- resolve returns 503 when namespace server is missing
- error envelopes remain consistent
- correlation ID propagates through request path

---

## Drill and test-truthfulness scenarios

- drill claims real worker path and actually uses worker path
- drill proves a negative assertion, not only happy path
- drill isolates stale state by correlation ID or draft ID
- drill resource tags match actual touched resources
- scheduler runs disjoint drills in parallel safely

---

## Failure and recovery scenarios

- MCP process killed mid-flow
- MCP restarted and replay succeeds after recovery timeout
- dependency slowdown causes timeout before breaker open
- invalid actor identity causes audit issue and is visible
- config or flag change affects replay behavior predictably
- rollout introduces regression and a drill catches it

---

## Highest-priority scenarios for this repo

If only a short list is implemented or maintained aggressively, start
with these:

1. server down -> draft persisted -> worker replay after recovery
2. admin replay vs worker replay attribution
3. replay conflict on non-pending draft
4. multi-server routing with namespace isolation
5. breaker open / half-open / recovery behavior
6. scope denial + audit + metrics
7. audit failure visibility
8. worker namespace isolation during partial outage
