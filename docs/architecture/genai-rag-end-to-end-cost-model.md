# GenAI / RAG End-To-End Cost Model

This document explains how to reason about total cost in a production GenAI / RAG system.

## 1. Main Cost Buckets

| Bucket | Example |
| --- | --- |
| Inference | prompt + completion tokens |
| Retrieval | vector DB, reranker, cache misses |
| Embedding | indexing and refresh |
| Storage | raw docs, chunks, vectors, logs |
| Infra | CPUs, GPUs, memory, network |
| People / operations | review, monitoring, incident handling |

## 2. Per-Request Cost Breakdown

```text
Request cost =
  cache lookup
  + retrieval cost
  + rerank cost
  + prompt token cost
  + completion token cost
  + observability / platform overhead
```

## 3. Main Cost Drivers

- too many tokens in context
- too large Top-K
- too large rerank candidate set
- expensive model for simple query
- weak cache hit rate
- excessive re-embedding
- over-provisioned infra

## 4. Rough Example Model

| Layer | Example unit cost driver |
| --- | --- |
| Embeddings | documents x chunk count x embedding cost |
| Retrieval | queries x vector search cost |
| Rerank | queries x rerank candidates |
| LLM prompt | prompt tokens x rate |
| LLM completion | completion tokens x rate |
| Cache | memory + distributed cache infra |

## 5. Cost Control Levers

### Retrieval
- reduce candidate pool
- improve metadata filtering
- cache retrieval output

### Prompt
- compress context
- remove duplicate chunks
- enforce token budget

### Model
- route simple queries to smaller model
- fallback gracefully
- use quantized or local models when quality allows

### Infra
- autoscale
- batch background work
- tune idle resources

## 6. Example Cost Questions For Architects

- What is cost per answer?
- What is cost per active tenant?
- What is cost per 1,000 queries?
- What percent of requests hit cache?
- What percent require the expensive model?
- What is the monthly embedding refresh cost?

## 7. Final Insight

The most expensive AI system is the one that does unnecessary work repeatedly.
