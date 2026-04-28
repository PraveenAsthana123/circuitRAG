# RESOURCES: inference mcp_hr
"""
Drill: Idempotency-Key header at /api/v1/agent/ask dedupes retries.

Scenario: a client POSTs agent/ask with a leave request. Network
hiccups mid-response; the client retries with the same
Idempotency-Key. MCP must return the SAME ticket_id (via its
internal idempotency cache), not create a second one.

Flow:
 1. Agent/ask + idem_key → ticket_id=T1, idempotent_replay=False.
 2. Agent/ask + SAME idem_key + same payload → ticket_id=T1 (same!),
    idempotent_replay=True.
 3. Agent/ask + different idem_key → ticket_id=T2 (different), replay=False.
 4. Agent/ask WITHOUT idem_key (two back-to-back calls) → two
    different tickets. Proves the header is the trigger, not some
    accidental auto-dedup.
 5. Lowercase header variant + X-Idempotency-Key → both accepted
    equivalently.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_agent_idempotency.py

Prereqs: inference-svc + MCP running. Auth may be on or off;
when on, the drill supplies a write-capable token.
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
INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
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


def _mint() -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": "documind-local",
            "aud": "documind-services",
            "sub": "drill-idempotency",
            "email": "drill@documind.local",
            "tenant_id": TENANT,
            "roles": ["hr:read", "hr:write"],
            "kind": "access",
            "iat": now, "nbf": now, "exp": now + 900,
            "jti": uuid.uuid4().hex,
        },
        PRIV_KEY.read_bytes(),
        algorithm="RS256",
    )


def _ticket(body: dict) -> str:
    return ((body.get("action") or {}).get("result") or {}).get("ticket_id", "")


def _replay(body: dict) -> bool:
    return bool((body.get("action") or {}).get("idempotent_replay"))


async def _post(c: httpx.AsyncClient, token: str, headers_extra: dict, days: int, reason: str) -> dict:
    r = await c.post(
        f"{INFERENCE}/api/v1/agent/ask",
        headers={
            "X-Tenant-Id": TENANT,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **headers_extra,
        },
        json={
            "query": f"please submit a {days}-day leave request for {reason}",
            "employee_id": "E42",
        },
        timeout=60.0,
    )
    if r.status_code != 200:
        fail(f"agent/ask returned {r.status_code}: {r.text[:200]}")
    return r.json()


async def main() -> None:
    token = _mint()
    async with httpx.AsyncClient(timeout=60.0) as c:
        idem = str(uuid.uuid4())
        step(f"1. first call with Idempotency-Key={idem[:12]}...")
        body1 = await _post(c, token, {"Idempotency-Key": idem}, 1, "idempotency-first")
        t1 = _ticket(body1)
        if not t1:
            fail(f"no ticket on first call: {body1.get('action')}")
        if _replay(body1):
            fail(f"first call shouldn't be idempotent_replay=True: {body1['action']}")
        ok(f"ticket_id={t1} idempotent_replay=False")

        step("2. same Idempotency-Key again → same ticket, replay=True")
        body2 = await _post(c, token, {"Idempotency-Key": idem}, 1, "idempotency-first")
        t2 = _ticket(body2)
        if t2 != t1:
            fail(f"ticket changed on replay: {t1} → {t2}")
        if not _replay(body2):
            fail(f"replay flag not set: {body2['action']}")
        ok(f"ticket_id={t2} idempotent_replay=True")

        step("3. different Idempotency-Key → new ticket")
        idem_b = str(uuid.uuid4())
        body3 = await _post(c, token, {"Idempotency-Key": idem_b}, 1, "idempotency-second")
        t3 = _ticket(body3)
        if not t3 or t3 == t1:
            fail(f"expected new ticket, got {t3} (original was {t1})")
        if _replay(body3):
            fail(f"new key should not be replay: {body3['action']}")
        ok(f"ticket_id={t3} (new, not {t1})")

        step("4. no Idempotency-Key — two calls get DIFFERENT tickets")
        body4a = await _post(c, token, {}, 1, "idempotency-noheader-a")
        body4b = await _post(c, token, {}, 1, "idempotency-noheader-b")
        ta, tb = _ticket(body4a), _ticket(body4b)
        if not ta or not tb:
            fail(f"missing tickets: {ta}, {tb}")
        if ta == tb:
            fail(f"no-header calls got SAME ticket — accidental dedup?")
        ok(f"two distinct tickets {ta} and {tb} (no header → no dedup)")

        step("5. X-Idempotency-Key alias works equivalently")
        idem_c = str(uuid.uuid4())
        body5a = await _post(c, token, {"X-Idempotency-Key": idem_c}, 2, "idempotency-alias")
        body5b = await _post(c, token, {"X-Idempotency-Key": idem_c}, 2, "idempotency-alias")
        if _ticket(body5a) != _ticket(body5b):
            fail(f"X-Idempotency-Key alias didn't dedup: {_ticket(body5a)} vs {_ticket(body5b)}")
        if not _replay(body5b):
            fail(f"alias second call didn't set replay=True: {body5b['action']}")
        ok(f"X-Idempotency-Key alias: same ticket {_ticket(body5a)} + replay=True")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 IDEMPOTENCY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
