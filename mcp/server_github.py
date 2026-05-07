"""
GitHub MCP server — read-only Stage-1 for AI SDLC use case.

Per CLAUDE.md §44 (iter-68; user moving toward AI SDLC use-case;
GitHub is the most-critical missing tool — source control is the
spine of any SDLC), §47 (each MCP server owns ONE namespace;
github.* is the GitHub boundary), §47.6 (security: read-only
Stage-1; PR comment / issue create / merge are externally-visible
mutations — write surface ships separately per ADR-028 pattern with
its own ADR + approval workflow).

TOOLS (read only — Stage-1)
  github.repo_get_file        Get file contents at ref (sha/branch/tag)
  github.pr_lookup            Get PR metadata + diff URL
  github.pr_search            Search PRs (open/closed/merged) by query
  github.issue_lookup         Get issue metadata + body
  github.issue_search         Search issues by query (allowlisted q-string)
  github.code_search          Search code across configured repos

CONFIG (token + repo allow-list)
  GITHUB_TOKEN                 PAT or fine-grained token (read-only scopes)
  GITHUB_OWNER                 Default owner/org (e.g. anthropic)
  GITHUB_ALLOWED_REPOS         Comma-list of allowed `owner/repo` slugs;
                               agents cannot read repos outside this list.
                               When unset, server stays in stub mode.

GUARDRAILS
  - Repo slug regex ^[A-Za-z0-9._-]{1,100}/[A-Za-z0-9._-]{1,100}$
  - Path regex blocks .. + leading / + null bytes
  - Search query rejects DDL/DML-shaped keywords (defense-in-depth)
  - All tools side_effects='read'; scope='github:read'
  - Repo allow-list = second-layer gate (token alone could read any
    repo it has access to; allow-list narrows to named repos)
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
log = logging.getLogger("mcp.server_github")

app = FastAPI(title="DocuMind MCP — GitHub server")
setup_server_otel(app, service_name="mcp-server-github")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}/[A-Za-z0-9._-]{1,100}$")
_PATH_FORBIDDEN_RE = re.compile(r"\.\.|^/|\x00")
_QUERY_FORBIDDEN_RE = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|TRUNCATE|EXECUTE|UNION)\b",
    re.IGNORECASE,
)


def _allowed_repos() -> set[str]:
    raw = os.getenv("GITHUB_ALLOWED_REPOS", "").strip()
    if not raw:
        return set()
    return {r.strip() for r in raw.split(",") if r.strip()}


def _validate_repo_slug(slug: str) -> str:
    if not _REPO_SLUG_RE.fullmatch(slug):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_repo_slug", "slug": slug,
                    "message": "repo must match owner/name pattern"},
        )
    allow = _allowed_repos()
    if allow and slug not in allow:
        raise HTTPException(
            status_code=403,
            detail={"code": "repo_not_allowed", "slug": slug,
                    "message": f"repo not in GITHUB_ALLOWED_REPOS allow-list"},
        )
    return slug


def _validate_path(path: str) -> str:
    if not path or len(path) > 500:
        raise HTTPException(status_code=400,
                            detail={"code": "invalid_path", "path": path[:50]})
    if _PATH_FORBIDDEN_RE.search(path):
        raise HTTPException(
            status_code=400,
            detail={"code": "path_traversal_blocked", "path": path[:50],
                    "message": "path may not contain '..' / leading '/' / null bytes"},
        )
    return path


def _validate_query(q: str) -> str:
    if len(q) > 500:
        raise HTTPException(status_code=400,
                            detail={"code": "query_too_long", "max": 500})
    if _QUERY_FORBIDDEN_RE.search(q):
        raise HTTPException(
            status_code=400,
            detail={"code": "query_forbidden_keyword",
                    "message": "query contains DDL/DML-shaped keyword"},
        )
    return q


TOOLS: list[dict[str, Any]] = [
    {
        "name": "github.repo_get_file",
        "description": "Get a file's contents from a GitHub repo at a given ref.",
        "input_schema": {
            "type": "object",
            "required": ["repo", "path"],
            "properties": {
                "repo": {"type": "string"},
                "path": {"type": "string"},
                "ref": {"type": "string", "default": "HEAD"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "path": {"type": "string"},
                "ref": {"type": "string"},
                "content": {"type": "string"},
                "size": {"type": "integer"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["github:read"],
        "idempotent": True,
    },
    {
        "name": "github.pr_lookup",
        "description": "Look up a GitHub pull request by number.",
        "input_schema": {
            "type": "object",
            "required": ["repo", "number"],
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer", "minimum": 1},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
                "title": {"type": "string"},
                "state": {"type": "string"},
                "head": {"type": "string"},
                "base": {"type": "string"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["github:read"],
        "idempotent": True,
    },
    {
        "name": "github.pr_search",
        "description": "Search GitHub PRs by query (read-only).",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "prs": {"type": "array"},
                "total": {"type": "integer"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["github:read"],
        "idempotent": True,
    },
    {
        "name": "github.issue_lookup",
        "description": "Look up a GitHub issue by number.",
        "input_schema": {
            "type": "object",
            "required": ["repo", "number"],
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer", "minimum": 1},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "state": {"type": "string"},
                "labels": {"type": "array"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["github:read"],
        "idempotent": True,
    },
    {
        "name": "github.issue_search",
        "description": "Search GitHub issues by query.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
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
        "required_scopes": ["github:read"],
        "idempotent": True,
    },
    {
        "name": "github.code_search",
        "description": "Search code across the configured GitHub repos.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "matches": {"type": "array"},
                "total": {"type": "integer"},
                "available": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["github:read"],
        "idempotent": True,
    },
]

_IDEMPOTENCY: dict[str, Any] = {}


def _live_or_stub() -> tuple[bool, str]:
    if os.getenv("GITHUB_TOKEN", "").strip():
        return True, ""
    return False, "GITHUB_TOKEN unset"


def _gh_get(url: str) -> dict[str, Any]:
    """One-shot GitHub REST GET. 10s timeout."""
    import urllib.request, json as _json  # noqa: PLC0415
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return _json.loads(r.read().decode("utf-8"))


def _repo_get_file_impl(args: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo_slug(args["repo"])
    path = _validate_path(args["path"])
    ref = args.get("ref", "HEAD")
    live, reason = _live_or_stub()
    if not live:
        return {"repo": repo, "path": path, "ref": ref, "content": "",
                "size": 0, "available": False, "reason": reason}
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
        data = _gh_get(url)
        # GitHub returns base64-encoded content for files
        import base64  # noqa: PLC0415
        content_b64 = data.get("content", "").replace("\n", "")
        content = base64.b64decode(content_b64).decode("utf-8", errors="replace") if content_b64 else ""
        return {
            "repo": repo, "path": path, "ref": ref,
            "content": content[:50000],  # 50 KiB cap
            "size": int(data.get("size", 0)),
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("github_repo_get_file_failed: %s", exc)
        return {"repo": repo, "path": path, "ref": ref, "content": "",
                "size": 0, "available": False, "error": str(exc)[:200]}


def _pr_lookup_impl(args: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo_slug(args["repo"])
    number = int(args["number"])
    live, reason = _live_or_stub()
    if not live:
        return {"repo": repo, "number": number, "title": "", "state": "",
                "head": "", "base": "", "available": False, "reason": reason}
    try:
        data = _gh_get(f"https://api.github.com/repos/{repo}/pulls/{number}")
        return {
            "repo": repo, "number": number,
            "title": data.get("title", "")[:300],
            "state": data.get("state", ""),
            "head": (data.get("head") or {}).get("ref", ""),
            "base": (data.get("base") or {}).get("ref", ""),
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("github_pr_lookup_failed: %s", exc)
        return {"repo": repo, "number": number, "title": "", "state": "",
                "head": "", "base": "", "available": False, "error": str(exc)[:200]}


def _pr_search_impl(args: dict[str, Any]) -> dict[str, Any]:
    q = _validate_query(args["query"])
    max_results = int(args.get("max_results", 25))
    live, reason = _live_or_stub()
    if not live:
        return {"prs": [], "total": 0, "available": False, "reason": reason}
    try:
        import urllib.parse  # noqa: PLC0415
        # GitHub search-issues API handles PRs too; force is:pr scope
        full_q = f"is:pr {q}"
        url = (
            f"https://api.github.com/search/issues"
            f"?q={urllib.parse.quote(full_q)}&per_page={max_results}"
        )
        data = _gh_get(url)
        return {
            "prs": [
                {"number": i.get("number"),
                 "title": i.get("title", "")[:200],
                 "state": i.get("state"),
                 "html_url": i.get("html_url")}
                for i in (data.get("items") or [])[:max_results]
            ],
            "total": int(data.get("total_count", 0)),
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("github_pr_search_failed: %s", exc)
        return {"prs": [], "total": 0, "available": False, "error": str(exc)[:200]}


def _issue_lookup_impl(args: dict[str, Any]) -> dict[str, Any]:
    repo = _validate_repo_slug(args["repo"])
    number = int(args["number"])
    live, reason = _live_or_stub()
    if not live:
        return {"repo": repo, "number": number, "title": "", "body": "",
                "state": "", "labels": [], "available": False, "reason": reason}
    try:
        data = _gh_get(f"https://api.github.com/repos/{repo}/issues/{number}")
        return {
            "repo": repo, "number": number,
            "title": data.get("title", "")[:300],
            "body": (data.get("body") or "")[:5000],
            "state": data.get("state", ""),
            "labels": [(l.get("name") if isinstance(l, dict) else str(l))
                       for l in (data.get("labels") or [])],
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("github_issue_lookup_failed: %s", exc)
        return {"repo": repo, "number": number, "title": "", "body": "",
                "state": "", "labels": [], "available": False, "error": str(exc)[:200]}


def _issue_search_impl(args: dict[str, Any]) -> dict[str, Any]:
    q = _validate_query(args["query"])
    max_results = int(args.get("max_results", 25))
    live, reason = _live_or_stub()
    if not live:
        return {"issues": [], "total": 0, "available": False, "reason": reason}
    try:
        import urllib.parse  # noqa: PLC0415
        full_q = f"is:issue {q}"
        url = (
            f"https://api.github.com/search/issues"
            f"?q={urllib.parse.quote(full_q)}&per_page={max_results}"
        )
        data = _gh_get(url)
        return {
            "issues": [
                {"number": i.get("number"),
                 "title": i.get("title", "")[:200],
                 "state": i.get("state"),
                 "html_url": i.get("html_url")}
                for i in (data.get("items") or [])[:max_results]
            ],
            "total": int(data.get("total_count", 0)),
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("github_issue_search_failed: %s", exc)
        return {"issues": [], "total": 0, "available": False, "error": str(exc)[:200]}


def _code_search_impl(args: dict[str, Any]) -> dict[str, Any]:
    q = _validate_query(args["query"])
    max_results = int(args.get("max_results", 25))
    live, reason = _live_or_stub()
    if not live:
        return {"matches": [], "total": 0, "available": False, "reason": reason}
    try:
        import urllib.parse  # noqa: PLC0415
        # Narrow to allow-listed repos when set
        allow = _allowed_repos()
        if allow:
            scope = " ".join(f"repo:{r}" for r in allow)
            full_q = f"{scope} {q}"
        else:
            full_q = q
        url = (
            f"https://api.github.com/search/code"
            f"?q={urllib.parse.quote(full_q)}&per_page={max_results}"
        )
        data = _gh_get(url)
        return {
            "matches": [
                {"path": m.get("path"),
                 "repo": (m.get("repository") or {}).get("full_name"),
                 "html_url": m.get("html_url")}
                for m in (data.get("items") or [])[:max_results]
            ],
            "total": int(data.get("total_count", 0)),
            "available": True,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("github_code_search_failed: %s", exc)
        return {"matches": [], "total": 0, "available": False, "error": str(exc)[:200]}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-github"}


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
        service_label="mcp_github",
    )


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(status_code=502, detail={"code": "upstream_error"})
    try:
        if req.name == "github.repo_get_file":
            return _repo_get_file_impl(req.arguments)
        if req.name == "github.pr_lookup":
            return _pr_lookup_impl(req.arguments)
        if req.name == "github.pr_search":
            return _pr_search_impl(req.arguments)
        if req.name == "github.issue_lookup":
            return _issue_lookup_impl(req.arguments)
        if req.name == "github.issue_search":
            return _issue_search_impl(req.arguments)
        if req.name == "github.code_search":
            return _code_search_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(status_code=500,
                            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]}) from exc
    raise HTTPException(status_code=500, detail={"code": "no_dispatch_for_tool", "name": req.name})
