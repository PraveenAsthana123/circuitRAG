# Architecture Decision Records (ADRs)

A retrospective + ongoing index of the architectural decisions
visible in this repo's commit history. Closes the convergence-
shortlist item "ADR index" (cited 2× — `enterprise-gap-review §2`
and `architecture-and-ai-governance-gap-review §1`).

## What an ADR is here

Each file in this directory captures one decision in four sections:

1. **Status** — Accepted / Proposed / Deprecated / Superseded by ADR-N
2. **Context** — what forces / constraints led to the decision
3. **Decision** — what was decided
4. **Consequences** — what's now true, what trade-offs remain, what
   future work the decision unblocks or constrains

ADRs are append-only. When a decision is reversed, the new ADR
*supersedes* the old one (and updates the old one's Status); the
old ADR is never deleted, because the trail of "we used to do X
and switched to Y because Z" is the load-bearing artefact.

## Index

| # | Title | Status | Implementing commit | Drill |
| --- | --- | --- | --- | --- |
| [001](./001-audit-actor-id-text.md) | `governance.audit_log.actor_id` is TEXT, not UUID | Accepted | `2b47d4a` | `drill_audit_actor_type` |
| [002](./002-circuit-breaker-unification.md) | Single canonical CircuitBreaker; `_MCPBreaker` deleted | Accepted | `d1845ab` | `drill_breaker_transitions`, `drill_multi_breaker_visibility` |
| [003](./003-idempotency-postgres-protocol-seam.md) | Postgres-backed idempotency via `IdempotencyStore` protocol | Accepted | `ce56ab6` | `drill_idempotency_durable` |
| [004](./004-audit-fail-closed-per-call.md) | `fail_closed` is per-call, not per-action policy table | Accepted | `0fad44b` | `drill_audit_fail_closed` |
| [005](./005-action-drafts-state-machine-in-storage.md) | Storage-level CHECK constraints enforce the draft state machine | Accepted | `4455e64` | `drill_action_draft_state_constraint` |
| [006](./006-jwt-strict-claim-validation.md) | JWT verifier rejects malformed-but-decodable tokens | Accepted | `4b11cf8` | `drill_jwt_identity_contract` |
| [007](./007-actor-type-from-identity-not-route.md) | `actor_type` is derived from identity, never from route shape | Accepted | `2b47d4a` | `drill_audit_actor_type` |
| [008](./008-transport-breakers-vector-graph.md) | Per-backend transport breakers around Qdrant + Neo4j | Accepted | `87816d9` | `drill_retrieval_transport_breaker` |
| [009](./009-worker-auto-reject-after-n-failures.md) | Worker auto-rejects drafts after N consecutive 4xx-shape failures | Accepted | `880022e` | `drill_worker_auto_reject` |
| [010](./010-metric-cardinality-no-tenant-label.md) | No `tenant_id` label on Prometheus series — cardinality discipline | Accepted | `334917e`, `aa255a0`, `19ff1eb` | `drill_worker_metrics`, `drill_worker_backlog_age`, `drill_inference_token_metric` |
| [011](./011-drill-pattern-real-stack-no-mocks.md) | Drills exercise real services; mocks belong in pytest | Accepted | (CLAUDE.md §43, every `drill_*.py`) | self-referential |
| [012](./012-orchestration-layer-local-first.md) | Orchestration stays local; defer external frameworks (Paperclip, AutoGen, LangGraph) | Accepted | (this commit) | n/a — design decision |
| [013](./013-audit-redaction-policy.md) | Audit `details` redaction is opt-in per call; default preserves forensics | Proposed | — (deferred from `09458ef`) | n/a until implementing commit lands |
| [028](./028-csv-to-db-ingest-write-surface-contract.md) | CSV-to-DB ingest is a separate approval-gated MCP write surface | Proposed | — (contract only) | future implementation drill set |

## Planned ADRs (not yet authored)

These are decisions visible in pending commits / catalog items:

- ADR-014: Eval-baseline storage — when to cut a baseline, who
  approves replacement, where rows live
  (governance.eval_baselines)
- ADR-015: Presidio NER upgrade for PII — context-aware redaction
  (e.g., "John Smith" → "[REDACTED:person]") layered on top of
  the regex v1
- ADR-016: Cluster-coordinated breaker state — Redis-backed shared
  state for multi-replica deployments
- ADR-017: Audit retention policy — when can rows be dropped /
  archived, and what does that mean for the hash chain

## How to write a new ADR

1. Number it as `NNN-kebab-case-title.md` in this directory.
2. Use the template at the top of any existing ADR.
3. Add a row to the index table above.
4. Mark the row with the implementing commit hash (or "(this commit)"
   if landing together).
5. Reference the ADR from the implementing commit's message.

ADRs are usually **retrospective** here — written after the
implementing commit lands. That's deliberate: writing ADRs upfront
turns into design-by-committee. Writing them after captures the
real reasons rather than the imagined ones.

## What's NOT an ADR

- Bug fixes — go in commit messages
- Internal refactors — go in commit messages
- Style decisions — go in CLAUDE.md or `docs/policies/`
- Per-iteration drill work — go in `docs/scenarios/` and the drill
  itself

ADRs are for decisions that future-you will spend energy *understanding
why we did it that way*. If a fresh reader needs context to trust the
code, that's an ADR.
