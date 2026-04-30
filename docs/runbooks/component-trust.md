# How to trust each component is actually working

> Verifiable trust signals for every shipped component. No narrative —
> commands you run, numbers you see, drills that lock the contract.
>
> Locked by `mcp/tests/drill_verify_stack.py`.

## One-liner: verify everything

```bash
bash scripts/verify-stack.sh
```

Output:
```
postgres                       [PASS] localhost:55432 - accepting connections
redis                          [PASS] PONG
qdrant                         [PASS] {"status":"ok"}
neo4j                          [PASS] {"name":"neo4j","versions":["5.21.0"]}
prometheus                     [PASS] Prometheus Server is Healthy.
...
═══ Summary ═══
PASS:  N
FAIL:  0
SKIP:  M  (component not deployed; not a fault)
```

PASS / FAIL / SKIP per component. SKIP means "not deployed" (no fault). FAIL means "deployed but broken".

## Per-component trust commands

### Circuit breakers

| What to verify | Command | Expected |
|---|---|---|
| State machine correctness | `.venv/bin/python mcp/tests/drill_breaker_transitions.py` | `ALL N STEPS PASSED` |
| Per-transport breakers (vector + graph) | `.venv/bin/python mcp/tests/drill_retrieval_transport_breaker.py` | `ALL N STEPS PASSED` |
| Prometheus gauge correctness | `curl -s http://localhost:9090/api/v1/query?query=documind_circuit_breaker_state` | JSON with breaker state per name |
| Live state in dashboard | `http://localhost:3001/d/documind-overview` (Grafana) | "Circuit breaker state" panel populated |

Code path: `libs/py/documind_core/circuit_breaker.py` + `libs/py/documind_core/breakers.py` (5 specialized breakers).
ADR: `docs/architecture/adr/002-circuit-breaker-unification.md`.

### Istio (mesh)

| What to verify | Command | Expected |
|---|---|---|
| YAML structure | `kubectl apply --dry-run=client -f infra/istio/` | no errors per file |
| Drill | `.venv/bin/python mcp/tests/drill_minikube_istio_setup.py` | `ALL 11 STEPS PASSED` |
| Live mesh state (after `bash scripts/istio-up.sh`) | `kubectl -n istio-system get pods` | `istiod` Running |
| Authz policy enforcement | `kubectl -n documind get authorizationpolicies` | 10+ named entries |
| Sidecar injection | `kubectl -n documind get pods` (after deploy) | each pod has `istio-proxy` container |

Status: scripts shipped + drill green; **operator runs `bash scripts/istio-up.sh` to actually start a minikube cluster**. Local dev does NOT need it.

### API gateway

| What to verify | Command | Expected |
|---|---|---|
| Compose wiring | `.venv/bin/python mcp/tests/drill_api_gateway_compose.py` | `ALL 11 STEPS PASSED` |
| Container starts | `docker compose --profile app up -d api-gateway && docker compose ps api-gateway` | STATUS = healthy |
| /healthz responds | `curl -sf http://localhost:8080/healthz` | `{"status":"ok"}` |
| JWT validation rejects malformed | `curl -sH "Authorization: Bearer x.y.z" http://localhost:8080/api/v1/...` | 401 INVALID_TOKEN |
| Rate-limit returns 429 | bombard with `>`100 RPS from same IP | 429 + `Retry-After` |
| Correlation_id propagation | `curl -sI http://localhost:8080/healthz` | `X-Correlation-Id: <uuid>` header |

Code path: `services/api-gateway/cmd/main.go` + `internal/middleware/{jwt,ratelimit}.go`.

### Model Context Protocol (MCP)

| What to verify | Command | Expected |
|---|---|---|
| 3 servers exist | `ls mcp/server_*.py` | `server_drills.py server_hr.py server_itsm.py server_common.py` |
| Common scaffolding | `grep -c 'enforce_scope\|setup_server_otel' mcp/server_common.py` | > 0 |
| MCP tool list (live, against running server) | `curl -sf http://localhost:8092/tools/list` | JSON array with `drill.list, drill.run` |
| Scope rejection | `curl -sf http://localhost:8092/tools/call -d '{"name":"drill.run","args":{}}'` | 403 INSUFFICIENT_SCOPE if no auth header |
| Drills | `.venv/bin/python mcp/tests/drill_mcp_*.py` | each `ALL N STEPS PASSED` |

### RAG (vector + graph hybrid)

| What to verify | Command | Expected |
|---|---|---|
| Vector DB (Qdrant) accessible | `curl -sf http://localhost:6333/readyz` | `{"status":"ok"}` |
| Graph DB (Neo4j) accessible | `curl -sfu neo4j:documind http://localhost:7474/db/neo4j/info` | JSON with version |
| Hybrid retrieve drill | `.venv/bin/python mcp/tests/drill_hybrid_retrieve.py` | `ALL N STEPS PASSED` |
| Tenant isolation | `.venv/bin/python mcp/tests/drill_retrieval_tenant_isolation.py` | `ALL N STEPS PASSED` |
| End-to-end with test fixture | (see "Round-trip test" section below) | retrieved chunks contain unique phrase |

Code path: `services/retrieval-svc/app/services/{vector_searcher,graph_searcher}.py` + `HybridRetriever`.

### Vectorless RAG (Elasticsearch)

| What to verify | Command | Expected |
|---|---|---|
| Wrapper class exists | `ls services/retrieval-svc/app/services/elastic_searcher.py` | file present |
| Skeleton drill | `.venv/bin/python mcp/tests/drill_elastic_searcher_skeleton.py` | `ALL 9 STEPS PASSED` |
| ES container | `docker compose ps elasticsearch` | STATUS = Up (healthy) |
| ES API (live) | `curl -sf http://localhost:9200` | JSON with `version.number` |
| Indexed documents (after operator-side ingestion) | `curl -sf http://localhost:9200/documind_documents/_count` | `{"count":N}` |

