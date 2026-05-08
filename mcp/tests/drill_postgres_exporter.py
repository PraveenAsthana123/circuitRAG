#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: postgres-exporter compose + scrape contract (per §43 + §47.6).

Locks the Postgres metrics exporter wired into the docker-compose
stack and the prometheus scrape config that picks it up. Closes
the gap surfaced by the post-Trivy audit (no postgres_exporter
container; postgres latency / connection / query-cache metrics
were invisible to Grafana before this iteration).

Eight steps. Five negative.

Step coverage:
  1. POSITIVE: docker-compose.yml declares postgres-exporter service
  2. POSITIVE: image is prometheuscommunity/postgres-exporter
  3. POSITIVE: prometheus.yml has postgres-exporter scrape config
  4. NEGATIVE: image is PINNED (not :latest — drift would change
     metric labels without code review)
  5. NEGATIVE: DATA_SOURCE_NAME uses ${VAR:-default} pattern,
     never hardcoded credentials
  6. NEGATIVE: scrape target is the docker-network DNS name
     (postgres-exporter:9187), not localhost — which would fail
     from inside the prometheus container
  7. NEGATIVE: depends_on postgres with service_healthy condition
     (otherwise exporter starts before postgres + crashloops)
  8. POSITIVE: healthcheck probes /metrics endpoint

Per CLAUDE.md §43, §47.6 (observability is first-class), §49
compose-footer (composes with prometheus.yml + Grafana dashboards
in infra/observability/grafana-dashboards/), §51 forensic substrate.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
PROM = REPO / "infra" / "observability" / "prometheus.yml"


GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    if not COMPOSE.exists() or not PROM.exists():
        fail(
            f"missing source files; COMPOSE={COMPOSE.exists()} "
            f"PROM={PROM.exists()}"
        )
    compose = COMPOSE.read_text(encoding="utf-8")
    prom = PROM.read_text(encoding="utf-8")

    # ── 1. compose has postgres-exporter service block ────────────────
    step("1. POSITIVE: docker-compose.yml declares postgres-exporter")
    if "  postgres-exporter:" not in compose:
        fail("postgres-exporter service block missing from docker-compose.yml")
    ok("postgres-exporter service block present")

    # Locate the block — between its declaration and the next service
    block_match = re.search(
        r"\n  postgres-exporter:.*?(?=\n  \w[^:]*:\s*\n|\Z)",
        compose,
        re.DOTALL,
    )
    if not block_match:
        fail("cannot locate postgres-exporter block")
    block = block_match.group(0)

    # ── 2. image is prometheuscommunity/postgres-exporter ─────────────
    step("2. POSITIVE: image is prometheuscommunity/postgres-exporter")
    if "prometheuscommunity/postgres-exporter" not in block:
        fail(
            "postgres-exporter must use prometheuscommunity/postgres-exporter "
            "(canonical image)"
        )
    ok("canonical image referenced")

    # ── 3. prometheus.yml has scrape config ──────────────────────────
    step("3. POSITIVE: prometheus.yml has postgres-exporter scrape config")
    if "postgres-exporter" not in prom:
        fail(
            "prometheus.yml does NOT declare postgres-exporter scrape job — "
            "metrics endpoint will run but never be collected"
        )
    if not re.search(r"job_name:\s*postgres-exporter", prom):
        fail("prometheus.yml missing job_name: postgres-exporter")
    ok("scrape job declared in prometheus.yml")

    # ── 4. NEGATIVE: image is PINNED (not :latest) ────────────────────
    step("4. NEGATIVE: image is PINNED — never :latest")
    image_match = re.search(
        r"image:\s*prometheuscommunity/postgres-exporter:([^\s]+)", block
    )
    if not image_match:
        fail("postgres-exporter image tag missing entirely")
    tag = image_match.group(1)
    if tag == "latest":
        fail(
            "image pinned to :latest — drift would change metric labels "
            "without code review (§16 reproducibility)"
        )
    if not re.match(r"v?\d+\.\d+", tag):
        fail(
            f"image tag '{tag}' doesn't look like a version pin "
            "(expected v?N.N.N)"
        )
    ok(f"image pinned to {tag}")

    # ── 5. NEGATIVE: credentials use ${VAR:-default} pattern ──────────
    step(
        "5. NEGATIVE: DATA_SOURCE_NAME uses ${VAR:-default} pattern "
        "(never hardcoded credentials in repo)"
    )
    dsn_match = re.search(r"DATA_SOURCE_NAME:\s*\"?([^\"\n]+)\"?", block)
    if not dsn_match:
        fail("postgres-exporter missing DATA_SOURCE_NAME")
    dsn = dsn_match.group(1)
    if "${" not in dsn:
        fail(
            f"DATA_SOURCE_NAME does NOT use env-var substitution: '{dsn[:80]}' — "
            "credentials must be ${DOCUMIND_PG_USER:-...} pattern, not literal"
        )
    ok("DATA_SOURCE_NAME uses env-var substitution (no hardcoded creds)")

    # ── 6. NEGATIVE: scrape target uses docker DNS name ───────────────
    step(
        "6. NEGATIVE: scrape target uses docker-network DNS name "
        "(postgres-exporter:9187), NOT localhost"
    )
    target_match = re.search(
        r"job_name:\s*postgres-exporter\s*\n\s*static_configs:\s*\n\s*-\s*targets:\s*\[([^\]]+)\]",
        prom,
    )
    if not target_match:
        fail("cannot parse postgres-exporter scrape target")
    target = target_match.group(1).strip()
    if "localhost" in target.lower() or "127.0.0.1" in target:
        fail(
            f"target uses localhost/127.0.0.1: {target} — won't resolve from "
            "inside the prometheus container; must be docker DNS name"
        )
    if "postgres-exporter:9187" not in target.replace('"', ""):
        fail(f"target should be 'postgres-exporter:9187', got: {target}")
    ok(f"target uses docker DNS: {target}")

    # ── 7. NEGATIVE: depends_on postgres with service_healthy ─────────
    step(
        "7. NEGATIVE: depends_on postgres with service_healthy "
        "(prevents exporter crashloop on cold start)"
    )
    if "depends_on:" not in block:
        fail("postgres-exporter has no depends_on block — will crashloop on cold start")
    if "postgres:" not in block:
        fail("depends_on doesn't reference postgres service")
    if "service_healthy" not in block:
        fail(
            "depends_on lacks 'condition: service_healthy' — exporter would "
            "start before postgres is ready and fail-fast-loop"
        )
    ok("depends_on postgres + service_healthy condition present")

    # ── 8. POSITIVE: healthcheck on /metrics endpoint ─────────────────
    step("8. POSITIVE: healthcheck probes /metrics endpoint")
    if "healthcheck:" not in block:
        fail("postgres-exporter has no healthcheck — Docker won't notice silent failure")
    if "/metrics" not in block:
        fail(
            "healthcheck doesn't probe /metrics — could pass while metrics "
            "endpoint is broken"
        )
    ok("healthcheck on /metrics endpoint present")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
