# Feedback Loop: Human And AI Learning System

This document explains how to design the feedback loop that turns a static AI system into an improving one.

## 1. Core Concept

Feedback is how the system learns from reality.

Without a feedback loop:
- the system repeats the same mistakes
- quality drift is invisible
- human operators become manual patch layers

With a feedback loop:
- user pain becomes labeled data
- retrieval and prompts improve
- evaluation datasets get stronger

## 2. 5W

| Dimension | Explanation |
| --- | --- |
| What | The capture, review, labeling, and reuse of user/system feedback |
| Why | Production behavior always reveals failures that offline design missed |
| Where | UI feedback widgets, operator queues, audit surfaces, evaluation datasets, retraining or reindex flows |
| When | After answers, after tool actions, after incidents, and during periodic quality review |
| Who | Users, operators, reviewers, AI engineers, platform owners |

## 3. Feedback Loop Flow

```text
User query
  -> system answer / action
  -> user feedback
  -> human review
  -> label / classify failure
  -> update dataset / rules / prompts / retrieval
  -> re-evaluate
  -> redeploy or reindex
```

## 4. Types Of Feedback

| Type | Example | Use |
| --- | --- | --- |
| Explicit feedback | thumbs up / thumbs down | direct signal |
| Implicit feedback | copy, retry, reformulate query | weak but useful signal |
| Operator review | flagged draft or answer review | trusted adjudication |
| System feedback | low confidence, breaker trip, guardrail hit | internal quality signal |

## 5. Sequence Flow

```text
User submits query
  -> system responds
  -> user rates response
  -> review queue collects bad or uncertain cases
  -> reviewer labels failure type
  -> quality pipeline updates datasets / rules
  -> future system version is reevaluated
```

## 6. Network Flow

```text
Client UI
  -> feedback endpoint
  -> feedback store
  -> review queue / governance service
  -> evaluation dataset builder
  -> prompt / retrieval / training update path
```

## 7. Failure Taxonomy

Track feedback by failure class:

- wrong retrieval
- missing retrieval
- hallucinated answer
- incomplete answer
- policy violation
- bad tool decision
- latency frustration
- stale content

This is stronger than just positive vs negative.

## 8. Human Review Layer

Human review is critical because raw user feedback is noisy.

Reviewers should decide:
- was retrieval wrong?
- was the prompt wrong?
- was the model wrong?
- was the data missing?
- was policy too strict or too weak?

## 9. How Feedback Should Be Used

| Feedback result | Action |
| --- | --- |
| Retrieval miss | improve chunking, indexing, metadata, hybrid search |
| Hallucination | strengthen grounding prompt or guardrails |
| Wrong document selected | improve ranking / reranking |
| User dissatisfaction with style | prompt or model behavior adjustment |
| Repeated incident cluster | add golden test case and regression gate |

## 10. Common Failures

| Failure | Root cause | Fix |
| --- | --- | --- |
| Feedback collected but not used | no operational owner | assign feedback triage process |
| Thumbs down with no explanation | too little context | ask failure category |
| Reviewer overload | too much raw feedback | triage by severity and confidence |
| Same issue keeps returning | no regression dataset update | feed reviewed cases into evaluation |

## 11. What To Explain In Interview

Say:

> I treat feedback as structured data, not UI decoration. User signals, operator review, and system signals are turned into labeled failure categories, then fed back into retrieval improvements, prompt updates, evaluation datasets, and eventually retraining or reindexing.

## 12. Sample Feedback Record

```json
{
  "query": "What is the travel reimbursement policy?",
  "answer_id": "ans_123",
  "feedback": "negative",
  "reason": "wrong_source",
  "tenant_id": "tenant_a",
  "review_status": "confirmed",
  "action_taken": "add_retrieval_regression_case"
}
```

## 13. Brutal Insight

Most teams think feedback means thumbs up / down.

Real feedback systems mean:
- structured failure taxonomy
- human validation
- dataset improvement
- measurable follow-through

