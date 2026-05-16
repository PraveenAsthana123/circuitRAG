# 📦 `ingestion-svc` — Advanced README

🧩 **Service**  ·  **Path:** `services/ingestion-svc`  ·  **Generated:** 2026-05-16 20:22 UTC

> Ingestion-service FastAPI application.

This README is **auto-generated** by [`scripts/generate_folder_report.py`](../../scripts/generate_folder_report.py). It explains what this folder does, every file inside it, how the files link to each other, every API endpoint, every database call, every test case, and the production controls (security / reliability / performance / observability). Re-run after major changes.

---

## 🔎 Section 0 — Auto-Detected Facts

| Metric | Value |
|---|---|
| Folder | `services/ingestion-svc` |
| Total files | 50 |
| Python files | 42 |
| TypeScript/JS files | 0 |
| Go files | 0 |
| Shell scripts | 0 |
| Lines of code | 3,323 |
| Python classes | 41 |
| Python functions | 135 |
| Async functions | 71 |
| Total API endpoints | 7 |
| Total DB call sites | 42 |
| DB / Storage libs | Neo4j, Qdrant, Redis, asyncpg |
| Concurrency primitives | asyncio (async/await) |
| Caching primitives | in-memory @lru_cache, redis |
| Input validation | Manual escape, Pydantic BaseModel |
| AI / LLM deps | Ollama |
| Test files | 1 |
| Detected test cases | 7 |
| Tests dir present | ✅ |
| Dockerfile | ✅ |
| pyproject.toml | ❌ |
| go.mod | ❌ |
| package.json | ❌ |
| Top git contributors | `11	PraveenAsthana123`, `4	Praveen` |

#### Longest functions (top 5)

| Location | Name | Lines |
|---|---|---|
| `app/main.py:55` | `create_app` | 182 |
| `app/saga/document_saga.py:294` | `_step_chunk` | 143 |
| `app/saga/recovery.py:84` | `_compensate` | 86 |
| `app/saga/document_saga.py:138` | `run` | 82 |
| `app/saga/reembed_worker.py:75` | `_run_once` | 76 |

#### Smells detected

_(no smells detected by grep)_


## 1. Purpose — Business + Technical

### Business problem this folder solves

> _Reviewer to fill: Ingestion-service FastAPI application._

### Technical contract this folder exposes

> _Reviewer to fill: API surface, events emitted, data persisted, downstream consumers._

### Out-of-scope (what this folder does NOT do)

> _Reviewer to fill: explicit non-goals — prevents scope creep at review time._


## ⚡ Quick Start (5 commands)

```bash
# 1. From repo root, activate venv
source .venv/bin/activate

# 2. Bring up backends this service depends on (Postgres / Redis / Kafka / etc.)
docker compose -f infra/docker-compose.yml up -d postgres redis kafka

# 3. Set the env vars (see §C below for the full list)
export DOCUMIND_POSTGRES_URL='postgresql://...'
export DOCUMIND_REDIS_URL='redis://localhost:56379/0'

# 4. Start the service
cd services/ingestion-svc
uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload

# 5. Verify
curl http://localhost:8082/health
```

If `/health` returns `{"status": "ok"}` you're up. Full health matrix: `python3 scripts/advanced_healthcheck.py --layer app`.


## 🗺 How to Read This Folder (Guided Tour)

Read these files in order — by the end, you'll understand 80% of this folder's behavior. Click any path to jump straight to the source.

1. **`app/main.py`** (🚀 entry point / app bootstrap, 240 LOC) — App boot wiring — middleware stack, router registration, lifespan startup, DI container setup.
2. **`app/core/config.py`** (⚙ config / settings, 29 LOC) — Every env var the service reads. Read this BEFORE running locally.
3. **`app/routers/documents.py`** (🌐 HTTP router / API endpoints, 112 LOC) — All HTTP routes. Most lines here are decorators + Pydantic models — the actual logic delegates to services.
4. **`app/routers/health.py`** (🌐 HTTP router / API endpoints, 47 LOC) — All HTTP routes. Most lines here are decorators + Pydantic models — the actual logic delegates to services.
5. **`app/schemas/document.py`** (📋 data model / schema, 54 LOC) — Pydantic request/response models. Read alongside the router.
6. **`app/schemas/__init__.py`** (📋 data model / schema, 16 LOC) — Pydantic request/response models. Read alongside the router.
7. **`app/services/ingestion_service.py`** (🧠 business service / use-case, 200 LOC) — Where business logic lives. Most of the interesting code is here.
8. **`app/services/pii_hook.py`** (🧠 business service / use-case, 189 LOC) — Where business logic lives. Most of the interesting code is here.

Click absolute paths for direct `cat`-ability in the §2 File Inventory above.


## ⚙ Environment Variables

All env vars this folder reads, auto-extracted from `BaseSettings` field declarations and `os.environ.get` calls.

### Runtime `os.environ.get` / `os.getenv` calls

| Variable | Default | Source location |
|---|---|---|
| `PII_REDACTOR_ENABLED` | **required** | `app/saga/document_saga.py:311` |
| `PII_REDACTOR_ENABLED` | **required** | `app/services/pii_hook.py:87` |

_Variables marked **required** must be set — missing values may raise on startup or silently default to empty strings._


## 2. File Inventory

Every Python file in this folder, with role / classes / functions / LOC / first docstring line. Full absolute paths listed below the table for easy `cat`-ability.