Status: **wrapper shipped, ingestion pipeline NOT shipped**. Until operator wires ingestion, `search()` returns `[]`.

### Elasticsearch (deployed)

| What to verify | Command | Expected |
|---|---|---|
| Container running | `docker compose ps elasticsearch` | STATUS healthy |
| /_cluster/health | `curl -sf http://localhost:9200/_cluster/health` | `"status":"green" or "yellow"` |
| Indices listed | `curl -sf http://localhost:9200/_cat/indices` | text table with `filebeat-*` indices (log aggregation) |

## Cross-tool data tracking (correlation_id pattern)

**One id, every tool.** Every request gets a server-generated UUID at the gateway; it threads through OTel baggage + audit row + log line + LLM call.

```
                   correlation_id = uuid v4 (server-generated)
                                  │
   ┌──────────────────────────────┼──────────────────────────────┐
   │                              │                              │
   ▼                              ▼                              ▼
NGINX log              api-gateway log            Backend log + audit
("X-Correlation-Id")  (extracted from header)    (correlation_id field)
                                  │                              │
                                  ▼                              ▼
              OTel span attribute              Postgres audit_log_partitioned
              (`documind.correlation_id`)       (correlation_id column)
                                  │                              │
                                  ▼                              ▼
                            Jaeger trace                     Council audit
                       (.loop/issue_audit.jsonl)            (chain[role])
                                  │
                                  ▼
                         Langfuse trace_id
                        (per-LLM-call metadata)
```

**To trace one request through every tool:**

```bash
# 1. Operator gets correlation_id from user error envelope, log, or trace UI
CID="abc12345-..."

# 2. Find every log line for this request
grep "$CID" /var/log/nginx/access.log
grep "$CID" services/*/logs/*.json   # if file logs
docker compose logs --since 1h | grep "$CID"

# 3. Find every audit row
psql -h localhost -p 55432 -U documind -d documind -c \
  "SELECT * FROM audit_log_partitioned WHERE correlation_id='$CID'"

# 4. Find every LLM call
grep "$CID" .loop/issue_audit.jsonl
grep "$CID" .loop/experts_log.jsonl

# 5. Find OTel spans
curl -sf "http://localhost:16686/api/traces?service=...&tags=correlation_id:$CID"
```

Code path: `libs/py/documind_core/observability.py` (middleware) + `libs/py/documind_core/middleware.py` (BaggageContextMiddleware).

## Switching tools (provider abstraction)

The repo uses **server-side configuration + try-fallback chain**, not a swappable adapter pattern. Examples:

| Switch | How |
|---|---|
| Cloud Kimi → local-chair (already wired) | `services/sidecar-advisor/advisor.py` catches `OllamaModelNotFoundError` → fallback (commit `6831dee`) |
| Ollama → vLLM | change `OLLAMA_BASE_URL` env to vLLM URL; `requirements.txt` swaps `langchain-community` `Ollama` for `langchain-community.llms.vllm` |
| Qdrant → Pinecone | swap `services/retrieval-svc/app/services/vector_searcher.py` (one file); same `search()` interface |
| Neo4j → ArangoDB | same — swap `graph_searcher.py`; `HybridRetriever` doesn't care |
| ES → Typesense | swap `elastic_searcher.py`; same interface |

The `<thing>_searcher.py` pattern means each provider is one file. Add new provider = new file with same `async search()` signature.

## Round-trip test (multi-modal)

Test fixtures committed at `tests/fixtures/multimodal/`:

```
sample.txt   — text with unique phrase "blue elephant"
sample.csv   — 3-row CSV with unique phrase "orange porcupine"
sample.json  — JSON document with unique phrase "yellow zebra"
```

End-to-end test (when ingestion-svc + retrieval-svc are running):

```bash
# 1. Ingest each fixture (POSTs to ingestion-svc; chunked + embedded + indexed)
for f in tests/fixtures/multimodal/sample.{txt,csv,json}; do
  curl -F "file=@$f" -F "tenant_id=test" \
       http://localhost:8082/api/v1/documents/upload
done

# 2. Query for unique phrases — must retrieve only the right doc
curl -G http://localhost:8083/api/v1/retrieve \
  --data-urlencode "query=blue elephant" \
  --data-urlencode "tenant_id=test" | jq '.results[].chunk_id'
# Expected: chunks from sample.txt only

curl -G http://localhost:8083/api/v1/retrieve \
  --data-urlencode "query=orange porcupine" \
  --data-urlencode "tenant_id=test" | jq '.results[].chunk_id'
# Expected: chunks from sample.csv only
```

For PDF / image / audio / video:
- ingestion-svc supports PDF (via pypdf), DOCX (via python-docx), HTML (via beautifulsoup4)
- **NOT supported yet**: image OCR, audio transcription, video frame extraction
- The drill catalog reflects what's actually wired; absence of a multimodal drill = not yet wired

## What's NOT trustable yet (honest)

- **vectorless retrieval**: wrapper shipped (`elastic_searcher.py`); ingestion pipeline not wired → search returns `[]`
- **knowledge graph build**: graph-svc planned; queries return [] today
- **LLM incident summarizer**: design only; no service code
- **Image / audio / video ingestion**: framework supports but no parsers wired

These are honestly marked PLANNED in `docs/STATUS.md` "What's NOT working" section.

## Brutal rule

> Trust = drill output + benchmark numbers + audit row + correlation_id
> trace, NOT narrative. If you can't reproduce a claim with a command,
> the claim is suspect. Run `bash scripts/verify-stack.sh` before you
> trust anything in this README.
