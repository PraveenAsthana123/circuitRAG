#!/usr/bin/env python3
"""Build skeleton + prompt template files referenced by registry.yaml.

Per ADR-029 + iter-69 registry. Iter-70 ships the 40 template files
(20 skeletons + 20 prompts) needed by the LangGraph generator (iter-74).

This script is the ONE-time builder; it reads the registry, renders
each skeleton + prompt from a parameterised template, and writes
them into the paths the registry references. Re-running is idempotent:
if a file already exists with non-default content, it's preserved
(operator may have hand-customized).

Usage:
  python3 scripts/build_doc_framework_templates.py            # write
  python3 scripts/build_doc_framework_templates.py --dry-run  # preview
  python3 scripts/build_doc_framework_templates.py --force    # overwrite

Per CLAUDE.md §44 + ADR-029 §Iter-by-iter rollout.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from doc_framework_registry import (  # noqa: E402
    DocEntry, Registry, load_registry,
)

# Skeleton template — Markdown structure each doc starts from.
# The LLM generator (iter-74) fills in the section bodies; the
# skeleton provides the contract shape so reviewers find sections
# in predictable places. Each skeleton has the same outer shape +
# doc-specific sections injected via {sections} placeholder.
SKELETON_TEMPLATE = """\
# {display_name}

> Per ADR-029 doc framework. Generated from a business use-case;
> revised through reviewer feedback until KPI ≥ {min_kpi:.0%}.
> Owner role: **{owner_role}**. Reviewer roles: **{reviewer_roles}**.

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

{sections}

## 4. KPI Scoring

> Per-dimension scores (0-10). Approval gate: average ≥ {min_kpi:.0%}.

| Dimension | Score (0-10) | Rationale |
|---|---|---|
{kpi_table}

## 5. Reviewer Sign-Offs

| Reviewer Role | Status | Date | Notes |
|---|---|---|---|
{reviewer_table}

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
- Moved To: `approved/{doc_type}/<doc_id>/final.md`
"""

# Per-doc-type section content. The skeleton template uses {sections}
# which is rendered from this map. Each doc gets canonical sections
# that match its KPI dimensions + standard SDLC headings.
DOC_SECTIONS: dict[str, str] = {
    "srs": """\
