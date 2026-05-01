# Explainability module (`/api/v1/agentic/tasks/{id}/explain`) — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/explainability.py` + endpoint in main.py
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | — |
| **P1** | 4 | rows #6 (placeholders are explicit None — not all auditors accept that), #18 (no schema-mismatch drill), #25 (sub-fields not Pydantic-validated), #39 (no SLA on /explain response time) |
| **P2** | 3 | rows #19, #22, #36 |

## Highlights

- ✅ 23-field §48.4 schema (post-CB-E added breaker_states)
- ✅ REQUIRED_AUDIT_FIELDS lock — endpoint returns 500 if any missing
- ✅ Pure function — assemble_explanation drillable in isolation
- ✅ Defensive sub-field reads (handle missing routing_decision)

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 6 | Silent fallback | ⚠ | **P1** — explanation.top_features = None; some EU AI Act readers reject None; would prefer "computation_pending" with explanation |
| 13 | Latency histogram | ✗ | No metric on /explain endpoint response time |
| 18 | Drill — schema mismatch | ⚠ | **P1** — drill_explainability_row covers schema completeness; doesn't cover "row has 24 keys" (extra) or future-extension cases |
| 23 | Cost of failures | n/a | Read-only endpoint |
| 25 | Audit row sub-validation | ✗ | **P1** — sub-objects (explanation, cost_tokens) aren't typed/validated; could leak stale shapes |
| 39 | SLA on /explain | ✗ | **P1** — no p95 SLO; if response > 5s under load, regulator can't extract within minutes |

## Brutal one-liner

> Strong shape contract, weak content depth. **No P0**. The fields that are explicitly
> None (SHAP, counterfactual, fairness) need a content plan or formal "deferred"
> annotation per §48.10 — auditors hate `None`. P1 is real but not
> production-blocking.
