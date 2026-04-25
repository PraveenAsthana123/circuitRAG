# RESOURCES: mcp_hr inference pg
"""
Drill: documind_circuit_breaker_transitions_total counts only real
state changes, not every poll.

Gauge (``_state``) tells you state NOW. Counter (``_transitions_total``)
tells you HOW OFTEN a breaker has flapped. Together: alert on
"state is open for 5 minutes" AND on "breaker has flipped >5 times
in the last 10 minutes" — both are important, different signals.

Flow:
 1. Baseline counter snapshot.
 2. Kill MCP + 3 agent/ask → mcp_hr CB closed→open: +1 counter on the
    closed→open label.
 3. Wait one exporter cycle. Counter still +1 (no double-count from
    polls).
 4. Restart MCP + wait CB recovery + probe call → open→half_open→closed
    path. Counter picks up at least one transition on the recovery
    edge (half_open→closed OR open→closed depending on poll timing).
 5. Counter for ``mcp_hr`` strictly > baseline; counter for
    unrelated ``retrieval-svc`` series UNCHANGED (label isolation).

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_breaker_transitions.py
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
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PRIV_KEY = REPO / "scripts" / "dev-keys" / "jwt-public.pem"
PRIV_KEY_SIGN = REPO / "scripts" / "dev-keys" / "jwt-private.pem"

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
            "sub": "drill-transitions",
            "email": "drill@documind.local",
            "tenant_id": TENANT,
            "roles": roles,
            "kind": "access",
            "iat": now, "nbf": now, "exp": now + 900,
            "jti": uuid.uuid4().hex,
        },
        PRIV_KEY_SIGN.read_bytes(),
        algorithm="RS256",
    )


# Matches: documind_circuit_breaker_transitions_total{name="...",from_state="...",to_state="..."}  <value>
_TR_LINE = re.compile(
    r'^documind_circuit_breaker_transitions_total\{([^}]*)\}\s+(\S+)$',
    re.MULTILINE,
)


def _transitions(body: str) -> dict[tuple[str, str, str], float]:
    out: dict[tuple[str, str, str], float] = {}
    for m in _TR_LINE.finditer(body):
        labels = {}
        for part in m.group(1).split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            labels[k.strip()] = v.strip().strip('"')
        key = (labels.get("name", ""), labels.get("from_state", ""), labels.get("to_state", ""))
        try:
            out[key] = float(m.group(2))
        except ValueError:
            continue
    return out


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    env["MCP_AUTH_REQUIRED"] = "true"
    env["MCP_JWT_PUBLIC_KEY_PATH"] = str(PRIV_KEY)
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    log = open("/tmp/documind-mcp-hr-transitions-drill.log", "w")
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


async def _wait_recovery_timeout(c: httpx.AsyncClient, namespace: str) -> float:
    """
    Read ``recovery_timeout_s`` from /health/detailed and sleep that
    duration + 0.5s. Same pattern as drill_audit_actor_type — drives
    the wait length from the live breaker config rather than baking
    a fixed ``sleep(32)`` into the drill. If recovery_timeout changes
    via env or prod tune, the drill picks it up automatically.

    Returns the timeout actually waited (seconds) so the caller can
    log it for diagnosis.
    """
    target = f"mcp_{namespace}"
    r = await c.get(f"{INFERENCE}/api/v1/health/detailed", timeout=2.0)
    if r.status_code == 200:
        for b in r.json().get("breakers", []):
            if b.get("name") == target:
                rt = b.get("recovery_timeout_s")
                if rt is not None:
                    await asyncio.sleep(float(rt) + 0.5)
                    return float(rt)
    # Fallback for older inference-svc versions that don't expose
    # recovery_timeout_s. Conservative — better to wait too long than
    # probe before the breaker eligibility window opens.
    await asyncio.sleep(30.5)
    return 30.0


async def _poll_metrics_until(
    c: httpx.AsyncClient,
    predicate,  # callable(transitions_dict) -> bool
    *,
    deadline_s: float = 12.0,
    poll_s: float = 0.5,
) -> dict[tuple[str, str, str], float]:
    """
    Poll /metrics until ``predicate(transitions)`` returns True or the
    deadline elapses. Replaces the fixed ``await asyncio.sleep(7)``
    "exporter cycle + scrape" pattern — observation-driven instead of
    guessing-the-cycle. Returns the final transitions dict on success;
    raises if the deadline elapses (deterministic CI signal that the
    expected counter delta never landed).

    BreakerMetricsExporter pushes state every 5s by default, so a 12s
    deadline gives us comfortably more than one full cycle while still
    failing fast if metrics are stuck.
    """
    end = asyncio.get_running_loop().time() + deadline_s
    last: dict[tuple[str, str, str], float] = {}
    while asyncio.get_running_loop().time() < end:
        try:
            r = await c.get(METRICS, timeout=2.0)
            if r.status_code == 200:
                last = _transitions(r.text)
                if predicate(last):
                    return last
        except httpx.HTTPError:
            pass
        await asyncio.sleep(poll_s)
    raise RuntimeError(
        f"transitions counter did not satisfy predicate within {deadline_s}s; "
        f"last seen: { {k: v for k, v in last.items() if k[0] == 'mcp_hr'} }"
    )


async def main() -> None:
    write_tok = _mint(["hr:read", "hr:write"])
    async with httpx.AsyncClient(timeout=60.0) as c:
        step("1. baseline transition counter snapshot for mcp_hr")
        r = await c.get(METRICS)
        if r.status_code != 200:
            fail(f"/metrics returned {r.status_code}")
        before = _transitions(r.text)
        baseline_closed_open = before.get(("mcp_hr", "closed", "open"), 0)
        baseline_hopen_closed = (
            before.get(("mcp_hr", "half_open", "closed"), 0)
            + before.get(("mcp_hr", "open", "closed"), 0)
        )
        baseline_retrieval = before.get(("retrieval-svc", "closed", "open"), 0)
        ok(
            f"mcp_hr closed→open={baseline_closed_open} "
            f"recovery_edges={baseline_hopen_closed} "
            f"retrieval baseline={baseline_retrieval}"
        )

        step("2. kill MCP + 3 agent/ask → mcp_hr closed→open (+1)")
        _kill_mcp()
        await _dead(c, MCP_BASE)
        for i in range(3):
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_tok}",
                },
                json={
                    "query": f"please submit a {i+1}-day leave for transition drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            if (r.json().get("action") or {}).get("degraded") is not True:
                fail(f"call {i} didn't degrade")
        ok("3 degraded calls — CB should have tripped")

        step("3. poll /metrics for closed→open delta — counter +1, not +N")
        # Replaced fixed sleep(7) with bounded polling. The exporter
        # pushes every 5s, so we wait up to 12s (>1 full cycle) for
        # the closed→open delta to land. Faster CI on the happy path
        # (often arrives in 2-3s) and a deterministic failure on
        # genuine bugs.
        after = await _poll_metrics_until(
            c,
            lambda t: t.get(("mcp_hr", "closed", "open"), 0) - baseline_closed_open >= 1,
        )
        delta = after.get(("mcp_hr", "closed", "open"), 0) - baseline_closed_open
        if delta > 2:
            # Allow ≤2 in case the CB flapped briefly during setup; but > 2
            # means every poll is counting as a transition (the bug).
            fail(f"counter inflated — delta={delta} suggests per-poll counting")
        ok(f"mcp_hr closed→open delta={int(delta)} (poll-robust)")
        # Label isolation: retrieval-svc counter unchanged.
        if after.get(("retrieval-svc", "closed", "open"), 0) != baseline_retrieval:
            fail(f"retrieval-svc counter moved on mcp_hr event: {after}")

        step("4. restart MCP + config-driven recovery wait + probe → recovery edge +1")
        mcp_proc = _spawn_mcp()
        try:
            if not await _healthy(c, MCP_BASE):
                fail("MCP didn't come back")
            # Read recovery_timeout_s from /health/detailed instead of
            # hardcoding 32. If the breaker config changes (env override,
            # prod tune), the drill picks it up automatically.
            waited = await _wait_recovery_timeout(c, "hr")
            print(f"    waited {waited:.1f}s (config-driven recovery_timeout)")
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_tok}",
                },
                json={
                    "query": "please submit a 1-day leave for recovery probe",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            if not (r.json().get("action") or {}).get("ok"):
                fail(f"probe didn't succeed: {r.json()}")
            # Poll /metrics for the recovery edge instead of a fixed 7s
            # wait. The exporter pushes every 5s; predicate succeeds as
            # soon as ANY recovery edge counter moved.
            post = await _poll_metrics_until(
                c,
                lambda t: (
                    (t.get(("mcp_hr", "half_open", "closed"), 0)
                     + t.get(("mcp_hr", "open", "closed"), 0)
                     + t.get(("mcp_hr", "open", "half_open"), 0))
                    - baseline_hopen_closed
                    >= 1
                ),
            )
            # Recovery can show as open→half_open then half_open→closed OR
            # directly open→closed depending on when the exporter polled.
            # Accept either; what matters: SOME recovery-edge counter moved.
            recovery_delta = (
                post.get(("mcp_hr", "half_open", "closed"), 0)
                + post.get(("mcp_hr", "open", "closed"), 0)
                + post.get(("mcp_hr", "open", "half_open"), 0)
                - baseline_hopen_closed
            )
            ok(f"mcp_hr recovery edges delta={int(recovery_delta)}")
        finally:
            if mcp_proc.poll() is None:
                mcp_proc.terminate()
                try:
                    mcp_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    mcp_proc.kill()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 TRANSITION-COUNTER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
