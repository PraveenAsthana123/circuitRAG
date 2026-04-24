# HITL — Durable MCP Draft Persistence (closes DEMO-DAY-3-MCP gap)

**Status:** 🟢 Green. In-memory `_DRAFTS` dict → `governance.action_drafts` table. Drills pass. Golden demo still green end-to-end with PG-backed drafts.
**Date:** 2026-04-24

Closes:
- `docs/DEMO-DAY-3-MCP.md §"What's NOT in this first cut"` row
  "Audit log persisted to `governance.audit_log` / replace in-memory `_DRAFTS`".
- `docs/DEMO-GOLDEN.md` follow-up "Persist drafts to `governance.hitl_queue`".

---

## What shipped

```
services/governance-svc/migrations/
  003_action_drafts.sql       — table + indexes + RLS (FORCE)
mcp/
  drafts.py                    — DraftStore protocol + InMemoryDraftStore + PostgresDraftStore
  client.py                    — MCPClient now takes a draft_store + gets a resolve_draft()
  tests/drill_hitl.py          — 7-step drill: save → verify PG row → restart → replay → verify replayed
services/inference-svc/
  app/main.py                  — lifespan wires PostgresDraftStore from DbClient
docs/
  DEMO-HITL.md                 — this file
```

## Schema (summary)

```sql
CREATE TABLE governance.action_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id        TEXT NOT NULL UNIQUE,           -- "DRAFT-XXXX" returned to the caller
    tenant_id       UUID,                           -- NULL for service-account calls
    tool            TEXT NOT NULL,                  -- e.g. "hr.leave_request"
    arguments       JSONB NOT NULL,                 -- original tool arguments
    correlation_id  UUID,
    reason          TEXT NOT NULL,                  -- "cb_open" | "ConnectError" | "http_5xx"
    status          TEXT NOT NULL DEFAULT 'pending',-- pending | replayed | rejected
    replay_result   JSONB,
    replayed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- indexes on (status, created_at) and (tenant_id, status, created_at)
-- RLS: ENABLE + FORCE; tenant_isolation policy using current_setting('app.current_tenant')
```

## Design decisions

**Separate table, not `governance.hitl_queue`.** The existing
`hitl_queue` is shaped for answer-review (question / retrieved_chunks /
generated_answer / confidence). Action drafts are a different concern:
the arguments + tool + reason + replay result. Jamming both into one
table would force us to null-out load-bearing columns on either side.
Two focused tables, one human reviewer view that UNIONs them, is the
right shape — and leaves us free to evolve each schema independently.

**RLS on, two connection modes.** Runtime services connect as
`documind_app` (NOBYPASSRLS). The policy is
`tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant')`,
so:
- tenant-scoped save/read/update → `DbClient.tenant_connection(tenant_id)`
- NULL-tenant (service-account) rows → `DbClient.admin_connection()`
  (same user, just no tenant setting; the `tenant_id IS NULL` branch
  of the policy lets the row through).
Both paths live in `PostgresDraftStore._conn_for(tenant_id)`.

**`draft_id` is the capability token.** Knowing a `DRAFT-XXXX` string
is how an operator proves legitimate access. But with FORCE RLS the
store can't look up a tenant-scoped row without first knowing the
tenant — so all mutating APIs take `tenant_id` as a parameter. The
agent already has it from request context; no cost.

**Fallback to in-memory.** If Postgres isn't reachable at startup,
`inference-svc` logs `draft_store_fallback_inmemory` and continues to
run. Drafts won't survive restart — but the service still boots, the
`/api/v1/ask` endpoint still works, and `/api/v1/agent/ask` still
returns `degraded=true` on MCP failure. One failed dependency → one
degraded capability, not a total outage.

**Replay is a capability, not an automated worker.** `MCPClient.resolve_draft(draft_id, tenant_id=...)` is a stepping stone: it proves
the round-trip (PG row → retry tool → mark replayed). A scheduled job
that polls `list_pending_drafts` and replays on some policy lives in
a follow-up — not this change.

## The 7-step HITL drill

```
── 1. Bring up MCP + open PG pool ──
  ✓ MCP healthy at http://127.0.0.1:8090
  ✓ PG pool open + PostgresDraftStore wired

── 2. Happy path — ticket created (no draft) ──
  ✓ ticket_id=HR-6B0D67C0

── 3. Kill MCP → call fails → draft persisted ──
  ✓ degraded=True draft_id=DRAFT-FED7CD5531

── 4. Query PG — row exists, status='pending' ──
  ✓ row OK status=pending tool=hr.leave_request
    tenant=137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a reason=ConnectError

── 5. Restart MCP → resolve_draft → ticket created ──
  ✓ MCP back up
  ✓ replay ticket_id=HR-802F9D5D idempotent_replay=False

── 6. PG row now status='replayed' with result ──
  ✓ status=replayed result.ticket_id=HR-802F9D5D
    replayed_at=2026-04-24 19:22:20.767961+00:00

── 7. Second resolve_draft returns DRAFT_NOT_PENDING ──
  ✓ second replay rejected: {'code': 'DRAFT_NOT_PENDING', 'status': 'replayed'}

════════════════════════════════════════
  ALL 7 HITL STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag DOCUMIND_PG_USER=documind_app DOCUMIND_PG_PASSWORD=documind_app python mcp/tests/drill_hitl.py`

## Integration evidence — the golden demo still green, with PG

After restarting `inference-svc` with the new wiring, the golden demo
ran end-to-end: `draft_store_ready backend=postgres`, all 10 steps
green (PASSED: 13, FAILED: 0), and the draft persisted in step 7 was
visible directly in Postgres:

```
draft_id         | tool             | status  | reason       | correlation_id
-----------------+------------------+---------+--------------+--------------------------------------
DRAFT-28906F2EF9 | hr.leave_request | pending | ConnectError | c21995aa-594e-426b-9cfc-54ca2aff4355
```

Two rows visible post-run: the HITL drill's replayed row, and the
golden demo's pending row — exactly what the two scripts produced.

## Remaining follow-ups

| Follow-up | Status |
| --- | --- |
| Admin API: `GET /api/v1/drafts?status=pending` + `POST /api/v1/drafts/{id}/resolve` | ✅ closed — see [DEMO-ADMIN-API.md](DEMO-ADMIN-API.md) |
| Audit log for every draft transition | ✅ closed — see [DEMO-AUDIT.md](DEMO-AUDIT.md) |
| Scheduled replay worker | ✅ closed — see [DEMO-WORKER.md](DEMO-WORKER.md) |
| JWT scope check before `resolve_draft` | open — only role `hr:write` can resolve an `hr.*` draft |

Each remaining gap is a focused commit.
