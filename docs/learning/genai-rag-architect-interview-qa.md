# GenAI / RAG Architect Interview Q&A

This document contains architect-level interview questions and short strong answers for GenAI, RAG, fine-tuning, and agentic systems.

## 1. What makes a RAG system production-ready?

Strong answer:

It must have strong data quality, tenant-safe retrieval, evaluation datasets, versioned prompts and models, runtime controls like timeouts and breakers, cost visibility, observability, and a closed feedback loop for continuous improvement.

## 2. What are the biggest gaps between a demo and a platform?

Strong answer:

The gaps are usually control and operations, not model quality: dataset versioning, lineage, evaluation gating, feedback loops, prompt/model versioning, deployment strategy, cost routing, and failure controls.

## 3. How do you design data for RAG?

Strong answer:

Separate retrieval data, evaluation data, training data, and feedback data. Apply ingestion, cleaning, metadata enrichment, chunking, embedding, indexing, and then close the loop with reviewed feedback and reindex or retrain paths.

## 4. How do you evaluate RAG quality?

Strong answer:

I split evaluation into retrieval, generation, safety, and runtime layers. I use golden datasets, edge cases, adversarial tests, and regression thresholds before rollout, then track online drift and cost after deployment.

## 5. How do you control hallucination?

Strong answer:

Improve retrieval quality first, enforce grounded prompting, add faithfulness checks, support no-answer behavior, and audit citation quality instead of relying on the model alone.

## 6. How do you reduce latency?

Strong answer:

Reduce candidate set size early, parallelize independent retrieval branches, compress prompt context, cache repeated work, route simpler tasks to smaller models, and stream responses quickly.

## 7. How do you reduce cost?

Strong answer:

Reduce unnecessary work first: smaller retrieval sets, prompt compression, cache, model routing, and infrastructure right-sizing. Cost optimization is not just “pick a cheaper model.”

## 8. How do you prevent cross-tenant leakage?

Strong answer:

Tenant filters must be mandatory in retrieval and cache namespaces. Access policy should be enforced at the repository or query layer, backed by audit and explicit isolation tests.

## 9. How do you design a feedback loop?

Strong answer:

Collect explicit and implicit feedback, classify failures, route low-confidence or high-risk cases to human review, and feed confirmed failures into evaluation datasets, retrieval tuning, prompt updates, or retraining.

## 10. How do you handle agent risk?

Strong answer:

Agents need bounded execution: max iterations, timeouts, budget caps, tool allowlists, HITL escalation, audit logging, and fallback paths such as draft persistence when tool execution fails.

## 11. What do you version in a GenAI platform?

Strong answer:

Datasets, chunk sets, embeddings, indexes, prompts, models, evaluation sets, and deployment configuration. Without versioning, behavior changes are untraceable.

## 12. What is the most important system insight?

Strong answer:

Model quality is downstream of data quality, retrieval quality, and control quality. Most failures that look like “LLM problems” are actually data, retrieval, or runtime control problems.

## Final Interview Line

> A production GenAI platform is not just a model integration. It is a controlled data, retrieval, evaluation, feedback, security, and cost system with an LLM inside it.
