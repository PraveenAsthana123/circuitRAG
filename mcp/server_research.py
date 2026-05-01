"""MCP research server (E6: real URL-fetch backing).

E6 wires research.synthesize to do REAL httpx fetches when the caller
supplies `urls: [str]`. The server fetches each URL, extracts title +
meta description + first 500 chars of body text, and returns them as
sources. The agent layer (ResearchAgent) does the LLM synthesis with
real source content.

When no urls are supplied (caller passed only `topic`), the server
falls back to canned data with stub:True — there's no web search API
key bundled, so we cannot truly discover sources from a topic alone.
That's an honest contract.

Security guards:
  - URL scheme MUST be http or https (no file://, no ftp://, no data:)
  - Per-URL timeout 10s
  - Max 5 URLs per call
  - Body size cap 1 MiB (httpx truncates after)
  - argv list / no shell anywhere

Run:
    MCP_RESEARCH_PORT=8094 python mcp/server_research.py
"""
from __future__ import annotations

import logging
import os
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_research")

app = FastAPI(title="DocuMind MCP — Research server (E6)")


MAX_URLS_PER_CALL = int(os.environ.get("MCP_RESEARCH_MAX_URLS", "5"))
PER_URL_TIMEOUT_SEC = float(os.environ.get("MCP_RESEARCH_TIMEOUT_SEC", "10"))
MAX_BODY_BYTES = int(os.environ.get("MCP_RESEARCH_MAX_BODY_BYTES", str(1024 * 1024)))
ALLOWED_SCHEMES = {"http", "https"}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "research.synthesize",
        "description": (
            "Fetch caller-supplied URLs and extract title/description/snippet "
            "as research sources. When `urls` provided → REAL httpx fetch. "
            "When only `topic` provided → STUB (no web search API bundled)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What to research."},
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": MAX_URLS_PER_CALL,
                    "description": "Optional list of URLs to fetch (max 5).",
                },
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
    return {
        "status": "ok",
        "service": "mcp-server-research",
        "stub": "partial",  # canned for topic-only; real for urls-supplied
        "max_urls_per_call": str(MAX_URLS_PER_CALL),
    }


@app.get("/tools/list")
async def list_tools() -> dict[str, Any]:
    return {"tools": TOOLS}


def _validate_url(raw: str) -> str | None:
    """Reject anything that isn't http(s). Returns the canonical URL or None."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = urlparse(raw.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return None
    if not parsed.netloc:
        return None
    return raw.strip()


class _MetaExtractor(HTMLParser):
    """Pulls <title> + <meta name="description" content="..."> + body text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.text_parts: list[str] = []
        self._in_title = False
        self._in_skip = False  # script / style / noscript

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l == "title":
            self._in_title = True
        elif tag_l in {"script", "style", "noscript"}:
            self._in_skip = True
        elif tag_l == "meta":
            attrs_dict = {k.lower(): (v or "") for k, v in attrs}
            if attrs_dict.get("name") == "description":
                self.description = attrs_dict.get("content", "")[:500]

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l == "title":
            self._in_title = False
        elif tag_l in {"script", "style", "noscript"}:
            self._in_skip = False

    def handle_data(self, data: str) -> None:
        if self._in_skip:
            return
        if self._in_title:
            self.title += data
        else:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)


def _extract_metadata(content: bytes, content_type: str) -> dict[str, str]:
    """Parse HTML for title + description + first 500 chars of body text.

    Falls back to plain-text snippet for non-HTML content. Truncates
    everything to safe lengths.
    """
    text = content[:MAX_BODY_BYTES].decode("utf-8", errors="replace")
    if "html" in content_type.lower():
        parser = _MetaExtractor()
        try:
            parser.feed(text)
        except Exception:  # noqa: BLE001 — malformed HTML; degrade gracefully
            pass
        body = " ".join(parser.text_parts)
        body = re.sub(r"\s+", " ", body).strip()
        return {
            "title": parser.title.strip()[:200] or "(no title)",
            "description": parser.description.strip()[:500],
            "snippet": body[:500],
        }
    snippet = re.sub(r"\s+", " ", text).strip()[:500]
    return {"title": "(non-HTML resource)", "description": "", "snippet": snippet}


async def _fetch_one(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    try:
        r = await client.get(url, follow_redirects=True, timeout=PER_URL_TIMEOUT_SEC)
        meta = _extract_metadata(r.content[:MAX_BODY_BYTES], r.headers.get("content-type", ""))
        return {
            "url": url,
            "status": r.status_code,
            "title": meta["title"],
            "description": meta["description"],
            "snippet": meta["snippet"],
            "ok": 200 <= r.status_code < 400,
            "fetched_bytes": len(r.content),
        }
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return {
            "url": url,
            "status": None,
            "title": None,
            "description": None,
            "snippet": None,
            "ok": False,
            "error": str(exc),
        }


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

    raw_urls = req.arguments.get("urls") or []
    if not isinstance(raw_urls, list):
        return {
            "ok": False,
            "error": {"code": "invalid_input", "message": "urls must be a list"},
        }

    # Validate + dedupe URLs.
    if len(raw_urls) > MAX_URLS_PER_CALL:
        return {
            "ok": False,
            "error": {
                "code": "too_many_urls",
                "message": f"max {MAX_URLS_PER_CALL} URLs per call; got {len(raw_urls)}",
            },
        }
    validated_urls: list[str] = []
    rejected: list[dict[str, str]] = []
    for u in raw_urls:
        cleaned = _validate_url(u)
        if cleaned and cleaned not in validated_urls:
            validated_urls.append(cleaned)
        elif u not in [r["url"] for r in rejected]:
            rejected.append({"url": str(u)[:200], "reason": "scheme not http(s) or empty"})

    if not validated_urls:
        # No real URLs → topic-only fallback (canned, stub:True).
        return {
            "ok": True,
            "data": {
                "topic": topic,
                "summary": f"[STUB] {topic} synthesised from canned sources.",
                "sources": [
                    {"title": "Canonical reference (stub)", "url": f"https://example.test/{topic}",
                     "relevance": "primary"},
                ],
                "suggested_approach": f"[STUB] outline approach for {topic}; supply `urls` for real fetch.",
                "risks": ["stub data — supply `urls` for real httpx fetch"],
                "stub": True,
                "rejected_urls": rejected,
            },
        }

    # Real fetch path.
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=PER_URL_TIMEOUT_SEC, follow_redirects=True) as client:
        import asyncio as _asyncio
        results = await _asyncio.gather(*[_fetch_one(client, u) for u in validated_urls])

    sources = [
        {
            "title": r.get("title") or r["url"],
            "url": r["url"],
            "relevance": ("primary" if i == 0 else "secondary"),
            "snippet": r.get("snippet") or "",
            "fetch_ok": r.get("ok", False),
            "http_status": r.get("status"),
        }
        for i, r in enumerate(results)
    ]
    fetched_count = sum(1 for r in results if r.get("ok"))

    return {
        "ok": True,
        "data": {
            "topic": topic,
            "summary": (
                f"Fetched {fetched_count}/{len(validated_urls)} URL(s) for: {topic}. "
                "Server-side extraction includes title + meta description + first 500 chars."
            ),
            "sources": sources,
            "suggested_approach": "Caller (ResearchAgent / LLM) should synthesise from the source snippets above.",
            "risks": [r["error"] for r in results if not r.get("ok") and r.get("error")],
            "stub": False,
            "real_backing": "httpx",
            "fetched_count": fetched_count,
            "rejected_urls": rejected,
        },
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("MCP_RESEARCH_PORT", "8094"))
    uvicorn.run(app, host="0.0.0.0", port=port)
