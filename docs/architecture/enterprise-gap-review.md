# Enterprise Gap Review

This note reviews what still appears missing from an enterprise-maturity point of view in this repo.

The repo already has strong architectural ingredients:

- service separation
- API gateway
- MCP-based action layer
- replay and draft handling
- breakers
- observability infrastructure
- governance and evaluation concepts

But enterprise readiness is not only about having the pieces.
It is about how complete, visible, governed, and operable those pieces are.

## 1. Monitoring Maturity Gaps

The repo has meaningful observability infrastructure, but monitoring maturity still appears incomplete.

### Missing or underdeveloped

- business and workflow SLOs, not only service health
- per-tenant health visibility
- draft backlog, replay, degraded-mode, and queue-age dashboards
- alert routing by owning subsystem
- runbooks tied to alerts
- clearer retrieval-quality and model-quality monitoring
- stronger operator-facing dashboards instead of mostly backend-oriented signals

### Why this matters

Enterprise systems fail operationally when teams can see:

- CPU
- memory
- latency

but cannot clearly see:

- degraded workflows
- tenant-specific pain
- replay backlog growth
- audit failures
- model quality drift

## 2. Architecture Governance Gaps

The repo has a lot of architectural intent, but governance still needs stronger “system of record” qualities.

### Missing or underdeveloped

- clearer canonical architecture docs for the current live system
- subsystem ownership map
- stronger dependency rules between services and shared libraries
- ADR coverage for major architectural choices
- clearer separation between:
  - current state
  - planned state
  - scenario or aspirational state
- stronger contract boundaries across route, service, worker, and store layers

### Why this matters

Enterprise systems decay when architecture is “known by the team” but not clearly governed.

## 3. Tracking And Traceability Gaps

The repo has correlation IDs, audit concepts, and tracing surfaces, but broader change and workflow traceability is still thinner than an enterprise deployment would want.

### Missing or underdeveloped

- deploy -> incident -> rollback -> follow-up tracking chain
- feature-flag inventory and lifecycle tracking
- prompt, model, and retrieval version tracking in one place
- end-to-end request lineage:
  - user request
  - tool call
  - degraded draft
  - replay
  - audit result
- easier operator view of “what changed recently?”
- better long-range comparison of quality, cost, and regression history

### Why this matters

Enterprise teams need to answer:

- what changed?
- when did this start?
- which version caused this?
- how did this action move across systems?

## 4. Security And Governance Gaps

The repo has strong governance thinking, but some areas still feel more documented than fully surfaced as operational capabilities.

### Missing or underdeveloped

- fuller identity-provider and provisioning story in live code paths
- stronger retention and deletion enforcement surfaces
- secret rotation and key-management visibility
- privacy and PII review surfaces in operator UI
- policy versioning and rollout visibility
- governance dashboards for denials, escalations, and audit failures

### Why this matters

Enterprise governance is not only about blocking bad requests.
It is also about proving:

- what policy was active
- what was denied
- what was escalated
- what data was protected

## 5. Platform And Operations Gaps

The repo includes many production-oriented ideas, but the operator experience still seems behind the backend design.

### Missing or underdeveloped

- production-grade admin console
- environment promotion discipline across dev, stage, prod
- release gates tied to drills, evals, and SLOs
- cost and capacity planning dashboards
- disaster-recovery and restore drills
- operational readiness checklists per service
- more complete service ownership and escalation surfaces

### Why this matters

Enterprise operations depend on clarity during:

- rollout
- incident
- recovery
- audit
- cost pressure

## 6. AI/RAG-Specific Enterprise Gaps

This is one of the biggest remaining areas.

### Missing or underdeveloped

- prompt registry
- model registry
- retrieval policy registry
- eval dataset and version registry
- online quality monitoring beyond core infra metrics
- review workflow for bad answers and tool mistakes
- stronger AI-specific trace and prompt inspection tooling

### Why this matters

Enterprise AI systems are not mature when the team knows:

- the code path

but cannot easily inspect:

- prompt version
- model version
- retrieval configuration
- quality drift over time
- token and cost behavior

### Strong likely addition

An LLM/RAG observability layer such as:

- Langfuse
- Phoenix

would likely add significant value here.

## 7. Developer Experience And Scale Gaps

For enterprise-scale maintenance, repo ergonomics matter too.

### Missing or underdeveloped

- non-interactive frontend lint setup
- clearer local orchestration for all services
- stronger CI visibility for drill and scenario coverage
- architecture conformance checks
- easier repo navigation for new engineers
- stronger “what is authoritative?” guidance across docs

### Why this matters

A system can be architecturally sound and still expensive to evolve if developer workflows are inconsistent.

## 8. Highest-Value Missing Enterprise Layers

If reduced to the most important missing areas, the biggest gaps are:

1. operator and admin dashboards
2. SLO, runbook, and alert ownership discipline
3. AI-specific observability and evaluation tracking
4. architecture governance and ADR discipline
5. end-to-end change and workflow traceability
6. cost, capacity, and tenant-level operational visibility

