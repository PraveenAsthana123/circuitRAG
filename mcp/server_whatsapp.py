"""
WhatsApp MCP server — read-only Stage-1 (template lookup only).

Per CLAUDE.md §44 (iter-67 batch), §47 (each MCP server owns one
namespace; whatsapp.* is the WhatsApp Business API boundary), §47.6
(security: WhatsApp message SEND is externally-visible mutation
visible to consumers — explicitly outside Stage-1 scope; needs separate
ADR with consent + opt-out tracking + cost guardrails).

TOOLS (read only — Stage-1)
  whatsapp.template_lookup    Look up a pre-approved message template
                              by name (read-only against template registry)
  whatsapp.template_list      List available templates (paginated)

CONFIG
  WHATSAPP_BUSINESS_ACCOUNT_ID    WABA id (Meta Business Manager)
  WHATSAPP_ACCESS_TOKEN           Permanent system-user access token
  When unset → tools return available:False stub.

WHY READ-ONLY ONLY
  Sending a WhatsApp message is:
    - externally visible (consumer sees it on their phone)
    - cost-billed (per Meta's pricing tier)
    - consent-regulated (GDPR + WhatsApp opt-in policy)
  None of these are appropriate for Stage-1 agent autonomy. Per §42
  external messages are explicitly gated. The send-surface needs:
    - approval workflow (like csv_ingest.apply_approved_load)
    - consent verification (read from a consent registry)
    - cost ceiling (per-tenant per-day budget)
    - opt-out enforcement (recipients on opt-out list → 400)
  All deferred to a future ADR-029 (analogous to ADR-028).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from mcp.server_common import (
    ToolCallRequest,
    build_auth,
    handle_tool_call,
    mount_metrics_endpoint,
    setup_server_otel,
)
from mcp.server_common import (
    enforce_scope as _enforce_scope_common,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_whatsapp")

app = FastAPI(title="DocuMind MCP — WhatsApp server")
setup_server_otel(app, service_name="mcp-server-whatsapp")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _validate_template_name(name: str) -> str:
    if not _TEMPLATE_NAME_RE.fullmatch(name):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_template_name", "name": name,
                    "message": "template name must match ^[a-z0-9_]+$"},
        )
    return name


TOOLS: list[dict[str, Any]] = [
    {
        "name": "whatsapp.template_lookup",
        "description": "Look up a pre-approved WhatsApp message template by name.",
        "input_schema": {
            "type": "object",
            "required": ["template_name"],
            "properties": {"template_name": {"type": "string"}},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "language": {"type": "string"},
                "body": {"type": "string"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["whatsapp:read"],
        "idempotent": True,
    },
    {
        "name": "whatsapp.template_list",
        "description": "List available WhatsApp message templates (paginated).",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "templates": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["whatsapp:read"],
        "idempotent": True,
    },
]

_IDEMPOTENCY: dict[str, Any] = {}


def _live_or_stub() -> tuple[bool, str]:
    keys = ("WHATSAPP_BUSINESS_ACCOUNT_ID", "WHATSAPP_ACCESS_TOKEN")
    if all(os.getenv(k, "").strip() for k in keys):
        return True, ""
    missing = [k for k in keys if not os.getenv(k, "").strip()]
    return False, f"unset env: {missing}"


def _template_lookup_impl(args: dict[str, Any]) -> dict[str, Any]:
    name = _validate_template_name(args["template_name"])
    live, reason = _live_or_stub()
    if not live:
        return {"name": name, "language": "", "body": "",
                "available": False, "reason": reason}
    return {"name": name, "language": "en_US", "body": "",
            "available": True, "stub": "live_wiring_pending"}


def _template_list_impl(args: dict[str, Any]) -> dict[str, Any]:
    live, reason = _live_or_stub()
    if not live:
        return {"templates": [], "available": False, "reason": reason}
    return {"templates": [], "available": True, "stub": "live_wiring_pending"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-whatsapp"}


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
        req=req, tools=TOOLS, idempotency_key=idempotency_key,
        authorization=authorization, auth_required=_AUTH_REQUIRED,
        verifier=_VERIFIER, idempotency_store=_IDEMPOTENCY,
        dispatch=_dispatch, tracer_module=__name__, logger=log,
        service_label="mcp_whatsapp",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={"code": "upstream_error"})
    try:
        if req.name == "whatsapp.template_lookup":
            return _template_lookup_impl(req.arguments)
        if req.name == "whatsapp.template_list":
            return _template_list_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]}) from exc
    raise HTTPException(status_code=500, detail={"code": "no_dispatch_for_tool", "name": req.name})
