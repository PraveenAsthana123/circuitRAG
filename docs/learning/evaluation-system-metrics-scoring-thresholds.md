# Evaluation System: Metrics, Scoring, And Thresholds

This document covers how to design evaluation for RAG, fine-tuning, agentic, and backend AI systems.

## 1. Core Concept

Evaluation is the quality control system of AI architecture.

Without evaluation:
- quality is opinion
- regressions go unnoticed
- prompt and model changes are unsafe
- production incidents are harder to explain

With evaluation:
- quality becomes measurable
- rollout decisions become defensible
- regressions can be blocked before release

## 2. 5W

| Dimension | Explanation |
| --- | --- |
| What | Metrics, thresholds, score aggregation, and pass/fail logic for AI output quality |
| Why | AI systems are probabilistic; evaluation is what makes them governable |
| Where | Offline benchmark runs, online production checks, regression gates, dashboards |
| When | Before rollout, during runtime, after incidents, and on a scheduled basis |
| Who | AI engineers, backend engineers, platform owners, reviewers, architects |

## 3. Evaluation Layers

### Retrieval evaluation
- context precision
- context recall
- chunk relevance
- ranking quality

### Generation evaluation
- answer relevance
- answer correctness
- faithfulness
- hallucination rate
- structured-output validity

### Agent/tool evaluation
- tool choice correctness
- action safety
- retry behavior
- bounded execution

### System evaluation
- latency
- cost
- failure rate
- degradation quality

## 4. Evaluation Architecture

```text
Golden dataset
  -> candidate system version
  -> retrieval evaluation
  -> generation evaluation
  -> safety evaluation
  -> aggregate scoring
  -> threshold checks
  -> pass / fail / investigate
```

## 5. Sequence Flow

```text
Engineer changes prompt/model/retrieval logic
  -> evaluation run triggered
  -> dataset loaded
  -> system executes full pipeline
  -> scores computed per metric
  -> baseline comparison made
  -> regression gate decision returned
```

## 6. Network Flow

```text
Dataset store
  -> evaluation service
  -> retrieval path
  -> inference path
  -> guardrail path
  -> metric aggregator
  -> report / dashboard / CI gate
```

## 7. Important Metrics

| Area | Metric | Why it matters |
| --- | --- | --- |
| Retrieval | Recall@K | Did we retrieve the needed evidence? |
| Retrieval | Precision@K | How much noise is in the context set? |
| Retrieval | MRR / nDCG | Was the right evidence ranked early enough? |
| Generation | Faithfulness | Did the answer stay grounded in evidence? |
| Generation | Relevance | Did it answer the actual question? |
| Generation | Correctness | Was the factual content correct? |
| Safety | Policy violation rate | Did the system break rules? |
| Runtime | p95 / p99 latency | Is the system usable? |
| Runtime | Cost per answer | Is the system economically viable? |

## 8. Scoring Strategy

Avoid one-metric evaluation.

Use weighted scoring:

```text
overall_score =
  0.30 * retrieval_quality
+ 0.30 * faithfulness
+ 0.20 * answer_relevance
+ 0.10 * safety_score
+ 0.10 * latency_score
```

Keep raw metrics visible too.
Weighted scores are useful for rollups, not for hiding failure detail.

## 9. Thresholds

Thresholds create release discipline.

Examples:
- Faithfulness >= 0.90
- Retrieval Recall@10 >= 0.85
- Hallucination rate <= 0.03
- p95 latency <= 2.5s
- Cost per request <= target budget

Use:
- hard fail thresholds for safety and severe quality regressions
- warning thresholds for degradations that need review

## 10. Offline vs Online Evaluation

### Offline
- reproducible
- cheaper
- safer before release
- limited by dataset quality

### Online
- real user traffic
- captures true behavior
- harder to control
- must be observable and safe

Best practice:
- use offline evaluation for gating
- use online evaluation for drift detection and validation

## 11. Common Failures

| Failure | Root cause | Fix |
| --- | --- | --- |
| Great offline score, bad production behavior | benchmark mismatch | refresh dataset with real queries |
| Retrieval score good, answer bad | weak prompt or generation path | isolate retrieval vs generation layers |
| Good average score, bad edge cases | over-optimized median behavior | add adversarial and long-tail tests |
| Cost spikes after improvement | quality gained by brute-force context growth | add cost thresholds |

## 12. What To Explain In Interview

Say:

> I separate evaluation into retrieval, generation, safety, and runtime layers. I run offline benchmarks before rollout, compare against a baseline, enforce hard thresholds for safety and major regressions, and then watch online signals for drift, cost, and user-impacting failures.

## 13. Sample Evaluation Skeleton

```python
def evaluate_run(results: list[dict]) -> dict:
    total = len(results)
    faithfulness = sum(r["faithful"] for r in results) / total
    relevance = sum(r["relevant"] for r in results) / total
    avg_latency = sum(r["latency_s"] for r in results) / total
    return {
        "faithfulness": faithfulness,
        "relevance": relevance,
        "avg_latency_s": avg_latency,
        "pass": faithfulness >= 0.9 and relevance >= 0.85 and avg_latency <= 2.5,
    }
```

## 14. Brutal Insight

Most teams say they evaluate.

Real evaluation means:
- versioned datasets
- explicit metrics
- thresholds
- baselines
- rollback decisions

