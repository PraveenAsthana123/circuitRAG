# Phase 24 — Pre-Retrieval & Post-Retrieval

RAG accuracy is won or lost HERE — most teams over-invest in the LLM and under-invest in retrieval shaping.

---

## Part 1 — Pre-Retrieval

**Goal:** improve the query BEFORE the search.

### A. Query cleaning

| Problem | Fix |
| --- | --- |
| Typos | normalize / correct |
| Noise | strip stopwords |
| Long query | compress |
| Mixed language | detect + translate |

### B. Query rewriting (very important)

| Type | Example |
| --- | --- |
| Expansion | "travel policy" → "travel reimbursement policy rules" |
| Clarification | "leave" → "employee leave policy" |
| Intent detection | Q&A vs action route |
| Multi-query generation | 3–5 paraphrased variants; union retrieved sets |
| Semantic rewrite | embed a better-phrased version |

### C. Query classification

| Class | Action |
| --- | --- |
| FAQ | use cache |
| Policy | structured retrieval |
| Code | code-specific retrieval |
| Financial | table-aware retrieval |
| Action | MCP route |
| Low confidence | ask clarification |

### D. Query routing

| Route | Condition |
| --- | --- |
| Vector DB | semantic |
| BM25 | exact keyword |
| Graph DB | relationship |
| Cache | repeated query |
| MCP | action request |

### E. Filters BEFORE retrieval (critical)

| Filter | Why |
| --- | --- |
| `tenant_id` | isolation — always enforced |
| `region` | compliance |
| `role` | RBAC |
| `sensitivity` | PII |
| `document_type` | relevance |
| `date / version` | freshness |

### Failure matrix (pre)

| Failure | Cause | Fix |
| --- | --- | --- |
| Wrong intent | bad classification | improve classifier |
| Missing docs | no expansion | multi-query |
| Irrelevant results | no filters | apply ABAC |
| Too broad query | no rewrite | refine |
| Wrong DB used | no routing | add router |

---

## Part 2 — Post-Retrieval

**Goal:** improve retrieved results BEFORE the LLM.

### A. Reranking (critical)

| Method | Tool |
| --- | --- |
| Cross-encoder | BGE reranker v2, Cohere rerank |
| LLM rerank | LLM scoring (expensive, high quality) |
| Hybrid scoring | vector + BM25 RRF |

### B. Filtering

| Filter | Why |
| --- | --- |
| Low similarity | remove noise |
| Duplicate chunks | remove redundancy |
| Outdated docs | avoid wrong answers |
| Unauthorized chunks | ABAC enforcement |
| Low confidence | remove weak results |

### C. Chunk selection

| Strategy | Why |
| --- | --- |
| Top-K (5–10) | control tokens |
| Diversity | MMR; avoid near-duplicates |
| Section-aware | better context |
| Hierarchical | include parent section |

### D. Context compression

| Method | Use |
| --- | --- |
| Summarization | reduce tokens |
| Sentence extraction | keep key info |
| Deduplication | remove repeats |
| Keyword extraction | reduce noise |

### E. Context structuring

| Method | Example |
| --- | --- |
| Section grouping | group chunks by document |
| Ordering | rank by relevance |
| Citation mapping | attach source IDs |
| Chunk linking | connect related chunks |

### Failure matrix (post)

| Failure | Cause | Fix |
| --- | --- | --- |
| Hallucination | bad chunks reached model | rerank + confidence filter |
| Irrelevant answer | no filtering | filter + rerank |
| Token overflow | too many chunks | reduce top-K / compress |
| Duplicate context | overlap | dedupe |
| Missing key info | low recall | increase top-K / multi-query |
| Wrong source | bad metadata | fix tagging |

## 3. Combined flow

```mermaid
flowchart LR
  q([query]) --> clean[clean + normalize]
  clean --> cls[classify intent]
  cls --> rewrite[rewrite + multi-query]
  rewrite --> route{route}
  route -->|semantic| vec[Qdrant]
  route -->|keyword| bm25[BM25]
  route -->|relationship| graph[Neo4j]
  route -->|repeat| cache[Redis]
  vec --> rrf[RRF fusion]
  bm25 --> rrf
  graph --> expand[1-hop neighbours]
  expand --> rrf
  rrf --> rerank[cross-encoder]
  rerank --> mmr[MMR dedup]
  mmr --> compress[summarize low-rank]
  compress --> pack[context pack]
  pack --> llm[LLM]
```

## 4. Metrics

| Metric | Meaning |
| --- | --- |
| `recall@k` | did we retrieve the right chunk? |
| `precision@k` | are retrieved chunks relevant? |
| `MRR` | ranking quality |
| `nDCG` | ordering quality |
| `duplicate_rate` | redundancy |
| `context_tokens` | efficiency |
| `latency_ms` | performance |

## 5. Tools

| Need | Tools |
| --- | --- |
| Query rewrite | LLM · LangChain router |
| Classification | ML / LLM |
| Reranker | BGE reranker · Cohere |
| Hybrid | OpenSearch + Qdrant |
| Deduplication | cosine similarity threshold |
| Compression | LLM summarizer · spaCy |
| Graph expansion | Neo4j Cypher 1-hop |

## 6. Exit criteria

- [ ] `services/retrieval-svc/app/query_rewriter.py` with multi-query + classification.
- [ ] `services/retrieval-svc/app/reranker.py` integrated cross-encoder.
- [ ] `services/retrieval-svc/app/filter_engine.py` applies `tenant_id` + `role` + `region` + `sensitivity` + `freshness`.
- [ ] Tests:
  - [ ] `tests/rag/test_query_rewrite.py`
  - [ ] `tests/rag/test_reranking.py`
  - [ ] `tests/rag/test_filtering.py`
  - [ ] `tests/rag/test_deduplication.py`
- [ ] Dashboard: precision@5, recall@5, rerank latency, dedup rate.

## 7. Brutal checklist

| Question | Required |
| --- | --- |
| Can the query be rewritten? | Yes |
| Can the system classify intent? | Yes |
| Are filters applied BEFORE retrieval? | Yes |
| Is reranking used? | Yes |
| Are duplicate chunks removed? | Yes |
| Is context compressed? | Yes |
| Are token limits respected? | Yes |
| Can the system say "no result"? | Yes |
