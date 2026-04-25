# Pipeline Catalog

This document lists the main pipelines relevant to DocuMind's current
RAG, MCP, replay, breaker, audit, and operational control-plane shape.

It is intended as a practical reference for:

- system understanding
- workflow discussion
- drill planning
- observability design
- failure-mode review

For each pipeline, in addition to inputs / outputs / steps / failure
points / metrics, this catalog records:

- **Files involved** — concrete code paths, not abstractions.
- **Owner layer** — which architectural layer is authoritative.
- **Key invariants** — what must hold for the pipeline to be correct.
- **Best drill / test** — the existing drill that exercises it (or a
  "GAP" note when no drill exists yet, with a suggested name).

---

## 1. Document ingestion pipeline

**Input**

- uploaded file or document

**Output**

- parsed, chunked, embedded, indexed document ready for retrieval

**Typical steps**

- receive upload
- store blob/object
- create metadata/state
- parse document
- chunk content
- generate embeddings
- write vector index
- update document status

**Failure points**

- file storage failure
- parser failure
- oversized or invalid document
- embedding service unavailable
- vector DB write failure

**Metrics**

- upload success rate
- parse latency
- chunk count per doc
- embedding latency
- indexing success/failure
- backlog age for ingestion jobs

**Files involved**

- `services/ingestion-svc/app/main.py`
- `services/ingestion-svc/app/parsers/`
- `services/ingestion-svc/app/chunking/`
- `services/ingestion-svc/app/embedding/`
- `services/ingestion-svc/app/services/`
- `services/ingestion-svc/migrations/`

**Owner layer**

`services/ingestion-svc`

**Key invariants**

- Tenant ID is stamped on every chunk and never replaced downstream.
- Document `status` transitions are monotonic (`pending → parsing →
  ready` or `failed`); never resurrects from a terminal state.
- Embedding model + dimension are recorded with the document so a
  later embedding-model swap is detectable.

**Best drill / test**

GAP — no end-to-end ingestion drill today. Propose
`drill_ingestion_e2e` (upload → parse → chunk → embed → vector
write, with negative assertion: malformed document leaves status
in `failed`, not silently ready).

---

## 2. Retrieval pipeline

**Input**

- user query with tenant and auth context

**Output**

- ranked context chunks or documents

**Typical steps**

- validate request context
- build retrieval query
- run vector search
- apply metadata and tenant filters
- optionally merge graph or keyword results
- rerank candidates
- return top-k context

**Failure points**

- retrieval timeout
- wrong tenant filter
- stale index
- reranker failure
- low-quality recall

**Metrics**

- retrieval latency
- top-k size
- reranker latency
- empty-result rate
- retrieval quality signals where available

**Files involved**

- `services/retrieval-svc/app/main.py`
- `services/retrieval-svc/app/services/retrieval.py`
- `services/inference-svc/app/services/retrieval_client.py`
  (consumer; wraps the call in `CircuitBreaker.call_async`)

**Owner layer**

`services/retrieval-svc` (provider) + `services/inference-svc`
(consumer) — split because retrieval is reused by the agent path
too.

**Key invariants**

- Tenant filter is mandatory on every query — retrieval can never
  cross tenants.
- `top_k` is bounded server-side; clients can request smaller, not
  larger.
- A retrieval timeout never returns partial results without a
  timeout flag in the response.

**Best drill / test**

GAP — no dedicated retrieval drill. Propose
`drill_retrieval_tenant_isolation` (cross-tenant query MUST return
zero hits even if vectors match) and
`drill_retrieval_timeout_envelope`.

---

## 3. RAG answer pipeline

**Input**

- user question

**Output**

- answer with citations and metadata

**Typical steps**

- receive question
- retrieve context
- build prompt
- call model
- post-process result
- attach citations
- return answer

**Failure points**

- retrieval failure
- model timeout
- malformed model output
- citation mismatch
- low faithfulness

**Metrics**

- end-to-end latency
- model latency
- token and cost usage
- answer success/failure
- citation presence
- faithfulness/relevance signals

**Files involved**

- `services/inference-svc/app/services/rag_inference.py`
- `services/inference-svc/app/services/agent.py` (when the path
  is agentic)
- `services/inference-svc/app/routers/__init__.py:ask`

**Owner layer**

`services/inference-svc`

