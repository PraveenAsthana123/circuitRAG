# Subsystem Ownership Map

Closes the convergence-shortlist "subsystem ownership map" item
(cited 2× — `enterprise-gap-review §2` "ownership map by subsystem"
and `architecture-and-ai-governance-gap-review §5` "subsystem owner
matrix").

Pairs with `.github/CODEOWNERS` (which routes PR reviews) and the
[ADR index](./adr/README.md) (which records *why* decisions
were made). This document answers a different question: **for each
subsystem, who is responsible, what files belong to it, what drills
exercise it, and which ADRs constrain it?**

The repo is currently single-maintainer — every row points to
`@PraveenAsthana123`. The structure is built so it stays useful
when the team grows: a future split (e.g. governance to a dedicated
team) is one column-edit per row, not a re-architecture.

## Ownership table

| Subsystem | Code owner | Key files | Drills | ADRs |
| --- | --- | --- | --- | --- |
| **API gateway** | `@PraveenAsthana123` | `services/api-gateway/cmd/main.go`, `internal/middleware/`, `internal/proxy/` | (Go side; pytest in-svc) | — |
| **Identity** | `@PraveenAsthana123` | `services/identity-svc/`, `libs/py/documind_core/auth.py` | `drill_jwt_identity_contract` | [006](./adr/006-jwt-strict-claim-validation.md) |
| **Ingestion** | `@PraveenAsthana123` | `services/ingestion-svc/app/parsers/`, `app/chunking/`, `app/embedding/`, `app/saga/` | (no end-to-end ingestion drill yet — catalog gap) | — |
| **Retrieval** | `@PraveenAsthana123` | `services/retrieval-svc/app/services/{vector_searcher,graph_searcher,hybrid_retriever,reranker,embedder_client}.py` | `drill_retrieval_tenant_isolation`, `drill_retrieval_degraded_envelope`, `drill_retrieval_transport_breaker` | [008](./adr/008-transport-breakers-vector-graph.md) |
| **Inference** | `@PraveenAsthana123` | `services/inference-svc/app/services/{rag_inference,agent,ollama_client,retrieval_client}.py`, `app/agents/multi_hop_agent.py` | (covered indirectly via agent + worker drills) | — |
| **MCP control plane** | `@PraveenAsthana123` | `mcp/client.py`, `mcp/server_common.py`, `mcp/server_{hr,itsm,drills}.py`, `mcp/drafts.py`, `mcp/idempotency.py` | `drill_audit_actor_type`, `drill_action_draft_state_constraint`, `drill_idempotency_durable`, `drill_draft_reject`, `drill_mcp_server_scope`, `drill_mcp_tool_call_metrics`, `drill_resolve_draft_routing`, `drill_admin_api`, `drill_agent_*` | [001](./adr/001-audit-actor-id-text.md), [003](./adr/003-idempotency-postgres-protocol-seam.md), [005](./adr/005-action-drafts-state-machine-in-storage.md), [007](./adr/007-actor-type-from-identity-not-route.md) |
| **Replay worker** | `@PraveenAsthana123` | `services/inference-svc/app/workers/draft_replay.py` | `drill_audit_actor_type` step 4, `drill_worker_metrics`, `drill_worker_auto_reject`, `drill_worker_backlog_age`, `drill_worker_sweep_span` | [007](./adr/007-actor-type-from-identity-not-route.md), [009](./adr/009-worker-auto-reject-after-n-failures.md), [010](./adr/010-metric-cardinality-no-tenant-label.md) |
| **Audit / governance** | `@PraveenAsthana123` | `libs/py/documind_core/audit.py`, `services/governance-svc/migrations/{001,004,005,006,007}.sql`, `scripts/audit_verify.py` | `drill_audit`, `drill_audit_seal`, `drill_audit_verifier`, `drill_audit_actor_type`, `drill_audit_fail_closed`, `drill_action_draft_state_constraint`, `drill_agent_denial_audit`, `drill_agent_denial_metrics` | [001](./adr/001-audit-actor-id-text.md), [004](./adr/004-audit-fail-closed-per-call.md), [005](./adr/005-action-drafts-state-machine-in-storage.md) |
| **Circuit breakers** | `@PraveenAsthana123` | `libs/py/documind_core/circuit_breaker.py`, `libs/py/documind_core/breakers.py`, `services/inference-svc/app/workers/breaker_metrics.py` | `drill_breaker_transitions`, `drill_multi_breaker_visibility`, `drill_prometheus_breakers`, `drill_health_detailed`, `drill_retrieval_transport_breaker` | [002](./adr/002-circuit-breaker-unification.md), [008](./adr/008-transport-breakers-vector-graph.md) |
| **Observability** | `@PraveenAsthana123` | `libs/py/documind_core/observability.py`, `mcp/server_common.py` (tracer + metrics), `services/inference-svc/app/middleware.py:SpanAttributeMiddleware` | `drill_prometheus_breakers`, `drill_mcp_tool_call_metrics`, `drill_worker_sweep_span` | [010](./adr/010-metric-cardinality-no-tenant-label.md) |
| **FinOps / cost** | `@PraveenAsthana123` | `services/finops-svc/`, `services/inference-svc/app/services/ollama_client.py` (token counter) | `drill_inference_token_metric` | [010](./adr/010-metric-cardinality-no-tenant-label.md) |
| **Evaluation** | `@PraveenAsthana123` | `services/evaluation-svc/`, `data/eval/v1` | (no eval-pipeline drill — catalog gap, planned ADR-014) | — |
| **Frontend** | `@PraveenAsthana123` | `services/frontend/app/`, `components/`, `lib/api.ts`, `styles/` | (manual smoke + `next build`; no headless-browser drill yet) | — |
| **Drill / testing infra** | `@PraveenAsthana123` | `scripts/run_drills.py`, `mcp/server_drills.py`, `mcp/tests/drill_*.py` | `drill_runner_junit`, `drill_runner_scheduler`, `drill_runner_hardening`, `drill_drill_server` | [011](./adr/011-drill-pattern-real-stack-no-mocks.md) |
| **Idempotency** | `@PraveenAsthana123` | `mcp/idempotency.py`, `services/governance-svc/migrations/007_mcp_idempotency.sql`, `libs/py/documind_core/idempotency_middleware.py` | `drill_idempotency_durable` | [003](./adr/003-idempotency-postgres-protocol-seam.md) |
| **Scheduled jobs** | `@PraveenAsthana123` | `scripts/scheduled_kaggle_ingest.sh`, host cron | (no drill — script is operational tooling) | — |
| **Infra / deployment** | `@PraveenAsthana123` | `infra/`, `data/nginx-{tls,cache,logs}/`, `Dockerfile`s | (k8s-side; no in-repo drill) | — |
| **Docs / catalogs** | `@PraveenAsthana123` | `docs/architecture/`, `docs/scenarios/`, `docs/learning/`, `docs/policies/`, `CLAUDE.md` | n/a (markdown reviews) | [012](./adr/012-orchestration-layer-local-first.md) |

## Cross-cutting concerns

Some properties cut across multiple subsystems. When a PR touches
one of these, all listed subsystem owners review:

| Concern | Touches | Why all owners |
| --- | --- | --- |
| **Tenant isolation** | retrieval, audit, MCP, idempotency, observability | a regression in any layer leaks data |
| **JWT shape contract** | identity, MCP, every service | the contract is enforced at every hop |
| **Hash-chain integrity** | audit, governance migrations, audit-verify script | one writer's bug breaks every reader |
| **Circuit-breaker semantics** | every service that uses CircuitBreaker | divergence in semantics defeats unified dashboards (see ADR-002) |
| **Metric label cardinality** | every Prometheus emitter | one label adds 1000 series, all dashboards regress |
| **Drill-real-stack pattern** | every drill author | a mocked drill is a tautology |

## How to update this map

1. When a new subsystem lands, add a row.
2. When a subsystem splits (e.g., retrieval into `retrieval-vector`
   and `retrieval-graph`), keep the parent row + add child rows
   referencing it.
3. When ownership transfers, update the `Code owner` column AND
   `.github/CODEOWNERS` in the same commit.
4. When a new drill targets an existing subsystem, add it to the
   `Drills` column. The grep target is the subsystem row, not a
   separate index.
5. When a new ADR constrains an existing subsystem, add it to the
   `ADRs` column. Use the [adr/README.md](./adr/README.md) index
   as the source of truth.

## Why this format

The alternatives considered:

* **`CODEOWNERS` alone** — routes PR reviews but doesn't link to
  drills/ADRs. A reviewer landing on a draft-replay PR has no
  pointer to "which drills should I run?" or "what ADRs constrain
  this?"
* **Per-subsystem README in each directory** — already exists
  partially. Useful for in-tree navigation; less useful when a
  reviewer needs the cross-subsystem picture (e.g., "tenant
  isolation: which subsystems own which piece?").
* **A ticketing-system / wiki link** — fragile across migrations.
  Markdown in the repo is the authoritative artefact.

This map sits *above* CODEOWNERS (one line per directory) and
*below* the ADRs (one decision per file). It's the index that makes
both useful.

## Cross-references

- [.github/CODEOWNERS](../../.github/CODEOWNERS) — PR review routing
- [docs/architecture/adr/README.md](./adr/README.md) — decision
  index
- [docs/scenarios/pipeline-catalog.md](../scenarios/pipeline-catalog.md)
  — pipeline-shaped view (15 pipelines × 4 dimensions each)
- [docs/policies/DRILL-TESTING-POLICY.md](../policies/DRILL-TESTING-POLICY.md)
  — drill discipline
