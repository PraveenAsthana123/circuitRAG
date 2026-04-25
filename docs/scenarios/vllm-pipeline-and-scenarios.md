# vLLM Pipeline And Scenarios

This document captures the main vLLM serving pipeline, the failure modes that matter in production, and the scenarios worth testing for enterprise RAG and agentic systems.

It is not a generic LLM checklist. It is meant to help reason about:

- model-serving behavior
- throughput and latency
- GPU and memory pressure
- prompt and tokenizer correctness
- multi-model and adapter routing
- reliability and recovery
- observability and governance

## 1. vLLM Serving Pipeline

### Input
- chat/completion request
- prompt or message list
- model identifier
- sampling configuration
- auth, tenant, and correlation metadata

### Output
- generated text or token stream
- usage metadata
- model/version attribution
- structured error if serving fails

### Typical Steps
- receive request from API/gateway
- validate request shape and limits
- resolve target model or adapter
- tokenize prompt/messages
- schedule request inside vLLM engine
- allocate or reuse KV cache
- run generation on GPU
- stream or return final output
- emit metrics, traces, and logs

### Failure Points
- invalid model name or routing target
- tokenizer mismatch
- prompt too large for configured context window
- GPU memory exhaustion
- scheduler starvation under mixed request sizes
- generation timeout or cancellation
- malformed structured output
- model server unavailable

### Metrics
- request count by model
- queue wait time
- generation latency p50/p95/p99
- tokens in / tokens out
- time to first token
- throughput tokens/sec
- cancellation rate
- failure rate by class

## 2. Model Loading Pipeline

### Input
- configured model path, repo, or artifact reference
- runtime settings
- GPU topology
- optional LoRA adapters

### Output
- ready or failed model server instance

### Typical Steps
- start process or pod
- load weights
- initialize tokenizer
- allocate GPU memory
- initialize vLLM engine
- load optional adapters
- expose readiness and health endpoints

### Failure Points
- wrong model path
- incompatible CUDA/runtime build
- insufficient GPU memory
- corrupted or partial model artifact
- adapter load mismatch
- readiness endpoint reports healthy too early

### Metrics
- cold-start time
- warm-start time
- model-load failure count
- GPU memory reserved on startup
- readiness delay

## 3. Core Serving Scenarios

- single prompt completion
- chat completion with role-formatted input
- streaming token generation
- non-streaming full-response generation
- batch inference
- concurrent mixed-size requests
- cancellation during streaming
- timeout during long generation
- long-context inference near limit
- multi-tenant inference on shared serving tier

## 4. Model Loading Scenarios

- cold start model load
- warm restart after healthy shutdown
- model load failure from bad path or revision
- insufficient GPU memory on startup
- quantized model load
- LoRA adapter load
- multiple model serving on same cluster
- wrong adapter or missing adapter selected

## 5. Performance Scenarios

- high-QPS burst
- sustained throughput load
- short prompt and short output
- short prompt and long output
- long prompt and short output
- long prompt and long output
- large batch efficiency
- mixed prompt-size fairness
- KV cache pressure under concurrency
- context window near configured limit
- GPU memory fragmentation
- queue buildup from slow long-context requests

## 6. Reliability Scenarios

- vLLM process crash during traffic
- generation fails mid-request
- caller timeout while server continues generating
- upstream retry causes duplicate work risk
- OOM during inference
- health endpoint says ready while serving is degraded
- model server unreachable
- rolling deployment with live traffic
- degraded fallback to alternate model/provider
- circuit breaker opens after repeated vLLM failures

## 7. Tokenization And Prompt Scenarios

- malformed prompt input
- tokenizer mismatch after model change
- special token handling
- stop sequence correctness
- max-token enforcement
- prompt truncation policy
- system/user/assistant role formatting
- prompt injection content inside retrieved context
- structured-output prompt with tight formatting requirements

## 8. Sampling And Output Scenarios

- deterministic generation with `temperature=0`
- stochastic generation with sampling enabled
- top-k variation
- top-p variation
- repetition-penalty impact
- stop-token exact termination
- max-token cut-off
- empty output or low-information output
- malformed JSON or schema-violating output

## 9. Multi-Model And Adapter Scenarios

- base model only
- base model plus LoRA adapter
- tenant-specific adapter routing
- wrong adapter selected
- adapter missing
- model switch by feature flag
- shadow traffic to alternate model
- staged rollout of new model revision

## 10. Infrastructure Scenarios

- single-GPU serving
- multi-GPU tensor parallel serving
- autoscaling under load
- node eviction or restart
- GPU unavailable on one node
- CUDA or driver mismatch
- container image mismatch
- model cache miss on startup
- slow network-attached model storage

## 11. Security And Governance Scenarios

- unauthorized model access
- tenant-isolated routing enforcement
- prompt logging redaction
- PII in prompt or retrieved context
- policy block before request reaches vLLM
- audit request metadata with model attribution
- enforce per-tenant or per-feature model allowlist

## 12. Observability Scenarios

- end-to-end trace from gateway to vLLM
- per-model latency dashboard
- token-usage dashboard
- GPU utilization dashboard
- queue-wait visibility
- failed generation classification
- model-load status visibility
- deployment/version attribution in logs and metrics
- drift after prompt or model config change

## 13. RAG-Specific vLLM Scenarios

