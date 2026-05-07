# ADR-029: Business-usecase → 20-doc generation + role-based review framework

## Status

Proposed — 2026-05-07. Iter-69 ships the FOUNDATION (this ADR + doc
registry + workflow contract). Iter-70..78 ship the implementation.

## Context

The user requested a complete framework where:

1. User provides ONE business use-case as input
2. Application auto-generates 20 governance documents:
   - SRS, BRD, HLD, LLD, System Architecture
   - Test Cases, Infra Docs, DevOps Docs, Security Docs
   - Project Plan, Deployment Plan, Capacity Plan
   - Estimation Plan, Resource Plan, Cost Plan
   - Risk Plan, Task Assigning Plan, Team Plan
   - Quality Plan, Vendor Plan
3. Each role has its own UI navigation node + 2 folders
   (new vs approved)
4. Each role/department can review docs + give feedback
5. Feedback drives doc revision until KPI threshold (100%) is met
6. Inter-department feedback gets its own tab
7. Approved docs (100% KPI) move to `approved/` folder

This is a substantial multi-iter feature touching:
- LangGraph DAG workflow for multi-doc generation
- Postgres schema for workflow state (new → reviewing → feedback →
  revising → approved)
- Per-role + per-department feedback collection
- KPI scoring engine
- Frontend UI (role nodes, review panels, feedback tabs)
- Doc-template registry (one prompt per doc type per role)

Per CLAUDE.md §13 (no over-engineering), §44 (autonomous-loop ONE
thing per iter), §45.4 (no checkbox flips without code), §47
(architecture: 7 design surfaces; this feature spans HLD + LLD + JAD +
governance + load testing), §47.5 (JAD chain — JAD session → BRD →
C4 → ADRs → backlog → sprints): the right move is to scope the
contract here, then ship one component per iter.

## Decision

Build a **Multi-Doc Generation + Review Framework** as a new feature
layer on top of the existing platform. Composition of existing
primitives (LangGraph + council + MCP + governance.audit_log + UI)
produces this feature; no new infrastructure required.

### High-level architecture

```
User business-usecase input
        ↓
  Doc-Template Registry (20 entries; iter-70)
        ↓
  Generation Workflow (LangGraph DAG; iter-74)
        ↓
  governance.docs (Postgres; iter-71)
        ↓
  Per-Role Review Surface (HTTP API; iter-72)
        ↓
  Frontend UI (role nodes + folders + tabs; iter-73)
        ↓
  KPI Scoring Engine (iter-71)
        ↓
  Iterate revise → review until 100% KPI
        ↓
  Approved → move to approved/ folder
```

### 20 Documents — registry-driven

Each doc has:
- `doc_type` (slug; e.g. `srs`, `brd`, `hld`)
- `display_name`
- `owner_role` (primary role responsible)
- `reviewer_roles[]` (which roles must approve)
- `kpi_dimensions[]` (e.g. completeness / consistency / risk /
  feasibility — per-doc-type weights)
- `template_path` (Markdown skeleton)
- `prompt_path` (LLM prompt template that fills the skeleton)
- `min_kpi` (default 100)
- `interdept_required` (bool; some docs need cross-team approval)

Initial registry per user request:

| # | Doc Type | Slug | Owner Role | Reviewer Roles |
|---|---|---|---|---|
| 1 | SRS | `srs` | Business Analyst | Product, Architect, QA |
| 2 | BRD | `brd` | Business Analyst | Product, Stakeholder |
| 3 | HLD | `hld` | Architect | Engineering Manager, Tech Lead |
| 4 | LLD | `lld` | Tech Lead | Architect, Engineer |
| 5 | System Architecture | `sad` | Architect | Engineering, Security |
| 6 | Test Cases | `tcd` | QA Lead | Engineering, Product |
| 7 | Infra Docs | `infra` | DevOps | SRE, Security |
| 8 | DevOps Docs | `devops` | DevOps | SRE, Engineering |
| 9 | Security Docs | `sec` | Security Lead | Architect, Compliance |
| 10 | Project Plan | `pp` | Project Manager | Sponsor, Tech Lead |
| 11 | Deployment Plan | `dp` | DevOps | SRE, PM |
| 12 | Capacity Plan | `cap` | SRE | DevOps, Architect |
| 13 | Estimation Plan | `est` | PM | Tech Lead, Engineering |
| 14 | Resource Plan | `rp` | PM | HR, Engineering |
| 15 | Cost Plan | `cp` | PM | Finance, Sponsor |
| 16 | Risk Plan | `risk` | PM | Security, Compliance |
| 17 | Task Assigning Plan | `tap` | Tech Lead | Engineering |
| 18 | Team Plan | `team` | Engineering Manager | HR, PM |
| 19 | Quality Plan | `qp` | QA Lead | Engineering, Product |
| 20 | Vendor Plan | `vp` | PM | Procurement, Finance |

