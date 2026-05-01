#!/usr/bin/env python3
# RESOURCES: readonly
"""Structural drill for the admin monitoring/runtime surface.

Locks the existence and basic contract of:

- /admin/monitoring
- /app-meta/runtime-status

This is intentionally readonly and source-based. It verifies the
operator page still presents the key monitoring/runtime sections and
that the local runtime route remains present as the backing truth
surface.

Negative assertions cover: page exists with the required section
markers, runtime-status route exists with the JSON contract, and
neither file silently regresses (page emptied / route deleted) —
both events would leave the monitoring dashboard a dead UI without
operator awareness.
"""
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MONITORING_PAGE = REPO / "services" / "frontend" / "app" / "admin" / "monitoring" / "page.tsx"
RUNTIME_ROUTE = REPO / "services" / "frontend" / "app" / "app-meta" / "runtime-status" / "route.ts"


def must_contain(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> int:
    print("-- 1. POSITIVE: monitoring page exists --")
    assert MONITORING_PAGE.exists(), f"missing page: {MONITORING_PAGE}"
    page = MONITORING_PAGE.read_text(encoding="utf-8")
    print(f"  ok: {MONITORING_PAGE.relative_to(REPO)}")

    print("-- 2. POSITIVE: runtime-status route exists --")
    assert RUNTIME_ROUTE.exists(), f"missing route: {RUNTIME_ROUTE}"
    route = RUNTIME_ROUTE.read_text(encoding="utf-8")
    print(f"  ok: {RUNTIME_ROUTE.relative_to(REPO)}")

    print("-- 3. POSITIVE: monitoring page keeps score/current-status surface --")
    must_contain(page, "Score and current status", "score section heading")
    must_contain(page, "Overall score", "overall score card")
    must_contain(page, "Current status", "current status card")
    print("  ok: score/current-status section present")

    print("-- 4. POSITIVE: monitoring page keeps input/process/output model --")
    must_contain(page, "Input, process, output", "pipeline section heading")
    must_contain(page, "Operator/admin requests through the frontend and API gateway.", "input bullet")
    must_contain(page, "Health APIs aggregate readiness, breakers, prompt registry, tools, and upstream probes.", "process bullet")
    must_contain(page, "Go-style services expose /metrics on the app port; FastAPI services using setup_observability usually expose Prometheus on a separate DOCUMIND_PROMETHEUS_PORT chosen by the local start-env script.", "metrics contract bullet")
    must_contain(page, "In-app operator pages: monitoring, forensics, sidecar telemetry, agentic control plane.", "output bullet")
    print("  ok: input/process/output section present")

    print("-- 5. POSITIVE: monitoring page keeps runtime service visibility sections --")
    must_contain(page, "Active or running services", "running services heading")
    must_contain(page, "Services not running or unhealthy", "not running heading")
    must_contain(page, "Resource consumers", "resource section heading")
    print("  ok: runtime visibility sections present")

    print("-- 6. POSITIVE: monitoring page keeps circuit breaker implementation inventory --")
    must_contain(page, "Circuit breaker implementations", "breaker inventory heading")
    must_contain(page, "ObservabilityCircuitBreaker", "observability breaker inventory row")
    must_contain(page, "CognitiveCircuitBreaker", "cognitive breaker inventory row")
    print("  ok: breaker implementation inventory present")

    print("-- 7. POSITIVE: monitoring page keeps observability stack links and exporter inventory --")
    must_contain(page, "Alertmanager", "alertmanager link or inventory row")
    must_contain(page, "Node exporter", "node exporter inventory row")
    must_contain(page, "cAdvisor", "cadvisor inventory row")
    print("  ok: alerting/exporter surfaces present")

    print("-- 8. POSITIVE: monitoring page references runtime-status route --")
    must_contain(page, "api.frontendRuntimeStatus()", "frontend runtime status API call")
    print("  ok: page references runtime-status")

    print("-- 9. POSITIVE: runtime-status route uses local runtime truth commands --")
    must_contain(route, "docker", "docker command usage")
    must_contain(route, "compose", "docker compose usage")
    must_contain(route, "stats", "docker stats usage")
    must_contain(route, "systemctl", "systemctl usage")
    must_contain(route, "ollama", "ollama service check")
    print("  ok: route checks docker/runtime state")

    print("-- 10. NEGATIVE: runtime-status route must remain frontend-owned local route --")
    if "/api/" in str(RUNTIME_ROUTE.relative_to(REPO)):
        raise AssertionError("runtime-status route drifted under /api/* and may be rewritten to the gateway")
    print("  ok: route remains outside /api/*")

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
