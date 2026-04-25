# RESOURCES: pg inference mcp_hr
"""
Drill: /api/v1/health/upstreams probes every upstream this service
depends on — retrieval-svc, ollama, MCP namespaces, governance DB.

Closes the audit-checklist gap "service-level monitoring" and the
gRPC/microservices reference docs' cross-service reachability
scenarios. Reading any single /health endpoint only tells operators
about one service; this gives a unified upstream view from
inference-svc's perspective.

Negative-assertion §43-style:
 1. baseline — endpoint returns 200 with the expected upstream
    families. Each known-up service appears with reachable=true.
 2. parallel-probe latency bound — total endpoint latency must NOT
    exceed (sum of probe timeouts). Probes run in parallel; a
    regression that serialised them would 5x the dashboard's stale
    window.
 3. db probe is real — governance-db row's status is 'connected',
    not just a default. NEGATIVE: a regression that hardcoded
    db.reachable=true (skipping the SELECT 1) would still pass
    step 1 but fail this.
 4. version surfaces when /health returns one — retrieval-svc
    /health includes ``version``; that field round-trips. NEGATIVE:
    a regression that didn't parse version would render '—' even
    when the upstream supplied one.
 5. label-stable kind classification — kinds ∈ {db, http_service,
    llm, mcp}. Operators alert per-kind; cardinality drift would
    break dashboards.
 6. results sort stable — by (kind, name) ASC. NEGATIVE: a row
    order that swapped between refreshes would make the dashboard
    flicker visually.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_inference_health_upstreams.py
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
INF_BASE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


VALID_KINDS = {"db", "http_service", "llm", "mcp"}


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as c:
        step("1. baseline — endpoint returns 200 with upstream rows")
        started = time.perf_counter()
        r = await c.get(f"{INF_BASE}/api/v1/health/upstreams")
        elapsed = time.perf_counter() - started
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}: {r.text[:200]}")
        body = r.json()
        for required in ("service", "observed_at", "upstreams"):
            if required not in body:
                fail(f"missing top-level key: {required}")
        upstreams = body["upstreams"]
        if not isinstance(upstreams, list) or not upstreams:
            fail(f"upstreams must be non-empty list, got {upstreams!r}")
        names = {u["name"] for u in upstreams}
        # The known-wired set on the dev stack. retrieval-svc + ollama +
        # mcp_hr + governance-db are minimum; mcp_itsm is optional.
        required_names = {"retrieval-svc", "ollama", "mcp_hr", "governance-db"}
        missing = required_names - names
        if missing:
            fail(
                f"required upstreams missing: {missing}. Either probe "
                f"specs are wrong or an upstream isn't running."
            )
        ok(f"observed {len(upstreams)} upstreams: {sorted(names)}")

        step("2. parallel-probe latency bound — total < 2.5s")
        # Each probe has a 2s timeout. If they're serialised, 5
        # upstreams x 2s = 10s. Parallel = max single probe.
        # Generous bound: 2.5s to absorb scrape overhead.
        if elapsed > 2.5:
            fail(
                f"endpoint took {elapsed:.2f}s — probes likely serialised. "
                f"With 5 upstreams at 2s timeout each, parallel should "
                f"finish in <2.1s; serial would take ~10s."
            )
        ok(f"endpoint returned in {elapsed*1000:.0f}ms (parallel probes)")

        step("3. governance-db probe is real (status='connected')")
        db_rows = [u for u in upstreams if u["kind"] == "db"]
        if len(db_rows) != 1:
            fail(f"expected 1 db row, got {len(db_rows)}")
        db = db_rows[0]
        if not db["reachable"]:
            fail(f"governance-db not reachable: {db}")
        if db["status"] != "connected":
            fail(
                f"db status should be literal 'connected' (proves "
                f"SELECT 1 ran), got {db['status']!r}. A regression "
                f"that hardcoded reachable=true would fail this."
            )
        if db["latency_ms"] is None or db["latency_ms"] < 0:
            fail(f"db latency_ms missing or negative: {db['latency_ms']!r}")
        ok(f"governance-db connected, latency={db['latency_ms']:.1f}ms")

        step("4. version surfaces — retrieval-svc /health carries version")
        rsv = next((u for u in upstreams if u["name"] == "retrieval-svc"), None)
        if rsv is None:
            fail("retrieval-svc row missing")
        if not rsv["reachable"]:
            fail(f"retrieval-svc not reachable: {rsv}")
        if rsv["version"] in (None, ""):
            fail(
                f"retrieval-svc version not parsed; got {rsv['version']!r}. "
                f"The /health response should include version=0.1.0 (or similar). "
                f"A regression that skipped JSON parsing would show '—'."
            )
        ok(f"retrieval-svc version={rsv['version']!r} parsed from /health")

        step("5. kind labels stable — only valid kinds appear")
        kinds = {u["kind"] for u in upstreams}
        unknown = kinds - VALID_KINDS
        if unknown:
            fail(
                f"unknown kind label(s) {unknown} appeared. Operators "
                f"alert per-kind; cardinality drift breaks dashboards."
            )
        ok(f"kinds observed: {sorted(kinds)} (all within enum)")

        step("6. row order stable — by (kind, name) ASC")
        order = [(u["kind"], u["name"]) for u in upstreams]
        if order != sorted(order):
            fail(
                f"upstreams not sorted by (kind, name) — order: {order}. "
                f"Unstable row order would flicker the dashboard between "
                f"refreshes."
            )
        ok(f"order locked: {[n for _, n in order]}")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 UPSTREAM-HEALTH STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