## 9. Best Next Documentation To Add

Useful next docs would be:

- `operator-dashboard-requirements.md`
- `slo-alert-runbook-matrix.md`
- `ai-observability-and-eval-governance.md`
- `architecture-ownership-and-adr-index.md`
- `change-traceability-and-release-governance.md`

## 10. Bottom Line

This repo is not missing “core architecture ideas.”
It already has many of them.

The bigger enterprise gaps are around:

- operational visibility
- governance maturity
- AI-specific observability
- ownership clarity
- change traceability
- operator tooling

That is the difference between a strong technical prototype and a stronger enterprise operating platform.

---

## 11. How These Gaps Map To DocuMind Today

### Already shipped (cross-referenced from other gap reviews)

The repo is not weak everywhere — substantial governance work has
already landed:

| Gap class (from §1-§7) | What's done | Reference |
| --- | --- | --- |
| Audit chain integrity | hash-chained per-tenant + forensic break records + verifier CLI | `drill_audit_verifier`, `drill_audit_seal` |
| Audit attribution | actor_type + actor_id (operator/worker/service/system) | `drill_audit_actor_type` (5 steps) |
| Audit fail-closed for governance-critical actions | per-call `fail_closed=True` | `drill_audit_fail_closed` |
| Cross-tenant data isolation | RLS at PG + filter at Qdrant | `drill_retrieval_tenant_isolation` |
| Identity contract validation | strict claim-shape validator | `drill_jwt_identity_contract` |
| Storage state-machine guard | CHECK constraints on `action_drafts.status` | `drill_action_draft_state_constraint` |
| Replay safety (CAS) | `mark_replayed` + `mark_rejected` rowcount-checked | `drill_audit_actor_type` step 4, `drill_draft_reject` |
| Idempotency (durable) | Postgres-backed cache with payload-fingerprint conflict detection | `drill_idempotency_durable` |
| Permanent-failure terminal state | auto-reject after N consecutive failures | `drill_worker_auto_reject` |
| Transport circuit breakers | unified `CircuitBreaker` + per-dependency series | `drill_breaker_transitions`, `drill_retrieval_transport_breaker` |
| Backend independence under partial outage | per-namespace breaker, per-namespace worker bailout | `drill_multi_breaker_visibility`, `drill_worker_metrics` |

### The actionable enterprise gaps (next-iteration shortlist)

Most of §1-§7 collapses to a small set of bounded code/doc commits:

| # | Gap | Commit shape |
| --- | --- | --- |
| 1 | **Operator/admin dashboard** — surface live `/health/detailed` data in the frontend admin page | ~150 LoC on `services/frontend/app/admin/page.tsx` + 5s refresh; one drill |
| 2 | **Backlog-age gauge** — `documind_draft_pending_age_seconds{namespace}` (started + abandoned mid-iteration earlier) | ~50 LoC in `app/workers/draft_replay.py` + drill |
| 3 | **Worker sweep span** — wrap `_sweep` in OTel span with tenant/namespace attributes | ~10 LoC; trace continuity from sweep → resolve_draft |
| 4 | **Token-counter metric** — `documind_inference_tokens_total{model,kind}` | middleware on inference-svc; closes cost-anomaly story |
| 5 | **Eval workflow productization** — minimal eval-run script + result viewer | larger; depends on baseline |
| 6 | **Prompt registry** — single source of truth for prompt versions referenced in audit `details` | small if backed by a Git-tracked YAML; bigger if a UI is wanted |
| 7 | **PII redaction layer** — `libs/py/documind_core/pii.py` + redact-before-log middleware | from security-and-governance-scenarios.md §13; high enterprise priority |
| 8 | **SLO/runbook/alert ownership matrix** — markdown only | enterprise hygiene; no code |
| 9 | **ADR index** — list of design decisions with rationale | docs/architecture/adr/ folder |
| 10 | **Cluster-coordinated breaker state** | only useful at multi-replica scale; deferred |

### What's documented vs what's enforced

Many of the §1-§7 items are documented but not yet enforced in
code:

- **Documented**: PII handling (security-and-governance-scenarios.md
  §13), tenant isolation invariants (pipeline-catalog.md §2),
  policy-versioning concepts (security-and-governance-scenarios.md §4).
- **Enforced in code**: tenant filter in Qdrant + RLS, audit chain,
  CB transitions, idempotency CAS, JWT shape, draft state machine.
- **Both**: cross-tenant access, scope checks, fail_closed on
  operator actions.

The enterprise gap is most often "documented but not enforced." A
drill is the bridge between the two: documented invariant + drill
that proves it = enforced contract.

### The single highest-leverage move

The frontend admin dashboard (#1 above) closes:
  * frontend review item #3 ("admin is a placeholder")
  * platform-and-tooling §9 high-severity gap ("operator visibility")
  * this doc's §1 ("operator-facing admin dashboards, not only
    backend metrics")
  * this doc's §3 ("better operator view of what changed recently")

One commit, three gap reviews advanced. That's the next loop pick
if the user signals "advance."
