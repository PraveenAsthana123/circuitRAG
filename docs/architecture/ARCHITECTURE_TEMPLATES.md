# Architecture Templates

> §19 mandate. The substantive C4 templates already exist in this
> directory and at the deep-dive frontend pages. This file indexes them.

## C4 model — 7 levels (CLAUDE.md §47.2 extended)

| Level | File | Purpose |
|---|---|---|
| L1 Context | [`C4-context.md`](C4-context.md) | System ↔ external actors |
| L2 Container | [`C4-container.md`](C4-container.md) | Top-level deployable units |
| L3 Component | [`C4-component.md`](C4-component.md) | Inside-container components |
| L4 Code | (per service `app/` or `cmd/` directory) | Implementation |
| L5 Governance | [`AI_GOVERNANCE_GUIDE.md`](AI_GOVERNANCE_GUIDE.md) | Roles, decision rights, ADR registry |
| L6 Observability | [`otel-repo-wide-coverage-matrix.md`](otel-repo-wide-coverage-matrix.md) | Logs, traces, metrics, decision audit |
| L7 Lifecycle | (deploy + rollback runbooks under `runbooks/`) | Build → release → rollback → retire |

## ADR template

See existing ADRs at [`adr/`](adr/) for the project-local style.
Required fields per CLAUDE.md §47.3:

- Status (proposed / accepted / superseded)
- Context (what problem this solves)
- Decision (the choice in 1-3 sentences)
- Consequences (positive + negative + risks accepted)
- Alternatives considered
- References

ADRs are immutable once accepted; supersede via a new ADR with a
new sequential number.

## HLD / LLD / SAD

CircuitRAG specifically:

| Doc | Purpose |
|---|---|
| [`HLD-documind.md`](HLD-documind.md) | High-level design |
| [`LLD-documind-by-tool-and-component.md`](LLD-documind-by-tool-and-component.md) | Low-level design per tool |
| [`security-compliance-ai-governance-and-growth-os-blueprint.md`](security-compliance-ai-governance-and-growth-os-blueprint.md) | System architecture document (security + AI governance) |
| [`chatbot-design-brd-hld-lld.md`](chatbot-design-brd-hld-lld.md) | Worked BRD → HLD → LLD example |

## Sequence diagrams + flowcharts

Live inline in the architecture docs as Mermaid blocks. Examples:

- [`agentic-a2a-langgraph-fastapi-mcp.md`](agentic-a2a-langgraph-fastapi-mcp.md) — A2A flow
- [`tool-architecture-and-process-flows.md`](tool-architecture-and-process-flows.md) — per-tool process
- [`MODULE-FLOWS.md`](MODULE-FLOWS.md) — input/process/output per module
- [`repo-ingestion-and-preprocessing-architecture.md`](repo-ingestion-and-preprocessing-architecture.md) — ingestion pipeline

## Deep-dive admin pages (frontend)

Every architectural surface has a `services/frontend/app/admin/<topic>/deep/page.tsx`
deep-dive. All 45 pages carry a `<DeepDiveCrossRefs>` footer per
§49 — the dependency graph is visible from the UI.

Rendered list: see [`docs/DEMO-E2E-ADMIN-SMOKE.md`](../DEMO-E2E-ADMIN-SMOKE.md)
or run `ls services/frontend/app/admin/*/deep/page.tsx`.
