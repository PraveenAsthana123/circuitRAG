# What's missing — state-of-art gap analysis

> Honest inventory of every advanced AI/LLM component the operator
> referenced. Companion to `docs/STATUS.md` (current state) — this
> file documents the **distance to top-tier**.
>
> Verdict: **NOT top 1% / NOT state-of-art** — this is a **mid-tier
> platform with strong governance + safety patterns, missing the
> heavy-hitter inference/eval/guardrails frameworks that distinguish
> state-of-art enterprise AI**.
>
> Locked by `mcp/tests/drill_missing_inventory.py`.

## Inference performance

### vLLM (high-throughput LLM serving)
**Status**: ❌ **not present**. Project uses Ollama (llama.cpp backend).
- vLLM gives 2-24× higher throughput via PagedAttention + continuous batching
- Critical for >100 concurrent users; Ollama serializes requests per model
- **What it would take**: vLLM container in compose with `profiles: [gpu]`; GPU + CUDA toolchain; switch sidecar-advisor + agent-orchestrator client config to point at vLLM endpoint
- **Effort**: 2-3 iterations + GPU-host operator setup
- **Documented?**: `/admin/llmops/deep` mentions vLLM as planned

### TensorRT-LLM
**Status**: ❌ **not present**. NVIDIA-specific inference optimizer.
- ~1.5-2× speedup over vLLM on NVIDIA hardware
- Requires CUDA + specific NVIDIA GPU class (Hopper / Ampere ideal)
- **What it would take**: model conversion via `trtllm-build`; container that bundles TensorRT runtime; same client-config swap as vLLM
- **Effort**: substantial — model rebuild per LLM swap

### ONNX Runtime
**Status**: ❌ **not present**. Cross-platform inference (CPU/GPU/edge).
- Useful for shipping models to non-server environments (browser, mobile, embedded)
- Not relevant for current server-only deployment
- **Verdict**: SKIP unless edge/mobile requirement emerges

### MLC-LLM
**Status**: ❌ **not present**. Apache TVM-based; targets WebGPU + mobile.
- Niche: useful when shipping LLMs to user devices (browser-side inference)
- **Verdict**: SKIP for server-side platform

### LLVM IR / MLIR
**Status**: ❌ **not relevant**. Compiler infrastructure for building inference engines.
- This project consumes inference; doesn't compile LLMs.
- **Verdict**: SKIP — not in scope.

### KV cache management
**Status**: ⚠ **implicit (Ollama handles internally)**.
- Ollama uses llama.cpp's automatic KV cache; no explicit policy
- vLLM exposes PagedAttention with explicit cache management
- For long-context workloads, explicit cache policy matters
- **What it would take**: switching to vLLM (kv-cache becomes first-class)

### Memory / RAM management
**Status**: ⚠ **basic Redis cache, no LLM-specific tuning**.
- Per-tenant cache eviction not implemented
- Token-budget tracking partial (drill_token_budget exists; no enforcement)
- **What it would take**: token-budget middleware + per-tenant eviction in cache.py

## Evaluation frameworks

### Ragas (RAG evaluation)
**Status**: ❌ **not present**. The de-facto RAG eval framework.
- Computes faithfulness / answer relevance / context precision per query
- evaluation-svc/app/metrics/ has token-overlap proxies (not real Ragas)
- **What it would take**: `pip install ragas` + wrap retrieval-svc responses + drill
- **Effort**: 1 iteration
- **Recommended**: HIGH PRIORITY for any RAG platform

### Deepeval
**Status**: ❌ **not present**. End-to-end LLM eval framework with rubrics.
- LLM-as-judge with calibrated rubrics
- Pytest-style test cases for LLM outputs
- **What it would take**: `pip install deepeval` + golden test suite; integrate with CI
- **Effort**: 2 iterations (framework wiring + golden suite authoring)

### G-Eval (LLM-as-judge with chain-of-thought)
**Status**: ❌ **not present**. Subset of Deepeval; runnable independently.
- Evaluates LLM outputs against criteria with CoT reasoning
- **Verdict**: ships as part of Deepeval; pull both together

### Eval golden set
**Status**: ⚠ **documented as PLANNED**.
- `/admin/output-eval/deep#evaluation-harness` documents the framework
- evaluation-svc has REST API but no formal golden-set committed
- **What it would take**: commit `tests/golden_sets/sidecar_council_v1.jsonl` + CLI runner + CI hook
- **Effort**: 2 iterations

