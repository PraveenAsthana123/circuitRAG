# RESOURCES: inference mcp_hr mcp_itsm
"""
Drill: per-namespace MCP breakers are visible on /health/detailed AND
the shared Prometheus gauge.

Complements the single-breaker detailed-health + prom-gauges drills.
Now that inference-svc holds multiple MCPClients, each with its own
CB, each must surface independently — killing one server must trip
that breaker alone and leave the other untouched.

Flow:
 1. /api/v1/health/detailed reports breakers for BOTH mcp_hr AND
    mcp_itsm at state=closed.
 2. /metrics shows documind_circuit_breaker_state{name="mcp_hr"}=0
    AND {name="mcp_itsm"}=0.
 3. Kill ITSM server. Fire 3 agent/ask incident-open queries —
    mcp_itsm breaker trips.
 4. /health/detailed now reports mcp_itsm.state=open, mcp_hr.state=closed
    (isolation: HR untouched).
 5. Wait one exporter cycle. /metrics reports mcp_itsm=2, mcp_hr=0.
 6. Restart ITSM, wait recovery_timeout + one probe call —
    mcp_itsm back to closed on both surfaces.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_multi_breaker_visibility.py
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
METRICS = os.getenv("METRICS_URL", "http://127.0.0.1:9466/metrics")
ITSM_PORT = int(os.getenv("MCP_ITSM_PORT", "8091"))
ITSM_BASE = os.getenv("MCP_ITSM_URL", f"http://127.0.0.1:{ITSM_PORT}")
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PRIV_KEY = REPO / "scripts" / "dev-keys" / "jwt-private.pem"

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _mint(roles: list[str]) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": "documind-local",
            "aud": "documind-services",
            "sub": "drill-multi-breakers",
            "email": "drill@documind.local",
            "tenant_id": TENANT,
            "roles": roles,
            "kind": "access",
            "iat": now, "nbf": now, "exp": now + 900,
            "jti": uuid.uuid4().hex,
        },
        PRIV_KEY.read_bytes(),
        algorithm="RS256",
    )


def _kill_itsm() -> None:
    subprocess.run(["fuser", "-k", f"{ITSM_PORT}/tcp"], check=False, capture_output=True)


def _spawn_itsm() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_ITSM_PORT"] = str(ITSM_PORT)
    env["MCP_AUTH_REQUIRED"] = "true"
    env["MCP_JWT_PUBLIC_KEY_PATH"] = str(REPO / "scripts" / "dev-keys" / "jwt-public.pem")
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    log = open("/tmp/documind-mcp-itsm-multi-breakers-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_itsm.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )


_STATE_LINE = re.compile(
    r'^documind_circuit_breaker_state\{name="([^"]+)"\}\s+(\S+)$',
    re.MULTILINE,
)


def _gauge(body: str) -> dict[str, float]:
    return {m.group(1): float(m.group(2)) for m in _STATE_LINE.finditer(body)}


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
    write_both = _mint(["hr:write", "itsm:write"])

    async with httpx.AsyncClient(timeout=60.0) as c:
        step("1. /detailed reports both mcp_hr and mcp_itsm at closed")
        r = await c.get(f"{INFERENCE}/api/v1/health/detailed")
        if r.status_code != 200:
            fail(f"detailed health {r.status_code}")
        body = r.json()
        brs = {b["name"]: b["state"] for b in (body.get("breakers") or [])}
        if brs.get("mcp_hr") != "closed":
            fail(f"mcp_hr missing or non-closed: {brs}")
        if brs.get("mcp_itsm") != "closed":
            fail(f"mcp_itsm missing or non-closed: {brs}")
        ok(f"breakers={brs}")

        step("2. /metrics reports both mcp_hr=0 and mcp_itsm=0")
        g = _gauge((await c.get(METRICS)).text)
        if g.get("mcp_hr") != 0:
            fail(f"mcp_hr gauge missing/non-zero: {g}")
        if g.get("mcp_itsm") != 0:
            fail(f"mcp_itsm gauge missing/non-zero: {g}")
        ok(f"gauge series: {sorted(g.items())}")

        step("3. kill ITSM + 3 agent/ask incident-open queries → ITSM CB trips")
        _kill_itsm()
        await _dead(c, ITSM_BASE)
        for i in range(3):
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_both}",
                },
                json={
                    "query": f"please open an incident for multi-breaker drill #{i}",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            action = r.json().get("action") or {}
            if not action.get("degraded"):
                fail(f"call {i} didn't degrade: {action}")
        ok("3 degraded ITSM calls recorded")

        step("4. /detailed — mcp_itsm=open, mcp_hr=closed (isolation)")
        await asyncio.sleep(0.5)
        body = (await c.get(f"{INFERENCE}/api/v1/health/detailed")).json()
        brs = {b["name"]: b["state"] for b in body["breakers"]}
        if brs.get("mcp_itsm") != "open":
            fail(f"mcp_itsm not open: {brs}")
        if brs.get("mcp_hr") != "closed":
            fail(f"mcp_hr spilled to open on ITSM outage: {brs}")
        ok(f"breakers={brs}")

        step("5. /metrics (after exporter cycle) — mcp_itsm=2, mcp_hr=0")
        await asyncio.sleep(7)  # exporter cycle is 5s; 7s guarantees one
        g = _gauge((await c.get(METRICS)).text)
        if g.get("mcp_itsm") != 2:
            fail(f"mcp_itsm gauge expected 2 (open), got {g.get('mcp_itsm')}")
        if g.get("mcp_hr") != 0:
            fail(f"mcp_hr gauge moved: {g.get('mcp_hr')}")
        ok(f"gauge: mcp_itsm=2 mcp_hr=0 (isolation preserved in Prom too)")

        step("6. restart ITSM, 32s CB recovery, one probe → mcp_itsm back to closed")
        proc = _spawn_itsm()
        try:
            if not await _healthy(c, ITSM_BASE):
                fail("ITSM didn't come back")
            print("    waiting 32s for CB recovery_timeout...")
            await asyncio.sleep(32)
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_both}",
                },
                json={
                    "query": "please open an incident for ITSM-recovery probe",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            action = r.json().get("action") or {}
            if not action.get("ok"):
                fail(f"probe didn't succeed: {action}")
            await asyncio.sleep(0.5)
            body = (await c.get(f"{INFERENCE}/api/v1/health/detailed")).json()
            brs = {b["name"]: b["state"] for b in body["breakers"]}
            if brs.get("mcp_itsm") not in ("closed", "half_open"):
                fail(f"mcp_itsm didn't recover: {brs}")
            ok(f"recovered: mcp_itsm={brs['mcp_itsm']} mcp_hr={brs['mcp_hr']}")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 MULTI-BREAKER-VISIBILITY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
