# DocuMind — Tech Stack Inventory

Every piece of load-bearing software and the exact version. If it's not on this page and we rely on it, that's a gap — file it as a design-area issue.

Updated: 2026-04-23.

---

## Runtime services

| Service | Language | Framework | Port (dev) | Responsibility |
| --- | --- | --- | --- | --- |
| `api-gateway` | Go 1.22 | `net/http` + `chi` | 8080 | JWT validation, correlation-id, rate limit, route |
| `ingestion-svc` | Python 3.11 | FastAPI | 8081 | Upload → parse → chunk → embed saga |
| `retrieval-svc` | Python 3.11 | FastAPI | 8082 | Qdrant + Neo4j hybrid retrieval, reranking |
| `inference-svc` | Python 3.11 | FastAPI | 8083 | LLM calls, prompt/PII/injection checks, CCB |
| `governance-svc` | Python 3.11 | FastAPI | 8084 | HITL queue, audit log, responsible-AI checks |
| `finops-svc` | Python 3.11 | FastAPI | 8085 | Token usage, budgets, billing rollups |
| `evaluation-svc` | Python 3.11 | FastAPI | 8086 | Eval suites, feedback, drift detection |
| `identity-svc` | Python 3.11 | FastAPI | 8087 | Users, tenants, API keys, JWT minting |
| `observability-svc` | Python 3.11 | FastAPI | 8088 | SLO definitions, alert rules, incident log |
| `frontend` | TypeScript | Next.js 14 (App Router) | 3000 | UI — upload, ask, documents, /tools |

---

## Data stores

| Store | Version | Purpose | Port | Notes |
| --- | --- | --- | --- | --- |
| PostgreSQL | 16 | Source of truth, RLS-enforced | 5432 | FORCE RLS on every tenant table. Three roles: `documind` (owner), `documind_app` (runtime, NOBYPASSRLS), `documind_ops` (privileged, BYPASSRLS). |
| Qdrant | 1.12 | Vector ANN | 6333 | Payload filter `tenant_id` is mandatory on every query. HNSW + scalar quantization. |
| Neo4j | 5.23 | Knowledge graph | 7687 | Relationship traversal for multi-hop retrieval. |
| Redis | 7.4 | Cache + rate limit | 6379 | Keys namespaced `{tenant_id}:…`. AOF + RDB persistence. |
| Kafka | 3.7 | Event backbone | 9092 | CloudEvents envelope. Outbox pattern (PG → Kafka via relay). |
| MinIO | RELEASE.2024-10-13 | S3-compatible blob | 9000 | Raw document uploads. Signed URLs for direct-to-store. |

---

## AI / Inference

| Component | Version | Purpose |
| --- | --- | --- |
| Ollama | 0.4 | Local LLM host — llama3, mistral, phi3 |
| vLLM | 0.6 | GPU-backed inference (production) |
| BGE-m3 | via sentence-transformers 3.1 | Embeddings (1024-dim, multilingual) |
| BGE reranker v2 | cross-encoder | Rerank top-20 → top-5 |
| Llama-guard-3-8b | via Ollama | Output safety classifier |

---

## Networking / mesh

| Component | Version | Purpose |
| --- | --- | --- |
| Istio | 1.23 | Service mesh, mTLS STRICT, AuthorizationPolicy |
| NGINX | 1.27 | Edge ingress + CDN-style caching for /assets |
| gRPC | via `grpcio` 1.66 | Internal service-to-service RPCs (see `proto/`) |
| Envoy | 1.31 (inside Istio) | Data-plane proxy |
| Kiali | 1.89 | Service mesh visualization |

---

## Observability

| Component | Version | Purpose |
| --- | --- | --- |
| OpenTelemetry Collector | 0.109 | Traces + metrics + logs pipeline |
| Prometheus | 2.54 | Metrics storage + alerting |
| Grafana | 11.2 | Dashboards |
| Jaeger | 1.60 | Distributed traces UI |
| Elasticsearch | 8.15 | Log search |
| Logstash | 8.15 | Log pipeline |
| Kibana | 8.15 | Log UI |

---

## Reliability primitives

| Primitive | Location | Guards |
| --- | --- | --- |
| Generic circuit breaker | `libs/py/documind_core/circuit_breaker.py` | Any external call |
| Retrieval CB | `services/retrieval-svc/app/breakers.py` | Qdrant + Neo4j |
| Token CB | `services/inference-svc/app/breakers.py` | Token spend per minute |
| Agent-loop CB | `services/inference-svc/app/breakers.py` | Agent recursion depth + wall-clock |
| Observability CB | `libs/py/documind_core/observability_breaker.py` | OTel collector + Prom pushgateway |
| Cognitive CB | `libs/py/documind_core/ccb.py` | LLM token stream (repetition, drift, rules) |

---

## Governance / safety

| Module | Purpose |
| --- | --- |
| `PromptInjectionDetector` | Input scanner, regex + classifier |
| `PIIScanner` | Emails, phones, SSNs, credit cards, names |
| `AdversarialInputFilter` | Character-level obfuscation, zero-width attacks |
| `ResponsibleAIChecker` | Output scanner — toxicity, bias, PII leakage |
| `AIExplainer` | Per-decision explanation record |
| `InterpretabilityTrace` | Full span-level trace of decision path |

---

## Dev + CI

| Tool | Purpose |
| --- | --- |
| `pytest` | Test runner |
| `ruff` | Lint (replaces flake8, pyflakes, pyupgrade) |
| `black` | Formatter |
| `mypy` | Type check |
| `bandit` | Security lint |
| `pip-audit` | Dependency CVE scan |
| `pre-commit` | Git hooks |
| `Makefile` | `make test` / `make lint` / `make build` |
| GitHub Actions | CI on every PR (matrix per service) |
| Docker Compose | Local dev stack |
| Playwright | E2E (frontend) |
| Vitest | Frontend unit tests |

---

## Dependencies to audit quarterly

Third-party packages that could shift licensing or abandonware risk:

- `asyncpg` (Postgres driver) — MIT, active
- `qdrant-client` — Apache-2.0, Qdrant maintains
- `neo4j` (driver) — Apache-2.0, Neo4j maintains
- `redis-py` — MIT, active
- `opentelemetry-*` — Apache-2.0, CNCF
- `fastapi` — MIT, active
- `pydantic` v2 — MIT, active
- `grpcio` — Apache-2.0, Google

Any package move to a dual license or rug-pull gets an ADR within a week.