## Guardrails / Safety frameworks

### Guardrails AI
**Status**: ❌ **not present**. The Python `guardrails-ai` package.
- Validators for tone, PII, format, custom rules
- Reasks the LLM if output fails validation
- **What it would take**: `pip install guardrails-ai` + add validators to sidecar-advisor LLM call sites + drill
- **Effort**: 1-2 iterations
- **Recommended**: HIGH PRIORITY for production LLM platform

### NeMo Guardrails (NVIDIA)
**Status**: ❌ **not present**. Programmable guardrails via Colang.
- Topic-level dialog policy (input rails / output rails / dialog rails)
- Heavier than Guardrails AI; more expressive
- **What it would take**: Colang ruleset + NeMo container + integration; drill
- **Effort**: 3 iterations
- **Recommended**: medium priority — value scales with agent count

### Built-in guardrails (this repo)
**Status**: ⚠ **documentation + drills, no active validation library**.
- `/admin/guardrails/deep` documents the 3-layer pattern (input / output / behavior)
- `drill_guardrail_otel_attributes` locks observability of guardrail triggers
- libs/py/documind_core/ai_governance.py has basic PII redaction
- **Gap**: no active package wraps LLM calls; relies on prompt-engineering + post-hoc check
- **Recommended**: replace prompt-engineering with Guardrails AI

## Interpretability / Explainability

