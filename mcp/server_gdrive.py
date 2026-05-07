"""
Google Drive MCP server — read-only Stage-1.

Per CLAUDE.md §44 (iter-67 batch), §47 (each MCP server owns one
namespace; gdrive.* is the Google Drive boundary), §47.6 (security:
read-only Stage-1; file-write / share-permission tools need separate
ADR + write surface).

TOOLS (read only)
  gdrive.file_search          Search by query (Google Drive API q-string;
                              keyword-allowlisted to block injection-shaped
                              SQL-like patterns)
  gdrive.file_get_metadata    Get metadata for a file id (no content fetch
                              in Stage-1; that's documents.* for already-
                              downloaded files)

CONFIG (Service-account flow — most common for enterprise)
  GDRIVE_SERVICE_ACCOUNT_KEY   Path to service-account JSON key
                                (or raw JSON in env if path absent)
  GDRIVE_DELEGATED_USER         User email to impersonate (domain-wide delegation)
  When unset → tools return available:False stub.

ID HYGIENE
  Drive file ids are alphanumeric + hyphens + underscores (Google's
  format). Reject anything else at the boundary to prevent injection
  in URL path segments.
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
log = logging.getLogger("mcp.server_gdrive")

app = FastAPI(title="DocuMind MCP — Google Drive server")
setup_server_otel(app, service_name="mcp-server-gdrive")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,200}$")
_QUERY_FORBIDDEN_RE = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|TRUNCATE|EXECUTE|UNION)\b",
    re.IGNORECASE,
)


def _validate_file_id(fid: str) -> str:
    if not _FILE_ID_RE.fullmatch(fid):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_file_id", "id": fid,
                    "message": "file_id must match ^[A-Za-z0-9_-]{1,200}$"},
        )
    return fid


def _validate_query(q: str) -> str:
    if len(q) > 500:
        raise HTTPException(status_code=400,
                            detail={"code": "query_too_long", "max": 500})
    if _QUERY_FORBIDDEN_RE.search(q):
        raise HTTPException(
            status_code=400,
            detail={"code": "query_forbidden_keyword",
                    "message": "query contains DDL/DML-shaped keyword"},
        )
    return q


TOOLS: list[dict[str, Any]] = [
    {
        "name": "gdrive.file_search",
        "description": "Search Google Drive files by query string.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "files": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["gdrive:read"],
        "idempotent": True,
    },
    {
        "name": "gdrive.file_get_metadata",
        "description": "Get metadata for a Google Drive file by id (no content fetch).",
        "input_schema": {
            "type": "object",
            "required": ["file_id"],
            "properties": {"file_id": {"type": "string"}},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "mimeType": {"type": "string"},
                "modifiedTime": {"type": "string"},
                "size": {"type": "integer"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["gdrive:read"],
        "idempotent": True,
    },
]

_IDEMPOTENCY: dict[str, Any] = {}


def _live_or_stub() -> tuple[bool, str]:
    if os.getenv("GDRIVE_SERVICE_ACCOUNT_KEY", "").strip():
        return True, ""
    return False, "GDRIVE_SERVICE_ACCOUNT_KEY unset"


def _file_search_impl(args: dict[str, Any]) -> dict[str, Any]:
    _validate_query(args["query"])
    live, reason = _live_or_stub()
    if not live:
        return {"files": [], "available": False, "reason": reason}
    return {"files": [], "available": True, "stub": "live_wiring_pending"}


def _file_get_metadata_impl(args: dict[str, Any]) -> dict[str, Any]:
    fid = _validate_file_id(args["file_id"])
    live, reason = _live_or_stub()
    if not live:
        return {"id": fid, "name": "", "mimeType": "", "modifiedTime": "",
                "size": 0, "available": False, "reason": reason}
    return {"id": fid, "name": "", "mimeType": "", "modifiedTime": "",
            "size": 0, "available": True, "stub": "live_wiring_pending"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-gdrive"}


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
        service_label="mcp_gdrive",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={"code": "upstream_error"})
    try:
        if req.name == "gdrive.file_search":
            return _file_search_impl(req.arguments)
        if req.name == "gdrive.file_get_metadata":
            return _file_get_metadata_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]}) from exc
    raise HTTPException(status_code=500, detail={"code": "no_dispatch_for_tool", "name": req.name})
