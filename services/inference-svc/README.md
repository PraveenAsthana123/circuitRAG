# 📦 `inference-svc` — Advanced README

🧩 **Service**  ·  **Path:** `services/inference-svc`  ·  **Generated:** 2026-05-16 20:02 UTC

> Inference service FastAPI application.

This README is **auto-generated** by [`scripts/generate_folder_report.py`](../../scripts/generate_folder_report.py). It explains what this folder does, every file inside it, how the files link to each other, every API endpoint, every database call, every test case, and the production controls (security / reliability / performance / observability). Re-run after major changes.

---

## 🔎 Section 0 — Auto-Detected Facts

| Metric | Value |
|---|---|
| Folder | `services/inference-svc` |
| Total files | 27 |
| Python files | 22 |
| TypeScript/JS files | 0 |
| Go files | 0 |
| Shell scripts | 0 |
| Lines of code | 5,174 |
| Python classes | 54 |
| Python functions | 97 |
| Async functions | 56 |
| Total API endpoints | 3 |
| Total DB call sites | 14 |
| DB / Storage libs | Kafka (aiokafka), Redis, asyncpg |
| Concurrency primitives | Lock / RLock, asyncio (async/await) |
| Caching primitives | redis |
| Input validation | Pydantic BaseModel |
| AI / LLM deps | Anthropic SDK, LangChain, LangGraph, Ollama, OpenAI SDK, Ragas |
| Test files | 1 |
| Detected test cases | 3 |
| Tests dir present | ✅ |
| Dockerfile | ✅ |
| pyproject.toml | ❌ |
| go.mod | ❌ |
| package.json | ❌ |
| Top git contributors | `71	PraveenAsthana123`, `6	Praveen` |

#### Longest functions (top 5)

| Location | Name | Lines |
|---|---|---|
| `app/services/rag_inference.py:121` | `ask` | 381 |
| `app/main.py:49` | `create_app` | 369 |
| `app/main.py:71` | `lifespan` | 277 |
| `app/routers/__init__.py:326` | `health_upstreams` | 260 |
| `app/routers/__init__.py:1080` | `admin_trace_link` | 199 |

#### Smells detected (grep heuristics — verify manually)

| Smell | Count |
|---|---|
| hardcoded localhost URL | 2 |


## 1. Purpose — Business + Technical

### Business problem this folder solves

> _Reviewer to fill: Inference service FastAPI application._

### Technical contract this folder exposes

> _Reviewer to fill: API surface, events emitted, data persisted, downstream consumers._

### Out-of-scope (what this folder does NOT do)

> _Reviewer to fill: explicit non-goals — prevents scope creep at review time._


## 2. File Inventory

Every Python file in this folder, with role / classes / functions / LOC / first docstring line. Full absolute paths listed below the table for easy `cat`-ability.

