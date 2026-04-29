# RESOURCES: inference mcp_hr
"""
Drill: documind_agent_denials_total increments on agent-level rejections.

Complements drill_agent_denial_audit (forensics, PG-hash-chained) with
a real-time aggregation signal (Prometheus counter). Together they
cover two operational time horizons — alert within a minute, investigate
within a quarter.

Flow:
 1. Snapshot baseline counter values from /metrics.
 2. Fire hr:read + leave_request → intent=action_denied_scope.
    Assert `documind_agent_denials_total{reason="scope",tool="hr.leave_request"}`
    incremented by exactly 1.
 3. Fire hr:write + leave_request with `allow_actions=false` →
    intent=action_declined. Assert
    `documind_agent_denials_total{reason="allow_actions_false",tool="hr.leave_request"}`
    incremented by exactly 1.
 4. Fire hr:write + leave_request happy path → NO counter increment.
 5. Fire a plain-RAG query (no intent match) → NO counter increment.

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_agent_denial_metrics.py
"""
from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
METRICS = os.getenv("METRICS_URL", "http://127.0.0.1:9466/metrics")
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
            "sub": "drill-denial-metrics",
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


# Prometheus exposition: documind_agent_denials_total{reason="...",tool="..."}  <value>
_COUNTER_RE = re.compile(
    r'^documind_agent_denials_total\{([^}]*)\}\s+(\S+)$',
    re.MULTILINE,
)


def _parse_counter(body: str) -> dict[tuple[str, str], float]:
    """Return {(reason, tool): value} from /metrics body."""
    out: dict[tuple[str, str], float] = {}
    for m in _COUNTER_RE.finditer(body):
        label_str, value = m.group(1), m.group(2)
        labels = dict(
            p.split("=", 1) for p in label_str.split(",") if "=" in p
        )
        reason = labels.get("reason", "").strip().strip('"')
        tool = labels.get("tool", "").strip().strip('"')
        try:
            out[(reason, tool)] = float(value)
        except ValueError:
            continue
    return out


async def _sample(c: httpx.AsyncClient) -> dict[tuple[str, str], float]:
    r = await c.get(METRICS)
    if r.status_code != 200:
        fail(f"metrics endpoint returned {r.status_code}")
    return _parse_counter(r.text)


async def main() -> None:
    read_tok = _mint(["hr:read"])
    write_tok = _mint(["hr:read", "hr:write"])

    async with httpx.AsyncClient(timeout=60.0) as c:
        step("1. baseline counter snapshot")
        before = await _sample(c)
        ok(f"baseline: {before}")

        step("2. hr:read + leave_request → reason=scope tool=hr.leave_request +1")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {read_tok}",
            },
            json={
                "query": "please submit a 1-day leave request for metrics-scope drill",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        if r.json().get("intent") != "action_denied_scope":
            fail(f"intent wrong: {r.json().get('intent')}")
        await asyncio.sleep(0.3)
        after = await _sample(c)
        key = ("scope", "hr.leave_request")
        delta = after.get(key, 0) - before.get(key, 0)
        if delta != 1:
            fail(f"scope counter delta={delta} (expected 1)  before={before}  after={after}")
        ok(f"reason=scope tool=hr.leave_request +1 (total={after.get(key, 0)})")

        step("3. hr:write + allow_actions=false → reason=allow_actions_false +1")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {write_tok}",
            },
            json={
                "query": "please submit a 1-day leave request for metrics-decline drill",
                "employee_id": "E42",
                "allow_actions": False,
            },
            timeout=60.0,
        )
        if r.json().get("intent") != "action_declined":
            fail(f"intent wrong: {r.json().get('intent')}")
        await asyncio.sleep(0.3)
        after2 = await _sample(c)
        key2 = ("allow_actions_false", "hr.leave_request")
        delta2 = after2.get(key2, 0) - after.get(key2, 0)
        if delta2 != 1:
            fail(f"allow_actions_false delta={delta2} (expected 1)  before={after}  after={after2}")
        # And the scope counter should NOT have moved
        if after2.get(key, 0) != after.get(key, 0):
            fail(
                f"scope counter shifted on decline path: "
                f"{after.get(key, 0)} → {after2.get(key, 0)}"
            )
        ok(f"reason=allow_actions_false +1; scope counter untouched")

        step("4. hr:write happy path — NO counter increment")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {write_tok}",
            },
            json={
                "query": "please submit a 1-day leave request for metrics-happy",
                "employee_id": "E42",
            },
            timeout=60.0,
        )
        body = r.json()
        if body.get("intent") != "action":
            fail(f"expected intent=action, got {body.get('intent')}")
        await asyncio.sleep(0.3)
        after3 = await _sample(c)
        # The scope and decline totals should both be unchanged since after2
        if after3.get(key, 0) != after2.get(key, 0):
            fail("scope counter moved on happy path")
        if after3.get(key2, 0) != after2.get(key2, 0):
            fail("decline counter moved on happy path")
        ok(f"no counter changes on happy path (as expected)")

        step("5. plain-RAG query — NO counter increment")
        r = await c.post(
            f"{INFERENCE}/api/v1/agent/ask",
            headers={
                "X-Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Authorization": f"Bearer {read_tok}",
            },
            json={
                "query": "what is the travel reimbursement limit?",
            },
            timeout=60.0,
        )
        if r.json().get("intent") != "answer":
            fail(f"expected intent=answer, got {r.json().get('intent')}")
        await asyncio.sleep(0.3)
        after4 = await _sample(c)
        if after4 != after3:
            fail(
                f"counter moved on plain-RAG (intent shouldn't have matched any tool):\n"
                f"before={after3}\nafter={after4}"
            )
        ok("plain-RAG query left all counters untouched")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 DENIAL-METRICS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
