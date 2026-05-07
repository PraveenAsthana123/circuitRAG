# ADR-025: Feature-flag-gated dual-write for §47.7 expand→migrate transitions

## Status

Accepted — applied across commits `7c404e1` (mcp-gateway-dualwrite,
iter 11), `1fc1b0b` (opsworker-dualwrite, iter 12), and `c23d142`
(tools-catalog-sync, iter 13). Surfaced via `migrate_phase_status` in
commits `c23d142` (iter 14) + `bb2dy3c97` (iter 16 dashboard panel).

## Context

CLAUDE.md §47.7 lays out the four-layer rollback discipline:
expand → migrate → contract. For database schemas, the policy is
clear:

  1. **Expand**: add the new table/column. NEVER drop the old one
     in the same release.
  2. **Migrate**: backfill data, dual-write to keep both stores in
     sync.
  3. **Contract**: remove the old store ONLY after the new one has
     proven itself in production.

This session shipped 3 schema-expansions (iters 7-9) followed by 3
write-path migrations (iters 11-13). Each migration faces a tension:

  * The **legacy writer** (JSONL audit, JSON task file, Python TOOLS
    literal) is the current load-bearing source — disabling it while
    the SQL surface is unproven is a §47.7 rollback violation.
  * The **SQL writer** must run alongside until the operator
    validates parity in production.
  * The **operator** needs an explicit opt-in mechanism so they can
    flip writers on per-environment (dev → staging → prod) at their
    own pace, NOT on the deploy that ships the code.

We needed one consistent pattern to handle all three migrations,
drilled the same way, surfaced in one place on the dashboard.

## Decision

**Every §47.7 migrate-phase write-path uses the same feature-flag
pattern.** Concretely:

1. The legacy writer remains untouched and authoritative.
2. The new SQL writer is a sibling function called ONLY when an
   environment variable is set to `"1"`.
3. The env variable name follows the convention
   `<SUBSYSTEM>_SQL_<MODE>_ENABLED` (e.g.
   `MCP_GATEWAY_SQL_AUDIT_ENABLED`, `OPS_WORKER_SQL_ENABLED`,
   `MCP_TOOLS_SYNC_ENABLED`).
4. SQL write failure NEVER propagates back to the caller — caught
   + logged via `logging.warning`. The legacy writer's success
   path is preserved.
5. The drill MUST exercise:
   - the OFF state (flag unset → no SQL row, legacy still written)
   - the ON state (flag set → both surfaces, parity verified)
   - the SQL-failure path (PG unreachable → legacy still written)
   - read-only contract grep (no INSERT/UPDATE/DELETE in
     unrelated functions)
6. Paperclip's `migrate_phase_status` aggregator surfaces:
   - per-flag enabled / env_var / since_iter / legacy_path / sql_table
   - per-flag legacy_size_bytes vs sql_count parity signal
   - honest_gap when flag is ON but parity is `no_traffic_since_flip`
7. `.env.template` documents every flag with default `0` (off).

## Consequences

### Positive

- **Operator owns the rollout cadence per surface**. Three flags
  flipped independently means dev can validate iter-11 alone before
  enabling iter-12. A bad SQL-side schema choice in one surface
  doesn't block the others.
- **Behavior unchanged on deploy**. Code lands in production with
  flag=0; legacy writers behave identically. No surprise SQL load
  from a release.
- **Drill discipline scales**. The 4-step drill template (off /
  on / sql-fail / read-only-grep) applies to every dual-write,
  drillable in ~7 steps each. Three migrations = 22 drilled
  invariants without per-feature scaffolding.
- **Dashboard visibility solves the "did I configure it?" problem**.
  The migrate_phase_status panel shows operator at-a-glance which
  flags are on AND whether traffic is flowing. Misconfiguration
  (flag=on but writer never ran) lights up in red.

### Negative

- **Two writers in production for the migrate-phase window**. Higher
  CPU + I/O on every write path while the flag is on. Mitigated by
  best-effort SQL: failure adds ~20ms log overhead, not a request
  block.
- **Schema drift risk**. The legacy and SQL surfaces can diverge if
  a field is added to one but not the other. Drill mitigates by
  asserting field parity on the round-trip in step 3.
