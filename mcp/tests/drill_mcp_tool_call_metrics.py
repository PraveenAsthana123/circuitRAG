# RESOURCES: mcp_hr
"""
Drill: documind_mcp_tool_calls_total counter on each MCP server.

Each MCP server now mounts /metrics exposing a counter labelled by
(namespace, tool, outcome). This gives ops per-tool volume + failure
rate without going through Jaeger.

Flow:
 1. Baseline snapshot of the counter for mcp_hr's hr.leave_request
    (any outcome).
 2. 3 successful hr.leave_request calls → outcome=ok +3.
 3. 1 idempotent replay (same key twice) → outcome=replay +1 for
    the second call.
 4. Call with an unknown tool name → HTTP 404 → outcome=http_404 +1.
 5. Label isolation: hr.policy_lookup counters unchanged throughout.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_mcp_tool_call_metrics.py
"""
from __future__ import annotations

import asyncio
import os
import re
import uuid
from pathlib import Path

import httpx

HR_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


_LINE = re.compile(
    r'^documind_mcp_tool_calls_total\{([^}]*)\}\s+(\S+)$',
    re.MULTILINE,
)


def _parse(body: str) -> dict[tuple[str, str, str], float]:
    out: dict[tuple[str, str, str], float] = {}
    for m in _LINE.finditer(body):
        labels: dict[str, str] = {}
        for part in m.group(1).split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            labels[k.strip()] = v.strip().strip('"')
        key = (
            labels.get("namespace", ""),
            labels.get("tool", ""),
            labels.get("outcome", ""),
        )
        try:
            out[key] = float(m.group(2))
        except ValueError:
            continue
    return out


async def _scrape(c: httpx.AsyncClient) -> dict[tuple[str, str, str], float]:
    r = await c.get(f"{HR_BASE}/metrics")
    if r.status_code != 200:
        fail(f"/metrics returned {r.status_code}")
    return _parse(r.text)


async def _call(c: httpx.AsyncClient, name: str, args: dict, idem: str | None = None) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    return await c.post(
        f"{HR_BASE}/tools/call",
        headers=headers,
        json={
            "name": name,
            "arguments": args,
            "tenant_id": TENANT,
        },
    )


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as c:
        step("1. baseline counter snapshot")
        before = await _scrape(c)
        hr_leave_ok_before = before.get(("mcp_hr", "hr.leave_request", "ok"), 0)
        hr_leave_replay_before = before.get(("mcp_hr", "hr.leave_request", "replay"), 0)
        hr_policy_ok_before = before.get(("mcp_hr", "hr.policy_lookup", "ok"), 0)
        unknown_before = before.get(("mcp_hr", "hr.nonexistent", "http_404"), 0)
        ok(
            f"leave_ok={hr_leave_ok_before} leave_replay={hr_leave_replay_before} "
            f"policy_ok={hr_policy_ok_before}"
        )

        step("2. 3 successful hr.leave_request → outcome=ok +3")
        for i in range(3):
            r = await _call(
                c, "hr.leave_request",
                {"employee_id": "E1", "days": i + 1, "reason": f"metrics drill {i}"},
            )
            if r.status_code != 200 or not r.json().get("ok"):
                fail(f"call {i}: {r.status_code} {r.text[:200]}")
        await asyncio.sleep(0.2)
        after = await _scrape(c)
        delta_ok = after.get(("mcp_hr", "hr.leave_request", "ok"), 0) - hr_leave_ok_before
        if delta_ok != 3:
            fail(f"expected leave_ok +3, got +{int(delta_ok)}")
        if after.get(("mcp_hr", "hr.policy_lookup", "ok"), 0) != hr_policy_ok_before:
            fail("policy_ok moved when it shouldn't have (label isolation)")
        ok(f"leave_ok +{int(delta_ok)}; policy_ok unchanged")

        step("3. idempotent replay — outcome=replay +1")
        idem = str(uuid.uuid4())
        await _call(
            c, "hr.leave_request",
            {"employee_id": "E1", "days": 1, "reason": "idem-replay"}, idem=idem,
        )
        await _call(
            c, "hr.leave_request",
            {"employee_id": "E1", "days": 1, "reason": "idem-replay"}, idem=idem,
        )
        await asyncio.sleep(0.2)
        post = await _scrape(c)
        delta_replay = (
            post.get(("mcp_hr", "hr.leave_request", "replay"), 0)
            - hr_leave_replay_before
        )
        if delta_replay != 1:
            fail(f"expected leave_replay +1, got +{int(delta_replay)}")
        # Note: the FIRST idem call also counts as ok, so ok counter went +4 total since start of test
        # (3 from step 2 + 1 new). That's fine — assertion here is just that replay fires.
        ok(f"leave_replay +{int(delta_replay)} (first call ok, second replay)")

        step("4. unknown tool name → outcome=http_404 +1")
        r = await _call(c, "hr.nonexistent", {})
        if r.status_code != 404:
            fail(f"expected 404, got {r.status_code}")
        await asyncio.sleep(0.2)
        post2 = await _scrape(c)
        delta_404 = (
            post2.get(("mcp_hr", "hr.nonexistent", "http_404"), 0) - unknown_before
        )
        if delta_404 != 1:
            fail(f"expected http_404 +1, got +{int(delta_404)}")
        ok(f"http_404 +{int(delta_404)} on unknown tool")

        step("5. label isolation — hr.policy_lookup counters unchanged")
        final = post2
        if final.get(("mcp_hr", "hr.policy_lookup", "ok"), 0) != hr_policy_ok_before:
            fail("policy_ok counter moved during drill")
        ok("label isolation preserved")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 TOOL-CALL-METRICS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
