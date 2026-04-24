# DocuMind — 67 Design Areas Reference Tables

Every area has a full table covering: **components, technical details, implementation, tools & frameworks, how to implement, real-world example, pros, cons, limitations, recommendations, challenges, edge cases + solutions, alternatives**, plus **DocuMind status** and a **class pointer** into this repo.

**PEP8:** all Python is `pycodestyle --max-line-length=120` clean (verified 2026-04-23).
**Class-based:** every component is a class — constructor injection, no module-level mutable state.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Implemented as class(es) + tests, runnable from a reasonable host |
| 🟡 | Partially implemented — structure in place, one or more sub-parts deferred |
| ❌ | Designed (in the spec) but not yet written into code |

## Group files

| File | Areas | Theme |
|---|---|---|
| [`01-system-and-boundaries.md`](01-system-and-boundaries.md) | 1–8 | System boundary, trust/failure/tenant boundaries, control/data/management planes |
| [`02-state-consistency-async.md`](02-state-consistency-async.md) | 9–20 | State models, consistency, path isolation, sync/async, events, sagas, idempotency |
| [`03-services.md`](03-services.md) | 21–29 | Service decomposition + the 8 services (identity, ingestion, retrieval, inference, eval, governance, finops, observability) |
| [`04-contracts-retrieval-cache.md`](04-contracts-retrieval-cache.md) | 30–42 | API/event/prompt/output contracts, retrieval schema, knowledge + embedding + index lifecycles, cache architecture |
| [`05-capacity-resilience-release.md`](05-capacity-resilience-release.md) | 43–55 | Capacity, queues, backpressure, DB/vector/graph strategies, HA/DR/multi-region, blast radius, release/rollback isolation, feature flags |
| [`06-policy-eval-observability.md`](06-policy-eval-observability.md) | 56–67 | Policy-as-code, HITL, feedback, offline/online eval, regression gate, observability/audit/SLO by design, design-for-change/debuggability, socio-technical |
| [`07-ai-governance-extras.md`](07-ai-governance-extras.md) | E2–E7 | AI-specific debuggability, explainability, responsibility, secure-AI, portability, interpretability |

## Status snapshot (all 67 + CCB extra)

