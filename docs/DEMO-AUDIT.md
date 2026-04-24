# Audit Log — Tamper-Evident Hash Chain for MCP Draft Lifecycle

**Status:** 🟢 Green. 6-step drill passes; chain hashes recompute end-to-end.
**Date:** 2026-04-24

Closes:
- `docs/DEMO-HITL.md §"Remaining follow-ups"` row
  "Audit log for every draft transition".

Every `mcp_draft.created` / `mcp_draft.replayed` transition now lands
a row in `governance.audit_log` with `previous_hash` + `entry_hash`
forming a per-tenant append-only chain. Any modification or
insertion after the fact breaks the chain, making the tampering
detectable by a reader that re-walks the rows.

---

## What shipped

```
libs/py/documind_core/audit.py   — AuditWriter + hash helpers
mcp/client.py                     — MCPClient takes optional audit_log;
                                    writes on draft.created + draft.replayed
services/inference-svc/
  app/main.py                     — lifespan builds an AuditWriter from
                                    the DbClient and hands it to MCPClient
mcp/tests/drill_audit.py          — 6-step drill proving chain integrity
docs/DEMO-AUDIT.md                — this file
```

## Actions emitted today

| action | when | details payload |
| --- | --- | --- |
| `mcp_draft.created` | `MCPClient._persist_draft` fires (CB OPEN, connection refused, or HTTP 5xx) | `{draft_id, tool, reason, cb_state}` |
| `mcp_draft.replayed` | `MCPClient.resolve_draft` successfully re-executes a pending draft | `{draft_id, tool, result, idempotent_replay}` |

Future actions that will join the same chain (not in this change):
`mcp_draft.rejected`, `policy.evaluated`, `admin.login`,
`admin.tenant_toggled`, etc. The schema + writer support any
`(action, resource_type, details)` tuple.

## Hash scheme

```
previous_hash = last audit_log row's entry_hash for this tenant
body = {
  "previous_hash": previous_hash,
  "timestamp":     NOW()::text,
  "tenant_id":     tenant_id,
  "actor_type":    actor_type,
  "action":        action,
  "resource_type": resource_type or "",
  "details":       details
}
entry_hash = sha256( canonical_json(body) )
```

`canonical_json` uses sorted keys + compact separators so whitespace
and key order cannot perturb the hash for the same logical row.
The first row for a new tenant uses `previous_hash = ""`.

## RLS + the chain

`documind_app` is NOBYPASSRLS. The writer opens a tenant-scoped
session (`SET LOCAL app.current_tenant`) before SELECTing the last
`entry_hash` AND before INSERTing — so the chain read + write are
both subject to tenant isolation. Cross-tenant chain forging is
blocked by Postgres, not by application code.

The drill verifies this indirectly: it can only read its own
tenant's rows when it explicitly sets `app.current_tenant` in the
reader session. Without the setting the RLS policy returns zero rows
(silent isolation — same failure mode as the admin API's 404 on
cross-tenant draft lookups).

## The 6-step drill

```
── 0. sanity — inference + MCP healthy ──
  ✓ services up
  ✓ baseline audit rows for tenant=0 last_hash=...

── 1. kill MCP ──
  ✓ MCP down

── 2. agent/ask → draft created ──
  ✓ degraded draft_id=DRAFT-D6A4AC8BE3

── 3. audit row for mcp_draft.created exists + chains ──
  ✓ mcp_draft.created row chain-valid hash=163f4545a1a0...

── 4. restart MCP → POST /drafts/{id}/resolve ──
  ✓ MCP back up
    waiting 32s for CB recovery_timeout...
  ✓ replayed ticket_id=HR-0652822F

── 5. audit row for mcp_draft.replayed chains onto prior ──
  ✓ mcp_draft.replayed chain-valid hash=5ae29248ec72...
    details.ticket_id=HR-0652822F

── 6. full-chain verify — every row hash recomputes ──
  ✓ all 2 rows hash-valid, chain intact end-to-end

════════════════════════════════════════
  ALL 6 AUDIT STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_audit.py`

## What's next (still open)

- ✅ Verification CLI — done, see [DEMO-AUDIT-VERIFIER.md](DEMO-AUDIT-VERIFIER.md).
- Dual-audit: also stream rows to Kafka `audit.events` topic for
  real-time governance consumers.
- `actor_id` population: today we use `actor_type="service"` with
  `actor_id=NULL`; a JWT middleware pass would fill in the user's
  UUID and move the row from "service action" to "attributable action".
- Retention policy: audit rows are currently permanent. A
  `003_audit_retention.sql` migration should set
  a 90-day retention window for dev, configurable per-tenant in prod.
