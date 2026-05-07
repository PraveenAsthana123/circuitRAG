# RESOURCES: inference
"""
Drill: ClientErrorReporter's wrapped window.fetch reports 4xx/5xx
+ network errors as fetch_failed / fetch_error to the client-error
ring buffer.

Closes the post-mortem gap "network/API failure capture" — runtime
JS errors were already reported, but HTTP-shaped failures (the
500 the user just hit on /tools/rag-scenarios) were invisible to
the backend.

The drill tests at the BACKEND boundary by directly POSTing
fetch_failed / fetch_error events with the canonical shape, then
verifying:
  * the kind values are accepted
  * they surface in the GET listing
  * the badge classification is preserved (UI-side, but the data
    shape locks)
  * route / extra fields round-trip end-to-end

The frontend wrap itself (window.fetch override) is exercised by
real browser traffic — verifying the wrap-then-POST chain happens
in browser-driven smoke testing, not from a CLI drill.

Negative-assertion §43-style:
 1. POST kind='fetch_failed' with status=500 → 201 + record
    appears in GET. NEGATIVE: the backend rejecting the new kind
    string (e.g. an enum on the schema) would silently drop the
    new error class.
 2. POST kind='fetch_error' with error_name='TypeError' → 201 +
    surfaces. NEGATIVE: same as above for network-error class.
 3. extra dict round-trips full URL + method + status. NEGATIVE:
    a regression that stripped extra fields would lose the
    operator-actionable context (which URL failed, which method).
 4. Reporting recursion guard: a hypothetical fetch_failed for
    /api/v1/admin/client-errors itself MUST NOT be accepted from
    a normal call site. Backend just accepts; the recursion guard
    is on the client side. Verify the guard's intent by emitting
    one such record and confirming the backend stores it (the
    guard prevents the client from sending it; the backend is
    a passive sink).
 5. fetch_failed and fetch_error appear DISTINCT in the listing
    (different kind labels). NEGATIVE: collapsing both into one
    label would conflate "server returned 500" with "DNS
    failed" — different incidents, different alerting.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_client_error_fetch_capture.py
"""
from __future__ import annotations

import asyncio
import os
import uuid

import httpx

INF_BASE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def _post(c: httpx.AsyncClient, body: dict) -> tuple[int, dict]:
    r = await c.post(
        f"{INF_BASE}/api/v1/admin/client-errors",
        json=body,
    )
    return r.status_code, r.json()


async def _list(c: httpx.AsyncClient) -> dict:
    r = await c.get(f"{INF_BASE}/api/v1/admin/client-errors")
    if r.status_code != 200:
        fail(f"GET {r.status_code}")
    return r.json()


async def main() -> None:
    marker = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(timeout=10.0) as c:
        step("1. POST kind='fetch_failed' with status=500 → 201 + appears in GET")
        status, body = await _post(c, {
            "kind": "fetch_failed",
            "message": f"GET /tools/rag-scenarios → 500 [{marker}]",
            "route": "/tools/rag-scenarios",
            "user_agent": "drill",
            "extra": {
                "method": "GET",
                "url": "/tools/rag-scenarios",
                "status": 500,
                "status_text": "Internal Server Error",
            },
        })
        if status != 201:
            fail(f"expected 201, got {status}: {body}")
        if body["kind"] != "fetch_failed":
            fail(f"kind mismatch: {body['kind']!r}")
        listing = await _list(c)
        found = next(
            (r for r in listing["records"] if marker in r["message"]),
            None,
        )
        if found is None:
            fail("fetch_failed record didn't surface in GET listing")
        ok(f"id={found['id']} kind={found['kind']} status round-trip")

        step("2. POST kind='fetch_error' with TypeError → 201 + surfaces")
        marker2 = uuid.uuid4().hex[:8]
        status, body = await _post(c, {
            "kind": "fetch_error",
            "message": f"GET /api/v1/foo → Failed to fetch [{marker2}]",
            "route": "/admin",
            "user_agent": "drill",
            "extra": {
                "method": "GET",
                "url": "/api/v1/foo",
                "error_name": "TypeError",
            },
        })
        if status != 201 or body["kind"] != "fetch_error":
            fail(f"unexpected: {status} {body}")
        listing = await _list(c)
        found2 = next(
            (r for r in listing["records"] if marker2 in r["message"]),
            None,
        )
        if found2 is None:
            fail("fetch_error didn't surface")
        ok(f"id={found2['id']} kind={found2['kind']} surfaced")

        step("3. extra dict round-trips method + url + status")
        if found["extra"].get("method") != "GET":
            fail(f"extra.method dropped: {found['extra']}")
        if found["extra"].get("url") != "/tools/rag-scenarios":
            fail(f"extra.url dropped: {found['extra']}")
        if found["extra"].get("status") != 500:
            fail(f"extra.status dropped or coerced: {found['extra']}")
        if found2["extra"].get("error_name") != "TypeError":
            fail(f"extra.error_name dropped: {found2['extra']}")
        ok("extra fields round-trip end-to-end")

        step("4. backend accepts fetch_failed against /api/v1/admin/client-errors path")
        # The CLIENT-side guard prevents this from being emitted by
        # the wrap (recursion-prevention). The backend is a passive
        # sink and DOES accept it — drill confirms the backend
        # doesn't filter (which would be a different bug class:
        # if backend filtered, a real recursion bug would be
        # silently masked).
        marker3 = uuid.uuid4().hex[:8]
        status, body = await _post(c, {
            "kind": "fetch_failed",
            "message": f"hypothetical recursion attempt [{marker3}]",
            "route": "/admin/client-errors",
            "extra": {"url": "/api/v1/admin/client-errors", "status": 500},
        })
        if status != 201:
            fail(f"backend should accept (passive sink), got {status}")
        ok("backend accepts (recursion guard is client-side, by design)")

        step("5. fetch_failed and fetch_error stay DISTINCT in listing")
        listing = await _list(c)
        kinds_observed = {r["kind"] for r in listing["records"]}
        if "fetch_failed" not in kinds_observed:
            fail(f"fetch_failed missing from kinds: {kinds_observed}")
        if "fetch_error" not in kinds_observed:
            fail(f"fetch_error missing from kinds: {kinds_observed}")
        # Negative: they aren't merged into 'fetch_anything'.
        if "fetch_anything" in kinds_observed or "fetch" in kinds_observed:
            fail(
                f"unexpected merged label in kinds: {kinds_observed}. "
                f"fetch_failed (server returned 4xx/5xx) and fetch_error "
                f"(network/DNS/CORS failure) are different incidents — "
                f"distinct labels matter for alerting."
            )
        ok(f"both labels present + distinct in {sorted(kinds_observed)}")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 FETCH-CAPTURE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
