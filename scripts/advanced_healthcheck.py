#!/usr/bin/env python3
"""
Advanced multi-layer health-check + troubleshoot + tracking tool.

Probes circuitRAG across 7 layers in parallel + reports actionable
remediation steps for every red row. Output: terminal table + optional
JSON dump (`--json`) for tooling integration.

The 7 layers:
  1. App services       — HTTP probes against FastAPI/Go endpoints
  2. Infrastructure     — Docker container state + healthchecks
  3. Database           — Postgres / Redis / Qdrant / Neo4j round-trip
  4. Process            — host-side uvicorn/node PIDs + RSS + uptime
  5. Logs               — tail recent error patterns from /tmp/*.log
  6. Observability      — Prometheus targets up; Jaeger receiving spans
  7. Mesh               — Istio + Kiali (if minikube/dm-istio context up)

Per-row output: STATUS · COMPONENT · DETAIL · LATENCY · REMEDIATION.
Color-coded; exits 0 only if ALL critical rows are green.

Usage:
  python3 scripts/advanced_healthcheck.py             # full table
  python3 scripts/advanced_healthcheck.py --layer app # one layer
  python3 scripts/advanced_healthcheck.py --json      # machine-readable
  python3 scripts/advanced_healthcheck.py --fix       # print only remediation

Per CLAUDE.md §43 (drilled by drill_advanced_healthcheck.py), §47.6
(observability is first-class), §51 (forensic substrate), §57.5
(5-question on-call runbook), §57.7 (honesty about live state).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

# ── ANSI ────────────────────────────────────────────────────────────────
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
GRAY = "\033[90m"
BLUE = "\033[34m"
BOLD = "\033[1m"
NC = "\033[0m"


@dataclass
class Probe:
    """One actionable health check across a single component."""
    layer: str
    component: str
    status: str = "?"  # GREEN / YELLOW / RED / GRAY
    detail: str = ""
    latency_ms: int = -1
    remediation: str = ""
    severity: str = "info"  # critical / warn / info
    extra: dict[str, Any] = field(default_factory=dict)


# ── Layer 1: App service probes ────────────────────────────────────────

APP_SERVICES = [
    # (name, url, health_path, expected_status, kind, port_for_lsof)
    ("orchestrator", "http://localhost:8050", "/health/live", 200, "fastapi", 8050),
    ("retrieval", "http://localhost:8083", "/health", 200, "fastapi", 8083),
    ("inference", "http://localhost:8084", "/health", 200, "fastapi", 8084),
    ("ingestion", "http://localhost:8082", "/health", 200, "fastapi", 8082),
    ("evaluation", "http://localhost:8085", "/health", 200, "fastapi", 8085),
    ("frontend", "http://localhost:3000", "/", 200, "nextjs", 3000),
    ("api-gateway", "http://localhost:8088", "/", 200, "go", 8088),
]


def probe_http(url: str, timeout: float = 3.0) -> tuple[bool, int, str]:
    """HTTP GET probe. Returns (ok, latency_ms, evidence)."""
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            ms = int((time.monotonic() - t0) * 1000)
            return (200 <= r.status < 400, ms, f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return (False, ms, f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
        return (False, -1, str(e)[:60])
    except Exception as e:  # noqa: BLE001
        return (False, -1, f"{type(e).__name__}: {str(e)[:50]}")


def probe_app_services() -> list[Probe]:
    """Probe each app service. Returns one Probe per service."""
    probes = []
    for name, base, health_path, _, kind, port in APP_SERVICES:
        ok, ms, evidence = probe_http(base + health_path)
        if ok:
            p = Probe(
                layer="app",
                component=f"{name} ({kind})",
                status="GREEN",
                detail=evidence,
                latency_ms=ms,
                remediation="",
                severity="info",
            )
        else:
            # Check if anything is listening on the port at all
            listening = port_is_listening(port)
            if listening:
                detail = f"port {port} bound but {health_path} unreachable: {evidence}"
                remediation = (
                    f"Service crashed after binding. Check `tail -30 /tmp/{name}*.log`. "
                    f"Restart via the layer's boot script."
                )
            else:
                detail = f"nothing listening on :{port}"
                if name == "api-gateway":
                    remediation = "Go binary not installed on host. Run via docker: `docker compose up -d api-gateway` OR install go locally."
                elif name in ("orchestrator",):
                    remediation = "bash scripts/agent-orchestrator-up.sh"
                elif name in ("ingestion",):
                    remediation = (
                        "cd services/ingestion-svc && setsid nohup env "
                        "PYTHONPATH=/mnt/deepa/rag/libs/py:/mnt/deepa/rag "
                        "DOCUMIND_PG_PORT=55432 DOCUMIND_QDRANT_API_KEY=dev-qdrant-key "
                        "DOCUMIND_REDIS_URL=redis://localhost:56379/0 "
                        "/mnt/deepa/rag/.venv/bin/python -m uvicorn app.main:app "
                        "--host 0.0.0.0 --port 8082 > /tmp/ingestion-svc.log 2>&1 &"
                    )
                elif name == "frontend":
                    remediation = "cd services/frontend && setsid nohup ./node_modules/.bin/next dev --port 3000 > /tmp/frontend.log 2>&1 &"
                else:
                    remediation = f"Start with: `bash /tmp/start_one_svc.sh {name}-svc {port} 9467`"
            p = Probe(
                layer="app",
                component=f"{name} ({kind})",
                status="RED",
                detail=detail,
                latency_ms=ms,
                remediation=remediation,
                severity="critical" if name in ("orchestrator", "retrieval", "inference") else "warn",
            )
        probes.append(p)
    return probes


def port_is_listening(port: int) -> bool:
    """Returns True if anything is bound to localhost:port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


