# Phase 8 — Governance, FinOps, Evaluation

**Status:** Stub. Services exist (Go skeletons); UI exists at /tools; pipelines NOT wired end-to-end.

## Governance

### Scope

- Policy-as-code (allow / deny / review) → `governance.policies` (CEL expressions)
- Human-in-the-loop queue → `governance.hitl_queue`
- Audit log with hash-chain tamper evidence → `governance.audit_log`
- Feature flags per tenant → `governance.feature_flags`
- Prompt registry — every active prompt versioned → `governance.prompts`
- Output guardrails — PII / toxicity / jailbreak leakage → `libs/py/documind_core/ai_governance.py`

### Exit criteria

- [ ] CEL runtime integrated (engine evaluates policies from DB at decision time).
- [ ] Reviewer UI in governance-svc for HITL queue.
- [ ] Hash-chain writer for audit log (append-only).
- [ ] Prompt versioning referenced from every AI decision row.
- [ ] Threat model doc (STRIDE per service) in `docs/security/threat-model.md`.

## FinOps

### Scope

- Per-query token tracking — `finops.token_usage` partitioned daily
- Per-tenant budget + Token CB integration
- $/tenant/day Grafana panel
- Model routing based on budget tier (premium → mid → small)
- Cache-hit $ saved panel
- Shadow pricing table (for planning)

### Exit criteria

- [ ] inference-svc emits `token_used` event per call with {tenant, model, prompt_tokens, completion_tokens, cost_usd}.
- [ ] finops-svc consumer writes to `finops.token_usage`.
- [ ] Grafana panel `cost-per-tenant` from `infra/grafana/dashboards/`.
- [ ] Token CB reads budget from `finops.budgets` and trips on exceed.
- [ ] Monthly rollup job `finops.billing_periods` — reconciled against token_usage.

## Evaluation

### Scope

- Offline — golden dataset, precision@k / nDCG / faithfulness / answer relevance
- Online — sampling % of production traffic; score via heuristic + LLM-judge
- Regression gate in CI — fail merge on metric drop > threshold
- Drift detection — PSI/CSI on embedding distribution vs reference
- Feedback capture — thumbs up/down + comment → `eval.feedback`
- Active learning — feedback triggers fine-tune or prompt update

### Exit criteria

- [ ] Golden dataset committed to `docs/eval/golden/*.jsonl` (50+ Q/A pairs).
- [ ] Ragas integration — `make eval` runs faithfulness + context precision/recall.
- [ ] Report artifact in `data/eval/<date>/report.json` + Grafana panel.
- [ ] CI fails merge on faithfulness drop > 3%, precision drop > 5%.
- [ ] Sampling consumer for online eval (Kafka `query.served` topic).
- [ ] Feedback capture endpoints wired.

## Cross-phase dependencies

| Depends on | Phase |
| --- | --- |
| Structured logging + correlation-id | Phase 7 |
| Kafka event backbone | Phase 5 |
| Circuit Breakers | Phase 3 |
| mTLS + AuthorizationPolicy | Phase 1 |
| Real services running | Day 1.5 (outstanding) |

## Phase-8 exit criteria (top-level)

The phase is complete when an auditor can run:

```bash
make audit
```

and get:
1. Last 30 days of governance decisions (allow / review / deny) per tenant.
2. Last 30 days of $/tenant usage vs budget.
3. Last 7 days of eval report vs baseline.
4. List of every prompt version in production + last change timestamp.
5. Every HITL queue entry + resolution status.

All five items must come from live data, not slides.
