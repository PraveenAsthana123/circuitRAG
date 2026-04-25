"""
Second MCP server — IT service management.

Proves the multi-server pattern: same contract, different namespace,
independent scope enforcement. Shares no code with ``server_hr.py``
by design — the ``mcp/`` package's promise is that a tool server
is standalone (no ``documind_core`` import). Duplicating the ~60
lines of OTel + JWT setup is a conscious "duplicate first, refactor
if a third server arrives" choice. A future ``mcp/server_common.py``
can factor out the shared bits.

Tools:
  * ``itsm.incident_lookup`` — read a ticket by id (``itsm:read``)
  * ``itsm.incident_open`` — create a new ticket (``itsm:write``)

Run:
    MCP_ITSM_PORT=8091 python mcp/server_itsm.py
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
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
log = logging.getLogger("mcp.server_itsm")

app = FastAPI(title="DocuMind MCP — ITSM server")
setup_server_otel(app, service_name="mcp-server-itsm")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


# ---------------------------------------------------------------------------
# In-memory ITSM state
# ---------------------------------------------------------------------------
@dataclass
class ITSMState:
    tickets: dict[str, dict[str, Any]] = field(default_factory=dict)


state = ITSMState()


def _build_idempotency_store():
    """Postgres-backed when DOCUMIND_PG_HOST is set; in-memory otherwise."""
    from mcp.idempotency import (
        InMemoryIdempotencyStore,
        PostgresIdempotencyStore,
    )

    pg_host = os.getenv("DOCUMIND_PG_HOST", "").strip()
    if pg_host and os.getenv("MCP_IDEMPOTENCY_DURABLE", "true").lower() == "true":
        dsn = (
            f"postgresql://{os.getenv('DOCUMIND_PG_USER', 'documind_app')}:"
            f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind_app')}@"
            f"{pg_host}:{os.getenv('DOCUMIND_PG_PORT', '5432')}/"
            f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
        )
        ttl = int(os.getenv("MCP_IDEMPOTENCY_TTL_S", "86400"))
        log.info("mcp_itsm_idempotency_store=postgres ttl=%ds", ttl)
        return PostgresIdempotencyStore(dsn, ttl_seconds=ttl)
    log.info("mcp_itsm_idempotency_store=in_memory (NOT durable)")
    return InMemoryIdempotencyStore()


_IDEMPOTENCY = _build_idempotency_store()


# ---------------------------------------------------------------------------
# Tool catalog
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "itsm.incident_lookup",
        "description": "Look up an existing ITSM incident by ticket id.",
        "input_schema": {
            "type": "object",
            "required": ["incident_id"],
            "properties": {
                "incident_id": {"type": "string", "pattern": "^ITSM-[A-F0-9]{8}$"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["incident_id", "status"],
            "properties": {
                "incident_id": {"type": "string"},
                "status": {"type": "string"},
                "title": {"type": "string"},
                "priority": {"type": "string"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["itsm:read"],
        "idempotent": True,
    },
    {
        "name": "itsm.incident_open",
        "description": "Open a new ITSM incident on behalf of an employee.",
        "input_schema": {
            "type": "object",
            "required": ["title", "description"],
            "properties": {
                "title": {"type": "string", "maxLength": 200},
                "description": {"type": "string", "maxLength": 4000},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
                "reporter_employee_id": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["incident_id", "status"],
            "properties": {
                "incident_id": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        "side_effects": "write",
        "required_scopes": ["itsm:write"],
        "idempotent": True,
    },
]


# ToolCallRequest comes from mcp.server_common


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-itsm"}


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
        req=req,
        tools=TOOLS,
        idempotency_key=idempotency_key,
        authorization=authorization,
        auth_required=_AUTH_REQUIRED,
        verifier=_VERIFIER,
        idempotency_store=_IDEMPOTENCY,
        dispatch=_dispatch,
        tracer_module=__name__,
        logger=log,
        service_label="mcp_itsm",
    )


async def _dispatch(
    req: ToolCallRequest,
    idempotency_key: str | None,
    cid: str,
) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "tool_not_found", "name": req.name},
        )
    if os.getenv("MCP_INJECT_FAIL") == "1":
        log.warning("mcp_itsm_inject_fail active — returning 502")
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": "ITSM system unavailable"},
        )

    try:
        if req.name == "itsm.incident_lookup":
            incident_id = req.arguments.get("incident_id", "")
            record = state.tickets.get(incident_id)
            if record is None:
                return {"ok": False, "error": {"code": "incident_not_found", "message": incident_id}}
            result = {
                "incident_id": incident_id,
                "status": record["status"],
                "title": record["title"],
                "priority": record["priority"],
            }
        elif req.name == "itsm.incident_open":
            incident_id = f"ITSM-{uuid.uuid4().hex[:8].upper()}"
            record = {
                "title": req.arguments["title"],
                "description": req.arguments["description"],
                "priority": req.arguments.get("priority", "normal"),
                "reporter_employee_id": req.arguments.get("reporter_employee_id", ""),
                "status": "open",
                "created_at": time.time(),
                "correlation_id": cid,
                "tenant_id": req.tenant_id,
            }
            state.tickets[incident_id] = record
            result = {"incident_id": incident_id, "status": "open"}
        else:  # pragma: no cover
            raise HTTPException(status_code=501, detail={"code": "not_implemented"})

        # Idempotency cache writes owned by handle_tool_call.
        return {"ok": True, "result": result}

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("mcp_itsm_tool_failed name=%s", req.name)
        return {"ok": False, "error": {"code": "internal_error", "message": str(exc)}}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_ITSM_PORT", "8091"))
    uvicorn.run(app, host="127.0.0.1", port=port)
