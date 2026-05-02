#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: §35 DR Metrics L2→L3 dashboard endpoint exists and is honest.

The previous drill locked target definitions in
``libs/py/documind_core/dr_metrics.py``. This drill locks the next
maturity step: a runtime admin surface exposes current-vs-target rows
without fabricating current recovery numbers before the quarterly DR
drill exists.

Eight steps. Four negative assertions.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
MAIN_FILE = SVC / "app" / "main.py"
MODELS_FILE = SVC / "app" / "models.py"
LIBS = REPO / "libs" / "py"


def main() -> int:
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(SVC))
    sys.path.insert(0, str(LIBS))
    os.environ.setdefault("DOCUMIND_PROMETHEUS_PORT", "0")

    from app.main import app
    from fastapi.testclient import TestClient

    print("-- 1. POSITIVE: admin DR targets route is registered in main.py --")
    main_text = MAIN_FILE.read_text(encoding="utf-8")
    assert "/api/v1/admin/dr-targets" in main_text, "missing /api/v1/admin/dr-targets route"
    assert "get_admin_dr_targets" in main_text, "missing get_admin_dr_targets handler"
    print("  ok: route + handler present")

    print("-- 2. POSITIVE: endpoint imports the canonical target source --")
    assert "from documind_core.dr_metrics import all_targets" in main_text, (
        "endpoint must reuse documind_core.dr_metrics.all_targets"
    )
    print("  ok: endpoint reuses all_targets()")

    print("-- 3. POSITIVE: response models lock the dashboard schema --")
    models_text = MODELS_FILE.read_text(encoding="utf-8")
    for needle in ("DrTargetsDashboardView", "DrTargetTierDashboardView", "DrMetricComparisonView"):
        assert needle in models_text, f"missing response model {needle}"
    print("  ok: dashboard response models present")

    print("-- 4. POSITIVE: TestClient returns dashboard payload --")
    client = TestClient(app)
    resp = client.get("/api/v1/admin/dr-targets")
    assert resp.status_code == 200, f"unexpected status {resp.status_code}: {resp.text[:200]}"
    payload = resp.json()
    print("  ok: endpoint returns HTTP 200")

    print("-- 5. NEGATIVE: every tier must be exposed, in governance order --")
    tiers = payload["tiers"]
    actual_order = [t["tier"] for t in tiers]
    assert actual_order == ["critical", "important", "standard"], (
        f"tier order drifted: {actual_order}"
    )
    print(f"  ok: tier order = {actual_order}")

    print("-- 6. NEGATIVE: every tier exposes exactly five DR metrics --")
    expected_metrics = {"rto", "rpo", "mttd", "mttr", "failover"}
    for tier in tiers:
        metrics = {m["metric"] for m in tier["measurements"]}
        assert metrics == expected_metrics, f"{tier['tier']} metrics drifted: {metrics}"
    print("  ok: rto/rpo/mttd/mttr/failover exposed for every tier")

    print("-- 7. NEGATIVE: current values are not fabricated before the L4 drill --")
    assert payload["current_measurement_source"] is None, (
        "current_measurement_source must stay null until real drill evidence exists"
    )
    for tier in tiers:
        for measurement in tier["measurements"]:
            assert measurement["current_seconds"] is None, (
                f"{tier['tier']} {measurement['metric']} fabricated current_seconds"
            )
            assert measurement["status"] == "not_measured", (
                f"{tier['tier']} {measurement['metric']} must be not_measured before L4"
            )
    print("  ok: current values are explicit null/not_measured")

    print("-- 8. NEGATIVE: target values match the canonical dr_metrics module --")
    from documind_core.dr_metrics import all_targets

    expected_by_tier = {
        target.tier: {
            "rto": target.rto_seconds,
            "rpo": target.rpo_seconds,
            "mttd": target.mttd_seconds,
            "mttr": target.mttr_seconds,
            "failover": target.failover_seconds,
        }
        for target in all_targets()
    }
    for tier in tiers:
        actual = {m["metric"]: m["target_seconds"] for m in tier["measurements"]}
        assert actual == expected_by_tier[tier["tier"]], (
            f"{tier['tier']} target drift: expected {expected_by_tier[tier['tier']]}, got {actual}"
        )
    print("  ok: endpoint targets match documind_core.dr_metrics")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
