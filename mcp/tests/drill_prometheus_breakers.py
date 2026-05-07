# RESOURCES: inference mcp_hr
"""
Drill: Prometheus gauges track external breaker state transitions.

The inference-svc BreakerMetricsExporter polls mcp_client.cb_state +
obs_breaker.state every N seconds and pushes values into the shared
``documind_circuit_breaker_state{name=<n>}`` gauge. This drill proves:

 1. Baseline: after boot, `mcp_hr=0` (closed) and `otlp-export=0` are
    both visible on /metrics alongside the pre-existing retrieval-svc
    and ollama-llm series.
 2. Trip the MCP CB by killing MCP and firing 3 agent/ask calls. The
    client's breaker transitions CLOSED → OPEN (failure_threshold=3).
 3. Wait one exporter cycle. /metrics now reports `mcp_hr=2` (open).
 4. Restart MCP, wait recovery_timeout (32s default), fire a probe
    call. The CB goes back to CLOSED.
 5. Wait one exporter cycle. /metrics reports `mcp_hr=0` again.

Only the `mcp_hr` series transitions — `otlp-export` stays at 0
throughout because the OTel collector is healthy. (A separate drill
could exercise that too, but it's slow: stopping the collector for
~90s to let the OCB trip.)

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_prometheus_breakers.py
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
METRICS_URL = os.getenv("METRICS_URL", "http://127.0.0.1:9466/metrics")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"
H = {"X-Tenant-Id": TENANT, "Content-Type": "application/json"}


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


_STATE_LINE = re.compile(
    r'^documind_circuit_breaker_state\{name="([^"]+)"\}\s+(\S+)$',
    re.MULTILINE,
)


def _gauge(body: str) -> dict[str, float]:
    return {m.group(1): float(m.group(2)) for m in _STATE_LINE.finditer(body)}


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    log = open("/tmp/documind-mcp-hr-prom-drill.log", "w")  # noqa: SIM115 (subprocess.Popen takes FD ownership)
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_hr.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )


async def _healthy(c: httpx.AsyncClient, url: str, tries: int = 30) -> bool:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    return False


async def _dead(c: httpx.AsyncClient, url: str, tries: int = 10) -> None:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=1.0)
            if r.status_code != 200:
                return
        except httpx.HTTPError:
            return
        await asyncio.sleep(0.3)


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as c:
        step("1. baseline — /metrics has mcp_hr + otlp-export at 0")
        r = await c.get(METRICS_URL)
        if r.status_code != 200:
            fail(f"metrics endpoint returned {r.status_code}")
        g = _gauge(r.text)
        if g.get("mcp_hr") is None:
            fail(f"mcp_hr not in gauge series; saw names={list(g)}")
        if g["mcp_hr"] != 0:
            fail(f"expected mcp_hr=0 (closed), got {g['mcp_hr']}")
        if g.get("otlp-export") is None:
            fail(f"otlp-export not in gauge series; saw names={list(g)}")
        if g["otlp-export"] != 0:
            fail(f"expected otlp-export=0, got {g['otlp-export']}")
        ok(f"baseline series: {sorted(g.items())}")

        step("2. kill MCP + 3 agent/ask → CB trips to OPEN")
        _kill_mcp()
        await _dead(c, MCP_BASE)
        for i in range(3):
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers=H,
                json={
                    "query": f"Please submit a {i+1}-day leave for prom gauge drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            if r.status_code != 200:
                fail(f"agent/ask {i} returned {r.status_code}")
            a = r.json().get("action") or {}
            if not a.get("degraded"):
                fail(f"call {i} did not degrade")
        ok("3 degraded calls; MCP CB should be OPEN")

        step("3. wait one exporter cycle (7s) + assert mcp_hr=2 on /metrics")
        await asyncio.sleep(7)
        r = await c.get(METRICS_URL)
        g = _gauge(r.text)
        if g.get("mcp_hr") != 2:
            fail(f"expected mcp_hr=2 (open), got {g.get('mcp_hr')}")
        if g.get("otlp-export") != 0:
            fail(
                f"otlp-export should stay at 0 while collector is healthy, "
                f"got {g.get('otlp-export')}",
            )
        # Other breakers should be untouched
        for k in ("retrieval-svc", "ollama-llm"):
            if k in g and g[k] != 0:
                fail(f"unrelated series {k} moved: {g[k]}")
        ok("mcp_hr=2 (open) — other series unchanged")

        step("4. restart MCP, wait recovery_timeout (32s), fire probe")
        mcp_proc = _spawn_mcp()
        try:
            if not await _healthy(c, MCP_BASE):
                fail("MCP didn't come back")
            print("    waiting 32s for CB recovery_timeout...")
            await asyncio.sleep(32)
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers=H,
                json={"query": "Please submit a 1-day leave for recovery probe", "employee_id": "E42"},
                timeout=60.0,
            )
            a = r.json().get("action") or {}
            if not (a.get("ok") or a.get("result")):
                fail(f"recovery probe did not succeed: {a}")
            ok(f"probe succeeded ticket={(a.get('result') or {}).get('ticket_id')}")

            step("5. wait another exporter cycle + assert mcp_hr=0 again")
            await asyncio.sleep(7)
            r = await c.get(METRICS_URL)
            g = _gauge(r.text)
            if g.get("mcp_hr") != 0:
                fail(f"expected mcp_hr=0 after recovery, got {g.get('mcp_hr')}")
            ok("mcp_hr=0 (closed) — transition round-trip visible in Prometheus")
        finally:
            if mcp_proc.poll() is None:
                mcp_proc.terminate()
                try:
                    mcp_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    mcp_proc.kill()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 PROMETHEUS-GAUGE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
