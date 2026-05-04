# Techstack install sweep — 2026-05-04

Operator request: "setup all expect kubernat" — install every missing
tool from the mandatory + optional stack except Kubernetes (kubectl,
istioctl, ArgoCD CLI). Per CLAUDE.md §42 + bypassPermissions setting.

## Stack delta — before vs after

### Mandatory tools

| Tool | Before | After | Notes |
|------|--------|-------|-------|
| LangGraph | ✅ | ✅ | py:langgraph |
| **CrewAI** | ❌ rejected | ❌ rejected | Per techstack-eval: name-collision risk + bus-factor 1; explicitly skipped |
| **Langfuse** | ❌ | ✅ | py:langfuse |
| Istio | ❌ | ❌ skipped | Requires K8s; per operator instruction |
| Ollama | ✅ 0.13.5, 14 models | ✅ unchanged | |
| **RAGAS** | ❌ | ✅ 0.4.3 | py:ragas (required mistralai>=1.0,<2.0 pin to fix instructor compat) |
| **Guardrails** | ❌ | ✅ | py:guardrails-ai |
| **API gateway** (Envoy) | ❌ | ✅ | docker container documind-envoy on :58080 (admin :58081) |
| PostgreSQL | ✅ healthy 10d | ✅ unchanged | port 55432 |
| Redis | ✅ healthy 10d | ✅ unchanged | port 56379 |
| Qdrant | ⚠ unhealthy probe | ⚠ same (app /healthz green) | port 6333 |
| **OpenSearch** | ❌ | ✅ green 1-node cluster | docker container documind-opensearch on :59200, admin :59600 |
| Docker | ✅ | ✅ unchanged | |
| Kubernetes (kubectl) | ❌ | ❌ skipped | per operator |
| **Vault** | ❌ | ✅ 1.18.0 | binary at ~/.local/bin/vault |
| OTel + Prometheus + Grafana | ✅ | ✅ unchanged | |

### Optional tools (bonus)

| Tool | Before | After |
|------|--------|-------|
| **MLflow** | ❌ | ✅ py:mlflow |
| **LlamaIndex** | ❌ | ✅ py:llama_index |
| **Haystack** | ❌ | ✅ py:haystack |
| **AutoGen** | ❌ | ✅ via ag2 (`pyautogen` deprecated; AutoGen renamed to ag2) |
| **Ray** | ❌ | ✅ py:ray |
| **Temporal** | ❌ | ✅ py:temporalio |
| **DVC** | ❌ | ✅ py:dvc |
| **DeepEval** | ❌ | ✅ py:deepeval |
| **LiteLLM** | ❌ | ✅ py:litellm |
| **PydanticAI** | ❌ | ✅ py:pydantic_ai |

### Security tooling

| Tool | Before | After | Use |
|------|--------|-------|-----|
| **OPA** | ❌ | ✅ 0.68.0 | policy-as-code (Rego eval) |
| **Conftest** | ❌ | ✅ 0.55.0 | OPA test runner |
| **Syft** | ❌ | ✅ 1.44.0 | SBOM generation |
| **Cosign** | ❌ | ✅ 2.4.0 | container image signing |
| **Trivy** | ❌ | ✅ 0.70.0 | container vulnerability scan |
| **GitHub CLI** | ❌ | ✅ 2.55.0 | gh PR/issue automation |
| **Promptfoo** | ❌ | ✅ npm-global | prompt eval / red-team |

## Skipped (per operator instruction "expect kubernat")

- **kubectl** — k8s client
- **istioctl** — service mesh CLI (requires k8s)
- **ArgoCD CLI** — GitOps for k8s

## Skipped (explicit policy decision)

- **CrewAI** — rejected via techstack-eval (name-collision typosquat risk; bus-factor 1)

## Live verification — all green

```bash
# Python deps
for m in ragas guardrails langfuse litellm pydantic_ai deepeval mlflow \
         llama_index haystack autogen temporalio dvc ray; do
  .venv/bin/python3 -c "import $m" && echo "  ✓ $m"
done
# → all 13 ✓

# Binaries
for b in vault opa conftest syft cosign trivy gh promptfoo; do
  command -v $b && $b --version 2>&1 | head -1
done
# → all 8 ✓

# Docker
docker ps --format "table {{.Names}}\t{{.Status}}"
# → opensearch, envoy, postgres, redis, qdrant, kafka, neo4j, minio,
#   grafana, prometheus, jaeger, otel-collector all up
```

## Quirks caught during install

1. **Mistralai version conflict** — RAGAS depends on `instructor` which expects `from mistralai import Mistral`. mistralai 0.4.x exports nothing at top-level; mistralai 2.x has different API. Pin to `mistralai>=1.0,<2.0` resolves.

2. **AutoGen package rename** — `pyautogen` is now deprecated; the package is `ag2` and still imports as `autogen`. Installing `ag2` directly is the modern path.

3. **Trivy URL** — `aquasecurity/trivy/releases/download/v0.55.0/...` returned 404. The latest release URL pattern needed `v0.70.0`. Used GitHub API `/repos/aquasecurity/trivy/releases/latest` to discover the current asset URL.

4. **OpenSearch + Envoy network** — initial run failed with "network rag_default not found". Correct network is `documind` (per `docker network ls`).

5. **OpenTelemetry version drift** — pip install introduced opentelemetry-instrumentation-* 0.62b0 alongside 0.60b1 still pinned. Warnings only; no functional break (verified by service ingest still working post-install).

6. **Ingestion-svc rate limit** — discovered during deep RAG test: 10 uploads per tenant per window. Not an install issue; documented in `rag-deep-test-2026-05-04.md`.

## Composes with

- `scripts/techstack_audit.py` — checks each entry on the canonical list
- `~/.kaggle/kaggle.json` — credentials per global §36 (used in deep RAG test)
- `~/.local/bin/` — operator-local binary install path
- `/mnt/deepa/rag/.venv/` — project venv for Python deps
- `docs/architecture/rag-deep-test-2026-05-04.md` — empirical pipeline test using newly-installed corpus
- §42 — operational autonomy (this install was pre-approved per the policy)
- §47.7 — Kubernetes 3-probe pattern (Istio installation deferred until K8s migration)
- §52 — brutal tool review (each new tool gets a 40-row review when adopted into actual codebase)
- §56 — techstack additions policy (formal 6-gate adoption process)

## Outstanding follow-ups

- **Configure** the new tools — installation ≠ wired-up. Each needs:
  - **Langfuse**: project + host config + LANGFUSE_PUBLIC_KEY env var
  - **RAGAS**: hook into evaluation-svc; decide which metrics (faithfulness, answer_relevancy, context_precision)
  - **Guardrails**: define rule pack; wire to inference-svc input/output filters
  - **Envoy**: route config (currently default — empty); needs upstream cluster definitions
  - **OpenSearch**: index template; integrate with retrieval-svc as hybrid backend
  - **Vault**: dev-mode init; migrate secrets from .env files
  - **MLflow**: tracking URI; hook training pipelines
  - **Temporal**: server (separate container) + worker registration

- **§52 brutal-review** of each new tool: 40-row checklist against the active integration

- **§56 6-gate** formal adoption tracking: tool-evaluation page, Stage-1 adapter, drill, doc, etc.

## The brutal rule

> Installing 21 tools is the easy 5%. The remaining 95% is configuring,
> wiring into the request hot path, validating with drills, and proving
> they actually deliver value over the in-house alternatives. This doc
> records install state. Trust signals come from the integration
> drills + production validation that come next.
