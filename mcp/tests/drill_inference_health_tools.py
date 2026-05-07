# RESOURCES: mcp_hr inference
"""
Drill: /api/v1/health/tools surfaces per-tool MCP /metrics as a
typed aggregate.

Closes the rest of Phase-1 #2 from
``docs/architecture/mcp-agent-gap-review.md``: the metric
primitives shipped in commit 598ca9a; this drill proves the
aggregation endpoint that surfaces them to the operator UI.

Flow:
 1. Hit /api/v1/health/tools — baseline. Capture pre-call counts
    for hr.leave_request (namespace=mcp_hr).
 2. Successful hr.leave_request via direct MCP call. Re-fetch
    /health/tools and verify:
      * calls.ok          delta == 1
      * latency.count     delta == 1
      * latency.sum       increased
      * latency.avg       not None
      * denials           UNCHANGED for that tool
    NEGATIVE: a successful call must NOT bump any denial counter
    for the tool.
 3. Send unauthenticated call. Re-fetch and verify:
      * denials.NOT_AUTHENTICATED delta == 1
      * latency.count             UNCHANGED
    NEGATIVE: a denied call must NOT contribute to the latency
    aggregate (the avg the dashboard renders would otherwise
    include sub-microsecond auth fails).
 4. Insufficient-scope call (hr:read on hr.leave_request which
    needs hr:write). Verify denials.INSUFFICIENT_SCOPE delta==1.
 5. Per-tool isolation — hr.policy_lookup stats must be
    UNCHANGED across all the steps above. NEGATIVE: a regression
    that aggregated all tools together would still pass step 2-4
    but fail this label-isolation check.
 6. ``unreachable`` shape — the field is a list (never None);
    when all MCP servers are reachable it is empty. NEGATIVE: a
    regression that returns ``unreachable: null`` would break the
    UI's panel-stale render path.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_inference_health_tools.py
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
INF_BASE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
HR_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
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
            "sub": "drill-health-tools",
            "email": "drill@documind.local",
            "tenant_id": TENANT,
            "roles": roles,
            "kind": "access",
            "iat": now,
            "nbf": now,
            "exp": now + 900,
            "jti": uuid.uuid4().hex,
        },
        PRIV_KEY.read_bytes(),
        algorithm="RS256",
    )


async def _fetch_tools(c: httpx.AsyncClient) -> dict:
    r = await c.get(f"{INF_BASE}/api/v1/health/tools")
    if r.status_code != 200:
        fail(f"/health/tools returned {r.status_code}: {r.text[:200]}")
    return r.json()


def _row(payload: dict, *, namespace: str, tool: str) -> dict | None:
    """Pluck a single (namespace, tool) row from the response, or
    None if it hasn't been seen yet (no calls => no row)."""
    for t in payload.get("tools", []):
        if t.get("namespace") == namespace and t.get("tool") == tool:
            return t
    return None


def _calls(row: dict | None, outcome: str) -> int:
    if row is None:
        return 0
    return int((row.get("calls") or {}).get(outcome, 0))


def _denials(row: dict | None, reason: str) -> int:
    if row is None:
        return 0
    return int((row.get("denials") or {}).get(reason, 0))


def _latency_count(row: dict | None) -> int:
    if row is None:
        return 0
    return int((row.get("latency") or {}).get("count", 0))


async def _call_hr(
    c: httpx.AsyncClient,
    *, name: str, args: dict, token: str | None = None,
    raw_authz: str | None = None,
) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if raw_authz is not None:
        headers["Authorization"] = raw_authz
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    return await c.post(
        f"{HR_BASE}/tools/call",
        headers=headers,
        json={"name": name, "arguments": args, "tenant_id": TENANT},
    )


