#!/usr/bin/env python3
"""Offline-safe readiness checker for Jaeger, Prometheus, and Grafana."""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
COMPOSE = REPO / "docker-compose.yml"
OBS = REPO / "infra" / "observability"
PROM = OBS / "prometheus.yml"
OTEL = OBS / "otel-config.yaml"
DATASOURCES = OBS / "grafana-datasources.yaml"
DASH_PROVIDER = OBS / "grafana-dashboards.yaml"
DASHBOARD = OBS / "grafana-dashboards" / "documind-overview.json"
ALERT_RULES = OBS / "alert-rules.yml"


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _service(name: str) -> dict[str, Any]:
    return _yaml(COMPOSE).get("services", {}).get(name, {})


def _has_healthcheck(name: str) -> bool:
    svc = _service(name)
    test = svc.get("healthcheck", {}).get("test")
    return bool(test and isinstance(test, list) and len(test) >= 2)


def _ports(name: str) -> list[str]:
    return [str(port) for port in _service(name).get("ports", [])]


def _scrape_jobs() -> set[str]:
    prom = _yaml(PROM)
    return {job.get("job_name", "") for job in prom.get("scrape_configs", [])}


def _datasource_map() -> dict[str, dict[str, Any]]:
    data = _yaml(DATASOURCES)
    return {ds.get("name", ""): ds for ds in data.get("datasources", [])}


def _live_get(url: str, timeout: float = 1.5) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 500, "status": response.status, "error": ""}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "status": None, "error": str(exc)[:200]}


def status(*, live: bool = False) -> dict[str, Any]:
    datasources = _datasource_map()
    prom_ds = datasources.get("Prometheus", {})
    jaeger_ds = datasources.get("Jaeger", {})
    jobs = _scrape_jobs()
    otel = _yaml(OTEL)
    compose_services = _yaml(COMPOSE).get("services", {})
    dashboard = _json(DASHBOARD)
    panels = json.dumps(dashboard.get("panels", []))
    required_jobs = {
        "otel-collector",
        "node-exporter",
        "cadvisor",
        "postgres-exporter",
        "inference-svc",
        "retrieval-svc",
    }
    triad = {
        "jaeger": {
            "compose_service": "jaeger" in compose_services,
            "image": _service("jaeger").get("image", ""),
            "ports": _ports("jaeger"),
            "healthcheck": _has_healthcheck("jaeger"),
            "otlp_enabled": _service("jaeger").get("environment", {}).get("COLLECTOR_OTLP_ENABLED") == "true",
            "grafana_datasource": jaeger_ds.get("type") == "jaeger" and jaeger_ds.get("url") == "http://jaeger:16686",
        },
        "prometheus": {
            "compose_service": "prometheus" in compose_services,
            "image": _service("prometheus").get("image", ""),
            "ports": _ports("prometheus"),
            "healthcheck": _has_healthcheck("prometheus"),
            "rules_loaded": "/etc/prometheus/alert-rules.yml" in _yaml(PROM).get("rule_files", []),
            "alertmanager_target": ["alertmanager:9093"]
            in [
                item.get("static_configs", [{}])[0].get("targets", [])
                for item in _yaml(PROM).get("alerting", {}).get("alertmanagers", [])
            ],
            "required_scrape_jobs_present": sorted(required_jobs & jobs),
            "missing_scrape_jobs": sorted(required_jobs - jobs),
            "grafana_datasource": prom_ds.get("type") == "prometheus" and prom_ds.get("uid") == "prometheus",
        },
        "grafana": {
            "compose_service": "grafana" in compose_services,
            "image": _service("grafana").get("image", ""),
            "ports": _ports("grafana"),
            "healthcheck": _has_healthcheck("grafana"),
            "datasources": sorted(datasources),
            "dashboard_provider": DASH_PROVIDER.exists(),
            "overview_dashboard": DASHBOARD.exists(),
            "has_prometheus_panels": "node_cpu_seconds_total" in panels and "container_cpu_usage_seconds_total" in panels,
            "has_jaeger_datasource_link": jaeger_ds.get("jsonData", {}).get("tracesToLogsV2", {}).get("datasourceUid") == "prometheus",
        },
        "otel_collector": {
            "compose_service": "otel-collector" in compose_services,
            "image": _service("otel-collector").get("image", ""),
            "ports": _ports("otel-collector"),
            "healthcheck": _has_healthcheck("otel-collector"),
            "health_extension": "health_check" in otel.get("extensions", {}),
            "traces_to_jaeger": "otlp/jaeger" in otel.get("service", {}).get("pipelines", {}).get("traces", {}).get("exporters", []),
            "metrics_to_prometheus": "prometheus" in otel.get("service", {}).get("pipelines", {}).get("metrics", {}).get("exporters", []),
        },
    }
    ready = all(
        all(value for value in component.values() if not isinstance(value, list | dict | str))
        for component in triad.values()
    ) and not triad["prometheus"]["missing_scrape_jobs"]
    payload: dict[str, Any] = {
        "triad": triad,
        "ready": ready,
        "files": {
            "compose": str(COMPOSE.relative_to(REPO)),
            "prometheus": str(PROM.relative_to(REPO)),
            "otel": str(OTEL.relative_to(REPO)),
            "grafana_datasources": str(DATASOURCES.relative_to(REPO)),
            "grafana_dashboard": str(DASHBOARD.relative_to(REPO)),
            "alert_rules": str(ALERT_RULES.relative_to(REPO)),
        },
        "recommendation": (
            "Use this offline gate in CI. Use --live after docker compose is up "
            "to check local HTTP readiness endpoints."
        ),
    }
    if live:
        payload["live"] = {
            "jaeger": _live_get("http://localhost:16686/"),
            "prometheus": _live_get("http://localhost:9090/-/ready"),
            "grafana": _live_get("http://localhost:3001/api/health"),
            "otel_metrics": _live_get("http://localhost:9464/metrics"),
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fail-on-not-ready", action="store_true")
    args = parser.parse_args()
    payload = status(live=args.live)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Observability triad ready={payload['ready']}")
        for name, component in payload["triad"].items():
            print(f"{name}: service={component.get('compose_service')} healthcheck={component.get('healthcheck')}")
    return 1 if args.fail_on_not_ready and not payload["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
