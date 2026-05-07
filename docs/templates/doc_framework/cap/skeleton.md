# Capacity Plan

> Per ADR-029 doc framework. Generated from a business use-case;
> revised through reviewer feedback until KPI ≥ 100%.
> Owner role: **sre**. Reviewer roles: **devops_lead, architect**.

## 1. Metadata

- Doc ID: `<filled at generation>`
- Project ID: `<filled at generation>`
- Tenant ID: `<filled at generation>`
- Version: `<filled at generation>`
- Status: `NEW | GENERATING | DRAFTED | IN_REVIEW | FEEDBACK | REVISING | APPROVED | ARCHIVED`
- Created: `<ISO timestamp>`
- Last Revised: `<ISO timestamp>`

## 2. Business Use-Case (Input)

> Captured verbatim from the user's submission. This section is the
> single source of truth for what the doc is solving for. Reviewers
> compare ALL other sections against this.

`<business use-case text>`

## 3. Doc-Specific Sections

### 3.1 Load Projection (1y / 3y / 5y)
### 3.2 Growth Assumptions + Drivers
### 3.3 Bottleneck Analysis
### 3.4 Scaling Strategy (vertical / horizontal / sharding)
### 3.5 Cost-At-Capacity Curve

## 4. KPI Scoring

> Per-dimension scores (0-10). Approval gate: average ≥ 100%.

| Dimension | Score (0-10) | Rationale |
|---|---|---|
| load_projection |  | _<reviewer fills>_ |
| growth_assumptions |  | _<reviewer fills>_ |
| bottleneck_analysis |  | _<reviewer fills>_ |
| scaling_strategy |  | _<reviewer fills>_ |
| cost_at_capacity |  | _<reviewer fills>_ |

## 5. Reviewer Sign-Offs

| Reviewer Role | Status | Date | Notes |
|---|---|---|---|
| sre (owner) |  |  |  |
| devops_lead | pending |  |  |
| architect | pending |  |  |

## 6. Inter-Department Feedback

> Cross-role feedback that affects this doc. Tracked in a separate
> tab in the UI; visible here as an immutable append-only list.

_(none yet — populated as reviewers from non-owner roles file feedback)_

## 7. Revision History

> Each revision appends one row. Never delete; per §38 audit immutability.

| Version | Author | Reason | KPI Before | KPI After |
|---|---|---|---|---|

## 8. Approval

- Final KPI: `<filled when KPI ≥ min_kpi>`
- Approved By: `<all reviewer roles after sign-off>`
- Approval Date: `<ISO timestamp>`
- Moved To: `approved/cap/<doc_id>/final.md`