| Relative path | Role (inferred) | Classes | Functions | LOC | Summary |
|---|---|---|---|---|---|
| `app/agents/__init__.py` | 🚀 entry point / app bootstrap | 0 | 0 | 16 | Agent orchestration (Design Area 11 — Agent State, + Extra — CCB). |
| `app/agents/multi_hop_agent.py` | 🚀 entry point / app bootstrap | 2 | 0 | 179 | Multi-hop RAG agent — skeleton showing the full breaker story in action. |
| `app/agents/multi_hop_fanout.py` | 🚀 entry point / app bootstrap | 2 | 1 | 235 | Parallel sub-question fanout for the multi-hop RAG agent. |
| `app/core/config.py` | ⚙ config / settings | 1 | 0 | 18 | Inference-service configuration. |
| `app/main.py` | 🚀 entry point / app bootstrap | 0 | 1 | 421 | Inference service FastAPI application. |
| `app/routers/__init__.py` | 🌐 HTTP router / API endpoints | 0 | 20 | 1660 | Inference HTTP routes. |
| `app/schemas/__init__.py` | 📋 data model / schema | 32 | 0 | 698 | Inference request/response schemas (Design Area 33 — Output Contract). |
| `app/services/__init__.py` | 🧠 business service / use-case | 0 | 0 | 19 | _(no docstring)_ |
| `app/services/agent.py` | 🧠 business service / use-case | 2 | 1 | 323 | Agent flow: answer + optional MCP action. |
| `app/services/guardrails.py` | 🧠 business service / use-case | 3 | 0 | 209 | Output guardrails (Design Area 33 — Output Contract, §38 AI Governance). |
| `app/services/ollama_client.py` | 🧠 business service / use-case | 2 | 1 | 191 | Ollama LLM client — wrapped in a circuit breaker. |
| `app/services/prompt_builder.py` | 🧠 business service / use-case | 2 | 0 | 102 | Prompt construction + versioning (Design Area 32 — Prompt Contract). |
| `app/services/prompt_repo.py` | 🧠 business service / use-case | 2 | 0 | 327 | DB-backed prompt registry (Design Area 32 — Prompt Contract). |
| `app/services/rag_inference.py` | 🧠 business service / use-case | 1 | 0 | 502 | RagInferenceService — end-to-end glue for the read path. |
| `app/services/retrieval_client.py` | 🧠 business service / use-case | 1 | 0 | 51 | gRPC/HTTP client for retrieval-svc (using HTTP+JSON here for simplicity). |
| `app/workers/__init__.py` | 🚀 entry point / app bootstrap | 0 | 0 | 2 | Background workers scheduled from the inference-svc lifespan. |
| `app/workers/breaker_metrics.py` | 🚀 entry point / app bootstrap | 1 | 0 | 123 | Background exporter: bridges non-CircuitBreaker breakers into the |
| `app/workers/draft_replay.py` | 🚀 entry point / app bootstrap | 1 | 4 | 558 | Draft replay worker — periodically resolves pending MCP drafts. |
| `tests/conftest.py` | 📄 module | 0 | 1 | 21 | pytest config for inference-svc tests. |
| `tests/test_integration_inference.py` | 🧪 test | 0 | 3 | 143 | Integration test for RagInferenceService with mocked externals. |

### Absolute paths (clickable)

- `/mnt/deepa/rag/services/inference-svc/app/agents/__init__.py`
- `/mnt/deepa/rag/services/inference-svc/app/agents/multi_hop_agent.py`
- `/mnt/deepa/rag/services/inference-svc/app/agents/multi_hop_fanout.py`
- `/mnt/deepa/rag/services/inference-svc/app/core/config.py`
- `/mnt/deepa/rag/services/inference-svc/app/main.py`
- `/mnt/deepa/rag/services/inference-svc/app/routers/__init__.py`
- `/mnt/deepa/rag/services/inference-svc/app/schemas/__init__.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/__init__.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/agent.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/guardrails.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/ollama_client.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/prompt_builder.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/prompt_repo.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/rag_inference.py`
- `/mnt/deepa/rag/services/inference-svc/app/services/retrieval_client.py`
- `/mnt/deepa/rag/services/inference-svc/app/workers/__init__.py`
- `/mnt/deepa/rag/services/inference-svc/app/workers/breaker_metrics.py`
- `/mnt/deepa/rag/services/inference-svc/app/workers/draft_replay.py`
- `/mnt/deepa/rag/services/inference-svc/tests/conftest.py`
- `/mnt/deepa/rag/services/inference-svc/tests/test_integration_inference.py`


## 3. C4 Model — Context / Container / Component / Code

### Level 1 — System Context

_Where does this folder sit in the broader system?_

```mermaid
flowchart LR
    Caller([External Caller]) --> This["inference-svc"]
    This --> documind_core_breakers[documind_core/breakers]
    This --> app_services[app/services]
    This --> documind_core_config[documind_core/config]
    This --> documind_core_auth[documind_core/auth]
    This --> documind_core_logging_config[documind_core/logging_config]
    This --> documind_core_middleware[documind_core/middleware]
```

### Level 2 — Container

_What external dependencies does this folder talk to?_

