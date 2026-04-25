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

import asyncio
import logging
import os
import re
import select
import signal
import subprocess
import sys
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
# Interpreter resolution order:
#   1. PYTHON_BIN env var — explicit override for ops who pin a specific venv.
#   2. sys.executable — the interpreter THIS server runs under.
# The previous default of ``/tmp/documind-venv/bin/python`` was a host-
# specific path that didn't exist on most boxes. Falling back to
# sys.executable means a properly-installed deployment "just works"
# without anyone having to discover the env var. CI sets PYTHON_BIN
# explicitly when it wants determinism (e.g. comparing two venvs).
PY_BIN = os.getenv("PYTHON_BIN") or sys.executable
DEFAULT_TIMEOUT_S = int(os.getenv("MCP_DRILL_TIMEOUT_S", "180"))
# Hard caps for production hardening. Each cap is independently
# overridable so an operator can tune for a beefy CI box without
# editing source.
#   MCP_DRILL_MAX_CONCURRENT — gate on simultaneous drill.run executions.
#     Drills spawn services + Postgres connections + ports; without a
#     cap a burst of drill.run calls fork-bombs the host. Default 2 is
#     conservative; CI matches scripts/run_drills.py's --parallel.
#   MCP_DRILL_MAX_STDOUT_BYTES — truncate the captured drill stdout
#     before it ever reaches a Python ``bytes`` allocation. A drill
#     printing a megabyte JSON dump can't OOM the runner.
MAX_CONCURRENT_DRILLS = max(1, int(os.getenv("MCP_DRILL_MAX_CONCURRENT", "2")))
MAX_STDOUT_BYTES = max(4_000, int(os.getenv("MCP_DRILL_MAX_STDOUT_BYTES", "65_536")))
_DRILL_RUN_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_DRILLS)
RESOURCE_TAG_RE = re.compile(r"^#\s*RESOURCES\s*:\s*(.+)$", re.MULTILINE)
RESULT_RE = re.compile(r"ALL\s+(\d+)\s+.*STEPS\s+PASSED")
DEFAULT_RESOURCES = ["mcp_hr", "inference", "pg"]

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


# ---------------------------------------------------------------------------
# Idempotency store. Backed by Postgres when DOCUMIND_PG_HOST is set
# (production posture) — durable, coordinated, TTL-purged, with same-
# key-different-payload conflict detection. Falls back to in-memory
# for tests and bare dev runs without Postgres.
#
# The previous module-level ``_IDEMPOTENCY: dict`` was honest dev
# tooling but wedged any deployment that horizontally scaled the
# drill server (a retry routed to a different replica re-executed).
# Migration 007 + mcp/idempotency.py close that gap.
# ---------------------------------------------------------------------------
def _build_idempotency_store():
    """Return a Postgres store if env wires one, else in-memory."""
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
        log.info("mcp_drills_idempotency_store=postgres ttl=%ds", ttl)
        return PostgresIdempotencyStore(dsn, ttl_seconds=ttl)
    log.info("mcp_drills_idempotency_store=in_memory (NOT durable)")
    return InMemoryIdempotencyStore()


