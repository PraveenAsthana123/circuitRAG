"""MCP deploy server (D3 stub).

§42 HARD STOP: this server requires that the caller present an
approval_id. Even a stub that just records a deploy MUST refuse
without an approval. Real apply (docker compose / kubectl / helm)
lands in a follow-up; today the stub returns a fake deploy_id +
rollback_handle so downstream observer flow can be drilled.

Run:
    MCP_DEPLOY_PORT=8096 python mcp/server_deploy.py
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_deploy")

app = FastAPI(title="DocuMind MCP — Deploy server (D3 stub)")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "deploy.compose_apply",
        "description": "Apply a docker-compose stack. Requires approval_id (§42).",
        "input_schema": {
            "type": "object",
            "properties": {
                "approval_id": {"type": "string"},
                "compose_file": {"type": "string"},
            },
            "required": ["approval_id", "compose_file"],
        },
        "required_scopes": ["deploy:write"],
    },
    {
        "name": "deploy.compose_rollback",
        "description": "Roll back a previously applied compose stack.",
        "input_schema": {
            "type": "object",
            "properties": {"rollback_handle": {"type": "string"}},
            "required": ["rollback_handle"],
        },
        "required_scopes": ["deploy:write"],
    },
]


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    tenant_id: str | None = None
    correlation_id: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-deploy", "stub": "true"}


@app.get("/tools/list")
async def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest) -> dict[str, Any]:
    if req.name == "deploy.compose_apply":
        approval_id = req.arguments.get("approval_id")
        if not approval_id:
            return {
                "ok": False,
                "error": {
                    "code": "approval_required",
                    "message": "§42 HARD STOP: deploy.compose_apply requires approval_id.",
                },
            }
        deploy_id = uuid.uuid4().hex
        return {
            "ok": True,
            "data": {
                "deploy_id": deploy_id,
                "rollback_handle": f"compose:{deploy_id}",
                "status": "applied",
                "approval_id": approval_id,
                "stub": True,
            },
        }
    if req.name == "deploy.compose_rollback":
        handle = req.arguments.get("rollback_handle")
        if not handle:
            return {
                "ok": False,
                "error": {"code": "invalid_input", "message": "rollback_handle is required"},
            }
        return {
            "ok": True,
            "data": {"rollback_handle": handle, "status": "rolled_back", "stub": True},
        }
    return {
        "ok": False,
        "error": {"code": "tool_not_found", "name": req.name},
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("MCP_DEPLOY_PORT", "8096"))
    uvicorn.run(app, host="0.0.0.0", port=port)