### 3.1 Functional Requirements
### 3.2 Non-Functional Requirements
### 3.3 Acceptance Criteria
### 3.4 Out of Scope
### 3.5 Traceability Matrix (requirement → test case)""",
    "brd": """\
### 3.1 Business Objectives + Value
### 3.2 Stakeholders + Sponsors
### 3.3 In-Scope vs Out-of-Scope
### 3.4 Success Criteria + Metrics
### 3.5 Constraints + Assumptions""",
    "hld": """\
### 3.1 System Context (C4 Level 1)
### 3.2 Containers (C4 Level 2)
### 3.3 Data Flow + Integration Points
### 3.4 Non-Functional Targets (latency / throughput / availability)
### 3.5 Cost + Cost-Per-Request Estimate""",
    "lld": """\
### 3.1 Component Decomposition (C4 Level 3)
### 3.2 Class / Module Diagrams
### 3.3 API Contracts (request/response shapes)
### 3.4 Data Model (DDL + ERD)
### 3.5 Error Handling + Edge Cases""",
    "sad": """\
### 3.1 Architecture Overview (all C4 levels)
### 3.2 Cross-Cutting Concerns (security/observability/governance)
### 3.3 ADR Index + Linkage
### 3.4 Tech Choice Justification
### 3.5 Migration Strategy (current → target)""",
    "tcd": """\
### 3.1 Test Strategy
### 3.2 Test Cases (one per requirement; happy + edge + negative)
### 3.3 Test Data + Fixtures
### 3.4 Pass/Fail Criteria
### 3.5 Traceability (test → requirement)""",
    "infra": """\
### 3.1 Infrastructure Topology (network / compute / storage)
### 3.2 Capacity Profile (peak / average / growth)
### 3.3 High Availability Design
### 3.4 Disaster Recovery (RTO / RPO)
### 3.5 Cost Estimate (per environment)""",
    "devops": """\
### 3.1 CI/CD Pipeline (build → test → deploy → verify)
### 3.2 Rollback Strategy
### 3.3 Monitoring + Alerting Hooks
### 3.4 Secrets Management
### 3.5 Operational Runbooks""",
    "sec": """\
### 3.1 Threat Model (STRIDE per component)
### 3.2 Security Controls (preventive / detective / corrective)
### 3.3 Compliance Mapping (SOC2 / ISO 27001 / GDPR / etc.)
### 3.4 Incident Response Plan
### 3.5 Audit Trail Design""",
    "pp": """\
### 3.1 Milestones + Critical Path
### 3.2 Dependencies (internal + external)
### 3.3 Communication Plan
### 3.4 Success Metrics
### 3.5 Status Reporting Cadence""",
    "dp": """\
### 3.1 Release Strategy (blue-green / canary / progressive)
### 3.2 Pre-Deploy Validation Steps
### 3.3 Rollback Plan + Trigger Conditions
### 3.4 Communication Plan (stakeholder notifications)
### 3.5 Downtime Budget + SLA Impact""",
    "cap": """\
### 3.1 Load Projection (1y / 3y / 5y)
### 3.2 Growth Assumptions + Drivers
### 3.3 Bottleneck Analysis
### 3.4 Scaling Strategy (vertical / horizontal / sharding)
### 3.5 Cost-At-Capacity Curve""",
    "est": """\
### 3.1 Work Breakdown Structure
### 3.2 Effort Basis (story points / hours / FTE)
### 3.3 Risk Buffer + Methodology
### 3.4 Dependency Estimate
### 3.5 Total Estimate Summary""",
    "rp": """\
### 3.1 Skill Inventory + Match-To-Tasks
### 3.2 Availability Schedule
### 3.3 Ramp-Up Time Per Role
### 3.4 Backup Assignments
### 3.5 Utilization Targets""",
    "cp": """\
### 3.1 Line-Item Cost Breakdown
### 3.2 TCO Analysis (3y / 5y)
### 3.3 Contingency Buffer
### 3.4 Cost Attribution (which team / cost center)
### 3.5 Benchmark Comparison""",
    "risk": """\
### 3.1 Risk Identification (per category: tech / ops / security / compliance / financial)
### 3.2 Probability x Impact Matrix
### 3.3 Mitigation Plan (per risk)
### 3.4 Monitoring Triggers + Response Owner
### 3.5 Risk Acceptance Criteria""",
    "tap": """\
### 3.1 Task Catalog (with acceptance criteria)
### 3.2 Assignee Match (skill + availability)
### 3.3 Dependency Graph
### 3.4 Effort Estimate Per Task
### 3.5 Sprint Allocation""",
    "team": """\
### 3.1 Role Definitions + Headcount
### 3.2 Skill Coverage Map
### 3.3 Reporting Lines + RACI
### 3.4 Communication Pattern (sync / async / cadence)
### 3.5 Onboarding Plan""",
    "qp": """\
### 3.1 Quality Metrics (definition + targets)
### 3.2 Test Strategy + Coverage
### 3.3 Acceptance Gates Per Stage
### 3.4 Tooling Choice + Rationale
### 3.5 Feedback Loop (production → quality)""",
    "vp": """\
### 3.1 Vendor Inventory + Evaluation Criteria
### 3.2 SLA Terms + Penalties
### 3.3 Cost Breakdown Per Vendor
### 3.4 Risk Assessment Per Vendor
### 3.5 Exit Strategy + Vendor-Lock-In Mitigation""",
}

