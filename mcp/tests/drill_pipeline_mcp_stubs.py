#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for D3 — 4 MCP server stubs (research / tests / deploy / observe).

Source-level + structural drill. Verifies each stub server:
  - has GET /health, GET /tools/list, POST /tools/call
  - declares the expected tools in TOOLS catalog with required_scopes
  - tool dispatch returns ok:true with canned data, ok:false with
    structured error code on unknown tool

Negative assertions:
  1. server_deploy MUST reject deploy.compose_apply without approval_id
     (§42 HARD STOP — even the stub enforces this)
  2. Every stub returns 'stub: True' marker so downstream code can
     distinguish canned from real responses
  3. /tools/call with unknown name returns error_code='tool_not_found'
     (not silent 200)
  4. server_research synthesize MUST return ≥1 source even on canned
     data (downstream §48.5 retrieval-trail contract)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


REPO = Path(__file__).resolve().parents[2]
MCP_DIR = REPO / "mcp"


def _load_app(filename: str):
    """Load mcp/<filename>.py as a module and return its FastAPI app."""
    spec = importlib.util.spec_from_file_location(f"d3_{filename}", MCP_DIR / f"{filename}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"d3_{filename}"] = mod
    spec.loader.exec_module(mod)
    return mod.app, mod


def main() -> int:
    print("-- 1. POSITIVE: 4 stub server files exist --")
    for name in ("server_research", "server_tests", "server_deploy", "server_observe"):
        path = MCP_DIR / f"{name}.py"
        assert path.exists(), f"missing {path}"
    print("  ok: server_research / server_tests / server_deploy / server_observe present")

    print("-- 2. POSITIVE: each server has /health + /tools/list + /tools/call --")
    apps = {
        "research": _load_app("server_research"),
        "tests": _load_app("server_tests"),
        "deploy": _load_app("server_deploy"),
        "observe": _load_app("server_observe"),
    }
    for label, (app, _mod) in apps.items():
        client = TestClient(app)
        for path in ("/health", "/tools/list"):
            r = client.get(path)
            assert r.status_code == 200, f"{label}: {path} → {r.status_code}"
        # /tools/call needs a body
        r = client.post("/tools/call", json={"name": "x.unknown", "arguments": {}})
        assert r.status_code == 200, f"{label}: /tools/call → {r.status_code}"
    print("  ok: all 4 stubs respond on /health + /tools/list + /tools/call")

    print("-- 3. NEGATIVE: unknown tool name → ok:false + 'tool_not_found' --")
    for label, (app, _mod) in apps.items():
        client = TestClient(app)
        r = client.post("/tools/call", json={"name": "x.unknown", "arguments": {}})
        body = r.json()
        assert body.get("ok") is False, f"{label}: unknown tool got ok:true"
        assert body["error"]["code"] == "tool_not_found", f"{label}: wrong error_code"
    print("  ok: unknown tool → tool_not_found across all 4 stubs")

    print("-- 4. POSITIVE: research.synthesize returns ≥1 source --")
    client = TestClient(apps["research"][0])
    r = client.post(
        "/tools/call",
        json={"name": "research.synthesize", "arguments": {"topic": "OAuth2 PKCE"}},
    )
    body = r.json()
    assert body["ok"] is True
    sources = body["data"]["sources"]
    assert len(sources) >= 1, "research.synthesize stub must return ≥1 source (§48.5 contract)"
    assert body["data"].get("stub") is True, "stub must self-mark"
    print(f"  ok: research returned {len(sources)} source(s) + stub marker")

    print("-- 5. NEGATIVE: deploy.compose_apply WITHOUT approval_id → §42 reject --")
    client = TestClient(apps["deploy"][0])
    r = client.post(
        "/tools/call",
        json={"name": "deploy.compose_apply",
              "arguments": {"compose_file": "docker-compose.yml"}},
    )
    body = r.json()
    assert body["ok"] is False, (
        "§42 BREACH: deploy.compose_apply accepted without approval_id"
    )
    assert body["error"]["code"] == "approval_required", (
        f"wrong error code: {body['error']}"
    )
    assert "§42" in body["error"]["message"] or "approval" in body["error"]["message"].lower()
    print("  ok: §42 hard stop survives at the MCP server boundary")

    print("-- 6. POSITIVE: deploy.compose_apply WITH approval_id → ok + rollback_handle --")
    r = client.post(
        "/tools/call",
        json={"name": "deploy.compose_apply",
              "arguments": {"approval_id": "apr-123", "compose_file": "docker-compose.yml"}},
    )
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["rollback_handle"], "rollback_handle MUST be present for B6 observer"
    print(f"  ok: applied with rollback_handle={body['data']['rollback_handle']}")

    print("-- 7. POSITIVE: tests.run_pytest (post-E5: real collect-only backing) --")
    client = TestClient(apps["tests"][0])
    # E5 made pytest real (collect-only). target='x' is not under
    # ALLOWED_TARGET_ROOTS so this now correctly returns target_not_allowed.
    # The contract this step locks is: jest stays stubbed (no Node).
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_jest", "arguments": {"target": "x"}},
    )
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["passed"] is True
    assert body["data"]["stub"] is True, "jest must remain stubbed (no Node toolchain)"
    print("  ok: tests.run_jest still stub:True (post-E5; jest deferred)")

    print("-- 8. POSITIVE: observe.compute_p95_delta returns metrics --")
    client = TestClient(apps["observe"][0])
    r = client.post(
        "/tools/call",
        json={"name": "observe.compute_p95_delta", "arguments": {"service": "frontend"}},
    )
    body = r.json()
    assert body["ok"] is True
    assert "p95_baseline_ms" in body["data"]
    assert "p95_observed_ms" in body["data"]
    print("  ok: observe.compute_p95_delta returns baseline + observed (B6 input)")

    print("-- 9. POSITIVE: every server's /health declares its stub state --")
    # Post-E2/E3/E4/E5: tests + observe servers have real backings now,
    # so 'stub' is 'partial' (tests, jest still stubbed) or 'false'
    # (observe, all real). research + deploy stay full-stub.
    expected_stub = {
        "research": "partial", # E6: real for urls-supplied, stub for topic-only
        "tests": "partial",   # ruff/pytest/mypy real, jest stub
        "deploy": "true",     # canned (stays canned for safety)
        "observe": "false",   # all 3 tools real (E3+E4)
    }
    for label, (app, _mod) in apps.items():
        client = TestClient(app)
        body = client.get("/health").json()
        stub_val = body.get("stub")
        assert stub_val == expected_stub[label], (
            f"{label}: /health stub='{stub_val}', expected '{expected_stub[label]}' "
            "(stub state must match server's actual backing reality)"
        )
    print(f"  ok: stub state declared accurately by each server: {expected_stub}")

    print()
    print("ALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
