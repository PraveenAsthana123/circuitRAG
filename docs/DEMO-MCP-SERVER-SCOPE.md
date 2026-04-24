# MCP Server-Side Scope Enforcement

**Status:** 🟢 Green. 8-step drill passes on direct calls; end-to-end agent/ask path validated with forwarded JWT.
**Date:** 2026-04-24

Closes a real defence-in-depth gap: until this commit, the inference-svc
admin API (`/api/v1/drafts/{id}/resolve`) was the **only** place that
enforced per-tool scopes. Any caller with network access to
`:8090/tools/call` — a sidecar, a neighbouring pod, a misconfigured
proxy — could execute tools without any auth. Now the MCP server
verifies the caller's JWT and intersects `roles` against the tool's
declared `required_scopes` before executing.

---

## What shipped

```
libs/py/documind_core/auth.py      ← JWTAuthMiddleware now captures
                                      request.state.raw_token for forwarding
mcp/client.py                       ← MCPClient.call_tool + resolve_draft
                                      accept auth_token=, sent as
                                      Authorization: Bearer ... to MCP
services/inference-svc/
  app/services/agent.py             ← agent.ask(auth_token=) pass-through
  app/routers/__init__.py           ← agent/ask + resolve_draft routes read
                                      request.state.raw_token and forward
mcp/server_hr.py                    ← MCP_AUTH_REQUIRED=true turns on
                                      _TokenVerifier + _enforce_scope; runs
                                      BEFORE the idempotency cache lookup
                                      so a leaked key isn't a replay primitive
mcp/tests/drill_mcp_server_scope.py ← 8-step drill
docs/DEMO-MCP-SERVER-SCOPE.md       ← this file
```

## Config

```
MCP_AUTH_REQUIRED=true                      # opt-in; false by default
MCP_JWT_PUBLIC_KEY_PATH=<path>              # falls back to DOCUMIND_JWT_PUBLIC_KEY_PATH
DOCUMIND_JWT_ISSUER=documind-local          # default
DOCUMIND_JWT_AUDIENCE=documind-services     # default
```

Why opt-in rather than on-by-default: the existing drills +
`mcp/tests/drill_e2e.py` + `drill_hitl.py` call MCP directly without
tokens. Turning scope on globally would break them; a deliberate
enablement via env keeps each drill in charge of its own auth posture.
Production / staging sets `MCP_AUTH_REQUIRED=true` explicitly.

## Token-forwarding data flow

```
  User --Bearer-->  NGINX / API gw  --Bearer-->  inference-svc
                                                       │
           ┌───────────────────────────────────────────┤
           │  JWTAuthMiddleware                        │
           │    verify signature + claims              │
           │    state.tenant_id = claim.tenant_id      │
           │    state.roles = claim.roles              │
           │    state.raw_token = raw  ← NEW           │
           └───────────────────────────────────────────┤
                                                       │
                                                       ▼
                                  routes/agent_ask, routes/resolve_draft
                                        │
                                        │  auth_token = state.raw_token
                                        ▼
                                  agent.ask(..., auth_token=...)
                                        │
                                        │  forward
                                        ▼
                                  MCPClient.call_tool(..., auth_token=...)
                                        │
                                        │  Authorization: Bearer <raw>
                                        ▼
                                  mcp-server-hr POST /tools/call
                                        │
                                        │  _enforce_scope:
                                        │    _VERIFIER.verify(token)
                                        │    required = tool.required_scopes
                                        │    if required.isdisjoint(roles): 403
                                        ▼
                                  (dispatch or idempotent replay)
```

Both hops verify the SAME JWT with the SAME public key. This is not
a "trusted service-account" pattern — it's end-user identity
flowing through the mesh, so every hop can make its own policy
decision. If an attacker compromises inference-svc, MCP still
refuses to execute tools the *user's* roles don't cover.

## Scope check comes BEFORE the idempotency cache

Deliberate: if we checked scope only on fresh calls and trusted the
cache for replays, a leaked `Idempotency-Key` would be a replay
primitive — an attacker with read-only scope could resurrect past
write actions just by replaying the key. The check runs first, then
the dispatch path checks idempotency. Step 8 of the drill asserts
this explicitly.

## The 8-step drill

```
── 1. sanity — /health OK without auth (public) ──
  ✓ mcp-server-hr is up
  ✓ MCP_AUTH_REQUIRED enforcement confirmed

── 2. /tools/call no Authorization → 401 NOT_AUTHENTICATED ──
── 3. bogus token → 401 INVALID_TOKEN ──
── 4. hr.leave_request w/ hr:read only → 403 INSUFFICIENT_SCOPE ──
  ✓ tool=hr.leave_request required=['hr:write'] have=['hr:read']
── 5. hr.leave_request w/ hr:write → 200 + ticket ──
── 6. hr.policy_lookup (read tool) w/ hr:read → 200 ──
── 7. idempotent replay w/ hr:write again → same ticket ──
── 8. replay attempt w/ hr:read only → 403 ──
  ✓ INSUFFICIENT_SCOPE on replay — idempotency cache does NOT bypass scope

════════════════════════════════════════
  ALL 8 MCP-SERVER-SCOPE STEPS PASSED
════════════════════════════════════════
```

Run it (MCP must already be running with `MCP_AUTH_REQUIRED=true`):

```bash
PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_mcp_server_scope.py
```

## End-to-end agent path

Verified with inference-svc running auth-on + MCP auth-on:

```
agent/ask + Bearer <hr:write token>
  → 200 + action.result.ticket_id=HR-D7333805

agent/ask + Bearer <hr:read token>
  → 200, action.ok=false, degraded=false, error=None
  (MCP returned 403; MCPClient correctly did NOT persist a draft
   because 4xx is a caller problem, not a downstream outage.)
```

## Defence-in-depth table

Before this commit:

| Entry point | Scope check? |
| --- | --- |
| `POST /api/v1/drafts/{id}/resolve` | ✅ tool-derived role |
| `POST /api/v1/agent/ask` | ❌ any tenant-authenticated caller |
| `POST /tools/call` (direct) | ❌ anyone on the network |

After:

| Entry point | Scope check? |
| --- | --- |
| `POST /api/v1/drafts/{id}/resolve` | ✅ at admin API AND at MCP |
| `POST /api/v1/agent/ask` | ✅ at MCP (token forwarded) |
| `POST /tools/call` (direct) | ✅ at MCP |

inference-svc's perimeter check on `/resolve` is still load-bearing —
it gives a cleaner 403 at the user-facing layer — but MCP's enforcement
means compromise of inference-svc alone doesn't give an attacker tool
execution they shouldn't have.

## Remaining follow-ups

- **Error envelope shape mismatch** — ✅ closed by the follow-up
  commit that added `_normalise_error` and `drill_client_error_envelope.py`.
  MCP's 4xx now arrives at callers as
  `ToolResult(ok=False, error={'code': ..., 'http_status': ..., ...})`
  with the full `required`/`have`/`tool`/`name` detail preserved. 4xx
  still leaves the circuit breaker CLOSED (correctly distinguishes
  "server said no" from "server is unreachable").
- **Agent-level scope gate** — today an `hr:read`-only user can still
  hit `/api/v1/agent/ask` and have the agent *attempt* an action,
  getting a late 403 from MCP. A cleaner UX pre-checks at the agent
  layer before even running the RAG pipeline, using
  `required_role_for_tool(intent.tool)`.
- **Stdio/SSE transport** — still on the MCP scaffold follow-up list;
  orthogonal to scope enforcement (same JWT, different transport).
