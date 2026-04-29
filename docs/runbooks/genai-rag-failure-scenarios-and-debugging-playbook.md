# GenAI / RAG Failure Scenarios And Debugging Playbook

This playbook covers common production failures in GenAI, RAG, and agentic systems and how to debug them.

## 1. Debugging Order

Use this order:

1. identify user-visible symptom
2. identify request / correlation ID
3. check retrieval
4. check prompt/context
5. check model/runtime
6. check guardrails/policy
7. check cache / stale state
8. check deployment/version drift

## 2. Failure Scenarios

### Wrong answer

Likely causes:
- wrong chunks retrieved
- ranking weak
- prompt weak
- answer not grounded

Checks:
- retrieved chunks
- reranker scores
- final prompt
- citations

Fixes:
- improve chunking
- improve metadata filtering
- add reranking
- strengthen grounding prompt

### Hallucinated answer

Likely causes:
- weak no-answer behavior
- insufficient context
- weak guardrails

Checks:
- retrieved evidence
- confidence score
- guardrail result

Fixes:
- add fail-safe no-answer path
- reduce unsupported synthesis
- add faithfulness checks

### No answer when answer exists

Likely causes:
- retrieval miss
- stale index
- bad metadata filter

Checks:
- query normalization
- vector hits
- lexical hits
- tenant/access filter

Fixes:
- re-index
- improve hybrid retrieval
- inspect metadata filters

### Slow response

Likely causes:
- too many candidates
- reranking too much
- too much prompt context
- model too heavy

Checks:
- retrieval latency
- reranker latency
- token count
- first-token latency

Fixes:
- reduce K
- reduce rerank set
- compress context
- route to smaller model

### Cross-tenant leakage

Likely causes:
- missing tenant filter
- cache key not tenant-scoped
- broken policy layer

Checks:
- payload filter
- query logs
- cache keys
- audit trail

Fixes:
- enforce tenant filter in repo layer
- namespace cache keys
- add isolation proof test

### Agent loop

Likely causes:
- no max-iteration cap
- poor stop condition
- tool retry loop

Checks:
- iteration counter
- cost budget
- step logs
- decision node transitions

Fixes:
- max iterations
- wall-clock timeout
- tool cooldown
- HITL escalation

## 3. Debugging Checklists

### Retrieval Checklist

- Was the right source ingested?
- Was it chunked correctly?
- Was it embedded with correct model version?
- Was the right tenant filter applied?
- Was the index fresh?
- Were candidate chunks reranked?

### Prompt Checklist

- Was the right prompt version used?
- Did context exceed token budget?
- Was context truncated?
- Did the prompt allow unsupported synthesis?

### Model Checklist

- Was the correct model selected?
- Did fallback trigger?
- Was model latency abnormal?
- Was output quality lower after routing change?

### Guardrail Checklist

- Did guardrails fire?
- Were they too weak?
- Were they too strict?
- Did they redact needed evidence?

### Cache Checklist

- Was this a stale cache hit?
- Was TTL too long?
- Was tenant keying correct?
- Was the query normalized correctly?

## 4. Production Metrics To Check First

- retrieval latency
- first-token latency
- p95 response latency
- token count
- cache hit rate
- retrieval miss rate
- hallucination / faithfulness failure rate
- human escalation rate
- breaker open rate

## 5. Sample Incident Flow

```text
User reports bad answer
  -> find request ID
  -> inspect retrieved chunks
  -> inspect prompt version + model version
  -> inspect answer + citations
  -> classify issue
  -> patch retrieval / prompt / policy / model routing
  -> add regression case
```

## 6. Final Insight

The best debugging move is usually not “look at the model.”
It is “walk the retrieval and control path in order.”
