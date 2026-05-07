"""MCP server for local Ollama — Tier 5 #5.15.

Exposes the local Ollama installation as MCP tools so any
MCP-compatible agent (orchestrator's worker / sidecar-advisor /
external client) can invoke local models through the same wire
format as the rest of the MCP fleet (server_hr, server_itsm,
server_drills, ...).

EXPOSED TOOLS
=============

  ollama.generate     — non-streaming generation
                         args: model (str), prompt (str), system (str|None),
                               temperature (float, default 0.1),
                               num_predict (int, default 512),
                               keep_alive (str, default '5m')
                         out:  text (str), tokens_used (int), latency_s (float)

  ollama.list_models  — list models present in local Ollama
                         args: (none)
                         out:  models (list[str])

  ollama.warm         — pre-load a model with keep_alive=24h
                         args: model (str)
                         out:  warmed (bool), latency_s (float)

§42 / §50.5.3 BOUNDARIES
========================

  - generate is bounded at 240s timeout
  - generate's prompt MUST NOT exceed 32K chars (one-shot guard)
  - per-tool scopes (per CLAUDE.md §50): ollama:generate / ollama:read /
    ollama:warm — declared at registration time
  - never push to ollama (no model upload from MCP layer)
  - never modify model files / OS state

USAGE
=====

  python3 mcp/server_ollama.py  # serves on $MCP_OLLAMA_PORT (default 8098)

Drilled by mcp/tests/drill_server_ollama.py.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError

from mcp.server_common import (  # type: ignore[import-untyped]
    build_auth,
    enforce_scope,
    setup_server_otel,
)

log = logging.getLogger("mcp.server_ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_TIMEOUT_S = 240.0
PROMPT_MAX_CHARS = 32_000


# ---------------------------------------------------------------------
# MCP tool schemas (Pydantic; extra='forbid' prevents PII contamination)
# ---------------------------------------------------------------------

class GenerateArgs(BaseModel):
    model: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=PROMPT_MAX_CHARS)
    system: str | None = Field(default=None, max_length=4000)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    num_predict: int = Field(default=512, ge=1, le=8192)
    keep_alive: str = Field(default="5m", max_length=16)
    model_config = {"extra": "forbid"}


class ListModelsArgs(BaseModel):
    model_config = {"extra": "forbid"}


class WarmArgs(BaseModel):
    model: str = Field(min_length=1, max_length=128)
    keep_alive: str = Field(default="24h", max_length=16)
    model_config = {"extra": "forbid"}


class ToolCallRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------

def _curl_post(url: str, payload: dict, timeout: float) -> dict:
    proc = subprocess.run(
        ["curl", "-s", "--max-time", str(int(timeout)),
         "-X", "POST", url,
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if proc.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail={"error": "ollama_call_failed",
                    "exit_code": proc.returncode,
                    "stderr": proc.stderr.strip()[:200]},
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "ollama_returned_non_json",
                    "stdout_preview": proc.stdout[:200]},
        ) from exc


def _curl_get(url: str, timeout: float) -> dict:
    proc = subprocess.run(
        ["curl", "-s", "--max-time", str(int(timeout)), url],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if proc.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail={"error": "ollama_call_failed",
                    "exit_code": proc.returncode},
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "ollama_returned_non_json",
                    "stdout_preview": proc.stdout[:200]},
        ) from exc


def tool_generate(args: GenerateArgs) -> dict:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": args.prompt,
        "stream": False,
        "options": {
            "temperature": args.temperature,
            "num_predict": args.num_predict,
        },
        "keep_alive": args.keep_alive,
    }
    if args.system:
        payload["system"] = args.system
    started = time.time()
    body = _curl_post(f"{OLLAMA_URL}/api/generate", payload, timeout=DEFAULT_TIMEOUT_S)
    elapsed = round(time.time() - started, 2)
    return {
        "text": body.get("response", ""),
        "tokens_used": int(body.get("eval_count", 0)),
        "latency_s": elapsed,
    }


def tool_list_models(_args: ListModelsArgs) -> dict:
    body = _curl_get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
    return {"models": [m.get("name", "") for m in body.get("models", []) if m.get("name")]}


def tool_warm(args: WarmArgs) -> dict:
    payload = {
        "model": args.model,
        "prompt": "reply: ok",
        "stream": False,
        "options": {"num_predict": 4, "temperature": 0.0},
        "keep_alive": args.keep_alive,
    }
    started = time.time()
    body = _curl_post(f"{OLLAMA_URL}/api/generate", payload, timeout=120.0)
    elapsed = round(time.time() - started, 2)
    warmed = bool(body.get("response"))
    return {"warmed": warmed, "latency_s": elapsed}


# ---------------------------------------------------------------------
# Tool registry — declares scopes per CLAUDE.md §50
# ---------------------------------------------------------------------

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "ollama.generate": {
        "args_schema": GenerateArgs,
        "handler": tool_generate,
        "required_scopes": ["ollama:generate"],
    },
    "ollama.list_models": {
        "args_schema": ListModelsArgs,
        "handler": tool_list_models,
        "required_scopes": ["ollama:read"],
    },
    "ollama.warm": {
        "args_schema": WarmArgs,
        "handler": tool_warm,
        "required_scopes": ["ollama:warm"],
    },
}


# ---------------------------------------------------------------------
# FastAPI surface
# ---------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="mcp-server-ollama", version="0.1.0")
    setup_server_otel(app, service_name="mcp-server-ollama")
    AUTH_REQUIRED, VERIFIER = build_auth()

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        # Quick check: can we reach Ollama?
        try:
            _curl_get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
            return {"status": "ready"}
        except HTTPException:
            raise HTTPException(status_code=503, detail={"error": "ollama_unreachable"})

    @app.get("/tools/list")
    async def list_tools() -> dict[str, Any]:
        return {
            "tools": [
                {"name": name, "scopes": meta["required_scopes"]}
                for name, meta in TOOL_REGISTRY.items()
            ],
        }

    @app.post("/tools/call")
    async def call_tool(req: ToolCallRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        meta = TOOL_REGISTRY.get(req.tool)
        if meta is None:
            raise HTTPException(status_code=404,
                                detail={"error": "unknown_tool", "tool": req.tool})
        if AUTH_REQUIRED:
            for scope in meta["required_scopes"]:
                enforce_scope(VERIFIER, authorization, scope)
        try:
            args = meta["args_schema"].model_validate(req.arguments)
        except ValidationError as ve:
            raise HTTPException(status_code=400,
                                detail={"error": "invalid_args",
                                        "errors": [str(e) for e in ve.errors()[:3]]})
        return meta["handler"](args)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MCP_OLLAMA_PORT", "8098"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
