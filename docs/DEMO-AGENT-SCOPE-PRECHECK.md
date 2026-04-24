# Agent-Layer Scope Pre-Check

**Status:** 🟢 Green. 5-step drill confirms `hr:read`-only calls get a structured denial *before* the MCP round-trip.
**Date:** 2026-04-24

Closes a UX + efficiency gap I flagged in the MCP server-side scope
commit: before this change, an `hr:read`-only user hitting
`/api/v1/agent/ask` with a leave-request query would run the full
RAG pipeline (embed + retrieve + LLM), then fire an MCP tool call,
then eat a 403 from MCP, and receive a terse `ok=false` response.
Wasted latency, wasted tokens, opaque error. Now the agent detects
the tool at the point intent matches, checks scope against the
caller's roles, and short-circuits with a structured denial that
still includes the grounded RAG answer.

---

## What shipped

```
services/inference-svc/
  app/services/agent.py      ← scope pre-check after intent detection,
                               before MCP. Uses required_role_for_tool
                               from documind_core.auth.
  app/routers/__init__.py    ← passes roles + auth_required through to
                               the agent.
  app/schemas/__init__.py    ← intent field doc adds action_denied_scope
mcp/tests/drill_agent_scope_precheck.py   ← 5-step drill
docs/DEMO-AGENT-SCOPE-PRECHECK.md          ← this file
```

## The new response shape

```json
{
  "answer": "According to [Source: ...], the parental-leave policy ...",
  "citations": [ /* grounded + cited, same as always */ ],
  "correlation_id": "...",
  "action": {
    "tool": "hr.leave_request",
    "ok": false,
    "error": {
      "code": "INSUFFICIENT_SCOPE",
      "required": ["hr:write"],
      "have":     ["hr:read"],
      "tool":     "hr.leave_request"
    }
  },
  "intent": "action_denied_scope"
}
```

A client sees:
- a useful RAG answer (the user asked a substantive question, the
  agent ran the pipeline, the grounded text is still valuable)
- a structured action.error telling them what they'd need to execute
  the action
- a distinct intent value `action_denied_scope` so dashboards /
  metrics / UIs can treat this as a policy decision, not a failed
  attempt

### Four intent values, four branches

| `intent` | When | Action object |
| --- | --- | --- |
| `answer` | Query didn't match any tool pattern | `None` |
| `action` | Tool matched, scope OK, MCP executed | full result or draft |
| `action_declined` | Tool matched but caller set `allow_actions=false` | `None` |
| `action_denied_scope` | Tool matched, caller lacks required role | `ok=false`, structured `error` |

## Why do RAG before the scope check

The scope check happens *after* the RAG pipeline runs. That might
look wasteful — couldn't we check scope first and skip RAG if the
caller can't act? Three reasons we don't:

1. **The user asked a question.** Even if they can't submit a leave
   request, they *can* read the policy. The RAG answer is still
   useful content; withholding it because they can't execute the
   action is a worse UX than what we have now.
2. **Intent detection depends on the query.** We only know which
   tool is implicated after parsing the query. Without running the
   intent matcher we can't know which role is required.
3. **The RAG layer is cheap relative to the tool execution.** For
   an `hr.leave_request` that creates tickets, we save the MCP
   round-trip + the audit row + the idempotency write. For a pure
   read action we'd save almost nothing. The pre-check's value is
   in avoiding write-side waste and attempt-logged-as-failed noise.

## The 5-step drill

```
── 1. sanity — inference auth_required + mcp up ──
  ✓ inference auth=required; mcp up

── 2. hr:write — happy path creates ticket ──
  ✓ intent=action ticket=HR-...

── 3. hr:read ONLY — action_denied_scope, no MCP call ──
  ✓ intent=action_denied_scope
    error={'code': 'INSUFFICIENT_SCOPE', 'required': ['hr:write'],
            'have': ['hr:read'], 'tool': 'hr.leave_request'}
    answer_len=... citations=3

── 4. verify MCP log shows NO /tools/call for the denied correlation ──
  ✓ MCP log clean for denied correlation_id <uuid>

── 5. a plain-RAG query ignores scope — intent stays 'answer' ──
  ✓ intent=answer action=None — scope check didn't spuriously trigger

════════════════════════════════════════
  ALL 5 AGENT-SCOPE-PRECHECK STEPS PASSED
════════════════════════════════════════
```

Step 4 is the load-bearing one. It grep's `/tmp/mcp-scoped.log` for
the denied request's correlation_id. If the agent had still made
the MCP call, it would have logged the correlation there; absence
is proof of short-circuit.

## Defence-in-depth table (updated)

| Entry point | Scope check? |
| --- | --- |
| `POST /api/v1/drafts/{id}/resolve` | ✅ at admin API AND at MCP |
| `POST /api/v1/agent/ask` | ✅ pre-check in agent + confirm at MCP |
| `POST /tools/call` (direct) | ✅ at MCP |

Three layers for a tool execution: admin API (for replays) or agent
(for new tool calls) rejects unauthorised callers early; MCP's
server-side check is the wall that catches anyone who bypassed the
perimeter. All three use the same `required_role_for_tool`
convention — `hr.leave_request → hr:write`, `itsm.incident_open →
itsm:write`, etc.

## Remaining follow-ups

- **Tool-registry overrides.** The convention is `namespace:write`.
  If a tool ever needs a different scope (e.g. `hr.policy_lookup`
  requires `hr:read`, not `hr:write`), today the agent's pre-check
  hard-codes `:write`. A lookup in the tool catalog's
  `required_scopes` field would match MCP's own enforcement. Small
  follow-up; the convention is correct for every current tool.
- **Metrics label for denial cause.** `documind_agent_denials_total
  {reason="scope"|"allow_actions_false"}` would let a dashboard
  distinguish policy denials from user-configured ones.
- **Audit row on agent-level denial.** Today only MCP-executed
  tools produce `mcp_draft.created` / `mcp_draft.replayed` rows.
  Agent-level denials could log `agent.scope_denied` to the same
  hash-chained audit log so governance reviews see rejections
  too.
