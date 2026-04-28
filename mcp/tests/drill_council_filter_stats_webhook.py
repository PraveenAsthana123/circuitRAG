#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: --webhook URL alert posting (Phase 5T).

Phase 5O/R fire alerts; Phase 5T POSTs them out-of-band to a Slack /
Discord / generic webhook. Best-effort: webhook failure must NOT
flip the exit code (alerts already fired = exit 1).

Eight steps. Six negative assertions.

  1. _normalize_fired flattens both 2-tuples (single-window) and
     3-tuples (weekly) into a uniform dict shape.
  2. NEGATIVE: build_webhook_payload accepts only WEBHOOK_FORMATS;
     unknown format raises ValueError. Typo in --webhook-format
     must fail fast, not POST garbage.
  3. NEGATIVE: 'generic' format includes raw fired_alerts +
     context + timestamp. Operators piping this to PagerDuty /
     custom routers need the structured shape.
  4. NEGATIVE: 'slack' format uses Block Kit (text + blocks
     fields), with one section block per fired alert. Without
     the 'text' fallback, Slack mobile previews show empty.
  5. NEGATIVE: 'discord' format uses embeds (capped at 10 per
     Discord's hard limit). Each embed has title + description.
  6. NEGATIVE: post_webhook returns (False, msg) on connection
     refused — does NOT raise, does NOT change exit. Captured at
     the URLError boundary.
  7. NEGATIVE: post_webhook honors timeout_s. We bind a server
     that accepts but never responds; with a 0.5s timeout, post
     returns (False, ...) under 2s wall.
  8. POSITIVE: end-to-end via in-process HTTP server — start
     server on 127.0.0.1:0, post_webhook to it, verify the
     server received exactly one POST with the expected payload.

Run: python3 mcp/tests/drill_council_filter_stats_webhook.py
"""
from __future__ import annotations

import http.server
import importlib.util
import json
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_drill_5T", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5T"] = mod
    spec.loader.exec_module(mod)
    return mod


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that stores incoming POST bodies on the server
    instance for later inspection."""
    received: list = []  # set by drill before serving

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n).decode("utf-8")
        self.server.received.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": body,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args, **kwargs):
        # Silence stderr access logs during the drill
        pass


def _start_server() -> tuple[socketserver.TCPServer, str]:
    """Start an HTTP server on 127.0.0.1:<random> and return
    (server, url). Caller is responsible for shutdown()."""
    server = socketserver.TCPServer(("127.0.0.1", 0), _RecordingHandler)
    server.received = []
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}/webhook"


class _SilentTimeoutHandler(http.server.BaseHTTPRequestHandler):
    """Accepts the connection but never sends a response — used to
    verify post_webhook honors the timeout."""
    def do_POST(self):
        time.sleep(10.0)  # past any reasonable test timeout
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args, **kwargs):
        pass


