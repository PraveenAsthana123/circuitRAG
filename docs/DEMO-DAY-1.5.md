# Demo Day 1.5 — Ingestion Service LIVE

**Goal:** Start services as processes against the Day-1 healthy infra, exercise `/health`, document every failure found.

**Status:** 🟢 **Ingestion-svc green on :8082** after fixing two real bugs.

**Date:** 2026-04-24

---

## Evidence captured

### 1. Ingestion service boot log

```
neo4j_constraints_ensured
admin_connection_acquired (RLS bypass)
saga_recovery_complete recovered=0 age_threshold=0:15:00
ingestion_service_ready model=nomic-embed-text dim=768
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8082 (Press CTRL+C to quit)
```

### 2. Health check

```bash
$ curl -s -w "[%{http_code}]\n" http://127.0.0.1:8082/health
{"status":"ok","service":"ingestion-svc","version":"0.1.0","checks":{}}
[200]

$ curl -s -w "[%{http_code}]\n" http://127.0.0.1:8082/healthz
{"status":"ok"}
[200]
```

### 3. Routes discovered

```
/api/v1/documents
/api/v1/documents/upload
/api/v1/documents/{document_id}
/api/v1/documents/{document_id}/chunks
/health
/healthz
```

### 4. Startup components (what actually initialized)

| Component | State |
| --- | --- |
| Postgres (port 55432) | healthy + migrations applied |
| Qdrant (port 6333, API key auth) | healthy + returns collections |
| Neo4j (port 7687) | constraints ensured on startup |
| Redis (port 56379) | healthy |
| MinIO (port 59000) | healthy |
| Ollama (port 11434) | healthy + embedder `nomic-embed-text` loaded |
| OTel collector | down — Observability CB skipping silently (as designed) |
| Kafka (port 59092) | up; ingestion-svc consumer pool initialized |

---

## Real bugs fixed to get this far

### Bug 1: `_BreakerGuardedMetricExporter` missing `_preferred_aggregation`

**Symptom:**
```
AttributeError: '_BreakerGuardedMetricExporter' object has no attribute '_preferred_aggregation'
```

**Cause:** OTel SDK 1.27+ introduced `_preferred_aggregation` on the exporter interface; our breaker wrapper forwarded `_preferred_temporality` but not the new one.

**Fix:** `libs/py/documind_core/observability.py` — added a second property forwarding `self._inner._preferred_aggregation`. One commit, 4 lines.

This is a concrete example of the Observability CB doing its job — wrapping the real exporter behind a breaker so dead OTel never blocks user requests.

### Bug 2: Qdrant empty-API-key interpreted as "required but unset"

**Symptom:**
```
qdrant_client.http.exceptions.UnexpectedResponse: 401 (Unauthorized)
b'Must provide an API key or an Authorization bearer token'
ERROR:    Application startup failed.
```

**Cause:** `docker-compose.yml` sets `QDRANT__SERVICE__API_KEY: ${DOCUMIND_QDRANT_API_KEY:-}`. When the env var isn't set, Qdrant receives the key as empty string — which it treats as "auth required but no valid key" rather than "auth disabled". Classic Docker env interpolation gotcha.

**Fix:** `docker-compose.override.yml` — set a static dev key `dev-qdrant-key`. Both server and client use it. One YAML block.

### Config issue: `DOCUMIND_ENV=dev` → `development`

Pydantic `Literal` config only accepts `"development" | "staging" | "production"`. Our convenience alias `dev` wasn't handled. Documented in Day-1.5 env script as the explicit value.

---

## What's in `/tmp/start-ingestion-env.sh` (reproducible)

```bash
export DOCUMIND_PG_HOST=localhost
export DOCUMIND_PG_PORT=55432
export DOCUMIND_PG_USER=documind_app
export DOCUMIND_PG_PASSWORD=documind_app
export DOCUMIND_REDIS_HOST=localhost
export DOCUMIND_REDIS_PORT=56379
export DOCUMIND_QDRANT_HOST=localhost
export DOCUMIND_QDRANT_PORT=6333
export DOCUMIND_QDRANT_API_KEY=dev-qdrant-key
export DOCUMIND_NEO4J_URI=bolt://localhost:7687
export DOCUMIND_NEO4J_USER=neo4j
export DOCUMIND_NEO4J_PASSWORD=documind
export DOCUMIND_MINIO_ENDPOINT=localhost:59000
export DOCUMIND_MINIO_ACCESS_KEY=documind
export DOCUMIND_MINIO_SECRET_KEY=documind-secret
export DOCUMIND_OLLAMA_URL=http://localhost:11434
export DOCUMIND_KAFKA_BOOTSTRAP_SERVERS=localhost:59092
export DOCUMIND_ENV=development
export PYTHONPATH=/mnt/deepa/rag/services/ingestion-svc
```

---

## What's NOT done yet (honest Day-1.5 gaps)

| Still open | Blocker |
| --- | --- |
| Retrieval + inference services started | not yet exercised |
| `POST /api/v1/documents/upload` with a real PDF → saga → indexed | need a sample PDF + multipart upload test |
| `POST /api/v1/ask` → cited answer (full E2E) | requires retrieval + inference also running |
| OTel collector connected → Jaeger trace | collector not started (intentional — proves Observability CB works) |
| ELK stack tested | not started in Day-1 overrides |
| `@with_resilience` decorator at call sites | Phase 3 §11 work |
| MCP code | Phase 6 §8 work — zero code |

---

## Next Day-1.5 step

1. Start retrieval-svc on :8083 with the same env script.
2. Start inference-svc on :8084.
3. Upload a real PDF via `POST /api/v1/documents/upload`.
4. Poll `GET /api/v1/documents/{id}` until `state=active`.
5. `POST /api/v1/ask` on retrieval-svc → grounded answer with citation.

Day 1.5's exit criterion: **one full query cites a real chunk from a real uploaded document**.
