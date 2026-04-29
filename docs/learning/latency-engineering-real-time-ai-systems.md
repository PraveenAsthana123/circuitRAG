# Latency Engineering In Real-Time AI Systems

This document explains how to design AI and RAG systems for real-time user experience.

## 1. Core Concept

Latency is cumulative.

A slow AI system is usually not one slow model.
It is many small delays across:
- preprocessing
- retrieval
- ranking
- prompt assembly
- model inference
- post-processing

## 2. 5W

| Dimension | Explanation |
| --- | --- |
| What | Techniques to reduce end-to-end latency in interactive AI systems |
| Why | Users judge the whole system by perceived response time |
| Where | Gateway, retrieval, ranking, context packing, model runtime, streaming, cache |
| When | During architecture design, scaling, and incident response |
| Who | Backend engineers, AI engineers, platform teams, architects |

## 3. Latency Budget Mindset

Break the full request into budgets:

| Layer | Example budget |
| --- | --- |
| Gateway / auth | 50 ms |
| Retrieval | 200 ms |
| Reranking | 150 ms |
| Prompt assembly | 50 ms |
| LLM first token | 500 ms |
| Streaming completion | remaining budget |

## 4. Latency Flow

```text
Request
  -> cache check
  -> query preprocess
  -> parallel retrieval
  -> Top-K / rerank
  -> prompt assembly
  -> model inference
  -> stream response
```

## 5. Sequence Flow

```text
Client sends query
  -> gateway authenticates
  -> retrieval branches execute in parallel
  -> results merged and ranked
  -> prompt built
  -> model starts generation
  -> first token streamed
  -> answer completes
```

## 6. Network Flow

```text
Client
  -> gateway
  -> retrieval orchestrator
     -> vector DB
     -> cache
     -> graph or lexical branch
  -> inference service
  -> model runtime
  -> streamed response
```

## 7. Main Techniques

| Goal | Technique |
| --- | --- |
| Faster retrieval | ANN search, metadata filtering, smaller candidate pool |
| Faster orchestration | async fan-out, bounded concurrency |
| Faster generation | smaller model, streaming, prompt compression |
| Faster repeated queries | cache |
| Faster user perception | stream first token early |

## 8. Common Latency Problems

| Problem | Root cause | Fix |
| --- | --- | --- |
| Slow retrieval | too many candidates, weak filters | reduce K, better filters, ANN tuning |
| Slow reranking | reranking too many chunks | shrink candidate pool first |
| Slow first token | prompt too large, big model | compress context, route model |
| Slow whole answer | no streaming | stream partial tokens |
| Tail latency spikes | one slow dependency | timeout + breaker + fallback |

## 9. What To Explain In Interview

Say:

> I treat latency as a budgeted multi-stage problem. I reduce it by parallelizing independent retrieval branches, shrinking candidate sets early, enforcing prompt budgets, using caching, routing simpler work to smaller models, and streaming the response so users see progress before completion.

## 10. Sample Async Fan-Out Skeleton

```python
results = await asyncio.gather(
    fetch_vector_hits(query),
    fetch_graph_hits(query),
    fetch_cache_hints(query),
)
```

## 11. Brutal Insight

Most teams talk about model latency.

Real latency engineering starts before inference:
- better retrieval
- smaller candidate sets
- tighter token budgets
- better orchestration

