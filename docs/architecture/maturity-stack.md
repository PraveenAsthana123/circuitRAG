# Enterprise AI Maturity Stack — Current State

> Per `~/.claude/policies/enterprise-ai-maturity-stack.md`. Scores
> each of the 14 items (35-48) at the project's current maturity level.
> Quarterly review; track L1→L6 movement.

**Project**: `/mnt/deepa/rag` (DocuMind RAG Platform)
**Date**: 2026-05-01
**Reviewer**: Audit (post-CB rebuild + per-tool reviews)

---

## Score card

| # | Item | Current Level | Target Level | Status | P0/P1 gap |
|---|---|---|---|---|---|
| 35 | DR Metrics | **L3** | L4 | 🟡 | Targets defined per tier + dashboard endpoint `/api/v1/admin/dr-targets` exposes target-vs-current with explicit `not_measured` placeholder (locked by `drill_dr_metrics_dashboard_endpoint.py` step 7); missing: quarterly DR drill that populates current values |
| 36 | Capacity Planning | **L2** | L4 | 🟡 | Load model partial (smoke only); no quarterly capacity exercise |
| 37 | Dependency Contracts | **L2** | L4 | 🟡 | Brutal review per-tool exists; no Pact testing in CI; no contract registry |
| 38 | Schema Evolution | **L3** | L5 | 🟢 | 8 migrations all additive (per §28); RLS audit (015) drilled; missing: schema registry + drift detection |
| 39 | Observability Taxonomy | **L3** | L5 | 🟡 | Standard log schema partial; OTel collector running; missing: enforced naming convention + sampling strategy |
| 40 | Business KPI Tracking | **L1** | L4 | 🔴 | Cost columns + audit row exist (A5/C4); no business KPIs, no ROI, no per-segment dashboards |
| 41 | Change Management | **L1** | L3 | 🔴 | Frontend `/admin/agentic` exists; no training, no adoption tracking |
| 42 | Documentation | **L3** | L5 | 🟢 | 14 per-tool reviews + C4 L1+L2 + 50+ commits with §51 metadata; missing: BRD/HLD/LLD per service, ADR catalog, runbooks |
| 43 | Integration & Operating Model | **L2** | L5 | 🟡 | People/Platform exist; Process partial (no formal LLMOps); Governance: RAI/security/compliance docs incomplete |
| 44 | Production Validation | **L2** | L5 | 🟡 | Drills lock contracts (per §43); no shadow testing, no drift detection, no auto-rollback (B6 observer is the closest, still scaffold) |
| 45 | Continuous Improvement | **L1** | L4 | 🔴 | No feedback loop, no eval harness, no experimentation engine; commits drift toward "build" not "learn" |
| 46 | Platformization | **L2** | L5 | 🟡 | Agent framework + LLM client pool + model router exist; no prompt registry, no model gateway, no tool marketplace, no eval platform |
| 47 | Strategic Alignment | **L1** | L4 | 🔴 | No portfolio mgmt, no value attribution per agent, no maturity tracking before this doc |
| 48 | AI Governance OS | **L1** | L5 | 🔴 | Policy/decision/risk/compliance/audit engines do NOT exist as a unified surface; pieces scattered (model_router has policy; explainability has audit; no Compliance Engine) |

**Overall**: weighted average **L2.14** (was L1.85 at first assessment; #35 moved L1→L2→L3 across two iters); target **L4.5**. Concrete gap: ~137 hr engineering + 6 mo of org change to reach L4.

---

## L1-L6 maturity per item — current state legend

🔴 **L1 (experiments)** — exists in some form for one team / use case, no unified surface
🟡 **L2-L3 (projects → platform)** — components shipped; not yet integrated platform-grade
🟢 **L4-L5 (integrated → strategic)** — platform-grade with governance; quarterly review process

---

## Critical P0 enterprise gaps (block regulator-shippable)

| # | Item | Gap | Effort |
|---|---|---|---|
| 48 | **AI Governance OS** | Compliance Engine missing; no GDPR / ISO 42001 / NIST AI RMF mapping concrete in code | ~30 hr |
| 44 | **Production Validation** | No drift detection on live decisions | ~20 hr |
| 35 | **DR Metrics** | Targets + dashboard endpoint shipped; quarterly DR drill remaining (the actual recovery exercise) | ~7 hr remaining |
| 47 | **Strategic Alignment** | No business KPI → AI use case mapping | ~15 hr |
| 40 | **Business KPI Tracking** | Audit row exists; no aggregation / dashboard / per-segment view | ~25 hr |

---

## How to update this assessment

```bash
# Quarterly: re-score each item by re-reading the policy
# and walking through the project's actual artifacts.
#
# Mark items that improved (L2 → L3, etc.) with the date
# and pointing commit hash for the artifact that closed the gap.
```

## See also

- `~/.claude/policies/enterprise-ai-maturity-stack.md` — the policy (items 35-48)
- `~/.claude/policies/brutal-tool-review.md` — per-tool 40-row review
- `docs/architecture/tool-reviews/` — 14 per-tool reviews (the per-tool layer)
- `docs/architecture/c4/` — L1, L2 architecture diagrams
- CLAUDE.md §52 + §53 — policy references