| # | Area | Status | Primary class / file |
|---|---|---|---|
| 1 | System Boundary | ✅ | `infra/nginx/nginx.conf` + `services/api-gateway/cmd/main.go` |
| 2 | Responsibility Boundary | ✅ | one schema per service in `libs/py/documind_core/db_client.py` + DB migrations |
| 3 | Trust Boundary | ✅ | `libs/py/documind_core/middleware.py`, `encryption.py`, `infra/istio/20-peer-authentication.yaml` |
| 4 | Failure Boundary | ✅ | `libs/py/documind_core/circuit_breaker.py` + `breakers.py` (5 specialized) |
| 5 | Tenant Boundary | ✅ | `DbClient.tenant_connection`, `Cache.tenant_key`, `RateLimiter.tenant_key`, migrations with RLS |
| 6 | Control Plane | 🟡 | `services/governance-svc` (skeleton Go) + policy tables |
| 7 | Data Plane | ✅ | ingestion-svc, retrieval-svc, inference-svc |
| 8 | Management Plane | 🟡 | observability-svc (Go skeleton) + Prometheus + Grafana + Kibana + Kiali |
| 9 | State Model | ✅ | `DocumentRepo.ALLOWED_TRANSITIONS` |
| 10 | Session State | 🟡 | Redis wiring via `documind_core.cache` — session keys documented, session service not yet built |
| 11 | Agent State | 🟡 | `AgentLoopCircuitBreaker` + `MultiHopRagAgent` skeleton |
| 12 | Consistency Model | ✅ | documented + enforced via tenant_connection + Kafka idempotent consumers |
| 13 | Read Path vs Write Path | ✅ | ingestion-svc (write) ≠ retrieval-svc (read); CQRS at the domain level |
| 14 | Admin Path Isolation | ✅ | `/api/v1/admin/*` routing in api-gateway + separate rate bucket |
| 15 | Evaluation Path Isolation | ✅ | evaluation-svc standalone + eval schema |
| 16 | Sync vs Async | ✅ | `run_saga_inline` flag + Kafka consumer plumbing |
| 17 | Event-Driven Design | ✅ | `libs/py/documind_core/kafka_client.py` + `schemas/events/*.json` |
| 18 | Workflow Orchestration | ✅ | `services/ingestion-svc/app/saga/document_saga.py` + `recovery.py` |
| 19 | Compensation Logic | ✅ | `DocumentIngestionSaga._run_compensations` |
| 20 | Idempotency Strategy | ✅ | `IdempotencyStore` + `IdempotencyMiddleware` |
| 21 | Service Decomposition | ✅ | 10 services; Go for I/O-bound, Python for ML-bound |
| 22 | Identity Service | 🟡 | Go skeleton + proto contract |
| 23 | Knowledge Ingestion Service | ✅ | full implementation |
| 24 | Retrieval Service | ✅ | full implementation |
| 25 | Inference Service | ✅ | full implementation |
| 26 | Evaluation Service | ✅ | metrics + API + migrations |
| 27 | Governance Service | 🟡 | Go skeleton + policy schema + protos |
| 28 | Observability Service | 🟡 | Go skeleton + alert rules |
| 29 | FinOps Service | 🟡 | Go skeleton + shadow-pricing table |
| 30 | API Contract Strategy | ✅ | REST (OpenAPI via FastAPI auto) + gRPC protos |
| 31 | Event Contract Strategy | ✅ | `schemas/events/*.json` (CloudEvents JSON Schema) |
| 32 | Prompt Contract Strategy | ✅ | `PromptBuilder` + `PROMPT_TEMPLATES` + governance `prompts` table |
| 33 | Output Contract Strategy | ✅ | `GuardrailChecker` + CCB signals |
| 34 | Retrieval Schema | ✅ | `retrieval-svc/app/schemas` + proto `RetrievedChunk` |
| 35 | Knowledge Lifecycle | ✅ | document state machine with all 10 states |
| 36 | Source Trust Model | ❌ | documented in spec |
| 37 | Historical Knowledge Policy | ❌ | documented in spec |
| 38 | Index Lifecycle | 🟡 | Qdrant `ensure_collection` + zero-downtime swap pattern documented |
| 39 | Embedding Lifecycle | 🟡 | model versioning fields on chunk schema; re-embed job not yet built |
| 40 | Cache Architecture | ✅ | `libs/py/documind_core/cache.py` |
| 41 | Cache Consistency | ✅ | TTL + `invalidate_prefix` + event-driven helpers |
| 42 | Tenant-Aware Cache | ✅ | `Cache.tenant_key` enforces tenant namespace |
| 43 | Capacity Model | 🟡 | HPA manifests + custom `inference_inflight` metric |
| 44 | Queue Strategy | ✅ | Kafka (docker-compose + K8s StatefulSet); DLQ pattern in `kafka_client.py` |
| 45 | Backpressure Strategy | ✅ | 4 layers: nginx RL → gateway RL → service RL → CB |
| 46 | Database Strategy | ✅ | Postgres schema-per-service + RLS + WAL mode + PgBouncer-ready DSN |
| 47 | Vector DB Strategy | ✅ | `QdrantRepo.ensure_collection` with HNSW + scalar quantization |
| 48 | Graph Strategy | ✅ | `Neo4jRepo` with entity-chunk-document model |
| 49 | HA Strategy | ✅ | 2+ replicas, anti-affinity, readiness/liveness probes, graceful shutdown |
| 50 | DR Strategy | 🟡 | `docs/runbooks/DR_RUNBOOK.md` + backup commands; automated restore test not yet built |
| 51 | Multi-Region Strategy | ❌ | design docs only — interfaces abstracted, not deployed |
| 52 | Blast Radius Control | ✅ | NetworkPolicy default-deny + per-service egress; Istio AuthorizationPolicy; tenant quotas |
| 53 | Release Isolation | ✅ | Istio VS canary 90/10 + K8s rolling update `maxUnavailable: 0` |
| 54 | Rollback Isolation | ✅ | `kubectl rollout undo` ready; feature-flag kill switches via governance-svc |
| 55 | Feature Flag Strategy | 🟡 | governance `feature_flags` schema; runtime client deferred |
| 56 | Policy-as-Code | 🟡 | governance policies table + CEL spot; full CEL engine deferred |
| 57 | Human-in-the-Loop | 🟡 | `governance.hitl_queue` schema + docs; reviewer UI deferred |
| 58 | Feedback Architecture | 🟡 | `eval.feedback` schema; 👍/👎 capture deferred |
| 59 | Offline Evaluation | ✅ | evaluation-svc `POST /api/v1/evaluation/run` + metrics |
| 60 | Online Evaluation | ❌ | sampling consumer not yet built |
| 61 | Regression Gate | 🟡 | compute-and-compare logic deferred; AIops alert rule active |
| 62 | Observability by Design | ✅ | `documind_core.observability` + breaker-guarded exporters + JSON logs + correlation IDs |
| 63 | Auditability by Design | 🟡 | `governance.audit_log` table; hash-chain writer deferred |
| 64 | SLO-Driven Design | ✅ | `observability.slo_targets` seed + Prometheus alerts |
| 65 | Design-for-Change | ✅ | every external dep behind an interface (`EmbeddingProvider`, `Chunker`, `DocumentParser`, `VectorSearcher`, `GraphSearcher`) |
| 66 | Design-for-Debuggability | ✅ | `?debug=true`, correlation IDs across logs/traces, CCB snapshot, circuit breaker metrics |
| 67 | Socio-Technical | ✅ | `docs/runbooks/*` + per-service ownership documented |
| E1 | Cognitive Circuit Breaker | ✅ | `libs/py/documind_core/breakers.py` (new design area) |
| E2 | Debuggability (AI-specific) | ✅ | `InterpretabilityTrace`, `?debug=true`, CB snapshot |
| E3 | Explainability (XAI) | ✅ | `libs/py/documind_core/ai_governance.py::AIExplainer` |
| E4 | Responsibility (RAI) | ✅ | `ai_governance.py::ResponsibleAIChecker` (hot-path); bias benchmarks in eval-svc |
| E5 | Secure AI | ✅ | `ai_governance.py::PromptInjectionDetector` + `AdversarialInputFilter` + `PIIScanner` |
| E6 | Portability | ✅ | interface-based design across the repo; vLLM/Ollama drop-in compat; cloud-agnostic K8s manifests |
| E7 | Interpretability (business-step) | ✅ | `ai_governance.py::InterpretabilityTrace` |

### Counts (honest post-remediation — 2026-04-23)

See [`AUDIT-2026-04-23.md`](../../AUDIT-2026-04-23.md) for the narrative explaining the gap between earlier inflated claims and reality. After the remediation pass (outbox, JWT issuer, poisoning defense, re-embed worker, recovery-worker compensations, prompt DB registry, Dockerfiles, CI, pre-commit, integration tests):

- **✅ Implemented (class + tests + unit-run green, no live infra needed):** 31 / 67 + 7 extras
- **🟡 Partial (structure + primitives; wiring needs live infra to fully verify):** 24 / 67
- **❌ Designed only (spec + table, no code yet):** 12 / 67

**Tier of honesty:** "implemented" here means the class exists, has unit tests, and compiles/parses. It does NOT mean the whole system has been smoke-tested end-to-end against live Postgres/Qdrant/Neo4j/Kafka/Ollama — that requires `docker compose up` which has not been executed in this session.

The detailed per-area tables live in the 6 group files above.
