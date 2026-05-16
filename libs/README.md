# 📦 `libs` — Advanced README

  ·  **Path:** `libs`  ·  **Generated:** 2026-05-16 19:57 UTC

> _Purpose not detected from docstrings — reviewer to fill._

This README is **auto-generated** by [`scripts/generate_folder_report.py`](../../scripts/generate_folder_report.py). It explains what this folder does, every file inside it, how the files link to each other, every API endpoint, every database call, every test case, and the production controls (security / reliability / performance / observability). Re-run after major changes.

---

## 🔎 Section 0 — Auto-Detected Facts

| Metric | Value |
|---|---|
| Folder | `libs` |
| Total files | 89 |
| Python files | 65 |
| TypeScript/JS files | 0 |
| Go files | 0 |
| Shell scripts | 0 |
| Lines of code | 12,249 |
| Python classes | 256 |
| Python functions | 814 |
| Async functions | 150 |
| Total API endpoints | 6 |
| Total DB call sites | 19 |
| DB / Storage libs | Kafka (aiokafka), Neo4j, Redis, asyncpg |
| Concurrency primitives | Lock / RLock, asyncio (async/await), threading |
| Caching primitives | in-memory @lru_cache, redis |
| Input validation | Manual escape, Pydantic BaseModel |
| AI / LLM deps | LangChain, Ollama, Rebuff (PI defense) |
| Test files | 26 |
| Detected test cases | 420 |
| Tests dir present | ✅ |
| Dockerfile | ❌ |
| pyproject.toml | ❌ |
| go.mod | ❌ |
| package.json | ❌ |
| Top git contributors | `55	PraveenAsthana123`, `7	Praveen` |

#### Longest functions (top 5)

| Location | Name | Lines |
|---|---|---|
| `py/documind_core/circuit_breaker.py:347` | `__init__` | 152 |
| `py/documind_core/audit.py:146` | `write` | 143 |
| `py/documind_core/agent_board.py:317` | `run` | 101 |
| `py/documind_core/drift_detection.py:167` | `compare_windows` | 82 |
| `py/documind_core/breakers.py:249` | `check` | 69 |

#### Smells detected (grep heuristics — verify manually)

| Smell | Count |
|---|---|
| hardcoded localhost URL | 8 |


## 1. Purpose — Business + Technical

### Business problem this folder solves

> _Reviewer to fill: one paragraph describing the business need_

### Technical contract this folder exposes

> _Reviewer to fill: API surface, events emitted, data persisted, downstream consumers._

### Out-of-scope (what this folder does NOT do)

> _Reviewer to fill: explicit non-goals — prevents scope creep at review time._


## 2. File Inventory

Every Python file in this folder, with role / classes / functions / LOC / first docstring line. Full absolute paths listed below the table for easy `cat`-ability.