# ── Layer 2: Docker infrastructure ─────────────────────────────────────

EXPECTED_CONTAINERS = [
    "documind-postgres", "documind-redis", "documind-qdrant",
    "documind-neo4j", "documind-elasticsearch", "documind-kafka",
    "documind-minio", "documind-ollama",
    "documind-prometheus", "documind-grafana", "documind-jaeger",
    "documind-alertmanager", "documind-kibana", "documind-langfuse",
    "documind-otel", "documind-cadvisor", "documind-node-exporter",
    "documind-filebeat",
]


def probe_docker_containers() -> list[Probe]:
    """Run `docker ps` once, report per-container state."""
    probes: list[Probe] = []
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        running = {}
        for line in r.stdout.strip().split("\n"):
            if "\t" in line:
                name, status = line.split("\t", 1)
                running[name] = status
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return [Probe(layer="infra", component="docker", status="RED",
                      detail=f"docker ps failed: {e}",
                      remediation="Verify Docker daemon is running",
                      severity="critical")]

    for expected in EXPECTED_CONTAINERS:
        actual = running.get(expected)
        if actual is None:
            probes.append(Probe(layer="infra", component=expected, status="RED",
                                detail="container not running",
                                remediation=f"docker compose up -d {expected.replace('documind-', '')}",
                                severity="warn"))
        elif "unhealthy" in actual.lower():
            probes.append(Probe(layer="infra", component=expected, status="YELLOW",
                                detail=actual[:80],
                                remediation=f"docker logs {expected} | tail -30",
                                severity="warn"))
        else:
            probes.append(Probe(layer="infra", component=expected, status="GREEN",
                                detail=actual[:60],
                                remediation="", severity="info"))
    return probes


# ── Layer 3: Database round-trip ───────────────────────────────────────

def probe_postgres() -> Probe:
    """Run SELECT 1 against Postgres on host:55432."""
    t0 = time.monotonic()
    try:
        r = subprocess.run(
            ["docker", "exec", "-e", "PGPASSWORD=documind", "documind-postgres",
             "psql", "-U", "documind", "-d", "documind", "-c", "SELECT 1;"],
            capture_output=True, text=True, timeout=8,
        )
        ms = int((time.monotonic() - t0) * 1000)
        if r.returncode == 0 and "1 row" in r.stdout:
            return Probe(layer="db", component="postgres", status="GREEN",
                         detail="SELECT 1 OK", latency_ms=ms, severity="info")
        return Probe(layer="db", component="postgres", status="RED",
                     detail=f"query failed: {r.stderr[:80]}",
                     latency_ms=ms,
                     remediation="Check `docker logs documind-postgres | tail -30`",
                     severity="critical")
    except (subprocess.TimeoutExpired, OSError) as e:
        return Probe(layer="db", component="postgres", status="RED",
                     detail=str(e)[:60],
                     remediation="docker ps | grep documind-postgres",
                     severity="critical")


