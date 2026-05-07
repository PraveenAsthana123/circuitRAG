# High-Level Design

> Per ADR-029 doc framework. Generated from a business use-case;
> revised through reviewer feedback until KPI ≥ 100%.
> Owner role: **architect**. Reviewer roles: **engineering_manager, tech_lead**.

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

### 3.1 System Context (C4 Level 1)
### 3.2 Containers (C4 Level 2)
### 3.3 Data Flow + Integration Points
### 3.4 Non-Functional Targets (latency / throughput / availability)
### 3.5 Cost + Cost-Per-Request Estimate

## 4. KPI Scoring

> Per-dimension scores (0-10). Approval gate: average ≥ 100%.

| Dimension | Score (0-10) | Rationale |
|---|---|---|
| completeness |  | _<reviewer fills>_ |
| scalability |  | _<reviewer fills>_ |
| security |  | _<reviewer fills>_ |
| cost |  | _<reviewer fills>_ |
| fault_tolerance |  | _<reviewer fills>_ |

## 5. Reviewer Sign-Offs

| Reviewer Role | Status | Date | Notes |
|---|---|---|---|
| architect (owner) |  |  |  |
| engineering_manager | pending |  |  |
| tech_lead | pending |  |  |

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
- Moved To: `approved/hld/<doc_id>/final.md`