| Relative path | Role (inferred) | Classes | Functions | LOC | Summary |
|---|---|---|---|---|---|
| `app/chunking/__init__.py` | 📦 package marker | 0 | 0 | 23 | Chunking (Design Area 23 — Ingestion, Area 34 — Retrieval Schema). |
| `app/chunking/base.py` | 📄 module | 2 | 0 | 47 | Chunker interface + Chunk domain model. |
| `app/chunking/recursive.py` | 📄 module | 2 | 0 | 231 | Recursive character-based chunker. |
| `app/chunking/token_counter.py` | 📄 module | 1 | 0 | 42 | Token counting — central so every service agrees on what "512 tokens" means. |
| `app/core/config.py` | ⚙ config / settings | 1 | 0 | 29 | Ingestion-service configuration (subclasses the shared base). |
| `app/embedding/__init__.py` | 📦 package marker | 0 | 0 | 14 | Embedding providers (Design Area 39 — Embedding Lifecycle, Area 65 — |
| `app/embedding/base.py` | 📄 module | 1 | 0 | 36 | The EmbeddingProvider interface. |
| `app/embedding/ollama_embedder.py` | 📄 module | 1 | 0 | 86 | Ollama-backed embedder. |
| `app/main.py` | 🚀 entry point / app bootstrap | 0 | 1 | 240 | Ingestion-service FastAPI application. |
| `app/parsers/__init__.py` | 📦 package marker | 0 | 0 | 41 | Document parsers (Design Area 23 — Knowledge Ingestion, Design Area 65 — |
| `app/parsers/base.py` | 📄 module | 3 | 0 | 52 | Parser interface (Design Area 65 — Design-for-Change). |
| `app/parsers/docx_parser.py` | 📄 module | 1 | 0 | 51 | DOCX parser built on :mod:`python-docx`. |
| `app/parsers/html_parser.py` | 📄 module | 1 | 0 | 54 | HTML parser built on BeautifulSoup. |
| `app/parsers/markdown_parser.py` | 📄 module | 1 | 0 | 24 | Markdown parser — renders to HTML then reuses HtmlParser. One code path |
| `app/parsers/pdf_parser.py` | 📄 module | 1 | 0 | 47 | PDF parser built on :mod:`pypdf`. |
| `app/parsers/registry.py` | 📄 module | 1 | 0 | 48 | Parser registry — picks the right parser by file extension. |
| `app/parsers/text_parser.py` | 📄 module | 1 | 0 | 24 | Plain-text parser (.txt). No structure beyond paragraphs. |
| `app/repositories/__init__.py` | 💾 repository / data access | 0 | 0 | 29 | Repositories (Design Areas 46 — DB Strategy, 47 — Vector DB, 48 — Graph). |
| `app/repositories/chunk_repo.py` | 💾 repository / data access | 1 | 0 | 111 | Chunk metadata repository (Postgres, ingestion schema). |
| `app/repositories/document_repo.py` | 💾 repository / data access | 1 | 0 | 248 | Document metadata repository (Postgres, ingestion schema). |
| `app/repositories/neo4j_repo.py` | 💾 repository / data access | 1 | 0 | 132 | Neo4j repository (Design Area 48 — Graph Strategy). |
| `app/repositories/qdrant_repo.py` | 💾 repository / data access | 1 | 0 | 145 | Qdrant repository (Design Area 47 — Vector DB Strategy). |
| `app/repositories/saga_repo.py` | 💾 repository / data access | 1 | 0 | 112 | Saga persistence (Design Area 18 — Workflow Orchestration). |
| `app/routers/__init__.py` | 🌐 HTTP router / API endpoints | 0 | 0 | 5 | _(no docstring)_ |
| `app/routers/documents.py` | 🌐 HTTP router / API endpoints | 0 | 6 | 112 | Document HTTP routes (Design Area 23 — Ingestion Service API). |
| `app/routers/health.py` | 🌐 HTTP router / API endpoints | 0 | 3 | 47 | Health check endpoint — liveness + readiness (Design Area 49). |
| `app/saga/__init__.py` | 📦 package marker | 0 | 0 | 13 | _(no docstring)_ |
| `app/saga/document_saga.py` | 📄 module | 3 | 0 | 543 | Document ingestion saga (Design Areas 18 — Workflow Orchestration, |
| `app/saga/outbox.py` | 📄 module | 2 | 0 | 192 | Transactional outbox (Design Area 17). |
| `app/saga/recovery.py` | 📄 module | 1 | 0 | 170 | Saga crash recovery (Design Areas 18, 19). |
| `app/saga/reembed_worker.py` | 📄 module | 1 | 0 | 151 | Re-embed worker (Design Area 39 — Embedding Lifecycle). |
| `app/schemas/__init__.py` | 📋 data model / schema | 0 | 0 | 16 | _(no docstring)_ |
| `app/schemas/document.py` | 📋 data model / schema | 5 | 0 | 54 | Pydantic schemas (Design Area 30 — API Contracts). |
| `app/services/__init__.py` | 🧠 business service / use-case | 0 | 0 | 5 | _(no docstring)_ |
| `app/services/blob_service.py` | 🧠 business service / use-case | 1 | 0 | 81 | Blob storage wrapper (Design Areas 35 — Knowledge Lifecycle, 7 — Data Plane). |
| `app/services/ingestion_service.py` | 🧠 business service / use-case | 2 | 0 | 200 | IngestionService — business-logic wrapper over the saga orchestrator. |
| `app/services/pii_hook.py` | 🧠 business service / use-case | 1 | 4 | 189 | PII redaction hook for ingestion — Stage-2 adapter. |
| `app/services/poisoning_defense.py` | 🧠 business service / use-case | 3 | 0 | 172 | Retrieval-poisoning defense (Design Area 5 — Tenant Boundary, Extra E5 — Secure AI). |
| `tests/conftest.py` | 🧪 test | 0 | 1 | 21 | pytest config for ingestion-svc tests — adds the service's parent dir to path. |
| `tests/test_poisoning_defense.py` | 🧪 test | 0 | 8 | 82 | Tests for the retrieval-poisoning guard. |

### Absolute paths (clickable)

- `/mnt/deepa/rag/services/ingestion-svc/app/chunking/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/chunking/base.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/chunking/recursive.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/chunking/token_counter.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/core/config.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/embedding/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/embedding/base.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/embedding/ollama_embedder.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/main.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/base.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/docx_parser.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/html_parser.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/markdown_parser.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/pdf_parser.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/registry.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/parsers/text_parser.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/repositories/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/repositories/chunk_repo.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/repositories/document_repo.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/repositories/neo4j_repo.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/repositories/qdrant_repo.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/repositories/saga_repo.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/routers/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/routers/documents.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/routers/health.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/saga/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/saga/document_saga.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/saga/outbox.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/saga/recovery.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/saga/reembed_worker.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/schemas/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/schemas/document.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/services/__init__.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/services/blob_service.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/services/ingestion_service.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/services/pii_hook.py`
- `/mnt/deepa/rag/services/ingestion-svc/app/services/poisoning_defense.py`
- `/mnt/deepa/rag/services/ingestion-svc/tests/conftest.py`
- `/mnt/deepa/rag/services/ingestion-svc/tests/test_poisoning_defense.py`


## 🧭 Where Does X Live? (cheat sheet)

Use this table when you're modifying this folder and need to know where new code goes.

| I want to... | Role | Touch these files |
|---|---|---|
| Add a new HTTP endpoint | 🌐 HTTP router / API endpoints | `app/routers/__init__.py`, `app/routers/documents.py`, `app/routers/health.py` |
| Add a new Pydantic request/response model | 📋 data model / schema | `app/schemas/__init__.py`, `app/schemas/document.py` |
| Add a new business-logic method | 🧠 business service / use-case | `app/services/__init__.py`, `app/services/blob_service.py`, `app/services/ingestion_service.py` (+2 more) |
| Add a new SQL query or DB call | 💾 repository / data access | `app/repositories/__init__.py`, `app/repositories/chunk_repo.py`, `app/repositories/document_repo.py` (+3 more) |
| Add a new env var | ⚙ config / settings | `app/core/config.py` |
| Add a new test | 🧪 test | `tests/conftest.py`, `tests/test_poisoning_defense.py` |
| Boot a background worker | 🚀 entry point / app bootstrap | `app/main.py` |


## 3. C4 Model — Context / Container / Component / Code

### Level 1 — System Context

_Where does this folder sit in the broader system?_

```mermaid
flowchart LR
    Caller([External Caller]) --> This["ingestion-svc"]
    This --> app_parsers[app/parsers]
    This --> documind_core_config[documind_core/config]
    This --> documind_core_circuit_breaker[documind_core/circuit_breaker]
    This --> documind_core_exceptions[documind_core/exceptions]
    This --> documind_core_body_limit[documind_core/body_limit]
    This --> documind_core_db_client[documind_core/db_client]
```

### Level 2 — Container

_What external dependencies does this folder talk to?_

```mermaid
flowchart TB
    subgraph ingestion-svc
        Code[Source Code]
    end
    Code --> DB_0[("Neo4j")]
    Code --> DB_1[("Qdrant")]
    Code --> DB_2[("Redis")]
    Code --> DB_3[("asyncpg")]
    Code --> AI_0{{LLM: Ollama}}
```

### Level 3 — Component

_Internal files grouped by inferred role._

```mermaid
flowchart TB
    subgraph __package_marker["📦 package marker"]
        app_chunking___init___py["app/chunking/__init__.py"]
        app_embedding___init___py["app/embedding/__init__.py"]
        app_parsers___init___py["app/parsers/__init__.py"]
        app_saga___init___py["app/saga/__init__.py"]
    end
    subgraph __module["📄 module"]
        app_chunking_base_py["app/chunking/base.py"]
        app_chunking_recursive_py["app/chunking/recursive.py"]
        app_chunking_token_counter_py["app/chunking/token_counter.py"]
        app_embedding_base_py["app/embedding/base.py"]
        app_embedding_ollama_embedder_py["app/embedding/ollama_embedder.py"]
        app_parsers_base_py["app/parsers/base.py"]
        more___module["... +10 more"]
    end
    subgraph __config___settings["⚙ config / settings"]
        app_core_config_py["app/core/config.py"]
    end
    subgraph __entry_point___app_bootstrap["🚀 entry point / app bootstrap"]
        app_main_py["app/main.py"]
    end
    subgraph __repository___data_access["💾 repository / data access"]
        app_repositories___init___py["app/repositories/__init__.py"]
        app_repositories_chunk_repo_py["app/repositories/chunk_repo.py"]
        app_repositories_document_repo_py["app/repositories/document_repo.py"]
        app_repositories_neo4j_repo_py["app/repositories/neo4j_repo.py"]
        app_repositories_qdrant_repo_py["app/repositories/qdrant_repo.py"]
        app_repositories_saga_repo_py["app/repositories/saga_repo.py"]
    end
    subgraph __HTTP_router___API_endpoints["🌐 HTTP router / API endpoints"]
        app_routers___init___py["app/routers/__init__.py"]
        app_routers_documents_py["app/routers/documents.py"]
        app_routers_health_py["app/routers/health.py"]
    end
    subgraph __data_model___schema["📋 data model / schema"]
        app_schemas___init___py["app/schemas/__init__.py"]
        app_schemas_document_py["app/schemas/document.py"]
    end
    subgraph __business_service___use_case["🧠 business service / use-case"]
        app_services___init___py["app/services/__init__.py"]
        app_services_blob_service_py["app/services/blob_service.py"]
        app_services_ingestion_service_py["app/services/ingestion_service.py"]
        app_services_pii_hook_py["app/services/pii_hook.py"]
        app_services_poisoning_defense_py["app/services/poisoning_defense.py"]
    end
    subgraph __test["🧪 test"]
        tests_conftest_py["tests/conftest.py"]
        tests_test_poisoning_defense_py["tests/test_poisoning_defense.py"]
    end
```

### Level 4 — Code (top hotspots)

_Longest functions — these are the most likely refactor candidates._

```mermaid
flowchart TB
    app_main_py_55_create_app["create_app (182 lines)<br/>app/main.py:55"]
    app_saga_document_saga_py_294__step_chun["_step_chunk (143 lines)<br/>app/saga/document_saga.py:294"]
    app_saga_recovery_py_84__compensate["_compensate (86 lines)<br/>app/saga/recovery.py:84"]
    app_saga_document_saga_py_138_run["run (82 lines)<br/>app/saga/document_saga.py:138"]
    app_saga_reembed_worker_py_75__run_once["_run_once (76 lines)<br/>app/saga/reembed_worker.py:75"]
```


## 📐 Class Diagram (UML-style)

Top classes by method count, with inheritance arrows. Common framework bases (`BaseModel`, `BaseSettings`, `Exception`, `Enum`) use dotted lines.

```mermaid
classDiagram
    class DocumentIngestionSaga {
        +14 methods
        ~app/saga/document_saga.py:71
    }
    class IngestionService {
        +8 methods
        ~app/services/ingestion_service.py:45
    }
    class Neo4jRepo {
        +7 methods
        ~app/repositories/neo4j_repo.py:27
    }
    class DocumentRepo {
        +7 methods
        ~app/repositories/document_repo.py:56
    }
    Repository <|-- DocumentRepo
    class OutboxDrainWorker {
        +6 methods
        ~app/saga/outbox.py:80
    }
    class QdrantRepo {
        +6 methods
        ~app/repositories/qdrant_repo.py:41
    }
    class SagaRepo {
        +6 methods
        ~app/repositories/saga_repo.py:22
    }
    Repository <|-- SagaRepo
    class RecursiveChunker {
        +6 methods
        ~app/chunking/recursive.py:47
    }
    Chunker <|-- RecursiveChunker
    class ReembedWorker {
        +5 methods
        ~app/saga/reembed_worker.py:30
    }
    class OllamaEmbedder {
        +5 methods
        ~app/embedding/ollama_embedder.py:30
    }
    EmbeddingProvider <|-- OllamaEmbedder
    class ParserRegistry {
        +5 methods
        ~app/parsers/registry.py:17
    }
    class BlobService {
        +5 methods
        ~app/services/blob_service.py:24
    }
    class ChunkRepo {
        +4 methods
        ~app/repositories/chunk_repo.py:17
    }
    Repository <|-- ChunkRepo
    class TokenCounter {
        +4 methods
        ~app/chunking/token_counter.py:16
    }
    class EmbeddingProvider {
        +4 methods
        ~app/embedding/base.py:8
    }
    ABC <|-- EmbeddingProvider
```


_Showing top 15 of 41 classes (ranked by method count)._


## 4. Code Sequence — How Files Link to Each Other

**Import graph for files in this folder.** Reading order: start at any entry-point file (look for `🚀 entry point` role in the inventory above), then follow the arrows.

```mermaid
flowchart LR
    app_chunking_base_py["app/chunking/base.py"] --> app_parsers___init___py["app/parsers/__init__.py"]
    app_chunking_recursive_py["app/chunking/recursive.py"] --> app_parsers___init___py["app/parsers/__init__.py"]
    app_main_py["app/main.py"] --> app_chunking___init___py["app/chunking/__init__.py"]
    app_main_py["app/main.py"] --> app_core_config_py["app/core/config.py"]
    app_main_py["app/main.py"] --> app_embedding___init___py["app/embedding/__init__.py"]
    app_main_py["app/main.py"] --> app_parsers___init___py["app/parsers/__init__.py"]
    app_main_py["app/main.py"] --> app_repositories___init___py["app/repositories/__init__.py"]
    app_main_py["app/main.py"] --> app_routers___init___py["app/routers/__init__.py"]
    app_main_py["app/main.py"] --> app_saga___init___py["app/saga/__init__.py"]
    app_main_py["app/main.py"] --> app_services___init___py["app/services/__init__.py"]
    app_repositories_chunk_repo_py["app/repositories/chunk_repo.py"] --> app_chunking___init___py["app/chunking/__init__.py"]
    app_routers_documents_py["app/routers/documents.py"] --> app_schemas___init___py["app/schemas/__init__.py"]
    app_routers_documents_py["app/routers/documents.py"] --> app_services___init___py["app/services/__init__.py"]
    app_saga_document_saga_py["app/saga/document_saga.py"] --> app_chunking___init___py["app/chunking/__init__.py"]
    app_saga_document_saga_py["app/saga/document_saga.py"] --> app_embedding___init___py["app/embedding/__init__.py"]
    app_saga_document_saga_py["app/saga/document_saga.py"] --> app_parsers___init___py["app/parsers/__init__.py"]
    app_saga_document_saga_py["app/saga/document_saga.py"] --> app_repositories___init___py["app/repositories/__init__.py"]
    app_saga_document_saga_py["app/saga/document_saga.py"] --> app_saga___init___py["app/saga/__init__.py"]
    app_saga_document_saga_py["app/saga/document_saga.py"] --> app_services___init___py["app/services/__init__.py"]
    app_saga_reembed_worker_py["app/saga/reembed_worker.py"] --> app_embedding___init___py["app/embedding/__init__.py"]
    app_saga_reembed_worker_py["app/saga/reembed_worker.py"] --> app_repositories___init___py["app/repositories/__init__.py"]
    app_services_ingestion_service_py["app/services/ingestion_service.py"] --> app_chunking___init___py["app/chunking/__init__.py"]
    app_services_ingestion_service_py["app/services/ingestion_service.py"] --> app_core_config_py["app/core/config.py"]
    app_services_ingestion_service_py["app/services/ingestion_service.py"] --> app_embedding___init___py["app/embedding/__init__.py"]
    app_services_ingestion_service_py["app/services/ingestion_service.py"] --> app_parsers___init___py["app/parsers/__init__.py"]
    app_services_ingestion_service_py["app/services/ingestion_service.py"] --> app_repositories___init___py["app/repositories/__init__.py"]
    app_services_ingestion_service_py["app/services/ingestion_service.py"] --> app_saga___init___py["app/saga/__init__.py"]
    app_services_poisoning_defense_py["app/services/poisoning_defense.py"] --> app_chunking___init___py["app/chunking/__init__.py"]
    tests_test_poisoning_defense_py["tests/test_poisoning_defense.py"] --> app_chunking___init___py["app/chunking/__init__.py"]
    tests_test_poisoning_defense_py["tests/test_poisoning_defense.py"] --> app_services___init___py["app/services/__init__.py"]
```

### Edge list

| From file | To file | Import-count |
|---|---|---|
| `app/main.py` | `app/saga/__init__.py` | 2 |
| `app/saga/document_saga.py` | `app/repositories/__init__.py` | 2 |
| `app/saga/document_saga.py` | `app/services/__init__.py` | 2 |
| `app/chunking/base.py` | `app/parsers/__init__.py` | 1 |
| `app/chunking/recursive.py` | `app/parsers/__init__.py` | 1 |
| `app/main.py` | `app/chunking/__init__.py` | 1 |
| `app/main.py` | `app/core/config.py` | 1 |
| `app/main.py` | `app/embedding/__init__.py` | 1 |
| `app/main.py` | `app/parsers/__init__.py` | 1 |
| `app/main.py` | `app/repositories/__init__.py` | 1 |
| `app/main.py` | `app/routers/__init__.py` | 1 |
| `app/main.py` | `app/services/__init__.py` | 1 |
| `app/repositories/chunk_repo.py` | `app/chunking/__init__.py` | 1 |
| `app/routers/documents.py` | `app/schemas/__init__.py` | 1 |
| `app/routers/documents.py` | `app/services/__init__.py` | 1 |
| `app/saga/document_saga.py` | `app/chunking/__init__.py` | 1 |
| `app/saga/document_saga.py` | `app/embedding/__init__.py` | 1 |
| `app/saga/document_saga.py` | `app/parsers/__init__.py` | 1 |
| `app/saga/document_saga.py` | `app/saga/__init__.py` | 1 |
| `app/saga/reembed_worker.py` | `app/embedding/__init__.py` | 1 |
| `app/saga/reembed_worker.py` | `app/repositories/__init__.py` | 1 |
| `app/services/ingestion_service.py` | `app/chunking/__init__.py` | 1 |
| `app/services/ingestion_service.py` | `app/core/config.py` | 1 |
| `app/services/ingestion_service.py` | `app/embedding/__init__.py` | 1 |
| `app/services/ingestion_service.py` | `app/parsers/__init__.py` | 1 |
| `app/services/ingestion_service.py` | `app/repositories/__init__.py` | 1 |
| `app/services/ingestion_service.py` | `app/saga/__init__.py` | 1 |
| `app/services/poisoning_defense.py` | `app/chunking/__init__.py` | 1 |
| `tests/test_poisoning_defense.py` | `app/chunking/__init__.py` | 1 |
| `tests/test_poisoning_defense.py` | `app/services/__init__.py` | 1 |


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

**Detected endpoints:** 7

| Method | Route | Defined in | Input (schema) | Process (summary) | Output (schema) |
|---|---|---|---|---|---|
| `GET` | `/health` | `app/routers/health.py:11` | _TBD_ | _TBD_ | _TBD_ |
| `GET` | `/healthz` | `app/routers/health.py:17` | _TBD_ | _TBD_ | _TBD_ |
| `GET` | `/health/ready` | `app/routers/health.py:23` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/upload` | `app/routers/documents.py:32` | _TBD_ | _TBD_ | _TBD_ |
| `GET` | `/{document_id}` | `app/routers/documents.py:82` | _TBD_ | _TBD_ | _TBD_ |
| `GET` | `/{document_id}/chunks` | `app/routers/documents.py:93` | _TBD_ | _TBD_ | _TBD_ |
| `DELETE` | `/{document_id}` | `app/routers/documents.py:104` | _TBD_ | _TBD_ | _TBD_ |

_Reviewer fills the last three columns from the Pydantic models in the handler. Auto-extraction of Pydantic schemas is on the roadmap._


## 🏗 Input/Process/Output + Integration + Design Principles

### Input / Process / Output per endpoint

| Endpoint | INPUT (validation chain) | PROCESS (call chain) | OUTPUT (response chain) |
|---|---|---|---|
| `GET /health` | Pydantic schema validated at middleware | Router `app/routers/health.py:11` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `GET /healthz` | Pydantic schema validated at middleware | Router `app/routers/health.py:17` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `GET /health/ready` | Pydantic schema validated at middleware | Router `app/routers/health.py:23` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `POST /upload` | Pydantic schema validated at middleware | Router `app/routers/documents.py:32` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `GET /{document_id}` | Pydantic schema validated at middleware | Router `app/routers/documents.py:82` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `GET /{document_id}/chunks` | Pydantic schema validated at middleware | Router `app/routers/documents.py:93` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `DELETE /{document_id}` | Pydantic schema validated at middleware | Router `app/routers/documents.py:104` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |

### Integration sequence (ordered by import volume)

Other folders this one calls into, ordered by how heavily it depends on each:

```mermaid
sequenceDiagram
  autonumber
  participant This as ingestion-svc
  participant documind_core_exceptions as documind_core/exceptions
  participant documind_core_db_client as documind_core/db_client
  participant app_chunking as app/chunking
  participant app_parsers as app/parsers
  participant app_repositories as app/repositories
  participant app_services as app/services
  This->>documind_core_exceptions: call (~8 import sites)
  documind_core_exceptions-->>This: response
  This->>documind_core_db_client: call (~8 import sites)
  documind_core_db_client-->>This: response
  This->>app_chunking: call (~6 import sites)
  app_chunking-->>This: response
  This->>app_parsers: call (~5 import sites)
  app_parsers-->>This: response
  This->>app_repositories: call (~5 import sites)
  app_repositories-->>This: response
  This->>app_services: call (~5 import sites)
  app_services-->>This: response
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
| **Single business capability** | `ingestion-svc` owns ONE capability (see §1 Purpose). Cross-capability logic lives in other services. |
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


## 🔬 Execution Sequence + Debug Tap Points

For each phase a request goes through, this section shows: **(1)** the file:line where it happens, **(2)** the log line you'll see, **(3)** the command to inspect that phase's output in real time. Use this as your debug-flow chart — start at Phase 0, move down until output stops matching the expected log line; that's where the failure is.

**Worked example:** `GET /health` (app/routers/health.py:11)

### Phase-by-phase debug tap table

| # | Phase | Code location | Log line to grep | Command to inspect |
|---|---|---|---|---|
| 0 | **TCP connect** | OS / docker network | `client_connected` | `curl -v http://localhost:8082/health 2>&1 \| head -15` |
| 1 | **Middleware: request_id assign** | `documind_core/middleware.py` | `request_id=...` | `docker logs documind-ingestion-svc -f \| grep request_id` |
| 2 | **Middleware: auth** | `documind_core/auth.py` | `auth_ok` or `auth_denied` | `docker logs documind-ingestion-svc -f \| grep auth_` |
| 3 | **Middleware: tenant resolution** | `documind_core/middleware.py` | `tenant_id=<id>` | `docker logs documind-ingestion-svc -f \| grep tenant_id` |
| 4 | **Pydantic validation** | `app/schemas/*.py` | `422 Unprocessable` (on fail) | `docker logs documind-ingestion-svc -f \| grep -E 'validation\|422'` |
| 5 | **Router dispatch** | `app/routers/health.py:11` | `GET /health` | `docker logs documind-ingestion-svc -f \| grep '/health'` |
| 6 | **Business service call** | `app/services/*.py` | `service_method_start` | `docker logs documind-ingestion-svc -f \| grep service_` |
| 7 | **DB query** | `app/repositories/*.py` or `documind_core/db_client.py` | `asyncpg.execute` or `SELECT...` | `docker logs documind-postgres -f \| grep -E 'duration:'` |
| 8 | **External call (LLM / vector)** | `app/services/*_client.py` | `llm_call_start` / `vector_search_start` | `docker logs documind-ingestion-svc -f \| grep -E 'llm_\|vector_'` |
| 9 | **Decision audit log** | `documind_core/ai_governance.py` | `decision_audit:` | `psql -p 55432 -U documind -c "SELECT * FROM decision_audit ORDER BY ts DESC LIMIT 1;"` |
| 10 | **Response shaping** | `app/schemas/*.py` (response model) | `response_ms=` | `docker logs documind-ingestion-svc -f \| grep response_ms` |
| 11 | **Trace span flush** | OTel exporter | _(async)_ | Open Jaeger UI: `http://localhost:16686/search?service=ingestion-svc` |

### Reproducible end-to-end trace

Use this script to fire ONE request and see every phase's output in a single terminal:

```bash
REQ_ID=$(uuidgen)
echo "=== Issuing GET /health with request_id=$REQ_ID ==="

# Phase 0-2: tail logs in background
docker logs documind-ingestion-svc --tail=0 -f 2>&1 | grep --line-buffered "$REQ_ID" &
TAIL_PID=$!
sleep 0.5

# Phase 3-10: fire the request
curl -X GET http://localhost:8082/health \
  -H "X-Correlation-ID: $REQ_ID" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{}' -w "\nTOTAL=%{time_total}s\n"

sleep 2  # let logs flush
kill $TAIL_PID

# Phase 9: pull the decision audit row
psql -h localhost -p 55432 -U documind -d documind \
  -c "SELECT request_id, model_version, prompt_version, decision, confidence FROM decision_audit WHERE request_id='$REQ_ID';"

# Phase 11: pull the trace span tree
open "http://localhost:16686/search?service=ingestion-svc&tags=%7B%22request_id%22%3A%22$REQ_ID%22%7D"
```

### Debug-order checklist (when something breaks)

Walk the phases IN ORDER — first phase with missing/wrong output is the failure point. Don't skip ahead:

1. **Phase 0 fail?** Service not running → `bash scripts/circuitrag-status.sh`
2. **Phase 1-3 fail?** Middleware misconfigured → check env vars + middleware order in `main.py`
3. **Phase 4 fail (422)?** Request body doesn't match schema → check Pydantic model in `app/schemas/`
4. **Phase 5 fail (404)?** Route not registered → check router import in `main.py`
5. **Phase 6 fail (500)?** Business logic exception → tail logs for stack trace
6. **Phase 7 fail?** DB unreachable → `psql -p 55432 -U documind -c "SELECT 1;"`
7. **Phase 8 fail?** External dep down → check `/health/upstreams` + circuit breaker state
8. **Phase 9 missing?** Decision audit not persisted → check Kafka consumer lag
9. **Phase 10 slow?** Response shaping bottleneck → profile the response model
10. **Phase 11 empty Jaeger?** OTel exporter misconfigured → check `OTEL_EXPORTER_OTLP_ENDPOINT`


## 🧠 Business Logic — How It's Written + Logical Step Sequence

### Where business logic lives

Business logic is **separated from HTTP** — routers receive validated requests and immediately delegate to a service class. Services hold the state machines, calling repositories for I/O and external clients for LLM / vector / Kafka.

**Primary business-logic file in this folder:** `app/services/ingestion_service.py` (200 LOC, 2 classes, 0 functions)

### The canonical logical step sequence

Every business-service method in this folder follows this 11-step skeleton (some steps are skipped if not applicable):

```python
async def some_service_method(self, request: RequestSchema) -> ResponseSchema:
    # ── Step 1: Pre-conditions / argument check ─────────────────
    if not request.is_valid():
        raise BadRequest('reason')

    # ── Step 2: Idempotency check (X-Idempotency-Key) ──────────
    cached = await self.cache.get(request.idempotency_key)
    if cached:
        return cached  # short-circuit duplicate request

    # ── Step 3: Authorization (RBAC / tenant scope) ────────────
    self.authz.require(request.actor, 'resource:action')

    # ── Step 4: Load context (DB / cache / config) ─────────────
    context = await self.repo.load_context(request.tenant_id)

    # ── Step 5: Apply business rules ───────────────────────────
    decision = self.rules.evaluate(request, context)

    # ── Step 6: External calls (LLM / vector / 3rd-party) ──────
    async with self.breaker:  # circuit breaker wrap
        llm_response = await self.llm.call(...)

    # ── Step 7: Post-processing / output validation ────────────
    self.guardrails.check(llm_response)

    # ── Step 8: Persist state (DB write + Kafka emit) ──────────
    async with self.repo.transaction():
        await self.repo.save(record)
        await self.kafka.publish('topic', event)

    # ── Step 9: Decision audit row (§38 + §48) ─────────────────
    await self.audit.log_decision({
        'request_id': request.id,
        'model_version': self.model.version,
        'prompt_version': self.prompt.version,
        'decision': decision,
        'confidence': llm_response.confidence,
    })

    # ── Step 10: Cache the response (if idempotent) ────────────
    await self.cache.set(request.idempotency_key, response, ttl=3600)

    # ── Step 11: Return + emit metric ──────────────────────────
    self.metrics.observe('request_latency', elapsed_ms)
    return ResponseSchema(...)
```

### How to map a real method to this skeleton

1. Open `app/services/ingestion_service.py` in your editor
2. Find the longest function (likely `main service method`)
3. Walk it line by line; tag each block with the corresponding step number from the skeleton above
4. Steps that are missing are opportunities (e.g. missing idempotency check, missing audit row) — file as P1/P2 in the brutal-tool-review for this folder

### Inspecting each step at runtime

| Step | What to inspect | How |
|---|---|---|
| 1 | Pre-condition rejects | grep `BadRequest` in logs |
| 2 | Idempotency cache hits | grep `cache_hit=true` in logs |
| 3 | Authz denials | grep `authz_denied` in logs |
| 4 | Context load latency | `pg_stat_statements` slow-query log |
| 5 | Rule evaluation | trace span `business.rules.evaluate` |
| 6 | External call latency | trace span `llm.call` / `vector.search` |
| 7 | Guardrail rejections | grep `guardrail_triggered` in logs |
| 8 | Transaction commits | grep `tx_commit` in logs |
| 9 | Decision audit rows | `SELECT * FROM decision_audit ORDER BY ts DESC LIMIT 5;` |
| 10 | Cache writes | `redis-cli -p 56379 MONITOR` |
| 11 | Latency histogram | Grafana panel: `histogram_quantile(0.95, ...)` |


## 7. Sequence Diagrams per Endpoint

### Generic flow (all endpoints)

```mermaid
sequenceDiagram
  autonumber
  participant Client
  participant API as ingestion-svc
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

### `GET /health` (app/routers/health.py:11)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/health.py:11)
  participant S as Service
  participant D as DB / external
  C->>H: GET /health
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `GET /healthz` (app/routers/health.py:17)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/health.py:17)
  participant S as Service
  participant D as DB / external
  C->>H: GET /healthz
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `GET /health/ready` (app/routers/health.py:23)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/health.py:23)
  participant S as Service
  participant D as DB / external
  C->>H: GET /health/ready
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /upload` (app/routers/documents.py:32)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/documents.py:32)
  participant S as Service
  participant D as DB / external
  C->>H: POST /upload
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `GET /{document_id}` (app/routers/documents.py:82)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (app/routers/documents.py:82)
  participant S as Service
  participant D as DB / external
  C->>H: GET /{document_id}
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

_(+2 more endpoints — diagrams omitted for brevity.)_


## 🔬 Annotated Example Request

Walk through what happens when a client calls **`GET /health`** (app/routers/health.py:11).

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Client sends HTTP request                                        │
│    GET /health                                                     │
│    Headers: Authorization, X-Correlation-ID, X-Tenant-ID            │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Middleware stack (auth → logging → tracing → rate-limit)         │
│    - Validate JWT / API key                                         │
│    - Resolve tenant_id from token                                   │
│    - Start span; inject request_id into baggage                     │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Pydantic validation                                              │
│    - Parse request body against schema                              │
│    - 422 on validation error (with field-level details)             │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Router handler                                                   │
│    app/routers/health.py:11
│    - Receive validated request + injected Depends()                 │
│    - Delegate to business service                                   │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. Business service                                                 │
│    - Apply rules / orchestrate multi-step logic                     │
│    - Call repositories for DB I/O                                   │
│    - Call external services (LLM / vector DB / etc.)             │
│    - Emit metrics + log decision audit row                          │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 6. Response shaping                                                 │
│    - Build response Pydantic model                                  │
│    - Serialize to JSON                                              │
│    - Add correlation_id, latency_ms to headers                      │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
                       Client
```

### Inspecting this in real time

```bash
# 1. Tail the service log
docker logs documind-ingestion-svc --tail=20 -f &

# 2. Issue the request with a fresh correlation_id
REQ_ID=$(uuidgen)
curl -X GET http://localhost:<PORT>/health \
  -H "X-Correlation-ID: $REQ_ID" \
  -H "Authorization: Bearer <token>" \
  -d '{}'

# 3. Find the trace in Jaeger
open http://localhost:16686/search?service=ingestion-svc&tags=%7B%22request_id%22%3A%22$REQ_ID%22%7D
```


## 8. Database Layer

**DB / storage libraries:** Neo4j, Qdrant, Redis, asyncpg

**Total DB call sites:** 42

| Pattern | Count |
|---|---|
| `execute` | 18 |
| `fetch/fetchall/fetchrow` | 16 |
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
| No hardcoded values | — | smell count: 0 |
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
| SQL injection prevention | — | DB libs: Neo4j, Qdrant, Redis, asyncpg — parameterized queries only |
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
| Thread safety validated | — | primitives: asyncio (async/await) |
| Race conditions prevented | — | — |
| Deadlocks avoided (lock ordering) | — | — |
| Parallel processing where beneficial | — | 71 async fns |

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
**Test functions parsed:** 7

| Test name | Location | Purpose (from docstring) |
|---|---|---|
| `test_allows_clean_chunk` | `tests/test_poisoning_defense.py:18` | _(no docstring)_ |
| `test_rejects_injection_chunk` | `tests/test_poisoning_defense.py:25` | _(no docstring)_ |
| `test_redacts_pii_chunk` | `tests/test_poisoning_defense.py:33` | _(no docstring)_ |
| `test_batch_filters_rejected_and_flags_redacted` | `tests/test_poisoning_defense.py:41` | _(no docstring)_ |
| `test_does_not_reject_legitimate_technical_use_of_override` | `tests/test_poisoning_defense.py:59` | _(no docstring)_ |
| `test_does_not_reject_documentation_referencing_previous_section` | `tests/test_poisoning_defense.py:68` | _(no docstring)_ |
| `test_does_not_reject_forget_as_verb_in_prose` | `tests/test_poisoning_defense.py:76` | _(no docstring)_ |

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

**Detected AI deps:** Ollama

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
| `documind_core/exceptions` | 8 | _reviewer-described_ |
| `documind_core/db_client` | 8 | _reviewer-described_ |
| `app/chunking` | 6 | _reviewer-described_ |
| `app/parsers` | 5 | _reviewer-described_ |
| `app/repositories` | 5 | _reviewer-described_ |
| `app/services` | 5 | _reviewer-described_ |
| `app/embedding` | 4 | _reviewer-described_ |
| `app/saga` | 4 | _reviewer-described_ |
| `documind_core/config` | 2 | _reviewer-described_ |
| `documind_core/kafka_client` | 2 | _reviewer-described_ |
| `app/core` | 2 | _reviewer-described_ |
| `documind_core/circuit_breaker` | 1 | _reviewer-described_ |
| `documind_core/body_limit` | 1 | _reviewer-described_ |
| `documind_core/idempotency` | 1 | _reviewer-described_ |
| `documind_core/idempotency_middleware` | 1 | _reviewer-described_ |
| `documind_core/logging_config` | 1 | _reviewer-described_ |
| `documind_core/middleware` | 1 | _reviewer-described_ |
| `documind_core/observability` | 1 | _reviewer-described_ |
| `documind_core/rate_limiter` | 1 | _reviewer-described_ |
| `app/routers` | 1 | _reviewer-described_ |
| `app/schemas` | 1 | _reviewer-described_ |
| `documind_core/schemas` | 1 | _reviewer-described_ |
| `documind_core/ai_governance` | 1 | _reviewer-described_ |

### External — third-party packages

| Package | Import-count |
|---|---|
| `base` | 11 |
| `fastapi` | 5 |
| `html_parser` | 3 |
| `token_counter` | 2 |
| `docx_parser` | 2 |
| `markdown_parser` | 2 |
| `pdf_parser` | 2 |
| `text_parser` | 2 |
| `qdrant_client` | 2 |
| `best_config_loader` | 2 |
| `blob_service` | 2 |
| `minio` | 2 |
| `recursive` | 1 |
| `tiktoken` | 1 |
| `ollama_embedder` | 1 |
| `httpx` | 1 |
| `redis` | 1 |
| `registry` | 1 |
| `docx` | 1 |
| `bs4` | 1 |


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
1. Tail logs:        tail -50 /tmp/ingestion-svc.log   (if host-side)
                     docker logs documind-ingestion-svc --tail=50   (if container)
2. Health probe:     curl http://localhost:<PORT>/health
3. Fleet probe:      python3 scripts/advanced_healthcheck.py --layer app
4. Trace:            Open Jaeger → search request_id → see span tree
5. Metrics:          Open Grafana → service dashboard → look for spike
6. Drill:            ls mcp/tests/drill_*ingestion-svc*.py and run
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
| `c6e58b8` | 2026-05-16 | docs(readme): advanced auto-generated READMEs (project + per-folder) |
| `ec1f7b4` | 2026-05-07 | fix(iter-88): bulk lint cleanup across services/ libs/ mcp/ scripts/ (1139 ruff fixes; drill suite still green) |
| `8fcb426` | 2026-05-05 | feat(ingestion): Stage-2 best_config_loader as SECONDARY chunking-strategy hint |
| `38ca47a` | 2026-05-04 | feat(ingestion): Stage-3 wire chunking strategy selector into saga |
| `cd77b0c` | 2026-05-04 | feat(ingestion): Stage-3 wire PII redactor into DocumentIngestionSaga |
| `4f7354c` | 2026-05-04 | feat(retrieval): BGE reranker protected by NativeComputeWrapper — Stage-2 |
| `ef5a97a` | 2026-04-30 | fix(ci): unblock python CI — 100% encryption.py coverage + lint sweep |
| `868dfaa` | 2026-04-30 | chore(lint): apply ruff autofix lane via issue dispatcher (34 fixes) |

```bash
git log --oneline -- services/ingestion-svc    # see all commits
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
| No memory leaks | bounded caches | — | smells: 0 |
| No N+1 queries | hot paths reviewed | — | 42 DB call sites |
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
