# Generation Prompt — Test Case Document

> System role: enterprise governance document author.
> Doc type: `tcd` (Test Case Document).
> Owner role: `qa_lead`.
> Reviewer roles: `senior_engineer`, `product_manager`.
> Approval threshold: KPI ≥ 100% across 5 dimensions.

## Inputs (filled by the generator at runtime)

- `business_usecase`: <user-supplied business use-case text>
- `tenant_id`: <UUID>
- `project_id`: <UUID>
- `revision_round`: <integer; 1 for first draft, N for nth revision>
- `prior_feedback`: <list of feedback entries from prior round; empty on round 1>

## Output contract

Produce a Markdown document that fills the skeleton at
`docs/templates/doc_framework/tcd/skeleton.md`. Every section MUST be populated with substantive
content derived from the business use-case + prior feedback. A section
saying "TBD" or "to be determined" fails KPI dimension `requirement_coverage`.

## KPI dimensions (the reviewer rubric)

- **requirement_coverage** — score 0-10; weight 1.0 (uniform across dims)
- **edge_case_coverage** — score 0-10; weight 1.0 (uniform across dims)
- **test_data_completeness** — score 0-10; weight 1.0 (uniform across dims)
- **traceability** — score 0-10; weight 1.0 (uniform across dims)
- **acceptance_criteria** — score 0-10; weight 1.0 (uniform across dims)

For each dimension, the reviewer scores 0-10. Your draft should
score ≥9 on first pass on every dimension; revisions tighten the
remaining points.

## Hard constraints (per §38 governance)

- DO NOT invent stakeholders, dates, regulators, or vendor names.
  When unknown → use `<TBD: needs operator input>` with a specific
  question the operator must answer.
- DO NOT invent regulatory citations. Use only what's in the
  business use-case OR ask in `<TBD>`.
- DO cite ADRs when they apply (use existing ADR-001..ADR-029).
- DO produce one section per skeleton heading; never collapse two
  headings into one body.
- DO keep the doc under 8000 words. Reviewer fatigue hurts KPI.

## Revision behavior

When `revision_round > 1`:
1. Read `prior_feedback`. Each entry has `dimension` + `comment`.
2. For every feedback comment, edit the relevant section to address it.
3. APPEND to "## 7. Revision History" with this revision's row.
4. DO NOT silently revert prior content; only modify what feedback targets.
