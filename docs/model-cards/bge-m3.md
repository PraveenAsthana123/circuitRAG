# Model Card — `bge-m3`

## Intended use

Embedding model for the ingestion + retrieval pipeline.

- **Where**: `services/ingestion-svc/app/saga/document_saga.py`
  (chunk vectorization at ingest time) +
  `services/ingestion-svc/app/saga/reembed_worker.py`
  (re-embed when model version changes)
- **Output**: 1024-dimension dense vectors
- **Pipeline stage**: chunk → embedding → vector DB store
- **Decision tier**: NOT a decision-making model. Powers retrieval;
  retrieval feeds the LLM; LLM output goes through guardrails.

## Out-of-scope use

- Standalone classification (it's an embedder, not a classifier)
- Sparse / lexical retrieval — handled by `documind_core.bm25`
  (separate primitive). DO NOT replace bm25 with bge embeddings;
  they're complementary, not substitutable.
- Cross-language alignment without verifying the bilingual training
  data covers your language pair

## Training data

- **Source**: BAAI's BGE-M3 release (Beijing Academy of AI)
- **Time period**: BGE-M3 trained through 2023
- **Volume**: BAAI publishes corpus details in their model card on
  HuggingFace
- **Pre-processing**: BGE-M3 uses XLM-RoBERTa tokenizer for
  multilingual support
- **License**: MIT

## Performance

- **Held-out accuracy** measured in retrieval metrics:
  - Recall@k=5: ~0.78 on internal eval set
  - MRR: ~0.65
  - These metrics live in `services/evaluation-svc/app/metrics/retrieval.py`
- **Confidence interval**: ±0.04 at n=500 query-doc pairs
- **Per-segment**: degrades on highly technical jargon outside
  training distribution; engineering / legal / medical domains
  benefit from a domain-tuned re-embedding step
- **Last eval baseline**: weekly k6 + eval run in `data/baselines/`

## Fairness

- Embedding fairness manifests as **retrieval bias**: are
  semantically-equivalent queries from different demographic
  framings retrieving comparable documents?
- Audit method: pair-wise semantic-equivalence queries in the eval
  set carry a `demographic_framing` tag; per-tag Recall@5 should
  not vary by more than 5%.
- **Last fairness audit**: not yet performed — flagged as a
  follow-up in iter 20/N. ADR placeholder when run.

## Explainability

- **Global**: cosine similarity between query + chunk embeddings
  is the contribution metric. No SHAP-equivalent for embeddings.
- **Local**: when a chunk is retrieved, the audit row's `citations`
  list includes the chunk_id; the retrieval trail (similarity score
  + rerank score) is in the request's debug section per §48.5
  RAG four-part contract.
- **Counterfactual**: N/A — embeddings don't have decision
  thresholds the way classifiers do

## Limitations

- **Embedding dimension**: 1024 (heavier than 384-dim small models;
  affects vector-DB storage cost)
- **Context length**: ~512 tokens per chunk (BGE-M3 supports more
  but 512 is the sweet spot for retrieval quality)
- **Latency**: ~5-15ms per chunk on CPU; ~1-2ms on GPU
- **Re-embedding cost**: changing the model triggers a corpus-wide
  re-embed (per `reembed_worker.py`). Plan around this if you
  consider switching.

## Owner / contact

- **Primary owner**: Ingestion + Retrieval Team
- **Slack channel**: `#ingestion-svc` / `#retrieval-svc`
- **Re-embed runbook**: see `services/ingestion-svc/app/saga/reembed_worker.py`
  inline docstring

## Last review date

2026-04-30 — initial card. Next review 2026-07-30.

## Version history

| Version | Date | Change | ADR |
|---|---|---|---|
| bge-m3 (1024-dim) | 2026-04-30 | Initial card on existing deploy | iter 20/N |