_IDEMPOTENCY = _build_idempotency_store()


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
    """
    Spawn a drill subprocess and capture its result.

    Hardening (over the previous ``subprocess.run`` version):
      * **Process group** — the child is the leader of a new process
        group via ``start_new_session=True``. On timeout we
        ``killpg(SIGKILL)`` so any helper processes the drill spawned
        (MCP servers, retrieval-svc replicas) die with the parent
        instead of orphaning.
      * **Stdout cap** — output is read in chunks and truncated at
        ``MAX_STDOUT_BYTES``. A misbehaving drill that prints a
        gigabyte JSON dump can't OOM the runner.
      * **Path injection guard** — ``known`` set is rebuilt on every
        call; only file basenames matching the on-disk catalogue are
        accepted. (Pattern is also enforced upstream by the JSON
        Schema, but defence-in-depth.)
    """
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

    # Popen with new process group so we can SIGKILL the whole tree
    # on timeout. ``start_new_session=True`` is the POSIX way; on
    # Windows this would need ``creationflags=CREATE_NEW_PROCESS_GROUP``
    # but DocuMind is Linux-only.
    proc = subprocess.Popen(  # noqa: S603 — argv list, no shell, name validated above
        [PY_BIN, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    captured = bytearray()
    timed_out = False
    deadline = time.monotonic() + timeout_s
    truncated = False
    # Read with ``select`` so a silent / sleeping child can't block us
    # past the deadline. The previous version used ``proc.stdout.read()``
    # which only returns when the child writes — a drill that runs
    # ``time.sleep(120)`` would block past the timeout entirely. select
    # gives us deadline-honouring poll semantics, and the read is
    # non-blocking on the stdout fd.
    assert proc.stdout is not None  # for type narrowing
    fd = proc.stdout.fileno()
    try:
        while True:
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                timed_out = True
                break
            # Wait up to remaining_time for stdout activity OR child exit.
            # On select timeout, ready=[] and we re-check the deadline.
            ready, _, _ = select.select([fd], [], [], min(remaining_time, 1.0))
            if not ready:
                # Deadline-tick. Check if child exited cleanly with no
                # more output to drain — if so, we're done.
                if proc.poll() is not None:
                    break
                continue
            chunk = os.read(fd, 4096)
            if not chunk:
                # EOF → child closed stdout. Wait for exit (should be
                # imminent) then bail.
                break
            remaining_cap = MAX_STDOUT_BYTES - len(captured)
            if remaining_cap <= 0:
                # Already at the cap. Discard further reads in a tight
                # drain loop so the child's pipe doesn't block — but
                # also bail out fast on timeout while draining.
                truncated = True
                while True:
                    rem = deadline - time.monotonic()
                    if rem <= 0:
                        timed_out = True
                        break
                    rd, _, _ = select.select([fd], [], [], min(rem, 1.0))
                    if not rd:
                        if proc.poll() is not None:
                            break
                        continue
                    if not os.read(fd, 4096):
                        break
                break
            captured.extend(chunk[:remaining_cap])
            if len(chunk) > remaining_cap:
                truncated = True
    except OSError:  # noqa: BLE001 — capture is best-effort; we still need to reap
        pass

    if timed_out or proc.poll() is None:
        # Kill the entire process group — any subprocess the drill
        # spawned (mcp_hr, retrieval-svc, etc.) gets SIGKILL'd too.
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()  # last-ditch direct kill
            proc.wait()

    duration = time.monotonic() - t0
    text = captured.decode(errors="replace")
    m = RESULT_RE.search(text)
    steps = int(m.group(1)) if m else 0
    tail_lines = text.strip().splitlines()[-20:]
    tail = "\n".join(tail_lines)
    if truncated:
        tail = (
            f"[stdout truncated at {MAX_STDOUT_BYTES} bytes]\n" + tail
        )
    if timed_out:
        return {
            "ok": False,
            "exit_code": -2,
            "steps_passed": steps,
            "duration_s": round(duration, 2),
            "tail": tail or f"timeout after {timeout_s}s",
        }
    return {
        "ok": proc.returncode == 0 and bool(m),
        "exit_code": proc.returncode,
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
        idempotency_store=_IDEMPOTENCY,
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
            # Concurrency cap — gate inflight drill.run executions. A
            # burst of calls beyond MAX_CONCURRENT_DRILLS waits at the
            # semaphore; first-in / first-out. ``_run_drill`` is sync
            # (subprocess), so we offload to a thread to avoid blocking
            # the event loop while holding the semaphore.
            async with _DRILL_RUN_SEMAPHORE:
                result = await asyncio.to_thread(_run_drill, name, timeout_s)
        else:  # pragma: no cover
            raise HTTPException(status_code=501, detail={"code": "not_implemented"})
        # handle_tool_call now owns idempotency cache writes — see
        # mcp/server_common.py + mcp/idempotency.py. The dispatch
        # only returns the response; finalize is handled upstream.
        return {"ok": True, "result": result}
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("mcp_drills_tool_failed name=%s", req.name)
        return {"ok": False, "error": {"code": "internal_error", "message": str(exc)}}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_DRILLS_PORT", "8092"))
    uvicorn.run(app, host="127.0.0.1", port=port)