```mermaid
flowchart TB
    subgraph inference-svc
        Code[Source Code]
    end
    Code --> DB_0[("Kafka (aiokafka)")]
    Code --> DB_1[("Redis")]
    Code --> DB_2[("asyncpg")]
    Code --> AI_0{{LLM: Anthropic SDK}}
    Code --> AI_1{{LLM: LangChain}}
    Code --> AI_2{{LLM: LangGraph}}
    Code --> AI_3{{LLM: Ollama}}
    Code --> AI_4{{LLM: OpenAI SDK}}
    Code --> AI_5{{LLM: Ragas}}
```

### Level 3 — Component

_Internal files grouped by inferred role._

```mermaid
flowchart TB
    subgraph __entry_point___app_bootstrap["🚀 entry point / app bootstrap"]
        app_agents___init___py["app/agents/__init__.py"]
        app_agents_multi_hop_agent_py["app/agents/multi_hop_agent.py"]
        app_agents_multi_hop_fanout_py["app/agents/multi_hop_fanout.py"]
        app_main_py["app/main.py"]
        app_workers___init___py["app/workers/__init__.py"]
        app_workers_breaker_metrics_py["app/workers/breaker_metrics.py"]
        more___entry_point___app_bootstrap["... +1 more"]
    end
    subgraph __config___settings["⚙ config / settings"]
        app_core_config_py["app/core/config.py"]
    end
    subgraph __HTTP_router___API_endpoints["🌐 HTTP router / API endpoints"]
        app_routers___init___py["app/routers/__init__.py"]
    end
    subgraph __data_model___schema["📋 data model / schema"]
        app_schemas___init___py["app/schemas/__init__.py"]
    end
    subgraph __business_service___use_case["🧠 business service / use-case"]
        app_services___init___py["app/services/__init__.py"]
        app_services_agent_py["app/services/agent.py"]
        app_services_guardrails_py["app/services/guardrails.py"]
        app_services_ollama_client_py["app/services/ollama_client.py"]
        app_services_prompt_builder_py["app/services/prompt_builder.py"]
        app_services_prompt_repo_py["app/services/prompt_repo.py"]
        more___business_service___use_case["... +2 more"]
    end
    subgraph __module["📄 module"]
        tests_conftest_py["tests/conftest.py"]
    end
    subgraph __test["🧪 test"]
        tests_test_integration_inference_py["tests/test_integration_inference.py"]
    end
```

### Level 4 — Code (top hotspots)

_Longest functions — these are the most likely refactor candidates._

```mermaid
flowchart TB
    app_services_rag_inference_py_121_ask["ask (381 lines)<br/>app/services/rag_inference.py:121"]
    app_main_py_49_create_app["create_app (369 lines)<br/>app/main.py:49"]
    app_main_py_71_lifespan["lifespan (277 lines)<br/>app/main.py:71"]
    app_routers___init___py_326_health_upstr["health_upstreams (260 lines)<br/>app/routers/__init__.py:326"]
    app_routers___init___py_1080_admin_trace["admin_trace_link (199 lines)<br/>app/routers/__init__.py:1080"]
```


## 4. Code Sequence — How Files Link to Each Other

**Import graph for files in this folder.** Reading order: start at any entry-point file (look for `🚀 entry point` role in the inventory above), then follow the arrows.

```mermaid
flowchart LR
    app_agents_multi_hop_agent_py["app/agents/multi_hop_agent.py"] --> app_services___init___py["app/services/__init__.py"]
    app_main_py["app/main.py"] --> app_core_config_py["app/core/config.py"]
    app_main_py["app/main.py"] --> app_routers___init___py["app/routers/__init__.py"]
    app_main_py["app/main.py"] --> app_services___init___py["app/services/__init__.py"]
    app_main_py["app/main.py"] --> app_workers___init___py["app/workers/__init__.py"]
    app_routers___init___py["app/routers/__init__.py"] --> app_schemas___init___py["app/schemas/__init__.py"]
    app_routers___init___py["app/routers/__init__.py"] --> app_services___init___py["app/services/__init__.py"]
    app_services_agent_py["app/services/agent.py"] --> app_schemas___init___py["app/schemas/__init__.py"]
    app_services_agent_py["app/services/agent.py"] --> app_services___init___py["app/services/__init__.py"]
    app_services_rag_inference_py["app/services/rag_inference.py"] --> app_schemas___init___py["app/schemas/__init__.py"]
    tests_test_integration_inference_py["tests/test_integration_inference.py"] --> app_schemas___init___py["app/schemas/__init__.py"]
    tests_test_integration_inference_py["tests/test_integration_inference.py"] --> app_services___init___py["app/services/__init__.py"]
```