### SHAP (per-prediction feature attribution)
**Status**: ❌ **not present**. Industry-standard feature importance.
- Per-decision attribution for ML predictions
- For LLM/RAG: would need adaptation (no native LLM SHAP)
- **What it would take**: `pip install shap` + wrapper for evaluation-svc decisions
- **Effort**: 2 iterations
- **Verdict**: useful only if classical-ML decisions exist (this project's are mostly LLM-shaped)

### LIME (local interpretable model-agnostic)
**Status**: ❌ **not present**. Same family as SHAP.
- **Verdict**: SKIP — overlap with SHAP; pick one

### Captum (PyTorch interpretability)
**Status**: ❌ **not present**.
- Useful only if PyTorch models are deployed (currently all LLM via Ollama)
- **Verdict**: SKIP unless custom PyTorch models added

### LIT (Language Interpretability Tool, Google)
**Status**: ❌ **not present**.
- Browser UI for LLM probe experiments
- **Verdict**: nice-to-have for research; not production-grade

### This repo's interpretability
**Status**: ⚠ **citation discipline + audit trail only**.
- `/admin/explainability/deep` documents §48 explainability policy
- Council pattern + citation-resolver provide reproducibility (`.loop/issue_audit.jsonl`)
- **Gap**: no per-decision feature-level attribution
- **What it would take for top-tier**: pair Ragas (faithfulness scores) + Deepeval (LLM-judge rubrics) + audit chain → composite interpretability

## Agentic / A2A protocols

### LangGraph
**Status**: ✅ **shipped + exact-pinned**.
- agent-orchestrator-svc uses langgraph 1.1.10
- Drill locks the pin

### A2A (Agent-to-Agent protocol — e.g. Google's A2A spec)
**Status**: ⚠ **in-process council pattern only**.
- sidecar-advisor council = author + reviewer + advisor (in-process function calls)
- No formal A2A protocol layer (HTTP-based agent invocation with capability discovery)
- **What it would take**: Implement A2A spec OR adopt LangGraph's multi-agent / OpenAI's swarm pattern
- **Effort**: 3-5 iterations
- **Verdict**: only worth it when agents need to run in separate processes

### MCP (Model Context Protocol — Anthropic)
**Status**: ✅ **partial — 3 servers shipped**.
- mcp/server_drills.py + server_hr.py + server_itsm.py
- Built on mcp/server_common.py (auth + scopes + traces + idempotency)
- 8 more candidate servers identified in earlier exploration (orchestrator, sidecar, evaluation, etc.)
- **Recommended**: extend MCP fleet (highest-leverage agent-protocol work)

### Multi-agent orchestration patterns
**Status**: ⚠ **single pattern (council) implemented**.
- More patterns exist: planner+executor (already in agent-orchestrator), debate, society-of-mind, hierarchical
- This project uses council for sidecar; planner+executor for orchestrator
- **Recommended**: ADR documenting which pattern to use when

## Governance / Responsible AI

### Open-source AI governance tools

| Tool | Status |
| --- | --- |
| **MLflow** (model registry + experiment tracking) | ❌ not present; evaluation-svc + audit_log are partial substitutes |
| **Aporia** / **Arize** / **WhyLabs** (model monitoring SaaS) | ❌ not present |
| **EvidentlyAI** (open-source ML monitoring) | ❌ not present |
| **Giskard** (open-source LLM testing + scanning) | ❌ not present |
| **deepchecks** (test suite for ML/LLM) | ❌ not present |
| **fiddler-ai** (explainability + monitoring) | ❌ not present |

**Verdict**: this repo's governance is bespoke (audit_log_partitioned + drill catalog + ratchet pattern + decision audit per §38). Comparable in shape to enterprise tooling but project-specific. **Adopting MLflow + EvidentlyAI would give industry-standard surfaces** (model registry visible to MLOps tools, monitoring dashboards readable by external tooling).

### Responsible AI
**Status**: ⚠ **documented as design** (`/admin/explainability/deep`, ADR-018, §48).
- 3 layers: input validation, output validation, behavior validation
- Citation discipline as mechanical hallucination guardrail (proven in council)
- **Gap**: no formal Responsible AI framework integration

### Ethical AI
**Status**: ⚠ **policy-level only** (CLAUDE.md §50.5 safety gate).
- All security findings → human-review
- Real-bug rules (mypy attr-defined, eslint rules-of-hooks) → human-review
- **Gap**: no fairness testing, no bias detection across demographic groups

### Portable AI
**Status**: ⚠ **partial** (FastAPI + standard formats).
- All services use OpenAPI; portable across clients
- Pinned dependencies (langgraph, langchain-core)
- **Gap**: no model export to ONNX / GGUF for redeployment

### Performance AI
**Status**: ✅ **k6 load testing shipped this iteration**.
- 5-phase profile (smoke + load + stress + soak + spike)
- SLO thresholds enforced; drill locks them
- **Gap (cited above)**: no vLLM/TensorRT for higher throughput at the LLM layer

### Debug AI
**Status**: ✅ **correlation_id-led triage shipped**.
- /admin/forensics for trace → draft → audit → HITL chain
- Audit row per LLM invocation in `.loop/issue_audit.jsonl`
- **Gap**: no LLM-specific tracing (Langfuse just shipped — fills this)

## Backward / forward compatibility

### Backward compat (existing clients keep working)
**Status**: ⚠ **policy documented, not enforced**.
- Per global §28: new fields with defaults; never remove fields
- ADR-009 worker-auto-reject (graceful degradation)
- **Gap**: no contract tests assert backward compat per release

### Forward compat (new clients work with old servers)
**Status**: ⚠ **API-versioned (v1) but no formal forward-compat tests**.
- /api/v1/* prefix everywhere
- **Gap**: no JSON schema with optional+ignored unknown fields verified

### What top-tier needs
- **Pact** or **schemathesis** for contract testing
- **schemaregistry** (Confluent or Apicurio) for event versioning
- **Backward-compat drill** — per-PR check that old clients still parse new responses
- **Effort**: 2 iterations

## What's actually distinguishing this repo

The repo IS top-tier in:
- **Drill testing pattern**: 100+ readonly drills locking real-stack behavior with NEGATIVE markers
- **Ratchet discipline**: KNOWN_*/DOMAIN_* floors that walk to match observed reality (ADR-015)
- **Citation discipline**: every council answer must cite chunk_ids; verifier resolves
- **Audit-row-per-LLM-call** (§38)
- **Multi-model council pattern** with empirical validation (E402: single-model wrong → council right)
- **Convergent-work pattern** (ADR-022): autonomous-loop + parallel-tool produce byte-identical artifacts

These are **bespoke patterns competitive with state-of-art**. The gap to top-1% is mostly the integration of standard frameworks (Ragas, Guardrails AI, MLflow, vLLM) — not architectural reinvention.

## Recommended adoption order (highest ROI first)

1. **Langfuse** ✅ (just shipped this session) — LLM observability
2. **Guardrails AI** — input/output validation library; 1-2 iterations
3. **Ragas** — RAG eval framework; 1 iteration
4. **MLflow** — model registry visible to external MLOps tooling; 2 iterations
5. **Deepeval** — pytest-style LLM tests in CI; 2 iterations
6. **EvidentlyAI** — open-source monitoring dashboards; 2 iterations
7. **Giskard** — LLM scanning for bias/regression; 2 iterations
8. **NeMo Guardrails** — programmable dialog policy via Colang; 3 iterations
9. **vLLM** — high-throughput inference (operator GPU host required); 2-3 iterations + GPU setup
10. **A2A protocol layer** — only when multi-process agent fleet emerges; 3-5 iterations

After items 1-7, the repo would be **competitive with state-of-art enterprise AI platforms**. Items 8-10 are differentiators where each adds specialized value depending on requirement.

## What's definitely NOT missing (and why)

- **Architectural diagrams**: 4 C4 levels + 28+ deep-dive pages cover this exhaustively
- **CI gates**: ruff + mypy + bandit + pytest all hard-gated
- **Test catalog**: 100+ drills > most production AI platforms
- **Audit trail**: §38 audit_row + LangFuse + correlation_id propagation = regulator-readable
- **Safety gates**: §50.5 (security → human-review) + §48 (explainability evidence) + multi-model council

## RAG component primitives — what landed in `libs/py/documind_core`

After the 2026-04-30 "implement all" pass, these primitives are
now first-class shared library code rather than scattered across
service boilerplate. Each is at ≥97% test coverage:

| Component | Module | Pattern (per playbook §7) | Coverage |
|---|---|---|---|
| Multi-strategy chunking (7 strategies) | `chunking.py` | Strategy + Factory | 98% |
| Top-K min-heap helper | `fusion.top_k` | Heap | 100% |
| Reciprocal Rank Fusion (hybrid retrieval) | `fusion.reciprocal_rank_fusion` | Greedy + dict accumulator | 100% |
| MMR (post-retrieval diversification) | `mmr.py` | Greedy + similarity matrix | 97% |
| Multi-pattern PII scanner (Aho-Corasick-style) | `pii.py` | Combined-regex DFA + Luhn | 96% |
| Token counting + budget packing | `tokens.py` | Greedy pack | 100% |
| Pre-retrieval query rewriter | `query_rewriter.py` | Composable normalizer + expander + acronym detect | 100% |

These plus the 12 prior 100%-covered modules (encryption, rate_limiter,
schemas, logging_config, cache, audit, config, db_client, exceptions,
body_limit, idempotency, dispatch_pool) push project coverage to ~65%.

### Still missing primitives (next iteration candidates)

| Primitive | Module name | Why deferred |
|---|---|---|
| Semantic cache (HNSW+threshold) | `semantic_cache.py` | Needs HNSW lib pin (faiss/hnswlib) |
| Embedding cache with model-versioned keys | `embedding_cache.py` | 1-line on top of existing `cache.py` |
| Code-aware chunking | `chunking_code.py` | Needs tree-sitter binding |
| Table-aware chunking | `chunking_table.py` | Needs PDF/HTML table parser |
| Hierarchical chunking | `chunking_hierarchical.py` | Builds on `recursive` + parent_id |
| Streaming citation linker | `citations.py` | Needs claim segmentation |

## Cloud-readiness — what works on AWS / Azure / GCP today vs needs work

The repo is local-first by design (Ollama, Docker Compose, on-disk
SQLite for sidecar advisor). Going to cloud is mostly about
swapping the per-provider building blocks. Component-by-component:

| Component | Local default | AWS swap | Azure swap | GCP swap | Effort |
|---|---|---|---|---|---|
| LLM inference | Ollama (llama.cpp) | Bedrock / SageMaker | Azure OpenAI | Vertex AI | 1 iter — provider abstraction already exists in `inference-svc` |
| Embeddings | Ollama nomic-embed | Bedrock Titan / OpenAI | Azure OpenAI ada | Vertex textembedding | 1 iter via env config |
| Vector DB | Qdrant container | OpenSearch + KNN, pgvector RDS | AI Search | Vertex Matching Engine | 1-2 iters per provider (`vector_searcher.py` is the seam) |
| Graph DB | Neo4j container | Neptune | Cosmos Gremlin | (none managed) | 1-2 iters |
| Vectorless RAG | Elasticsearch container | OpenSearch | Cognitive Search | Vertex Search | 1-2 iters |
| Object storage | MinIO | S3 | Azure Blob | GCS | 1 iter — already S3-API compatible |
| Postgres | local container | RDS | Azure DB for Postgres | Cloud SQL | 1 iter — DSN swap |
| Redis | local container | ElastiCache | Azure Cache | Memorystore | 1 iter — URL swap |
| Kafka | local container | MSK | Event Hubs (Kafka) | Confluent Cloud | 1 iter — bootstrap servers |
| OTel collector | local | ADOT | App Insights / Azure Monitor | Cloud Trace | 1 iter — exporter swap |
| Prometheus | local | Managed Prometheus / CloudWatch | Azure Monitor | Cloud Monitoring | 1 iter |
| Grafana | local | Managed Grafana | Azure Managed Grafana | (use Cloud Monitoring) | 1 iter |
| API gateway | NGINX / api-gateway svc | API Gateway / ALB | API Management / App Gateway | API Gateway / Cloud LB | 2 iters — replace ingress definitions |
| Service mesh | Istio (config-shipped) | App Mesh / Istio EKS | Open Service Mesh | Anthos Service Mesh | 2-3 iters |
| Auth | Local JWT keys | Cognito / IAM | Azure AD / Entra ID | Identity Platform / IAP | 2-3 iters |
| Secrets | env files (chmod 600) | Secrets Manager / Parameter Store | Key Vault | Secret Manager | 1 iter — already abstracted via env loader |
| KMS / encryption keys | local Fernet key | KMS | Key Vault HSM | Cloud KMS | 1 iter — `encryption.py` swap |
| TLS / certs | self-signed | ACM | Front Door / App Gateway | Cloud LB | 1 iter |
| Container runtime | Docker Compose | EKS / ECS | AKS | GKE | 1-2 iters — k8s manifests already in `infra/k8s/` |
| Workflow / batch | bash scripts in `scripts/` | Step Functions / Batch | Logic Apps / Batch | Workflows / Batch | 2 iters |

### Cloud-readiness summary

- **All major components have a provider seam already**: vector / graph / search / inference are abstracted as `<thing>_searcher.py` per §47 architecture conventions
- **Secrets pattern is portable**: env-file → cloud-secret-store is a 1-liner per provider
- **No vendor-locked APIs in business code**: governance / audit / policy is pure Python
- **k8s manifests already shipped** under `infra/k8s/` — drop-in for any managed-k8s offering
- **Istio config shipped** — drop-in for App Mesh / OSM / Anthos via `infra/istio/`
- **Cloud-specific gaps**: no Terraform, no Helm chart per environment, no OIDC per cloud — these are 2-3 iter add-ons

### What WOULDN'T just work on cloud

- **Local-disk SQLite** in sidecar-advisor — needs cloud DB swap (uses litestream replication or just Postgres)
- **Hardcoded `localhost` ports** in some scripts — already paramaterizable via env, but a few scripts assume local
- **GPU-bound inference** — Ollama can run on EC2 GPU instances but containerizing CUDA is a separate rabbit hole; vLLM cloud variant is cleaner

### Recommended cloud rollout order

1. Storage layer (S3/Blob/GCS, RDS Postgres, ElastiCache) — 1 iteration
2. Inference (Bedrock/Azure OpenAI/Vertex behind same API) — 1 iteration
3. Vector + graph (managed equivalents) — 1-2 iterations
4. Observability (managed OTel/Prom/Grafana) — 1 iteration
5. Auth (Cognito/Entra/Identity Platform) — 2-3 iterations
6. Container runtime (EKS/AKS/GKE) — 1-2 iterations
7. Service mesh + ingress + secrets manager — 2-3 iterations
8. CI/CD per cloud (CodePipeline / Azure DevOps / Cloud Build) — 1-2 iterations

**Total to fully-managed cloud deployment: ~12-18 iterations of focused work, mostly seam-swapping rather than rewrites.**

## Brutal rule

> Top 1% AI platforms are not built by inventing architecture; they
> are built by integrating standard frameworks (vLLM, Ragas,
> Guardrails AI, MLflow, NeMo) on top of solid governance + audit +
> drill discipline. This repo has the latter — the work to top-1%
> is mostly the integration list in "Recommended adoption order"
> above. Each is a 1-3 iteration item; the architectural reinvention
> is already done.
>
> Cloud portability is similarly mostly seam-swapping. Every
> external dependency has a provider abstraction file
> (`<thing>_searcher.py`, `<thing>_client.py`, env-driven config)
> so going AWS / Azure / GCP is configuration + manifest work,
> NOT business-logic rewrites.
