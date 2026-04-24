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
from mcp.server_common import (
    ToolCallRequest,
    build_auth,
    enforce_scope as _enforce_scope_common,
    handle_tool_call,
    mount_metrics_endpoint,
    setup_server_otel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_drills")

app = FastAPI(title="DocuMind MCP — drill runner")
setup_server_otel(app, service_name="mcp-server-drills")
mount_metrics_endpoint(app)

REPO = Path(__file__).resolve().parent.parent
DRILL_DIR = REPO / "mcp" / "tests"
PY_BIN = os.getenv("PYTHON_BIN", "/tmp/documind-venv/bin/python")
DEFAULT_TIMEOUT_S = int(os.getenv("MCP_DRILL_TIMEOUT_S", "180"))
RESOURCE_TAG_RE = re.compile(r"^#\s*RESOURCES\s*:\s*(.+)$", re.MULTILINE)
RESULT_RE = re.compile(r"ALL\s+(\d+)\s+.*STEPS\s+PASSED")
DEFAULT_RESOURCES = ["mcp_hr", "inference", "pg"]

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


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


# ToolCallRequest comes from mcp.server_common


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
    return await handle_tool_call(
        req=req,
        tools=TOOLS,
        idempotency_key=idempotency_key,
        authorization=authorization,
        auth_required=_AUTH_REQUIRED,
        verifier=_VERIFIER,
        idempotency_cache=_IDEMPOTENCY,
        dispatch=_dispatch,
        tracer_module=__name__,
        logger=log,
        service_label="mcp_drills",
    )


async def _dispatch(
    req: ToolCallRequest,
    idempotency_key: str | None,
    cid: str,
) -> dict[str, Any]:
    """Extracted so handle_tool_call can wrap it with span + idempotency."""
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_DRILLS_PORT", "8092"))
    uvicorn.run(app, host="127.0.0.1", port=port)
