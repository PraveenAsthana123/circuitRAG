"""
Microsoft Teams MCP server — read-only Stage-1.

Per CLAUDE.md §44 (iter-67 batch with jira/whatsapp/gdrive/servicenow),
§47 (each MCP server owns one namespace; teams.* is the Teams boundary),
§47.6 (security: read-only Stage-1; sending Teams messages is
externally-visible mutation per §42 — needs separate ADR + write surface
analogous to ADR-028 for csv_ingest).

TOOLS (read only)
  teams.channel_list         List channels for the configured team
  teams.message_search       Search recent messages (read; no send)

CONFIG (Microsoft Graph API — bearer token via app registration)
  TEAMS_TENANT_ID            AAD tenant id
  TEAMS_CLIENT_ID            App registration client id
  TEAMS_CLIENT_SECRET        App registration client secret
  TEAMS_TEAM_ID              Default team to list channels for
  When unset → tools return available:False stub (no live calls).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from mcp.server_common import (
    ToolCallRequest,
    build_auth,
    enforce_scope as _enforce_scope_common,
    handle_tool_call,
    mount_metrics_endpoint,
    setup_server_otel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_teams")

app = FastAPI(title="DocuMind MCP — Microsoft Teams server")
setup_server_otel(app, service_name="mcp-server-teams")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


TOOLS: list[dict[str, Any]] = [
    {
        "name": "teams.channel_list",
        "description": "List channels for the configured Teams team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "channels": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["teams:read"],
        "idempotent": True,
    },
    {
        "name": "teams.message_search",
        "description": "Search recent Teams messages by query string (read-only).",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "maxLength": 200},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "messages": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["teams:read"],
        "idempotent": True,
    },
]

_IDEMPOTENCY: dict[str, Any] = {}


def _live_or_stub() -> tuple[bool, str]:
    keys = ("TEAMS_TENANT_ID", "TEAMS_CLIENT_ID", "TEAMS_CLIENT_SECRET")
    if all(os.getenv(k, "").strip() for k in keys):
        return True, ""
    missing = [k for k in keys if not os.getenv(k, "").strip()]
    return False, f"unset env: {missing}"


def _channel_list_impl(args: dict[str, Any]) -> dict[str, Any]:
    live, reason = _live_or_stub()
    if not live:
        return {"channels": [], "available": False, "reason": reason}
    # Stage-1: live wiring deferred — would call Microsoft Graph
    # /teams/{team-id}/channels with bearer token from MSAL flow.
    # Returns available:True + empty list to signal config is complete
    # but the live call hasn't been wired yet (separate iter).
    return {"channels": [], "available": True, "stub": "live_wiring_pending"}


def _message_search_impl(args: dict[str, Any]) -> dict[str, Any]:
    query = args["query"]
    if len(query) > 200:
        raise HTTPException(status_code=400,
                            detail={"code": "query_too_long", "max": 200})
    live, reason = _live_or_stub()
    if not live:
        return {"messages": [], "available": False, "reason": reason}
    return {"messages": [], "available": True, "stub": "live_wiring_pending"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-teams"}


@app.get("/tools/list")
async def tools_list() -> dict[str, Any]:
    return {"tools": TOOLS}


@app.post("/tools/call")
async def tools_call(
    req: ToolCallRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await handle_tool_call(
        req=req, tools=TOOLS, idempotency_key=idempotency_key,
        authorization=authorization, auth_required=_AUTH_REQUIRED,
        verifier=_VERIFIER, idempotency_store=_IDEMPOTENCY,
        dispatch=_dispatch, tracer_module=__name__, logger=log,
        service_label="mcp_teams",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={"code": "upstream_error"})
    try:
        if req.name == "teams.channel_list":
            return _channel_list_impl(req.arguments)
        if req.name == "teams.message_search":
            return _message_search_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]}) from exc
    raise HTTPException(status_code=500, detail={"code": "no_dispatch_for_tool", "name": req.name})
