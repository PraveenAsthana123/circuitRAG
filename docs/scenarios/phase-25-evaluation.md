# Phase 25 — Model Evaluation & Benchmarking

Without eval you *think* the system works. With eval you *prove* it.

Scope: LLM · RAG · MCP · Agent · A2A (Agent-to-Agent).

---

## 1. Five evaluation layers

| Layer | What we evaluate |
| --- | --- |
| LLM | raw model quality |
| RAG | retrieval + generation |
| MCP | tool / action correctness |
| Agent | multi-step reasoning |
| A2A | agent collaboration quality |

## 2. LLM evaluation

### Metrics

| Metric | Meaning |
| --- | --- |
| Accuracy | correct answer |
| BLEU / ROUGE | text similarity |
| Semantic similarity | meaning match |
| Hallucination rate | unsupported claims |
| Toxicity | unsafe output |
| Latency | response time |
| Cost / token | efficiency |

### Test scenarios

| Scenario | Expected |
| --- | --- |
| Factual question | correct answer |
| Ambiguous query | clarification |
| Unsafe query | refusal |
| Long context | coherent answer |
| Multi-language | correct response |
| Adversarial prompt | safe behaviour |

## 3. RAG evaluation (most important)

### Metrics

| Metric | Meaning |
| --- | --- |
| Context Precision | retrieved chunks relevant |
| Context Recall | important chunks retrieved |
| Faithfulness | answer grounded in context |
| Answer Relevance | matches question |
| Citation Accuracy | correct source attributed |
| No-answer accuracy | avoids hallucination |

### Test scenarios

| Scenario | Expected |
| --- | --- |
| Correct doc present | retrieved |
| Wrong doc present | filtered |
| No doc present | no-answer |
| Multi-doc answer | combined correctly |
| Outdated doc | ignored (freshness filter) |
| Restricted doc | blocked (ABAC) |
| Noisy retrieval | reranked |
| Large context | trimmed |

## 4. MCP evaluation

### Metrics

| Metric | Meaning |
| --- | --- |
| Tool-selection accuracy | correct tool chosen |
| Action success rate | successful execution |
| Latency | tool execution time |
| Idempotency success | no duplicate actions |
| Failure recovery | retry / queue works |
| Security compliance | no unauthorized action |

### Test scenarios

| Scenario | Expected |
| --- | --- |
| Create ticket | correct tool |
| Invalid tool | blocked |
| Tool failure | retry or fallback |
| Duplicate request | ignored via idempotency key |
| Unauthorized action | blocked |
| Long-running task | async handled |

## 5. Agent evaluation

### Metrics

| Metric | Meaning |
| --- | --- |
| Task success rate | completed correctly |
| Step accuracy | each step valid |
| Tool-usage accuracy | correct sequence |
| Iteration count | efficient loop |
| Cost per task | token + tool cost |
| Failure recovery | retry / adjust |

### Test scenarios

| Scenario | Expected |
| --- | --- |
| Multi-step task | correct sequence |
| Missing data | re-query |
| Tool failure | fallback |
| Complex reasoning | correct plan |
| Infinite-loop risk | stopped by Agent-Loop CB |
| Unsafe action | blocked |

## 6. A2A (Agent-to-Agent) evaluation

### Metrics

| Metric | Meaning |
| --- | --- |
| Coordination accuracy | agents collaborate correctly |
| Conflict resolution | correct decision |
| Message quality | meaningful exchange |
| Latency | coordination speed |
| Consistency | same result across runs |

### Test scenarios

| Scenario | Expected |
| --- | --- |
| Planner + Executor | aligned |
| Multi-agent debate | best answer chosen |
| Conflicting outputs | resolved |
| Parallel agents | synchronized |
| One-agent failure | recovery |
| Shared memory | consistent state |

## 7. TDD

```python
def test_faithfulness_threshold():
    score = run_eval_on_golden_set()["faithfulness"]
    assert score > 0.90

def test_retrieval_recall_threshold():
    assert run_eval_on_golden_set()["recall_at_5"] > 0.80

def test_hallucination_rate_threshold():
    assert run_eval_on_golden_set()["hallucination_rate"] < 0.05
```

## 8. BDD

```
Feature: RAG evaluation

Scenario: Correct answer retrieval
  Given a question with known answer
  When RAG pipeline runs
  Then answer should be grounded in retrieved context

Scenario: No-answer scenario
  Given no relevant document
  When query is processed
  Then system responds with "I don't know"
```

## 9. Model-driven evaluation record

```json
{
  "request_id": "req_001",
  "question": "Travel policy?",
  "retrieved_chunks": 5,
  "context_precision": 0.90,
  "context_recall": 0.85,
  "faithfulness": 0.92,
  "answer_relevance": 0.95,
  "hallucination": false,
  "latency_ms": 2400,
  "cost_usd": 0.0038,
  "model_version": "llama3:8b",
  "prompt_version": "v2"
}
```

## 10. Output-first design

| Output goal | Metric |
| --- | --- |
| Correct answer | accuracy |
| Grounded answer | faithfulness |
| Fast answer | latency |
| Low cost | tokens / $ |
| Safe answer | policy compliance |

## 11. Failure matrix

| Failure | Cause | Fix |
| --- | --- | --- |
| Hallucination | bad retrieval | improve chunking / retrieval |
| Wrong ranking | no reranker | add reranker |
| Tool misuse | bad agent logic | improve planner |
| Inconsistent output | unstable model | temperature control |
| High latency | large context | optimize tokens |
| High cost | large model | route model |
| Poor collaboration | bad A2A | improve coordination |
| Security violation | missing guardrails | enforce policy |

## 12. Benchmark datasets

| Type | Example |
| --- | --- |
| QA dataset | internal KB |
| Policy dataset | HR / finance |
| Code dataset | repo-based |
| Synthetic dataset | generated |
| Adversarial dataset | prompt-injection corpus |
| Multilingual | global use-cases |
| Evaluation dataset | golden Q/A |

## 13. Tools

| Need | Tools |
| --- | --- |
| RAG evaluation | Ragas · DeepEval |
| LLM eval | OpenAI evals · HF |
| Experiment tracking | MLflow · Weights & Biases |
| A/B testing | feature flags |
| Observability | Prometheus + Grafana |
| Dataset management | DVC |

## 14. Exit criteria

- [ ] Golden dataset ≥ 50 Q/A committed to `docs/eval/golden/*.jsonl`.
- [ ] Tests:
  - [ ] `tests/eval/test_rag_metrics.py`
  - [ ] `tests/eval/test_llm_quality.py`
  - [ ] `tests/eval/test_mcp_actions.py`
  - [ ] `tests/eval/test_agent_workflow.py`
  - [ ] `tests/eval/test_a2a_collaboration.py`
- [ ] `make eval` runs Ragas + DeepEval + writes report to `data/eval/<date>/report.json`.
- [ ] CI gate: merge blocked on faithfulness drop > 3% or precision@5 drop > 5%.
- [ ] Online eval consumer samples 1% of `rag.response.generated.v1`.
- [ ] Weekly regression report surfaced in governance dashboard.

## 15. Brutal checklist

| Question | Required |
| --- | --- |
| Can you measure RAG quality? | Yes |
| Can you detect hallucination? | Yes |
| Can you compare models? | Yes |
| Can you benchmark retrieval? | Yes |
| Can you validate MCP actions? | Yes |
| Can you evaluate agents? | Yes |
| Can you test agent collaboration (A2A)? | Yes |
| Can you track improvement over time? | Yes |
