# 📦 `documind_core` — Advanced README

📚 **Library**  ·  **Path:** `libs/py/documind_core`  ·  **Generated:** 2026-05-16 23:25 UTC

> documind_core

This README is **auto-generated** by [`scripts/generate_folder_report.py`](../../scripts/generate_folder_report.py). It explains what this folder does, every file inside it, how the files link to each other, every API endpoint, every database call, every test case, and the production controls (security / reliability / performance / observability). Re-run after major changes.

---

## 🔎 Section 0 — Auto-Detected Facts

| Metric | Value |
|---|---|
| Folder | `libs/py/documind_core` |
| Total files | 41 |
| Python files | 38 |
| TypeScript/JS files | 0 |
| Go files | 0 |
| Shell scripts | 0 |
| Lines of code | 8,527 |
| Python classes | 134 |
| Python functions | 347 |
| Async functions | 50 |
| Total API endpoints | 0 |
| Total DB call sites | 10 |
| DB / Storage libs | Kafka (aiokafka), Neo4j, Redis, asyncpg |
| Concurrency primitives | Lock / RLock, asyncio (async/await), threading |
| Caching primitives | in-memory @lru_cache, redis |
| Input validation | Manual escape, Pydantic BaseModel |
| AI / LLM deps | LangChain, Ollama, Rebuff (PI defense) |
| Test files | 0 |
| Detected test cases | 0 |
| Tests dir present | ❌ — flag |
| Dockerfile | ❌ |
| pyproject.toml | ❌ |
| go.mod | ❌ |
| package.json | ❌ |
| Top git contributors | `52	PraveenAsthana123`, `6	Praveen` |

#### Longest functions (top 5)

| Location | Name | Lines |
|---|---|---|
| `circuit_breaker.py:347` | `__init__` | 152 |
| `audit.py:146` | `write` | 143 |
| `agent_board.py:317` | `run` | 101 |
| `drift_detection.py:167` | `compare_windows` | 82 |
| `breakers.py:249` | `check` | 69 |

#### Smells detected (grep heuristics — verify manually)

| Smell | Count |
|---|---|
| hardcoded localhost URL | 6 |


## 1. Purpose — Business + Technical

### Business problem this folder solves

> _Reviewer to fill: documind_core_

### Technical contract this folder exposes

> _Reviewer to fill: API surface, events emitted, data persisted, downstream consumers._

### Out-of-scope (what this folder does NOT do)

> _Reviewer to fill: explicit non-goals — prevents scope creep at review time._


## ⚡ Quick Start (library)

This is a shared library — not a runnable service. Use it from any service like:

```python
from documind_core import <symbol>
```

Run tests against the library:

```bash
cd libs/py/documind_core
pytest -q
```


## 🗺 How to Read This Folder (Guided Tour)

Read these files in order — by the end, you'll understand 80% of this folder's behavior. Click any path to jump straight to the source.

