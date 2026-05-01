"""MCP tests server (D3 stub).

Hosts tests.run_pytest + tests.run_jest + tests.run_ruff + tests.run_mypy.
Today returns canned passed=true; real subprocess execution lands in a
follow-up commit. The HTTP shape stabilises from this commit onward.

Run:
    MCP_TESTS_PORT=8095 python mcp/server_tests.py
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_tests")

app = FastAPI(title="DocuMind MCP — Tests server (D3 stub)")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "tests.run_pytest", "description": "Run pytest on the worker output.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]},
        "required_scopes": ["tests:run"],
    },
    {
        "name": "tests.run_jest", "description": "Run jest on the worker output.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]},
        "required_scopes": ["tests:run"],
    },
    {
        "name": "tests.run_ruff", "description": "Run ruff lint on the diff.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}},
                         "required": ["target"]},
        "required_scopes": ["tests:run"],
    },
    {
        "name": "tests.run_mypy", "description": "Run mypy type-check.",
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
    return {"status": "ok", "service": "mcp-server-tests", "stub": "true"}


@app.get("/tools/list")
async def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


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
    target = str(req.arguments.get("target", "")).strip()
    if not target:
        return {
            "ok": False,
            "error": {"code": "invalid_input", "message": "target is required"},
        }
    # Canned: passed=True. Real subprocess invocation in follow-up.
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
