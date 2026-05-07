# Quality Plan

> Per ADR-029 doc framework. Generated from a business use-case;
> revised through reviewer feedback until KPI ≥ 100%.
> Owner role: **qa_lead**. Reviewer roles: **senior_engineer, product_manager**.

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

### 3.1 Quality Metrics (definition + targets)
### 3.2 Test Strategy + Coverage
### 3.3 Acceptance Gates Per Stage
### 3.4 Tooling Choice + Rationale
### 3.5 Feedback Loop (production → quality)

## 4. KPI Scoring

> Per-dimension scores (0-10). Approval gate: average ≥ 100%.

| Dimension | Score (0-10) | Rationale |
|---|---|---|
| quality_metrics |  | _<reviewer fills>_ |
| test_strategy |  | _<reviewer fills>_ |
| acceptance_gates |  | _<reviewer fills>_ |
| tooling_choice |  | _<reviewer fills>_ |
| feedback_loop |  | _<reviewer fills>_ |

## 5. Reviewer Sign-Offs

| Reviewer Role | Status | Date | Notes |
|---|---|---|---|
| qa_lead (owner) |  |  |  |
| senior_engineer | pending |  |  |
| product_manager | pending |  |  |

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
- Moved To: `approved/qp/<doc_id>/final.md`
