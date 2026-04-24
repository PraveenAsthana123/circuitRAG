# Eval dataset v1 — IMPORTANT notes on validity

## Status

**Synthetic + partial.** The questions and ground-truth answers are real
domain content about DocuMind. However, the `expected_chunk_ids` field
values (e.g. `documind-overview-0`) are **placeholder strings that do
not correspond to any chunk actually indexed** in the corpus.

As a result:

- **Answer-relevance / faithfulness metrics** can be computed against
  this dataset (the `ground_truth` is real text about the system).
- **Retrieval metrics (precision@k / recall / MRR / NDCG)** CANNOT be
  computed against this dataset today — they require real chunk IDs.

## Why it's still useful

You can drive the pipeline through the evaluation-svc API using this
file to smoke-test the scoring pipeline. The retrieval metrics will
come back at 0, which tells you the dataset is not corpus-linked — the
point is: the evaluation SERVICE works, even if this SPECIFIC dataset
isn't retrieval-linked.

## Producing a retrieval-linked dataset

To make the retrieval metrics meaningful you need to:

1. Seed the corpus with the same text blocks that back the
   `ground_truth` answers. `scripts/seed_demo.py` writes sample docs
   into `data/samples/` but does NOT cover every topic in this eval
   dataset.
2. After ingestion, export `(chunk_id, text)` pairs for the seeded
   corpus.
3. For each question, programmatically identify the chunk(s) that most
   support the ground truth (e.g. via string-similarity match) and
   write those IDs back into this file.

A future commit will add `scripts/build_eval_dataset.py` that does this
automatically. Until then, treat retrieval metrics from this dataset as
**not meaningful**.

## Statistics

- **Items:** 50
- **Synthetic (placeholder chunk IDs):** 50 / 50
- **Corpus-linked (real chunk IDs):** 0 / 50
