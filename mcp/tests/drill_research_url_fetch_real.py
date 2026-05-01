#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for E6 — real URL-fetch backing in mcp/server_research.py.

Verifies research.synthesize:
  - topic-only call → stub:True canned (no web search API bundled)
  - urls-supplied call → real httpx fetch + extracted title/snippet
  - URL scheme validation rejects file:// / ftp:// / data:
  - rate cap (max 5 URLs per call) enforced

Negative assertions (security locks):
  1. file:// URL rejected (no local file exfiltration)
  2. data: URL rejected
  3. >5 URLs in one call → too_many_urls (rate cap)
  4. Empty topic → invalid_input
  5. urls field that isn't a list → invalid_input
  6. Stub fallback (topic-only) DOES emit stub:True so caller knows
     the result is canned, not real

We do NOT hit live external URLs — instead we use Python's
http.server temporarily on localhost so the drill is hermetic.
"""
from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from fastapi.testclient import TestClient


REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "mcp" / "server_research.py"


class _FakePageHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/clean":
            body = (
                b"<html><head><title>Test Page Title</title>"
                b'<meta name="description" content="A clean test description.">'
                b"</head><body><p>This is the body text of the test page.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/404":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"not found")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"hello plain text")

    def log_message(self, *_args: object) -> None:
        return  # silence


def _start_fake_server() -> tuple[HTTPServer, str, threading.Thread]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = HTTPServer(("127.0.0.1", port), _FakePageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    # Wait for server.
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    return server, base, thread


def _load():
    spec = importlib.util.spec_from_file_location("e6_server_research", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["e6_server_research"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    client = TestClient(mod.app)

    print("-- 1. POSITIVE: topic-only → stub:True canned --")
    r = client.post(
        "/tools/call",
        json={"name": "research.synthesize", "arguments": {"topic": "OAuth2 PKCE"}},
    )
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["stub"] is True, "topic-only must self-mark as stub"
    assert len(body["data"]["sources"]) >= 1
    print(f"  ok: stub:True canned with {len(body['data']['sources'])} canned source")

    print("-- 2. NEGATIVE: empty topic → invalid_input --")
    r = client.post(
        "/tools/call",
        json={"name": "research.synthesize", "arguments": {"topic": ""}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    print("  ok: empty topic rejected")

    print("-- 3. NEGATIVE: urls not a list → invalid_input --")
    r = client.post(
        "/tools/call",
        json={"name": "research.synthesize",
              "arguments": {"topic": "x", "urls": "not-a-list"}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    print("  ok: non-list urls rejected")

    print("-- 4. NEGATIVE: file:// scheme rejected (no local exfiltration) --")
    r = client.post(
        "/tools/call",
        json={"name": "research.synthesize",
              "arguments": {"topic": "x", "urls": ["file:///etc/passwd"]}},
    )
    body = r.json()
    assert body["ok"] is True
    # All URLs rejected → fall through to stub fallback, but the
    # rejected_urls list MUST record the file:// rejection.
    rejected = body["data"]["rejected_urls"]
    assert any("file:///etc/passwd" in r["url"] for r in rejected), (
        f"file:// URL must appear in rejected_urls; got {rejected}"
    )
    print(f"  ok: file:// rejected (recorded in rejected_urls)")

    print("-- 5. NEGATIVE: data: scheme rejected --")
    r = client.post(
        "/tools/call",
        json={"name": "research.synthesize",
              "arguments": {"topic": "x", "urls": ["data:text/plain,hello"]}},
    )
    body = r.json()
    rejected = body["data"]["rejected_urls"]
    assert any("data:" in r["url"] for r in rejected)
    print("  ok: data: rejected")

    print("-- 6. NEGATIVE: >5 URLs in one call → too_many_urls --")
    too_many = ["http://x.test/" + str(i) for i in range(10)]
    r = client.post(
        "/tools/call",
        json={"name": "research.synthesize", "arguments": {"topic": "x", "urls": too_many}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "too_many_urls", body
    print("  ok: 10 URLs > cap → rejected")

    print("-- 7. POSITIVE: real httpx fetch against local fake server --")
    server, base, thread = _start_fake_server()
    try:
        r = client.post(
            "/tools/call",
            json={"name": "research.synthesize",
                  "arguments": {"topic": "test fixture",
                                "urls": [f"{base}/clean"]}},
        )
        body = r.json()
        assert body["ok"] is True, f"fetch failed: {body}"
        data = body["data"]
        assert data["stub"] is False, "real-fetch result must NOT be stub:True"
        assert data["real_backing"] == "httpx"
        assert data["fetched_count"] == 1
        sources = data["sources"]
        assert len(sources) == 1
        assert sources[0]["title"] == "Test Page Title", (
            f"title not extracted from <title>; got {sources[0]['title']!r}"
        )
        assert "clean test description" in sources[0]["snippet"].lower() or \
               "body text" in sources[0]["snippet"].lower()
        assert sources[0]["http_status"] == 200
        print(f"  ok: real fetch extracted title='{sources[0]['title']}' http=200")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    print("-- 8. POSITIVE: 404 fetch → fetch_ok=False, ok envelope still True --")
    server, base, thread = _start_fake_server()
    try:
        r = client.post(
            "/tools/call",
            json={"name": "research.synthesize",
                  "arguments": {"topic": "x", "urls": [f"{base}/404"]}},
        )
        body = r.json()
        assert body["ok"] is True, f"envelope should be ok=true even for 404 page: {body}"
        sources = body["data"]["sources"]
        assert sources[0]["fetch_ok"] is False
        assert sources[0]["http_status"] == 404
        # fetched_count counts 200-range only.
        assert body["data"]["fetched_count"] == 0
        print("  ok: 404 captured as fetch_ok=False but envelope stayed ok")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
