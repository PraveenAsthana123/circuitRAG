#!/usr/bin/env python3
# RESOURCES: alertmanager
"""Drill for E4 — real Alertmanager backing in observe.check_alerts_fired.

Hits live Alertmanager at http://localhost:9093/api/v2/alerts. Resource
tag = alertmanager so the runner can serialise vs other AM drills.

Verifies:
  - check_alerts_fired returns alerts_fired (int) + alerts (list)
  - real_backing tag = 'alertmanager' on real responses
  - filter_state defaults to 'active' (not 'all') — operators care
    about firing-now alerts during a soak window, not historical

Negative assertions:
  1. Alertmanager unreachable → graceful error_code='alertmanager_unreachable'
  2. /health surfaces alertmanager_reachable=true/false
  3. response shape does not include the full AM record bodies (they're
     huge); only fingerprint + labels + annotations + state surfaces
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "mcp" / "server_observe.py"


def _load(env_overrides: dict[str, str] | None = None):
    if env_overrides:
        for k, v in env_overrides.items():
            os.environ[k] = v
    mod_name = f"e4_observe_{abs(hash(tuple(sorted((env_overrides or {}).items()))))}"
    spec = importlib.util.spec_from_file_location(mod_name, SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: server loads + AM reachable on /health --")
    os.environ.pop("ALERTMANAGER_URL", None)
    mod = _load()
    client = TestClient(mod.app)
    health = client.get("/health").json()
    if health.get("alertmanager_reachable") != "true":
        print(f"  SKIP: Alertmanager not reachable (health: {health})")
        print("  → drill skipped; rerun with AM running on 9093")
        return 0
    assert "alertmanager_url" in health
    print(f"  ok: AM reachable at {health['alertmanager_url']}")

    print("-- 2. POSITIVE: check_alerts_fired returns int + list --")
    r = client.post(
        "/tools/call",
        json={"name": "observe.check_alerts_fired", "arguments": {}},
    )
    body = r.json()
    assert body["ok"] is True, f"check_alerts_fired failed: {body}"
    assert isinstance(body["data"]["alerts_fired"], int)
    assert isinstance(body["data"]["alerts"], list)
    assert body["data"]["real_backing"] == "alertmanager"
    assert body["data"]["stub"] is False
    print(f"  ok: alerts_fired={body['data']['alerts_fired']}")

    print("-- 3. POSITIVE: filter_state defaults to 'active' --")
    assert body["data"]["filter_state"] == "active", (
        f"default filter_state should be 'active', got {body['data']['filter_state']!r}"
    )
    print("  ok: default filter_state='active' (firing-now, not historical)")

    print("-- 4. POSITIVE: response shape projects to small fields per alert --")
    if body["data"]["alerts_fired"] > 0:
        alert = body["data"]["alerts"][0]
        for key in ("fingerprint", "labels", "annotations", "starts_at", "state"):
            assert key in alert, f"alert missing {key}"
        # Should NOT contain the full Alertmanager raw body fields like
        # 'receivers' or 'updatedAt' — those are operator noise.
        assert "receivers" not in alert
        print(f"  ok: alert shape projected to {list(alert.keys())}")
    else:
        print("  ok: no alerts firing; shape check skipped (vacuously true)")

    print("-- 5. NEGATIVE: AM unreachable → graceful error --")
    bad_mod = _load({"ALERTMANAGER_URL": "http://127.0.0.1:1"})
    bad_client = TestClient(bad_mod.app)
    r = bad_client.post(
        "/tools/call",
        json={"name": "observe.check_alerts_fired", "arguments": {}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "alertmanager_unreachable"
    print("  ok: dead AM → 'alertmanager_unreachable'")
    os.environ.pop("ALERTMANAGER_URL", None)

    print("-- 6. POSITIVE: /health surfaces both Prometheus + AM reachability --")
    mod2 = _load()
    client2 = TestClient(mod2.app)
    health = client2.get("/health").json()
    assert "prometheus_reachable" in health
    assert "alertmanager_reachable" in health
    assert health["stub"] == "false", (
        f"stub field should be 'false' now that all 3 tools have real backing; got {health['stub']!r}"
    )
    print(f"  ok: stub='{health['stub']}' (no canned data path live)")

    print()
    print("ALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
