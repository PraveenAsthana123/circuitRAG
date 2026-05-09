#!/usr/bin/env python3
"""
Probe every tool in config/agentic_observability/oss_tooling_catalog.yaml
that is NOT covered by the BFF /api/v1/integrations-health surface
(which probes only 19 of 91 tools).

Coverage:
  - 16 shipped         → probe live state
  - 68 planned         → report PLANNED (no probe; would-add when deployed)
  -  4 partial         → probe live state + tag PARTIAL
  -  3 not_applicable  → SKIP

Probe types (auto-detected from install_path + name; explicit override
table below for cases where the heuristic would mis-classify):
  - import:<module>     → Python package importable
  - binary:<cmd>        → binary on PATH responds to --version / --help
  - http:<url>          → HTTP GET returns 2xx
  - tcp:<host>:<port>   → TCP connect succeeds
  - helm:<release>      → `helm list -A | grep release` matches
  - kubectl:<resource>  → `kubectl get <kind>/<name>` returns 0
  - planned             → report PLANNED, no probe
  - manual              → catalog declares "manual install"; report
                          NEEDS_VERIFY with hint

Output formats:
  TABLE (default)    — colored stdout, grouped by status
  TSV                — one tool/line, machine-readable
  JSON               — full result dict (BFF-consumable)

Usage:
  python3 scripts/catalog_tools_probe.py
  python3 scripts/catalog_tools_probe.py --format tsv
  python3 scripts/catalog_tools_probe.py --format json > /tmp/catalog-probe.json
  python3 scripts/catalog_tools_probe.py --only ragas,mlflow,k6
  python3 scripts/catalog_tools_probe.py --status-only HEALTHY  # filter
  python3 scripts/catalog_tools_probe.py --include-bff          # also probe the 19

Drilled by mcp/tests/drill_catalog_tools_probe.py.

Per CLAUDE.md §43 (drill discipline), §47.6 (observability is
first-class), §57.7 honesty (PLANNED is not pretended HEALTHY;
NEEDS_VERIFY is not pretended NOT_INSTALLED).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "config" / "agentic_observability" / "oss_tooling_catalog.yaml"

# ── ANSI ──────────────────────────────────────────────────────────────
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
GRAY = "\033[90m"
BLUE = "\033[34m"
BOLD = "\033[1m"
NC = "\033[0m"

# ── Tools already probed by BFF (skip unless --include-bff) ──────────
BFF_TOOLS = {
    "alertmanager", "cadvisor", "elasticsearch", "grafana", "jaeger",
    "kafka", "kiali", "kibana", "langfuse", "minio", "neo4j", "node_exporter",
    "ollama", "openclaw", "otel_collector", "postgres", "prometheus",
    "qdrant", "redis",
}

# ── Explicit probe-type overrides ────────────────────────────────────
# Catalog `install_path` hints can be ambiguous; this map is the source
# of truth when the heuristic would mis-classify. Format:
#   tool_name → ("probe_type", "probe_target")
# Where probe_type ∈ {import, binary, http, tcp, helm, kubectl, planned, manual}
PROBE_OVERRIDES: dict[str, tuple[str, str]] = {
    # Python packages — eval / safety / instrumentation
    "ragas":                       ("import",   "ragas"),
    "giskard":                     ("import",   "giskard"),
    "deepeval":                    ("import",   "deepeval"),
    "rebuff":                      ("import",   "rebuff"),
    "garak":                       ("import",   "garak"),
    "pyrit":                       ("import",   "pyrit"),
    "counterfit":                  ("import",   "counterfit"),
    "inspect_ai":                  ("import",   "inspect_ai"),
    "lm_evaluation_harness":       ("import",   "lm_eval"),
    "promptfoo":                   ("binary",   "promptfoo"),
    "trulens":                     ("import",   "trulens_eval"),
    "phoenix":                     ("import",   "phoenix"),
    "openai_evals_oss":            ("import",   "evals"),
    "vigil_llm":                   ("import",   "vigil"),
    "llama_guard":                 ("import",   "llama_guard"),
    "great_expectations":          ("import",   "great_expectations"),
    "soda_core":                   ("binary",   "soda"),
    "mlflow":                      ("import",   "mlflow"),
    "langgraph":                   ("import",   "langgraph"),
    "openlineage":                 ("import",   "openlineage"),
    "marquez":                     ("http",     "http://localhost:5000/api/v1/namespaces"),
    "traceloop_openllmetry":       ("import",   "traceloop"),
    "opentelemetry":               ("import",   "opentelemetry"),
    "resilience4j":                ("import",   "documind_core.circuit_breaker"),  # py port

    # Security CLIs / scanners
    "bandit":                      ("binary",   "bandit"),
    "checkov":                     ("binary",   "checkov"),
    "gitleaks":                    ("binary",   "gitleaks"),
    "trivy":                       ("binary",   "trivy"),
    "semgrep":                     ("binary",   "semgrep"),
    "kube_hunter":                 ("binary",   "kube-hunter"),
    "kubescape":                   ("binary",   "kubescape"),
    "helm_benchmark":              ("binary",   "helm"),  # checked via helm

    # Performance / load testing
    "k6":                          ("binary",   "k6"),
    "locust":                      ("binary",   "locust"),

    # Helm-installed K8s tools (probe via helm release)
    "argo_cd":                     ("helm",     "argo-cd"),
    "argo_rollouts":               ("helm",     "argo-rollouts"),
    "falco":                       ("helm",     "falco"),
    "keda":                        ("helm",     "keda"),
    "kyverno":                     ("helm",     "kyverno"),
    "loki":                        ("helm",     "loki"),
    "openbao":                     ("helm",     "openbao"),
    "opencost":                    ("helm",     "opencost"),
    "tempo":                       ("helm",     "tempo"),

    # eBPF / runtime security agents
    "tetragon":                    ("binary",   "tetragon"),
    "tracee":                      ("binary",   "tracee-ebpf"),
    "wazuh":                       ("kubectl",  "deploy/wazuh -n wazuh"),

    # Diagram / docs
    "mermaid_js":                  ("binary",   "mmdc"),  # @mermaid-js/mermaid-cli

    # Observability HTTP-probable
    "pyroscope":                   ("http",     "http://localhost:4040/healthz"),
    "elastic_stack":               ("http",     "http://localhost:9200/_cluster/health"),
    "opensearch_dashboards":       ("http",     "http://localhost:5602/api/status"),
    "dagster":                     ("import",   "dagster"),

    # 30 planned — no probe attempted
    "agentsight":                  ("planned",  ""),
    "airflow":                     ("planned",  ""),
    "apache_superset":             ("planned",  ""),
    "birt":                        ("planned",  ""),
    "datahub":                     ("planned",  ""),
    "dependency_track":            ("planned",  ""),
    "grype":                       ("planned",  ""),
    "jaspersoft_community":        ("planned",  ""),
    "keptn":                       ("planned",  ""),
    "knime":                       ("planned",  ""),
    "kube_bench":                  ("planned",  ""),
    "kubecost_oss":                ("planned",  ""),
    "lightdash":                   ("planned",  ""),
    "litmuschaos":                 ("planned",  ""),
    "metabase":                    ("planned",  ""),
    "nagios_core":                 ("planned",  ""),
    "netdata":                     ("planned",  ""),
    "openmetadata":                ("planned",  ""),
    "owasp_dependency_check":      ("planned",  ""),
    "pentaho_community":           ("planned",  ""),
    "polaris":                     ("planned",  ""),
    "redash":                      ("planned",  ""),
    "suricata":                    ("planned",  ""),
    "temporal":                    ("planned",  ""),
    "vault_oss":                   ("planned",  ""),
    "zabbix":                      ("planned",  ""),
    "zeek":                        ("planned",  ""),

    # Partial-status tools
    "opa_gatekeeper":              ("kubectl",  "crd/constrainttemplates.templates.gatekeeper.sh"),
    "neo4j_bloom":                 ("manual",   "Bloom is a desktop client; install separately"),
    "helm":                        ("binary",   "helm"),
}

# Tools to skip entirely (catalog status=not_applicable)
SKIP_TOOLS = {"crewai", "d3_js", "kubernetes_operators"}


def http_probe(url: str, timeout: float = 3.0) -> tuple[bool, int, str]:
    try:
        t0 = time.monotonic()
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            ms = int((time.monotonic() - t0) * 1000)
            return (200 <= r.status < 400, ms, f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return (False, ms, f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return (False, -1, str(e)[:80])


def tcp_probe(host: str, port: int, timeout: float = 2.0) -> tuple[bool, int, str]:
    try:
        t0 = time.monotonic()
        with socket.create_connection((host, port), timeout=timeout):
            ms = int((time.monotonic() - t0) * 1000)
            return (True, ms, "TCP open")
    except Exception as e:  # noqa: BLE001
        return (False, -1, str(e)[:80])


def import_probe(module: str) -> tuple[bool, int, str]:
    t0 = time.monotonic()
    try:
        importlib.import_module(module)
        ms = int((time.monotonic() - t0) * 1000)
        return (True, ms, f"import {module}")
    except Exception as e:  # noqa: BLE001
        return (False, -1, f"ImportError: {str(e)[:80]}")


def binary_probe(cmd: str) -> tuple[bool, int, str]:
    bin_path = shutil.which(cmd)
    if not bin_path:
        # Also check repo-local .tools/bin
        local = REPO / ".tools" / "bin" / cmd
        if local.exists() and os.access(local, os.X_OK):
            bin_path = str(local)
    if not bin_path:
        return (False, -1, "not on PATH")
    t0 = time.monotonic()
    for flag in ["--version", "version", "--help", "-h"]:
        try:
            r = subprocess.run(
                [bin_path, flag],
                capture_output=True, timeout=5.0,
            )
            ms = int((time.monotonic() - t0) * 1000)
            if r.returncode == 0:
                first_line = (r.stdout or r.stderr).decode(errors="ignore").splitlines()[:1]
                hint = first_line[0][:60] if first_line else "exit 0"
                return (True, ms, hint)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue
    return (False, -1, "no version/help flag worked")


def helm_probe(release: str) -> tuple[bool, int, str]:
    helm = shutil.which("helm")
    if not helm:
        helm_local = REPO / ".tools" / "bin" / "helm"
        if helm_local.exists():
            helm = str(helm_local)
    if not helm:
        return (False, -1, "helm not on PATH")
    t0 = time.monotonic()
    try:
        r = subprocess.run(
            [helm, "list", "-A", "--output", "json"],
            capture_output=True, timeout=10.0,
            env={**os.environ, "KUBECONFIG": os.environ.get("KUBECONFIG", "/mnt/deepa/.kube/config")},
        )
        ms = int((time.monotonic() - t0) * 1000)
        if r.returncode != 0:
            return (False, ms, f"helm list failed: {r.stderr.decode()[:60]}")
        releases = json.loads(r.stdout or b"[]")
        for rel in releases:
            if rel.get("name") == release or release in rel.get("name", ""):
                ns = rel.get("namespace", "?")
                status = rel.get("status", "?")
                return (status == "deployed", ms, f"ns={ns} status={status}")
        return (False, ms, f"no release named {release!r}")
    except Exception as e:  # noqa: BLE001
        return (False, -1, str(e)[:80])


def kubectl_probe(target: str) -> tuple[bool, int, str]:
    kubectl = shutil.which("kubectl") or str(REPO / ".tools" / "bin" / "kubectl")
    if not Path(kubectl).exists():
        return (False, -1, "kubectl not on PATH")
    t0 = time.monotonic()
    try:
        # target like "deploy/foo -n bar" or "crd/x.y"
        args = [kubectl, "get"] + target.split()
        r = subprocess.run(
            args, capture_output=True, timeout=10.0,
            env={**os.environ, "KUBECONFIG": os.environ.get("KUBECONFIG", "/mnt/deepa/.kube/config")},
        )
        ms = int((time.monotonic() - t0) * 1000)
        if r.returncode == 0:
            return (True, ms, "kubectl get OK")
        return (False, ms, f"kubectl get failed: {r.stderr.decode()[:60]}")
    except Exception as e:  # noqa: BLE001
        return (False, -1, str(e)[:80])


def probe_one(tool: dict[str, Any]) -> dict[str, Any]:
    name = tool.get("name", "?")
    cat = tool.get("category", "?")
    cat_status = tool.get("status", "?")

    if name in SKIP_TOOLS:
        return {"name": name, "category": cat, "catalog_status": cat_status,
                "probe_status": "SKIPPED", "evidence": "not_applicable", "latency_ms": -1}

    if name in BFF_TOOLS:
        return {"name": name, "category": cat, "catalog_status": cat_status,
                "probe_status": "BFF_PROBED",
                "evidence": "covered by /api/v1/integrations-health",
                "latency_ms": -1}

    if cat_status == "planned":
        return {"name": name, "category": cat, "catalog_status": cat_status,
                "probe_status": "PLANNED", "evidence": "not deployed (catalog status=planned)",
                "latency_ms": -1}

    pt, target = PROBE_OVERRIDES.get(name, ("manual", tool.get("install_path", "?")))

    if pt == "planned":
        return {"name": name, "category": cat, "catalog_status": cat_status,
                "probe_status": "PLANNED", "evidence": "not deployed (catalog status=planned)",
                "latency_ms": -1}
    if pt == "manual":
        return {"name": name, "category": cat, "catalog_status": cat_status,
                "probe_status": "NEEDS_VERIFY", "evidence": target[:80], "latency_ms": -1}

    probe_fn = {
        "import": import_probe,
        "binary": binary_probe,
        "helm": helm_probe,
        "kubectl": kubectl_probe,
    }.get(pt)
    if probe_fn is not None:
        ok, ms, evidence = probe_fn(target)
    elif pt == "http":
        ok, ms, evidence = http_probe(target)
    elif pt == "tcp":
        host, port = target.split(":")
        ok, ms, evidence = tcp_probe(host, int(port))
    else:
        ok, ms, evidence = False, -1, f"unknown probe type: {pt}"

    status = "HEALTHY" if ok else (
        "PARTIAL" if cat_status == "partial" else "NOT_INSTALLED"
    )
    return {"name": name, "category": cat, "catalog_status": cat_status,
            "probe_type": pt, "probe_target": target,
            "probe_status": status, "evidence": evidence, "latency_ms": ms}


def fmt_status(s: str) -> str:
    color = {
        "HEALTHY":      GREEN,
        "PARTIAL":      YELLOW,
        "PLANNED":      GRAY,
        "BFF_PROBED":   BLUE,
        "NOT_INSTALLED": RED,
        "NEEDS_VERIFY": YELLOW,
        "SKIPPED":      GRAY,
    }.get(s, "")
    return f"{color}{s:14s}{NC}"


def render_table(results: list[dict]) -> None:
    # Group by status
    order = ["HEALTHY", "PARTIAL", "BFF_PROBED", "NEEDS_VERIFY", "NOT_INSTALLED", "PLANNED", "SKIPPED"]
    by_status: dict[str, list[dict]] = {s: [] for s in order}
    for r in results:
        by_status.setdefault(r["probe_status"], []).append(r)
    counts = {k: len(v) for k, v in by_status.items() if v}

    print(f"\n{BOLD}=== TOOLS-CATALOG PROBE — {len(results)} tools ==={NC}")
    print(f"counts: {counts}\n")
    for st in order:
        rows = by_status.get(st, [])
        if not rows:
            continue
        print(f"{BOLD}{fmt_status(st)}{NC} ({len(rows)})")
        for r in sorted(rows, key=lambda x: x["name"]):
            ms = f"{r['latency_ms']:>5}ms" if r["latency_ms"] >= 0 else "  -  "
            ev = r.get("evidence", "")[:60]
            print(f"  {r['name']:30s} {r['category']:18s} {ms}  {ev}")
        print()


def render_tsv(results: list[dict]) -> None:
    print("name\tcategory\tcatalog_status\tprobe_status\tlatency_ms\tevidence")
    for r in results:
        print(f"{r['name']}\t{r['category']}\t{r.get('catalog_status','')}\t"
              f"{r['probe_status']}\t{r['latency_ms']}\t{r.get('evidence','')}")


def main() -> int:
    p = argparse.ArgumentParser(description="Probe catalog tools NOT covered by BFF integrations-health")
    p.add_argument("--format", choices=["table", "tsv", "json"], default="table")
    p.add_argument("--only", help="Comma-separated tool names to probe (overrides default scope)")
    p.add_argument("--status-only", help="Filter results to a single probe_status")
    p.add_argument("--include-bff", action="store_true", help="Also probe the 19 BFF-covered tools")
    p.add_argument("--parallel", type=int, default=8, help="Concurrent probes")
    p.add_argument("--catalog", default=str(CATALOG), help="Path to catalog YAML")
    args = p.parse_args()

    catalog = yaml.safe_load(Path(args.catalog).read_text(encoding="utf-8"))
    all_tools: list[dict] = catalog.get("tools", [])

    if args.only:
        wanted = {n.strip() for n in args.only.split(",")}
        all_tools = [t for t in all_tools if t.get("name") in wanted]
    elif not args.include_bff:
        all_tools = [t for t in all_tools if t.get("name") not in BFF_TOOLS]

    # Skip not_applicable
    all_tools = [t for t in all_tools if t.get("name") not in SKIP_TOOLS]

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = {ex.submit(probe_one, t): t for t in all_tools}
        for f in as_completed(futs):
            results.append(f.result())

    if args.status_only:
        results = [r for r in results if r["probe_status"] == args.status_only]

    if args.format == "json":
        print(json.dumps({"generated_at": time.time(), "results": results}, indent=2))
    elif args.format == "tsv":
        render_tsv(results)
    else:
        render_table(results)

    # Exit code: 0 if no NOT_INSTALLED among shipped, 1 otherwise (CI-friendly)
    bad = [r for r in results if r["probe_status"] == "NOT_INSTALLED"
           and r.get("catalog_status") == "shipped"]
    if bad and args.format == "table":
        print(f"{RED}{BOLD}❌ {len(bad)} shipped tool(s) not installed{NC}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
