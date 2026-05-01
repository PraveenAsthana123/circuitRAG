#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for E5 — real pytest --collect-only + mypy backing.

Verifies tests.run_pytest invokes pytest in collect-only mode (lists
tests without running them) and tests.run_mypy invokes mypy with
no-error-summary. Both honour the same target-validation security
guards as ruff (E2).

Negative assertions:
  1. pytest target outside ALLOWED_TARGET_ROOTS → target_not_allowed
  2. mypy target outside ALLOWED_TARGET_ROOTS → target_not_allowed
  3. pytest result MUST tag mode='collect-only' (no full execution
     could happen via this server until execution-mode commit)
  4. jest stays stubbed (no Node toolchain bundled)
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "mcp" / "server_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("e5_server_tests", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["e5_server_tests"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    client = TestClient(mod.app)

    print("-- 1. POSITIVE: pytest binary resolves --")
    assert mod._resolve_pytest_path() is not None, "pytest not found"
    print(f"  ok: pytest at {mod._resolve_pytest_path()}")

    print("-- 2. POSITIVE: mypy binary resolves --")
    assert mod._resolve_mypy_path() is not None, "mypy not found"
    print(f"  ok: mypy at {mod._resolve_mypy_path()}")

    print("-- 3. POSITIVE: pytest --collect-only against existing tests dir --")
    tests_target = REPO / "services" / "agent-orchestrator-svc" / "tests"
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_pytest", "arguments": {"target": str(tests_target)}},
    )
    body = r.json()
    assert body["ok"] is True, f"pytest collect failed: {body}"
    data = body["data"]
    assert data["mode"] == "collect-only", (
        f"§E5 contract: mode must be 'collect-only' (no full exec); got {data.get('mode')}"
    )
    assert data["real_backing"] == "pytest"
    assert data["stub"] is False
    assert isinstance(data["collected_count"], int)
    print(f"  ok: collected {data['collected_count']} tests via pytest --collect-only")

    print("-- 4. NEGATIVE: pytest target OUTSIDE roots → target_not_allowed --")
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_pytest", "arguments": {"target": "/etc"}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "target_not_allowed"
    print("  ok: /etc rejected")

    print("-- 5. POSITIVE: mypy on a clean source file --")
    target = REPO / "services" / "agent-orchestrator-svc" / "app" / "model_router.py"
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_mypy", "arguments": {"target": str(target)}},
    )
    body = r.json()
    assert body["ok"] is True, f"mypy failed: {body}"
    data = body["data"]
    assert data["real_backing"] == "mypy"
    assert data["stub"] is False
    assert isinstance(data["findings_count"], int)
    print(f"  ok: mypy ran (findings={data['findings_count']})")

    print("-- 6. NEGATIVE: mypy target OUTSIDE roots → target_not_allowed --")
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_mypy", "arguments": {"target": "/etc/hostname"}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "target_not_allowed"
    print("  ok: /etc rejected")

    print("-- 7. POSITIVE: jest stays stubbed --")
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_jest", "arguments": {"target": "x"}},
    )
    body = r.json()
    assert body["data"]["stub"] is True, "jest must remain stubbed (no Node toolchain bundled)"
    print("  ok: jest still stub:True")

    print("-- 8. NEGATIVE: pytest empty target → invalid_input --")
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_pytest", "arguments": {"target": ""}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    print("  ok: empty target rejected")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
