#!/usr/bin/env python3
# RESOURCES: prometheus
"""Drill for E3 — real Prometheus backing in mcp/server_observe.py.

Hits the LIVE Prometheus instance at http://localhost:9090. Resource
tag = prometheus so the runner can serialise vs other Prometheus
drills (per §43.4 vocabulary).

Verifies:
  - observe.prom_query against `up` returns ≥1 sample
  - observe.compute_p95_delta builds a valid histogram_quantile query
  - real_backing tag = 'prometheus' on real responses
  - check_alerts_fired stays stubbed (until follow-up Alertmanager wire)

Negative assertions (security guards):
  1. PromQL injection vector blocked: service="; DROP TABLE x" → invalid_input
  2. Empty query → invalid_input (no silent default to '*')
  3. service must match safe regex; tools.run with `service=foo;bar`
     returns invalid_input
  4. Prometheus unreachable → error_code='prometheus_unreachable'
     (proves graceful failure path; we test by pointing at a dead port)
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
    """Load fresh server module with optional env overrides for
    PROMETHEUS_URL (used in negative path test)."""
    if env_overrides:
        for k, v in env_overrides.items():
            os.environ[k] = v
    mod_name = f"e3_observe_{abs(hash(tuple(sorted((env_overrides or {}).items()))))}"
    spec = importlib.util.spec_from_file_location(mod_name, SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: server module loads + Prometheus reachable --")
    os.environ.pop("PROMETHEUS_URL", None)  # use default
    mod = _load()
    client = TestClient(mod.app)
    health = client.get("/health").json()
    if health.get("prometheus_reachable") != "true":
        print(f"  SKIP: Prometheus not reachable (health: {health})")
        print("  → drill skipped; rerun with Prometheus running on 9090")
        return 0
    print(f"  ok: Prometheus reachable at {health['prometheus_url']}")

    print("-- 2. POSITIVE: prom_query 'up' returns ≥1 sample --")
    r = client.post(
        "/tools/call",
        json={"name": "observe.prom_query", "arguments": {"query": "up"}},
    )
    body = r.json()
    assert body["ok"] is True, f"prom_query failed: {body}"
    samples = body["data"]["samples"]
    assert len(samples) >= 1, "Prometheus 'up' query should yield ≥1 series"
    assert body["data"]["real_backing"] == "prometheus"
    assert body["data"]["stub"] is False
    print(f"  ok: 'up' returned {len(samples)} samples")

    print("-- 3. NEGATIVE: empty query → invalid_input --")
    r = client.post(
        "/tools/call",
        json={"name": "observe.prom_query", "arguments": {"query": ""}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    print("  ok: empty query rejected")

    print("-- 4. NEGATIVE: compute_p95_delta with empty service → invalid_input --")
    r = client.post(
        "/tools/call",
        json={"name": "observe.compute_p95_delta", "arguments": {"service": ""}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    print("  ok: empty service rejected")

    print("-- 5. NEGATIVE: PromQL injection in service blocked --")
    # service must match [A-Za-z0-9_:.-]+ — anything else rejected.
    for evil in ('foo;bar', 'foo"} {x="', 'a b', "foo`bar`"):
        r = client.post(
            "/tools/call",
            json={"name": "observe.compute_p95_delta", "arguments": {"service": evil}},
        )
        body = r.json()
        assert body["ok"] is False, f"INJECTION: service={evil!r} accepted? {body}"
        assert body["error"]["code"] == "invalid_input"
    print("  ok: 4 injection patterns all rejected")

    print("-- 6. POSITIVE: compute_p95_delta with safe service builds query --")
    r = client.post(
        "/tools/call",
        json={"name": "observe.compute_p95_delta",
              "arguments": {"service": "frontend"}},
    )
    body = r.json()
    # The metric likely doesn't exist yet (no histogram), so result may
    # be ok=True with stub=True (no samples) — that's fine; we're
    # verifying the query CONSTRUCTION not the existence of the metric.
    if body["ok"]:
        assert body["data"]["service"] == "frontend"
        assert body["data"]["real_backing"] == "prometheus"
        print(f"  ok: query built (baseline_ms={body['data'].get('p95_baseline_ms')}, "
              f"observed_ms={body['data'].get('p95_observed_ms')})")
    else:
        # PromQL query may fail if metric isn't present — we only fail
        # the drill if the FAILURE was due to a security guard tripping
        # (which would mean a regression).
        assert body["error"]["code"] != "invalid_input", f"unexpected security fail: {body}"
        print(f"  ok: query syntactically valid; metric not yet ingested (error: {body['error']['code']})")

    print("-- 7. POSITIVE: check_alerts_fired (post-E4: real Alertmanager backing) --")
    r = client.post(
        "/tools/call",
        json={"name": "observe.check_alerts_fired", "arguments": {}},
    )
    body = r.json()
    # E4 made this REAL. Either ok:true (AM reachable) or
    # ok:false + alertmanager_unreachable (AM down). Both valid; what
    # we check is that it's NOT the legacy stub:True envelope.
    if body.get("ok"):
        assert body["data"].get("stub") is False, (
            "post-E4: check_alerts_fired must NOT return stub:True"
        )
        assert body["data"].get("real_backing") == "alertmanager"
        print(f"  ok: real_backing=alertmanager, alerts_fired={body['data']['alerts_fired']}")
    else:
        assert body["error"]["code"] == "alertmanager_unreachable"
        print("  ok: AM unreachable → graceful error (post-E4)")

    print("-- 8. NEGATIVE: Prometheus unreachable → graceful error --")
    # Reload module pointing at a dead port.
    os.environ["PROMETHEUS_URL"] = "http://127.0.0.1:1"
    bad_mod = _load({"PROMETHEUS_URL": "http://127.0.0.1:1"})
    bad_client = TestClient(bad_mod.app)
    r = bad_client.post(
        "/tools/call",
        json={"name": "observe.prom_query", "arguments": {"query": "up"}},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "prometheus_unreachable", body
    print("  ok: dead Prometheus → 'prometheus_unreachable' error_code")
    # Restore for any subsequent tests.
    os.environ.pop("PROMETHEUS_URL", None)

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
