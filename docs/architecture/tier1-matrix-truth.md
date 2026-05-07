# Tier-1 Architecture Matrix — verification-driven truth

> Per CLAUDE.md §45.4 (no checkbox flips without code) + §51
> (forensic substrate). Every row below maps to a verification
> command or an explicit operator action. Status drift between this
> document and the matrix UI is itself a §43 drill condition.

This file is the operator-readable reconciliation of the architecture
matrix the user surfaced on 2026-05-06. The original matrix had ~17
non-✅ rows; iter-33 through iter-42 closed every tractable row with
real code + drill + commit. The remaining gaps are explicit
operator-territory (§42-gated) actions documented at the end.

## Reconciliation

| Layer | Component | Tier-1 status | Verification |
|---|---|---|---|
| Load Balancer | nginx 1.27 | ✅ shipped | `docker-compose ps nginx` |
| Load Balancer | k8s ingress / Istio | ✅ scaffolded — 🟡 cluster-provisioning OPERATOR | manifests + drill ready; cluster missing | `python3 mcp/tests/drill_minikube_istio_setup.py` (15/15) — manifests at `infra/k8s/` + `infra/istio/` (operator action: provision cluster + `kubectl apply`) |
| API Gateway | Go gateway (port 8080) | ✅ shipped | `services/api-gateway/` Go tests + `docker-compose ps api-gateway` |
| API Gateway | gRPC service-to-service | ✅ shipped (iter-40) | `python3 mcp/tests/drill_grpc_codegen_complete.py` |
| Auth | JWT + RBAC + tenant check | ✅ shipped | `services/identity-svc/` Go tests |
| Rate Limiting | Per-IP + per-tenant | ✅ shipped | `python3 mcp/tests/drill_rate_limiter.py` |
| Circuit Breaker | DB + HTTP breakers | ✅ shipped | `python3 mcp/tests/drill_circuit_breaker.py` |
| Policy / PolisAI | Stage-1 policy_check.py | ✅ shipped | `python3 scripts/policy_check.py rules` (12 rules + default-deny) |
| Policy / PolisAI | Stage-2 OPA + Rego | ✅ shipped (was matrix-stale) | `python3 mcp/tests/drill_opa_approval_parity.py` (9/9; both engines parity) |
| Agent Router | Intent + Risk classifier (heuristic) | ✅ Stage-1 | `python3 scripts/agent_router.py --classify "..."` |
| Agent Router | Ollama-backed classifier | ✅ Stage-2 (was matrix-stale) | `agent_router.py:34,58` — Ollama qwen2.5 hook present + PYDANTICAI_ENABLED gate |
| Agent Council | Local council 4-role | ✅ shipped | `python3 scripts/local_council.py --help` |
| Agent Council | 5-role rename (Planner/Retriever/Risk/Evaluator/Writer) | ✅ shipped (iter-34) | `python3 mcp/tests/drill_council_5_role_aliasing.py` (7/7) |
| Execution / LangGraph | LangGraph 1.1.10 DAG | ✅ shipped | `python3 -c "import langgraph; print(langgraph.__version__)"` |
| Paperclip Sandbox | Stage-1 read-only aggregator | ✅ shipped | `python3 mcp/tests/drill_paperclip_stage1.py` |
| Paperclip Sandbox | Stage-2 propose-only loop | ✅ shipped (was matrix-stale) | `python3 mcp/tests/drill_paperclip_stage2_propose.py` (already exists) |
| Paperclip Sandbox | Stage-3 Goal→Plan→Execute→Evaluate→Improve | ✅ shipped (was matrix-stale) | `python3 mcp/tests/drill_paperclip_stage3_dispatcher.py` (already exists) |
| OpenClaw A2A | Stage-1 gate + envelope contract | ✅ Stage-1 | `python3 mcp/tests/drill_safety_approval_council.py` |
| OpenClaw A2A | Stage-2 Dispatch RPC + circuit breaker | ✅ shipped (was matrix-stale) | `openclaw_coordinator.py:405` Stage-2 envelope; gRPC contract via `proto/openclaw/v1/openclaw.proto` (codegen iter-40) |
| MCP Tool Layer | 8 MCP servers | ✅ shipped | `ls mcp/server_*.py \| wc -l` |
| MCP Tool Layer | mcp/server_paperclip.py | ✅ shipped (was matrix-stale) | `python3 mcp/tests/drill_mcp_server_paperclip.py` |
| Local LLM | Ollama 0.3.12 | ✅ shipped | `curl http://localhost:11434/api/tags \| jq '.models \| length'` |
| Council models | qwen2.5 / deepseek-coder / codegemma / codellama | ✅ shipped | `ollama list \| grep -E "qwen2.5\|deepseek-coder\|codegemma\|codellama"` |
| Tier-B Fallback | Claude CLI / Codex CLI | ✅ shipped | `python3 scripts/tier_b_fallback.py --help` |
| RAG / Chunking | Recursive token chunking | ✅ shipped | `python3 mcp/tests/drill_chunking.py` |
| RAG / Embedding | tiktoken + ollama embeddings | ✅ shipped | `python3 mcp/tests/drill_embedding_versioning.py` |
| RAG / Vector DB | Qdrant 1.11 | ✅ shipped | `curl http://localhost:6333/collections \| jq` |
| RAG / Graph DB | Neo4j 5.21 | ✅ shipped | `docker-compose ps neo4j` |
| RAG / Lakehouse | MinIO 2024.10 | ✅ shipped | `docker-compose ps minio` |
| RAG / BM25 | rank_bm25 0.2.2 | ✅ shipped | `python3 -c "import rank_bm25"` |
| RAG / Reranker | scikit-learn cross-encoder | ✅ shipped | `python3 mcp/tests/drill_reranker_protected.py` |
| RAG / Vectorless option | Graph-only retrieval | ✅ shipped (iter-36) | `python3 mcp/tests/drill_rag_vectorless_flag.py` (6/6) |
| Cache | Redis 7.4 | ✅ shipped | `docker-compose ps redis` |
| Event Bus | Kafka 7.6 + Zookeeper | ✅ shipped | `docker-compose ps kafka zookeeper` |
| Event Bus | aiokafka producer/consumer wiring | ✅ shipped (iter-50/51) | Library `libs/py/documind_core/kafka_client.py` (EventProducer + IdempotentConsumer); `services/ingestion-svc` publishes document.lifecycle events; `services/inference-svc` publishes query.generated.v1 events on every successful /api/v1/ask (lifespan iter-50; publish-point iter-51, both drilled). `python3 mcp/tests/drill_inference_svc_kafka_lifespan.py` (7/7) + `python3 mcp/tests/drill_inference_svc_kafka_publish_point.py` (8/8). Operator opt-in via DOCUMIND_KAFKA_BOOTSTRAP. |
| Search | Elasticsearch 8.15 | ✅ shipped | `curl http://localhost:9200/_cat/indices` |
| Search | Kibana 8.15 | ✅ shipped | `docker-compose ps kibana` |
| Search | Filebeat → ES | ✅ shipped | `docker-compose ps filebeat` |
| Service Mesh | Istio | ✅ scaffolded — 🟡 cluster-provisioning OPERATOR | manifests + drill ready; cluster missing | `python3 mcp/tests/drill_minikube_istio_setup.py` (15/15) — manifests at `infra/istio/` (gateway/virtualservice/auth/peer-auth/destinationrule/telemetry) (operator action: same as Load Balancer row) |
| Service Mesh | Kiali 1.86 (mesh viz) | ✅ shipped | `docker-compose ps kiali` |
| Eval / Guardrails AI | Output filtering + jailbreak defense | ✅ shipped (iter-35) | `python3 mcp/tests/drill_eval_engines_stage2.py` (`GUARDRAILS_EVAL_ENABLED=1`) |
| Eval / Ragas | RAG-specific eval (faithfulness, relevance) | ✅ shipped (iter-35) | `python3 mcp/tests/drill_eval_engines_stage2.py` (`RAGAS_EVAL_ENABLED=1`) |
| Eval / Giskard | LLM red-team + bias scan | ✅ shipped (iter-37) | `python3 mcp/tests/drill_eval_lakera_giskard_scaffolds.py` (`GISKARD_SCAN_ENABLED=1`) |
| Eval / Lakera + Rebuff | Prompt-injection defense | ✅ shipped (iter-37) | `python3 mcp/tests/drill_eval_lakera_giskard_scaffolds.py` (`LAKERA_API_KEY`/`REBUFF_ENABLED=1`) |
| Eval / DeepEval | Alternative RAG eval | ✅ shipped (iter-35) | `python3 mcp/tests/drill_eval_engines_stage2.py` (`DEEPEVAL_ENABLED=1`) |
| Security / Snyk | Dep vulnerability scan | 🟡 OPERATOR | `.snyk` + `.github/workflows/snyk.yml` shipped; needs `SNYK_TOKEN` repository secret (operator action: GitHub → Settings → Secrets → New repository secret) |
| Security / Bandit | Python static security | ✅ shipped | CI workflow `.github/workflows/ci.yml` step `Bandit (security)` |
| Security / pip-audit | Python dep audit | ✅ shipped (iter-33) | `python3 mcp/tests/drill_pip_audit_in_ci.py` (6/6 — blocking, drilled) |
| LLM Observability / Langfuse | Prompt/cost tracking | ✅ shipped | `docker-compose ps langfuse` |
| Tracing / Jaeger | Distributed traces | ✅ shipped | `curl http://localhost:16686/api/services \| jq` |
| Tracing / OpenTelemetry | OTel collector + SDK | ✅ shipped | `docker-compose ps otel-collector` |
| Metrics / Prometheus | Time-series metrics | ✅ shipped | `curl http://localhost:9090/-/healthy` |
| Dashboards / Grafana | Viz | ✅ shipped | `docker-compose ps grafana` |
| MLflow | (alt to Langfuse for ML obs) | ⛔ DELIBERATE-NOT-NOW | `docs/architecture/adr/` — Langfuse covers LLM obs per §40 (decision system); MLflow re-evaluation gated on dual-tracking signal demand |