# Prompt template that the LangGraph generator (iter-74) will use to
# fill the skeleton from a business use-case. Each doc gets the same
# outer prompt; the doc-specific sections come from the skeleton.
PROMPT_TEMPLATE = """\
# Generation Prompt — {display_name}

> System role: enterprise governance document author.
> Doc type: `{doc_type}` ({display_name}).
> Owner role: `{owner_role}`.
> Reviewer roles: {reviewer_roles_md}.
> Approval threshold: KPI ≥ {min_kpi:.0%} across {kpi_count} dimensions.

## Inputs (filled by the generator at runtime)

- `business_usecase`: <user-supplied business use-case text>
- `tenant_id`: <UUID>
- `project_id`: <UUID>
- `revision_round`: <integer; 1 for first draft, N for nth revision>
- `prior_feedback`: <list of feedback entries from prior round; empty on round 1>

## Output contract

Produce a Markdown document that fills the skeleton at
`{template_path}`. Every section MUST be populated with substantive
content derived from the business use-case + prior feedback. A section
saying "TBD" or "to be determined" fails KPI dimension `{first_kpi}`.

## KPI dimensions (the reviewer rubric)

{kpi_block}

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
"""


def _render_kpi_table(d: DocEntry) -> str:
    return "\n".join(
        f"| {k} |  | _<reviewer fills>_ |" for k in d.kpi_dimensions
    )


def _render_reviewer_table(d: DocEntry) -> str:
    rows = [f"| {d.owner_role} (owner) |  |  |  |"]
    rows.extend(f"| {r} | pending |  |  |" for r in d.reviewer_roles)
    return "\n".join(rows)


def _render_kpi_block(d: DocEntry) -> str:
    return "\n".join(
        f"- **{k}** — score 0-10; weight 1.0 (uniform across dims)"
        for k in d.kpi_dimensions
    )


def _render_skeleton(d: DocEntry) -> str:
    sections = DOC_SECTIONS.get(d.doc_type)
    if sections is None:
        sections = (
            f"### 3.1 (TODO: define sections for {d.doc_type})\n"
            f"### 3.2 (TODO)\n### 3.3 (TODO)"
        )
    return SKELETON_TEMPLATE.format(
        display_name=d.display_name,
        owner_role=d.owner_role,
        reviewer_roles=", ".join(d.reviewer_roles),
        min_kpi=d.min_kpi,
        sections=sections,
        kpi_table=_render_kpi_table(d),
        reviewer_table=_render_reviewer_table(d),
        doc_type=d.doc_type,
    )


def _render_prompt(d: DocEntry) -> str:
    return PROMPT_TEMPLATE.format(
        display_name=d.display_name,
        doc_type=d.doc_type,
        owner_role=d.owner_role,
        reviewer_roles_md=", ".join(f"`{r}`" for r in d.reviewer_roles),
        min_kpi=d.min_kpi,
        kpi_count=len(d.kpi_dimensions),
        first_kpi=d.kpi_dimensions[0],
        kpi_block=_render_kpi_block(d),
        template_path=d.template_path,
    )


def _write_if_safe(path: Path, content: str, *, dry_run: bool, force: bool) -> str:
    """Write only when missing OR --force. Returns one of:
    'created' / 'skipped_exists' / 'overwritten' / 'dry_create' /
    'dry_overwrite'."""
    if dry_run:
        return "dry_create" if not path.exists() else "dry_overwrite"
    if path.exists() and not force:
        return "skipped_exists"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "created" if not path.exists() else "overwritten"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change; don't write")
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing template/prompt files")
    args = parser.parse_args()

    reg = load_registry()
    print(f"Building templates for {len(reg.docs)} docs...")
    print(f"  dry_run={args.dry_run} force={args.force}")
    print()

    counts: dict[str, int] = {"created": 0, "overwritten": 0,
                              "skipped_exists": 0, "dry_create": 0,
                              "dry_overwrite": 0}
    for d in reg.docs:
        skel_path = REPO / d.template_path
        prompt_path = REPO / d.prompt_path
        skel_status = _write_if_safe(
            skel_path, _render_skeleton(d), dry_run=args.dry_run, force=args.force
        )
        prompt_status = _write_if_safe(
            prompt_path, _render_prompt(d), dry_run=args.dry_run, force=args.force
        )
        counts[skel_status] = counts.get(skel_status, 0) + 1
        counts[prompt_status] = counts.get(prompt_status, 0) + 1
        print(f"  {d.doc_type:6s}  skel={skel_status}  prompt={prompt_status}")

    print()
    print("Summary:")
    for k, v in sorted(counts.items()):
        if v:
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
