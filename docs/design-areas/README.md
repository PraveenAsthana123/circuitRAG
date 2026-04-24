# Design Areas — Index

This directory contains one doc per design area from the spec, each linking
to the code that implements it. The full written spec is at
[`../superpowers/specs/2026-04-23-documind-system-design.md`](../superpowers/specs/2026-04-23-documind-system-design.md);
this directory is the shorter, code-pointer view.

## The 67 areas, grouped

### Structure (Areas 1-8)

| # | Area | Code pointer |
| --- | --- | --- |
| 1 | System Boundary | `services/api-gateway/cmd/main.go` |
| 2 | Responsibility Boundary | `services/*/README.md` + spec table in §2.3 |
| 3 | Trust Boundary | `libs/py/documind_core/encryption.py`, `libs/py/documind_core/middleware.py` |
| 4 | Failure Boundary | `libs/py/documind_core/circuit_breaker.py` |
| 5 | Tenant Boundary | `libs/py/documind_core/db_client.py` (RLS), every `*_repo.py` |
| 6 | Control Plane | `services/governance-svc/cmd/main.go` |
| 7 | Data Plane | `services/ingestion-svc`, `services/retrieval-svc`, `services/inference-svc` |
| 8 | Management Plane | `services/observability-svc`, `services/finops-svc` |

### State + behavior (Areas 9-20)

| # | Area | Code pointer |
| --- | --- | --- |
| 9 | State Model | `services/ingestion-svc/app/repositories/document_repo.py` (ALLOWED_TRANSITIONS) |
| 10 | Session State | Redis (spec) — externalized, no in-process state |
| 11 | Agent State | Stubbed for summarization use case; spec Area 11 |
| 12 | Consistency Model | `docs/superpowers/specs/...md` Area 12 table |
| 13 | Read vs Write Path | `ingestion-svc` (write) vs `retrieval-svc` (read) |
| 14 | Admin Path Isolation | `services/api-gateway/cmd/main.go` (admin router group) |
| 15 | Evaluation Path Isolation | `services/evaluation-svc` |
| 16 | Sync vs Async | `services/ingestion-svc/app/services/ingestion_service.py` (run_saga_inline) |
| 17 | Event-Driven Design | `libs/py/documind_core/kafka_client.py`, `schemas/events/*.json` |
| 18 | Workflow Orchestration | `services/ingestion-svc/app/saga/document_saga.py` |
| 19 | Compensation Logic | `DocumentIngestionSaga._run_compensations` |
| 20 | Idempotency Strategy | `libs/py/documind_core/idempotency.py` |

### Services + contracts (Areas 21-33)

See individual service code + `schemas/events/*.json` for event contracts,
`libs/py/documind_core/schemas.py` for API contract shapes,
`services/inference-svc/app/services/prompt_builder.py` for prompt versioning.

### Retrieval + data (Areas 34-48)

| # | Area | Code pointer |
| --- | --- | --- |
| 34 | Retrieval Schema | `services/retrieval-svc/app/schemas/__init__.py` |
| 35 | Knowledge Lifecycle | `services/ingestion-svc/app/repositories/document_repo.py` states |
| 36 | Source Trust Model | Stubbed for demo (spec Area 36) |
| 37 | Historical Knowledge | Stubbed for demo |
| 38 | Index Lifecycle | `QdrantRepo.ensure_collection` |
| 39 | Embedding Lifecycle | `OllamaEmbedder.model_name`, re-embed on model change (spec) |
| 40 | Cache Architecture | `libs/py/documind_core/cache.py` |
| 41 | Cache Consistency | `Cache.invalidate_prefix` + event-driven invalidation |
| 42 | Tenant-Aware Cache | `Cache.tenant_key`, `rate_limiter.tenant_key` |
| 43 | Capacity Model | `services/observability-svc/cmd/main.go` |
| 44 | Queue Strategy | `schemas/events/*.json` + Kafka topic partitioning |
| 45 | Backpressure | `libs/py/documind_core/middleware.py` (RateLimitMiddleware) |
| 46 | Database Strategy | `libs/py/documind_core/db_client.py` + migrations/ |
| 47 | Vector DB Strategy | `services/ingestion-svc/app/repositories/qdrant_repo.py` |
| 48 | Graph Strategy | `services/ingestion-svc/app/repositories/neo4j_repo.py` |

### Resilience + release (Areas 49-55)

Most of these live as design decisions documented in the spec + infra/istio.
For the local demo, they're implemented as application-level patterns:
circuit breaker + rate limiting + feature flags live in `libs/py`.

### Policy + feedback (Areas 56-58)

| # | Area | Code pointer |
| --- | --- | --- |
| 56 | Policy-as-Code | `services/governance-svc/cmd/main.go` (Policy struct + CEL) |
| 57 | HITL | `services/governance-svc/migrations/001_initial.sql` (hitl_queue) |
| 58 | Feedback | `services/evaluation-svc/migrations/001_initial.sql` (feedback) |

### Evaluation (Areas 59-61)

| # | Area | Code pointer |
| --- | --- | --- |
| 59 | Offline Evaluation | `services/evaluation-svc/app/main.py` (run_scoring) |
| 60 | Online Evaluation | Stubbed (spec Area 60) |
| 61 | Regression Gate | Stubbed endpoint in evaluation-svc |

### By-design (Areas 62-66)

| # | Area | Code pointer |
| --- | --- | --- |
| 62 | Observability by Design | `libs/py/documind_core/observability.py`, `logging_config.py` |
| 63 | Auditability by Design | `governance.audit_log` migration + spec Area 63 |
| 64 | SLO-Driven Design | `services/observability-svc/cmd/main.go` + migration |
| 65 | Design-for-Change | Every `*/base.py` defining an interface (EmbeddingProvider, DocumentParser, Chunker, ...) |
| 66 | Design-for-Debuggability | `debug=true` query param in inference-svc; `X-Correlation-ID` everywhere |

### Socio-technical (Area 67)

Documented in spec + `docs/runbooks/`. Code can't encode Conway's law —
team structure does.
