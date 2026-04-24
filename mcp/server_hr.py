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
# Optional JWT scope enforcement (defence-in-depth).
#
# Turned on with MCP_AUTH_REQUIRED=true. Reads the same RS256 public key
# the rest of the stack validates against (MCP_JWT_PUBLIC_KEY_PATH or
# DOCUMIND_JWT_PUBLIC_KEY_PATH) and, on each /tools/call, verifies the
# caller's token and checks that their `roles` claim covers the tool's
# declared ``required_scopes``.
#
# Off by default so existing drills + dev work without a token. When on,
# the caller-forwarded JWT from inference-svc provides identity and scope.
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
            raw,
            self._pub,
            algorithms=["RS256"],
            issuer=self._iss,
            audience=self._aud,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        if claims.get("kind") != "access":
            raise _pyjwt.InvalidTokenError(
                f"wrong token kind: {claims.get('kind')!r}",
            )
        return claims


_AUTH_REQUIRED = os.getenv("MCP_AUTH_REQUIRED", "false").lower() == "true"
_VERIFIER: _TokenVerifier | None = None
if _AUTH_REQUIRED:
    if not _JWT_AVAILABLE:
        raise RuntimeError(
            "MCP_AUTH_REQUIRED=true but PyJWT is not installed",
        )
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
        "mcp_auth_required=true verifier_ready issuer=%s audience=%s",
        _VERIFIER._iss, _VERIFIER._aud,
    )


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    """
    Validate the caller's JWT and intersect roles with the tool's
    required_scopes. Returns the claims dict on success.
    Raises HTTPException(401|403) on any failure.
    """
    if _VERIFIER is None:
        # MCP_AUTH_REQUIRED=false — skip, return empty claims
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
# OTel — optional. When the SDK + OTLP exporter are present, emit traces
# so the MCP server-side span shows up in the inference-svc → MCP trace
# tree. Kept local to mcp/ (no documind_core import) so this package
# stays consumable by any service that wants it.
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
    """Wire OTel once per process. Silent no-op if SDK isn't installed."""
    if not _OTEL_AVAILABLE:
        log.info("mcp_server_otel_skipped reason=sdk_missing")
        return
    endpoint = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    resource = Resource.create({
        "service.name": "mcp-server-hr",
        "service.namespace": "documind",
        "deployment.environment": os.getenv("DOCUMIND_ENV", "development"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)),
    )
    _otel_trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    log.info("mcp_server_otel_initialized endpoint=%s service=mcp-server-hr", endpoint)


_setup_otel()


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
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    cid = req.correlation_id or str(uuid.uuid4())
    log.info(
        "mcp_tool_called name=%s tenant=%s corr=%s idempotency=%s auth=%s",
        req.name, req.tenant_id, cid, idempotency_key,
        "yes" if authorization else "no",
    )

    # Defence-in-depth scope check BEFORE the idempotency cache check,
    # so a replay still requires the caller to prove they're allowed to
    # see the cached result. (Without this, a leaked idempotency_key
    # would be a replay primitive.)
    if _AUTH_REQUIRED:
        tool = next((t for t in TOOLS if t["name"] == req.name), None)
        if tool is None:
            # Authenticate first (so unknown-name probes get 401 from
            # unauthenticated callers, 404 from authenticated ones —
            # same info-leak logic as the admin API).
            _enforce_scope(authorization, {"name": req.name, "required_scopes": []})
            raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
        _enforce_scope(authorization, tool)

    # Child span named after the tool itself — so Jaeger can filter a
    # trace to a specific tool invocation regardless of which generic
    # POST /tools/call hosted it. FastAPIInstrumentor already gave us
    # the HTTP-level server span; this is a business-level child.
    _tracer = (
        _otel_trace.get_tracer(__name__) if _OTEL_AVAILABLE else None
    )
    _span_cm = (
        _tracer.start_as_current_span(f"mcp.tool:{req.name}")
        if _tracer is not None
        else _NoopCM()
    )

    with _span_cm as _sp:
        if _OTEL_AVAILABLE and _sp is not None:
            _sp.set_attribute("mcp.tool.name", req.name)
            if req.tenant_id:
                # Unified with inference-svc / retrieval-svc so a
                # single Jaeger tag filter (documind.tenant_id=<uuid>)
                # returns every span for that tenant regardless of
                # which service the span came from.
                _sp.set_attribute("documind.tenant_id", req.tenant_id)
                _sp.set_attribute("mcp.tenant_id", req.tenant_id)  # back-compat
            _sp.set_attribute("documind.correlation_id", cid)
            _sp.set_attribute("mcp.correlation_id", cid)  # back-compat
            _sp.set_attribute(
                "mcp.idempotency_key_present", idempotency_key is not None,
            )

        # Idempotency replay
        if idempotency_key and idempotency_key in state.idempotency:
            cached = state.idempotency[idempotency_key]
            log.info("mcp_idempotent_replay key=%s", idempotency_key)
            if _OTEL_AVAILABLE and _sp is not None:
                _sp.set_attribute("mcp.idempotent_replay", True)
            return {**cached, "idempotent_replay": True}
        return await _dispatch(req, idempotency_key, cid)


class _NoopCM:
    def __enter__(self): return None
    def __exit__(self, *a): return False


async def _dispatch(
    req: "ToolCallRequest",
    idempotency_key: str | None,
    cid: str,
) -> dict[str, Any]:
    """Extracted so the span context manager wraps ALL of the work."""

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