**Key invariants**

- Every answer carries `correlation_id` and propagates it to logs +
  spans.
- `guardrails_passed` flag is honest — never set True when a check
  failed.
- Citations point to chunks the retrieval step actually returned,
  not hallucinated IDs.

**Best drill / test**

GAP — no end-to-end RAG-quality drill. Propose
`drill_rag_answer_e2e` plus a guardrail-failure negative case.
Drill on faithfulness/citation regressions belongs in a separate
eval pipeline (see deferred list).

---

## 4. Agentic tool-use pipeline

**Input**

- natural-language request that implies an action

**Output**

- tool result or degraded draft

**Typical steps**

- classify intent
- choose tool or namespace
- pre-check scopes
- build tool arguments
- call MCP tool
- return tool result
- or degrade to draft

**Failure points**

- wrong tool selection
- scope denial
- MCP outage
- bad tool arguments
- duplicate side-effect risk

**Metrics**

- action success rate
- denial rate
- degraded draft rate
- tool choice distribution
- latency by tool namespace

**Files involved**

- `services/inference-svc/app/services/agent.py`
- `mcp/client.py:call_tool`
- `libs/py/documind_core/auth.py:required_role_for_tool`

**Owner layer**

`services/inference-svc` (orchestration) + `mcp/` (transport)

**Key invariants**

- Scope is checked **before** the tool call (pre-check) so a
  scope-denied request never produces a side effect.
- Tenant context flows into the tool call (`tenant_id` in payload,
  not just the JWT).
- Degraded path always produces a `draft_id` AND an audit row
  (`mcp_draft.created`).

**Best drill / test**

- `drill_agent_scope_precheck` — denial before tool call.
- `drill_agent_idempotency` — same key returns cached.
- `drill_agent_multiserver_routing` — `itsm.*` routes to ITSM, not HR.
- `drill_agent_denial_audit` — denials produce audit rows.
- `drill_agent_denial_metrics` — denials surface as Prometheus events.

---

## 5. Draft fallback pipeline

**Input**

- action request during outage or degraded dependency state

**Output**

- persisted pending draft and degraded response

**Typical steps**

- detect breaker-open or tool-call failure
- build draft record
- persist draft
- optionally audit
- return degraded response with draft ID

**Failure points**

- draft persistence failure
- silent audit failure
- wrong tenant context
- duplicate draft creation

**Metrics**

- drafts created
- degraded response rate
- draft persistence failure rate
- audit success/failure for created drafts

**Files involved**

- `mcp/client.py:_persist_draft`
- `mcp/drafts.py:PostgresDraftStore.save`
- `services/governance-svc/migrations/003_action_drafts.sql`
- `services/governance-svc/migrations/006_action_drafts_state_constraint.sql`

**Owner layer**

`mcp/` (degradation logic) + `governance-svc` (storage contract)

**Key invariants**

- Every degraded response carries a non-empty `draft_id`.
- Tenant ID stamped on the draft is the caller's tenant, not the
  service tenant.
- Draft persistence failure does not shadow the degradation
  signal — caller still gets `degraded=True` with whatever draft_id
  was assigned (the persist failure is logged + countered).
- Status starts as `pending`; storage CHECK constraint
  `action_drafts_status_valid` rejects anything else.

**Best drill / test**

- `drill_audit_actor_type` step 1 — kill MCP, agent/ask, verify
  draft persisted with `mcp_draft.created` audit row.
- `drill_admin_api` — covers list + persist surface end-to-end.

---

## 6. Draft replay pipeline

**Input**

- pending draft with actor context

**Output**

- replayed action or retained pending draft

**Typical steps**

- fetch draft
- validate pending state
- call downstream MCP tool again
- if success, mark replayed
- write audit attribution
- if degraded, keep pending

**Failure points**

- replay on non-pending draft
- duplicate replay race
- namespace misrouting
- bad actor attribution
- audit write failure

**Metrics**

- replay success rate
- replay conflict rate
- degraded replay rate
- actor-type attribution counts
- replay latency

**Files involved**

- `mcp/client.py:resolve_draft` (+ `reject_draft`)
- `mcp/drafts.py:mark_replayed` + `mark_rejected`
- `libs/py/documind_core/audit.py:AuditWriter.write`
  (the `fail_closed` parameter)

**Owner layer**

