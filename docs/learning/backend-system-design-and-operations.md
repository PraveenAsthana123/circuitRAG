# Backend System Design And Operations

This guide covers the production-backend and distributed-systems side of
the repository.

---

## Retry, timeout, circuit breaker, and degraded-mode composition

These tools do different jobs:

- timeout protects caller latency
- retry handles transient failure
- breaker protects the system
- degraded mode preserves business continuity

Production-grade design needs:

- per-attempt timeout
- bounded retry count
- jittered backoff
- idempotency on write paths
- breaker metrics and visibility
- explicit degraded path when the dependency is unavailable

---

## Queues, worker pools, backpressure, and CPU-bound isolation

RAG systems are pipelines, so producer/consumer discipline matters.

Use bounded queues and bounded worker pools to:

- protect memory
- expose overload
- slow producers when downstream is saturated
- keep request-serving paths separate from long-running work

For CPU-heavy or risky work:

- OCR
- parsing
- conversion
- heavy evaluation

use processes/subprocesses, not the async event loop.

---

## Validation boundaries and schema contracts

Boundary rule:

- outside: raw payloads, strings, untrusted input
- inside: validated models, enums, typed data, normalized state

Use validation at:

- HTTP ingress
- tool-call ingress
- event-consumer ingress
- model-output parsing
- config load

Do not let raw `dict[str, Any]` leak deep into the system.

---

## Event-driven architecture, idempotency, and the "exactly once" lie

Assume:

- duplicates happen
- retries happen
- out-of-order delivery happens

Use:

- unique event IDs
- processed-event tables
- upsert by business key
- compare-and-swap transitions
- outbox for DB change plus event publication
- DLQ for poison payloads

Treat "exactly once" skeptically unless the scope is precisely defined.

---

## Workflows, state machines, and sagas

Any multi-step, failure-prone business flow should be modeled as an
explicit workflow.

Good workflow design means:

- states are explicit
- transitions are restricted
- retries are step-aware
- terminal failure is visible
- compensation policy is deliberate

In this codebase, replay is a workflow, not a helper.

---

## Middleware, request lifecycle, and dependency injection

Middleware is the right place to establish:

- correlation IDs
- tenant context
- JWT parsing
- security headers
- tracing attributes

Dependencies are the right place to enforce route-specific rules:

- required roles
- operator/admin checks
- resource-specific authorization

Keep entrypoints thin.

---

## Observability: logs, metrics, traces

Logs, metrics, and traces each answer different questions:

- logs explain events
- metrics show trends
- traces show flow and latency

Observability should let you answer:

- what happened?
- for which tenant/request?
- what dependency failed?
- what state is the workflow in?
- where did latency go?

Watch for observability debt:

- silent audit drops
- missing correlation IDs
- breaker behavior with no metrics
- replay or queue failures only visible in vague logs

---

## Security engineering in backend and RAG systems

You need to think about:

- authentication vs authorization
- tenant isolation at every layer
- prompt injection and untrusted retrieved text
- tool abuse and explicit tool policies
- safe document ingestion
- secret handling in logs/traces/errors
- outbound-call controls
- truthful audit attribution

In RAG, retrieved content is untrusted input, not trusted instruction.

---

## Database engineering: transactions, locking, RLS, and indexes

For most enterprise backends, the database is the correctness anchor.

Important skills:

- use transactions deliberately
- protect workflow transitions with conditional updates
- understand races and lost updates
- use row locking and `SKIP LOCKED` patterns where appropriate
- enforce invariants with constraints, not only application code
- design indexes around real access patterns
- use RLS intentionally and set session context correctly

---

## Redis, caching, invalidation, and consistency

Caching is easy to add and hard to make correct.

Important rules:

- every cache must have a purpose
- every keyspace needs an invalidation strategy, not just a TTL
- every tenant-scoped cache key must include tenant context
- Redis is for speed and coordination, not long-term correctness truth

Good uses:

- TTL read caches
- idempotency coordination
- rate limiting
- temporary coordination

---

## API design for enterprise backends

A strong API defines:

- request schema
- response schema
- error envelope
- auth requirements
- idempotency expectations
- async vs sync semantics
- compatibility and deprecation posture

Important concerns:

- additive changes are safer than breaking ones
- write APIs should consider idempotency keys
- async workflows often return `202 Accepted` plus job/workflow IDs
- error codes should be stable and machine-readable

---

## Configuration management and feature flags

Strong config design requires:

- typed config
- startup validation
- safe defaults
- clear static vs dynamic boundary
- explicit precedence rules
- auditability for dynamic config/flag changes

Feature flags are useful for:

- canary rollout
- per-tenant behavior changes
- emergency disablement
- migration paths

---

## Engineering process and delivery topics

### Code management

- branch discipline
- PR scope and reviewability
- ownership and subsystem stewardship
- traceability from change to deploy

### Build and packaging

- reproducible environments
- dependency pinning and lock discipline
- packaging strategy for shared libraries and services
- artifact creation and verification
- separating build artifact from runtime config

### Version control and versioning

- coherent commit history
- branch strategy
- semantic versioning where relevant
- API and event schema versioning
- migration-aware release discipline

### CI/CD and deployment

- fast local checks vs slower CI gates
- release and promotion flow
- deploy strategies: rolling, canary, blue/green
- rollback and kill-switch design
- post-deploy verification and release notes

---

## Model monitoring, eval, drift, debugging, incidents, and on-call

### Model monitoring and eval

Track:

- retrieval quality
- faithfulness
- citation quality
- tool correctness
- latency and cost
- policy violation rate
- drift after prompt/model/retrieval changes

### Debugging

Strong debugging means:

- narrow the failing invariant
- identify the first diverging layer
- preserve evidence
- use correlation IDs, traces, state, and metrics together

### Incident response and postmortems

Healthy loop:

- detect
- stabilize
- preserve evidence
- explain root cause
- add regression test/drill
- add missing metric/runbook
- tighten design where needed

### On-call and operational maturity

Focus on:

- actionable alerts
- SLOs and error budgets
- runbooks
- ownership clarity
- rollback and kill switches

