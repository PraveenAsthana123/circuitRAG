"""
Third MCP server — exposes the drill runner as tools.

Completes the multi-server pattern + gives an agent (or any MCP
client) programmatic access to "run a drill and report back." Used
by ops scripts, CI, and interactive agents.

Tools:
  * ``drill.list``           — enumerate available drills + resource tags
  * ``drill.run``            — execute one drill, return structured result

Design
------
Reuses the discovery + execution internals from
``scripts/run_drills.py`` via subprocess (same isolation as the
command-line runner). The server itself stays a thin HTTP wrapper;
every real run is a fresh Python process with its own sys.path and
imports, so one drill's import chain can't poison the server.

Security
--------
``drill.run`` is a WRITE action (tool spawns real subprocesses that
read/write live databases, restart MCPs, etc.). When
``MCP_AUTH_REQUIRED=true`` the tool demands ``drill:run`` in the
JWT's ``roles`` claim. ``drill:read`` suffices for ``drill.list``.

Run:
    MCP_DRILLS_PORT=8092 python mcp/server_drills.py
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_drills")

app = FastAPI(title="DocuMind MCP — drill runner")

REPO = Path(__file__).resolve().parent.parent
DRILL_DIR = REPO / "mcp" / "tests"
PY_BIN = os.getenv("PYTHON_BIN", "/tmp/documind-venv/bin/python")
DEFAULT_TIMEOUT_S = int(os.getenv("MCP_DRILL_TIMEOUT_S", "180"))
RESOURCE_TAG_RE = re.compile(r"^#\s*RESOURCES\s*:\s*(.+)$", re.MULTILINE)
RESULT_RE = re.compile(r"ALL\s+(\d+)\s+.*STEPS\s+PASSED")
DEFAULT_RESOURCES = ["mcp_hr", "inference", "pg"]


# ---------------------------------------------------------------------------
# Optional OTel (same pattern as server_hr / server_itsm)
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def _setup_otel() -> None:
    if not _OTEL_AVAILABLE:
        return
    endpoint = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    resource = Resource.create({
        "service.name": "mcp-server-drills",
        "service.namespace": "documind",
        "deployment.environment": os.getenv("DOCUMIND_ENV", "development"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)),
    )
    _otel_trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    log.info("mcp_server_drills_otel_initialized endpoint=%s", endpoint)


_setup_otel()


# ---------------------------------------------------------------------------
# Optional JWT (same scaffolding as server_hr / server_itsm)
# ---------------------------------------------------------------------------
try:
    import jwt as _pyjwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False


class _TokenVerifier:
    def __init__(self, *, public_key_path: str, issuer: str, audience: str) -> None:
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
    log.info("mcp_drills_auth_required=true issuer=%s", _VERIFIER._iss)


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
    if required and required.isdisjoint(set(claims.get("roles") or [])):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_SCOPE",
                "required": sorted(required),
                "have": sorted(claims.get("roles") or []),
                "tool": tool.get("name"),
            },
        )
    return claims


# ---------------------------------------------------------------------------
# Idempotency (thin; drill.run is the only write-side tool)
# ---------------------------------------------------------------------------
_IDEMPOTENCY: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Tool catalog
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "drill.list",
        "description": "Enumerate available drills and their resource tags.",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {
            "type": "object",
            "required": ["drills"],
            "properties": {
                "drills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "resources": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        },
        "side_effects": "read",
        "required_scopes": ["drill:read"],
        "idempotent": True,
    },
    {
        "name": "drill.run",
        "description": "Run a single drill. Returns ok + steps_passed + duration_s + exit_code + tail.",
        "input_schema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "pattern": r"^drill_[A-Za-z0-9_]+$"},
                "timeout_s": {"type": "integer", "minimum": 10, "maximum": 600},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["ok", "exit_code"],
            "properties": {
                "ok": {"type": "boolean"},
                "exit_code": {"type": "integer"},
                "steps_passed": {"type": "integer"},
                "duration_s": {"type": "number"},
                "tail": {"type": "string"},
            },
        },
        "side_effects": "write",
        "required_scopes": ["drill:run"],
        "idempotent": True,  # cached via Idempotency-Key; drills themselves are NOT idempotent
    },
]


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any]
    tenant_id: str | None = None
    correlation_id: str | None = None


# ---------------------------------------------------------------------------
# Discovery + execution helpers
# ---------------------------------------------------------------------------
def _discover_drills() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not DRILL_DIR.exists():
        return out
    for path in sorted(DRILL_DIR.glob("drill_*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = RESOURCE_TAG_RE.search(text)
        if m:
            tokens = [t.strip() for t in m.group(1).split() if t.strip()]
            if tokens == ["none"] or tokens == ["readonly"]:
                resources: list[str] = []
            else:
                resources = sorted(tokens)
        else:
            resources = list(DEFAULT_RESOURCES)
        out.append({"name": path.stem, "resources": resources})
    return out


def _run_drill(name: str, timeout_s: int) -> dict[str, Any]:
    # Only allow names from the discovered list — no arbitrary path
    # injection even with pattern validation above.
    known = {d["name"] for d in _discover_drills()}
    if name not in known:
        return {
            "ok": False,
            "exit_code": -1,
            "steps_passed": 0,
            "duration_s": 0.0,
            "tail": f"unknown drill: {name}",
        }
    path = DRILL_DIR / f"{name}.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [PY_BIN, str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": -2,
            "steps_passed": 0,
            "duration_s": timeout_s,
            "tail": (exc.stdout or b"").decode(errors="replace")[-4000:] or "timeout",
        }
    duration = time.monotonic() - t0
    text = result.stdout.decode(errors="replace")
    m = RESULT_RE.search(text)
    steps = int(m.group(1)) if m else 0
    tail = "\n".join(text.strip().splitlines()[-20:])
    return {
        "ok": result.returncode == 0 and bool(m),
        "exit_code": result.returncode,
        "steps_passed": steps,
        "duration_s": round(duration, 2),
        "tail": tail,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-drills"}


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
        "mcp_drills_tool_called name=%s corr=%s auth=%s",
        req.name, cid, "yes" if authorization else "no",
    )

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
            sp.set_attribute("documind.correlation_id", cid)

        if idempotency_key and idempotency_key in _IDEMPOTENCY:
            cached = _IDEMPOTENCY[idempotency_key]
            return {**cached, "idempotent_replay": True}

        tool = next((t for t in TOOLS if t["name"] == req.name), None)
        if tool is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "tool_not_found", "name": req.name},
            )

        try:
            if req.name == "drill.list":
                result = {"drills": _discover_drills()}
            elif req.name == "drill.run":
                name = req.arguments.get("name")
                if not name:
                    return {"ok": False, "error": {"code": "missing_arg", "arg": "name"}}
                timeout_s = int(req.arguments.get("timeout_s", DEFAULT_TIMEOUT_S))
                if _OTEL_AVAILABLE and sp is not None:
                    sp.set_attribute("drill.name", name)
                    sp.set_attribute("drill.timeout_s", timeout_s)
                result = _run_drill(name, timeout_s)
            else:  # pragma: no cover
                raise HTTPException(status_code=501, detail={"code": "not_implemented"})
            response = {"ok": True, "result": result}
            if idempotency_key:
                _IDEMPOTENCY[idempotency_key] = response
            return response
        except HTTPException:
            raise
        except Exception as exc:
            log.exception("mcp_drills_tool_failed name=%s", req.name)
            return {"ok": False, "error": {"code": "internal_error", "message": str(exc)}}


class _NoopCM:
    def __enter__(self): return None
    def __exit__(self, *a): return False


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_DRILLS_PORT", "8092"))
    uvicorn.run(app, host="127.0.0.1", port=port)
