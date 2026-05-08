#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Kiali advanced integration with the full circuitRAG tooling stack.

Locks the contract that Kiali becomes the single pane of glass for:
  • Istio mesh control plane                (in-cluster, real)
  • Prometheus metrics                       (host:9090 via host.minikube.internal)
  • Grafana dashboards                       (host:3001)
  • Jaeger distributed tracing               (host:16686)
  • OpenTelemetry collector                  (visible via OTel-exported metrics)
  • Custom dashboards for: API gateway, load balancer, circuit breaker,
    paperclip MCP, polysai, hybrid-architect, langchain/langgraph,
    vector DB, cache DB, chunking, output evaluation (ragas+giskard+
    deepeval), OTel collector
  • Istio ServiceEntries for the docker-compose services so Kiali
    "sees" them (prometheus / grafana / jaeger / kibana / elasticsearch
    / otel / qdrant / redis / postgres / paperclip / hybrid-architect /
    agent-orchestrator / langfuse — 13 entries total)

10 steps, 4 negative.

  1. POSITIVE: kiali-cluster-config.yaml exists + valid K8s ConfigMap
  2. POSITIVE: ConfigMap wires Prometheus + Grafana + Jaeger via
              host.minikube.internal (minikube DNS for the host)
  3. POSITIVE: ConfigMap declares ≥10 custom_dashboards covering every
              tool the user listed (rag-pipeline, vector-db, cache-db,
              chunking, output-eval, circuit-breaker, api-gateway,
              hybrid-architect, paperclip-mcp, polysai, otel-collector)
  4. POSITIVE: ConfigMap declares dashboards for circuitRAG components
              (key Grafana dashboard names registered for deep links)
  5. POSITIVE: service-entries.yaml exists + declares ≥13 ServiceEntries
              for docker-compose services
  6. NEGATIVE: ServiceEntries use resolution: DNS (NOT STATIC — Istio
              webhook rejects hostnames in STATIC endpoints)
  7. NEGATIVE: ConfigMap does NOT use bare prometheus.istio-system
              (the addon default points at a Prometheus that doesn't
              exist; must override to host.minikube.internal)
  8. NEGATIVE: ConfigMap tracing.enabled is true (NOT false; the
              addon default is false → no Jaeger panels in Kiali)
  9. NEGATIVE: legacy infra/kiali/kiali.yaml not auto-applied to
              cluster (it's a docker-compose file mount, not a
              cluster manifest — applying it would overwrite the
              real ConfigMap)
 10. POSITIVE: docs/runbooks/istio-local-deploy.md (or equivalent)
              exists OR the kiali-cluster-config.yaml itself
              documents the apply order

Per CLAUDE.md §43 (drill discipline; ≥3 negatives — 4 here),
§47.6 (observability is first-class), §49 (compose footer — Kiali
joins integrations-health + tools-launcher + monitoring), §51
(forensic substrate), §57.7 (honesty — declared dashboards forward-
contract the metric labels service authors must adopt; doesn't
silently claim mesh graph for unmeshed compose services).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml  # PyYAML, available in dev venv

REPO = Path(__file__).resolve().parents[2]
CLUSTER_CFG = REPO / "infra" / "kiali" / "kiali-cluster-config.yaml"
SVC_ENTRIES = REPO / "infra" / "kiali" / "service-entries.yaml"
LEGACY_CFG = REPO / "infra" / "kiali" / "kiali.yaml"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"

REQUIRED_DASHBOARDS = [
    "documind-rag-pipeline",
    "documind-vector-db",
    "documind-cache-db",
    "documind-chunking",
    "documind-output-eval",
    "documind-circuit-breaker",
    "documind-api-gateway",
    "documind-hybrid-architect",
    "documind-paperclip-mcp",
    "documind-polysai",
    "documind-otel-collector",
]

REQUIRED_GRAFANA_DASHBOARDS = [
    "Istio Service",
    "Istio Workload",
    "RAG Pipeline",
    "Vector DB",
    "Cache",
    "Chunking",
    "Output Evaluation",
    "Circuit Breaker",
    "API Gateway",
    "Hybrid Architect",
    "Paperclip",
    "Polysai",
]

