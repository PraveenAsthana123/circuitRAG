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
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_itsm")

app = FastAPI(title="DocuMind MCP — ITSM server")


# ---------------------------------------------------------------------------
# Optional OTel — same pattern as server_hr.py
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def _setup_otel() -> None:
    if not _OTEL_AVAILABLE:
        log.info("mcp_server_itsm_otel_skipped reason=sdk_missing")
        return
    endpoint = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    resource = Resource.create({
        "service.name": "mcp-server-itsm",
        "service.namespace": "documind",
        "deployment.environment": os.getenv("DOCUMIND_ENV", "development"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)),
    )
    _otel_trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    log.info("mcp_server_itsm_otel_initialized endpoint=%s", endpoint)


_setup_otel()


# ---------------------------------------------------------------------------
# Optional JWT scope enforcement — MCP_AUTH_REQUIRED=true
# ---------------------------------------------------------------------------
try:
    import jwt as _pyjwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False


class _TokenVerifier:
    def __init__(self, *, public_key_path: str, issuer: str, audience: str) -> None:
        from pathlib import Path
        self._pub = Path(public_key_path).read_bytes()
        self._iss = issuer
        self._aud = audience

    def verify(self, raw: str) -> dict[str, Any]:
        claims = _pyjwt.decode(
            raw, self._pub,
            algorithms=["RS256"],
            issuer=self._iss,
            audience=self._aud,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        if claims.get("kind") != "access":
            raise _pyjwt.InvalidTokenError(f"wrong token kind: {claims.get('kind')!r}")
        return claims


_AUTH_REQUIRED = os.getenv("MCP_AUTH_REQUIRED", "false").lower() == "true"
_VERIFIER: _TokenVerifier | None = None
if _AUTH_REQUIRED:
    if not _JWT_AVAILABLE:
        raise RuntimeError("MCP_AUTH_REQUIRED=true but PyJWT not installed")
    _VERIFIER = _TokenVerifier(
        public_key_path=os.getenv(
            "MCP_JWT_PUBLIC_KEY_PATH",
            os.getenv(
                "DOCUMIND_JWT_PUBLIC_KEY_PATH",
                "./scripts/dev-keys/jwt-public.pem",
            ),
        ),
        issuer=os.getenv("DOCUMIND_JWT_ISSUER", "documind-local"),
        audience=os.getenv("DOCUMIND_JWT_AUDIENCE", "documind-services"),
    )
    log.info(
        "mcp_itsm_auth_required=true issuer=%s",
        _VERIFIER._iss,
    )


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    if _VERIFIER is None:
        return {}
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"code": "NOT_AUTHENTICATED", "message": "Bearer token required"},
        )
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"code": "NOT_AUTHENTICATED", "message": "malformed Authorization header"},
        )
    try:
        claims = _VERIFIER.verify(parts[1].strip())
    except _pyjwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc
    required = set(tool.get("required_scopes") or [])
    if not required:
        return claims
    have = set(claims.get("roles") or [])
    if required.isdisjoint(have):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_SCOPE",
                "required": sorted(required),
                "have": sorted(have),
                "tool": tool.get("name"),
            },
        )
    return claims


# ---------------------------------------------------------------------------
# In-memory ITSM state
# ---------------------------------------------------------------------------
@dataclass
class ITSMState:
    tickets: dict[str, dict[str, Any]] = field(default_factory=dict)
    idempotency: dict[str, dict[str, Any]] = field(default_factory=dict)


state = ITSMState()


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


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any]
    tenant_id: str | None = None
    correlation_id: str | None = None


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
    cid = req.correlation_id or str(uuid.uuid4())
    log.info(
        "mcp_itsm_tool_called name=%s tenant=%s corr=%s auth=%s",
        req.name, req.tenant_id, cid, "yes" if authorization else "no",
    )

    # Scope before cache (leaked key ≠ replay primitive)
    if _AUTH_REQUIRED:
        tool = next((t for t in TOOLS if t["name"] == req.name), None)
        if tool is None:
            _enforce_scope(authorization, {"name": req.name, "required_scopes": []})
            raise HTTPException(
                status_code=404,
                detail={"code": "tool_not_found", "name": req.name},
            )
        _enforce_scope(authorization, tool)

    tracer = _otel_trace.get_tracer(__name__) if _OTEL_AVAILABLE else None
    span_cm = (
        tracer.start_as_current_span(f"mcp.tool:{req.name}")
        if tracer is not None
        else _NoopCM()
    )

    with span_cm as sp:
        if _OTEL_AVAILABLE and sp is not None:
            sp.set_attribute("mcp.tool.name", req.name)
            if req.tenant_id:
                sp.set_attribute("documind.tenant_id", req.tenant_id)
                sp.set_attribute("mcp.tenant_id", req.tenant_id)
            sp.set_attribute("documind.correlation_id", cid)
            sp.set_attribute("mcp.correlation_id", cid)
            sp.set_attribute("mcp.idempotency_key_present", idempotency_key is not None)

        if idempotency_key and idempotency_key in state.idempotency:
            cached = state.idempotency[idempotency_key]
            log.info("mcp_itsm_idempotent_replay key=%s", idempotency_key)
            if _OTEL_AVAILABLE and sp is not None:
                sp.set_attribute("mcp.idempotent_replay", True)
            return {**cached, "idempotent_replay": True}
        return await _dispatch(req, idempotency_key, cid)


class _NoopCM:
    def __enter__(self): return None
    def __exit__(self, *a): return False


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

        response = {"ok": True, "result": result}
        if idempotency_key:
            state.idempotency[idempotency_key] = response
        return response

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("mcp_itsm_tool_failed name=%s", req.name)
        return {"ok": False, "error": {"code": "internal_error", "message": str(exc)}}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_ITSM_PORT", "8091"))
    uvicorn.run(app, host="127.0.0.1", port=port)