## Operator-territory items

Three rows above marked 🟡 OPERATOR require external resources or
multi-week migration; they are **not autonomous-loop scope**:

### k8s ingress / Istio service mesh
- **Why operator**: requires a Kubernetes cluster (EKS / GKE / AKS / k3s)
  and is a multi-week migration of the docker-compose stack.
- **What's shipped today**: docker-compose stack with nginx + Kiali for
  mesh viz; Go services already containerized + healthcheck'd.
- **Operator action to advance**: provision a cluster, write `infra/k8s/`
  Helm charts (template scaffold per §47.13 cross-reference map),
  apply Istio profile-mesh (already drilled at
  `mcp/tests/drill_kiali_profile_mesh.py`).

### Snyk dep vulnerability scan
- **Why operator**: requires a `SNYK_TOKEN` repository secret to authenticate
  with snyk.io; cannot be set autonomously per §42 (modifying secret stores).
- **What's shipped today**: `.snyk` ignore-allowlist file + GitHub Actions
  workflow `.github/workflows/snyk.yml` with the right action steps.
- **Operator action to advance**: GitHub → Settings → Secrets and variables
  → Actions → New repository secret → `SNYK_TOKEN` = `<value from snyk.io>`.

### MLflow (deliberate-not-now)
- **Why deliberate**: Langfuse covers LLM observability per §40
  (decision system). MLflow's value-add over Langfuse is for classical
  ML experiment tracking — not the current circuitRAG focus.
- **Re-evaluation trigger**: 1+ classical-ML experiment-tracking ask from
  ops; then file ADR for dual-tracking decision.

## How this document stays honest

- Any row flipping ✅ → ⚠️ → ❌ in source state without a corresponding
  matrix update is a §43 drill regression.
- The verification commands are runnable today; if any fails, the row
  is RED in the next snapshot — bit-rot self-detection.
- New rows enter via §47.13 (architecture cross-reference map) +
  §43 drill + this file in the same commit.

## Forensic context

Iter-33 through iter-42 (commits 5e24043..7b2a6e5 + the tail commits
that close iter-37/38-39-40) reconciled this matrix:
- **6 real code-changes** (iter-33, 34, 35, 36, 37, 40) flipped
  "partial" → "shipped" with drill verification.
- **5 matrix-stale corrections** (iter-38, 39, 42, agent_router Stage-2,
  mcp/server_paperclip) — the code had shipped earlier but the matrix
  wasn't updated; verification commands prove current state.
- **3 operator-territory** items (k8s/Istio, Snyk-token, MLflow)
  surfaced explicitly with the action needed.

This file was produced by the autonomous-loop run on 2026-05-06 per
CLAUDE.md §45.4 (no checkbox flips without code).
