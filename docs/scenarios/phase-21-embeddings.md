# Phase 21 — Embeddings Deep Dive

Embeddings turn text/image/code into vectors. Wrong embedding model or missing version stamp = wrong retrieval = hallucination. Most teams under-invest here.

---

## 1. Types

| Type | Use |
| --- | --- |
| Text | policy docs, PDFs, FAQs |
| Code | source-code RAG |
| Table | finance, invoices |
| Image | visual search, scanned docs |
| Multimodal | text + image + chart |
| Query embedding | user question → vector |
| Document embedding | chunk → vector |
| Hybrid sparse+dense | BM25 + vector retrieval |

## 2. Model options

| Category | Examples | Use |
| --- | --- | --- |
| Open-source local | BGE-m3, E5, GTE, Nomic, MiniLM, Instructor | private / low-cost |
| Hosted | OpenAI `text-embedding-3`, Cohere embed v3, Azure, Bedrock Titan | managed quality |
| Multimodal | CLIP, SigLIP, BLIP | image/text |
| Domain-tuned | finance / legal / medical models | higher accuracy on jargon |

**DocuMind default:** BGE-m3 1024-dim multilingual. Local, free, strong.

## 3. Critical checks (every embedding)

| Check | What to verify |
| --- | --- |
| Correct model used | model name + version stored in metadata |
| Same model for query + index | avoid mismatch — **fatal** |
| Vector dimension matches DB | schema validation |
| `embedding_version` stored | re-index without drift |
| PII handled before embedding | sensitive data control |
| Empty chunks skipped | no junk vectors |
| Duplicate chunks detected | reduce index noise |
| Language supported | multilingual retrieval |
| Normalization applied (L2) | correct cosine similarity |
| Drift monitored | model/data changes tracked |

## 4. TDD

```python
def test_embedding_dimension():
    vector = embed_text("sample policy text")
    assert len(vector) == 768

def test_embedding_metadata():
    result = embed_chunk(chunk)
    assert result.metadata["embedding_version"] is not None
    assert result.metadata["model_name"] is not None

def test_query_doc_model_match():
    q = embed_query("test")
    d = embed_doc("test")
    assert q.model_name == d.model_name
    assert q.version == d.version
```

## 5. BDD

```
Feature: Embedding generation for enterprise documents

Scenario: Generate embedding for clean HR policy chunk
  Given a valid HR policy chunk
  When the embedding service processes it
  Then a vector is generated
  And the vector includes model version metadata

Scenario: Block sensitive PII chunk
  Given a chunk containing sensitive employee data
  When embedding is requested
  Then the chunk is masked or blocked
```

## 6. Model-driven schema

```json
{
  "embedding_id": "emb_001",
  "chunk_id": "chunk_001",
  "document_id": "doc_001",
  "tenant_id": "tenant_hr",
  "model_name": "bge-m3",
  "embedding_version": "v1",
  "dimension": 1024,
  "vector_hash": "sha256:abc123",
  "created_at": "2026-04-24T00:00:00Z"
}
```

## 7. Output-first

| Desired output | Embedding requirement |
| --- | --- |
| Accurate citation | relevant chunks retrieved |
| Low hallucination | high-recall embeddings |
| Fast answer | efficient vector search (quantization) |
| Multilingual | multilingual model |
| Secure answer | PII-safe embedding pipeline |
| Version rollback | embedding_version per chunk |

## 8. Benchmarking

| Benchmark | Why |
| --- | --- |
| recall@k | did correct chunk appear? |
| precision@k | were top chunks relevant? |
| MRR | correct answer ranked high? |
| nDCG | ordering quality |
| latency | embedding speed |
| cost / 1K chunks | FinOps |
| index size | storage cost |
| multilingual score | language coverage |

## 9. Failure matrix

| Failure | Root cause | Fix |
| --- | --- | --- |
| Poor retrieval | weak model | test BGE / E5 / Cohere / OpenAI |
| Dimension mismatch | wrong DB config | schema validation |
| Stale vectors | doc updated | re-embed changed chunks (hash compare) |
| Slow indexing | model too large | batch + GPU + async queue |
| High cost | hosted model overuse | cache embeddings |
| Data leak | PII embedded | scan before embedding |
| Query mismatch | different query vs doc model | enforce config |
| Multilingual failure | English-only model | use multilingual |

## 10. Tools

| Need | Tools |
| --- | --- |
| Local embeddings | sentence-transformers · BGE · E5 |
| Hosted | OpenAI API · Cohere · Azure OpenAI |
| Multimodal | CLIP · SigLIP · BLIP |
| Benchmark | MTEB · BEIR |
| Drift detection | PSI / CSI over embedding space |

## 11. Exit criteria

- [ ] `services/ingestion-svc/app/embedding_service.py` + `services/retrieval-svc/app/query_embedder.py` share a `ModelConfig` so query + doc always use the same model.
- [ ] Every chunk row stamped with `embedding_model` + `embedding_version` (verified by test).
- [ ] Shadow-index pattern documented for upgrades.
- [ ] Tests:
  - [ ] `tests/rag/test_embedding_dimension.py`
  - [ ] `tests/rag/test_embedding_metadata.py`
  - [ ] `tests/rag/test_embedding_security.py` (PII pre-embed scan)
  - [ ] `tests/rag/test_embedding_benchmark.py`
- [ ] MTEB-subset benchmark on golden set committed.
- [ ] Drift dashboard (embedding distribution PSI vs baseline).

## 12. Brutal checklist

| Question | Required |
| --- | --- |
| Is embedding model + version stored per chunk? | Yes |
| Are query + index embeddings compatible (same model+version)? | Yes |
| Is PII handled before embedding? | Yes |
| Can embeddings be re-created? | Yes — shadow index |
| Can model A vs B be benchmarked? | Yes — golden set + MTEB |
| Is recall@k measured? | Yes |
| Is cost tracked? | Yes |
| Is drift monitored? | Yes |