`mcp/` (transition + audit composition)

**Key invariants**

- CAS guard on transition: only `WHERE status='pending'` succeeds;
  rowcount=0 → caller skips duplicate side-effects.
- `audit_fail_closed` is per-call — operator-driven replays opt in
  for hard guarantees, worker stays fail-open.
- `replayed_at` and `replay_result` populated atomically with the
  status flip.
- `actor_type` ∈ {`operator`, `worker`, `service`, `system`} is
  derived from identity, never inferred from route shape.

**Best drill / test**

- `drill_audit_actor_type` step 2 — operator path, non-UUID `sub`
  round-trips.
- `drill_resolve_draft_routing` — `itsm.*` draft replays through
  ITSM client.
- `drill_action_draft_state_constraint` step 4 — first replay wins
  CAS, second is rejected (False).

---

## 7. Replay worker pipeline

**Input**

- pending drafts from store

**Output**

- replay attempts and worker stats

**Typical steps**

- poll or list pending drafts
- group or filter by tenant and namespace
- respect backoff
- skip unhealthy namespaces if breaker is open
- attempt replay
- update stats and logs

**Failure points**

- backlog growth
- namespace starvation
- repeated error loops
- weak backoff behavior
- hidden worker failure

**Metrics**

- worker sweep count
- replay count
- skip count
- error count
- oldest pending draft age
- backlog size by namespace or tenant

**Files involved**

- `services/inference-svc/app/workers/draft_replay.py`
- `services/inference-svc/app/main.py` (lifespan wires the
  service token + actor_id + auto-reject threshold)

**Owner layer**

`services/inference-svc`

**Key invariants**

- Per-draft backoff: a draft attempted within `_backoff` seconds
  is fast-skipped (no retry storms).
- Per-namespace bailout: if `hr` degrades, sweep continues for
  `itsm` in the same cycle (no global stall).
- CB-open fast-skip: a draft whose target client's CB is OPEN is
  skipped before the call (no retries fighting the breaker).
- `auto_reject_threshold` (default 5) bounds permanent-failure
  loops — after N consecutive failures the draft is auto-rejected.
- `actor_type="worker"`, `actor_id=<service-token sub>` on every
  worker-driven audit row (not `service`, not NULL).

**Best drill / test**

- `drill_audit_actor_type` step 4 — real worker invocation, not a
  client costume.
- `drill_worker_metrics` — `documind_draft_replay_total` per
  outcome label.
- `drill_worker_auto_reject` — N-th consecutive failure transitions
  the draft to rejected with worker attribution.

---

## 8. MCP request pipeline

**Input**

- tool name, arguments, auth, correlation, and idempotency context

**Output**

- normalized tool result or error

**Typical steps**

- build request
- attach headers
- server validates schema
- enforce scope
- execute tool
- emit tool metrics
- return structured result

**Failure points**

- auth invalid
- scope denied
- malformed payload
- wrong namespace or tool routing
- inconsistent error envelope

**Metrics**

- calls by tool
- success/error/degraded/replay outcomes
- auth/scope denial counts
- latency by tool
- idempotent replay counts

**Files involved**

- `mcp/server_common.py:handle_tool_call`
- `mcp/server_hr.py`, `mcp/server_itsm.py`, `mcp/server_drills.py`
- `mcp/idempotency.py` (Postgres-backed `IdempotencyStore`)
- `services/governance-svc/migrations/007_mcp_idempotency.sql`

**Owner layer**

`mcp/` — single-process per server; protocol seam is
`IdempotencyStore`.

**Key invariants**

- Scope check happens **before** idempotency lookup — a leaked
  Idempotency-Key cannot bypass scope enforcement.
- Idempotency state machine: `new → in_progress → succeeded |
  failed`; same key + different payload fingerprint → 409.
- Tool catalog has a TTL (60s default); a stale catalog can be
  served during outage but never indefinitely.
- Error envelope is consistent: every failure has `code`, optional
  `http_status`, optional `details`.

**Best drill / test**

- `drill_mcp_server_scope` — scope denial before cache.
- `drill_mcp_tool_call_metrics` — outcome labels populated.
- `drill_idempotency_durable` — 6-step durability proof
  including bypass-store-and-reconstruct.
- `drill_jwt_identity_contract` — malformed JWT shape rejected
  before claims propagate.