### Edge list

| From file | To file | Import-count |
|---|---|---|
| `tests/test_integration_inference.py` | `app/services/__init__.py` | 9 |
| `app/routers/__init__.py` | `app/services/__init__.py` | 3 |
| `tests/test_integration_inference.py` | `app/schemas/__init__.py` | 3 |
| `app/main.py` | `app/services/__init__.py` | 2 |
| `app/main.py` | `app/workers/__init__.py` | 2 |
| `app/agents/multi_hop_agent.py` | `app/services/__init__.py` | 1 |
| `app/main.py` | `app/core/config.py` | 1 |
| `app/main.py` | `app/routers/__init__.py` | 1 |
| `app/routers/__init__.py` | `app/schemas/__init__.py` | 1 |
| `app/services/agent.py` | `app/schemas/__init__.py` | 1 |
| `app/services/agent.py` | `app/services/__init__.py` | 1 |
| `app/services/rag_inference.py` | `app/schemas/__init__.py` | 1 |


## 5. Request Flowchart

Generic request lifecycle for this folder. Branches that don't apply are auto-removed based on detected dependencies (DB / cache / LLM).

```mermaid
flowchart TD
    Start([Request arrives]) --> Validate{{Validate input}}
    Validate -- invalid --> Err400[400 Bad Request]
    Validate -- ok --> Auth{{Auth + RBAC check}}
    Auth -- denied --> Err401[401/403]
    Auth -- ok --> Logic[Business logic]
    Logic --> CacheCheck{{Cache hit?}}
    CacheCheck -- yes --> Return[Return cached]
    CacheCheck -- no --> Compute[Compute / fetch]
    Compute --> DB[(Database)]
    DB --> Compute
    Compute --> LLM{{LLM / RAG call}}
    LLM --> Compute
    Compute --> Log[Emit log + metric + trace span]
    Log --> Return2[Return response]
    Err400 --> Log
    Err401 --> Log
```


## 6. API Endpoints — Input / Process / Output

**Detected endpoints:** 3

| Method | Route | Defined in | Input (schema) | Process (summary) | Output (schema) |
|---|---|---|---|---|---|
| `GET` | `/health` | `app/routers/__init__.py:52` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/api/v1/ask` | `app/routers/__init__.py:1288` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/api/v1/agent/ask` | `app/routers/__init__.py:1355` | _TBD_ | _TBD_ | _TBD_ |

_Reviewer fills the last three columns from the Pydantic models in the handler. Auto-extraction of Pydantic schemas is on the roadmap._


## 7. Sequence Diagrams per Endpoint

### Generic flow (all endpoints)

```mermaid
sequenceDiagram
  autonumber
  participant Client
  participant API as inference-svc
  participant MW as Middleware (auth + logging)
  participant Svc as Business Service
  participant DB as Database
  Client->>API: HTTP request
  API->>MW: pass through
  MW-->>API: validated + auth ok
  API->>Svc: call handler
  Svc->>DB: read / write
  DB-->>Svc: result
  Svc-->>API: domain object
  API-->>Client: JSON response
  Note over API: emit log + metric + span
```

### Per-endpoint sequence stubs (top 5)

