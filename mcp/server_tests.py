"""MCP tests server (E2: real ruff backing + stubbed pytest/jest/mypy).

E2 wires tests.run_ruff to a real subprocess `ruff check --output-format=json`
with security guards. pytest / jest / mypy remain stubbed for now —
they need a sandboxed execution environment (pytest in particular
imports user code; mypy walks the import graph). Ruff is read-only,
deterministic, and produces structured JSON output, so it's the safest
'real' tool to wire first.

Security guards on tests.run_ruff:
  - argv built as list, NEVER shell=True
  - target path validated:
      * must be a non-empty string
      * must resolve under ALLOWED_TARGET_ROOTS (env-driven; default
        the repo root)
      * symlinks resolved before the prefix check
  - 60s hard timeout
  - ruff binary resolved via shutil.which OR explicit env path

Run:
    MCP_TESTS_PORT=8095 \
    MCP_TESTS_TARGET_ROOT=/mnt/deepa/rag \
    python mcp/server_tests.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_tests")


# P0 #34: track in-flight subprocesses so SIGTERM can clean them up.
# Without this, ruff/pytest/mypy children outlive uvicorn after a kill,
# eventually exhausting OS file descriptors over many restart cycles.
_ACTIVE_PROCS: set[asyncio.subprocess.Process] = set()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    # Shutdown: kill any in-flight subprocesses + wait for cleanup.
    log.info("mcp_tests_shutdown active_procs=%d", len(_ACTIVE_PROCS))
    for proc in list(_ACTIVE_PROCS):
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # already gone
    # Give subprocess.kill() a moment to propagate; bounded wait.
    await asyncio.gather(
        *[p.wait() for p in _ACTIVE_PROCS if p.returncode is None],
        return_exceptions=True,
    )
    _ACTIVE_PROCS.clear()


app = FastAPI(title="DocuMind MCP — Tests server (E2)", lifespan=_lifespan)


# Where the operator allows tools to scan. Env override:
#   MCP_TESTS_TARGET_ROOT=/abs/path1:/abs/path2
_DEFAULT_ROOT = "/mnt/deepa/rag"
ALLOWED_TARGET_ROOTS: list[Path] = [
    Path(p).resolve()
    for p in (os.environ.get("MCP_TESTS_TARGET_ROOT") or _DEFAULT_ROOT).split(":")
    if p.strip()
]


def _resolve_ruff_path() -> str | None:
    """Locate the ruff binary. Env override → PATH → known venv."""
    explicit = os.environ.get("RUFF_PATH")
    if explicit and os.path.exists(explicit):
        return explicit
    found = shutil.which("ruff")
    if found:
        return found
    fallback = "/mnt/deepa/rag/.venv/bin/ruff"
    if os.path.exists(fallback):
        return fallback
    return None


def _resolve_pytest_path() -> str | None:
    explicit = os.environ.get("PYTEST_PATH")
    if explicit and os.path.exists(explicit):
        return explicit
    found = shutil.which("pytest")
    if found:
        return found
    fallback = "/mnt/deepa/rag/.venv/bin/pytest"
    if os.path.exists(fallback):
        return fallback
    return None


def _resolve_mypy_path() -> str | None:
    explicit = os.environ.get("MYPY_PATH")
    if explicit and os.path.exists(explicit):
        return explicit
    found = shutil.which("mypy")
    if found:
        return found
    fallback = "/mnt/deepa/rag/.venv/bin/mypy"
    if os.path.exists(fallback):
        return fallback
    return None


def _validate_target(raw: str) -> Path | None:
    """Resolve `raw` and confirm it's under one of ALLOWED_TARGET_ROOTS.

    Returns the resolved Path on success, None if invalid (caller maps
    to error envelope). Symlinks are resolved before the prefix check
    so a symlink ↦ outside-the-root cannot escape.
    """
    if not raw or not isinstance(raw, str):
        return None
    candidate = Path(raw).resolve()
    if not candidate.exists():
        return None
    for root in ALLOWED_TARGET_ROOTS:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    return None


TOOLS: list[dict[str, Any]] = [
    {
        "name": "tests.run_pytest",
        "description": ("Run `pytest --collect-only` against validated target. REAL backing — "
                        "collect-only is read-only (lists tests without running them); "
                        "full execution is a follow-up commit with sandboxing."),
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]},
        "required_scopes": ["tests:run"],
    },
    {
        "name": "tests.run_jest", "description": "Run jest. Currently STUBBED.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]},
        "required_scopes": ["tests:run"],
    },
    {
        "name": "tests.run_ruff",
        "description": "Run ruff lint with --output-format=json on validated target. REAL backing.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]},
        "required_scopes": ["tests:run"],
    },
    {
        "name": "tests.run_mypy",
        "description": "Run `mypy --no-error-summary` against validated target. REAL backing.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]},
        "required_scopes": ["tests:run"],
    },
]


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    tenant_id: str | None = None
    correlation_id: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-tests", "stub": "partial",
            "ruff_real": "true" if _resolve_ruff_path() else "false"}


@app.get("/tools/list")
async def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


async def _run_ruff(target: Path) -> dict[str, Any]:
    """Run ruff check with structured JSON output. Returns the
    {ok, data, error} envelope expected by ToolCallResponse."""
    ruff = _resolve_ruff_path()
    if ruff is None:
        return {
            "ok": False,
            "error": {"code": "ruff_not_installed",
                      "message": "ruff binary not found; set RUFF_PATH or install ruff"},
        }

    argv = [ruff, "check", "--output-format=json", "--exit-zero", str(target)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _ACTIVE_PROCS.add(proc)
    except (FileNotFoundError, PermissionError) as fnf:
        return {
            "ok": False,
            "error": {"code": "ruff_exec_failed", "message": str(fnf)},
        }

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=60.0)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "ok": False,
            "error": {"code": "ruff_timeout", "message": "ruff exceeded 60s"},
        }

    _ACTIVE_PROCS.discard(proc)
    _ACTIVE_PROCS.discard(proc)
    raw = (stdout_b or b"").decode("utf-8", errors="replace").strip()
    stderr_text = (stderr_b or b"").decode("utf-8", errors="replace")

    findings: list[dict[str, Any]] = []
    if raw:
        try:
            findings = json.loads(raw)
            if not isinstance(findings, list):
                findings = []
        except json.JSONDecodeError:
            findings = []

    failed_summary = [
        {
            "test": f.get("code") or f.get("rule") or "unknown",
            "error": f.get("message") or "",
            "file": f.get("filename"),
            "line": (f.get("location") or {}).get("row"),
        }
        for f in findings
    ]

    return {
        "ok": True,
        "data": {
            "runner": "ruff",
            "passed": len(findings) == 0,
            "failed": failed_summary,
            "coverage_pct": None,
            "log_tail": stderr_text[-500:],
            "stub": False,
            "real_backing": "ruff",
            "findings_count": len(findings),
        },
    }



async def _run_pytest_collect(target: Path) -> dict[str, Any]:
    """Run pytest in collect-only mode. Read-only listing of tests.

    Side effect: pytest imports modules during collection. Operator-
    controlled target is validated by _validate_target. 60s timeout.
    """
    pytest_bin = _resolve_pytest_path()
    if pytest_bin is None:
        return {
            "ok": False,
            "error": {"code": "pytest_not_installed",
                      "message": "pytest binary not found; set PYTEST_PATH"},
        }
    argv = [pytest_bin, "--collect-only", "-q", "--no-header", str(target)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _ACTIVE_PROCS.add(proc)
    except (FileNotFoundError, PermissionError) as fnf:
        return {"ok": False, "error": {"code": "pytest_exec_failed", "message": str(fnf)}}
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=60.0)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        _ACTIVE_PROCS.discard(proc)
        return {"ok": False, "error": {"code": "pytest_timeout", "message": "collect-only > 60s"}}
    _ACTIVE_PROCS.discard(proc)
    raw = (stdout_b or b"").decode("utf-8", errors="replace")
    stderr_text = (stderr_b or b"").decode("utf-8", errors="replace")
    node_lines = [
        ln.strip()
        for ln in raw.splitlines()
        if ln.strip() and "::" in ln and "tests collected" not in ln.lower()
    ]
    summary_match = next(
        (ln for ln in raw.splitlines() if "tests collected" in ln.lower()),
        None,
    )
    return {
        "ok": True,
        "data": {
            "runner": "pytest",
            "mode": "collect-only",
            "passed": True,
            "failed": [],
            "collected_count": len(node_lines),
            "collected_tests": node_lines[:200],
            "summary": summary_match.strip() if summary_match else None,
            "log_tail": stderr_text[-500:],
            "stub": False,
            "real_backing": "pytest",
        },
    }


async def _run_mypy(target: Path) -> dict[str, Any]:
    """Run mypy --no-error-summary against validated target."""
    mypy_bin = _resolve_mypy_path()
    if mypy_bin is None:
        return {
            "ok": False,
            "error": {"code": "mypy_not_installed",
                      "message": "mypy binary not found; set MYPY_PATH"},
        }
    argv = [mypy_bin, "--no-error-summary", "--show-error-codes",
            "--ignore-missing-imports", str(target)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _ACTIVE_PROCS.add(proc)
    except (FileNotFoundError, PermissionError) as fnf:
        return {"ok": False, "error": {"code": "mypy_exec_failed", "message": str(fnf)}}
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=120.0)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        _ACTIVE_PROCS.discard(proc)
        return {"ok": False, "error": {"code": "mypy_timeout", "message": "mypy > 120s"}}
    _ACTIVE_PROCS.discard(proc)
    raw = (stdout_b or b"").decode("utf-8", errors="replace")
    error_lines = [ln for ln in raw.splitlines() if ": error:" in ln]
    failed = [
        {
            "test": ln.split("[")[-1].rstrip("]").strip() if "[" in ln else "type-error",
            "error": ln.split("error:", 1)[-1].strip(),
            "file": ln.split(":", 1)[0],
            "line": (ln.split(":", 2)[1] if ln.count(":") >= 2 else None),
        }
        for ln in error_lines
    ]
    return {
        "ok": True,
        "data": {
            "runner": "mypy",
            "passed": len(error_lines) == 0,
            "failed": failed,
            "coverage_pct": None,
            "log_tail": raw[-500:],
            "stub": False,
            "real_backing": "mypy",
            "findings_count": len(error_lines),
        },
    }


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest) -> dict[str, Any]:
    runner_map = {
        "tests.run_pytest": "pytest",
        "tests.run_jest": "jest",
        "tests.run_ruff": "ruff",
        "tests.run_mypy": "mypy",
    }
    runner = runner_map.get(req.name)
    if runner is None:
        return {
            "ok": False,
            "error": {"code": "tool_not_found", "name": req.name},
        }
    target_raw = str(req.arguments.get("target", "")).strip()
    if not target_raw:
        return {
            "ok": False,
            "error": {"code": "invalid_input", "message": "target is required"},
        }

    # E2/E5: real backings for ruff, pytest (collect-only), mypy.
    # jest stays stubbed — Node toolchain isn't bundled with the
    # service container.
    if runner in ("ruff", "pytest", "mypy"):
        validated = _validate_target(target_raw)
        if validated is None:
            return {
                "ok": False,
                "error": {
                    "code": "target_not_allowed",
                    "message": (
                        f"target {target_raw!r} does not exist or is outside "
                        f"ALLOWED_TARGET_ROOTS={[str(r) for r in ALLOWED_TARGET_ROOTS]}"
                    ),
                },
            }
        if runner == "ruff":
            return await _run_ruff(validated)
        if runner == "pytest":
            return await _run_pytest_collect(validated)
        if runner == "mypy":
            return await _run_mypy(validated)

    # jest only — stays stubbed.
    return {
        "ok": True,
        "data": {
            "runner": runner,
            "passed": True,
            "failed": [],
            "coverage_pct": None,
            "log_tail": f"[STUB] {runner} did not actually run; returning canned pass.",
            "stub": True,
        },
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("MCP_TESTS_PORT", "8095"))
    uvicorn.run(app, host="0.0.0.0", port=port)
