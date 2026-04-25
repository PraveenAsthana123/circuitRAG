# LLMOps Entity and Lifecycle Matrix

This matrix shows the major LLMOps entities and the lifecycle states they should support.

## 1. Core lifecycle states

Common states:

- `draft`
- `candidate`
- `active`
- `inactive`
- `deprecated`
- `archived`
- `rolled_back`

Not every entity uses every state, but most should use at least a subset.

## 2. Entity matrix

| Entity | Purpose | Important versions | Common states | Key questions |
|---|---|---|---|---|
| dataset | source data asset | dataset version | draft, candidate, active, archived | what data fed eval or training |
| evaluation dataset | benchmark asset | dataset version | draft, active, archived | what benchmark was used |
| retrieval corpus | indexed knowledge source | corpus version | candidate, active, inactive, archived | what documents are searchable now |
| chunk version | chunking output set | chunk version | candidate, active, inactive, archived | what chunking strategy is live |
| embedding model | vectorization model | model version | candidate, active, inactive, deprecated | what embeddings built the index |
| vector index | retrieval index | index version | candidate, active, inactive, archived | which index is currently serving |
| reranker model | reranking model | model version | candidate, active, inactive | which reranker shapes results |
| prompt | prompt template | prompt version | draft, candidate, active, inactive, deprecated | which prompt is live |
| policy | safety/guardrail policy | policy version | draft, active, inactive, deprecated | what rules applied |
| llm model | large model | model version | candidate, active, inactive, deprecated, rolled_back | which model serves requests |
| slm model | small model | model version | candidate, active, inactive | which low-cost model is available |
| experiment run | tracked experiment | run ID | draft, completed, archived | what config produced what score |
| deployment | live serving config | deployment version | candidate, active, inactive, rolled_back | what is serving in each env |
| evaluation report | quality evidence | report version | draft, approved, archived | what evidence justified rollout |

## 3. Active vs inactive meaning

### Active
- currently used in production or live environment
- should be visible in admin/operator UI
- should be tied to observability and support workflows

### Inactive
- still valid but not currently serving live traffic
- may still be available for rollback or shadow testing

### Deprecated
- should no longer be used for new rollouts
- retained temporarily for traceability or controlled rollback only

### Archived
- retained for history and audit
- not expected to serve live traffic

## 4. Repo-specific high-value entities

For this repo, the highest-value entities to operationalize first are:

1. prompt
2. llm model
3. embedding model
4. vector index
5. retrieval corpus
6. evaluation report

## 5. Best operator visibility fields

For each active entity, operators should be able to see:

- name
- version
- state
- owner
- environment
- activated_at
- previous_version
- rollback_target
- related evaluation evidence

## 6. Best governance fields

Each governed entity should also carry:

- who approved it
- approval timestamp
- change reason
- linked code or release reference
- linked dataset or eval run where relevant

## 7. Bottom line

The core LLMOps principle is simple:

every important AI asset should have:

- identity
- version
- state
- owner
- observability
- rollback story

Without that, LLMOps is incomplete.
