# LLMOps

This document explains the main concepts in LLMOps for enterprise AI systems.

LLMOps is the operational discipline around:

- data
- prompts
- models
- experiments
- deployments
- observability
- governance

The goal is not just to run an LLM. The goal is to manage the lifecycle of AI assets safely and repeatedly.

## 1. Main LLMOps domains

### Data
- dataset registry
- dataset versioning
- provenance tracking
- quality profiling
- sensitive-data handling
- evaluation dataset management

### Retrieval data
- corpus registry
- chunk versioning
- embedding model versioning
- index versioning
- metadata schema tracking

### Models
- model registry
- model versioning
- active vs inactive versions
- deployment mapping
- rollback targets
- SLM and LLM inventory

### Prompts
- prompt registry
- prompt versioning
- active prompt
- candidate prompt
- deprecated prompt
- prompt ownership

### Experiments
- run tracking
- parameter tracking
- evaluation result tracking
- comparison across runs
- cost and latency tracking

### Deployment
- deployment registry
- canary or shadow rollout
- active deployment version
- rollback workflow
- environment promotion

### Observability
- prompt traces
- token tracking
- latency
- cost
- error rates
- quality signals
- feedback capture

### Governance
- approval workflow
- audit trail
- policy versioning
- lifecycle states
- retirement or archive policy

## 2. Why LLMOps matters

Without LLMOps, teams lose track of:

- which model is active
- which prompt generated a result
- which embedding version built the index
- what changed between good and bad behavior
- who approved a rollout
- how to roll back safely

LLMOps turns AI systems into managed systems instead of intuition-based systems.

## 3. Key LLMOps entities

The most common operational entities are:

- dataset
- evaluation dataset
- retrieval corpus
- chunk version
- embedding model
- embedding index
- prompt
- policy
- llm model
- slm model
- reranker model
- experiment run
- deployment
- evaluation report

## 4. Common lifecycle states

Most LLMOps entities should support lifecycle states such as:

- draft
- candidate
- active
- inactive
- deprecated
- archived
- rolled_back

These states should be explicit, not implied by naming conventions.

## 5. Model management

Model management should answer:

- what model versions exist
- which is active
- which are inactive
- which deployment uses which version
- which prompt sets were validated against which model
- what rollback target exists

This applies to:

- LLMs
- SLMs
- embedding models
- rerankers

## 6. Prompt management

Prompt management should answer:

- what prompt is active now
- what previous prompt was active
- what evaluation evidence exists for a new prompt
- what model a prompt was validated against
- who approved activation

Prompt versioning is one of the most important and most commonly missing LLMOps features.

## 7. Retrieval and feature data management

In RAG systems, the retrieval layer behaves like a special data and feature layer.

Important assets to manage:

- source corpus version
- chunking strategy version
- embedding model version
- index version
- metadata schema version
- policy filters affecting retrieval

If retrieval assets are not versioned, AI behavior becomes hard to explain.

## 8. Experiment tracking

A strong LLMOps setup tracks:

- model version
- prompt version
- retrieval config
- dataset version
- parameters
- latency
- cost
- evaluation scores

This creates a stable answer to:

- what changed
- why did quality move
- what should be promoted or rolled back

## 9. Observability in LLMOps

Observability should include:

- prompt and response traces
- token usage
- latency
- cost
- error outcomes
- retrieval quality
- groundedness or faithfulness
- user feedback

LLMOps observability is more than system metrics. It must connect AI behavior to versions and runs.

## 10. Governance in LLMOps

Governance should answer:

- who approved the model or prompt
- whether the asset is active or inactive
- what policy version applied
- whether the asset handles sensitive data
- what evidence exists for safety or quality

## 11. LLM vs SLM

### LLM concerns
- expensive serving
- long-context tuning
- GPU scheduling
- high-latency and high-cost paths

### SLM concerns
- low-cost routing
- local or edge serving
- specialized use cases
- fallback usage

A mature LLMOps system tracks both.

## 12. Bottom line

LLMOps is the management system for AI assets and AI change.

It should make it easy to answer:

- what is active
- what changed
- what performed well
- what should be rolled back
- what is safe to promote