### `GET /health` (app/routers/__init__.py:52)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/__init__.py:52)
  participant S as Service
  participant D as DB / external
  C->>H: GET /health
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /api/v1/ask` (app/routers/__init__.py:1288)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/__init__.py:1288)
  participant S as Service
  participant D as DB / external
  C->>H: POST /api/v1/ask
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /api/v1/agent/ask` (app/routers/__init__.py:1355)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/__init__.py:1355)
  participant S as Service
  participant D as DB / external
  C->>H: POST /api/v1/agent/ask
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```


## 8. Database Layer

**DB / storage libraries:** Kafka (aiokafka), Redis, asyncpg

**Total DB call sites:** 14

| Pattern | Count |
|---|---|
| `fetch/fetchall/fetchrow` | 6 |
| `ORM CRUD` | 8 |

### Query Optimization checklist

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Indexes on every WHERE / ORDER BY column | — | EXPLAIN ANALYZE hot paths |
| Full table scans avoided | — | — |
| Batch operations used (not N writes in a loop) | — | — |
| Parameterized queries (NEVER f-string SQL) | — | — |

### Transactions (ACID)

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Transaction boundaries narrow (no HTTP / LLM inside) | — | — |
| Rollback on exception | — | — |
| Isolation level documented (READ COMMITTED / SERIALIZABLE) | — | — |
| Deadlock prevention strategy | — | — |

### N+1 Query Findings (reviewer to fill)

| Endpoint / Function | Suspect Loop | Est. Queries / Request | Fix |
|---|---|---|---|
| — | — | — | — |


## 9. Code Quality + Complexity

### Readability

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Clear variable / function / class names | — | — |
| No misleading naming (no `tmp` / `xyz` / `foo`) | — | — |
| Small focused functions (≤ 50 lines) | — | 5 > 50 lines (see Section 0) |
| Avoid deeply nested conditions (≤ 4 levels) | — | — |

### Clean code

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| No dead / commented-out code | — | — |
| No `print()` — use logger | — | — |
| No hardcoded values | — | smell count: 2 |
| Constants extracted to a settings module | — | — |

### Complexity

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Long methods broken down | — | — |
| No overengineering (premature abstractions) | — | — |
| Cyclomatic complexity ≤ 15 per function | — | run `ruff complexity` or `radon` |


## 10. Security Review

### Authentication & Authorization

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Authentication implemented correctly | — | Bearer / JWT / session |
| Authorization (RBAC / ABAC) checks | — | no client-side trust |
| Tokens validated server-side every request | — | rotate, expire, revoke |

### OWASP Top 10

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Request validation present | — | sanitization: Pydantic BaseModel |
| SQL injection prevention | — | DB libs: Kafka (aiokafka), Redis, asyncpg — parameterized queries only |
| XSS / CSRF prevention | — | output encoding / CSP / SameSite |
| Path traversal prevention | — | no user input concatenated to file paths |
| Prompt injection prevention | — | Rebuff / output filter |

### Secret Management

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| No secrets in code | — | smell count: 0 password literals, 0 api key literals |
| Env vars / Vault used | — | Pydantic BaseSettings or env reader |
| Secret rotation strategy | — | documented in runbook |

### Sensitive Data

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| PII masked in logs | — | structured logger with field redaction |
| Encryption in transit (TLS) | — | — |
| Encryption at rest (DB / object store) | — | — |
| GDPR — retention + right-to-be-forgotten | — | — |


## 11. Performance Review

### Memory

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Large object retention avoided | — | — |
| Streaming for large files / data | — | — |
| Caches bounded (LRU / TTL) | — | caching: redis |

### Concurrency

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Thread safety validated | — | primitives: Lock / RLock, asyncio (async/await) |
| Race conditions prevented | — | — |
| Deadlocks avoided (lock ordering) | — | — |
| Parallel processing where beneficial | — | 56 async fns |

### Latency

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| External API calls batched / cached | — | — |
| Timeouts on every external call | — | — |
| No blocking I/O inside async functions | — | — |


## 12. Reliability & Observability

### Failure Handling

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Retry (bounded + exp backoff + jitter) | — | — |
| Circuit breaker around external deps | — | — |
| Graceful degradation | — | — |

### Timeout Handling

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Timeout on every external call (HTTP / DB / subprocess) | — | — |
| No infinite waits | — | — |

### Observability

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Structured (JSON) logging | — | correlation_id + tenant_id + request_id |
| Metrics (RED: rate / errors / duration) | — | — |
| Tracing (OpenTelemetry → Jaeger / Tempo) | — | — |
| Baggage propagation across services | — | — |


## 13. Test Cases

**Test files detected:** 1
**Test functions parsed:** 3

| Test name | Location | Purpose (from docstring) |
|---|---|---|
| `test_rag_inference_happy_path` | `tests/test_integration_inference.py:25` | _(no docstring)_ |
| `test_rag_inference_rejects_prompt_injection` | `tests/test_integration_inference.py:85` | _(no docstring)_ |
| `test_rag_inference_empty_retrieval_raises` | `tests/test_integration_inference.py:118` | _(no docstring)_ |

### Coverage matrix (reviewer to fill)

| Metric | Value | Min |
|---|---|---|
| Statement coverage | _TBD_ % | 80% |
| Branch coverage | _TBD_ % | 70% |
| Critical-path coverage | _TBD_ % | 100% |
| Negative-test coverage | _TBD_ % | 80% |


## 14. Logging & Monitoring

### Logging

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Structured (JSON) logs | — | — |
| Correlation ID present | — | — |
| No PII / secrets in log lines | — | — |
| No excessive logging (no logs in hot loops) | — | — |

### Monitoring

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Alerts defined (SLO-burn aware) | — | — |
| Dashboards exist (Grafana) | — | — |
| On-call playbook references | — | — |


## 15. LLM / GenAI / RAG

**Detected AI deps:** Anthropic SDK, LangChain, LangGraph, Ollama, OpenAI SDK, Ragas

### Prompt Safety

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Prompt injection handling (input filter) | — | — |
| Output sanitization | — | — |
| Prompt versioning in registry | — | — |
| Toxicity / bias filtering | — | — |

### RAG Quality

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Chunking strategy validated (size + overlap) | — | — |
| Embedding model versioned (re-embed on bump) | — | — |
| Vector DB query optimized (recall@k measured) | — | — |
| Metadata filtering exists (per-tenant) | — | — |

### Cost

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Model fallback strategy defined | — | — |
| Token usage minimized (cache / truncation) | — | — |
| Per-tenant cost ceiling enforced | — | — |

### Explainability / Responsible AI

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Citation / source grounding (every claim cited) | — | — |
| Confidence scoring (Ragas / DeepEval) | — | Ragas |
| Decision audit row per prediction (§48) | — | — |
| Fairness / bias checks | — | — |


## 16. SOLID + Microservice Principles

### SOLID

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| S — Single Responsibility (one reason to change per class) | — | — |
| O — Open/Closed (extend via composition, not modification) | — | — |
| L — Liskov Substitution (subclasses honor contracts) | — | — |
| I — Interface Segregation (no fat interfaces) | — | — |
| D — Dependency Inversion (depend on abstractions) | — | — |

### Microservice

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Single business capability | — | — |
| Bounded context (no domain bleed) | — | — |
| Independent deploy (no coupled releases) | — | — |
| Resilience patterns (CB / retry / bulkhead) | — | — |


## 17. Integration with Other Folders

### Internal — other folders in this repo

| Folder / Module | Import-count | Purpose |
|---|---|---|
| `app/services` | 16 | _reviewer-described_ |
| `documind_core/exceptions` | 6 | _reviewer-described_ |
| `app/schemas` | 6 | _reviewer-described_ |
| `documind_core/breakers` | 3 | _reviewer-described_ |
| `documind_core/auth` | 3 | _reviewer-described_ |
| `documind_core/circuit_breaker` | 3 | _reviewer-described_ |
| `documind_core/config` | 2 | _reviewer-described_ |
| `documind_core/db_client` | 2 | _reviewer-described_ |
| `mcp` | 2 | _reviewer-described_ |
| `app/workers` | 2 | _reviewer-described_ |
| `documind_core/rebuff_detector` | 2 | _reviewer-described_ |
| `documind_core/logging_config` | 1 | _reviewer-described_ |
| `documind_core/middleware` | 1 | _reviewer-described_ |
| `documind_core/observability` | 1 | _reviewer-described_ |
| `documind_core/rate_limiter` | 1 | _reviewer-described_ |
| `app/core` | 1 | _reviewer-described_ |
| `app/routers` | 1 | _reviewer-described_ |
| `documind_core/audit` | 1 | _reviewer-described_ |
| `documind_core/kafka_client` | 1 | _reviewer-described_ |
| `documind_core/schemas` | 1 | _reviewer-described_ |
| `mcp/client` | 1 | _reviewer-described_ |
| `documind_core/ai_governance` | 1 | _reviewer-described_ |

### External — third-party packages

| Package | Import-count |
|---|---|
| `fastapi` | 4 |
| `httpx` | 4 |
| `prometheus_client` | 4 |
| `prompt_builder` | 4 |
| `best_config_loader` | 3 |
| `guardrails` | 2 |
| `ollama_client` | 2 |
| `retrieval_client` | 2 |
| `opentelemetry` | 2 |
| `langfuse_tracer` | 2 |
| `pytest` | 2 |
| `multi_hop_agent` | 1 |
| `multi_hop_fanout` | 1 |
| `redis` | 1 |
| `importlib` | 1 |
| `best_config_history` | 1 |
| `urllib` | 1 |
| `pydantic` | 1 |
| `prompt_repo` | 1 |
| `rag_inference` | 1 |


## 18. Debugging Guide

### Step-by-step when something breaks

```
1. Tail logs:        tail -50 /tmp/inference-svc.log   (if host-side)
                     docker logs documind-inference-svc --tail=50   (if container)