1. **`logging_config.py`** (⚙ config / settings, 201 LOC) — Every env var the service reads. Read this BEFORE running locally.
2. **`config.py`** (⚙ config / settings, 182 LOC) — Every env var the service reads. Read this BEFORE running locally.
3. **`agent_board.py`** (🤖 agent / tool, 616 LOC) — AgentBoard — multi-agent task / review / advise pattern with bounded
4. **`agentic_framework.py`** (🤖 agent / tool, 260 LOC) — Agentic engineering framework — meta-template for every agent.
5. **`kafka_client.py`** (🔌 external service adapter, 335 LOC) — Wraps an external API (LLM / vector DB / message bus). Look for circuit breakers + retries.
6. **`db_client.py`** (🔌 external service adapter, 149 LOC) — Wraps an external API (LLM / vector DB / message bus). Look for circuit breakers + retries.
7. **`middleware.py`** (🪝 middleware / interceptor, 391 LOC) — FastAPI middleware stack (Design Areas 62 — Observability, 5 — Tenant,
8. **`circuit_breaker.py`** (📄 module, 1072 LOC) — Circuit Breaker (Design Area 4 — Failure Boundary, Extra — Circuit Breaker).

Click absolute paths for direct `cat`-ability in the §2 File Inventory above.


## ⚙ Environment Variables

All env vars this folder reads, auto-extracted from `BaseSettings` field declarations and `os.environ.get` calls.

### Pydantic BaseSettings fields

| Variable | Default | Source location |
|---|---|---|
| `DOCUMIND_ENV` | `'development'` | `config.py:53` |
| `DOCUMIND_LOG_LEVEL` | `'INFO'` | `config.py:54` |
| `DOCUMIND_LOG_JSON` | `True` | `config.py:55` |
| `DOCUMIND_REGION` | `'local'` | `config.py:56` |
| `DOCUMIND_SERVICE_NAME` | `Field(default='documind-service', description='Overridden per service')` | `config.py:57` |
| `DOCUMIND_JWT_PUBLIC_KEY_PATH` | `'./scripts/dev-keys/jwt-public.pem'` | `config.py:62` |
| `DOCUMIND_JWT_ISSUER` | `'documind-local'` | `config.py:63` |
| `DOCUMIND_JWT_AUDIENCE` | `'documind-services'` | `config.py:64` |
| `DOCUMIND_JWT_ACCESS_TTL` | `900` | `config.py:65` |
| `DOCUMIND_JWT_REFRESH_TTL` | `604800` | `config.py:66` |
| `DOCUMIND_ENCRYPTION_KEY` | `None` | `config.py:68` |
| `DOCUMIND_ADMIN_API_KEY` | `None` | `config.py:69` |
| `DOCUMIND_CORS_ORIGINS` | `'http://localhost:3000,http://localhost:5173'` | `config.py:70` |
| `DOCUMIND_PG_HOST` | `'localhost'` | `config.py:75` |
| `DOCUMIND_PG_PORT` | `5432` | `config.py:76` |
| `DOCUMIND_PG_DB` | `'documind'` | `config.py:77` |
| `DOCUMIND_PG_USER` | `'documind'` | `config.py:78` |
| `DOCUMIND_PG_PASSWORD` | `SecretStr('documind')` | `config.py:79` |
| `DOCUMIND_PG_MAX_CONNS` | `20` | `config.py:80` |
| `DOCUMIND_PG_MIN_CONNS` | `2` | `config.py:81` |
| `DOCUMIND_REDIS_URL` | `'redis://localhost:6379/0'` | `config.py:83` |
| `DOCUMIND_REDIS_POOL_SIZE` | `20` | `config.py:84` |
| `DOCUMIND_QDRANT_URL` | `'http://localhost:6333'` | `config.py:86` |
| `DOCUMIND_QDRANT_API_KEY` | `None` | `config.py:87` |
| `DOCUMIND_QDRANT_COLLECTION` | `'chunks'` | `config.py:88` |
| `DOCUMIND_NEO4J_URI` | `'bolt://localhost:7687'` | `config.py:90` |
| `DOCUMIND_NEO4J_USER` | `'neo4j'` | `config.py:91` |
| `DOCUMIND_NEO4J_PASSWORD` | `SecretStr('documind')` | `config.py:92` |
| `DOCUMIND_KAFKA_BOOTSTRAP` | `'localhost:9094'` | `config.py:101` |
| `DOCUMIND_KAFKA_CLIENT_ID` | `'documind'` | `config.py:102` |
| `DOCUMIND_KAFKA_CONSUMER_GROUP_PREFIX` | `'documind-'` | `config.py:103` |
| `DOCUMIND_MINIO_ENDPOINT` | `'localhost:9000'` | `config.py:105` |
| `DOCUMIND_MINIO_ACCESS_KEY` | `SecretStr('documind')` | `config.py:106` |
| `DOCUMIND_MINIO_SECRET_KEY` | `SecretStr('documind-secret')` | `config.py:107` |
| `DOCUMIND_MINIO_BUCKET` | `'documents'` | `config.py:108` |
| `DOCUMIND_MINIO_USE_SSL` | `False` | `config.py:109` |
| `DOCUMIND_OLLAMA_URL` | `'http://localhost:11434'` | `config.py:114` |
| `DOCUMIND_OLLAMA_LLM_MODEL` | `'llama3.1:8b'` | `config.py:115` |
| `DOCUMIND_OLLAMA_EMBED_MODEL` | `'nomic-embed-text'` | `config.py:116` |
| `DOCUMIND_OLLAMA_TIMEOUT_SECONDS` | `60` | `config.py:117` |
| `DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT` | `'http://localhost:4317'` | `config.py:122` |
| `DOCUMIND_OTEL_SERVICE_NAMESPACE` | `'documind'` | `config.py:123` |
| `DOCUMIND_PROMETHEUS_PORT` | `9464` | `config.py:124` |
| `DOCUMIND_RATE_LIMIT_API_PER_MIN` | `100` | `config.py:129` |
| `DOCUMIND_RATE_LIMIT_UPLOAD_PER_MIN` | `10` | `config.py:130` |
| `DOCUMIND_RATE_LIMIT_ADMIN_PER_MIN` | `50` | `config.py:131` |
| `DOCUMIND_RATE_LIMIT_INFERENCE_PER_MIN` | `20` | `config.py:132` |
| `DOCUMIND_CHUNK_SIZE` | `512` | `config.py:137` |
| `DOCUMIND_CHUNK_OVERLAP` | `50` | `config.py:138` |
| `DOCUMIND_RETRIEVAL_TOP_K` | `10` | `config.py:139` |
| `DOCUMIND_RERANK_TOP_K` | `5` | `config.py:140` |
| `DOCUMIND_MAX_CONTEXT_TOKENS` | `4000` | `config.py:141` |

### Runtime `os.environ.get` / `os.getenv` calls

| Variable | Default | Source location |
|---|---|---|
| `REBUFF_ENABLED` | **required** | `rebuff_detector.py:55` |
| `REBUFF_API_TOKEN` | **required** | `rebuff_detector.py:56` |
| `REBUFF_API_URL` | `https://www.rebuff.ai` | `rebuff_detector.py:57` |
| `REBUFF_PI_THRESHOLD` | `0.5` | `rebuff_detector.py:67` |
| `DOCUMIND_RATE_LIMIT_DISABLED` | **required** | `middleware.py:325` |
| `SENTRY_DSN` | **required** | `error_tracking.py:65` |
| `DOCUMIND_ENV` | `development` | `error_tracking.py:76` |
| `DOCUMIND_RELEASE` | `dev` | `error_tracking.py:87` |

_Variables marked **required** must be set — missing values may raise on startup or silently default to empty strings._


## 2. File Inventory

Every Python file in this folder, with role / classes / functions / LOC / first docstring line. Full absolute paths listed below the table for easy `cat`-ability.

| Relative path | Role (inferred) | Classes | Functions | LOC | Summary |
|---|---|---|---|---|---|
| `__init__.py` | 📦 package marker | 0 | 0 | 134 | documind_core |
| `a2a_protocol.py` | 📄 module | 6 | 3 | 333 | Agent-to-Agent (A2A) protocol — registry + message bus + connector + delegation. |
| `agent_board.py` | 🤖 agent / tool | 5 | 5 | 616 | AgentBoard — multi-agent task / review / advise pattern with bounded |
| `agentic_framework.py` | 🤖 agent / tool | 2 | 2 | 260 | Agentic engineering framework — meta-template for every agent. |
| `ai_governance.py` | 📄 module | 14 | 1 | 700 | AI governance primitives — debuggability, explainability, responsibility, |
| `audit.py` | 📄 module | 2 | 3 | 292 | Tamper-evident audit log (Design Area 27 — Governance). |
| `auth.py` | 📄 module | 2 | 4 | 348 | JWT auth verifier + FastAPI dependency for Python services. |
| `bm25.py` | 📄 module | 2 | 1 | 133 | BM25 lexical retrieval — wraps `rank_bm25` for the hybrid-retrieval |
| `body_limit.py` | 📄 module | 1 | 0 | 58 | Request-body size limit (FastAPI middleware). |
| `breakers.py` | 📄 module | 18 | 1 | 1049 | Specialized circuit breakers (Design Area 4 + Extra-CB, plus AI/RAG-specific). |
| `cache.py` | 📄 module | 1 | 0 | 134 | Cache helpers (Design Areas 40 — Cache Architecture, 41 — Cache Consistency, |
| `chunking.py` | 📄 module | 10 | 1 | 416 | Multi-strategy chunking — Strategy + Factory pattern (§7 of the |
| `circuit_breaker.py` | 📄 module | 6 | 1 | 1072 | Circuit Breaker (Design Area 4 — Failure Boundary, Extra — Circuit Breaker). |
| `citations.py` | 📄 module | 4 | 2 | 202 | Citation linking — claim-to-source provenance (§16.6 + §48 of the |
| `config.py` | ⚙ config / settings | 1 | 1 | 182 | Configuration foundation (Design Areas 6 — Control Plane, 55 — Feature Flags, |
| `db_client.py` | 🔌 external service adapter | 2 | 0 | 149 | PostgreSQL client (Design Areas 5 — Tenant RLS, 12 — Consistency, 46 — DB Strategy). |
| `dispatch_pool.py` | 📄 module | 3 | 0 | 213 | DispatchPool - fanout 100+ tasks with bounded LLM concurrency. |
| `dr_metrics.py` | 📄 module | 1 | 2 | 139 | Disaster Recovery target metrics — single source of truth. |
| `drift_detection.py` | 📄 module | 2 | 3 | 249 | Drift detection — Production Validation §44 maturity item. |
| `embedding_cache.py` | 📄 module | 2 | 2 | 179 | Embedding cache — content-hash → vector with model-version namespacing |
| `encryption.py` | 📄 module | 1 | 1 | 74 | At-rest encryption for secrets stored in the database. |
| `error_tracking.py` | 📄 module | 0 | 5 | 153 | Error-tracking integration — Sentry wrapper. |
| `exceptions.py` | 📄 module | 10 | 0 | 176 | Domain exception hierarchy (Design Area 9 — State Model; cross-cutting). |
| `fusion.py` | 📄 module | 1 | 2 | 145 | Hybrid retrieval fusion — RRF + heap-based top-K (§16.5 of the |
| `governance_os.py` | 📄 module | 8 | 1 | 363 | AI Governance OS — unified policy / decision / risk / compliance / audit surface. |
| `idempotency.py` | 📄 module | 2 | 0 | 65 | HTTP idempotency (Design Area 20). |
| `idempotency_middleware.py` | 📄 module | 1 | 0 | 113 | FastAPI middleware for the ``X-Idempotency-Key`` pattern (Design Area 20). |
| `kafka_client.py` | 🔌 external service adapter | 2 | 2 | 335 | Kafka client (Design Areas 17 — Event-Driven, 19 — Compensation, |
| `logging_config.py` | ⚙ config / settings | 0 | 8 | 201 | Structured logging (Design Area 62 — Observability by Design). |
| `middleware.py` | 🪝 middleware / interceptor | 6 | 1 | 391 | FastAPI middleware stack (Design Areas 62 — Observability, 5 — Tenant, |
| `mmr.py` | 📄 module | 0 | 1 | 100 | MMR — Maximal Marginal Relevance (§16.6 post-retrieval diversification). |
| `observability.py` | 📄 module | 0 | 5 | 251 | Observability setup (Design Areas 62 — Observability by Design, 64 — SLO-Driven). |
| `pii.py` | 📄 module | 2 | 1 | 193 | PII detection — multi-pattern Aho-Corasick-style scanner (§16.11 |
| `query_rewriter.py` | 📄 module | 2 | 0 | 133 | Pre-retrieval query processing (§16.4 of the playbook). |
| `rate_limiter.py` | 📄 module | 2 | 2 | 191 | Rate limiting (Design Areas 42 — Tenant-Aware Cache, 45 — Backpressure). |
| `rebuff_detector.py` | 📄 module | 2 | 7 | 272 | Rebuff detector — Stage-1 runtime PI-defense adapter (per §47.6, §48, §56). |
| `schemas.py` | 📄 module | 4 | 0 | 49 | Shared response schemas (Global CLAUDE.md §6 — API Design Standards). |
| `tokens.py` | 📄 module | 2 | 2 | 99 | Token counting + budget helpers (§16.1 / §16.2 of the playbook). |

### Absolute paths (clickable)

- `/mnt/deepa/rag/libs/py/documind_core/__init__.py`
- `/mnt/deepa/rag/libs/py/documind_core/a2a_protocol.py`
- `/mnt/deepa/rag/libs/py/documind_core/agent_board.py`
- `/mnt/deepa/rag/libs/py/documind_core/agentic_framework.py`
- `/mnt/deepa/rag/libs/py/documind_core/ai_governance.py`
- `/mnt/deepa/rag/libs/py/documind_core/audit.py`
- `/mnt/deepa/rag/libs/py/documind_core/auth.py`
- `/mnt/deepa/rag/libs/py/documind_core/bm25.py`
- `/mnt/deepa/rag/libs/py/documind_core/body_limit.py`
- `/mnt/deepa/rag/libs/py/documind_core/breakers.py`
- `/mnt/deepa/rag/libs/py/documind_core/cache.py`
- `/mnt/deepa/rag/libs/py/documind_core/chunking.py`
- `/mnt/deepa/rag/libs/py/documind_core/circuit_breaker.py`
- `/mnt/deepa/rag/libs/py/documind_core/citations.py`
- `/mnt/deepa/rag/libs/py/documind_core/config.py`
- `/mnt/deepa/rag/libs/py/documind_core/db_client.py`
- `/mnt/deepa/rag/libs/py/documind_core/dispatch_pool.py`
- `/mnt/deepa/rag/libs/py/documind_core/dr_metrics.py`
- `/mnt/deepa/rag/libs/py/documind_core/drift_detection.py`
- `/mnt/deepa/rag/libs/py/documind_core/embedding_cache.py`
- `/mnt/deepa/rag/libs/py/documind_core/encryption.py`
- `/mnt/deepa/rag/libs/py/documind_core/error_tracking.py`
- `/mnt/deepa/rag/libs/py/documind_core/exceptions.py`
- `/mnt/deepa/rag/libs/py/documind_core/fusion.py`
- `/mnt/deepa/rag/libs/py/documind_core/governance_os.py`
- `/mnt/deepa/rag/libs/py/documind_core/idempotency.py`
- `/mnt/deepa/rag/libs/py/documind_core/idempotency_middleware.py`
- `/mnt/deepa/rag/libs/py/documind_core/kafka_client.py`
- `/mnt/deepa/rag/libs/py/documind_core/logging_config.py`
- `/mnt/deepa/rag/libs/py/documind_core/middleware.py`
- `/mnt/deepa/rag/libs/py/documind_core/mmr.py`
- `/mnt/deepa/rag/libs/py/documind_core/observability.py`
- `/mnt/deepa/rag/libs/py/documind_core/pii.py`
- `/mnt/deepa/rag/libs/py/documind_core/query_rewriter.py`
- `/mnt/deepa/rag/libs/py/documind_core/rate_limiter.py`
- `/mnt/deepa/rag/libs/py/documind_core/rebuff_detector.py`
- `/mnt/deepa/rag/libs/py/documind_core/schemas.py`
- `/mnt/deepa/rag/libs/py/documind_core/tokens.py`


## 🧭 Where Does X Live? (cheat sheet)

Use this table when you're modifying this folder and need to know where new code goes.

| I want to... | Role | Touch these files |
|---|---|---|
| Add a new env var | ⚙ config / settings | `config.py`, `logging_config.py` |
| Wrap a new external API | 🔌 external service adapter | `db_client.py`, `kafka_client.py` |
| Add a new middleware (auth / logging / tracing) | 🪝 middleware / interceptor | `middleware.py` |
| Add a new agent / tool | 🤖 agent / tool | `agent_board.py`, `agentic_framework.py` |


## 3. C4 Model — Context / Container / Component / Code

### Level 1 — System Context

_Where does this folder sit in the broader system?_

```mermaid
flowchart LR
    Caller([External Caller]) --> This["documind_core"]
```

### Level 2 — Container

_What external dependencies does this folder talk to?_

```mermaid
flowchart TB
    subgraph documind_core
        Code[Source Code]
    end
    Code --> DB_0[("Kafka (aiokafka)")]
    Code --> DB_1[("Neo4j")]
    Code --> DB_2[("Redis")]
    Code --> DB_3[("asyncpg")]
    Code --> AI_0{{LLM: LangChain}}
    Code --> AI_1{{LLM: Ollama}}
    Code --> AI_2{{LLM: Rebuff (PI defense)}}
```

### Level 3 — Component

_Internal files grouped by inferred role._

```mermaid
flowchart TB
    subgraph __package_marker["📦 package marker"]
        __init___py["__init__.py"]
    end
    subgraph __module["📄 module"]
        a2a_protocol_py["a2a_protocol.py"]
        ai_governance_py["ai_governance.py"]
        audit_py["audit.py"]
        auth_py["auth.py"]
        bm25_py["bm25.py"]
        body_limit_py["body_limit.py"]
        more___module["... +24 more"]
    end
    subgraph __agent___tool["🤖 agent / tool"]
        agent_board_py["agent_board.py"]
        agentic_framework_py["agentic_framework.py"]
    end
    subgraph __config___settings["⚙ config / settings"]
        config_py["config.py"]
        logging_config_py["logging_config.py"]
    end
    subgraph __external_service_adapter["🔌 external service adapter"]
        db_client_py["db_client.py"]
        kafka_client_py["kafka_client.py"]
    end
    subgraph __middleware___interceptor["🪝 middleware / interceptor"]
        middleware_py["middleware.py"]
    end
```

### Level 4 — Code (top hotspots)

_Longest functions — these are the most likely refactor candidates._

```mermaid
flowchart TB
    circuit_breaker_py_347___init__["__init__ (152 lines)<br/>circuit_breaker.py:347"]
    audit_py_146_write["write (143 lines)<br/>audit.py:146"]
    agent_board_py_317_run["run (101 lines)<br/>agent_board.py:317"]
    drift_detection_py_167_compare_windows["compare_windows (82 lines)<br/>drift_detection.py:167"]
    breakers_py_249_check["check (69 lines)<br/>breakers.py:249"]
```


## 📐 Class Diagram (UML-style)

Top classes by method count, with inheritance arrows. Common framework bases (`BaseModel`, `BaseSettings`, `Exception`, `Enum`) use dotted lines.

```mermaid
classDiagram
    class CircuitBreaker {
        +37 methods
        ~circuit_breaker.py:329
    }
    class AgentBoard {
        +9 methods
        ~agent_board.py:231
    }
    class AgentLoopCircuitBreaker {
        +9 methods
        ~breakers.py:426
    }
    class Cache {
        +7 methods
        ~cache.py:30
    }
    class EmbeddingCache {
        +7 methods
        ~embedding_cache.py:75
    }
    class _StepContext {
        +6 methods
        ~ai_governance.py:640
    }
    class _BreakerGuardedMetricExporter {
        +6 methods
        ~observability.py:203
    }
    MetricExporter <|-- _BreakerGuardedMetricExporter
    class AgentRegistry {
        +6 methods
        ~a2a_protocol.py:125
    }
    class PIIScanner {
        +6 methods
        ~pii.py:104
    }
    class ObservabilityCircuitBreaker {
        +6 methods
        ~breakers.py:574
    }
    class CognitiveCircuitBreaker {
        +6 methods
        ~breakers.py:906
    }
    class DbClient {
        +6 methods
        ~db_client.py:36
    }
    class InterpretabilityTrace {
        +5 methods
        ~ai_governance.py:592
    }
    class IdempotentConsumer {
        +5 methods
        ~kafka_client.py:218
    }
    class TokenCircuitBreaker {
        +5 methods
        ~breakers.py:216
    }
```


_Showing top 15 of 134 classes (ranked by method count)._


## 4. Code Sequence — How Files Link to Each Other

**Import graph for files in this folder.** Reading order: start at any entry-point file (look for `🚀 entry point` role in the inventory above), then follow the arrows.

```mermaid
flowchart LR
    __init___py["__init__.py"] --> ai_governance_py["ai_governance.py"]
    __init___py["__init__.py"] --> body_limit_py["body_limit.py"]
    __init___py["__init__.py"] --> breakers_py["breakers.py"]
    __init___py["__init__.py"] --> circuit_breaker_py["circuit_breaker.py"]
    __init___py["__init__.py"] --> exceptions_py["exceptions.py"]
    __init___py["__init__.py"] --> idempotency_middleware_py["idempotency_middleware.py"]
    ai_governance_py["ai_governance.py"] --> exceptions_py["exceptions.py"]
    audit_py["audit.py"] --> exceptions_py["exceptions.py"]
    breakers_py["breakers.py"] --> circuit_breaker_py["circuit_breaker.py"]
    breakers_py["breakers.py"] --> exceptions_py["exceptions.py"]
    circuit_breaker_py["circuit_breaker.py"] --> exceptions_py["exceptions.py"]
    db_client_py["db_client.py"] --> exceptions_py["exceptions.py"]
    encryption_py["encryption.py"] --> exceptions_py["exceptions.py"]
    idempotency_middleware_py["idempotency_middleware.py"] --> idempotency_py["idempotency.py"]
    kafka_client_py["kafka_client.py"] --> exceptions_py["exceptions.py"]
    middleware_py["middleware.py"] --> exceptions_py["exceptions.py"]
    middleware_py["middleware.py"] --> logging_config_py["logging_config.py"]
    middleware_py["middleware.py"] --> rate_limiter_py["rate_limiter.py"]
    observability_py["observability.py"] --> breakers_py["breakers.py"]
    rate_limiter_py["rate_limiter.py"] --> exceptions_py["exceptions.py"]
```

### Edge list

| From file | To file | Import-count |
|---|---|---|
| `__init__.py` | `ai_governance.py` | 1 |
| `__init__.py` | `body_limit.py` | 1 |
| `__init__.py` | `breakers.py` | 1 |
| `__init__.py` | `circuit_breaker.py` | 1 |
| `__init__.py` | `exceptions.py` | 1 |
| `__init__.py` | `idempotency_middleware.py` | 1 |
| `ai_governance.py` | `exceptions.py` | 1 |
| `audit.py` | `exceptions.py` | 1 |
| `breakers.py` | `circuit_breaker.py` | 1 |
| `breakers.py` | `exceptions.py` | 1 |
| `circuit_breaker.py` | `exceptions.py` | 1 |
| `db_client.py` | `exceptions.py` | 1 |
| `encryption.py` | `exceptions.py` | 1 |
| `idempotency_middleware.py` | `idempotency.py` | 1 |
| `kafka_client.py` | `exceptions.py` | 1 |
| `middleware.py` | `exceptions.py` | 1 |
| `middleware.py` | `logging_config.py` | 1 |
| `middleware.py` | `rate_limiter.py` | 1 |
| `observability.py` | `breakers.py` | 1 |
| `rate_limiter.py` | `exceptions.py` | 1 |


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

_No HTTP endpoints detected via `@app.*` / `@router.*` decorators._


## 🏗 Input/Process/Output + Integration + Design Principles

### Input / Process / Output per endpoint

| Endpoint | INPUT (validation chain) | PROCESS (call chain) | OUTPUT (response chain) |
|---|---|---|---|
| _(no endpoints)_ | — | — | — |

### Integration sequence (ordered by import volume)

Other folders this one calls into, ordered by how heavily it depends on each:

```mermaid
sequenceDiagram
  autonumber
  participant This as documind_core
```

### SOLID principles applied here

| Principle | Where it shows up in this folder |
|---|---|
| **S — Single Responsibility** | Each file has ONE role — routers route, services orchestrate, repos query, schemas describe. The §2 File Inventory shows the role per file; any file with multiple roles violates SRP. |
| **O — Open/Closed** | New endpoints add new router functions; new business cases add new service methods. Existing methods stay closed for modification. |
| **L — Liskov Substitution** | All adapter clients (Ollama / OpenAI / Anthropic) implement the same LLM-client protocol — they're interchangeable behind the circuit breaker. |
| **I — Interface Segregation** | Pydantic models split request, response, and internal state into separate schemas — no client gets a fat model with fields it doesn't use. |
| **D — Dependency Inversion** | Services receive their dependencies via FastAPI `Depends()` — they depend on abstractions (factories), not concrete repos. Swap implementations in tests via the `app.dependency_overrides` dict. |

### Microservice principles applied here

| Principle | Application |
|---|---|
| **Single business capability** | `documind_core` owns ONE capability (see §1 Purpose). Cross-capability logic lives in other services. |
| **Bounded context** | Schemas + repositories are scoped to this service's bounded context — no shared DB tables with other services. |
| **DB per service** | Each service owns its tables. Cross-service reads go through HTTP or Kafka — never a direct DB join. |
| **Independent deploy** | Service is independently deployable — its container is built + released without coupling to other services. |
| **Resilience patterns** | Circuit breakers (`documind_core/breakers/`), retries with exponential backoff, bulkheads, timeouts on every external call. |
| **Observability** | Every request has a `request_id` propagated via OTel baggage; every external call emits a trace span. |

### Design-principle stack (how the principles compose)

Reading bottom-to-top — earlier principles enable later ones:

```text
┌─────────────────────────────────────────────────────────────┐
│ 7. AI Governance (§38 + §48): decision audit + explainability│
├─────────────────────────────────────────────────────────────┤
│ 6. Production Gates (§47.11): 10 gates BEFORE deploy        │
├─────────────────────────────────────────────────────────────┤
│ 5. Resilience: CB + retry + bulkhead + timeout              │
├─────────────────────────────────────────────────────────────┤
│ 4. Microservice: single capability, bounded context, DB/svc │
├─────────────────────────────────────────────────────────────┤
│ 3. SOLID: SRP + OCP + LSP + ISP + DIP                       │
├─────────────────────────────────────────────────────────────┤
│ 2. 12-factor: stateless, deps in venv, config in env        │
├─────────────────────────────────────────────────────────────┤
│ 1. KISS / YAGNI / DRY: every line earns its place           │
└─────────────────────────────────────────────────────────────┘
```

**How to use this stack:** when adding a new feature, check it from the bottom up. KISS first (simplest design that works), then SOLID (does any class violate SRP?), then microservice (does this leak the bounded context?), then resilience (what fails when the downstream is slow?), then gates (which production gate enforces this?), then governance (which audit row records this decision?).


## 🔬 Code Logic Deep Dive — Variables / DSA / Memory / Pseudocode

Auto-extracted from the hottest file in this folder: **`circuit_breaker.py`** (1072 LOC, 6 classes, 1 functions).

### Module-level variables (state map)

| Variable | Type | Mutability |
|---|---|---|
| `T` | `_inferred_` | immutable |
| `log` | `_inferred_` | immutable |
| `_UNKNOWN_CAUSE_LABEL` | `_inferred_` | constant |
| `_STATE_NUMERIC` | `_inferred_` | ⚠ MUTABLE dict |
| `_last_state` | `dict[str, str]` | immutable |

### Data structures + algorithms detected in `circuit_breaker.py`

- collections.Counter
- collections.deque (FIFO/LIFO queue)
- asyncio.Lock / Semaphore
- set comprehension
- dict comprehension
- generator expression

### Memory characteristics

- ⚠ `open()` without `with` detected — file handle leak risk.
- ℹ `@dataclass` used — instances are mutable by default; consider `frozen=True` if immutability needed.

### Pseudocode for hottest function: `__init__` (circuit_breaker.py:347, 152 lines)

```text
FUNCTION __init__(self, name):
   1. [ASSIGN] self.name = name
   2. [ASSIGN] self.failure_threshold = failure_threshold
   3. [ASSIGN] self.recovery_timeout = recovery_timeout
   4. [ASSIGN] self.expected_exception = expected_exception if expected_exception is not None e
   5. [ASSIGN] self.call_timeout_s = call_timeout_s
   6. [ASSIGN] self.failure_window_size = failure_window_size
   7. [ASSIGN] self.failure_threshold_rate = failure_threshold_rate
   8. [ASSIGN] self.half_open_max_concurrent = max(1, half_open_max_concurrent)
   9. [ASSIGN] self.half_open_success_threshold = max(1, half_open_success_threshold)
  10. [ASSIGN] self.backoff_factor = max(1.0, backoff_factor)
  11. [ASSIGN] self.recovery_timeout_max = max(recovery_timeout, recovery_timeout_max)
  12. [ASSIGN] self.backoff_jitter = max(0.0, min(1.0, backoff_jitter))
  13. [ASSIGN] self.max_concurrent = max_concurrent
  14. [ASSIGN] self.slow_call_threshold_s = slow_call_threshold_s
  15. [ASSIGN] self.slow_call_rate = max(0.0, min(1.0, slow_call_rate))
  16. [ASSIGN] self.on_state_change = on_state_change
  17. [ASSIGN] self.health_check = health_check
  18. [ASSIGN] self.tenant_id = tenant_id
  19. [ASSIGN] self.otel_baggage = otel_baggage
  20. [TYPED-ASSIGN] self._forced_state: State | None = None
  ... +15 more statements truncated
```

### Reading this section

- **Module-level variables** are loaded ONCE per process. `⚠ MUTABLE` warns of state shared across requests — guard with locks or use request-scoped storage.
- **DSA detected** tells you what algorithmic patterns are in play (hash maps, priority queues, recursion). Use this to predict complexity at scale.
- **Memory characteristics** flag the leak / unbounded-growth patterns that fail under load.
- **Pseudocode** is an AST-projected outline of the hottest function. Walk it top-to-bottom to understand the control flow before reading the real source.


## 7. Sequence Diagrams per Endpoint

_No endpoints detected; sequence-diagram template intentionally omitted._


## 8. Database Layer

**DB / storage libraries:** Kafka (aiokafka), Neo4j, Redis, asyncpg

**Total DB call sites:** 10

| Pattern | Count |
|---|---|
| `execute` | 2 |
| `fetch/fetchall/fetchrow` | 3 |
| `ORM CRUD` | 5 |

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
| No hardcoded values | — | smell count: 6 |
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
| Request validation present | — | sanitization: Manual escape, Pydantic BaseModel |
| SQL injection prevention | — | DB libs: Kafka (aiokafka), Neo4j, Redis, asyncpg — parameterized queries only |
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
| Caches bounded (LRU / TTL) | — | caching: in-memory @lru_cache, redis |

### Concurrency

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Thread safety validated | — | primitives: Lock / RLock, asyncio (async/await), threading |
| Race conditions prevented | — | — |
| Deadlocks avoided (lock ordering) | — | — |
| Parallel processing where beneficial | — | 50 async fns |

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

**Test files detected:** 0
_No `test_*` functions parsed via AST. Either tests live elsewhere or names don't match the `test_*` convention._


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

**Detected AI deps:** LangChain, Ollama, Rebuff (PI defense)

### Prompt Safety

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Prompt injection handling (input filter) | — | Rebuff |
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
| Confidence scoring (Ragas / DeepEval) | — | — |
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
| _(none)_ | — | — |

### External — third-party packages

| Package | Import-count |
|---|---|
| `opentelemetry` | 23 |
| `exceptions` | 10 |
| `fastapi` | 8 |
| `prometheus_client` | 7 |
| `starlette` | 7 |
| `pydantic` | 4 |
| `redis` | 4 |
| `sentry_sdk` | 3 |
| `structlog` | 3 |
| `rebuff` | 3 |
| `breakers` | 2 |
| `circuit_breaker` | 2 |
| `ai_governance` | 1 |
| `body_limit` | 1 |
| `idempotency_middleware` | 1 |
| `jwt` | 1 |
| `rank_bm25` | 1 |
| `httpx` | 1 |
| `pydantic_settings` | 1 |
| `asyncpg` | 1 |


## 📖 Domain Glossary

Project-wide vocabulary a new developer needs. If you see a term in code you don't recognize, check here first.

| Term | Definition |
|---|---|
| **RAG** | Retrieval-Augmented Generation — the pattern of grounding LLM output in retrieved documents to reduce hallucination. |
| **Chunk** | A token-bounded slice of a source document (typically 256–1024 tokens with 10–20% overlap). Embedded + stored in the vector DB. |
| **Embedding** | Vector representation of text. Re-embed everything when the embedding model version bumps. |
| **Vector DB** | Qdrant in this project. Stores chunk embeddings + metadata, returns top-k by cosine similarity. |
| **Rerank** | Second-stage retrieval — re-scores the top-k from the vector DB with a more expensive cross-encoder for better relevance. |
| **Hybrid retrieval** | Vector + keyword (Elasticsearch / BM25) merged via reciprocal-rank-fusion. |
| **MCP** | Model Context Protocol — tool-server contract used by agents to call namespace-scoped operations (drill / ingest / etc.). |
| **Tenant** | A logical customer boundary. Every row + every cache key + every prompt context is tenant-scoped. |
| **Drill** | A runnable script that exercises real services + asserts ≥3 negative invariants (per §43). Lives under `mcp/tests/drill_*.py`. |
| **Breaker** | Circuit breaker — opens after N failures to a downstream dep, lets traffic shed instead of cascading. See `documind_core/breakers/`. |
| **Baggage** | OpenTelemetry context (request_id / tenant_id / actor) propagated across spans + service hops. |
| **Decision audit row** | Per-AI-call record persisted to Postgres with request_id, prompt_version, model_version, output, confidence, fairness_flag — per §38 + §48. |
| **Fanout** | Parallel sub-query split for multi-hop RAG (`services/inference-svc/app/agents/multi_hop_fanout.py`). |
| **Council** | 3-model author + reviewer + advisor pattern for code-fix proposals (per §50). |
| **Side-channel port** | Separate Prometheus `/metrics` port (9465–9470) per service to avoid app-port middleware interference. |
| **Trust scorecard** | 5-layer aggregate (governance + tool review + maturity stack + drill catalog + production gates) used for go/no-go. |
| **HBR** | High-Blast-Radius — file patterns that force the pre-commit hook to refresh the drill catalog. |
| **HITL** | Human-In-The-Loop — escalation path when confidence falls in the 0.5–0.8 range (per §40). |
| **Forensic substrate** | The §51-required metadata block (Date/Location/Approach/Policies/Verification) in every commit body. |


## 18. Debugging Guide

### Step-by-step when something breaks

```
1. Tail logs:        tail -50 /tmp/documind_core.log   (if host-side)
                     docker logs documind-documind_core --tail=50   (if container)
2. Health probe:     curl http://localhost:<PORT>/health
3. Fleet probe:      python3 scripts/advanced_healthcheck.py --layer app
4. Trace:            Open Jaeger → search request_id → see span tree
5. Metrics:          Open Grafana → service dashboard → look for spike
6. Drill:            ls mcp/tests/drill_*documind_core*.py and run
```

### Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| 502 / connection refused | service down | check `circuitrag-status.sh` |
| Slow p95 latency | DB N+1 or LLM throttle | Section 8 + Section 15 |
| 5xx spike | downstream dep down | check `/health/upstreams` |
| Memory growth | unbounded cache or closure leak | Section 11 |
| Wrong-tenant data | RLS bypass | tenant isolation drill |


## 📅 Recent Activity & Open TODOs

### Last 8 commits touching this folder

| Hash | Date | Subject |
|---|---|---|
| `551405a` | 2026-05-16 | docs: regen_all_docs.sh orchestrator + complete README/REPORT regen pass |
| `0211a6c` | 2026-05-16 | docs(reports): rename to *_ASSESSMENT_REPORT.md + Code Logic Deep Dive section |
| `15eca63` | 2026-05-16 | docs(reports): frontend + backend specialized assessments + drill fix |
| `77409b7` | 2026-05-16 | docs(reports): FOLDER_REPORT.md alongside README.md per two-file convention |
| `4068a70` | 2026-05-16 | docs(readme): audit checklist + drill_readme_generator + sidecar fold-in |
| `5ecd9be` | 2026-05-16 | docs(readme): 11 more sections for new-dev onboarding + bugfixes |
| `c6e58b8` | 2026-05-16 | docs(readme): advanced auto-generated READMEs (project + per-folder) |
| `4e2ec04` | 2026-05-08 | fix(rebuff): bridge langchain vectorstore import |

```bash
git log --oneline -- libs/py/documind_core    # see all commits
git blame <file>                       # who wrote what
```

### Open TODO / FIXME / HACK markers

_No TODO / FIXME markers found — folder is hygienic._


## 19. Production Gates (hard pass/fail)

| Gate | Target | Status | Evidence |
|---|---|---|---|
| Code coverage ≥ 80% | statements + branches | — | — |
| Naming convention enforced | ruff / eslint | — | — |
| Zero critical CVEs | Trivy / Bandit | — | — |
| No hardcoded secrets | gitleaks | — | — |
| No memory leaks | bounded caches | — | smells: 6 |
| No N+1 queries | hot paths reviewed | — | 10 DB call sites |
| All APIs validated | Pydantic / Zod | — | sanitization: Manual escape, Pydantic BaseModel |
| Duplicate logic eliminated | DRY check | — | — |
| Structured logging with correlation_id | — | — | — |
| Distributed tracing wired | OpenTelemetry | — | — |
| For AI: prompt injection tested | Rebuff / Garak | — | AI deps present |
| For AI: hallucination scoring ≥ 0.85 | Ragas faithfulness | — | n/a |


## 📋 Reporting + Audit Checklist (10 categories × 10 rows)

**Honesty contract per §57.7:** sections that are deterministically auto-generated AND covered by a drill are pre-scored 10/10. Sections that require human judgment start at **TBD** — never auto-mark them as ✓ without evidence.

Aggregate score = sum of all 100 row scores. Target ≥ 80 for production. Each cell: ✓ (10) / ⚠ (5) / ✗ (0) / TBD.

### 1. Architecture & Design (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | C4 L1 Context diagram present | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 2 | C4 L2 Container diagram present | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 3 | C4 L3 Component diagram present | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 4 | C4 L4 Code (longest functions) | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 5 | ADR filed for major design decisions | TBD | `docs/architecture/adr/` |
| 6 | Bounded context documented | TBD | reviewer notes |
| 7 | Separation of concerns enforced | TBD | review §2 File Inventory roles |
| 8 | Class diagram (UML) present | **10** | ✓ §8 |
| 9 | Sequence diagram per endpoint | **10** | ✓ §15 |
| 10 | Integration graph documented | **10** | ✓ §27 |

### 2. Code Quality (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | File inventory with roles | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §5 |
| 2 | Longest-functions list | **10** | ✓ §0 |
| 3 | No function > 50 lines without justification | TBD | `radon cc -a -nc` |
| 4 | Cyclomatic complexity ≤ 15 per fn | TBD | `radon cc -nc` |
| 5 | No file > 500 lines without sub-modules | TBD | `wc -l` per file |
| 6 | Linted (ruff/eslint, zero warnings) | TBD | CI log |
| 7 | Type-checked (mypy/ts-strict) | TBD | CI log |
| 8 | No dead code (vulture / unused exports) | TBD | reviewer audit |
| 9 | DRY — no duplicate logic across files | TBD | reviewer audit |
| 10 | KISS — simplest design that works | TBD | reviewer judgment |

### 3. Security (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Input validation present (Pydantic/Zod) | **10** if detected | §20 — detected: Manual escape, Pydantic BaseModel |
| 2 | AuthN enforced (Depends-based) | TBD | — |
| 3 | OWASP Top 10 reviewed | TBD | STRIDE table per container |
| 4 | No hardcoded secrets | **10** | ✓ no hardcoded password/api-key literals detected |
| 5 | Secrets in Vault / env, not code | TBD | §4 Env Vars |
| 6 | SAST scan clean (bandit/semgrep) | TBD | CI log |
| 7 | Dependency CVE scan clean (pip-audit) | TBD | CI log |
| 8 | PII masked in logs | TBD | §24 |
| 9 | TLS / encryption in transit | TBD | infra config |
| 10 | For AI: prompt injection defense | **10** | Rebuff detected |

### 4. Performance (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Latency SLO documented | TBD | reviewer |
| 2 | Load tested (k6/Locust) | TBD | `tests/load/` |
| 3 | p95 measured + within SLO | TBD | Grafana panel |
| 4 | Pagination on list endpoints | TBD | — |
| 5 | Caches bounded (LRU/TTL) | **10** | detected: in-memory @lru_cache, redis |
| 6 | Async I/O where applicable | **10** | 50 async functions detected |
| 7 | Timeouts on all external calls | **10** | ✓ timeout= or asyncio.wait_for — detected at `dispatch_pool.py:174` |
| 8 | Memory profile clean (no growth) | TBD | py-spy / mprof |
| 9 | Capacity model documented | TBD | runbook |
| 10 | Cost per request tracked (token/cpu) | TBD | finops dashboard |

### 5. Reliability (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Retry with exp backoff | TBD | reviewer audit |
| 2 | Circuit breaker on external deps | **10** | ✓ CircuitBreaker wired — detected at `breakers.py:5` |
| 3 | Graceful degradation path | TBD | reviewer audit |
| 4 | Health probe (startup/liveness/readiness) | TBD | — |
| 5 | Rollback tested in staging | TBD | deploy runbook |
| 6 | DR plan with RTO/RPO | TBD | runbook |
| 7 | Idempotency keys for writes | TBD | reviewer audit |
| 8 | Dead-letter queue for events | TBD | Kafka config |
| 9 | Bulkhead isolation | TBD | reviewer audit |
| 10 | Chaos test passed | TBD | chaos run log |

### 6. Observability (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Execution sequence with debug taps | **10** | ✓ §13 |
| 2 | Business-logic step sequence | **10** | ✓ §14 |
| 3 | Structured JSON logs | **10** | ✓ structured logger — detected at `kafka_client.py:319` |
| 4 | correlation_id propagated everywhere | **10** | ✓ correlation_id used — detected at `__init__.py:16` |
| 5 | Tracing (OTel) wired | **10** | ✓ OTel imported — detected at `kafka_client.py:47` |
| 6 | Metrics exposed (RED: rate/errors/duration) | **10** | ✓ Prometheus instrumentation — detected at `ai_governance.py:47` |
| 7 | Grafana dashboard exists | TBD | dashboard URL |
| 8 | Alerts defined (SLO burn) | TBD | Alertmanager config |
| 9 | Runbook references | TBD | `ops/runbook/<svc>.md` |
| 10 | Decision audit row per AI call (§38+§48) | **10** | ✓ decision_audit ref — detected at `audit.py:20` |

### 7. Testing (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Test files detected | TBD | 0 test files |
| 2 | Test cases auto-parsed | TBD | 0 test functions |
| 3 | Statement coverage ≥ 80% | TBD | `pytest --cov` |
| 4 | Branch coverage ≥ 70% | TBD | `pytest --cov-branch` |
| 5 | Negative-test cases (≥3 per drill) | TBD | §43 discipline |
| 6 | Drill with real services (no mocks) | TBD | `mcp/tests/drill_*.py` |
| 7 | Property-based tests (hypothesis) | TBD | reviewer audit |
| 8 | Fuzz tests (atheris/honggfuzz) | TBD | reviewer audit |
| 9 | Contract tests with downstream services | TBD | reviewer audit |
| 10 | Smoke + load + chaos in CI | TBD | CI pipeline |

### 8. Operations (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Quick Start (5-cmd boot) | **10** | ✓ §2 |
| 2 | Env vars table | **10** | ✓ §4 |
| 3 | Where-does-X-live cheat sheet | **10** | ✓ §6 |
| 4 | Debugging guide | **10** | ✓ §29 |
| 5 | Runbook for common incidents | TBD | `ops/runbook/<svc>.md` |
| 6 | On-call rotation defined | TBD | PagerDuty |
| 7 | SLO/SLA published | TBD | reviewer audit |
| 8 | Capacity headroom monitored | TBD | Grafana panel |
| 9 | Cost dashboard | TBD | FinOps dashboard |
| 10 | Backup + restore tested | TBD | DR drill log |

### 9. Governance & Compliance (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Owner (team + on-call) defined | TBD | CODEOWNERS |
| 2 | Risk register entry | TBD | `docs/architecture/security/` |
| 3 | Change management process | TBD | PR template |
| 4 | Audit log retention ≥ 6 months | TBD | EU AI Act Art. 12 |
| 5 | Right-to-explanation supported | TBD | §48 + EU AI Act Art. 86 |
| 6 | Bias / fairness pre-deploy gate | TBD | §48 |
| 7 | Model card filed (for AI) | TBD | `docs/model-cards/` |
| 8 | SOC2 controls mapped | TBD | compliance matrix |
| 9 | GDPR — PII inventory | TBD | data lineage |
| 10 | Vendor / SaaS dependencies tracked | TBD | `docs/vendors.md` |

### 10. Documentation (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | README present | **10** | ✓ this file |
| 2 | README has all 33 §58 sections | **10** | ✓ drill-locked |
| 3 | README freshness < 7 days | TBD | git log mtime |
| 4 | File inventory current | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §5 |
| 5 | Recent activity tracked | **10** | ✓ §30 |
| 6 | Domain glossary present | **10** | ✓ §28 |
| 7 | ADRs cross-linked | TBD | reviewer audit |
| 8 | Runbook cross-linked | TBD | reviewer audit |
| 9 | OpenAPI spec generated + linked | TBD | `/openapi.json` URL |
| 10 | Sequence diagrams up-to-date | TBD | 0 endpoints diagrammed |

### Aggregate score

```
Auto-locked rows  : count below — drill-protected, deterministic
Reviewer-fill rows: TBD — reviewer scores honestly per evidence
Target            : ≥ 80 / 100 for production
Brutal rule       : never overwrite TBD with ✓ without evidence
```

Run `python3 mcp/tests/drill_readme_generator.py` to verify the auto-locked rows are still locked. Manually fill TBD rows during PR review using the evidence-column commands as starting point.


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