---

## 9. Circuit-breaker resilience pipeline

**Input**

- repeated dependency failures

**Output**

- open, half-open, and closed breaker behavior

**Typical steps**

- record failures
- open breaker after threshold
- fast reject while open
- wait recovery timeout
- half-open probe
- close on success or reopen on failure

**Failure points**

- wrong failure classification
- breaker drift across implementations
- no visibility into open/reject state
- retries fighting breaker behavior

**Metrics**

- breaker state
- opens
- rejections
- transitions
- half-open probes
- per-dependency health

**Files involved**

- `libs/py/documind_core/circuit_breaker.py` (canonical, post-unification)
- `mcp/client.py` (consumer — uses the canonical breaker via
  `allow / record_success / record_failure` API)
- `services/inference-svc/app/workers/breaker_metrics.py` (poll
  exporter for /health/detailed)

**Owner layer**

`libs/py/documind_core` — single state machine, single metric model.

**Key invariants**

- State ∈ `{closed, open, half_open}` (StrEnum); wire format is
  the lowercase string.
- `documind_circuit_breaker_transitions_total` increments only on
  real state change, not per poll.
- `recovery_timeout_s` exposed via `/health/detailed` so observers
  can compute when probe is eligible without hardcoding the value.
- `failures` (public property) is the consecutive-failure counter;
  resets to 0 on success.

**Best drill / test**

- `drill_breaker_transitions` — real state changes, exporter
  delta = +1 not +N.
- `drill_multi_breaker_visibility` — per-namespace independence.
- `drill_prometheus_breakers` — series labelled correctly.

---

## 10. Audit pipeline

**Input**

- sensitive action or state transition

**Output**

- hash-chained audit row

**Typical steps**

- build audit payload
- attach tenant, actor, and correlation context
- fetch previous hash
- compute entry hash
- persist record

**Failure points**

- invalid actor ID or type
- missing tenant context
- silent write failure
- chain verification break

**Metrics**

- audit write success/failure
- action counts by type
- actor-type distribution
- verification failures

**Files involved**

- `libs/py/documind_core/audit.py:AuditWriter.write`
- `services/governance-svc/migrations/001_initial.sql`
  (audit_log schema)
- `services/governance-svc/migrations/004_audit_log_breaks.sql`
  (forensic break records)
- `services/governance-svc/migrations/005_audit_actor_id_text.sql`
  (UUID → TEXT)
- `scripts/audit_verify.py` (chain reader + `--seal` writer)

**Owner layer**

`libs/py/documind_core` (writer) + `governance-svc` (schema +
verifier).

**Key invariants**

- Per-tenant hash chain: each row's `entry_hash` covers
  `previous_hash + body`. First row's `previous_hash = ""`.
- `actor_id` is TEXT — federated subjects (`okta:abc`,
  `alice@example.com`, `service:replay-worker`) all valid.
- `documind_audit_write_failures_total{action, error_type}`
  increments on every drop, both fail-open and fail-closed.
- `fail_closed=True` raises `DataError` (5xx) with the original
  exception preserved in `__cause__`.

**Best drill / test**

- `drill_audit_verifier` — chain integrity.
- `drill_audit_seal` — break records persist tampering evidence.
- `drill_audit_actor_type` — operator/worker/service distinction.
- `drill_audit_fail_closed` — both modes graph; default is open;
  forged-signature still 401.

---

## 11. Auth and tenant-context pipeline

**Input**

- HTTP request or service call with JWT and headers

**Output**

- request-scoped tenant, user, roles, and correlation context

**Typical steps**

- parse token
- validate issuer, audience, and kind
- set request state or context
- enforce required roles and scopes
- propagate auth downstream

**Failure points**

- invalid token
- wrong tenant source-of-truth handling
- auth context not forwarded
- cross-tenant access leak

**Metrics**

- auth failures
- insufficient-scope denials
- tenant mismatch incidents
- propagated-auth success where measurable

**Files involved**

- `libs/py/documind_core/auth.py` (`JWTVerifier`,
  `JWTAuthMiddleware`, `_validate_claims`, `require_roles`,
  `required_role_for_tool`)
- `libs/py/documind_core/middleware.py` (correlation + tenant
  context middleware)
- `services/inference-svc/app/main.py` (middleware stack wiring)

