# Repo-Specific LLMOps Architecture

This document maps LLMOps concepts to this repo.

## 1. Why LLMOps matters here

This repo already contains the beginnings of an LLMOps-capable architecture:

- prompt handling
- retrieval pipelines
- evaluation service
- observability direction
- governance direction
- admin/operator surfaces

The repo is not yet a full LLMOps platform, but it clearly has the right structural pieces.

## 2. Main LLMOps layers already visible

### Prompt layer
- prompt builder and prompt repository concepts exist in `inference-svc`
- admin already exposes prompt registry read surfaces

### Retrieval layer
- ingestion, chunking, embeddings, retrieval, and reranking are explicit services
- this makes corpus, chunk, embedding, and index versions operationally important

### Evaluation layer
- evaluation service exists
- offline evaluation direction already exists in docs and service structure

### Observability layer
- OTel direction exists
- Prometheus and Grafana direction exist
- admin views already expose operational state

### Governance layer
- audit and policy concepts exist
- prompt status and lifecycle concepts already appear in governance migrations and admin views

## 3. Repo-relevant LLMOps entities

The most important LLMOps entities for this repo are:

- prompt
- prompt version
- retrieval strategy
- chunking strategy
- embedding model
- vector index
- reranker model
- LLM serving backend
- evaluation report
- deployment config

## 4. What is already strong

### Strong direction
- prompt visibility exists
- retrieval components are explicit
- evaluation is not ignored
- observability is treated as first-class
- governance and audit are part of the architecture

### Why that matters
It means the repo already avoids the common anti-pattern of having an LLM but no operational control plane.

## 5. What is still missing or thinner

### Prompt registry maturity
- stronger prompt lifecycle workflow
- explicit active/candidate/deprecated transitions
- clearer approval and rollback path

### Model registry maturity
- clearer model inventory
- explicit active/inactive LLM and embedding versions
- stronger linkage between prompt and model version

### Retrieval asset lifecycle
- chunk version registry
- embedding/index version lineage
- re-embed and re-index lifecycle visibility

### Experiment tracking
- richer run comparison
- parameter and score history
- stronger promotion logic

### Deployment visibility
- better mapping from active model/prompt to live environment
- clearer release and rollback evidence

## 6. Best LLMOps architecture shape for this repo

### Data and retrieval assets
- ingestion-svc owns source processing
- retrieval-svc owns retrieval runtime behavior
- governance/admin surfaces expose active retrieval and prompt state

### Prompt and model state
- governance or config-backed registry owns prompt lifecycle
- model-serving layer exposes active model metadata
- admin UI shows current active set

### Evaluation
- evaluation-svc computes or stores benchmark and regression outcomes
- promotion should eventually depend on evaluation evidence

### Observability
- traces, metrics, and admin views should include prompt version, model version, and retrieval strategy

## 7. Best next LLMOps improvements

1. formal prompt lifecycle states
2. formal model and embedding inventory
3. retrieval-asset version lineage
4. experiment run comparison
5. deployment-to-version mapping
6. stronger admin visibility for active vs inactive assets

## 8. Bottom line

This repo already has the right architecture direction for LLMOps:

- prompts matter
- retrieval assets matter
- evaluation matters
- observability matters
- governance matters

The main next step is to make those entities and lifecycles more explicit and operational.