- retrieved context too large for context window
- context truncation changes answer quality
- citation-heavy prompt with large context
- answer generation after poor retrieval
- reranked top-k changes output quality
- prompt template update changes latency or token cost
- fallback model used when primary vLLM is unavailable
- long-document summarization through vLLM
- tool-calling prompt sent to vLLM-compatible endpoint

## 14. Evaluation Scenarios

- prompt A versus prompt B on same model
- model A versus model B on same prompt
- latency, cost, and quality tradeoff comparison
- regression after model version change
- regression after quantization change
- drift in faithfulness after retrieval or chunking change
- canary evaluation before full rollout
- shadow comparison on production-like traffic

## 15. Failure And Recovery Scenarios

- process crash and automatic restart
- pod restart and readiness recovery
- model reload after failure
- OOM and automatic recovery
- request queue drains after traffic spike
- breaker opens during outage and closes after recovery
- fallback provider handles traffic during outage
- rolling deploy recovers without dropping healthy traffic

## 16. Highest-Value Enterprise RAG Scenarios

1. cold start versus warm-start latency
2. high concurrency under mixed prompt sizes
3. long-context near-limit behavior
4. OOM and GPU memory pressure handling
5. streaming correctness and cancellation
6. rolling deployment with no bad traffic loss
7. fallback when vLLM is unavailable
8. prompt or model regression after change
9. per-tenant routing or adapter selection
10. observability of queue wait, tokens, latency, and GPU usage

## 17. Good Metrics To Track

- request count by model and tenant cohort
- success, timeout, cancel, and error counts
- latency p50/p95/p99
- time to first token
- tokens in and tokens out
- queue wait time
- GPU memory utilization
- GPU compute utilization
- model load duration
- cold-start frequency
- fallback-to-secondary-model count
- breaker open/reject counts if protected by breaker

## 18. Best Drill And Test Priorities

Start with the scenarios most likely to hurt production quality or uptime:

1. model server unavailable -> fallback path works
2. long-context request near limit -> truncation and latency remain controlled
3. mixed short and long requests -> queue fairness is acceptable
4. streaming request cancelled mid-generation -> cleanup is correct
5. model revision change -> latency and output regression detection works
6. OOM path -> service recovers safely and metrics are visible
7. per-tenant or per-feature routing -> correct model or adapter chosen
8. end-to-end tracing and token accounting -> visible in dashboards

---

## 19. How This Maps To DocuMind Today

DocuMind currently routes inference through **Ollama**, not vLLM:

- Embeddings: `nomic-embed-text` via `OllamaEmbedderClient`
  (see `services/retrieval-svc/app/services/embedder_client.py`).
- Chat completion: `llama3.1:8b` via the inference service
  (see `services/inference-svc/app/services/rag_inference.py`).

The scenarios above are deliberately **provider-agnostic** — when
this stack migrates from Ollama to vLLM (or adds vLLM as a
fallback), the catalog stays usable. Below is a quick mapping of
the most relevant scenario classes to where they live in the
current repo, and what's missing.

### Already covered

| Scenario | Where in repo |
| --- | --- |
| Model server unreachable → CB opens → degraded path | `mcp/client.py`, `libs/py/documind_core/circuit_breaker.py`, `drill_breaker_transitions` |
| Per-request idempotency cache | `mcp/idempotency.py` (Postgres-backed), `drill_idempotency_durable` |
| Tenant-isolated routing (data layer) | `services/retrieval-svc/app/services/vector_searcher.py`, `drill_retrieval_tenant_isolation` |
| Degraded retrieval signal in response envelope | `RetrieveResponse.degraded`, `drill_retrieval_degraded_envelope` |
| Request tracing (correlation_id end-to-end) | `libs/py/documind_core/middleware.py`, `SpanAttributeMiddleware` |
| Auth + scope enforcement before tool call | `libs/py/documind_core/auth.py`, `mcp/server_common.enforce_scope` |
| Audit chain on sensitive actions | `libs/py/documind_core/audit.py`, `drill_audit_*` |

### Gaps surfaced (good loop candidates)

| Area | Gap |
| --- | --- |
| Eval pipeline | No baseline for prompt/model regression detection. |
| Prompt redaction | Prompts may carry PII into logs without scrubbing. |
| Token-usage metric | Counts logged but not exposed as a Prometheus series. |
| Generation audit | Tool calls audited; raw generation requests are not. |
| Streaming + cancellation | Not surfaced in the current API. |
| Health depth | Health endpoints don't probe model readiness. |
| Fallback model | No secondary provider wired when Ollama is down. |
| Per-tenant model routing | Single model today; would need a registry first. |

### Drills that exist for the analogue

| vLLM scenario | Existing DocuMind drill (Ollama analogue) |
| --- | --- |
| Breaker opens on repeated failure | `drill_breaker_transitions` |
| Idempotent retry returns cached | `drill_idempotency_durable` |
| Tenant filter is enforced | `drill_retrieval_tenant_isolation` |
| Partial-result envelope | `drill_retrieval_degraded_envelope` |
| Worker auto-reject after N failures | `drill_worker_auto_reject` |

When vLLM lands as primary or fallback, the same drill SHAPES port
over — same negative-assertion structure, same observability
contract. The provider name in the metric labels changes; the
assertions don't.