- **Never-finished migrations are a real failure mode**. A flag
  flipped to ON in dev but never validated in prod could drift
  forever. Mitigation: §47.7 contract phase is an explicit
  operator decision; until then, dual-write is the durable state.

### Risks accepted

- **Connection-pool pressure**. Each dual-write opens an asyncpg
  connection per call (no pooling in the writer); under heavy
  load this could exhaust PG max_connections. Acceptable for the
  current per-event cadence (~1 write per gateway request, low
  thousands per day). If hot-path traffic increases 100x, switch
  to a shared pool.
- **Operator must know the flag exists**. We mitigate via
  `.env.template` documentation + the dashboard surface. But a
  true zero-discovery operator who never reads either could miss
  the migration window entirely. Acceptable cost — the legacy
  writer never breaks.

## Alternatives considered

### A1 — Synchronous dual-write with rollback on SQL failure

Rejected. Would mean the legacy success becomes blocked on SQL
availability. Per §47.7's "legacy authoritative until contract",
the SQL side cannot impede the legacy path's success. Operator
would never opt in if every PG hiccup broke production writes.

### A2 — Outbox pattern (legacy writes a queue, SQL writer drains)

Rejected for this iteration. The repo already has an outbox
pattern at `ingestion.outbox` for Kafka publishes; adding three
more outbox tables for migrate-phase work doubles the operator
mental model AND requires another worker process. The dual-write
pattern keeps the flag-flip surface minimal.

The right time for outbox would be when one of these surfaces
proves to need throughput-decoupling (e.g. SQL writes are too slow
to inline). Until then, sync dual-write is enough.

### A3 — Migrate-only, drop legacy on the same release

Rejected. Direct §47.7 violation. The session's three migrations
write to schemas that DON'T have the same shape as the legacy
sources (status normalization, field renames, JSONB conversion).
Without dual-write, an operator who needed to rollback the
migration would be left with both stores in incompatible states.

### A4 — Per-tenant flags instead of global env

Rejected as over-engineered for this iteration. The 3 surfaces are
service-account / system-tenant in their flag-on state; per-tenant
gating doesn't apply. Future iterations that move tenant-scoped
data could add a per-tenant flag IF the operator demands it.

## References

- CLAUDE.md §38 — governance gates
- CLAUDE.md §47.7 — expand→migrate→contract discipline
- CLAUDE.md §52 row 4 — operator API gap closure
- CLAUDE.md §55.3 — outcome-based contract

### Drilled by

- `mcp/tests/drill_mcp_gateway_dual_write.py` — 7 steps, 4 negative
- `mcp/tests/drill_ops_worker_dual_write.py` — 8 steps, 4 negative
- `mcp/tests/drill_tools_catalog_sync.py` — 10 steps, 5 negative
- `mcp/tests/drill_migrate_phase_status.py` — 9 steps, 4 negative

### Commits implementing this pattern

- `da95525` — iter 8 expand: `governance.tool_executions` table
- `5189b2e` — iter 9 expand: `governance.tools` table
- `05d4813` — iter 7 expand: `orchestration.agent_task_runs` lane
- `7c404e1` — **iter 11 migrate**: `MCP_GATEWAY_SQL_AUDIT_ENABLED` flag
- `1fc1b0b` — **iter 12 migrate**: `OPS_WORKER_SQL_ENABLED` flag
- `c23d142` — **iter 13 migrate**: `MCP_TOOLS_SYNC_ENABLED` flag
- `c23d142` — iter 14 surface: `migrate_phase_status` Paperclip key
- `bb2dy3c97` — iter 16 visibility: dashboard panel
- `365c4c8` — iter 15 regression: 12 drills added to verify-stack

### Operator-side activation (post-this-ADR)

```bash
# 1. Validate dev parity for one flag at a time:
export MCP_GATEWAY_SQL_AUDIT_ENABLED=1
# Run gateway through normal traffic; check
# /admin/dashboard → Migrate-phase panel for parity='active'
# OR query directly:
psql -c "SELECT count(*) FROM governance.tool_executions WHERE created_at > NOW() - INTERVAL '5 minutes';"

# 2. Once dev parity holds for ≥24h, enable in staging.
# 3. Once staging parity holds for ≥7d, enable in prod.
# 4. Contract-phase (remove JSONL writer) is a SEPARATE ADR.
```
