# AI Governance Guide

> §19 mandate. Substantive content lives at:
>
> See: [`security-compliance-ai-governance-and-growth-os-blueprint.md`](security-compliance-ai-governance-and-growth-os-blueprint.md) — full blueprint
> See: [`~/.claude/CLAUDE.md`](../../../.claude/CLAUDE.md) §38, §39, §40, §48 — global governance rules
> See: [`adr/`](adr/) — 23 ADRs governing project AI decisions
> See: [`../../mcp/tests/drill_explain_endpoint.py`](../../mcp/tests/drill_explain_endpoint.py) — §48 explainability drill
> See: [`../DEMO-EXPLAIN-ENDPOINT.md`](../DEMO-EXPLAIN-ENDPOINT.md) — `/api/v1/explain` endpoint

## The 15 production gates (CLAUDE.md §38.1)

Every release must clear:

1. Business goal + KPI defined
2. Requirements + acceptance criteria
3. Architecture (HLD + LLD + ADR)
4. Security (auth, secrets, PII, threat model)
5. Data (schema, lineage, retention)
6. Backend (idempotency, breakers, retries)
7. Frontend (a11y, responsive, browser)
8. AI/LLM (prompt versioning, eval, guardrails)
9. Testing (unit → integration → E2E → chaos)
10. Performance (latency, throughput, cost)
11. Operations (logs, traces, metrics)
12. Reliability (fallback, DR, rollback)
13. Deployment (CI/CD, canary)
14. Governance (ownership, approvals)
15. Documentation (runbook, support)

## HARD STOPS — do not deploy if missing

- ❌ No rollback plan
- ❌ No observability (logs/traces/metrics)
- ❌ No security review
- ❌ No AI guardrails (for AI features)
- ❌ No ownership defined

## Decision audit row (§38.3 + §48.4)

Every regulated AI decision persists:

```
request_id, prediction_id, timestamp, tenant_id, user_id,
model_name, model_version, prompt_version, input_features,
input_hash, prediction, confidence, explanation,
rules_applied, guardrails_triggered, human_override,
fairness_flag, latency_ms, cost_tokens, feedback
```

This is the SCHEMA. The storage is incidental (in-process LRU
today; Postgres `governance.decision_audit` next iteration).

The **`/api/v1/explain?prediction_id=<id>`** endpoint serves rows
back to a regulator within minutes per §48.12.

## Explainability four-part contract for RAG (§48.5)

A RAG answer is explainable only if all four are persisted:

1. **Retrieval trail** — chunk IDs + similarity + rerank scores
2. **Prompt rendering** — final prompt sent to LLM (post-templating)
3. **Citation mapping** — answer-span → source chunk ID
4. **Guardrail trace** — input + output filters fired

## Counterfactuals for regulated decisions

EU AI Act Art. 86 demands a right to explanation. circuitRAG
encodes counterfactuals in `ExplanationDetail.counterfactual` (see
[`services/evaluation-svc/app/explain.py`](../../services/evaluation-svc/app/explain.py)).

Counterfactuals must be:

- **Minimal** — smallest flip
- **Actionable** — only changeable features (income, debt) — never age/gender/race
- **Plausible** — within realistic distribution

## Fairness gate

Pre-deploy: disparate impact ≥ 0.8, equal-opportunity gap < 5%.
Persisted in `fairness_flag` field of decision audit row.

## Brutal rule (CLAUDE.md §38.8)

> Treat each AI answer or action like a financial transaction.
> It must be: identifiable, reproducible, explainable, versioned,
> auditable.
