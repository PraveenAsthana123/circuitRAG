# Phase 22 — Token Design, Budgeting, Estimation

Tokens = latency + cost + accuracy + failure control. Most silent RAG failures trace back to a token-budget mistake.

---

## 1. Token composition in a RAG request

| Component | Example tokens |
| --- | --- |
| User query | 50 |
| System prompt | 150 |
| Retrieved chunks (top-K) | 1200 |
| Instructions | 200 |
| **Total input** | **1600** |
| Output | 400 |
| **Total** | **2000** |

## 2. Budget allocation (rule of thumb)

| Component | % of context window |
| --- | --- |
| Retrieved context | 50–70% |
| System prompt | 10–20% |
| User query | 5–10% |
| Output reserve | 15–25% |

### Example — 8K model

| Component | Tokens |
| --- | --- |
| Max context | 8000 |
| Reserve for output | 1500 |
| Available input | 6500 |
| Context chunks | ~4000 |
| Prompt + query | ~2500 |

## 3. Estimation methods

| Method | Use |
| --- | --- |
| `tiktoken` / HF tokenizer | accurate pre-flight |
| `len(text) / 4` approx | quick estimate |
| Streaming tokens | during generation |
| Historical average | log-driven |

```python
def estimate_tokens(text: str) -> int:
    # Coarse estimate — use tiktoken for production paths.
    return len(text) // 4
```

## 4. Scenario → strategy

| Scenario | Approach |
| --- | --- |
| Pre-LLM call | estimate before send |
| During retrieval | adjust top-K |
| During prompt build | trim / compress |
| Streaming response | live count |
| Multi-turn chat | accumulate + summarize older turns |
| MCP action | include tool output in budget |
| Large docs | hierarchical chunks + summarize |
| Multi-language | token-per-char varies; measure per language |
| Long answers | cap output tokens |
| Cost control | pre-check budget; reject or degrade |

## 5. Failure matrix

| Problem | Cause | Fix |
| --- | --- | --- |
| Token overflow | too many chunks | reduce top-K |
| High cost | large prompts | compress context |
| Slow response | too many tokens | optimize |
| Truncated answer | no output reserve | reserve tokens |
| Context loss | chunks too small | rebalance |
| Chat history explosion | no summarization | summarize turns > N |
| Tool output overflow | large MCP response | summarize before re-inject |
| Language inflation | non-English | adjust per-language multiplier |
| Prompt bloat | verbose template | shrink + A/B test |
| Cache miss | token mismatch | normalize query first |

## 6. Optimization strategies

| Strategy | Benefit |
| --- | --- |
| Context compression | fewer tokens |
| Chunk filtering + rerank | keep best chunks |
| Query rewrite | smaller context |
| Conversation summarization | cap history |
| Semantic cache | skip LLM entirely |
| Model routing | smaller model when safe |
| Prompt optimization | reduce overhead |
| Hard token cap | enforce limit |
| Streaming output | better UX |

## 7. Observability metrics

| Metric | Purpose |
| --- | --- |
| `input_tokens` | cost tracking |
| `output_tokens` | cost + UX |
| `total_tokens` | overall |
| `tokens_per_query` | efficiency |
| `cost_per_query` | FinOps |
| `token_overflow_count` | failure detection |
| `avg_prompt_size` | optimization signal |
| `token_distribution` | tuning histogram |

## 8. TDD

```python
def test_token_limit():
    tokens = estimate_tokens(prompt)
    assert tokens < MAX_CONTEXT_LIMIT
```

### BDD

```
Feature: Token management

Scenario: Prevent token overflow
  Given a large document
  When building the prompt
  Then token count must not exceed model limit

Scenario: Adjust context dynamically
  Given limited token budget
  When retrieving chunks
  Then top-K is reduced to fit budget
```

## 9. Model-driven record

```json
{
  "request_id": "req_001",
  "input_tokens": 1600,
  "output_tokens": 400,
  "total_tokens": 2000,
  "model": "llama3",
  "token_limit": 8000,
  "truncated": false,
  "top_k_used": 6
}
```

## 10. Exit criteria

- [ ] `services/inference-svc/app/token_manager.py` with `estimate_tokens` + `fits_budget` + `trim_to_budget`.
- [ ] Tests:
  - [ ] `tests/rag/test_token_limit.py`
  - [ ] `tests/rag/test_token_overflow.py`
  - [ ] `tests/rag/test_token_estimation.py`
  - [ ] `tests/rag/test_token_budget.py`
- [ ] Usage events published on `usage.tokens.v1` for every LLM call.
- [ ] Grafana panel: tokens + cost per tenant per day.
- [ ] Token CB integration: budget exceeded → `TokenBreakerDecision.BLOCK`.

## 11. Brutal checklist

| Question | Required |
| --- | --- |
| Can token usage be estimated before the call? | Yes |
| Can the system prevent overflow? | Yes |
| Can top-K adjust dynamically? | Yes |
| Is output token reserved? | Yes |
| Is cost per query tracked? | Yes |
| Can chat history be compressed? | Yes |
| Are token metrics observable? | Yes |