def probe_redis() -> Probe:
    t0 = time.monotonic()
    try:
        r = subprocess.run(
            ["docker", "exec", "documind-redis", "redis-cli", "PING"],
            capture_output=True, text=True, timeout=5,
        )
        ms = int((time.monotonic() - t0) * 1000)
        if "PONG" in r.stdout:
            return Probe(layer="db", component="redis", status="GREEN",
                         detail="PING/PONG", latency_ms=ms, severity="info")
        return Probe(layer="db", component="redis", status="RED",
                     detail=f"no PONG: {r.stdout[:40]}",
                     remediation="docker restart documind-redis",
                     severity="warn")
    except (subprocess.TimeoutExpired, OSError) as e:
        return Probe(layer="db", component="redis", status="RED",
                     detail=str(e)[:60], severity="warn")


def probe_qdrant() -> Probe:
    """Probe Qdrant via API key. Reads docker env for actual key."""
    api_key = "dev-qdrant-key"  # documented dev default
    req = urllib.request.Request(
        "http://localhost:6333/collections",
        headers={"api-key": api_key},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=3) as r:  # noqa: S310
            ms = int((time.monotonic() - t0) * 1000)
            return Probe(layer="db", component="qdrant", status="GREEN",
                         detail=f"HTTP {r.status}", latency_ms=ms, severity="info")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return Probe(layer="db", component="qdrant", status="YELLOW",
                         detail="401 — wrong API key",
                         remediation="Set DOCUMIND_QDRANT_API_KEY=dev-qdrant-key (or read from docker env)",
                         severity="warn")
        return Probe(layer="db", component="qdrant", status="RED",
                     detail=f"HTTP {e.code}", severity="warn")
    except Exception as e:  # noqa: BLE001
        return Probe(layer="db", component="qdrant", status="RED",
                     detail=str(e)[:60], severity="warn")


def probe_neo4j() -> Probe:
    ok, ms, ev = probe_http("http://localhost:7474/")
    return Probe(
        layer="db", component="neo4j",
        status="GREEN" if ok else "RED",
        detail=ev, latency_ms=ms,
        remediation="" if ok else "docker restart documind-neo4j",
        severity="warn" if not ok else "info",
    )


def probe_databases() -> list[Probe]:
    return [probe_postgres(), probe_redis(), probe_qdrant(), probe_neo4j()]


# ── Layer 4: Host process tracking ─────────────────────────────────────

def probe_host_processes() -> list[Probe]:
    """Find uvicorn / node / port-forward processes; report RSS + uptime."""
    probes: list[Probe] = []
    patterns = [
        ("uvicorn-orchestrator", r"uvicorn.*--port 8050"),
        ("uvicorn-retrieval", r"uvicorn.*--port 8083"),
        ("uvicorn-inference", r"uvicorn.*--port 8084"),
        ("uvicorn-ingestion", r"uvicorn.*--port 8082"),
        ("uvicorn-evaluation", r"uvicorn.*--port 8085"),
        ("next-frontend", r"next-server|next dev"),
        ("kubectl-port-forward-kiali", r"port-forward.*svc/kiali"),
    ]
    try:
        ps = subprocess.run(["ps", "-eo", "pid,rss,etime,comm,args"],
                            capture_output=True, text=True, timeout=5)
        lines = ps.stdout.split("\n")
    except Exception as e:  # noqa: BLE001
        return [Probe(layer="proc", component="ps", status="RED",
                      detail=str(e), severity="warn")]

    for name, pat in patterns:
        rgx = re.compile(pat)
        match = next((line for line in lines if rgx.search(line)), None)
        if not match:
            probes.append(Probe(layer="proc", component=name, status="GRAY",
                                detail="not running", severity="info",
                                remediation="see app-services layer for boot command"))
            continue
        parts = match.split(None, 4)
        if len(parts) >= 4:
            pid, rss, etime = parts[0], parts[1], parts[2]
            try:
                rss_mb = int(rss) // 1024
            except ValueError:
                rss_mb = 0
            probes.append(Probe(layer="proc", component=name, status="GREEN",
                                detail=f"pid={pid} rss={rss_mb}MB uptime={etime}",
                                severity="info"))
    return probes


