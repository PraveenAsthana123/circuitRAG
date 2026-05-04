"""MCP server — Paperclip Stage-1 sandbox aggregator.

Exposes the read-only Paperclip aggregator (scripts/paperclip_manager.py)
as standard MCP tools so other agents / services / operator clients can
subscribe to the snapshot through one canonical surface.

Tools:
  * ``paperclip.snapshot`` — full snapshot dict (council_batch,
    apply_attempts, audit_decisions, pending_issues, council_outcomes).
    Read-only; idempotent; required_scopes=["snapshot:read"].
  * ``paperclip.health``   — operator-readable health probe (exists,
    runnable, last-snapshot-age). Read-only; idempotent;
    required_scopes=["snapshot:read"].

Stage-1 contract — drill-locked at multiple boundaries:
  - NO mutating tools (no paperclip.dispatch, paperclip.push,
    paperclip.assign). Every write verb in the runtime aggregator is
    refused with §42 + STAGE_1_READ_ONLY; this server inherits that
    posture by simply not registering write tools.
  - Both registered tools require the ``snapshot:read`` scope, which
    the PolisAI rule ``paperclip-read-snapshot`` grants to the
    ``paperclip:manager`` actor only.
  - Audit row per call lands in the standard MCP audit pipeline +
    .loop/policy_audit.jsonl when PolisAI is wired.

Run:
    MCP_PAPERCLIP_PORT=8099 python mcp/server_paperclip.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
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
log = logging.getLogger("mcp.server_paperclip")

app = FastAPI(title="DocuMind MCP — Paperclip Stage-1 sandbox aggregator")
setup_server_otel(app, service_name="mcp-server-paperclip")
mount_metrics_endpoint(app)

REPO = Path(__file__).resolve().parent.parent
PAPERCLIP_SCRIPT = REPO / "scripts" / "paperclip_manager.py"
PY_BIN = os.getenv("PYTHON_BIN") or sys.executable
DEFAULT_TIMEOUT_S = int(os.getenv("MCP_PAPERCLIP_TIMEOUT_S", "15"))
MAX_CONCURRENT = max(1, int(os.getenv("MCP_PAPERCLIP_MAX_CONCURRENT", "4")))
_SNAPSHOT_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


# ---------------------------------------------------------------------------
# Tool catalog — TWO tools, BOTH read-only.
# Stage-1 contract: do not register any tool with side_effects="write".
# Adding a write tool here is a Stage-2/3 promotion that requires:
#   1. A new PolisAI rule with explicit scope token
#   2. A drill update to lock the new tool's contract
#   3. An ADR documenting why the sandbox boundary moved
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "paperclip.snapshot",
        "description": (
            "Read the Stage-1 sandbox snapshot from the local "
            "paperclip_manager aggregator. Returns council batch + "
            "apply attempts + audit decisions + pending issues + "
            "council outcomes. Includes the §55.3 brutal-honesty signal "
            "(apply_rate)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 90,
                    "default": 7,
                },
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["stage", "version", "council_batch", "apply_attempts"],
            "properties": {
                "stage": {"type": "integer"},
                "version": {"type": "string"},
                "generated_at": {"type": "number"},
                "council_batch": {"type": "object"},
                "apply_attempts": {"type": "object"},
                "audit_decisions": {"type": "array"},
                "pending_issues": {"type": "object"},
                "council_outcomes": {"type": "object"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["snapshot:read"],
        "idempotent": True,
    },
    {
        "name": "paperclip.health",
        "description": (
            "Operator-readable health probe: paperclip_manager.py "
            "present + executable + responds within timeout."
        ),
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {
            "type": "object",
            "required": ["ok", "stage"],
            "properties": {
                "ok": {"type": "boolean"},
                "stage": {"type": "integer"},
                "script_present": {"type": "boolean"},
                "last_snapshot_at": {"type": "number"},
                "snapshot_age_s": {"type": "number"},
                "error": {"type": ["string", "null"]},
            },
        },
        "side_effects": "read",
        "required_scopes": ["snapshot:read"],
        "idempotent": True,
    },
]


def _run_snapshot(window_days: int) -> dict[str, Any]:
    """Invoke paperclip_manager.py snapshot — read-only, ≤15s.

    Distinct from the drill: this is the production hot path; we
    retry-once on a transient timeout and log per-call latency for
    the metrics dashboard.
    """
    started = time.time()
    proc = subprocess.run(
        [PY_BIN, str(PAPERCLIP_SCRIPT), "snapshot",
         "--window-days", str(window_days)],
        capture_output=True, text=True, timeout=DEFAULT_TIMEOUT_S, cwd=REPO,
    )
    elapsed = time.time() - started
    if proc.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "PAPERCLIP_SNAPSHOT_FAILED",
                "message": f"paperclip_manager exited {proc.returncode}",
                "stderr": proc.stderr[:300],
                "elapsed_s": round(elapsed, 2),
            },
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "PAPERCLIP_OUTPUT_NOT_JSON",
                "message": str(exc),
                "stdout_head": proc.stdout[:300],
            },
        ) from exc


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def _handle_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    window_days = int(args.get("window_days", 7))
    if not 1 <= window_days <= 90:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_WINDOW_DAYS",
                "message": "window_days must be in [1, 90]",
            },
        )
    async with _SNAPSHOT_SEMAPHORE:
        # Run blocking subprocess in a thread to keep the event loop hot.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_snapshot, window_days)


async def _handle_health(_args: dict[str, Any]) -> dict[str, Any]:
    health: dict[str, Any] = {
        "ok": True,
        "stage": 1,
        "script_present": PAPERCLIP_SCRIPT.exists(),
        "last_snapshot_at": 0.0,
        "snapshot_age_s": 0.0,
        "error": None,
    }
    if not PAPERCLIP_SCRIPT.exists():
        health["ok"] = False
        health["error"] = f"missing: {PAPERCLIP_SCRIPT}"
        return health
    try:
        async with _SNAPSHOT_SEMAPHORE:
            loop = asyncio.get_event_loop()
            snap = await loop.run_in_executor(None, _run_snapshot, 7)
        health["last_snapshot_at"] = snap.get("generated_at", 0.0)
        health["snapshot_age_s"] = max(
            0.0, time.time() - float(snap.get("generated_at", time.time())),
        )
    except HTTPException as exc:
        health["ok"] = False
        health["error"] = str(exc.detail)
    except Exception as exc:  # noqa: BLE001 — health probe never raises
        health["ok"] = False
        health["error"] = str(exc)[:300]
    return health


HANDLERS = {
    "paperclip.snapshot": _handle_snapshot,
    "paperclip.health": _handle_health,
}


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

@app.get("/v1/tools")
async def list_tools(authorization: str | None = Header(None)) -> dict[str, Any]:
    """List the 2 read-only tools. No auth-scope required for listing."""
    return {"tools": TOOLS}


@app.post("/v1/tools/call")
async def call_tool(
    payload: ToolCallRequest,
    authorization: str | None = Header(None),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Dispatch one tool call. Per §50, stage-1 has 2 read-only tools."""
    tool_name = payload.name
    tool = next((t for t in TOOLS if t["name"] == tool_name), None)
    if tool is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "UNKNOWN_TOOL",
                "message": f"Tool not registered: {tool_name!r}",
                "available": [t["name"] for t in TOOLS],
            },
        )
    _enforce_scope(authorization, tool)
    handler = HANDLERS.get(tool_name)
    if handler is None:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "TOOL_HANDLER_MISSING",
                "message": f"No handler bound for {tool_name!r}",
            },
        )

    # Use the common handle_tool_call wrapper for idempotency + audit.
    return await handle_tool_call(
        tool_name=tool_name,
        args=payload.args or {},
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        handler=handler,
    )


@app.get("/v1/health")
async def health() -> dict[str, Any]:
    """Liveness probe — does NOT call paperclip subprocess.
    Use paperclip.health tool for the deeper readiness check."""
    return {
        "ok": True,
        "service": "mcp-server-paperclip",
        "stage": 1,
        "script_present": PAPERCLIP_SCRIPT.exists(),
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("MCP_PAPERCLIP_PORT", "8099"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # noqa: S104
