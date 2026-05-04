# Compression / Optimization tool audit — 2026-05-04

Operator-supplied table of 19 LLM context / compression / optimization
tools. Audit + install. Per CLAUDE.md §42 + bypassPermissions.

## Table audit — install state

| # | Tool | Category | Installed? | Module / Binary |
|---|------|----------|-----------|-----------------|
| 1 | **TOON** | Structural compression | ❌ research only | No PyPI package; spec / format only |
| 2 | **ONTO** | Research format | ❌ research only | Not on PyPI |
| 3 | **LLMLingua** | Token compression | ✅ 0.2.2 | `py:llmlingua` |
| 4 | **LongLLMLingua** | RAG optimization | ✅ | `py:llmlingua.prompt_compressor.LongLLMLingua` (bundled with LLMLingua) |
| 5 | **CompactPrompt** | Pipeline compression | ❌ research only | Paper, no PyPI package |
| 6 | **Cmprsr** | Semantic compression | ❌ pattern only | Conceptual; implement via LiteLLM + prompt template |
| 7 | **LangChain Compression Retriever** | RAG opt | ✅ | `py:langchain_classic.retrievers.contextual_compression.ContextualCompressionRetriever` (moved in langchain 1.x) |
| 8 | **LlamaIndex** | RAG framework | ✅ | `py:llama_index` |
| 9 | **LiteLLM** | Cost gateway | ✅ | `py:litellm` |
| 10 | **Langfuse** | Observability | ✅ | `py:langfuse` |
| 11 | **Custom JSON minimization** | Pattern | n/a | DIY pattern (not a tool) |
| 12 | **Protobuf / Avro / Parquet** | Serialization | partial | py:pyarrow installed; protobuf bundled |
| 13 | **Semantic Cache (Redis)** | Cache pattern | ✅ | Redis 7.4 docker; py:redis client. Wiring layer in services TBD |
| 14 | **Prompt Compression (manual)** | Pattern | n/a | Pattern not a tool |
| 15 | **Re-ranking (BGE / cross-encoder)** | Post-retrieval | ✅ | `py:FlagEmbedding` (BGE) + `py:sentence_transformers` (cross-encoder) |
| 16 | **Hybrid Search (BM25 + Vector)** | Retrieval | ✅ | `py:rank_bm25` + Qdrant; wired in retrieval-svc strategy="hybrid" |
| 17 | **Sliding Window Context** | Context mgmt | n/a | Pattern (apply via tiktoken counter + window) |
| 18 | **Chunk Filtering** | Pre/post retrieval | partial | Need similarity-threshold filter (gap from deep RAG test) |
| 19 | **Token Budgeting Engine** | FinOps | partial | Some hooks in `services/inference-svc/app/services/rag_inference.py` |

**Summary:** 11 of 19 tools installed (compression-tool-table coverage). 4 are research-only (TOON, ONTO, CompactPrompt, Cmprsr) — no PyPI packages exist; if needed, would have to implement from paper. 4 are patterns/DIY rather than discrete tools.

## What was installed THIS session

```
pip install llmlingua FlagEmbedding langchain langchain-community
```

Result:
- LLMLingua 0.2.2 + LongLLMLingua bundled
- FlagEmbedding (BGE rerankers — bge-reranker-v2-m3, etc.)
- LangChain 1.2.17 (+ langchain-community + langchain-classic — CCR is at `langchain_classic.retrievers.contextual_compression`)

## Patterns wired in the project today

### ✅ Hybrid Search (#16)
- `services/retrieval-svc/` uses BM25 + vector via `rank_bm25` + Qdrant
- Strategy field in /api/v1/retrieve response: `"strategy": "hybrid"`
- Verified empirically in `docs/architecture/rag-deep-test-2026-05-04.md`

### ⚠ Chunk Filtering (#18) — gap surfaced
- Empirical test showed retrieval returns top-K with NO similarity threshold
- Q1 (Half-Life 2) returned 5 irrelevant chunks despite 0 matching content
- **Action:** add `min_score` filter to `RetrievalRequest` and reject chunks below threshold
- BGE reranker now installed — can wire as the post-retrieval filter

### ⚠ Re-ranking (#15) — installed but not wired
- FlagEmbedding installed; bge-reranker-v2-m3 model not pulled yet
- **Action:** integrate as post-retrieval rerank stage in retrieval-svc

### ⚠ Token Budgeting (#19) — partial
- `services/inference-svc/app/services/rag_inference.py` has token tracking
- finops-svc exists as a service but full token-budget engine not yet wired
- **Action:** integrate LiteLLM (now installed) for per-route budgeting

### ⚠ Semantic Cache (#13) — Redis up, wiring TBD
- Redis 7.4 docker container healthy
- py:redis client installed
- LiteLLM has built-in semantic cache support — should be the first integration

## What this surfaces — concrete next iterations

| Iteration | What | Tool composing |
|-----------|------|----------------|
| 1 | min_score filter in `/api/v1/retrieve` | (no new dep — config + retrieval-svc) |
| 2 | BGE reranker wired post-vector | FlagEmbedding (just installed) |
| 3 | LiteLLM gateway in front of Ollama | LiteLLM (just installed) |
| 4 | LiteLLM semantic cache enabled | LiteLLM + Redis |
| 5 | Langfuse trace integration in inference-svc | Langfuse (just installed) |
| 6 | RAGAS eval runner + dashboard | RAGAS (just installed) |
| 7 | LongLLMLingua compression for long contexts | LLMLingua (just installed) |
| 8 | Guardrails input/output filters | Guardrails (just installed) |
| 9 | Similarity-threshold drill (regression catch) | drill_*.py |

## Composes with

- `docs/architecture/techstack-install-2026-05-04.md` — bulk install record
- `docs/architecture/rag-deep-test-2026-05-04.md` — empirical evidence for #18 gap
- `services/retrieval-svc/app/main.py` — where chunk filtering + reranker wiring lands
- `services/inference-svc/app/services/rag_inference.py` — where token budgeting + Langfuse wiring lands
- §39 — RAG architecture standards (hybrid search + reranker + cache + monitoring)
- §43 — drill discipline (each new wiring lands with a drill)
- §52 — brutal tool review (per-tool 40-row when wired)
- §56 — techstack additions formal 6-gate process

## The brutal rule

> Compression tools are the easy 5%. Wiring them into the request hot
> path with a similarity floor + reranker + cache + observability is
> the 95%. The empirical RAG test (rag-deep-test-2026-05-04.md) showed
> retrieval without a threshold returns noise; the LLM saved it by
> refusing to hallucinate. The next iterations close that gap.