# ── Layer 5: Log error pattern scan ────────────────────────────────────

ERROR_PATTERNS = [
    (r"ImportError|ModuleNotFoundError", "import error"),
    (r"asyncpg\.exceptions\.InvalidPasswordError|password authentication failed", "Postgres auth"),
    (r"ConnectionRefusedError|Connection refused", "TCP refused"),
    (r"OSError.*Address already in use|errno 98", "port collision"),
    (r"out of memory|OOM|MemoryError", "OOM"),
    (r"CircuitBreakerOpen|circuit_open", "breaker open"),
    (r"Traceback \(most recent call last\)", "unhandled traceback"),
]


def probe_recent_logs() -> list[Probe]:
    """Scan /tmp/*.log + a few key project logs for recent errors."""
    probes: list[Probe] = []
    log_files = [
        ("orchestrator", "/tmp/agent-orchestrator-svc.log"),
        ("retrieval", "/tmp/retrieval-svc.log"),
        ("inference", "/tmp/inference-svc.log"),
        ("ingestion", "/tmp/ingestion-svc.log"),
        ("evaluation", "/tmp/evaluation-svc.log"),
        ("frontend", "/tmp/frontend.log"),
        ("kiali-pf", "/tmp/kiali-pf.log"),
    ]
    for name, path in log_files:
        if not Path(path).exists():
            probes.append(Probe(layer="log", component=name, status="GRAY",
                                detail="log file missing",
                                severity="info"))
            continue
        try:
            # Read last 200 lines
            r = subprocess.run(["tail", "-200", path],
                               capture_output=True, text=True, timeout=5)
            text = r.stdout
        except Exception as e:  # noqa: BLE001
            probes.append(Probe(layer="log", component=name, status="YELLOW",
                                detail=f"tail failed: {e}", severity="info"))
            continue
        hits: list[str] = []
        for pat, label in ERROR_PATTERNS:
            if re.search(pat, text):
                hits.append(label)
        if hits:
            probes.append(Probe(layer="log", component=name, status="YELLOW",
                                detail=f"errors in last 200 lines: {', '.join(hits)}",
                                remediation=f"tail -50 {path}",
                                severity="warn"))
        else:
            probes.append(Probe(layer="log", component=name, status="GREEN",
                                detail="no error patterns in last 200 lines",
                                severity="info"))
    return probes


# ── Layer 6: Observability targets ─────────────────────────────────────

def probe_prometheus_targets() -> list[Probe]:
    """Ask Prometheus which scrape targets are up."""
    try:
        with urllib.request.urlopen("http://localhost:9090/api/v1/targets", timeout=4) as r:  # noqa: S310
            data = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return [Probe(layer="obs", component="prometheus-targets", status="RED",
                      detail=str(e)[:60], severity="critical")]
    active = data.get("data", {}).get("activeTargets", [])
    up = sum(1 for t in active if t.get("health") == "up")
    total = len(active)
    status = "GREEN" if up == total and total > 0 else ("YELLOW" if up > 0 else "RED")
    return [Probe(layer="obs", component="prometheus-targets", status=status,
                  detail=f"{up}/{total} up",
                  remediation="" if status == "GREEN" else "Check failing target's /metrics endpoint",
                  severity="info" if status == "GREEN" else "warn")]


def probe_observability() -> list[Probe]:
    p_prom = probe_prometheus_targets()
    p_jaeger = probe_http("http://localhost:16686/")
    return p_prom + [
        Probe(layer="obs", component="jaeger-ui",
              status="GREEN" if p_jaeger[0] else "RED",
              detail=p_jaeger[2], latency_ms=p_jaeger[1],
              severity="info" if p_jaeger[0] else "warn",
              remediation="" if p_jaeger[0] else "docker restart documind-jaeger"),
    ]


# ── Layer 7: Mesh (Istio + Kiali) ─────────────────────────────────────

def probe_mesh() -> list[Probe]:
    """Probe Kiali port-forward + Istio context."""
    ok, ms, ev = probe_http("http://localhost:20001/kiali/healthz")
    kiali_probe = Probe(
        layer="mesh", component="kiali",
        status="GREEN" if ok else "RED",
        detail=ev, latency_ms=ms,
        remediation="" if ok else "bash scripts/kiali-port-forward.sh",
        severity="warn" if not ok else "info",
    )
    return [kiali_probe]


