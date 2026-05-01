# DEMO — §48 Explain Endpoint

## What it is

`/api/v1/explain?prediction_id=<id>` — the answer to §48.12:

> "If a regulator demands explanation of a specific past decision and
> you cannot produce one within minutes, your AI system is not
> deployable in any regulated jurisdiction."

Lives in `evaluation-svc` because that's where AI decision quality
measurement already lives.

## Endpoints

```
POST /api/v1/decisions      Seed a §48.4 decision audit row
GET  /api/v1/explain?prediction_id=<id>
                            Retrieve the row + its explanation
                            surfaces, or 404
```

`POST /api/v1/decisions` is the same shape an inference-time hook
would push when a prediction fires. In production this becomes a
Kafka consumer; the HTTP endpoint stays as the audit-tooling
backdoor.

## §48.4 row shape (DecisionAuditRow)

| Field | §48 mandate |
|---|---|
| `request_id` | Trace pivot |
| `prediction_id` | Idempotent key |
| `timestamp` | Audit |
| `tenant_id` | Multi-tenant scoping |
| `user_id` | Accountability |
| `model_name` + `model_version` | Reproducibility |
| `prompt_version` | RAG/LLM reproducibility |
| `input_features` + `input_hash` | What the model saw |
| `prediction` + `confidence` | What it said |
| `explanation` | SHAP / LIME / counterfactual / RAG citations |
| `rules_applied` | Policy attribution |
| `guardrails_triggered` | Safety gates |
| `human_override` | HITL flag |
| `fairness_flag` | Disparate-impact check |
| `latency_ms` + `cost_tokens` | Performance |

## ExplainResponse (the 5 §48 surfaces)

```json
{
  "audit": { /* full DecisionAuditRow */ },
  "explanation_method": "shap",
  "confidence": 0.87,
  "counterfactual": "If debt_ratio had been below 0.50…",
  "fairness_status": "pass"
}
```

The audit row is included verbatim so a regulator gets the raw
decision details and the explanation in one payload.

## Storage

V1 stub: in-process LRU ring buffer (capacity 10k). Survives
inflight requests but not service restart.

V2 (planned): Postgres `governance.decision_audit` per the §48
retention policy — 7 years for regulated, 1 year hot for
unregulated. The schema is the durable contract; the storage is
incidental.

## Drill

[`mcp/tests/drill_explain_endpoint.py`](../mcp/tests/drill_explain_endpoint.py)
— 6 steps, **3 negative assertions**.

| Step | Type | Locks |
|---|---|---|
| 1 | POST a valid row | 201 + echoed body |
| 2 | GET retrieves it | 200 + matching prediction_id |
| 3 | GET phantom_id | **404 + DECISION_NOT_FOUND** (no fabrication) |
| 4 | GET no param | **422** (no implicit "latest") |
| 5 | POST confidence=1.5 | **422** (schema gate 0.0–1.0) |
| 6 | Response shape | All 5 §48 surfaces present |

The negatives are the load-bearing part. Without them, a stub
that returns `{}` for every request would still "pass" naively —
the negatives prove the validation paths fire.

## Run

```bash
# from repo root
.venv/bin/python mcp/tests/drill_explain_endpoint.py
```

(Uses TestClient against the real FastAPI app + Pydantic
validation — no mocks of business logic per §43.)

## Files

| Path | Purpose |
|---|---|
| `services/evaluation-svc/app/explain.py` | Schemas + store + router builder |
| `services/evaluation-svc/app/main.py` | Wires `register_explain(app)` into the FastAPI app |
| `mcp/tests/drill_explain_endpoint.py` | Drill (6 steps, 3 negative) |

## Composition

| Composes with | Why |
|---|---|
| §48 Explainability | This is the gate §48.10 demands; before this commit, only a deep-dive page described it |
| §38 AI Governance | Audit row is the §38.7 "identifiable, reproducible, explainable" record |
| §47 Architecture | request_id pipe lands here as the audit row's correlation pivot |
| §43 Drill discipline | 3 negative assertions — phantom 404, missing param 422, confidence 422 |
| `evaluation-svc` (sibling) | Already owns evaluation/regression-gate; explain joins as the third surface |
