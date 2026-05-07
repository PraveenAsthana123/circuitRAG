# Infrastructure Document

> Per ADR-029 doc framework. Generated from a business use-case;
> revised through reviewer feedback until KPI ≥ 100%.
> Owner role: **devops_lead**. Reviewer roles: **sre, security_lead**.

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

### 3.1 Infrastructure Topology (network / compute / storage)
### 3.2 Capacity Profile (peak / average / growth)
### 3.3 High Availability Design
### 3.4 Disaster Recovery (RTO / RPO)
### 3.5 Cost Estimate (per environment)

## 4. KPI Scoring

> Per-dimension scores (0-10). Approval gate: average ≥ 100%.

| Dimension | Score (0-10) | Rationale |
|---|---|---|
| capacity_planning |  | _<reviewer fills>_ |
| high_availability |  | _<reviewer fills>_ |
| disaster_recovery |  | _<reviewer fills>_ |
| network_topology |  | _<reviewer fills>_ |
| cost_estimate |  | _<reviewer fills>_ |

## 5. Reviewer Sign-Offs

| Reviewer Role | Status | Date | Notes |
|---|---|---|---|
| devops_lead (owner) |  |  |  |
| sre | pending |  |  |
| security_lead | pending |  |  |

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
- Moved To: `approved/infra/<doc_id>/final.md`
