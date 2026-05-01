"""MCP observe server (D3 stub).

Hosts observe.prom_query + observe.compute_p95_delta + observe.check_alerts_fired.
Today returns canned metrics; real Prometheus + Loki integration is a
follow-up commit. ObserverAgent's two-signal rollback rule (§47.7) works
against this server's canned data so the e2e pipeline drill can verify
the rollback path.

Run:
    MCP_OBSERVE_PORT=8097 python mcp/server_observe.py
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_observe")

app = FastAPI(title="DocuMind MCP — Observe server (D3 stub)")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "observe.prom_query",
        "description": "Query Prometheus for a metric over a window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "window_seconds": {"type": "integer", "default": 300},
            },
            "required": ["query"],
        },
        "required_scopes": ["observe:read"],
    },
    {
        "name": "observe.compute_p95_delta",
        "description": "Compute p95 latency delta vs baseline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "baseline_window_seconds": {"type": "integer", "default": 3600},
                "compare_window_seconds": {"type": "integer", "default": 300},
            },
            "required": ["service"],
        },
        "required_scopes": ["observe:read"],
    },
    {
        "name": "observe.check_alerts_fired",
        "description": "Count alertmanager alerts fired in a window.",
        "input_schema": {
            "type": "object",
            "properties": {"window_seconds": {"type": "integer", "default": 300}},
        },
        "required_scopes": ["observe:read"],
    },
]


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    tenant_id: str | None = None
    correlation_id: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-observe", "stub": "true"}


@app.get("/tools/list")
async def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest) -> dict[str, Any]:
    if req.name == "observe.prom_query":
        q = str(req.arguments.get("query", ""))
        return {
            "ok": True,
            "data": {"query": q, "samples": [], "stub": True},
        }
    if req.name == "observe.compute_p95_delta":
        return {
            "ok": True,
            "data": {
                "service": req.arguments.get("service"),
                "p95_baseline_ms": 100,
                "p95_observed_ms": 110,
                "delta_pct": 10.0,
                "stub": True,
            },
        }
    if req.name == "observe.check_alerts_fired":
        return {
            "ok": True,
            "data": {"alerts_fired": 0, "alerts": [], "stub": True},
        }
    return {
        "ok": False,
        "error": {"code": "tool_not_found", "name": req.name},
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("MCP_OBSERVE_PORT", "8097"))
    uvicorn.run(app, host="0.0.0.0", port=port)
