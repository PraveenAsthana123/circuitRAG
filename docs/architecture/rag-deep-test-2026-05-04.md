# Deep RAG end-to-end test — 2026-05-04

**Run:** `python scripts/deep_rag_test.py` (or `/tmp/rag-deep-test/run_deep_test.py`)
**Date:** 2026-05-04 21:05 UTC
**Corpus:** Kaggle BBC News Archive (`hgultekin/bbcnewsarchive`) — 10 articles from `tech` category, 32k chars total
**Tenant:** `a5b309a3-6ef0-45aa-95d6-0eb66cc0febd` (UUID — required by ingestion-svc validation)

## Pipeline under test

| Stage | Endpoint | What it does |
|-------|----------|--------------|
| **Ingest** | `POST :8082/api/v1/documents/upload` (sync=true) | chunking + embedding + Qdrant insert |
| **Retrieve** | `POST :8083/api/v1/retrieve` | hybrid (vector + BM25) search |
| **Ask (full RAG)** | `POST :8084/api/v1/ask` | retrieve + LLM (`llama3.1:8b`) + citations |

## Headline numbers

| Stage | Status | Latency | Notes |
|-------|--------|---------|-------|
| Ingest | **10/10 ok** | 3.26s/doc avg (32.6s total) | sync mode = waits for embedding + Qdrant |
| Retrieve | **5/5 200** | p95 = 94ms | always returns 5 chunks |
| Ask | **5/5 200** | p95 = 4.4s | model=llama3.1:8b, prompt 763–1838 tokens |

## Per-query analysis (the real signal)

### ✅ Q3: "What is Microsoft doing about spyware?" — STRONG

- **Retrieved chunks:** ALL relevant — Microsoft anti-spyware investigation, Christmas virus, Microsoft patches
- **Answer (confidence 0.41):** "Microsoft is investigating a trojan program that attempts to switch off the firm's anti-spyware software, known as Bankash-A Trojan..."
- **Citations:** 3 documents, all on-topic
- **Verdict:** end-to-end RAG works correctly when corpus has matching content

### ⚠ Q5: "What is Wi-Fi or wireless internet?" — PARTIAL

- **Retrieved chunks:** top hit is "Wi-fi web reaches farmers in Peru" — relevant doc but specific use-case, not general definition
- **Answer (confidence 0.01):** "I don't have enough information... The context only mentions wireless technology in a Peru community-network case"
- **Verdict:** LLM correctly hedges when corpus has tangential but not directly-answering content

### ⚠ Q4: "What are mobile phone trends?" — PARTIAL

- **Retrieved chunks:** mobile phones mentioned in top-100 gadgets list
- **Answer (confidence 0.01):** "...The context only mentions mobile phones as one of the gadgets listed in a top 100 list..."
- **Verdict:** retrieval found mobile-phone mentions, LLM correctly notes they're not about "trends"

### ❌ Q1: "What is Half-Life 2 known for?" — RETRIEVAL DRIFT

- **Retrieved chunks:** 5 chunks — ALL irrelevant (mobile phones, ink democracy, Google toolbar)
- **Reason:** no Half-Life article in the 10 ingested docs. Vector retrieval returns nearest-neighbors regardless of relevance threshold
- **Answer (confidence 0.01):** "I don't have enough information in the provided documents."
- **Verdict:** RETRIEVAL doesn't filter on similarity threshold; LLM saves the day by refusing to hallucinate

### ❌ Q2: "What did Apple announce about iPod?" — RETRIEVAL DRIFT

- Same pattern as Q1 — no Apple iPod article in the 10 docs. Retrieved chunks: Google toolbar, "Technology gets the creative bug"
- LLM refuses (confidence 0.01)

## What this proves

✅ **Pipeline functional end-to-end:** ingest → embed → store → retrieve → LLM → citations all work
✅ **Hallucination defense holds:** LLM refuses (confidence 0.01) when retrieved chunks are off-topic — no fabricated answers across 4 of 5 low-relevance queries
✅ **Citation persistence:** every answer carries chunk_id + document_id + snippet, traceable to source
✅ **Latency budget green:** retrieve p95=94ms (well under 500ms target), ask p95=4.4s (acceptable for local LLM)
✅ **Confidence calibration directionally correct:** 0.01 for hedges/refusals, 0.41 for the one strong answer

## What this surfaces (action items)

❌ **Retrieval has no similarity-threshold filter.** It always returns top-K (here 5) regardless of how poor the match is. Q1 + Q2 returned 5 chunks each despite NO matching content in corpus. Hybrid score should have a hard floor below which the chunk is rejected.

⚠ **Reranking absent.** The retrieve response shows raw vector + BM25 hits. A rerank stage (cohere-rerank, BGE-rerank, or cross-encoder) would dramatically improve precision on the partial-match queries (Q4, Q5).

⚠ **Ground-truth Q&A pairing.** The test queries weren't built to match the actually-ingested 10 docs (only 1 query had a clean strong match). For a real evaluation, queries should be derived FROM the corpus (open SQuAD-style auto-generation).

⚠ **Chunking strategy review.** First chunk for Q1 was a fragment starting with "should be Number One. Why?" — clearly mid-sentence. Chunk boundaries don't respect sentence/paragraph structure perfectly.

✅ **Rate limit observed and respected:** ingestion-svc enforces 10 uploads per tenant per window. Test added 2s sleep between uploads to stay under the limit. Drill-worthy invariant.

## Composes with

- `scripts/deep_rag_test.py` — the harness (copied from /tmp/rag-deep-test/run_deep_test.py)
- `services/ingestion-svc/app/routers/documents.py` — POST /api/v1/documents/upload contract
- `services/retrieval-svc/app/main.py` — POST /api/v1/retrieve contract
- `services/inference-svc` — POST /api/v1/ask + RAG prompt template (`rag_answer_v1`)
- `~/.kaggle/kaggle.json` — credentials per global §36
- §38 — decision audit (every ask carries correlation_id + model + prompt_version + tokens)
- §39 — RAG architecture standards (chunking, embedding, retrieval, hallucination defense)
- §43 — drill discipline (this test should land as a drill on the deep_rag_test harness)
- §48 — explainability (citations are the explainability surface here)

## The brutal rule, restated

> A RAG system that returns 5 chunks for "What is Half-Life 2?" against a corpus with NO Half-Life content is broken at the retrieval layer — even if the LLM saves it by refusing to answer. Vector search without a similarity floor is auto-completion noise. The next iteration must add a relevance threshold + reranker before declaring retrieval production-ready.

## Reproducibility

```bash
# 1. Download corpus
kaggle datasets download -d hgultekin/bbcnewsarchive --unzip -p /tmp/rag-deep-test/

# 2. Confirm services up
curl -s http://localhost:8082/health  # ingestion-svc
curl -s http://localhost:8083/health  # retrieval-svc
curl -s http://localhost:8084/health  # inference-svc

# 3. Run the harness
python scripts/deep_rag_test.py

# 4. Inspect full results
cat /tmp/rag-deep-test/results.json | jq '.ask.results[].body | {q: .answer, conf: .confidence}'
```
