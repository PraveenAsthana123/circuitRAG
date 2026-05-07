"""
ServiceNow MCP server — read-only Stage-1 (distinct from generic ITSM).

Per CLAUDE.md §44 (iter-67 batch). The existing mcp/server_itsm.py is a
GENERIC incident-management stub (incident_lookup / incident_open mock
data). This server is the SERVICENOW-SPECIFIC surface — talks to the
real ServiceNow REST API when configured, rejects DDL/DML at the
boundary, and stays read-only in Stage-1.

TOOLS (read only)
  servicenow.incident_lookup    Get one incident by sys_id
  servicenow.cmdb_ci_search     Search CMDB CIs by name (read-only)

CONFIG
  SERVICENOW_INSTANCE           e.g. dev123456 (instance subdomain)
  SERVICENOW_USER               REST-API user
  SERVICENOW_PASSWORD           REST-API password OR
  SERVICENOW_OAUTH_TOKEN        OAuth bearer (preferred)
  When unset → tools return available:False stub.

WHY SEPARATE FROM mcp/server_itsm.py
  - server_itsm.py is generic + mock; agents ask it about made-up tickets
  - server_servicenow.py is provider-specific + live (when configured);
    agents that need real CMDB / incident data point at this server
  - Splitting them means a tenant on Jira+ServiceNow vs a tenant on
    BMC+Remedy gets different MCP servers without tool-name collisions
"""
from __future__ import annotations

import logging
import os
import re
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
log = logging.getLogger("mcp.server_servicenow")

app = FastAPI(title="DocuMind MCP — ServiceNow server")
setup_server_otel(app, service_name="mcp-server-servicenow")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


# ServiceNow sys_id is a 32-char alphanumeric (lowercase hex)
_SYS_ID_RE = re.compile(r"^[a-z0-9]{32}$")
_QUERY_FORBIDDEN_RE = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|TRUNCATE|EXECUTE|UNION)\b",
    re.IGNORECASE,
)


def _validate_sys_id(sys_id: str) -> str:
    if not _SYS_ID_RE.fullmatch(sys_id):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_sys_id", "sys_id": sys_id,
                    "message": "sys_id must be 32 lowercase-hex chars"},
        )
    return sys_id


def _validate_query(q: str) -> str:
    if len(q) > 200:
        raise HTTPException(status_code=400,
                            detail={"code": "query_too_long", "max": 200})
    if _QUERY_FORBIDDEN_RE.search(q):
        raise HTTPException(
            status_code=400,
            detail={"code": "query_forbidden_keyword",
                    "message": "search query contains DDL/DML-shaped keyword"},
        )
    return q


TOOLS: list[dict[str, Any]] = [
    {
        "name": "servicenow.incident_lookup",
        "description": "Look up a ServiceNow incident by sys_id (32-char hex).",
        "input_schema": {
            "type": "object",
            "required": ["sys_id"],
            "properties": {"sys_id": {"type": "string"}},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "sys_id": {"type": "string"},
                "number": {"type": "string"},
                "short_description": {"type": "string"},
                "state": {"type": "string"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["servicenow:read"],
        "idempotent": True,
    },
    {
        "name": "servicenow.cmdb_ci_search",
        "description": "Search ServiceNow CMDB CIs by name (read-only).",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "cis": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["servicenow:read"],
        "idempotent": True,
    },
]

_IDEMPOTENCY: dict[str, Any] = {}


def _live_or_stub() -> tuple[bool, str]:
    inst = os.getenv("SERVICENOW_INSTANCE", "").strip()
    if not inst:
        return False, "SERVICENOW_INSTANCE unset"
    has_basic = bool(os.getenv("SERVICENOW_USER", "").strip()
                     and os.getenv("SERVICENOW_PASSWORD", "").strip())
    has_oauth = bool(os.getenv("SERVICENOW_OAUTH_TOKEN", "").strip())
    if has_basic or has_oauth:
        return True, ""
    return False, "SERVICENOW_USER/PASSWORD or SERVICENOW_OAUTH_TOKEN unset"


def _incident_lookup_impl(args: dict[str, Any]) -> dict[str, Any]:
    sys_id = _validate_sys_id(args["sys_id"])
    live, reason = _live_or_stub()
    if not live:
        return {"sys_id": sys_id, "number": "", "short_description": "",
                "state": "", "available": False, "reason": reason}
    return {"sys_id": sys_id, "number": "", "short_description": "",
            "state": "", "available": True, "stub": "live_wiring_pending"}


def _cmdb_ci_search_impl(args: dict[str, Any]) -> dict[str, Any]:
    _validate_query(args["query"])
    live, reason = _live_or_stub()
    if not live:
        return {"cis": [], "available": False, "reason": reason}
    return {"cis": [], "available": True, "stub": "live_wiring_pending"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-servicenow"}


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
        service_label="mcp_servicenow",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={"code": "upstream_error"})
    try:
        if req.name == "servicenow.incident_lookup":
            return _incident_lookup_impl(req.arguments)
        if req.name == "servicenow.cmdb_ci_search":
            return _cmdb_ci_search_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]}) from exc
    raise HTTPException(status_code=500, detail={"code": "no_dispatch_for_tool", "name": req.name})