**Owner layer**

`libs/py/documind_core` — used by every Python service.

**Key invariants**

- JWT `tenant_id` (when present) is authoritative over
  `X-Tenant-ID` header.
- Strict claim shape: `sub` non-empty string ≤256, `tenant_id` UUID
  or empty/missing, `roles` list of `<ns>:<scope>` strings ≤32
  entries, `kind ∈ {access, refresh}`.
- `raw_token` stays on `request.state` so internal calls can
  forward the same identity (defence-in-depth at every hop).
- A bad token is **always** 401 even when `auth_required=False` —
  presenting a forged token is a positive signal of intent.

**Best drill / test**

- `drill_jwt_identity_contract` — 6 steps × negative shape rejections.
- `drill_mcp_server_scope` — scope enforcement at the MCP boundary.

---

## 12. Observability pipeline

**Input**

- logs, metrics, and traces emitted from runtime paths

**Output**

- dashboards, alerts, traces, and operational evidence

**Typical steps**

- emit structured logs
- emit Prometheus metrics
- emit traces and spans
- export to collectors
- visualize in Grafana, Jaeger, or similar systems

**Failure points**

- missing correlation IDs
- silent workflow failures
- noisy or non-actionable alerts
- missing subsystem metrics

**Metrics**

- observability pipeline health itself
- exporter errors
- alert volume/noise
- trace completeness where measurable

**Files involved**

- `libs/py/documind_core/observability.py` (OTel setup helpers)
- `libs/py/documind_core/breakers.py` (observability CB wrapper)
- `services/inference-svc/app/middleware.py:SpanAttributeMiddleware`
- `mcp/server_common.py` (tracer + `documind_mcp_tool_calls_total`
  + `mount_metrics_endpoint`)

**Owner layer**

`libs/py/documind_core` (helpers) + every service (call sites).

**Key invariants**

- Every request span carries `documind.correlation_id`.
- Tenant-scoped spans carry `documind.tenant_id` so Jaeger
  tag-filter queries by tenant work.
- Metric label cardinality is bounded — no `tenant_id` labels
  on counters; no dynamic high-cardinality strings.
- Observability failure (OTel exporter down) does not break the
  business path — `ObservabilityCircuitBreaker` shields it.

**Best drill / test**

- `drill_prometheus_breakers` — series labelled correctly.
- `drill_mcp_tool_call_metrics` — outcome labels exhaustive.
- `drill_breaker_transitions` — transitions counter doesn't
  inflate on polls.

---

## 13. Drill and testing pipeline

**Input**

- drill scripts and selected scenarios

**Output**

- pass/fail regression signal

**Typical steps**

- discover drills
- classify by resource tags
- run one or many drills
- collect output
- publish scoreboard or result

**Failure points**

- flaky timing
- stale-state pickup
- wrong resource tags
- tests proving the wrong path

**Metrics**

- drill pass rate
- drill duration
- flake rate
- failure category by subsystem

**Files involved**

- `scripts/run_drills.py` (resource-aware parallel runner +
  `--report junit=<path>`)
- `mcp/server_drills.py` (MCP-exposed runner with concurrency cap +
  killpg + stdout cap)
- `mcp/tests/drill_*.py` (~30 drills)

**Owner layer**

`scripts/` (CLI runner) + `mcp/` (MCP server) + `mcp/tests/`
(individual drills).

**Key invariants**

- Drills exercise REAL services — no mocks for runtime
  dependencies.
- Resource tags are honest — a drill that writes to PG cannot be
  tagged `readonly`.
- Every drill ships at least one negative assertion (proves
  something does NOT happen).
- Runner: subprocess kill on timeout uses `killpg` so child
  processes can't orphan.
- Runner stdout is capped at `MAX_STDOUT_BYTES` — no OOM from a
  hostile drill.

**Best drill / test**

- `drill_runner_junit` — JUnit output shape.
- `drill_runner_scheduler` — resource-tag parallelism semantics.
- `drill_runner_hardening` — concurrency cap + killpg + stdout
  cap + select-based deadline.
- `drill_drill_server` — MCP-exposed runner protocol.

---

## 14. Admin resolve pipeline

**Input**

- admin or operator request to resolve (or reject) a draft

**Output**

- structured replay or rejection result

**Typical steps**

