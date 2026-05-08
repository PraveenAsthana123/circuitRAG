#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Jaeger + Prometheus + Grafana advanced provisioning contract.

NEGATIVE: observability components must not be marked ready without concrete wiring.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def main() -> int:
    print("-- 1. POSITIVE: observability triad status script exports status --")
    import observability_triad_status

    payload = observability_triad_status.status()
    if "triad" not in payload or "ready" not in payload:
        print(f"x bad status shape: {payload.keys()}")
        return 1
    print("  ok: status shape stable")

    print("-- 2. POSITIVE: Jaeger compose + OTLP + Grafana datasource wired --")
    jaeger = payload["triad"]["jaeger"]
    for key in ("compose_service", "healthcheck", "otlp_enabled", "grafana_datasource"):
        if not jaeger.get(key):
            print(f"x jaeger missing {key}: {jaeger}")
            return 1
    if "16686:16686" not in jaeger["ports"]:
        print(f"x jaeger UI port not exposed: {jaeger['ports']}")
        return 1
    print("  ok: Jaeger ready path wired")

    print("-- 3. POSITIVE: Prometheus compose + rules + alertmanager wired --")
    prom = payload["triad"]["prometheus"]
    for key in ("compose_service", "healthcheck", "rules_loaded", "alertmanager_target", "grafana_datasource"):
        if not prom.get(key):
            print(f"x prometheus missing {key}: {prom}")
            return 1
    if prom["missing_scrape_jobs"]:
        print(f"x missing scrape jobs: {prom['missing_scrape_jobs']}")
        return 1
    print("  ok: Prometheus ready path wired")

    print("-- 4. POSITIVE: Grafana datasources, dashboards, and trace/log link wired --")
    grafana = payload["triad"]["grafana"]
    for key in (
        "compose_service",
        "healthcheck",
        "dashboard_provider",
        "overview_dashboard",
        "has_prometheus_panels",
        "has_jaeger_datasource_link",
    ):
        if not grafana.get(key):
            print(f"x grafana missing {key}: {grafana}")
            return 1
    if sorted(grafana["datasources"]) != ["Jaeger", "Prometheus"]:
        print(f"x unexpected grafana datasources: {grafana['datasources']}")
        return 1
    print("  ok: Grafana ready path wired")

    print("-- 5. POSITIVE: OTel collector fans traces to Jaeger and metrics to Prometheus --")
    otel = payload["triad"]["otel_collector"]
    for key in ("compose_service", "healthcheck", "health_extension", "traces_to_jaeger", "metrics_to_prometheus"):
        if not otel.get(key):
            print(f"x otel collector missing {key}: {otel}")
            return 1
    print("  ok: OTel fan-out path wired")

    print("-- 6. NEGATIVE: triad is ready only when no required scrape job is missing --")
    if not payload["ready"]:
        print(f"x triad not ready: {payload}")
        return 1
    print("  ok: offline readiness gate is green")

    print("\nALL 6 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