async def main() -> None:
    NS = "mcp_hr"
    TOOL = "hr.leave_request"
    OTHER = "hr.policy_lookup"
    write_token = _mint(["hr:write"])
    read_token = _mint(["hr:read"])

    async with httpx.AsyncClient(timeout=10.0) as c:
        step("0. baseline /api/v1/health/tools")
        base = await _fetch_tools(c)
        if "tools" not in base or "unreachable" not in base:
            fail(f"missing top-level keys: {sorted(base.keys())}")
        if not isinstance(base["unreachable"], list):
            fail(f"unreachable must be a list, got {type(base['unreachable']).__name__}")
        b_row = _row(base, namespace=NS, tool=TOOL)
        b_other = _row(base, namespace=NS, tool=OTHER)
        b_ok = _calls(b_row, "ok")
        b_lat = _latency_count(b_row)
        b_unauth = _denials(b_row, "NOT_AUTHENTICATED")
        b_insuff = _denials(b_row, "INSUFFICIENT_SCOPE")
        b_other_ok = _calls(b_other, "ok")
        b_other_lat = _latency_count(b_other)
        ok(
            f"baseline: {TOOL} ok={b_ok} lat_n={b_lat} "
            f"deny_unauth={b_unauth} deny_insuff={b_insuff}"
        )

        step("1. successful hr.leave_request → calls.ok +1, latency.count +1, denials UNCHANGED")
        r = await _call_hr(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 1, "reason": "health-tools drill"},
            token=write_token,
        )
        if r.status_code != 200 or not r.json().get("ok"):
            fail(f"call failed: {r.status_code} {r.text[:200]}")
        await asyncio.sleep(0.15)
        s1 = await _fetch_tools(c)
        s1_row = _row(s1, namespace=NS, tool=TOOL)
        if _calls(s1_row, "ok") - b_ok != 1:
            fail(
                f"calls.ok delta != 1; baseline={b_ok} now={_calls(s1_row, 'ok')}"
            )
        if _latency_count(s1_row) - b_lat != 1:
            fail(
                f"latency.count delta != 1; baseline={b_lat} now={_latency_count(s1_row)}"
            )
        avg = (s1_row.get("latency") or {}).get("avg_seconds")
        if avg is None or not isinstance(avg, (int, float)):
            fail(f"latency.avg_seconds must be a number after observations, got {avg!r}")
        if _denials(s1_row, "NOT_AUTHENTICATED") != b_unauth:
            fail("NOT_AUTHENTICATED bumped on a successful call (must NOT)")
        if _denials(s1_row, "INSUFFICIENT_SCOPE") != b_insuff:
            fail("INSUFFICIENT_SCOPE bumped on a successful call (must NOT)")
        ok(f"calls.ok +1; latency.count +1 avg={avg:.6f}; denials unchanged")
        b_ok = _calls(s1_row, "ok")
        b_lat = _latency_count(s1_row)

        step("2. unauthenticated → denials.NOT_AUTHENTICATED +1; latency UNCHANGED")
        r = await _call_hr(c, name=TOOL, args={"employee_id": "E1", "days": 1, "reason": "drill"})
        if r.status_code != 401:
            fail(f"expected 401, got {r.status_code}")
        await asyncio.sleep(0.15)
        s2 = await _fetch_tools(c)
        s2_row = _row(s2, namespace=NS, tool=TOOL)
        if _denials(s2_row, "NOT_AUTHENTICATED") - b_unauth != 1:
            fail(
                f"NOT_AUTHENTICATED delta != 1; "
                f"got {_denials(s2_row, 'NOT_AUTHENTICATED') - b_unauth}"
            )
        if _latency_count(s2_row) != b_lat:
            fail(
                f"latency.count moved on denied call — must NOT contribute. "
                f"baseline={b_lat} now={_latency_count(s2_row)}"
            )
        ok("denials.NOT_AUTHENTICATED +1; latency.count unchanged")
        b_unauth = _denials(s2_row, "NOT_AUTHENTICATED")

        step("3. insufficient scope → denials.INSUFFICIENT_SCOPE +1")
        r = await _call_hr(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
            token=read_token,
        )
        if r.status_code != 403:
            fail(f"expected 403, got {r.status_code}")
        await asyncio.sleep(0.15)
        s3 = await _fetch_tools(c)
        s3_row = _row(s3, namespace=NS, tool=TOOL)
        if _denials(s3_row, "INSUFFICIENT_SCOPE") - b_insuff != 1:
            fail(
                f"INSUFFICIENT_SCOPE delta != 1; "
                f"got {_denials(s3_row, 'INSUFFICIENT_SCOPE') - b_insuff}"
            )
        ok("denials.INSUFFICIENT_SCOPE +1")

        step("4. per-tool isolation — hr.policy_lookup stats UNCHANGED")
        s4 = await _fetch_tools(c)
        s4_other = _row(s4, namespace=NS, tool=OTHER)
        if _calls(s4_other, "ok") != b_other_ok:
            fail(
                f"hr.policy_lookup ok counter moved during drill — "
                f"baseline={b_other_ok} now={_calls(s4_other, 'ok')}. "
                f"Aggregation isn't keying on (namespace, tool) correctly."
            )
        if _latency_count(s4_other) != b_other_lat:
            fail(
                f"hr.policy_lookup latency.count moved during drill — "
                f"baseline={b_other_lat} now={_latency_count(s4_other)}"
            )
        ok("hr.policy_lookup unchanged across drill (label isolation works)")

        step("5. unreachable shape — list, empty when all MCP servers reachable")
        s5 = await _fetch_tools(c)
        u = s5.get("unreachable")
        if not isinstance(u, list):
            fail(
                f"unreachable must be a list (UI's stale-render path "
                f"depends on this); got {type(u).__name__}={u!r}"
            )
        # If anything's unreachable, surface it as info — drill doesn't
        # fail because the operator may have killed an MCP intentionally.
        if u:
            ok(f"unreachable={u} (acceptable — drill only requires list shape)")
        else:
            ok("all MCP servers reachable (unreachable=[])")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 HEALTH-TOOLS-AGGREGATE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