- authenticate and authorize
- fetch draft
- determine namespace client
- call replay or reject path
- map result to API response

**Failure points**

- wrong actor attribution
- no server for namespace
- replay conflict
- auth-policy mismatch

**Metrics**

- admin replay success/conflict/degraded counts
- operator attribution count
- namespace resolution failures

**Files involved**

- `services/inference-svc/app/routers/__init__.py`
  (`resolve_draft` + `reject_draft`)
- `services/inference-svc/app/schemas/__init__.py`
  (`DraftResolveResponse`, `DraftRejectRequest`,
  `DraftRejectResponse`)
- `mcp/client.py:resolve_draft` + `reject_draft`

**Owner layer**

`services/inference-svc` (route + schema) + `mcp/` (transport).

**Key invariants**

- Two-phase scope check: authenticate first (unauthenticated
  callers get 401 BEFORE the draft lookup, so they can't enumerate
  draft IDs by 404 vs 401), THEN derive role from tool namespace
  and re-check.
- `actor_type` derived from identity: verified human JWT →
  `operator`, no token → `system`. Never inferred from the route.
- `audit_fail_closed=True` for operator actions; worker stays
  fail-open.
- Namespace routing by tool prefix — an `itsm.*` draft routes to
  the ITSM client, never to HR.

**Best drill / test**

- `drill_admin_api` — list + resolve happy path.
- `drill_audit_actor_type` step 2 — operator attribution.
- `drill_resolve_draft_routing` — multi-namespace correctness.
- `drill_draft_reject` — terminal rejection + worker skip.

---

## 15. Governance and policy pipeline

**Input**

- request, tool, action, or query needing policy check

**Output**

- allow, deny, or escalate decision

**Typical steps**

- inspect request or action
- apply scope and policy rules
- return decision
- emit audit and metrics

**Failure points**

- over-permissive path
- over-restrictive path
- missing audit
- policy drift between docs and code

**Metrics**

- allow/deny counts
- escalation counts
- policy-trigger categories
- policy error/failure counts

**Files involved**

- `libs/py/documind_core/auth.py:require_roles` +
  `required_role_for_tool`
- `mcp/server_common.py:enforce_scope`
- `libs/py/documind_core/exceptions.py`
  (`PolicyViolationError`, `RateLimitedError`)
- `services/governance-svc/migrations/006_action_drafts_state_constraint.sql`
  (storage-level state-machine guard)

**Owner layer**

`libs/py/documind_core` (decision logic) + `governance-svc`
(storage constraints).

**Key invariants**

- Scope is enforced before the idempotency cache — a leaked
  Idempotency-Key cannot replay a denied action.
- State machine is enforced in storage too: CHECK constraint on
  `action_drafts.status` rejects values outside
  `{pending, replayed, rejected}`.
- Denials produce audit rows (`agent.scope_denied`,
  `mcp_draft.rejected`) with the same hash-chain integrity as
  successful actions.

**Best drill / test**

- `drill_mcp_server_scope` — `INSUFFICIENT_SCOPE` envelope.
- `drill_agent_scope_precheck` — denial before tool call.
- `drill_agent_denial_audit` — denials produce audit rows.
- `drill_agent_denial_metrics` — denials surface as Prometheus
  events.
- `drill_action_draft_state_constraint` — storage rejects
  illegal `status` values + CAS guard prevents bad transitions.

---

## Highest-priority pipelines for this repo

If only a small subset is tracked or maintained aggressively, start with
these:

1. MCP request pipeline
2. Draft fallback pipeline
3. Draft replay pipeline
4. Replay worker pipeline
5. Circuit-breaker resilience pipeline
6. Audit pipeline
7. Auth and tenant-context pipeline
8. Drill and testing pipeline

---

## Drill coverage gaps

The catalog surfaces three pipelines without dedicated drills today:

| Pipeline | Suggested drill |
| --- | --- |
| Document ingestion (1) | `drill_ingestion_e2e` |
| Retrieval (2) | `drill_retrieval_tenant_isolation` + `drill_retrieval_timeout_envelope` |
| RAG answer (3) | `drill_rag_answer_e2e` (citation-presence + guardrail-failure negatives) |

These are good loop candidates when there's no higher-priority
governance / replay / breaker work outstanding. Closing each one
adds a regression surface for a critical user-facing path.
