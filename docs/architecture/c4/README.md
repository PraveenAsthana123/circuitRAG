# C4 Architecture Diagrams

Per CLAUDE.md §47, every system must document architecture across
C4 L1 (System Context) through L7 (Lifecycle).

## Levels

| Level | File | Status |
|---|---|---|
| L1 — System Context | [L1-system-context.md](L1-system-context.md) | ✅ |
| L2 — Container | [L2-container.md](L2-container.md) | ✅ |
| L3 — Component (per service) | TODO — generate per `services/*` | ⏸ |
| L4 — Code (per critical class) | TODO — generate per `app/<critical>.py` | ⏸ |
| L5 — Governance | partial — see `/admin/governance` UI page; TODO file | ⏸ |
| L6 — Observability | partial — see Grafana dashboards; TODO file | ⏸ |
| L7 — Lifecycle | TODO — build → release → rollback → retire | ⏸ |

## Conventions

- **Format**: Mermaid (rendered by GitHub + most IDEs)
- **Notation**: C4 standard (Person / System / Container / Component)
- **Source of truth**: these `.md` files; the `/admin/c4-model/deep`
  page in the frontend is the operator-facing renderer
- **Versioning**: every diagram update lands in a commit alongside
  the architectural change that motivated it (per CLAUDE.md §51
  forensic-substrate rule)

## How to update

1. Edit the relevant `Lx-*.md` file.
2. Verify Mermaid renders cleanly (paste into [mermaid.live](https://mermaid.live)).
3. Commit with `docs(c4):` prefix.
4. If the architectural change is significant (new container, new
   external system, removed integration), file an ADR under
   `docs/adr/`.

## See also

- CLAUDE.md §47 — architecture surfaces (the policy)
- CLAUDE.md §52 — brutal tool review (per-tool detail beneath C4)
- `docs/architecture/tool-reviews/` — every reviewed tool