def main() -> int:
    stats = _load_stats()

    # ── Step 1: _normalize_fired flattens both shapes ──
    e = stats.parse_alert_expr("too_short>0.5")
    # 2-tuple shape (from check_alerts)
    flat_single = stats._normalize_fired([(e, 0.62)])
    if len(flat_single) != 1 or flat_single[0]["week"] is not None:
        print(f"✗ step 1: 2-tuple normalization wrong: {flat_single}")
        return 1
    # 3-tuple shape (from check_alerts_weekly)
    flat_weekly = stats._normalize_fired([(e, "2026-W17", 0.62)])
    if len(flat_weekly) != 1 or flat_weekly[0]["week"] != "2026-W17":
        print(f"✗ step 1: 3-tuple normalization wrong: {flat_weekly}")
        return 1
    # All required fields populated
    required = {"expr", "bucket", "op", "threshold", "observed", "week"}
    if not required.issubset(flat_weekly[0].keys()):
        print(f"✗ step 1: missing fields: {required - flat_weekly[0].keys()}")
        return 1
    print("✓ step 1: _normalize_fired flattens 2-tuple and 3-tuple shapes")

    # ── Step 2: NEGATIVE — unknown format rejected ──
    try:
        stats.build_webhook_payload([], {}, "garbage_format")
    except ValueError:
        pass
    else:
        print("✗ step 2: unknown format accepted; should raise ValueError")
        return 1
    # And every WEBHOOK_FORMAT is accepted
    fired_norm = stats._normalize_fired([(e, "2026-W17", 0.62)])
    for fmt in stats.WEBHOOK_FORMATS:
        try:
            stats.build_webhook_payload(fired_norm, {}, fmt)
        except Exception as exc:
            print(f"✗ step 2: {fmt!r} format raised: {exc}")
            return 1
    print(f"✓ step 2: {len(stats.WEBHOOK_FORMATS)} formats accepted, "
          "unknown rejected")

    # ── Step 3: NEGATIVE — generic shape ──
    payload = stats.build_webhook_payload(
        fired_norm, {"weekly": True, "alert_week_mode": "each"}, "generic"
    )
    if "fired_alerts" not in payload or "context" not in payload \
            or "timestamp" not in payload:
        print(f"✗ step 3: generic missing required keys: {payload.keys()}")
        return 1
    if payload["fired_alerts"] != fired_norm:
        print(f"✗ step 3: generic fired_alerts mangled: {payload['fired_alerts']}")
        return 1
    if payload["context"].get("weekly") is not True:
        print(f"✗ step 3: context not preserved: {payload['context']}")
        return 1
    print("✓ step 3: generic format includes fired_alerts + context + timestamp")

    # ── Step 4: NEGATIVE — slack Block Kit ──
    multi = stats._normalize_fired([
        (stats.parse_alert_expr("too_short>0.5"), "2026-W18", 0.62),
        (stats.parse_alert_expr("filtered>0.8"), "2026-W17", 0.85),
        (stats.parse_alert_expr("skip_token>0.2"), None, 0.30),
    ])
    payload = stats.build_webhook_payload(multi, {}, "slack")
    if "text" not in payload:
        print(f"✗ step 4: slack missing 'text' fallback")
        return 1
    if "blocks" not in payload:
        print(f"✗ step 4: slack missing 'blocks'")
        return 1
    sections = [b for b in payload["blocks"] if b.get("type") == "section"]
    if len(sections) != 3:
        print(f"✗ step 4: slack has {len(sections)} sections, expected 3 "
              "(one per fired alert)")
        return 1
    # Each section must mention the expr
    section_text = " ".join(s["text"]["text"] for s in sections)
    for f in multi:
        if f["expr"] not in section_text:
            print(f"✗ step 4: slack missing expr {f['expr']!r}: {section_text}")
            return 1
    print(f"✓ step 4: slack format = text + {len(sections)} sections "
          "(Block Kit ready)")

    # ── Step 5: NEGATIVE — discord embeds (capped at 10) ──
    many = stats._normalize_fired([
        (stats.parse_alert_expr("too_short>0.5"), f"2026-W{i:02d}", 0.6)
        for i in range(15)  # 15 fired — should cap at 10
    ])
    payload = stats.build_webhook_payload(many, {}, "discord")
    if "content" not in payload or "embeds" not in payload:
        print(f"✗ step 5: discord missing required fields: {payload.keys()}")
        return 1
    if len(payload["embeds"]) != 10:
        print(f"✗ step 5: discord embeds {len(payload['embeds'])}, "
              "expected 10 (Discord cap)")
        return 1
    # Each embed has title + description
    for i, em in enumerate(payload["embeds"]):
        if "title" not in em or "description" not in em:
            print(f"✗ step 5: discord embed {i} missing title/description: {em}")
            return 1
    print(f"✓ step 5: discord format caps at 10 embeds (was 15 fired)")

    # ── Step 6: NEGATIVE — connection refused returns (False, msg) ──
    # Find a port that's almost certainly not bound (high random port,
    # then close the socket immediately). Connect attempts will be
    # refused.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    refused_port = s.getsockname()[1]
    s.close()  # port now free → connections refused
    refused_url = f"http://127.0.0.1:{refused_port}/"
    try:
        ok, msg = stats.post_webhook(refused_url, {"x": 1}, timeout_s=2.0)
    except Exception as exc:
        print(f"✗ step 6: post_webhook RAISED on refused connection: "
              f"{type(exc).__name__}: {exc}")
        return 1
    if ok:
        print(f"✗ step 6: post_webhook returned ok=True on refused: {msg}")
        return 1
    if not msg:
        print(f"✗ step 6: post_webhook ok=False but msg empty")
        return 1
    print(f"✓ step 6: connection refused → (False, {msg!r}); no exception")

    # ── Step 7: NEGATIVE — timeout honored ──
    server = socketserver.TCPServer(("127.0.0.1", 0), _SilentTimeoutHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    timeout_url = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        t0 = time.monotonic()
        ok, msg = stats.post_webhook(timeout_url, {"x": 1}, timeout_s=0.5)
        elapsed = time.monotonic() - t0
        if elapsed > 2.0:
            print(f"✗ step 7: post_webhook took {elapsed:.2f}s with "
                  "timeout_s=0.5; timeout not honored")
            return 1
        if ok:
            print(f"✗ step 7: post_webhook returned ok=True on timeout: {msg}")
            return 1
        print(f"✓ step 7: timeout honored ({elapsed:.2f}s ≤ 2s, msg={msg!r})")
    finally:
        server.shutdown()
        server.server_close()

    # ── Step 8: POSITIVE — end-to-end via local HTTP server ──
    server, url = _start_server()
    try:
        payload = stats.build_webhook_payload(fired_norm, {"test": True}, "generic")
        ok, msg = stats.post_webhook(url, payload, timeout_s=2.0)
        if not ok:
            print(f"✗ step 8: post_webhook failed: {msg}")
            return 1
        # Wait briefly for the server thread to record the request
        for _ in range(50):
            if server.received:
                break
            time.sleep(0.02)
        if len(server.received) != 1:
            print(f"✗ step 8: server got {len(server.received)} requests, "
                  "expected 1")
            return 1
        rec = server.received[0]
        if rec["headers"].get("Content-Type") != "application/json":
            print(f"✗ step 8: Content-Type wrong: {rec['headers']}")
            return 1
        body = json.loads(rec["body"])
        if body["fired_alerts"] != fired_norm:
            print(f"✗ step 8: server received wrong fired_alerts")
            return 1
        if body["context"].get("test") is not True:
            print(f"✗ step 8: context not transmitted")
            return 1
        print(f"✓ step 8: end-to-end POST verified ({msg}, payload preserved)")
    finally:
        server.shutdown()
        server.server_close()

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
