"""
Google Cloud Platform MCP server — read-only Stage-1 (iter-71 SDLC batch).

Per CLAUDE.md §44 (iter-71; SDLC fleet expansion), §47 (each MCP
server owns ONE namespace; gcp.* is the Google Cloud Platform boundary), §47.6
(read-only Stage-1; write surfaces deferred — Mutating GCP calls need separate ADR per service.).

TOOLS (read only)
  gcp.gce_list_instances    List Compute Engine instances in a project/zone.
  gcp.gcs_list_bucket    List objects in a GCS bucket.

CONFIG
  GOOGLE_APPLICATION_CREDENTIALS
  When unset → tools return available:False stub (no live calls).
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
log = logging.getLogger("mcp.server_gcp")

app = FastAPI(title="DocuMind MCP — Google Cloud Platform server")
setup_server_otel(app, service_name="mcp-server-gcp")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


_QUERY_FORBIDDEN_RE = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|TRUNCATE|EXECUTE|UNION)\b",
    re.IGNORECASE,
)


def _validate_query(q: str) -> str:
    if not isinstance(q, str) or len(q) > 500:
        raise HTTPException(
            status_code=400,
            detail={"code": "query_too_long_or_invalid", "max": 500},
        )
    if _QUERY_FORBIDDEN_RE.search(q):
        raise HTTPException(
            status_code=400,
            detail={"code": "query_forbidden_keyword",
                    "message": "query contains DDL/DML-shaped keyword"},
        )
    return q


TOOLS: list[dict[str, Any]] = [
    {
        "name": "gcp.gce_list_instances",
        "description": 'List Compute Engine instances in a project/zone.',
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 500},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ['gcp:read'],
        "idempotent": True,
    },
    {
        "name": "gcp.gcs_list_bucket",
        "description": 'List objects in a GCS bucket.',
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 500},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ['gcp:read'],
        "idempotent": True,
    },
]

_IDEMPOTENCY: dict[str, Any] = {}


def _live_or_stub() -> tuple[bool, str]:
    keys = ('GOOGLE_APPLICATION_CREDENTIALS',)
    if all(os.getenv(k, "").strip() for k in keys):
        return True, ""
    missing = [k for k in keys if not os.getenv(k, "").strip()]
    return False, f"unset env: {missing}"


def _gce_list_instances_impl(args: dict[str, Any]) -> dict[str, Any]:
    if "query" in args:
        _validate_query(str(args.get("query", "")))
    live, reason = _live_or_stub()
    if not live:
        return {"results": [], "available": False, "reason": reason}
    return {"results": [], "available": True, "stub": "live_wiring_pending"}


def _gcs_list_bucket_impl(args: dict[str, Any]) -> dict[str, Any]:
    if "query" in args:
        _validate_query(str(args.get("query", "")))
    live, reason = _live_or_stub()
    if not live:
        return {"results": [], "available": False, "reason": reason}
    return {"results": [], "available": True, "stub": "live_wiring_pending"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-gcp"}


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
        service_label="mcp_gcp",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={"code": "upstream_error"})
    try:
        if req.name == "gcp.gce_list_instances":
            return _gce_list_instances_impl(req.arguments)
        if req.name == "gcp.gcs_list_bucket":
            return _gcs_list_bucket_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]}) from exc
    raise HTTPException(status_code=500, detail={"code": "no_dispatch_for_tool", "name": req.name})