### Workflow state machine

```
NEW
  ↓ (user submits business case)
GENERATING
  ↓ (LLM drafts via doc-template registry)
DRAFTED
  ↓ (visible in role's `new/` folder)
IN_REVIEW
  ↓ (reviewer role opens it)
FEEDBACK
  ↓ (reviewer files feedback OR approves)
REVISING (if feedback)        APPROVED (if all reviewers OK + KPI ≥ threshold)
  ↓ (LLM applies feedback)         ↓
DRAFTED (loop back)              moves to `approved/` folder
                                 ↓
                                 ARCHIVED
```

State transitions stored in `governance.docs` (one row per doc) +
`governance.doc_feedback` (one row per feedback entry; immutable
append-only per §38).

### KPI scoring (per-doc, per-dimension)

Each doc type defines its KPI dimensions. Examples:

- **SRS KPI dimensions**: completeness (10) / clarity (10) /
  testability (10) / traceability (10) / non-functional-coverage (10)
- **HLD KPI dimensions**: completeness (10) / scalability (10) /
  security (10) / cost (10) / fault-tolerance (10)
- **Risk Plan KPI dimensions**: identification (10) / probability (10) /
  impact (10) / mitigation (10) / monitoring (10)

Each dimension scored 0-10 by:
1. Auto-grader (LLM-based; stage-1 stub returns "needs human review")
2. Reviewer-role manual scoring (per-dimension feedback)

KPI score = `sum(dimensions) / (10 * len(dimensions))` → 0..1 → percent.

`min_kpi` defaults to 1.0 (100%) — the user-stated threshold. Operator
can lower per doc-type via registry update + drill update (ratchet).

### Folder structure

```
.docs/
  <tenant_id>/
    <project_id>/
      <role>/                       e.g. business_analyst/
        new/                        in-progress + reviewing + revising
          <doc_type>/<doc_id>/
            v1.md
            v2.md (after revision)
            ...
        approved/                   100% KPI achieved
          <doc_type>/<doc_id>/
            final.md
            kpi_record.json
            audit_trail.jsonl       per-role-feedback timeline
```

Per-role separation: each role sees only THEIR folder. Folder OS
permissions enforce isolation. Folder location is per-tenant + per-project
to handle multi-tenant + multi-project simultaneously.

### Inter-department feedback (separate tab)

A reviewer in role A can leave feedback that affects role B's
document. Stored as `feedback_type='cross_department'` + `target_role`.
Frontend renders these in a separate tab per role's review surface
so they don't conflate with the role's own feedback.

## Consequences

### Positive

- **Composition over invention**: every primitive (LangGraph +
  council + governance.audit_log + UI sidebar nodes) already exists.
  Iter-70..78 wire them together; no new infrastructure.
- **Registry-driven**: adding a 21st doc type = one row in
  `docs/templates/registry.yaml`, not a code change. Drill catches
  registry drift.
- **Per-role isolation**: folder structure + RBAC scope mean a
  Security reviewer sees their queue without seeing PM's drafts.
  Inter-department changes are explicit (separate tab) — no
  accidental cross-role visibility.
- **KPI threshold gates approval**: a doc cannot be marked Approved
  until its KPI score reaches `min_kpi`. Default 100 per user request;
  ratchetable per doc-type.
- **§38 audit immutable**: every feedback entry + every revision
  appended to `governance.doc_feedback` (never updated). Audit trail
  is the source of truth for "who approved what when".
- **§47 architectural surfaces preserved**: this feature USES the
  existing 7 design surfaces (HLD/LLD/SAD/ADR/JAD/Security/Rollout)
  rather than reinventing them.

### Negative

- **8+ iters of work**: this ADR + iter-70 (registry) + iter-71
  (state machine + Postgres schema) + iter-72 (review API) +
  iter-73 (UI) + iter-74 (LangGraph generator) + iter-75 (interdept
  tab) + iter-76+ (one prompt template per doc type, 20 iters at
  worst — though most can be batched as registry entries).
