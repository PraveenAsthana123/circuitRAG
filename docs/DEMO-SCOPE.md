# JWT Scope Enforcement on Draft Resolution

**Status:** 🟢 Green. 6-step drill passes: 401 / 401 / 403 / 200 / 409 all behave.
**Date:** 2026-04-24

Closes:
- `docs/DEMO-HITL.md §"Remaining follow-ups"` row
  "JWT scope check before `resolve_draft` — only role `hr:write` can
  resolve an `hr.*` draft".

Until now any caller with a valid `X-Tenant-Id` header could hit
`POST /api/v1/drafts/{id}/resolve` and replay a tool action — that
was fine for dev but unshippable for prod. This change wires RS256
JWT verification into inference-svc and makes the admin API's
resolve endpoint enforce a **tool-derived role** (`hr.leave_request`
requires `hr:write`).

---

## What shipped

```
libs/py/documind_core/auth.py      — JWTVerifier + JWTAuthMiddleware +
                                     require_roles + required_role_for_tool
mcp/client.py                       — MCPClient.get_draft() helper (so
                                     the router can derive role BEFORE
                                     running the resolve)
services/inference-svc/
  app/main.py                       — registers JWTAuthMiddleware when
                                     the public key is present; opt-in
                                     enforcement via DOCUMIND_AUTH_REQUIRED
  app/routers/__init__.py           — two-phase scope check on
                                     /api/v1/drafts/{id}/resolve
mcp/tests/drill_scope.py            — 6-step drill (401/401/403/200/409)
scripts/dev-keys/                    — RSA keypair generated from
                                     existing scripts/gen-dev-keys.sh
docs/DEMO-SCOPE.md                   — this file
```

## Token shape (mirrors identity-svc)

The Go `identity-svc` issuer mints RS256 tokens with this payload;
the Python verifier accepts the same:

```json
{
  "iss": "documind-local",
  "aud": "documind-services",
  "sub": "<user-uuid>",
  "tenant_id": "<tenant-uuid>",
  "email": "alice@example.com",
  "roles": ["hr:read", "hr:write"],
  "kind": "access",
  "jti": "<uuid>",
  "iat": ..., "nbf": ..., "exp": ...
}
```

The drill mints tokens locally using the same private key — no
identity-svc round-trip needed to prove the contract.

## Role mapping

```python
required_role_for_tool("hr.leave_request")   # → "hr:write"
required_role_for_tool("hr.policy_lookup")   # → "hr:write"
required_role_for_tool("itsm.incident_open") # → "itsm:write"
```

Resolving a draft is always a write-side action (the tool executes),
so we always require `:write`. A future listing-only endpoint could
use `:read` via the same `required_role_for_tool` convention applied
to a read-action variant.

## Auth mode switch

```
DOCUMIND_AUTH_REQUIRED=true   # prod / staging — reject unauth'd
DOCUMIND_AUTH_REQUIRED=false  # dev default — parse token if present,
                              #                do not reject un-tokenized
```

When the flag is off, the middleware still verifies + populates
`state.roles` for any valid token; only `require_roles()` enforcement
is skipped. This means:

- A drill can run `agent/ask` and `list /drafts` without a token,
  like before.
- Only `/api/v1/drafts/{id}/resolve` becomes scope-gated, and only
  when `auth_required=true`.

Future commits can migrate more endpoints under `require_roles`
without touching this gate's shape.

## Two-phase check — why 401 before 404

```python
if auth_required:
    require_roles()(request)                    # (a) 401 if unauthenticated
    record = await client.get_draft(draft_id, tenant_id=...)
    if record is None:
        raise HTTPException(404, ...)           # (b) 404 if not found
    require_roles(required_role_for_tool(record.tool))(request)  # (c) 403
```

The drill's first run flagged an **information leak**: the endpoint
was returning 404 before checking auth, which let an unauthenticated
attacker probe `DRAFT-*` IDs by observing 404-vs-401 response
patterns. The fix is the early `require_roles()` call — authenticate
before any resource lookup. 404 now means "you're authorized AND it
doesn't exist"; 401 means "we didn't even check".

Same principle the RLS layer applies: fail in a way that doesn't
leak existence. Here it's explicit because the role check depends on
the resource (the tool) so we can't put the check in a
`dependencies=[Depends(require_roles(...))]` list alone.

## The 6-step drill

```
── 0. sanity — inference + MCP healthy; auth_required enforced ──
  ✓ auth enforcement verified (401 on unauthenticated)

── 1. kill MCP + create pending draft via agent/ask ──
  ✓ pending draft_id=DRAFT-...

── 2. resolve w/o Authorization → 401 NOT_AUTHENTICATED ──
  ✓ 401 NOT_AUTHENTICATED

── 3. resolve w/ bogus token → 401 INVALID_TOKEN ──
  ✓ 401 INVALID_TOKEN

── 4. resolve w/ hr:read only → 403 INSUFFICIENT_SCOPE ──
  ✓ 403 INSUFFICIENT_SCOPE required=['hr:write'] have=['hr:read']

── 5. restart MCP + resolve w/ hr:write → 200 ──
    waiting 32s for CB recovery_timeout...
  ✓ 200 ticket_id=HR-...

── 6. second resolve w/ hr:write → 409 DRAFT_NOT_PENDING ──
  ✓ 409 DRAFT_NOT_PENDING (scope check didn't bypass state machine)

════════════════════════════════════════
  ALL 6 SCOPE STEPS PASSED
════════════════════════════════════════
```

Run it: `PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_scope.py`

## Remaining follow-ups

- Extend scope gates to `GET /api/v1/drafts` (list) and
  `POST /api/v1/agent/ask` (tool-derived write at creation time,
  not just replay).
- Redis-backed denylist check in the Python verifier — today the
  Go issuer maintains the deny-list; the Python side doesn't
  re-check on every request.
- Audit log entries for auth failures (401/403) for the tenant —
  feeds a "suspicious activity" dashboard.
- Scope mapping via a config file rather than hardcoded convention,
  so ops can grant `hr:write` via a different role name without a
  code change.