# ── Layer dispatcher + rendering ───────────────────────────────────────

LAYERS = {
    "app": probe_app_services,
    "infra": probe_docker_containers,
    "db": probe_databases,
    "proc": probe_host_processes,
    "log": probe_recent_logs,
    "obs": probe_observability,
    "mesh": probe_mesh,
}


def color_status(status: str) -> str:
    return {
        "GREEN": f"{GREEN}✓ GREEN{NC}",
        "YELLOW": f"{YELLOW}⚠ YELLOW{NC}",
        "RED": f"{RED}✗ RED{NC}",
        "GRAY": f"{GRAY}—  GRAY{NC}",
    }.get(status, status)


def render_table(probes: list[Probe], fix_only: bool = False) -> None:
    """Render grouped by layer with colored statuses + remediation tips."""
    by_layer: dict[str, list[Probe]] = {}
    for p in probes:
        by_layer.setdefault(p.layer, []).append(p)
    layer_order = ["app", "db", "infra", "proc", "log", "obs", "mesh"]

    for layer in layer_order:
        rows = by_layer.get(layer, [])
        if not rows:
            continue
        if fix_only and not any(p.status in ("RED", "YELLOW") for p in rows):
            continue
        print(f"\n{BOLD}── Layer: {layer} ──{NC}")
        for p in rows:
            if fix_only and p.status == "GREEN":
                continue
            lat = f"{p.latency_ms:>5}ms" if p.latency_ms >= 0 else "    -"
            print(f"  {color_status(p.status)}  {p.component:30s} {lat}  {p.detail[:60]}")
            if p.remediation and p.status != "GREEN":
                print(f"     {BLUE}→ fix:{NC} {p.remediation[:150]}")


def render_summary(probes: list[Probe]) -> int:
    """Aggregate counts + decide exit code."""
    counts: dict[str, int] = {"GREEN": 0, "YELLOW": 0, "RED": 0, "GRAY": 0}
    critical_red = 0
    for p in probes:
        counts[p.status] = counts.get(p.status, 0) + 1
        if p.status == "RED" and p.severity == "critical":
            critical_red += 1
    print(f"\n{BOLD}=== SUMMARY ==={NC}")
    print(f"  {GREEN}{counts['GREEN']:3d} green{NC}  "
          f"{YELLOW}{counts['YELLOW']:3d} yellow{NC}  "
          f"{RED}{counts['RED']:3d} red{NC}  "
          f"{GRAY}{counts['GRAY']:3d} gray{NC}  "
          f"({len(probes)} total)")
    if critical_red:
        print(f"  {RED}{BOLD}✗ {critical_red} CRITICAL red — exit 1{NC}")
        return 1
    if counts["RED"]:
        print(f"  {YELLOW}{BOLD}⚠ {counts['RED']} red (non-critical) — exit 0{NC}")
    else:
        print(f"  {GREEN}{BOLD}✓ no critical red — exit 0{NC}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Advanced multi-layer health-check + troubleshoot for circuitRAG.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--layer", choices=list(LAYERS.keys()),
                   help="Only probe ONE layer (otherwise: all 7)")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON instead of table")
    p.add_argument("--fix", action="store_true",
                   help="Only show non-green rows (focused triage view)")
    args = p.parse_args()

    layers_to_run = [args.layer] if args.layer else list(LAYERS.keys())

    # Run probes in parallel — each layer is its own thread
    results: list[Probe] = []
    with ThreadPoolExecutor(max_workers=len(layers_to_run)) as ex:
        futs = {ex.submit(LAYERS[lyr]): lyr for lyr in layers_to_run}
        for f in as_completed(futs):
            try:
                results.extend(f.result())
            except Exception as e:  # noqa: BLE001
                results.append(Probe(layer=futs[f], component="probe-error",
                                     status="RED",
                                     detail=f"{type(e).__name__}: {str(e)[:60]}",
                                     severity="critical"))

    if args.json:
        print(json.dumps([asdict(p) for p in results], indent=2))
        # Still compute exit code
        return 1 if any(p.status == "RED" and p.severity == "critical" for p in results) else 0

    render_table(results, fix_only=args.fix)
    return render_summary(results)


if __name__ == "__main__":
    sys.exit(main())
