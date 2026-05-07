"""
Jira MCP server — read-only Stage-1 surface for Jira issues.

Per CLAUDE.md §44 (autonomous-loop iter-67; user asked 'jira mcp' in
the SaaS-tools batch + 'setup these'), §47 (architecture: each MCP
server owns ONE namespace; jira.* is the Jira boundary), §47.6
(security: read-only Stage-1; write tools (issue create / comment /
transition) are externally-visible mutations and require a separate
ADR + write-surface server like ADR-028 for csv_ingest).

TOOLS (Stage-1 — read only)
  jira.issue_lookup       Get one issue by key (PROJ-123)
  jira.issue_search       JQL-allowlisted search (no UPDATE / DELETE)

CONFIG
  JIRA_BASE_URL           https://yourdomain.atlassian.net
  JIRA_EMAIL              service-account email
  JIRA_API_TOKEN          API token from id.atlassian.com
  When unset → tools return available:False stub (no live calls).

GUARDRAILS
  - JQL allowlist regex blocks DROP/DELETE/INSERT-shaped queries
    (Jira JQL doesn't have those keywords but defense-in-depth)
  - issue_key regex ^[A-Z][A-Z0-9_]{1,9}-[0-9]{1,8}$ — block
    path-traversal / injection in the URL parameter
  - All tools side_effects='read'; scope='jira:read'
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
    enforce_scope as _enforce_scope_common,
    handle_tool_call,
    mount_metrics_endpoint,
    setup_server_otel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_jira")

app = FastAPI(title="DocuMind MCP — Jira server")
setup_server_otel(app, service_name="mcp-server-jira")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,9}-[0-9]{1,8}$")
_JQL_FORBIDDEN_RE = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|TRUNCATE|EXECUTE|UNION)\b",
    re.IGNORECASE,
)
_MAX_JQL_LEN = 500


def _validate_issue_key(key: str) -> str:
    if not _ISSUE_KEY_RE.fullmatch(key):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_issue_key", "key": key,
                    "message": "issue_key must match ^[A-Z][A-Z0-9_]+-[0-9]+$"},
        )
    return key


def _validate_jql(jql: str) -> str:
    if len(jql) > _MAX_JQL_LEN:
        raise HTTPException(
            status_code=400,
            detail={"code": "jql_too_long", "max": _MAX_JQL_LEN},
        )
    if _JQL_FORBIDDEN_RE.search(jql):
        raise HTTPException(
            status_code=400,
            detail={"code": "jql_forbidden_keyword",
                    "message": "JQL contains DROP/DELETE/INSERT/UPDATE-shaped keyword"},
        )
    return jql


TOOLS: list[dict[str, Any]] = [
    {
        "name": "jira.issue_lookup",
        "description": "Look up a single Jira issue by key (e.g. PROJ-123).",
        "input_schema": {
            "type": "object",
            "required": ["issue_key"],
            "properties": {"issue_key": {"type": "string"}},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "summary": {"type": "string"},
                "status": {"type": "string"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["jira:read"],
        "idempotent": True,
    },
    {
        "name": "jira.issue_search",
        "description": "Search Jira issues via JQL (DROP/DELETE/INSERT-shaped queries blocked).",
        "input_schema": {
            "type": "object",
            "required": ["jql"],
            "properties": {
                "jql": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "issues": {"type": "array"},
                "total": {"type": "integer"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["jira:read"],
        "idempotent": True,
    },
]


def _build_idempotency_store():
    return {}


_IDEMPOTENCY = _build_idempotency_store()


def _live_or_stub() -> tuple[bool, str]:
    """Return (live, reason). Live when all 3 env vars set; stub otherwise."""
    base = os.getenv("JIRA_BASE_URL", "").strip()
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    if base and email and token:
        return True, ""
    return False, "JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN unset"


def _issue_lookup_impl(args: dict[str, Any]) -> dict[str, Any]:
    key = _validate_issue_key(args["issue_key"])
    live, reason = _live_or_stub()
    if not live:
        return {"key": key, "summary": "", "status": "", "available": False, "reason": reason}
    try:
        import urllib.request, base64, json as _json  # noqa: PLC0415
        base = os.environ["JIRA_BASE_URL"].rstrip("/")
        auth = base64.b64encode(
            f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()
        ).decode()
        req = urllib.request.Request(
            f"{base}/rest/api/3/issue/{key}",
            headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read().decode("utf-8"))
        fields = data.get("fields") or {}
        return {
            "key": data.get("key", key),
            "summary": fields.get("summary", "")[:300],
            "status": (fields.get("status") or {}).get("name", ""),
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("jira_issue_lookup_failed: %s", exc)
        return {"key": key, "summary": "", "status": "",
                "available": False, "error": str(exc)[:200]}


def _issue_search_impl(args: dict[str, Any]) -> dict[str, Any]:
    jql = _validate_jql(args["jql"])
    max_results = int(args.get("max_results", 25))
    live, reason = _live_or_stub()
    if not live:
        return {"issues": [], "total": 0, "available": False, "reason": reason}
    try:
        import urllib.request, urllib.parse, base64, json as _json  # noqa: PLC0415
        base = os.environ["JIRA_BASE_URL"].rstrip("/")
        auth = base64.b64encode(
            f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()
        ).decode()
        params = urllib.parse.urlencode({"jql": jql, "maxResults": max_results})
        req = urllib.request.Request(
            f"{base}/rest/api/3/search?{params}",
            headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = _json.loads(r.read().decode("utf-8"))
        return {
            "issues": [
                {"key": i.get("key"), "summary": (i.get("fields") or {}).get("summary", "")[:300]}
                for i in (data.get("issues") or [])[:max_results]
            ],
            "total": int(data.get("total", 0)),
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("jira_issue_search_failed: %s", exc)
        return {"issues": [], "total": 0, "available": False, "error": str(exc)[:200]}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-jira"}


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
        service_label="mcp_jira",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={"code": "upstream_error"})
    try:
        if req.name == "jira.issue_lookup":
            return _issue_lookup_impl(req.arguments)
        if req.name == "jira.issue_search":
            return _issue_search_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]}) from exc
    raise HTTPException(status_code=500, detail={"code": "no_dispatch_for_tool", "name": req.name})
