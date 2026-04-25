# ADR-007: `actor_type` is derived from identity, never from route shape

## Status

Accepted — implemented in commit `2b47d4a` + refined in `0ff9434`,
`85cf13a`, `880022e`.

## Context

The original admin /resolve route stamped `actor_type="operator"`
unconditionally. That's transport semantics, not identity
semantics. In a deployment with `auth_required=False` (dev) or
during a partial outage where auth was bypassed, an unauthenticated
script hitting the route was getting recorded as operator-driven.
A federated worker calling the same route with a service token
would also be recorded as operator. The audit log lied.

## Decision

`actor_type` derives from the verified identity, not the URL path.
Mapping:

  verified human JWT (auth_user_id present)  → `"operator"`
  no verified token (dev / auth_required=False) → `"system"`
  autonomous worker driving resolve_draft     → `"worker"`
  generic service-account call                → `"service"`

`actor_id` carries the verified `sub` claim:

  * operator path → JWT.sub of the human (ADR-006 ensures it's
    a non-empty string ≤256, possibly federated)
  * worker path → service-token `sub` decoded once at startup
    (commit `85cf13a`)
  * auto-rejected by worker → same worker `sub`, different action
    (`mcp_draft.rejected`, commit `880022e`)
  * unauth/system path → NULL

"Came through admin API" is no longer treated as "performed by a
human operator." The ADR is enforced by `drill_audit_actor_type`
step 2 (operator) and step 4 (real worker, not a costume).

## Consequences

* Governance reviews answer "who did this?" honestly.
* A future federated worker hitting the admin route still gets
  `system` (or `worker` if the lifespan recognizes its sub) —
  not silently misclassified.
* The mapping is visible in code at the callsite, not buried in
  a policy table. Same shape as ADR-004 (fail_closed per call).
* Drill's step 4 prevents a regression where someone wraps the
  worker in a costume that *looks* like a worker call but skips
  the real `DraftReplayWorker.sweep_once()` path.
