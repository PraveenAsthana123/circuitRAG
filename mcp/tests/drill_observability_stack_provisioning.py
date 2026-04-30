#!/usr/bin/env python3
# RESOURCES: readonly
"""Structural drill for local observability stack provisioning.

Locks the local observability hardening points that were previously only
partially wired:

- Grafana dashboard auto-provisioning
- Prometheus alert-rules loading
- Alertmanager local routing and Prometheus alerting hookup
- Host/container exporters for deeper infra metrics

Negative assertions cover: each provisioning artifact (Grafana
dashboards yaml, Prometheus alert-rules, Alertmanager config)
exists and references the canonical local-stack endpoints; without
these, operator dashboards render empty + alerts never fire +
incidents go silent.
"""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
PROM = REPO / "infra" / "observability" / "prometheus.yml"
RULES = REPO / "infra" / "observability" / "alert-rules.yml"
ALERTMANAGER = REPO / "infra" / "observability" / "alertmanager.yml"
GRAFANA_PROVIDER = REPO / "infra" / "observability" / "grafana-dashboards.yaml"
GRAFANA_DIR = REPO / "infra" / "observability" / "grafana-dashboards"
GRAFANA_OVERVIEW = GRAFANA_DIR / "documind-overview.json"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> int:
    compose = COMPOSE.read_text(encoding="utf-8")
    prom = PROM.read_text(encoding="utf-8")
    provider = GRAFANA_PROVIDER.read_text(encoding="utf-8")
    overview = GRAFANA_OVERVIEW.read_text(encoding="utf-8")

    print("-- 1. POSITIVE: alert rules file exists --")
    assert RULES.exists(), f"missing rules file: {RULES}"
    print(f"  ok: {RULES.relative_to(REPO)}")

    print("-- 2. POSITIVE: grafana dashboard provider file exists --")
    assert GRAFANA_PROVIDER.exists(), f"missing provider file: {GRAFANA_PROVIDER}"
    print(f"  ok: {GRAFANA_PROVIDER.relative_to(REPO)}")

    print("-- 3. POSITIVE: alertmanager config file exists --")
    assert ALERTMANAGER.exists(), f"missing alertmanager file: {ALERTMANAGER}"
    print(f"  ok: {ALERTMANAGER.relative_to(REPO)}")

    print("-- 4. POSITIVE: dashboard directory and overview dashboard exist --")
    assert GRAFANA_DIR.exists(), f"missing dashboard dir: {GRAFANA_DIR}"
    assert GRAFANA_OVERVIEW.exists(), f"missing overview dashboard: {GRAFANA_OVERVIEW}"
    print(f"  ok: {GRAFANA_OVERVIEW.relative_to(REPO)}")

    print("-- 5. POSITIVE: Prometheus loads rule_files --")
    require(prom, "rule_files:", "prometheus rule_files stanza")
    require(prom, "/etc/prometheus/alert-rules.yml", "alert-rules mount path")
    print("  ok: prometheus.yml loads alert rules")

    print("-- 6. POSITIVE: Prometheus compose service mounts alert rules --")
    require(compose, "./infra/observability/alert-rules.yml:/etc/prometheus/alert-rules.yml:ro", "prometheus alert-rules volume")
    print("  ok: docker-compose mounts alert rules")

    print("-- 7. POSITIVE: Prometheus points alerting traffic at Alertmanager --")
    require(prom, "alerting:", "prometheus alerting stanza")
    require(prom, 'targets: ["alertmanager:9093"]', "prometheus alertmanager target")
    print("  ok: prometheus.yml routes alerts to alertmanager:9093")

    print("-- 8. POSITIVE: compose defines local Alertmanager with mounted config --")
    require(compose, "alertmanager:", "alertmanager service")
    require(compose, "prom/alertmanager:v0.27.0", "alertmanager image")
    require(compose, "./infra/observability/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro", "alertmanager config volume")
    print("  ok: docker-compose provisions alertmanager")

    print("-- 9. POSITIVE: compose defines node-exporter and cadvisor services --")
    require(compose, "node-exporter:", "node-exporter service")
    require(compose, "prom/node-exporter:v1.8.2", "node-exporter image")
    require(compose, "cadvisor:", "cadvisor service")
    require(compose, "gcr.io/cadvisor/cadvisor:v0.49.1", "cadvisor image")
    print("  ok: docker-compose provisions host/container exporters")

    print("-- 10. POSITIVE: Prometheus scrapes node-exporter and cadvisor --")
    require(prom, "job_name: node-exporter", "node-exporter scrape job")
    require(prom, 'targets: ["node-exporter:9100"]', "node-exporter scrape target")
    require(prom, "job_name: cadvisor", "cadvisor scrape job")
    require(prom, 'targets: ["cadvisor:8080"]', "cadvisor scrape target")
    print("  ok: prometheus.yml scrapes infra exporters")

    print("-- 11. POSITIVE: Grafana dashboard includes host/container exporter panels --")
    require(overview, "node_cpu_seconds_total", "host cpu panel query")
    require(overview, "node_memory_MemAvailable_bytes", "host memory panel query")
    require(overview, "container_cpu_usage_seconds_total", "container cpu panel query")
    require(overview, "container_memory_working_set_bytes", "container memory panel query")
    print("  ok: overview dashboard references exporter metrics")

    print("-- 12. POSITIVE: Grafana compose service mounts dashboard provider and dashboard dir --")
    require(compose, "./infra/observability/grafana-dashboards.yaml:/etc/grafana/provisioning/dashboards/dashboards.yaml:ro", "grafana provider volume")
    require(compose, "./infra/observability/grafana-dashboards:/var/lib/grafana/dashboards:ro", "grafana dashboards dir volume")
    print("  ok: docker-compose mounts grafana dashboard provisioning")

    print("-- 13. POSITIVE: Grafana provider targets the mounted dashboards path --")
    require(provider, "providers:", "grafana providers stanza")
    require(provider, "/var/lib/grafana/dashboards", "grafana dashboard path")
    print("  ok: provider points at mounted dashboards path")

    print("-- 14. NEGATIVE: no manual-import-only README claim should remain true after provisioning --")
    readme = (GRAFANA_DIR / "README.md").read_text(encoding="utf-8")
    if "import this" in readme.lower() and "auto" not in readme.lower():
        raise AssertionError("dashboard README still appears to describe import-only flow without auto-provision context")
    print("  ok: README is not import-only drift")

    print("\nALL 14 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