| Relative path | Role (inferred) | Classes | Functions | LOC | Summary |
|---|---|---|---|---|---|
| `py/documind_core/__init__.py` | 🚀 entry point / app bootstrap | 0 | 0 | 134 | documind_core |
| `py/documind_core/a2a_protocol.py` | 📄 module | 6 | 3 | 333 | Agent-to-Agent (A2A) protocol — registry + message bus + connector + delegation. |
| `py/documind_core/agent_board.py` | 🤖 agent / tool | 5 | 5 | 616 | AgentBoard — multi-agent task / review / advise pattern with bounded |
| `py/documind_core/agentic_framework.py` | 🤖 agent / tool | 2 | 2 | 260 | Agentic engineering framework — meta-template for every agent. |
| `py/documind_core/ai_governance.py` | 📄 module | 14 | 1 | 700 | AI governance primitives — debuggability, explainability, responsibility, |
| `py/documind_core/audit.py` | 📄 module | 2 | 3 | 292 | Tamper-evident audit log (Design Area 27 — Governance). |
| `py/documind_core/auth.py` | 📄 module | 2 | 4 | 348 | JWT auth verifier + FastAPI dependency for Python services. |
| `py/documind_core/bm25.py` | 📄 module | 2 | 1 | 133 | BM25 lexical retrieval — wraps `rank_bm25` for the hybrid-retrieval |
| `py/documind_core/body_limit.py` | 📄 module | 1 | 0 | 58 | Request-body size limit (FastAPI middleware). |
| `py/documind_core/breakers.py` | 📄 module | 18 | 1 | 1049 | Specialized circuit breakers (Design Area 4 + Extra-CB, plus AI/RAG-specific). |
| `py/documind_core/cache.py` | 📄 module | 1 | 0 | 134 | Cache helpers (Design Areas 40 — Cache Architecture, 41 — Cache Consistency, |
| `py/documind_core/chunking.py` | 📄 module | 10 | 1 | 416 | Multi-strategy chunking — Strategy + Factory pattern (§7 of the |
| `py/documind_core/circuit_breaker.py` | 📄 module | 6 | 1 | 1072 | Circuit Breaker (Design Area 4 — Failure Boundary, Extra — Circuit Breaker). |
| `py/documind_core/citations.py` | 📄 module | 4 | 2 | 202 | Citation linking — claim-to-source provenance (§16.6 + §48 of the |
| `py/documind_core/config.py` | ⚙ config / settings | 1 | 1 | 182 | Configuration foundation (Design Areas 6 — Control Plane, 55 — Feature Flags, |
| `py/documind_core/db_client.py` | 🔌 external service adapter | 2 | 0 | 149 | PostgreSQL client (Design Areas 5 — Tenant RLS, 12 — Consistency, 46 — DB Strategy). |
| `py/documind_core/dispatch_pool.py` | 📄 module | 3 | 0 | 213 | DispatchPool - fanout 100+ tasks with bounded LLM concurrency. |
| `py/documind_core/dr_metrics.py` | 📄 module | 1 | 2 | 139 | Disaster Recovery target metrics — single source of truth. |
| `py/documind_core/drift_detection.py` | 📄 module | 2 | 3 | 249 | Drift detection — Production Validation §44 maturity item. |
| `py/documind_core/embedding_cache.py` | 📄 module | 2 | 2 | 179 | Embedding cache — content-hash → vector with model-version namespacing |
| `py/documind_core/encryption.py` | 📄 module | 1 | 1 | 74 | At-rest encryption for secrets stored in the database. |
| `py/documind_core/error_tracking.py` | 📄 module | 0 | 5 | 153 | Error-tracking integration — Sentry wrapper. |
| `py/documind_core/exceptions.py` | 📄 module | 10 | 0 | 176 | Domain exception hierarchy (Design Area 9 — State Model; cross-cutting). |
| `py/documind_core/fusion.py` | 📄 module | 1 | 2 | 145 | Hybrid retrieval fusion — RRF + heap-based top-K (§16.5 of the |
| `py/documind_core/governance_os.py` | 📄 module | 8 | 1 | 363 | AI Governance OS — unified policy / decision / risk / compliance / audit surface. |
| `py/documind_core/idempotency.py` | 📄 module | 2 | 0 | 65 | HTTP idempotency (Design Area 20). |
| `py/documind_core/idempotency_middleware.py` | 🪝 middleware / interceptor | 1 | 0 | 113 | FastAPI middleware for the ``X-Idempotency-Key`` pattern (Design Area 20). |
| `py/documind_core/kafka_client.py` | 🔌 external service adapter | 2 | 2 | 335 | Kafka client (Design Areas 17 — Event-Driven, 19 — Compensation, |
| `py/documind_core/logging_config.py` | ⚙ config / settings | 0 | 8 | 201 | Structured logging (Design Area 62 — Observability by Design). |
| `py/documind_core/middleware.py` | 🪝 middleware / interceptor | 6 | 1 | 391 | FastAPI middleware stack (Design Areas 62 — Observability, 5 — Tenant, |
| `py/documind_core/mmr.py` | 📄 module | 0 | 1 | 100 | MMR — Maximal Marginal Relevance (§16.6 post-retrieval diversification). |
| `py/documind_core/observability.py` | 📄 module | 0 | 5 | 251 | Observability setup (Design Areas 62 — Observability by Design, 64 — SLO-Driven). |
| `py/documind_core/pii.py` | 📄 module | 2 | 1 | 193 | PII detection — multi-pattern Aho-Corasick-style scanner (§16.11 |
| `py/documind_core/query_rewriter.py` | 📄 module | 2 | 0 | 133 | Pre-retrieval query processing (§16.4 of the playbook). |
| `py/documind_core/rate_limiter.py` | 📄 module | 2 | 2 | 191 | Rate limiting (Design Areas 42 — Tenant-Aware Cache, 45 — Backpressure). |
| `py/documind_core/rebuff_detector.py` | 📄 module | 2 | 7 | 272 | Rebuff detector — Stage-1 runtime PI-defense adapter (per §47.6, §48, §56). |
| `py/documind_core/schemas.py` | 📋 data model / schema | 4 | 0 | 49 | Shared response schemas (Global CLAUDE.md §6 — API Design Standards). |
| `py/documind_core/tokens.py` | 📄 module | 2 | 2 | 99 | Token counting + budget helpers (§16.1 / §16.2 of the playbook). |
| `py/tests/conftest.py` | 📄 module | 0 | 1 | 21 | pytest config for documind_core unit tests. |
| `py/tests/test_ai_governance.py` | 🧪 test | 0 | 33 | 370 | Unit tests for the AI-governance primitives. |
| `py/tests/test_audit.py` | 🧪 test | 4 | 2 | 277 | Tests for documind_core.audit — tamper-evident audit-log writer. |
| `py/tests/test_bm25.py` | 🧪 test | 4 | 0 | 121 | Tests for documind_core.bm25 — BM25 lexical retrieval wrapper. |
| `py/tests/test_body_limit.py` | 🧪 test | 2 | 1 | 112 | Tests for documind_core.body_limit — request-body size cap middleware. |
| `py/tests/test_breakers.py` | 🧪 test | 0 | 20 | 268 | Unit tests for the 5 specialized circuit breakers. |
| `py/tests/test_cache.py` | 🧪 test | 6 | 1 | 277 | Tests for documind_core.cache — tenant-aware Redis cache helper. |
| `py/tests/test_chunking.py` | 🧪 test | 10 | 0 | 282 | Tests for documind_core.chunking — Strategy + Factory pattern, 7 |
| `py/tests/test_citations.py` | 🧪 test | 5 | 1 | 187 | Tests for documind_core.citations — claim-to-source linker. |
| `py/tests/test_config.py` | ⚙ config / settings | 5 | 1 | 135 | Tests for documind_core.config — Pydantic Settings foundation. |
| `py/tests/test_db_client.py` | 🔌 external service adapter | 4 | 0 | 166 | Tests for documind_core.db_client — asyncpg pool + tenant RLS context. |
| `py/tests/test_dispatch_pool.py` | 🧪 test | 3 | 0 | 135 | Tests for documind_core.dispatch_pool — bounded-concurrency task pool. |
| `py/tests/test_embedding_cache.py` | 🧪 test | 8 | 1 | 218 | Tests for documind_core.embedding_cache. |
| `py/tests/test_encryption.py` | 🧪 test | 4 | 2 | 139 | Tests for documind_core.encryption — Fernet wrapper + sentinel prefix. |
| `py/tests/test_error_tracking.py` | 🧪 test | 5 | 1 | 141 | Tests for documind_core.error_tracking — Sentry init wrapper. |
| `py/tests/test_exceptions.py` | 🧪 test | 4 | 0 | 122 | Tests for documind_core.exceptions — domain exception hierarchy. |
| `py/tests/test_fusion.py` | 🧪 test | 5 | 0 | 148 | Tests for documind_core.fusion — RRF + heap top-K. |
| `py/tests/test_idempotency.py` | 🧪 test | 4 | 1 | 122 | Tests for documind_core.idempotency — Redis-backed X-Idempotency-Key cache. |
| `py/tests/test_idempotency_middleware.py` | 🪝 middleware / interceptor | 5 | 2 | 196 | Tests for documind_core.idempotency_middleware. |
| `py/tests/test_logging_config.py` | ⚙ config / settings | 7 | 0 | 215 | Tests for documind_core.logging_config — JSON structured logging. |
| `py/tests/test_mmr.py` | 🧪 test | 3 | 0 | 108 | Tests for documind_core.mmr — Maximal Marginal Relevance. |
| `py/tests/test_pii.py` | 🧪 test | 11 | 0 | 206 | Tests for documind_core.pii — multi-pattern PII scanner. |
| `py/tests/test_query_rewriter.py` | 🧪 test | 5 | 0 | 129 | Tests for documind_core.query_rewriter — pre-retrieval query |
| `py/tests/test_rate_limiter.py` | 🧪 test | 6 | 1 | 233 | Tests for documind_core.rate_limiter — sliding-window Redis limiter. |
| `py/tests/test_rls_isolation.py` | 🧪 test | 0 | 2 | 115 | Cross-tenant RLS isolation test (Design Area 5 — most important security test). |
| `py/tests/test_schemas.py` | 📋 data model / schema | 4 | 0 | 99 | Tests for documind_core.schemas — shared API response envelopes. |
| `py/tests/test_tokens.py` | 🧪 test | 3 | 0 | 123 | Tests for documind_core.tokens — token counting + budget packing. |

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
- `/mnt/deepa/rag/libs/py/tests/conftest.py`
- `/mnt/deepa/rag/libs/py/tests/test_ai_governance.py`
- `/mnt/deepa/rag/libs/py/tests/test_audit.py`
- `/mnt/deepa/rag/libs/py/tests/test_bm25.py`
- `/mnt/deepa/rag/libs/py/tests/test_body_limit.py`
- `/mnt/deepa/rag/libs/py/tests/test_breakers.py`
- `/mnt/deepa/rag/libs/py/tests/test_cache.py`
- `/mnt/deepa/rag/libs/py/tests/test_chunking.py`
- `/mnt/deepa/rag/libs/py/tests/test_citations.py`
- `/mnt/deepa/rag/libs/py/tests/test_config.py`
- `/mnt/deepa/rag/libs/py/tests/test_db_client.py`
- `/mnt/deepa/rag/libs/py/tests/test_dispatch_pool.py`
- `/mnt/deepa/rag/libs/py/tests/test_embedding_cache.py`
- `/mnt/deepa/rag/libs/py/tests/test_encryption.py`
- `/mnt/deepa/rag/libs/py/tests/test_error_tracking.py`
- `/mnt/deepa/rag/libs/py/tests/test_exceptions.py`
- `/mnt/deepa/rag/libs/py/tests/test_fusion.py`
- `/mnt/deepa/rag/libs/py/tests/test_idempotency.py`
- `/mnt/deepa/rag/libs/py/tests/test_idempotency_middleware.py`
- `/mnt/deepa/rag/libs/py/tests/test_logging_config.py`
- `/mnt/deepa/rag/libs/py/tests/test_mmr.py`
- `/mnt/deepa/rag/libs/py/tests/test_pii.py`
- `/mnt/deepa/rag/libs/py/tests/test_query_rewriter.py`
- `/mnt/deepa/rag/libs/py/tests/test_rate_limiter.py`
- `/mnt/deepa/rag/libs/py/tests/test_rls_isolation.py`
- `/mnt/deepa/rag/libs/py/tests/test_schemas.py`
- `/mnt/deepa/rag/libs/py/tests/test_tokens.py`


## 3. C4 Model — Context / Container / Component / Code

### Level 1 — System Context

_Where does this folder sit in the broader system?_

```mermaid
flowchart LR
    Caller([External Caller]) --> This["libs"]
    This --> documind_core_ai_governance[documind_core/ai_governance]
    This --> documind_core_exceptions[documind_core/exceptions]
    This --> documind_core_audit[documind_core/audit]
    This --> documind_core_bm25[documind_core/bm25]
    This --> documind_core_fusion[documind_core/fusion]
    This --> documind_core_body_limit[documind_core/body_limit]
```

### Level 2 — Container

_What external dependencies does this folder talk to?_

```mermaid
flowchart TB
    subgraph libs
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
    subgraph __entry_point___app_bootstrap["🚀 entry point / app bootstrap"]
        py_documind_core___init___py["py/documind_core/__init__.py"]
    end
    subgraph __module["📄 module"]
        py_documind_core_a2a_protocol_py["py/documind_core/a2a_protocol.py"]
        py_documind_core_ai_governance_py["py/documind_core/ai_governance.py"]
        py_documind_core_audit_py["py/documind_core/audit.py"]
        py_documind_core_auth_py["py/documind_core/auth.py"]
        py_documind_core_bm25_py["py/documind_core/bm25.py"]
        py_documind_core_body_limit_py["py/documind_core/body_limit.py"]
        more___module["... +23 more"]
    end
    subgraph __agent___tool["🤖 agent / tool"]
        py_documind_core_agent_board_py["py/documind_core/agent_board.py"]
        py_documind_core_agentic_framework_py["py/documind_core/agentic_framework.py"]
    end
    subgraph __config___settings["⚙ config / settings"]
        py_documind_core_config_py["py/documind_core/config.py"]
        py_documind_core_logging_config_py["py/documind_core/logging_config.py"]
        py_tests_test_config_py["py/tests/test_config.py"]
        py_tests_test_logging_config_py["py/tests/test_logging_config.py"]
    end
    subgraph __external_service_adapter["🔌 external service adapter"]
        py_documind_core_db_client_py["py/documind_core/db_client.py"]
        py_documind_core_kafka_client_py["py/documind_core/kafka_client.py"]
        py_tests_test_db_client_py["py/tests/test_db_client.py"]
    end
    subgraph __middleware___interceptor["🪝 middleware / interceptor"]
        py_documind_core_idempotency_middleware_py["py/documind_core/idempotency_middleware.py"]
        py_documind_core_middleware_py["py/documind_core/middleware.py"]
        py_tests_test_idempotency_middleware_py["py/tests/test_idempotency_middleware.py"]
    end
    subgraph __data_model___schema["📋 data model / schema"]
        py_documind_core_schemas_py["py/documind_core/schemas.py"]
        py_tests_test_schemas_py["py/tests/test_schemas.py"]
    end
    subgraph __test["🧪 test"]
        py_tests_test_ai_governance_py["py/tests/test_ai_governance.py"]
        py_tests_test_audit_py["py/tests/test_audit.py"]
        py_tests_test_bm25_py["py/tests/test_bm25.py"]
        py_tests_test_body_limit_py["py/tests/test_body_limit.py"]
        py_tests_test_breakers_py["py/tests/test_breakers.py"]
        py_tests_test_cache_py["py/tests/test_cache.py"]
        more___test["... +15 more"]
    end
```

### Level 4 — Code (top hotspots)

_Longest functions — these are the most likely refactor candidates._

```mermaid
flowchart TB
    py_documind_core_circuit_breaker_py_347_["__init__ (152 lines)<br/>py/documind_core/circuit_breaker.py:347"]
    py_documind_core_audit_py_146_write["write (143 lines)<br/>py/documind_core/audit.py:146"]
    py_documind_core_agent_board_py_317_run["run (101 lines)<br/>py/documind_core/agent_board.py:317"]
    py_documind_core_drift_detection_py_167_["compare_windows (82 lines)<br/>py/documind_core/drift_detection.py:167"]
    py_documind_core_breakers_py_249_check["check (69 lines)<br/>py/documind_core/breakers.py:249"]
```


## 4. Code Sequence — How Files Link to Each Other

**Import graph for files in this folder.** Reading order: start at any entry-point file (look for `🚀 entry point` role in the inventory above), then follow the arrows.

```mermaid
flowchart LR
    none[No internal imports detected — files are decoupled]
```

### Edge list

_No internal imports detected._


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

**Detected endpoints:** 6

| Method | Route | Defined in | Input (schema) | Process (summary) | Output (schema) |
|---|---|---|---|---|---|
| `POST` | `/api/x` | `py/tests/test_body_limit.py:32` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/upload/x` | `py/tests/test_body_limit.py:36` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/api/charge` | `py/tests/test_idempotency_middleware.py:59` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/api/fail` | `py/tests/test_idempotency_middleware.py:64` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/api/validate-error` | `py/tests/test_idempotency_middleware.py:69` | _TBD_ | _TBD_ | _TBD_ |
| `GET` | `/api/read` | `py/tests/test_idempotency_middleware.py:74` | _TBD_ | _TBD_ | _TBD_ |

_Reviewer fills the last three columns from the Pydantic models in the handler. Auto-extraction of Pydantic schemas is on the roadmap._


## 7. Sequence Diagrams per Endpoint

### Generic flow (all endpoints)

```mermaid
sequenceDiagram
  autonumber
  participant Client
  participant API as libs
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

### `POST /api/x` (py/tests/test_body_limit.py:32)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (py/tests/test_body_limit.py:32)
  participant S as Service
  participant D as DB / external
  C->>H: POST /api/x
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /upload/x` (py/tests/test_body_limit.py:36)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (py/tests/test_body_limit.py:36)
  participant S as Service
  participant D as DB / external
  C->>H: POST /upload/x
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /api/charge` (py/tests/test_idempotency_middleware.py:59)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (py/tests/test_idempotency_middleware.py:59)
  participant S as Service
  participant D as DB / external
  C->>H: POST /api/charge
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /api/fail` (py/tests/test_idempotency_middleware.py:64)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (py/tests/test_idempotency_middleware.py:64)
  participant S as Service
  participant D as DB / external
  C->>H: POST /api/fail
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /api/validate-error` (py/tests/test_idempotency_middleware.py:69)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (py/tests/test_idempotency_middleware.py:69)
  participant S as Service
  participant D as DB / external
  C->>H: POST /api/validate-error
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

_(+1 more endpoints — diagrams omitted for brevity.)_


## 8. Database Layer

**DB / storage libraries:** Kafka (aiokafka), Neo4j, Redis, asyncpg

**Total DB call sites:** 19

| Pattern | Count |
|---|---|
| `execute` | 7 |
| `fetch/fetchall/fetchrow` | 5 |
| `ORM CRUD` | 7 |

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
| No hardcoded values | — | smell count: 8 |
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
| Parallel processing where beneficial | — | 150 async fns |

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

**Test files detected:** 26
**Test functions parsed:** 420

| Test name | Location | Purpose (from docstring) |
|---|---|---|
| `test_injection_blocks_ignore_previous` | `py/tests/test_ai_governance.py:23` | _(no docstring)_ |
| `test_injection_blocks_delimiter_spoof` | `py/tests/test_ai_governance.py:29` | _(no docstring)_ |
| `test_injection_ok_benign` | `py/tests/test_ai_governance.py:35` | _(no docstring)_ |
| `test_injection_raises_on_block` | `py/tests/test_ai_governance.py:41` | _(no docstring)_ |
| `test_pii_detects_ssn_and_email` | `py/tests/test_ai_governance.py:52` | _(no docstring)_ |
| `test_pii_redact_replaces_inline` | `py/tests/test_ai_governance.py:61` | _(no docstring)_ |
| `test_pii_clean_text_no_findings` | `py/tests/test_ai_governance.py:69` | _(no docstring)_ |
| `test_adversarial_too_long_rejected` | `py/tests/test_ai_governance.py:79` | _(no docstring)_ |
| `test_adversarial_repeat_run_detected` | `py/tests/test_ai_governance.py:85` | _(no docstring)_ |
| `test_adversarial_benign_passes` | `py/tests/test_ai_governance.py:91` | _(no docstring)_ |
| `test_responsible_flags_protected_class_generalization` | `py/tests/test_ai_governance.py:101` | _(no docstring)_ |
| `test_responsible_flags_absolute_without_citation` | `py/tests/test_ai_governance.py:111` | _(no docstring)_ |
| `test_responsible_flags_missing_ai_disclosure` | `py/tests/test_ai_governance.py:121` | _(no docstring)_ |
| `test_responsible_clean_response_no_flags` | `py/tests/test_ai_governance.py:131` | _(no docstring)_ |
| `test_explainer_builds_narrative_with_chunks` | `py/tests/test_ai_governance.py:146` | _(no docstring)_ |
| `test_explainer_empty_retrieval_warns_in_narrative` | `py/tests/test_ai_governance.py:174` | _(no docstring)_ |
| `test_trace_records_step_with_timing` | `py/tests/test_ai_governance.py:195` | _(no docstring)_ |
| `test_injection_scan_empty_text_returns_empty` | `py/tests/test_ai_governance.py:214` | _(no docstring)_ |
| `test_injection_scan_no_match_returns_empty_list` | `py/tests/test_ai_governance.py:219` | _(no docstring)_ |
| `test_pii_scan_empty_text_returns_empty` | `py/tests/test_ai_governance.py:225` | _(no docstring)_ |
| `test_pii_scan_caps_at_20_findings` | `py/tests/test_ai_governance.py:229` | _(no docstring)_ |
| `test_pii_redact_empty_returns_empty` | `py/tests/test_ai_governance.py:240` | _(no docstring)_ |
| `test_pii_redact_value_handles_str` | `py/tests/test_ai_governance.py:245` | _(no docstring)_ |
| `test_pii_redact_value_handles_dict` | `py/tests/test_ai_governance.py:251` | _(no docstring)_ |
| `test_pii_redact_value_handles_list` | `py/tests/test_ai_governance.py:258` | _(no docstring)_ |
| `test_pii_redact_value_handles_tuple` | `py/tests/test_ai_governance.py:265` | _(no docstring)_ |
| `test_pii_redact_value_passes_through_numbers_and_none` | `py/tests/test_ai_governance.py:273` | _(no docstring)_ |
| `test_pii_redact_value_handles_nested` | `py/tests/test_ai_governance.py:281` | _(no docstring)_ |
| `test_explainer_guardrail_violations_appear_in_narrative` | `py/tests/test_ai_governance.py:295` | _(no docstring)_ |
| `test_adversarial_too_many_urls_flagged` | `py/tests/test_ai_governance.py:329` | _(no docstring)_ |
| `test_adversarial_non_printable_ratio_flagged` | `py/tests/test_ai_governance.py:337` | _(no docstring)_ |
| `test_trace_steps_property_returns_copy` | `py/tests/test_ai_governance.py:351` | _(no docstring)_ |
| `test_injection_scan_or_raise_passes_when_no_block` | `py/tests/test_ai_governance.py:365` | _(no docstring)_ |
| `test_strips_error_suffix` | `py/tests/test_audit.py:40` | _(no docstring)_ |
| `test_keeps_name_without_error_suffix` | `py/tests/test_audit.py:43` | _(no docstring)_ |
| `test_only_error_class` | `py/tests/test_audit.py:49` | _(no docstring)_ |
| `test_stable_across_key_order` | `py/tests/test_audit.py:62` | _(no docstring)_ |
| `test_handles_datetime_via_default_str` | `py/tests/test_audit.py:69` | _(no docstring)_ |
| `test_deterministic` | `py/tests/test_audit.py:80` | _(no docstring)_ |
| `test_changes_with_each_field` | `py/tests/test_audit.py:92` | _(no docstring)_ |
| `test_hash_is_sha256_hex` | `py/tests/test_audit.py:118` | _(no docstring)_ |
| `test_resource_type_none_treated_as_empty` | `py/tests/test_audit.py:132` | _(no docstring)_ |
| `test_first_row_seeds_chain_with_empty_prev` | `py/tests/test_audit.py:181` | _(no docstring)_ |
| `test_subsequent_row_chains_off_previous` | `py/tests/test_audit.py:193` | _(no docstring)_ |
| `test_service_stamped_into_details` | `py/tests/test_audit.py:202` | _(no docstring)_ |
| `test_caller_supplied_service_not_clobbered` | `py/tests/test_audit.py:214` | _(no docstring)_ |
| `test_fail_open_default_swallows_db_error` | `py/tests/test_audit.py:224` | _(no docstring)_ |
| `test_fail_closed_raises_data_error` | `py/tests/test_audit.py:234` | _(no docstring)_ |
| `test_hash_chain_matches_compute_function` | `py/tests/test_audit.py:249` | _(no docstring)_ |
| `test_lowercase_split` | `py/tests/test_bm25.py:25` | _(no docstring)_ |
| `test_strips_punct` | `py/tests/test_bm25.py:28` | _(no docstring)_ |
| `test_empty` | `py/tests/test_bm25.py:31` | _(no docstring)_ |
| `test_frozen` | `py/tests/test_bm25.py:36` | _(no docstring)_ |
| `test_empty_corpus` | `py/tests/test_bm25.py:43` | _(no docstring)_ |
| `test_basic_ranking` | `py/tests/test_bm25.py:48` | _(no docstring)_ |
| `test_no_match_returns_empty` | `py/tests/test_bm25.py:63` | _(no docstring)_ |
| `test_top_k_caps_results` | `py/tests/test_bm25.py:70` | _(no docstring)_ |
| `test_top_k_zero_raises` | `py/tests/test_bm25.py:75` | _(no docstring)_ |
| `test_empty_document_handled` | `py/tests/test_bm25.py:81` | _(no docstring)_ |
| `test_composes_with_rrf` | `py/tests/test_bm25.py:99` | _(no docstring)_ |
| `test_default_when_no_override` | `py/tests/test_body_limit.py:46` | _(no docstring)_ |
| `test_override_matches_prefix` | `py/tests/test_body_limit.py:50` | _(no docstring)_ |
| `test_no_content_length_passes` | `py/tests/test_body_limit.py:62` | _(no docstring)_ |
| `test_under_limit_passes` | `py/tests/test_body_limit.py:73` | _(no docstring)_ |
| `test_over_limit_rejected_413` | `py/tests/test_body_limit.py:79` | _(no docstring)_ |
| `test_path_override_higher_cap` | `py/tests/test_body_limit.py:90` | _(no docstring)_ |
| `test_malformed_content_length_treated_as_zero` | `py/tests/test_body_limit.py:99` | _(no docstring)_ |
| `test_retrieval_breaker_opens_when_quality_degrades` | `py/tests/test_breakers.py:28` | _(no docstring)_ |
| `test_retrieval_breaker_stays_closed_when_quality_good` | `py/tests/test_breakers.py:41` | _(no docstring)_ |
| `test_retrieval_breaker_opens_on_mostly_empty_results` | `py/tests/test_breakers.py:53` | _(no docstring)_ |
| `test_token_breaker_allow_under_budget` | `py/tests/test_breakers.py:73` | _(no docstring)_ |
| `test_token_breaker_rejects_over_daily` | `py/tests/test_breakers.py:85` | _(no docstring)_ |
| `test_token_breaker_warns_at_80pct` | `py/tests/test_breakers.py:98` | _(no docstring)_ |
| `test_token_breaker_rejects_per_request_blow_up` | `py/tests/test_breakers.py:111` | _(no docstring)_ |
| `test_token_breaker_raises_on_reject` | `py/tests/test_breakers.py:123` | _(no docstring)_ |
| `test_agent_breaker_stops_on_max_steps` | `py/tests/test_breakers.py:139` | _(no docstring)_ |
| `test_agent_breaker_detects_tool_loop` | `py/tests/test_breakers.py:150` | _(no docstring)_ |
| `test_agent_breaker_enforces_tool_budget` | `py/tests/test_breakers.py:159` | _(no docstring)_ |
| `test_agent_breaker_user_abort` | `py/tests/test_breakers.py:172` | _(no docstring)_ |
| `test_obs_breaker_allows_when_closed` | `py/tests/test_breakers.py:184` | _(no docstring)_ |
| `test_obs_breaker_opens_and_skips` | `py/tests/test_breakers.py:191` | _(no docstring)_ |
| `test_obs_breaker_never_raises` | `py/tests/test_breakers.py:200` | _(no docstring)_ |
| `test_ccb_blocks_on_repetition` | `py/tests/test_breakers.py:214` | _(no docstring)_ |
| `test_ccb_blocks_on_missing_citation_after_deadline` | `py/tests/test_breakers.py:226` | _(no docstring)_ |
| `test_ccb_continues_when_citation_present` | `py/tests/test_breakers.py:238` | _(no docstring)_ |
| `test_ccb_blocks_on_forbidden_pattern` | `py/tests/test_breakers.py:248` | _(no docstring)_ |
| `test_ccb_snapshot_includes_readings` | `py/tests/test_breakers.py:258` | _(no docstring)_ |
| `test_basic` | `py/tests/test_cache.py:40` | _(no docstring)_ |
| `test_single_part` | `py/tests/test_cache.py:43` | _(no docstring)_ |
| `test_empty_tenant_id_rejected` | `py/tests/test_cache.py:46` | _(no docstring)_ |
| `test_hit_returns_parsed` | `py/tests/test_cache.py:58` | _(no docstring)_ |
| `test_miss_returns_none` | `py/tests/test_cache.py:65` | _(no docstring)_ |
| `test_connection_error_fails_open` | `py/tests/test_cache.py:72` | _(no docstring)_ |
| `test_timeout_fails_open` | `py/tests/test_cache.py:80` | _(no docstring)_ |
| `test_os_error_fails_open` | `py/tests/test_cache.py:87` | _(no docstring)_ |
| `test_bad_json_returns_none` | `py/tests/test_cache.py:94` | _(no docstring)_ |
| `test_success_uses_default_ttl` | `py/tests/test_cache.py:107` | _(no docstring)_ |
| `test_explicit_ttl_overrides` | `py/tests/test_cache.py:115` | _(no docstring)_ |
| `test_connection_error_fails_open` | `py/tests/test_cache.py:122` | _(no docstring)_ |
| `test_serializes_with_default_str` | `py/tests/test_cache.py:131` | _(no docstring)_ |
| `test_zero_keys_returns_zero_no_call` | `py/tests/test_cache.py:146` | _(no docstring)_ |
| `test_multiple_keys_forwarded` | `py/tests/test_cache.py:153` | _(no docstring)_ |
| `test_no_matches_returns_zero` | `py/tests/test_cache.py:167` | _(no docstring)_ |
| `test_multiple_matches_deleted` | `py/tests/test_cache.py:179` | _(no docstring)_ |
| `test_cache_hit_skips_loader` | `py/tests/test_cache.py:197` | _(no docstring)_ |
| `test_miss_with_lock_calls_loader` | `py/tests/test_cache.py:207` | _(no docstring)_ |
| `test_miss_lock_contended_retry_hit` | `py/tests/test_cache.py:221` | _(no docstring)_ |
| `test_miss_lock_acquired_double_check_hits` | `py/tests/test_cache.py:242` | _(no docstring)_ |
| `test_miss_lock_contended_still_miss_falls_through` | `py/tests/test_cache.py:258` | _(no docstring)_ |
| `test_frozen` | `py/tests/test_chunking.py:40` | _(no docstring)_ |
| `test_default_version_stamped` | `py/tests/test_chunking.py:46` | _(no docstring)_ |
| `test_len` | `py/tests/test_chunking.py:50` | _(no docstring)_ |
| `test_simple_split` | `py/tests/test_chunking.py:58` | _(no docstring)_ |
| `test_empty_text` | `py/tests/test_chunking.py:63` | _(no docstring)_ |
| `test_size_zero_rejected` | `py/tests/test_chunking.py:66` | _(no docstring)_ |
| `test_whitespace_only_chunks_dropped` | `py/tests/test_chunking.py:70` | _(no docstring)_ |
| `test_overlap_repeats_text` | `py/tests/test_chunking.py:80` | _(no docstring)_ |
| `test_overlap_geq_size_rejected` | `py/tests/test_chunking.py:87` | _(no docstring)_ |
| `test_empty_text` | `py/tests/test_chunking.py:92` | _(no docstring)_ |
| `test_basic_split` | `py/tests/test_chunking.py:100` | _(no docstring)_ |
| `test_max_chars_caps_long_sentence` | `py/tests/test_chunking.py:105` | _(no docstring)_ |
| `test_empty_text` | `py/tests/test_chunking.py:113` | _(no docstring)_ |
| `test_blank_line_separated` | `py/tests/test_chunking.py:121` | _(no docstring)_ |
| `test_single_paragraph` | `py/tests/test_chunking.py:126` | _(no docstring)_ |
| `test_empty_strings_filtered` | `py/tests/test_chunking.py:130` | _(no docstring)_ |
| `test_simple_h1` | `py/tests/test_chunking.py:140` | _(no docstring)_ |
| `test_nested_headers_compose_path` | `py/tests/test_chunking.py:145` | _(no docstring)_ |
| `test_no_headers_falls_back_to_paragraph` | `py/tests/test_chunking.py:153` | _(no docstring)_ |
| `test_skips_header_with_empty_body` | `py/tests/test_chunking.py:162` | _(no docstring)_ |
| `test_under_limit_returns_single_chunk` | `py/tests/test_chunking.py:174` | _(no docstring)_ |
| `test_splits_on_first_separator` | `py/tests/test_chunking.py:179` | _(no docstring)_ |
| `test_falls_through_separator_cascade` | `py/tests/test_chunking.py:186` | _(no docstring)_ |
| `test_max_chars_zero_rejected` | `py/tests/test_chunking.py:199` | _(no docstring)_ |
| `test_oversized_atomic_unit_hard_cut` | `py/tests/test_chunking.py:203` | _(no docstring)_ |
| `test_caps_at_max_tokens` | `py/tests/test_chunking.py:216` | _(no docstring)_ |
| `test_custom_tokenizer` | `py/tests/test_chunking.py:224` | _(no docstring)_ |
| `test_max_tokens_zero_rejected` | `py/tests/test_chunking.py:230` | _(no docstring)_ |
| `test_empty_text` | `py/tests/test_chunking.py:234` | _(no docstring)_ |
| `test_enum` | `py/tests/test_chunking.py:242` | _(no docstring)_ |
| `test_string` | `py/tests/test_chunking.py:247` | _(no docstring)_ |
| `test_unknown_strategy_raises` | `py/tests/test_chunking.py:252` | _(no docstring)_ |
| `test_kwargs_forwarded` | `py/tests/test_chunking.py:258` | _(no docstring)_ |
| `test_every_strategy_stamps_version` | `py/tests/test_chunking.py:268` | _(no docstring)_ |
| `test_empty` | `py/tests/test_citations.py:30` | _(no docstring)_ |
| `test_single_sentence_no_terminator` | `py/tests/test_citations.py:34` | _(no docstring)_ |
| `test_multiple_sentences` | `py/tests/test_citations.py:40` | _(no docstring)_ |
| `test_offsets_correct` | `py/tests/test_citations.py:47` | _(no docstring)_ |
| `test_claim_frozen` | `py/tests/test_citations.py:55` | _(no docstring)_ |
| `test_cited_claim_frozen` | `py/tests/test_citations.py:60` | _(no docstring)_ |
| `test_is_supported_reflects_citations` | `py/tests/test_citations.py:65` | _(no docstring)_ |
| `test_min_overlap_out_of_range_raises` | `py/tests/test_citations.py:73` | _(no docstring)_ |
| `test_top_k_zero_raises` | `py/tests/test_citations.py:79` | _(no docstring)_ |
| `test_no_chunks_no_citations` | `py/tests/test_citations.py:85` | _(no docstring)_ |
| `test_finds_overlap_above_threshold` | `py/tests/test_citations.py:91` | _(no docstring)_ |
| `test_filters_below_min_overlap` | `py/tests/test_citations.py:105` | _(no docstring)_ |
| `test_top_k_caps_citations` | `py/tests/test_citations.py:115` | _(no docstring)_ |
| `test_citations_sorted_by_score_desc` | `py/tests/test_citations.py:128` | _(no docstring)_ |
| `test_claim_with_no_tokens_has_no_citations` | `py/tests/test_citations.py:142` | _(no docstring)_ |
| `test_all_supported_zero_rate` | `py/tests/test_citations.py:165` | _(no docstring)_ |
| `test_partial_support` | `py/tests/test_citations.py:174` | _(no docstring)_ |
| `test_empty_returns_zero` | `py/tests/test_citations.py:184` | _(no docstring)_ |
| `test_default_env_is_development` | `py/tests/test_config.py:30` | _(no docstring)_ |
| `test_default_postgres_credentials` | `py/tests/test_config.py:35` | _(no docstring)_ |
| `test_secret_passwords_default_to_dev_value` | `py/tests/test_config.py:41` | _(no docstring)_ |
| `test_optional_secrets_default_to_none` | `py/tests/test_config.py:48` | _(no docstring)_ |
| `test_env_prefix_accepted` | `py/tests/test_config.py:56` | _(no docstring)_ |
| `test_invalid_env_value_rejected` | `py/tests/test_config.py:62` | _(no docstring)_ |
| `test_int_coercion` | `py/tests/test_config.py:68` | _(no docstring)_ |
| `test_bool_coercion` | `py/tests/test_config.py:73` | _(no docstring)_ |
| `test_basic_format` | `py/tests/test_config.py:80` | _(no docstring)_ |
| `test_uses_get_secret_value` | `py/tests/test_config.py:87` | _(no docstring)_ |
| `test_default_split` | `py/tests/test_config.py:97` | _(no docstring)_ |
| `test_strips_whitespace` | `py/tests/test_config.py:103` | _(no docstring)_ |
| `test_empty_strings_filtered` | `py/tests/test_config.py:107` | _(no docstring)_ |
| `test_returns_default_class` | `py/tests/test_config.py:115` | _(no docstring)_ |
| `test_caches_per_class` | `py/tests/test_config.py:119` | _(no docstring)_ |
| `test_subclass_isolated` | `py/tests/test_config.py:124` | _(no docstring)_ |
| `test_init_does_not_connect` | `py/tests/test_db_client.py:30` | _(no docstring)_ |
| `test_pool_property_before_connect_raises` | `py/tests/test_db_client.py:36` | _(no docstring)_ |
| `test_connect_creates_pool` | `py/tests/test_db_client.py:42` | _(no docstring)_ |
| `test_connect_is_idempotent` | `py/tests/test_db_client.py:51` | _(no docstring)_ |
| `test_close_clears_pool` | `py/tests/test_db_client.py:62` | _(no docstring)_ |
| `test_close_when_never_connected_is_noop` | `py/tests/test_db_client.py:72` | _(no docstring)_ |
| `test_empty_tenant_id_rejected` | `py/tests/test_db_client.py:82` | _(no docstring)_ |
| `test_sets_current_tenant_via_set_config` | `py/tests/test_db_client.py:91` | _(no docstring)_ |
| `test_no_set_config_call` | `py/tests/test_db_client.py:126` | _(no docstring)_ |
| `test_to_dict_with_record` | `py/tests/test_db_client.py:152` | _(no docstring)_ |
| `test_to_dict_with_none` | `py/tests/test_db_client.py:158` | _(no docstring)_ |
| `test_init_stores_db` | `py/tests/test_db_client.py:162` | _(no docstring)_ |
| `test_success_rate_normal` | `py/tests/test_dispatch_pool.py:29` | _(no docstring)_ |
| `test_success_rate_zero_submitted_no_div_zero` | `py/tests/test_dispatch_pool.py:33` | _(no docstring)_ |
| `test_dataclass_default_error_none` | `py/tests/test_dispatch_pool.py:41` | _(no docstring)_ |
| `test_max_parallel_must_be_positive` | `py/tests/test_dispatch_pool.py:49` | _(no docstring)_ |
| `test_empty_task_list_short_circuits` | `py/tests/test_dispatch_pool.py:57` | _(no docstring)_ |
| `test_results_in_submission_order` | `py/tests/test_dispatch_pool.py:69` | _(no docstring)_ |
| `test_per_task_error_isolation` | `py/tests/test_dispatch_pool.py:84` | _(no docstring)_ |
| `test_per_task_timeout_enforced` | `py/tests/test_dispatch_pool.py:108` | _(no docstring)_ |
| `test_max_parallel_capped` | `py/tests/test_dispatch_pool.py:121` | _(no docstring)_ |
| `test_roundtrip` | `py/tests/test_embedding_cache.py:43` | _(no docstring)_ |
| `test_bytes_misaligned_raises` | `py/tests/test_embedding_cache.py:50` | _(no docstring)_ |
| `test_empty_roundtrip` | `py/tests/test_embedding_cache.py:56` | _(no docstring)_ |
| `test_hit_rate_normal` | `py/tests/test_embedding_cache.py:63` | _(no docstring)_ |
| `test_hit_rate_zero_total_no_div_zero` | `py/tests/test_embedding_cache.py:67` | _(no docstring)_ |
| `test_empty_model_rejected` | `py/tests/test_embedding_cache.py:75` | _(no docstring)_ |
| `test_model_property` | `py/tests/test_embedding_cache.py:80` | _(no docstring)_ |
| `test_miss_returns_none_increments_misses` | `py/tests/test_embedding_cache.py:87` | _(no docstring)_ |
| `test_hit_returns_vector_increments_hits` | `py/tests/test_embedding_cache.py:97` | _(no docstring)_ |
| `test_put_calls_setex_with_packed_bytes` | `py/tests/test_embedding_cache.py:108` | _(no docstring)_ |
| `test_put_skips_empty_vector` | `py/tests/test_embedding_cache.py:119` | _(no docstring)_ |
| `test_get_connection_error_fails_open` | `py/tests/test_embedding_cache.py:130` | _(no docstring)_ |
| `test_get_timeout_fails_open` | `py/tests/test_embedding_cache.py:139` | _(no docstring)_ |
| `test_put_connection_error_fails_open` | `py/tests/test_embedding_cache.py:146` | _(no docstring)_ |
| `test_corrupt_bytes_treated_as_miss` | `py/tests/test_embedding_cache.py:154` | _(no docstring)_ |
| `test_empty_tenant_id_rejected_on_get` | `py/tests/test_embedding_cache.py:166` | _(no docstring)_ |
| `test_empty_tenant_id_rejected_on_put` | `py/tests/test_embedding_cache.py:173` | _(no docstring)_ |
| `test_empty_tenant_id_rejected_on_invalidate` | `py/tests/test_embedding_cache.py:179` | _(no docstring)_ |
| `test_different_models_different_keys` | `py/tests/test_embedding_cache.py:187` | _(no docstring)_ |
| `test_invalidate_tenant_scans_and_deletes` | `py/tests/test_embedding_cache.py:206` | _(no docstring)_ |
| `test_empty_string_key_rejected` | `py/tests/test_encryption.py:38` | _(no docstring)_ |
| `test_empty_bytes_key_rejected` | `py/tests/test_encryption.py:42` | _(no docstring)_ |
| `test_invalid_fernet_key_rejected` | `py/tests/test_encryption.py:46` | _(no docstring)_ |
| `test_str_key_accepted` | `py/tests/test_encryption.py:50` | _(no docstring)_ |
| `test_bytes_key_accepted` | `py/tests/test_encryption.py:53` | _(no docstring)_ |
| `test_simple_string` | `py/tests/test_encryption.py:61` | _(no docstring)_ |
| `test_empty_string` | `py/tests/test_encryption.py:65` | _(no docstring)_ |
| `test_unicode` | `py/tests/test_encryption.py:68` | _(no docstring)_ |
| `test_long_payload` | `py/tests/test_encryption.py:72` | _(no docstring)_ |
| `test_output_has_sentinel_prefix` | `py/tests/test_encryption.py:76` | _(no docstring)_ |
| `test_two_encryptions_of_same_input_differ` | `py/tests/test_encryption.py:79` | _(no docstring)_ |
| `test_legacy_plaintext_passes_through` | `py/tests/test_encryption.py:93` | _(no docstring)_ |
| `test_empty_string_passes_through` | `py/tests/test_encryption.py:97` | _(no docstring)_ |
| `test_corrupt_sentinel_payload_returns_marker` | `py/tests/test_encryption.py:100` | _(no docstring)_ |
| `test_wrong_key_returns_marker` | `py/tests/test_encryption.py:105` | _(no docstring)_ |
| `test_partial_sentinel_treated_as_plaintext` | `py/tests/test_encryption.py:113` | _(no docstring)_ |
| `test_returns_string` | `py/tests/test_encryption.py:123` | _(no docstring)_ |
| `test_key_is_valid_for_cipher` | `py/tests/test_encryption.py:126` | _(no docstring)_ |
| `test_two_calls_return_different_keys` | `py/tests/test_encryption.py:131` | _(no docstring)_ |
| `test_key_length_is_fernet_standard` | `py/tests/test_encryption.py:136` | _(no docstring)_ |
| `test_no_env_no_arg_returns_false` | `py/tests/test_error_tracking.py:37` | _(no docstring)_ |
| `test_empty_env_returns_false` | `py/tests/test_error_tracking.py:42` | _(no docstring)_ |
| `test_whitespace_env_returns_false` | `py/tests/test_error_tracking.py:46` | _(no docstring)_ |
| `test_dsn_argument_initializes` | `py/tests/test_error_tracking.py:52` | _(no docstring)_ |
| `test_env_dsn_initializes` | `py/tests/test_error_tracking.py:60` | _(no docstring)_ |
| `test_explicit_dsn_overrides_env` | `py/tests/test_error_tracking.py:65` | _(no docstring)_ |
| `test_double_init_returns_false` | `py/tests/test_error_tracking.py:72` | _(no docstring)_ |
| `test_noop_before_init` | `py/tests/test_error_tracking.py:81` | _(no docstring)_ |
| `test_sets_tag_after_init` | `py/tests/test_error_tracking.py:86` | _(no docstring)_ |
| `test_no_tenant_no_user_safe` | `py/tests/test_error_tracking.py:96` | _(no docstring)_ |
| `test_returns_none_before_init` | `py/tests/test_error_tracking.py:107` | _(no docstring)_ |
| `test_captures_after_init_with_extras` | `py/tests/test_error_tracking.py:113` | _(no docstring)_ |
| `test_false_initially` | `py/tests/test_error_tracking.py:129` | _(no docstring)_ |
| `test_true_after_successful_init` | `py/tests/test_error_tracking.py:132` | _(no docstring)_ |
| `test_false_after_skipped_init` | `py/tests/test_error_tracking.py:137` | _(no docstring)_ |
| `test_defaults` | `py/tests/test_exceptions.py:31` | _(no docstring)_ |
| `test_per_raise_error_code_override` | `py/tests/test_exceptions.py:38` | _(no docstring)_ |
| `test_per_raise_http_status_override` | `py/tests/test_exceptions.py:43` | _(no docstring)_ |
| `test_details_passed_through` | `py/tests/test_exceptions.py:48` | _(no docstring)_ |
| `test_to_dict_envelope` | `py/tests/test_exceptions.py:52` | _(no docstring)_ |
| `test_4xx_codes` | `py/tests/test_exceptions.py:67` | _(no docstring)_ |
| `test_5xx_codes` | `py/tests/test_exceptions.py:80` | _(no docstring)_ |
| `test_is_external_service_error` | `py/tests/test_exceptions.py:94` | _(no docstring)_ |
| `test_default_message` | `py/tests/test_exceptions.py:104` | _(no docstring)_ |
| `test_retry_after_seconds_stamped_into_details` | `py/tests/test_exceptions.py:108` | _(no docstring)_ |
| `test_retry_after_seconds_omitted` | `py/tests/test_exceptions.py:112` | _(no docstring)_ |
| `test_details_merged_with_retry_after` | `py/tests/test_exceptions.py:118` | _(no docstring)_ |
| `test_empty_input` | `py/tests/test_fusion.py:27` | _(no docstring)_ |
| `test_single_ranking_preserves_order` | `py/tests/test_fusion.py:30` | _(no docstring)_ |
| `test_overlap_boosts_score` | `py/tests/test_fusion.py:36` | _(no docstring)_ |
| `test_empty_list_among_others_is_no_op` | `py/tests/test_fusion.py:44` | _(no docstring)_ |
| `test_large_k_flattens` | `py/tests/test_fusion.py:50` | _(no docstring)_ |
| `test_weight_amplifies_list` | `py/tests/test_fusion.py:62` | _(no docstring)_ |
| `test_mismatched_weights_raises` | `py/tests/test_fusion.py:71` | _(no docstring)_ |
| `test_zero_weight_excludes_list` | `py/tests/test_fusion.py:80` | _(no docstring)_ |
| `test_basic` | `py/tests/test_fusion.py:89` | _(no docstring)_ |
| `test_k_larger_than_n_returns_all` | `py/tests/test_fusion.py:95` | _(no docstring)_ |
| `test_empty_input` | `py/tests/test_fusion.py:100` | _(no docstring)_ |
| `test_k_one` | `py/tests/test_fusion.py:103` | _(no docstring)_ |
| `test_k_zero_raises` | `py/tests/test_fusion.py:108` | _(no docstring)_ |
| `test_k_negative_raises` | `py/tests/test_fusion.py:114` | _(no docstring)_ |
| `test_score_fn_called_once_per_item` | `py/tests/test_fusion.py:118` | _(no docstring)_ |
| `test_tied_scores_dont_compare_items` | `py/tests/test_fusion.py:131` | _(no docstring)_ |
| `test_frozen` | `py/tests/test_fusion.py:144` | _(no docstring)_ |
| `test_dataclass_fields` | `py/tests/test_idempotency.py:35` | _(no docstring)_ |
| `test_namespaces_by_tenant_route_key` | `py/tests/test_idempotency.py:42` | _(no docstring)_ |
| `test_different_tenants_get_different_keys` | `py/tests/test_idempotency.py:48` | _(no docstring)_ |
| `test_miss_returns_none` | `py/tests/test_idempotency.py:56` | _(no docstring)_ |
| `test_hit_returns_stored_response` | `py/tests/test_idempotency.py:64` | _(no docstring)_ |
| `test_bad_json_returns_none` | `py/tests/test_idempotency.py:74` | _(no docstring)_ |
| `test_missing_required_field_returns_none` | `py/tests/test_idempotency.py:83` | _(no docstring)_ |
| `test_write_uses_setex_with_ttl` | `py/tests/test_idempotency.py:95` | _(no docstring)_ |
| `test_default_str_fallback_for_datetime` | `py/tests/test_idempotency.py:108` | _(no docstring)_ |
| `test_get_passes_through` | `py/tests/test_idempotency_middleware.py:85` | _(no docstring)_ |
| `test_post_without_key_passes_through` | `py/tests/test_idempotency_middleware.py:94` | _(no docstring)_ |
| `test_post_without_tenant_passes_through` | `py/tests/test_idempotency_middleware.py:103` | _(no docstring)_ |
| `test_first_request_runs_handler_and_stores` | `py/tests/test_idempotency_middleware.py:115` | _(no docstring)_ |
| `test_cache_hit_skips_handler_returns_replay` | `py/tests/test_idempotency_middleware.py:136` | _(no docstring)_ |
| `test_5xx_response_not_cached` | `py/tests/test_idempotency_middleware.py:156` | _(no docstring)_ |
| `test_4xx_response_is_cached` | `py/tests/test_idempotency_middleware.py:169` | _(no docstring)_ |
| `test_json_body_round_trips` | `py/tests/test_idempotency_middleware.py:184` | _(no docstring)_ |
| `test_no_context_set_passes_through` | `py/tests/test_logging_config.py:48` | _(no docstring)_ |
| `test_correlation_stamped_when_set` | `py/tests/test_logging_config.py:54` | _(no docstring)_ |
| `test_all_three_stamped` | `py/tests/test_logging_config.py:59` | _(no docstring)_ |
| `test_explicit_event_field_wins` | `py/tests/test_logging_config.py:66` | _(no docstring)_ |
| `test_no_active_span_passes_through` | `py/tests/test_logging_config.py:77` | _(no docstring)_ |
| `test_active_span_stamps_ids` | `py/tests/test_logging_config.py:83` | _(no docstring)_ |
| `test_invalid_span_context_skipped` | `py/tests/test_logging_config.py:93` | _(no docstring)_ |
| `test_baggage_keys_added_when_absent` | `py/tests/test_logging_config.py:106` | _(no docstring)_ |
| `test_existing_keys_not_overwritten` | `py/tests/test_logging_config.py:112` | _(no docstring)_ |
| `test_empty_baggage_is_noop` | `py/tests/test_logging_config.py:118` | _(no docstring)_ |
| `test_event_renamed` | `py/tests/test_logging_config.py:128` | _(no docstring)_ |
| `test_no_event_field_unchanged` | `py/tests/test_logging_config.py:132` | _(no docstring)_ |
| `test_json_format_default` | `py/tests/test_logging_config.py:145` | _(no docstring)_ |
| `test_dev_console_renderer` | `py/tests/test_logging_config.py:152` | _(no docstring)_ |
| `test_noisy_libraries_quieted` | `py/tests/test_logging_config.py:157` | _(no docstring)_ |
| `test_idempotent` | `py/tests/test_logging_config.py:162` | _(no docstring)_ |
| `test_lowercase_level_accepted` | `py/tests/test_logging_config.py:168` | _(no docstring)_ |
| `test_returns_bound_logger` | `py/tests/test_logging_config.py:178` | _(no docstring)_ |
| `test_bind_only_correlation` | `py/tests/test_logging_config.py:196` | _(no docstring)_ |
| `test_bind_full_context` | `py/tests/test_logging_config.py:203` | _(no docstring)_ |
| `test_clear_resets_all` | `py/tests/test_logging_config.py:209` | _(no docstring)_ |
| `test_empty_query_similarity` | `py/tests/test_mmr.py:24` | _(no docstring)_ |
| `test_k_one` | `py/tests/test_mmr.py:27` | _(no docstring)_ |
| `test_k_larger_than_n` | `py/tests/test_mmr.py:36` | _(no docstring)_ |
| `test_lambda_one_pure_relevance` | `py/tests/test_mmr.py:47` | _(no docstring)_ |
| `test_lambda_balanced_picks_diverse` | `py/tests/test_mmr.py:59` | _(no docstring)_ |
| `test_lambda_zero_pure_diversity` | `py/tests/test_mmr.py:72` | _(no docstring)_ |
| `test_k_zero_raises` | `py/tests/test_mmr.py:89` | _(no docstring)_ |
| `test_lambda_negative_raises` | `py/tests/test_mmr.py:93` | _(no docstring)_ |
| `test_lambda_above_one_raises` | `py/tests/test_mmr.py:97` | _(no docstring)_ |
| `test_pairwise_wrong_outer_size_raises` | `py/tests/test_mmr.py:101` | _(no docstring)_ |
| `test_pairwise_wrong_inner_size_raises` | `py/tests/test_mmr.py:105` | _(no docstring)_ |
| `test_valid_visa` | `py/tests/test_pii.py:30` | _(no docstring)_ |
| `test_invalid_random_digits` | `py/tests/test_pii.py:35` | _(no docstring)_ |
| `test_too_short` | `py/tests/test_pii.py:38` | _(no docstring)_ |
| `test_empty` | `py/tests/test_pii.py:41` | _(no docstring)_ |
| `test_strips_non_digits` | `py/tests/test_pii.py:44` | _(no docstring)_ |
| `test_non_digit_only_returns_false` | `py/tests/test_pii.py:49` | _(no docstring)_ |
| `test_simple_email` | `py/tests/test_pii.py:54` | _(no docstring)_ |
| `test_subaddress_form` | `py/tests/test_pii.py:61` | _(no docstring)_ |
| `test_valid_ssn` | `py/tests/test_pii.py:67` | _(no docstring)_ |
| `test_rejects_invalid_area_codes` | `py/tests/test_pii.py:71` | _(no docstring)_ |
| `test_us_formats_detected` | `py/tests/test_pii.py:78` | _(no docstring)_ |
| `test_luhn_valid_card_detected` | `py/tests/test_pii.py:86` | _(no docstring)_ |
| `test_luhn_invalid_filtered_out` | `py/tests/test_pii.py:91` | _(no docstring)_ |
| `test_disable_luhn_check` | `py/tests/test_pii.py:97` | _(no docstring)_ |
| `test_aws_access_key` | `py/tests/test_pii.py:106` | _(no docstring)_ |
| `test_rsa_private_key_header` | `py/tests/test_pii.py:110` | _(no docstring)_ |
| `test_api_key_token` | `py/tests/test_pii.py:114` | _(no docstring)_ |
| `test_ipv4_detected` | `py/tests/test_pii.py:120` | _(no docstring)_ |
| `test_redact_replaces_pii` | `py/tests/test_pii.py:126` | _(no docstring)_ |
| `test_redact_preserves_non_pii` | `py/tests/test_pii.py:133` | _(no docstring)_ |
| `test_redact_no_pii_returns_unchanged` | `py/tests/test_pii.py:139` | _(no docstring)_ |
| `test_redact_with_labels` | `py/tests/test_pii.py:144` | _(no docstring)_ |
| `test_has_pii_short_circuits` | `py/tests/test_pii.py:152` | _(no docstring)_ |
| `test_empty_input` | `py/tests/test_pii.py:158` | _(no docstring)_ |
| `test_default_patterns_locked` | `py/tests/test_pii.py:164` | _(no docstring)_ |
| `test_custom_pattern_detected` | `py/tests/test_pii.py:182` | _(no docstring)_ |
| `test_pii_match_is_frozen` | `py/tests/test_pii.py:190` | _(no docstring)_ |
| `test_offsets_correct` | `py/tests/test_pii.py:198` | _(no docstring)_ |
| `test_frozen` | `py/tests/test_query_rewriter.py:27` | _(no docstring)_ |
| `test_lowercase` | `py/tests/test_query_rewriter.py:39` | _(no docstring)_ |
| `test_whitespace_collapse` | `py/tests/test_query_rewriter.py:43` | _(no docstring)_ |
| `test_curly_quotes_normalized` | `py/tests/test_query_rewriter.py:47` | _(no docstring)_ |
| `test_normalize_false_keeps_case` | `py/tests/test_query_rewriter.py:52` | _(no docstring)_ |
| `test_simple_expansion` | `py/tests/test_query_rewriter.py:58` | _(no docstring)_ |
| `test_word_boundary_safe` | `py/tests/test_query_rewriter.py:63` | _(no docstring)_ |
| `test_multiple_expansions_one_query` | `py/tests/test_query_rewriter.py:69` | _(no docstring)_ |
| `test_no_match_no_expansion_recorded` | `py/tests/test_query_rewriter.py:75` | _(no docstring)_ |
| `test_case_insensitive_match` | `py/tests/test_query_rewriter.py:79` | _(no docstring)_ |
| `test_acronym_detected` | `py/tests/test_query_rewriter.py:87` | _(no docstring)_ |
| `test_acronyms_deduplicated` | `py/tests/test_query_rewriter.py:92` | _(no docstring)_ |
| `test_lowercase_text_no_acronyms` | `py/tests/test_query_rewriter.py:97` | _(no docstring)_ |
| `test_single_letter_not_acronym` | `py/tests/test_query_rewriter.py:101` | _(no docstring)_ |
| `test_word_with_caps_inside_not_acronym` | `py/tests/test_query_rewriter.py:107` | _(no docstring)_ |
| `test_acronym_detected_before_normalization` | `py/tests/test_query_rewriter.py:112` | _(no docstring)_ |
| `test_empty_query` | `py/tests/test_query_rewriter.py:123` | _(no docstring)_ |
| `test_tenant_key_format` | `py/tests/test_rate_limiter.py:66` | _(no docstring)_ |
| `test_ip_key_format` | `py/tests/test_rate_limiter.py:69` | _(no docstring)_ |
| `test_keys_are_distinct_namespaces` | `py/tests/test_rate_limiter.py:72` | _(no docstring)_ |
| `test_dataclass_fields` | `py/tests/test_rate_limiter.py:83` | _(no docstring)_ |
| `test_registers_script` | `py/tests/test_rate_limiter.py:95` | _(no docstring)_ |
| `test_allowed_returns_decremented_remaining` | `py/tests/test_rate_limiter.py:112` | _(no docstring)_ |
| `test_allowed_with_zero_current_remaining_full` | `py/tests/test_rate_limiter.py:122` | _(no docstring)_ |
| `test_allowed_remaining_clamped_to_zero` | `py/tests/test_rate_limiter.py:130` | _(no docstring)_ |
| `test_denied_with_zero_oldest_uses_full_window` | `py/tests/test_rate_limiter.py:139` | _(no docstring)_ |
| `test_denied_reset_calculated_from_oldest` | `py/tests/test_rate_limiter.py:149` | _(no docstring)_ |
| `test_cost_greater_than_one_passed_through` | `py/tests/test_rate_limiter.py:159` | _(no docstring)_ |
| `test_redis_connection_error_fails_open` | `py/tests/test_rate_limiter.py:173` | _(no docstring)_ |
| `test_redis_timeout_fails_open` | `py/tests/test_rate_limiter.py:182` | _(no docstring)_ |
| `test_os_error_fails_open` | `py/tests/test_rate_limiter.py:189` | _(no docstring)_ |
| `test_unrelated_exceptions_propagate` | `py/tests/test_rate_limiter.py:196` | _(no docstring)_ |
| `test_passthrough_on_allowed` | `py/tests/test_rate_limiter.py:210` | _(no docstring)_ |
| `test_raises_on_denied` | `py/tests/test_rate_limiter.py:216` | _(no docstring)_ |
| `test_raised_error_includes_key_in_details` | `py/tests/test_rate_limiter.py:226` | _(no docstring)_ |
| `test_cross_tenant_read_is_empty` | `py/tests/test_rls_isolation.py:47` | _(no docstring)_ |
| `test_minimal_payload` | `py/tests/test_schemas.py:26` | _(no docstring)_ |
| `test_correlation_id_passes_through` | `py/tests/test_schemas.py:31` | _(no docstring)_ |
| `test_generic_dict_data` | `py/tests/test_schemas.py:35` | _(no docstring)_ |
| `test_basic` | `py/tests/test_schemas.py:41` | _(no docstring)_ |
| `test_has_more_flag` | `py/tests/test_schemas.py:46` | _(no docstring)_ |
| `test_negative_offset_rejected` | `py/tests/test_schemas.py:50` | _(no docstring)_ |
| `test_negative_total_rejected` | `py/tests/test_schemas.py:54` | _(no docstring)_ |
| `test_limit_zero_rejected` | `py/tests/test_schemas.py:58` | _(no docstring)_ |
| `test_limit_above_500_rejected` | `py/tests/test_schemas.py:64` | _(no docstring)_ |
| `test_default_details_is_empty_dict` | `py/tests/test_schemas.py:71` | _(no docstring)_ |
| `test_with_details` | `py/tests/test_schemas.py:76` | _(no docstring)_ |
| `test_minimal` | `py/tests/test_schemas.py:87` | _(no docstring)_ |
| `test_with_checks` | `py/tests/test_schemas.py:92` | _(no docstring)_ |
| `test_split_on_whitespace` | `py/tests/test_tokens.py:29` | _(no docstring)_ |
| `test_empty` | `py/tests/test_tokens.py:32` | _(no docstring)_ |
| `test_default` | `py/tests/test_tokens.py:37` | _(no docstring)_ |
| `test_empty` | `py/tests/test_tokens.py:40` | _(no docstring)_ |
| `test_custom_tokenizer` | `py/tests/test_tokens.py:44` | _(no docstring)_ |
| `test_basic_pack` | `py/tests/test_tokens.py:53` | _(no docstring)_ |
| `test_separator_counted_between_fragments` | `py/tests/test_tokens.py:65` | _(no docstring)_ |
| `test_first_fragment_no_separator_cost` | `py/tests/test_tokens.py:79` | _(no docstring)_ |
| `test_budget_zero_rejected` | `py/tests/test_tokens.py:89` | _(no docstring)_ |
| `test_oversized_fragment_excluded` | `py/tests/test_tokens.py:93` | _(no docstring)_ |
| `test_empty_fragments_skipped` | `py/tests/test_tokens.py:103` | _(no docstring)_ |
| `test_greedy_stops_at_first_overflow` | `py/tests/test_tokens.py:112` | _(no docstring)_ |

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
| `documind_core/exceptions` | 7 | _reviewer-described_ |
| `documind_core/cache` | 3 | _reviewer-described_ |
| `documind_core/fusion` | 2 | _reviewer-described_ |
| `documind_core/idempotency` | 2 | _reviewer-described_ |
| `documind_core/ai_governance` | 1 | _reviewer-described_ |
| `documind_core/audit` | 1 | _reviewer-described_ |
| `documind_core/bm25` | 1 | _reviewer-described_ |
| `documind_core/body_limit` | 1 | _reviewer-described_ |
| `documind_core/breakers` | 1 | _reviewer-described_ |
| `documind_core/circuit_breaker` | 1 | _reviewer-described_ |
| `documind_core/chunking` | 1 | _reviewer-described_ |
| `documind_core/citations` | 1 | _reviewer-described_ |
| `documind_core/config` | 1 | _reviewer-described_ |
| `documind_core/db_client` | 1 | _reviewer-described_ |
| `documind_core/dispatch_pool` | 1 | _reviewer-described_ |
| `documind_core/embedding_cache` | 1 | _reviewer-described_ |
| `documind_core/encryption` | 1 | _reviewer-described_ |
| `documind_core/error_tracking` | 1 | _reviewer-described_ |
| `documind_core/idempotency_middleware` | 1 | _reviewer-described_ |
| `documind_core/logging_config` | 1 | _reviewer-described_ |
| `documind_core/mmr` | 1 | _reviewer-described_ |
| `documind_core/pii` | 1 | _reviewer-described_ |
| `documind_core/query_rewriter` | 1 | _reviewer-described_ |
| `documind_core/rate_limiter` | 1 | _reviewer-described_ |
| `documind_core/schemas` | 1 | _reviewer-described_ |
| `documind_core/tokens` | 1 | _reviewer-described_ |

### External — third-party packages

| Package | Import-count |
|---|---|
| `pytest` | 25 |
| `opentelemetry` | 23 |
| `fastapi` | 11 |
| `exceptions` | 10 |
| `starlette` | 10 |
| `unittest` | 9 |
| `redis` | 8 |
| `prometheus_client` | 7 |
| `pydantic` | 6 |
| `structlog` | 4 |
| `sentry_sdk` | 3 |
| `rebuff` | 3 |
| `breakers` | 2 |
| `circuit_breaker` | 2 |
| `asyncpg` | 2 |
| `ai_governance` | 1 |
| `body_limit` | 1 |
| `idempotency_middleware` | 1 |
| `jwt` | 1 |
| `rank_bm25` | 1 |


## 18. Debugging Guide

### Step-by-step when something breaks

```
1. Tail logs:        tail -50 /tmp/libs.log   (if host-side)
                     docker logs documind-libs --tail=50   (if container)
2. Health probe:     curl http://localhost:<PORT>/health
3. Fleet probe:      python3 scripts/advanced_healthcheck.py --layer app
4. Trace:            Open Jaeger → search request_id → see span tree
5. Metrics:          Open Grafana → service dashboard → look for spike
6. Drill:            ls mcp/tests/drill_*libs*.py and run
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
| No memory leaks | bounded caches | — | smells: 8 |
| No N+1 queries | hot paths reviewed | — | 19 DB call sites |
| All APIs validated | Pydantic / Zod | — | sanitization: Manual escape, Pydantic BaseModel |
| Duplicate logic eliminated | DRY check | — | — |
| Structured logging with correlation_id | — | — | — |
| Distributed tracing wired | OpenTelemetry | — | — |
| For AI: prompt injection tested | Rebuff / Garak | — | AI deps present |
| For AI: hallucination scoring ≥ 0.85 | Ragas faithfulness | — | n/a |


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