- **LLM cost**: 20 docs × N revisions × M reviewer rounds = significant
  LLM tokens per business-usecase. Mitigated: cache stable doc
  sections; revise only changed sections; keep prompts under 4k tokens
  per doc.
- **KPI auto-grader is initially weak**: Stage-1 stub returns "needs
  human review" for every dimension; iter-76+ wires real evaluators
  per-dimension. Until then, every doc requires human review (which
  matches the user's request).

### Re-evaluation triggers (file ADR-NNN superseding this)

ADR-029 is **automatically re-opened** when:

1. **Doc count exceeds 30**: at >30 doc types, the registry approach
   strains; consider a doc-type taxonomy + sub-doc relationships.
2. **Cross-tenant document sharing requested**: a tenant wants to
   share a Doc with another tenant's reviewer. Current model is
   strictly per-tenant; cross-tenant requires consent + governance
   ADR.
3. **Real-time co-editing requested**: current model is async
   review (file feedback → trigger revise). Real-time CRDT-style
   editing is a different architecture entirely.

## Iter-by-iter rollout

| Iter | Scope | Drill |
|---|---|---|
| 69 | ADR-029 + doc registry YAML + drill | drill_doc_framework_registry (THIS) |
| 70 | Per-doc skeleton templates + prompt templates (20 files) | drill_doc_template_files |
| 71 | Postgres schema (governance.docs + doc_feedback) + state machine | drill_doc_workflow_state_machine |
| 72 | HTTP API (POST /docs / GET /docs/:id / POST /docs/:id/feedback) | drill_doc_api_contract |
| 73 | Frontend role-nodes + 2-folder UI + review panel | drill_doc_ui_role_nodes |
| 74 | LangGraph generator + LLM revision loop | drill_doc_generator_workflow |
| 75 | Interdepartmental feedback tab + cross-role notifications | drill_doc_interdept_feedback |
| 76 | KPI scoring engine + per-dimension auto-grader stubs | drill_doc_kpi_scoring |
| 77 | Folder lifecycle (new/ → approved/ on 100% KPI) | drill_doc_folder_lifecycle |
| 78 | End-to-end smoke: business-usecase → 20 drafts → review → approved | drill_doc_e2e_smoke |

## Alternatives considered

### A1. Build it as a single iter
**Rejected**: ~1000 files of code spread across 8 architectural
surfaces is not §44 ONE-thing-per-iter. Single-iter delivery is
also unauditable — a future maintainer can't trace which decision
landed when.

### A2. Use a third-party doc-generation framework (Sphinx-AI,
DocLLM, etc.)
**Rejected**: third-party frameworks have their own governance models
that conflict with §38 audit + §47 architecture. Build on existing
LangGraph + council + audit_log primitives; doesn't depend on
upstream's release cadence.

### A3. Skip the per-role folder structure; one shared doc store
**Rejected**: user explicitly asked for per-role separation +
2 folders (new vs approved). RBAC at folder level is also clearer
than RBAC at row level.

### A4. Skip the KPI threshold; binary approve/reject
**Rejected**: user explicitly asked for "100% KPI" gating. Binary
approval is faster but loses the per-dimension visibility (this
doc is 80% complete but only 50% on testability — actionable
feedback).

## References

- `2dab9a0` — `fix(iter-68): mcp/server_github.py + AI SDLC roadmap doc — close most-critical SDLC gap`
- `docs/architecture/adr/027-agent-framework-langgraph-not-crewai-agno.md`
  (LangGraph is the orchestrator; this feature uses it)
- `docs/architecture/adr/028-csv-to-db-ingest-write-surface-contract.md`
  (write-surface ADR pattern; doc-feedback append is the same shape)
- `docs/architecture/ai-sdlc-mcp-roadmap.md` (iter-68; this feature
  produces SDLC documents at scale)
- iter-58/59 reflection engine + human-review router (the
  feedback-loop pattern; doc review is structurally similar)
- CLAUDE.md §13 (no over-engineering) §38 (governance immutable
  audit) §43 (drill discipline) §44 (autonomous-loop one-thing-per-iter)
  §45.4 (no checkbox flips without code) §47 (7 architectural
  surfaces) §47.5 (JAD chain)
