# Code Guidelines

> §19 mandate. Substantive content lives at:
>
> See: [`~/.claude/CLAUDE.md`](../../../.claude/CLAUDE.md) — global rules §3, §13, §14, §33, §34
> See: [`pyproject.toml`](../pyproject.toml) — ruff/black/mypy config
> See: [`docs/architecture/`](architecture/) — design docs and ADRs

## Project-local additions to global rules

The global CLAUDE.md governs most rules. circuitRAG specifics:

- **Drill discipline**: every feature commit ships a drill (§43).
  Drills must include at least one negative assertion.
- **Compose-footer policy**: every page under
  `services/frontend/app/admin/<x>/deep/page.tsx` ends with
  `<DeepDiveCrossRefs>` listing 3-7 sibling pages with a
  one-sentence WHY each (§49).
- **ADR discipline**: one ADR per immutable decision, numbered
  sequentially under `docs/architecture/adr/`.
- **No mocks of business logic in drills**: drills hit real
  docker-compose services. Mocks belong in pytest under
  `libs/py/tests` or `services/<svc>/tests/`.

## Style enforcement

- **Python**: ruff (lint + format) + black + mypy. Configured in
  [`pyproject.toml`](../pyproject.toml).
- **Go**: gofmt + go vet. Run `go test ./...` per service.
- **TypeScript**: `next lint` (Next.js wrapper around ESLint) +
  Prettier. Format scripts in
  [`services/frontend/package.json`](../services/frontend/package.json)
  (`format`, `format:check`, `validate`, `pre-merge`).

## Naming conventions

| Surface | Convention |
|---|---|
| Service dirs | `<role>-svc` (e.g. `inference-svc`, `governance-svc`) |
| Drill files | `mcp/tests/drill_<topic>.py` |
| ADRs | `docs/architecture/adr/NNN-<slug>.md` (zero-padded 3-digit) |
| Demo docs | `docs/DEMO-<TOPIC>.md` |
| Migration files | `services/<svc>/migrations/NNN_<slug>.sql` |

## Review checklist

See [`docs/architecture/tech-lead-audit-checklist.md`](architecture/tech-lead-audit-checklist.md).
