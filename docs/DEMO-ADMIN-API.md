# HITL Admin API — List + Resolve MCP Drafts over HTTP

**Status:** 🟢 Green. 9-step drill passes end-to-end.
**Date:** 2026-04-24

Closes:
- `docs/DEMO-HITL.md §"Remaining follow-ups"` row
  "Admin API: GET /api/v1/drafts?status=pending + POST /api/v1/drafts/{id}/resolve".

The HITL persistence landed with the previous commit — drafts live in
`governance.action_drafts`. Until now, an operator only had two ways
to touch them: direct SQL, or a Python REPL driving `MCPClient`.
Neither is a shippable ops surface. This change exposes two HTTP
endpoints on `inference-svc` so any ops tool — a CLI, a curl cronjob,
a small Next.js page — can drive the replay loop.

---

## What shipped

```
services/inference-svc/
  app/schemas/__init__.py   — DraftSummary, DraftListResponse, DraftResolveResponse
  app/routers/__init__.py   — 2 new endpoints under /api/v1/drafts
mcp/tests/
  drill_admin_api.py        — 9-step HTTP drill
docs/
  DEMO-ADMIN-API.md         — this file
```

## API surface

### `GET /api/v1/drafts?status=pending`

Lists drafts for the requesting tenant. Today only `status=pending` is
supported; the query param exists for forward compat (future: `replayed`,
`rejected`, `all`).

**Headers:** `X-Tenant-Id: <uuid>` (required — RLS binds to it)

**200 response:**
```json
{
  "drafts": [
    {
      "draft_id": "DRAFT-8FE0F24E43",
      "tool": "hr.leave_request",
      "arguments": {"days": 4, "reason": "...", "employee_id": "E42"},
      "tenant_id": "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
      "correlation_id": "c21995aa-594e-426b-9cfc-54ca2aff4355",
      "reason": "ConnectError",
      "status": "pending",
      "created_at": 1777059010.123,
      "replayed_at": null,
      "replay_result": null
    }
  ],
  "tenant_id": "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
  "status_filter": "pending"
}
```

**400:** unsupported status filter.

### `POST /api/v1/drafts/{draft_id}/resolve`

Replays a pending draft via `MCPClient.resolve_draft(draft_id, tenant_id)`,
which re-invokes the original tool using `draft_id` as the idempotency
key, then marks the PG row `status=replayed` with the result.

**Headers:** `X-Tenant-Id: <uuid>`

**200 (happy path):**
```json
{
  "draft_id": "DRAFT-8FE0F24E43",
  "ok": true,
  "result": {"ticket_id": "HR-33287D2D", "status": "pending_approval"},
  "error": null,
  "degraded": false,
  "new_draft_id": null,
  "idempotent_replay": false
}
```

**200 (replay itself degraded — MCP still down):** `ok=false`, `degraded=true`,
`new_draft_id` set to the draft persisted by the failed replay. The
*original* draft stays `pending`; a fresh row is written for the new
failure. This is the "don't lose work even on a retry" invariant.

**404** `DRAFT_NOT_FOUND` — the id doesn't exist, or belongs to a
different tenant (RLS hides it).

**409** `DRAFT_NOT_PENDING` — already replayed / rejected. Safe to
retry once the initial state resolves.

---

## The 9-step drill

```
── 0. sanity — services up ──
  ✓ inference + MCP healthy

── 1. GET /api/v1/drafts — baseline ──
  ✓ baseline drafts (pending) = 1

── 2. kill MCP ──
  ✓ MCP down

── 3. agent/ask with leave request → degraded draft ──
  ✓ degraded=true new_draft_id=DRAFT-8FE0F24E43

── 4. GET /api/v1/drafts — new draft is listed ──
  ✓ draft found: tool=hr.leave_request reason=ConnectError
    args={'days': 4, 'reason': '...', 'employee_id': 'E42'}

── 5. restart MCP ──
  ✓ MCP back up

── 6. POST /api/v1/drafts/{id}/resolve ──
    waiting 32s for CB recovery_timeout...
  ✓ replay ok ticket_id=HR-33287D2D

── 7. GET /api/v1/drafts — replayed draft no longer pending ──
  ✓ replayed draft removed from pending (current pending count=1)

── 8. second resolve_draft → 409 DRAFT_NOT_PENDING ──
  ✓ 409 DRAFT_NOT_PENDING (status=replayed)

── 9. unknown draft_id → 404 DRAFT_NOT_FOUND ──
  ✓ 404 DRAFT_NOT_FOUND

════════════════════════════════════════
  ALL 9 ADMIN-API STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_admin_api.py`

---

## Why the 32s wait in step 6

The `MCPClient`'s circuit breaker in the running `inference-svc`
process counted the failure from step 3 and (after enough of them)
would open. Even with MCP back up, the client won't attempt until
`recovery_timeout` elapses — that's the whole point of the breaker.
In a real ops flow the operator replays drafts minutes or hours
after a known recovery, so the wait is invisible. The drill just
eats it.

A future follow-up: surface `cb_state` on `MCPClient` through an
`/api/v1/health/detailed` endpoint so a replay worker can poll,
wait for `closed`, then fire. Today's lack of it is a drill
inconvenience, not a correctness issue.

---

## Security — how far we got, what's next

Today:
- RLS isolation on `governance.action_drafts` (tenant can't see
  another tenant's drafts via either endpoint).
- `X-Tenant-Id` must be present; middleware rejects anonymous calls.
- 404 for "wrong tenant" (no side-channel: sending another tenant's
  draft_id returns the same 404 as an invented id).

Still open (tracked in [DEMO-HITL.md](DEMO-HITL.md)):
- JWT scope enforcement — only `hr:write` should be allowed to
  resolve an `hr.leave_request` draft.
- Audit log rows on every `resolve_draft` call — who replayed,
  when, with what result.

Both are additive: the endpoints stay the same shape, just with a
middleware that throws 403 before the replay path runs.

---

## Curl recipe (ops quick reference)

```bash
export T=137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a

# list pending drafts for my tenant
curl -s http://127.0.0.1:8084/api/v1/drafts?status=pending \
  -H "X-Tenant-Id: $T" | jq .

# replay a specific draft
curl -s -X POST http://127.0.0.1:8084/api/v1/drafts/DRAFT-8FE0F24E43/resolve \
  -H "X-Tenant-Id: $T" | jq .
```
