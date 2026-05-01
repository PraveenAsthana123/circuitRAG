"""MCP research server (D3 stub).

Hosts research.synthesize tool. Today returns canned data — the real
upstream integration (web search + Microsoft Docs MCP + RAG retrieval)
will replace the synthesize implementation in a follow-up commit. The
HTTP shape, /tools/list catalog, and tool args contract are stable
from this commit onward.

Wire-format note: minimal /tools/list + /tools/call — does NOT yet
plug into server_common's auth + idempotency + OTel pipeline. Adding
those is a separate hardening pass; the stub is operationally usable
for end-to-end pipeline drills today.

Run:
    MCP_RESEARCH_PORT=8094 python mcp/server_research.py
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_research")

app = FastAPI(title="DocuMind MCP — Research server (D3 stub)")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "research.synthesize",
        "description": "Search docs/web and produce a research summary "
                       "with sources, suggested approach, and risks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What to research."},
                "depth": {"type": "string", "enum": ["shallow", "standard", "deep"], "default": "standard"},
            },
            "required": ["topic"],
        },
        "required_scopes": ["research:read"],
    },
]


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    tenant_id: str | None = None
    correlation_id: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-research", "stub": "true"}


@app.get("/tools/list")
async def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest) -> dict[str, Any]:
    if req.name != "research.synthesize":
        return {
            "ok": False,
            "error": {"code": "tool_not_found", "name": req.name},
        }
    topic = str(req.arguments.get("topic", "")).strip()
    if not topic:
        return {
            "ok": False,
            "error": {"code": "invalid_input", "message": "topic is required"},
        }
    # Canned response — real integration replaces this body.
    return {
        "ok": True,
        "data": {
            "topic": topic,
            "summary": f"[STUB] {topic} synthesised from canned sources.",
            "sources": [
                {"title": "Canonical reference (stub)", "url": f"https://example.test/{topic}", "relevance": "primary"},
            ],
            "suggested_approach": f"[STUB] outline approach for {topic}; replace with real synthesis.",
            "risks": ["stub data — not authoritative"],
            "stub": True,
        },
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("MCP_RESEARCH_PORT", "8094"))
    uvicorn.run(app, host="0.0.0.0", port=port)
