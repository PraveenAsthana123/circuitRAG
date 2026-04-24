# Phase 4 — RAG Core

**Status:** Stub — structure + starter config.

## Topic map

### Chunking

| Type | Implementation | Default |
| --- | --- | --- |
| Paragraph-based | `services/ingestion-svc/app/chunking/windowed.py` | fallback |
| Section/heading | `services/ingestion-svc/app/chunking/structural.py` | **active for PDFs** (via `unstructured`) |
| Sentence window | `services/ingestion-svc/app/chunking/sentence.py` (pysbd) | mid-length docs |
| Semantic (embedding-clustered) | *planned* | — |
| AST (code) | *planned* | — |
| Table-aware | LayoutLMv3 — via `unstructured` |
| Legal-clause | *not implemented* |
| Hierarchical | doc → section → chunk (parent/child in `ingestion.chunks.parent_id`) | **recommended default** |

**Starter config (ship now):**
- section-aware
- 600–800 tokens
- 15% overlap
- metadata: `doc_id`, `section`, `tenant_id`, `embedding_model`, `embedding_version`

### Embeddings

| Bucket | Options | Active |
| --- | --- | --- |
| Local | BGE-m3, E5, Instructor, GTE, Nomic, MiniLM | **BGE-m3 1024-dim** |
| Hosted | OpenAI text-embedding-3, Cohere embed v3, Azure, Bedrock Titan | fallback |
| Multimodal | CLIP / SigLIP, BLIP | future |

**Key knobs:**
- `dimension` (BGE-m3: 1024)
- `normalization` (L2)
- `distance` (cosine)
- `embedding_version` stamp on every chunk — **critical for re-index without drift**

### Retrieval

| Pattern | Where |
| --- | --- |
| Hybrid (vector + BM25) | `services/retrieval-svc/app/services/hybrid_retriever.py` |
| Cross-encoder rerank | BGE reranker v2, top-20 → top-5 |
| Graph augmentation | `services/retrieval-svc/app/services/graph_searcher.py` |
| Tenant-aware | **mandatory** payload filter in `QdrantRepo` |

### Inference

| Pattern | Where |
| --- | --- |
| Grounded answer | `services/inference-svc/app/` |
| Model fallback (CB) | premium → smaller local (llama3) |
| Streaming | SSE + CCB |
| Context-window pack | greedy pack; compress low-score chunks |

### Cache

| Layer | Key schema | TTL |
| --- | --- | --- |
| Semantic answer cache | `tenant:{id}:q:{sha256(normalized_q + model_version + prompt_version)}` | 1h |
| Retrieval cache (top-K IDs) | `tenant:{id}:retr:{sha256(q)}` | 15m |
| Chunk cache | `tenant:{id}:chunk:{chunk_id}` | 24h |
| Embedding cache | `embed:{model_version}:{sha256(text)}` | 7d |
| Session cache | `tenant:{id}:sess:{user_id}` | 1h sliding |
| Rate-limit counter | `rl:{tenant}:{window}` | window |
| CB state | `cb:{name}:{instance}` | live |

**Non-negotiable:** never cache PII responses; invalidate on content-change events; tenant-namespaced keys.

### Output evaluation

| Dimension | Metric | Mode | Tool |
| --- | --- | --- | --- |
| Grounding | Faithfulness · context precision / recall | offline + sampled online | Ragas |
| Answer quality | Exact match / F1 · semantic similarity · LLM-judge | offline (golden) | Ragas / DeepEval |
| Safety | PII leakage · policy violations · toxicity | per-response | PIIScanner + ResponsibleAIChecker |
| System | Latency p50/p95/p99 · cost/query · cache-hit rate · hallucination rate | continuous | Prom + Grafana |

## Phase-4 exit criteria

- [ ] Golden eval dataset committed to `docs/eval/golden/` (50+ Q/A pairs).
- [ ] `make eval` runs Ragas → writes report to `data/eval/<date>.json`.
- [ ] CI job fails merge if faithfulness drops > 3% vs baseline.
- [ ] Cache TTLs configured per layer in `libs/py/documind_core/cache.py`.
- [ ] `embedding_version` stamped on every new chunk (verified by a test).

## Common pitfalls (see in every RAG project)

1. Chunk too small → no context → hallucination.
2. Chunk too large → token bloat → cost + latency.
3. No embedding version → silent drift after model upgrade.
4. No tenant filter in cache key → cross-tenant leak.
5. No eval pipeline → "it seems to work" illusion.
6. No cache invalidation → stale policy answers.