2. Health probe:     curl http://localhost:<PORT>/health
3. Fleet probe:      python3 scripts/advanced_healthcheck.py --layer app
4. Trace:            Open Jaeger → search request_id → see span tree
5. Metrics:          Open Grafana → service dashboard → look for spike
6. Drill:            ls mcp/tests/drill_*inference-svc*.py and run
```

### Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| 502 / connection refused | service down | check `circuitrag-status.sh` |
| Slow p95 latency | DB N+1 or LLM throttle | Section 8 + Section 15 |
| 5xx spike | downstream dep down | check `/health/upstreams` |
| Memory growth | unbounded cache or closure leak | Section 11 |
| Wrong-tenant data | RLS bypass | tenant isolation drill |


## 19. Production Gates (hard pass/fail)

| Gate | Target | Status | Evidence |
|---|---|---|---|
| Code coverage ≥ 80% | statements + branches | — | — |
| Naming convention enforced | ruff / eslint | — | — |
| Zero critical CVEs | Trivy / Bandit | — | — |
| No hardcoded secrets | gitleaks | — | — |
| No memory leaks | bounded caches | — | smells: 2 |
| No N+1 queries | hot paths reviewed | — | 14 DB call sites |
| All APIs validated | Pydantic / Zod | — | sanitization: Pydantic BaseModel |
| Duplicate logic eliminated | DRY check | — | — |
| Structured logging with correlation_id | — | — | — |
| Distributed tracing wired | OpenTelemetry | — | — |
| For AI: prompt injection tested | Rebuff / Garak | — | AI deps present |
| For AI: hallucination scoring ≥ 0.85 | Ragas faithfulness | — | yes |


## 20. Final Production Readiness Score

| Area | Score (/10) |
|---|---|
| Architecture | — |
| Security | — |
| Performance | — |
| Reliability | — |
| Observability | — |
| Testing | — |
| Scalability | — |
| AI Safety | — |
| DevOps | — |
| Maintainability | — |
| **Total** | **— / 100** |

### Decision

- [ ] **GO** — Production-ready (≥80, no failed gates)
- [ ] **CONDITIONAL GO** — Ship with documented follow-ups (≥60)
- [ ] **NO-GO** — Block release (any critical-red gate, or <60)

### Critical blockers

1. _TBD_

### Follow-ups (post-ship)

| ID | Description | Owner | Due |
|---|---|---|---|
| — | — | — | — |

### Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Tech Lead | — | — | — |
| Security | — | — | — |
| SRE | — | — | — |

---

_Generated by `scripts/generate_folder_report.py`. Re-run after major folder changes:_
_`python3 scripts/generate_folder_report.py --folder <this-folder> --force`_
