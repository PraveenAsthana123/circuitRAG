# Compatibility Guide

> §19 mandate. Substantive content lives at:
>
> See: [`~/.claude/CLAUDE.md`](../../.claude/CLAUDE.md) §28 — Backward & Forward Compatibility
> See: [`docs/architecture/adr/008-transport-breakers-vector-graph.md`](architecture/adr/008-transport-breakers-vector-graph.md) — circuit breaker compat
> See: [`docs/architecture/draft-replay-refactor-plan.md`](architecture/draft-replay-refactor-plan.md) — schema-evolution example

## API compatibility rules (CLAUDE.md §28.1)

- New fields MUST have defaults
- NEVER remove fields — deprecate first, remove after 2 releases
- NEVER change field types — version the API
- ALWAYS support both old and new field names during transition

## Database migration strategy: expand → migrate → contract

1. **Expand**: add the new column nullable OR with default. Keep
   old column. Both reads work.
2. **Migrate**: backfill new column. Update writers to write both.
   Update readers to prefer new, fall back to old.
3. **Contract**: stop writing old column. After 2 releases, drop
   old column in a new migration.

Never drop a column in the same release that adds it.

## ADR-008 example

`docs/architecture/adr/008-transport-breakers-vector-graph.md`
shows the pattern applied to circuit breakers across the
vector-search and graph-search transports. Both breakers stayed
operational during the rollout; only after the new breaker was
verified did the old code path get retired.

## Component compatibility (frontend)

- New props MUST have default values
- Deprecated props: support both + console.warn in dev
- Use `...rest` to forward unknown props (forward compatible)

## Deployment compatibility

- Both old and new code MUST run simultaneously (rolling deploy)
- Feature flags for risky changes
- Rollback plan documented for every release (CLAUDE.md §47.7)
- `/api/health` (or `/health/live` + `/health/ready`) always available

## Compatibility checklist per release

- [ ] No removed API fields without 2-release deprecation
- [ ] No same-release column add+drop
- [ ] All new props have defaults
- [ ] Feature flag gates new behavior (if risky)
- [ ] Rollback path tested in staging
- [ ] Health probes return same shape across versions
- [ ] Drill against previous-version client (if shipping API change)
