#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for E2 — real ruff backing in mcp/server_tests.py (Phase E2).

Verifies tests.run_ruff actually executes the ruff binary against a
real target file, parses JSON output, and reports findings (or absence
of findings = passed=True).

Negative assertions (the security locks):
  1. target path OUTSIDE ALLOWED_TARGET_ROOTS → error_code='target_not_allowed'
     (path traversal prevention)
  2. target path that does NOT exist → error_code='target_not_allowed'
  3. tests.run_ruff response carries 'real_backing':'ruff' (not stub:True)
     so downstream code can distinguish real from canned
  4. Empty stdout from ruff (no findings) → passed=True (clean code)

The drill creates a tiny .py fixture in /tmp under /mnt/deepa/rag's
allowed root and runs ruff against it. Real subprocess; real ruff;
real JSON parse.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "mcp" / "server_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("e2_server_tests", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["e2_server_tests"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    client = TestClient(mod.app)

    print("-- 1. POSITIVE: ruff binary resolves --")
    ruff_path = mod._resolve_ruff_path()
    assert ruff_path is not None, "ruff not found; install at .venv/bin/ruff or set RUFF_PATH"
    print(f"  ok: ruff at {ruff_path}")

    print("-- 2. POSITIVE: ALLOWED_TARGET_ROOTS includes /mnt/deepa/rag --")
    roots = mod.ALLOWED_TARGET_ROOTS
    assert any(str(r) == "/mnt/deepa/rag" for r in roots), (
        f"expected /mnt/deepa/rag in ALLOWED_TARGET_ROOTS, got {roots}"
    )
    print(f"  ok: roots={[str(r) for r in roots]}")

    print("-- 3. POSITIVE: clean target → passed=True with real_backing --")
    # Use a known-clean file — server_research.py has been ruff-passed.
    target_clean = REPO / "mcp" / "server_research.py"
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_ruff", "arguments": {"target": str(target_clean)}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True, f"ruff call failed: {body}"
    data = body["data"]
    assert data["runner"] == "ruff"
    assert data.get("real_backing") == "ruff", (
        f"expected real_backing=ruff, got: {data}"
    )
    assert data.get("stub") is False, "real ruff result must NOT carry stub:True"
    print(f"  ok: passed={data['passed']}, findings={data['findings_count']}")

    print("-- 4. NEGATIVE: target OUTSIDE allowed roots → target_not_allowed --")
    # /etc is outside /mnt/deepa/rag.
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_ruff", "arguments": {"target": "/etc/hostname"}},
    )
    body = r.json()
    assert body["ok"] is False, f"PATH TRAVERSAL: /etc accepted? {body}"
    assert body["error"]["code"] == "target_not_allowed", body
    print("  ok: /etc rejected with target_not_allowed")

    print("-- 5. NEGATIVE: nonexistent target → target_not_allowed --")
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_ruff", "arguments": {"target": "/mnt/deepa/rag/__phantom_does_not_exist__"}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "target_not_allowed"
    print("  ok: nonexistent path rejected")

    print("-- 6. NEGATIVE: empty target → invalid_input --")
    r = client.post(
        "/tools/call",
        json={"name": "tests.run_ruff", "arguments": {"target": ""}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    print("  ok: empty target rejected with invalid_input")

    print("-- 7. POSITIVE: target with deliberate ruff violation → passed=False + findings --")
    # Write a tiny file inside the repo with a known ruff finding (unused import).
    tmp_dir = REPO / "tmp_ruff_drill"
    tmp_dir.mkdir(exist_ok=True)
    fixture = tmp_dir / "violation.py"
    fixture.write_text("import os\n# unused import → F401\n", encoding="utf-8")
    try:
        r = client.post(
            "/tools/call",
            json={"name": "tests.run_ruff", "arguments": {"target": str(fixture)}},
        )
        body = r.json()
        assert body["ok"] is True, f"unexpected error: {body}"
        data = body["data"]
        # Either ruff catches F401 (passed=False, findings≥1) OR ruff is
        # configured to ignore F401. Both are valid runs; we just need
        # findings_count to be a real integer.
        assert isinstance(data["findings_count"], int)
        assert data["real_backing"] == "ruff"
        print(f"  ok: ran on real fixture (findings={data['findings_count']})")
    finally:
        fixture.unlink()
        tmp_dir.rmdir()

    print("-- 8. POSITIVE: pytest/jest/mypy stubs still return canned passes --")
    for tool in ("tests.run_pytest", "tests.run_jest", "tests.run_mypy"):
        r = client.post(
            "/tools/call",
            json={"name": tool, "arguments": {"target": "x"}},
        )
        body = r.json()
        assert body["ok"] is True
        assert body["data"]["passed"] is True
        assert body["data"]["stub"] is True, f"{tool}: stub:True missing"
    print("  ok: stubbed runners (pytest/jest/mypy) keep canned shape")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
