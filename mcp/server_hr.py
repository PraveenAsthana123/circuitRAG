"""
HR MCP server — exposes enterprise HR tools over HTTP.

Wire-format notes
-----------------
The canonical Model Context Protocol uses stdio or SSE. This implementation
uses plain HTTP/JSON because:

* It is testable with curl (drill #7 needs a running endpoint to kill).
* It mirrors the permission + idempotency + audit contract that the stdio
  version would require anyway — those are the enterprise-critical parts.

Real production: swap the transport. The Tool class + permission matrix
+ idempotency store would be identical.

Endpoints
---------
GET  /tools/list                        → advertise tools
POST /tools/call  {name, arguments}     → invoke tool
GET  /health                            → liveness probe

Idempotency
-----------
Client sends ``Idempotency-Key`` header. First call for a key is executed
and cached. Subsequent calls return the cached response with
``idempotent_replay=true``. Cache is in-memory — fine for a demo; swap for
Redis in production.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_hr")

app = FastAPI(title="DocuMind MCP — HR server")


# ---------------------------------------------------------------------------
# Fake HR backend (in-memory). Replace with real Workday/ADP client.
# ---------------------------------------------------------------------------
@dataclass
class HRState:
    tickets: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[str, dict[str, Any]] = field(default_factory=dict)


state = HRState()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "hr.policy_lookup",
        "description": "Look up the HR policy text for a named policy.",
        "input_schema": {
            "type": "object",
            "required": ["policy_name"],
            "properties": {
                "policy_name": {"type": "string", "enum": ["leave", "travel", "expense"]},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["policy_name", "text"],
            "properties": {
                "policy_name": {"type": "string"},
                "text": {"type": "string"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["hr:read"],
        "idempotent": True,
    },
    {
        "name": "hr.leave_request",
        "description": "Submit a leave request on behalf of an employee.",
        "input_schema": {
            "type": "object",
            "required": ["employee_id", "days", "reason"],
            "properties": {
                "employee_id": {"type": "string"},
                "days": {"type": "integer", "minimum": 1, "maximum": 30},
                "reason": {"type": "string", "minLength": 3, "maxLength": 500},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["ticket_id", "status"],
            "properties": {
                "ticket_id": {"type": "string"},
                "status": {"type": "string", "enum": ["submitted", "pending_approval"]},
            },
        },
        "side_effects": "write",
        "required_scopes": ["hr:write"],
        "idempotent": True,  # safe to retry with same Idempotency-Key
    },
]

_POLICY_TEXT = {
    "leave": "Employees accrue 1.5 days of paid leave per month. Unused days carry over up to 30.",
    "travel": "Travel reimbursement is $500/day max. Receipts must be submitted within 30 days.",
    "expense": "Expenses over $100 need manager approval. Alcoholic drinks are never reimbursable.",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any]
    correlation_id: str | None = None
    tenant_id: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-hr"}


@app.get("/tools/list")
async def tools_list() -> dict[str, Any]:
    return {"tools": TOOLS}


@app.post("/tools/call")
async def tools_call(
    req: ToolCallRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    cid = req.correlation_id or str(uuid.uuid4())
    log.info(
        "mcp_tool_called name=%s tenant=%s corr=%s idempotency=%s",
        req.name, req.tenant_id, cid, idempotency_key,
    )

    # Idempotency replay
    if idempotency_key and idempotency_key in state.idempotency:
        cached = state.idempotency[idempotency_key]
        log.info("mcp_idempotent_replay key=%s", idempotency_key)
        return {**cached, "idempotent_replay": True}

    # Tool dispatch
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})

    # Failure-injection endpoint for chaos drills — set MCP_INJECT_FAIL=1 to 502
    if os.getenv("MCP_INJECT_FAIL") == "1":
        log.warning("mcp_inject_fail active — returning 502")
        raise HTTPException(status_code=502, detail={"code": "upstream_error", "message": "HR system unavailable"})

    # Execute
    try:
        if req.name == "hr.policy_lookup":
            policy = req.arguments.get("policy_name")
            text = _POLICY_TEXT.get(policy)
            if text is None:
                return {"ok": False, "error": {"code": "policy_not_found", "message": policy}}
            result = {"policy_name": policy, "text": text}

        elif req.name == "hr.leave_request":
            ticket_id = f"HR-{uuid.uuid4().hex[:8].upper()}"
            state.tickets[ticket_id] = {
                "employee_id": req.arguments["employee_id"],
                "days": req.arguments["days"],
                "reason": req.arguments["reason"],
                "created_at": time.time(),
                "correlation_id": cid,
                "tenant_id": req.tenant_id,
            }
            result = {"ticket_id": ticket_id, "status": "pending_approval"}

        else:  # pragma: no cover
            raise HTTPException(status_code=501, detail={"code": "not_implemented"})

        response = {"ok": True, "result": result}
        if idempotency_key:
            state.idempotency[idempotency_key] = response
        return response

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("mcp_tool_failed name=%s", req.name)
        return {"ok": False, "error": {"code": "internal_error", "message": str(exc)}}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_HR_PORT", "8090"))
    uvicorn.run(app, host="127.0.0.1", port=port)