REQUIRED_SERVICE_ENTRIES = [
    "documind-prometheus",
    "documind-grafana",
    "documind-jaeger",
    "documind-kibana",
    "documind-elasticsearch",
    "documind-otel-collector",
    "documind-qdrant",
    "documind-redis",
    "documind-postgres",
    "documind-paperclip-mcp",
    "documind-hybrid-architect",
    "documind-agent-orchestrator",
    "documind-langfuse",
]


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. cluster ConfigMap exists + valid ────────────────────────────
    step("1. POSITIVE: kiali-cluster-config.yaml exists + valid ConfigMap")
    if not CLUSTER_CFG.exists():
        fail(f"missing: {CLUSTER_CFG.relative_to(REPO)}")
    raw = CLUSTER_CFG.read_text(encoding="utf-8")
    docs = list(yaml.safe_load_all(raw))
    cm_doc = next(
        (d for d in docs if d and d.get("kind") == "ConfigMap" and d.get("metadata", {}).get("name") == "kiali"),
        None,
    )
    if cm_doc is None:
        fail("kiali-cluster-config.yaml does NOT contain a ConfigMap named 'kiali'")
    cfg_text = cm_doc["data"]["config.yaml"]
    cfg = yaml.safe_load(cfg_text)
    ok(f"ConfigMap data.config.yaml parses ({len(cfg_text)}b)")

    # ── 2. external services wired to host.minikube.internal ───────────
    step("2. POSITIVE: Prometheus + Grafana + Jaeger via host.minikube.internal")
    ext = cfg.get("external_services", {})
    prom_url = ext.get("prometheus", {}).get("url", "")
    if "host.minikube.internal:9090" not in prom_url:
        fail(f"prometheus.url is not host.minikube.internal:9090 (got: {prom_url})")
    grafana = ext.get("grafana", {})
    if not grafana.get("enabled"):
        fail("grafana.enabled is not true")
    if "host.minikube.internal:3001" not in grafana.get("in_cluster_url", ""):
        fail("grafana.in_cluster_url not host.minikube.internal:3001")
    tracing = ext.get("tracing", {})
    if "host.minikube.internal:16686" not in tracing.get("in_cluster_url", ""):
        fail("tracing.in_cluster_url not host.minikube.internal:16686")
    ok("Prometheus + Grafana + Jaeger all reach host via host.minikube.internal")

    # ── 3. custom_dashboards cover every requested tool ────────────────
    step("3. POSITIVE: ≥11 custom_dashboards cover all requested tools")
    custom = cfg.get("custom_dashboards", [])
    declared = {d.get("name") for d in custom if isinstance(d, dict)}
    missing = [d for d in REQUIRED_DASHBOARDS if d not in declared]
    if missing:
        fail(f"custom_dashboards missing required entries: {missing}")
    ok(f"all {len(REQUIRED_DASHBOARDS)} required custom dashboards declared")

    # ── 4. Grafana dashboard list registers tool-specific deep links ──
    step("4. POSITIVE: Grafana dashboards list registers tool deep-links")
    graf_dash = grafana.get("dashboards", [])
    graf_names = " | ".join(
        d.get("name", "") for d in graf_dash if isinstance(d, dict)
    )
    missing_graf = [t for t in REQUIRED_GRAFANA_DASHBOARDS if t not in graf_names]
    if missing_graf:
        fail(f"Grafana dashboards list missing tool deep-links: {missing_graf}")
    ok(f"all {len(REQUIRED_GRAFANA_DASHBOARDS)} required Grafana deep-link names present")

    # ── 5. ServiceEntries for docker-compose services ──────────────────
    step("5. POSITIVE: ≥13 ServiceEntries for docker-compose services")
    if not SVC_ENTRIES.exists():
        fail(f"missing: {SVC_ENTRIES.relative_to(REPO)}")
    se_raw = SVC_ENTRIES.read_text(encoding="utf-8")
    se_docs = [d for d in yaml.safe_load_all(se_raw) if d]
    se_names = {
        d.get("metadata", {}).get("name")
        for d in se_docs
        if d.get("kind") == "ServiceEntry"
    }
    missing_se = [n for n in REQUIRED_SERVICE_ENTRIES if n not in se_names]
    if missing_se:
        fail(f"service-entries.yaml missing required entries: {missing_se}")
    ok(f"all {len(REQUIRED_SERVICE_ENTRIES)} required ServiceEntries declared ({len(se_names)} total)")

    # ── 6. NEGATIVE: ServiceEntries use DNS resolution ─────────────────
    step("6. NEGATIVE: ServiceEntries use resolution: DNS (not STATIC)")
    static_count = sum(
        1
        for d in se_docs
        if d.get("kind") == "ServiceEntry" and d.get("spec", {}).get("resolution") == "STATIC"
    )
    if static_count > 0:
        fail(
            f"{static_count} ServiceEntry uses resolution: STATIC — Istio webhook rejects "
            "hostnames as endpoint addresses there. MUST be DNS (or explicit IP literal)."
        )
    dns_count = sum(
        1
        for d in se_docs
        if d.get("kind") == "ServiceEntry" and d.get("spec", {}).get("resolution") == "DNS"
    )
    if dns_count < len(REQUIRED_SERVICE_ENTRIES):
        fail(f"only {dns_count} of {len(REQUIRED_SERVICE_ENTRIES)} required ServiceEntries use DNS")
    ok(f"all {dns_count} ServiceEntries use resolution: DNS (avoids STATIC hostname rejection)")

    # ── 7. NEGATIVE: prometheus URL is NOT the bare addon default ──────
    step("7. NEGATIVE: prometheus.url not the bare addon default")
    if "prometheus.istio-system" in prom_url and "host.minikube.internal" not in prom_url:
        fail(
            "prometheus.url is the addon default (prometheus.istio-system) "
            "which doesn't exist in this stack — Kiali charts would all be empty"
        )
    if prom_url == "":
        fail("prometheus.url is empty — Kiali falls back to addon default that doesn't resolve")
    ok("prometheus.url overrides the addon default (avoids empty-charts trap)")

    # ── 8. NEGATIVE: tracing.enabled is true (not addon default false) ─
    step("8. NEGATIVE: tracing.enabled is true (addon default is false)")
    if not tracing.get("enabled"):
        fail(
            "tracing.enabled is false (addon default) — Kiali shows no Jaeger panels. "
            "Must be true with provider: jaeger + in_cluster_url set."
        )
    if tracing.get("provider") != "jaeger":
        fail(f"tracing.provider is not jaeger (got: {tracing.get('provider')})")
    ok("tracing.enabled=true with provider=jaeger (Jaeger panels render in Kiali)")

    # ── 9. NEGATIVE: legacy infra/kiali/kiali.yaml NOT a K8s manifest ──
    step("9. NEGATIVE: legacy kiali.yaml is NOT a K8s manifest (won't overwrite ConfigMap)")
    if LEGACY_CFG.exists():
        legacy_raw = LEGACY_CFG.read_text(encoding="utf-8")
        # Legacy file is the docker-compose mounted config (raw Kiali
        # config, not a K8s ConfigMap wrapper). It MUST NOT contain
        # `kind: ConfigMap` — otherwise `kubectl apply -f infra/kiali/`
        # would silently overwrite the real cluster ConfigMap.
        if re.search(r"^kind:\s*ConfigMap", legacy_raw, re.MULTILINE):
            fail(
                "legacy infra/kiali/kiali.yaml has 'kind: ConfigMap' — "
                "would clobber the real cluster ConfigMap if applied via kubectl"
            )
        ok("legacy kiali.yaml is a raw config file (not a ConfigMap; safe)")
    else:
        ok("legacy kiali.yaml absent — clean state")

    # ── 10. POSITIVE: cluster ConfigMap documents apply order ─────────
    step("10. POSITIVE: cluster ConfigMap documents apply order")
    if "kubectl" not in raw and "apply" not in raw:
        fail("kiali-cluster-config.yaml does NOT document its apply path")
    if "rollout restart deploy/kiali" not in raw:
        fail(
            "kiali-cluster-config.yaml does NOT document the rollout-restart "
            "step — operators would apply the ConfigMap and Kiali would not "
            "pick it up until next pod recreation"
        )
    ok("cluster ConfigMap documents apply order including rollout-restart")

    print(f"\n{BOLD}{GREEN}ALL 10 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
