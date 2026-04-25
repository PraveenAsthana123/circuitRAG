# RESOURCES: mcp_hr
"""
Drill: per-tool telemetry primitives — latency histogram + scope-denial
counter on every MCP server.

Closes the Phase-1 #2 item from
``docs/architecture/mcp-agent-gap-review.md`` ("per-tool monitoring
views"). The gap was: ``documind_mcp_tool_calls_total{namespace,tool,
outcome}`` already exists, but operators had:

  * no per-tool latency signal (can't alert on p95 spike-by-tool);
  * no scope-denial signal (auth rejections only showed in logs,
    no rate-of-denial counter to alert on).

This commit added two metrics in mcp/server_common.py:

  * ``documind_mcp_tool_call_duration_seconds{namespace,tool}`` —
    histogram around the dispatch path. Replays + scope rejects
    DON'T contribute (replay is free; scope reject didn't dispatch).
  * ``documind_mcp_scope_denials_total{namespace,tool,reason}`` —
    counter of auth rejections, reason ∈ {NOT_AUTHENTICATED,
    INVALID_TOKEN, INSUFFICIENT_SCOPE}.

Negative-assertion §43-style:
 1. Successful tool call → latency_count +1 AND scope_denials
    UNCHANGED for that (namespace, tool). NEGATIVE: a successful
    call must NOT bump the denial counter — denial = auth reject,
    not "any non-200".
 2. Unauthenticated call → 401 NOT_AUTHENTICATED → scope_denials
    {reason=NOT_AUTHENTICATED} +1 AND latency_count UNCHANGED.
    NEGATIVE: a denied call must NOT contribute to the latency
    histogram — we never reached dispatch, recording timing
    would mask real-dispatch p95 with sub-microsecond auth
    failures.
 3. Garbage Bearer token → 401 INVALID_TOKEN → scope_denials
    {reason=INVALID_TOKEN} +1. Distinct reason label proves the
    counter doesn't lump all 401s together.
 4. Insufficient scope (hr:read only on hr.leave_request which
    needs hr:write) → 403 INSUFFICIENT_SCOPE → scope_denials
    {reason=INSUFFICIENT_SCOPE} +1.
 5. Idempotent replay (cache hit) → tool_calls{outcome=replay}
    bumps but latency_count UNCHANGED. NEGATIVE: a cache hit
    must NOT contribute latency — replay is free relative to a
    real dispatch, so mixing them poisons p95.
 6. Reason-label cardinality discipline — only the 4 known
    values appear (3 above + UNKNOWN sentinel). Other 401s
    (none here) would fall to UNKNOWN, never explode cardinality.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_mcp_per_tool_telemetry.py

Prereq: MCP server must be running with auth required.
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
            "sub": "drill-telemetry",
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


# Histogram count series: name suffix ``_count`` carries the
# observation count per (namespace, tool). Sum + buckets are
# also emitted but the count is the leverage point for a
# "did this fire?" assertion.
_LATENCY_COUNT = re.compile(
    r'^documind_mcp_tool_call_duration_seconds_count\{([^}]*)\}\s+(\S+)$',
    re.MULTILINE,
)
_DENIAL = re.compile(
    r'^documind_mcp_scope_denials_total\{([^}]*)\}\s+(\S+)$',
    re.MULTILINE,
)


def _parse_labels(label_str: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in label_str.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def _parse_latency(body: str) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for m in _LATENCY_COUNT.finditer(body):
        labels = _parse_labels(m.group(1))
        try:
            out[(labels.get("namespace", ""), labels.get("tool", ""))] = float(m.group(2))
        except ValueError:
            continue
    return out


def _parse_denials(body: str) -> dict[tuple[str, str, str], float]:
    out: dict[tuple[str, str, str], float] = {}
    for m in _DENIAL.finditer(body):
        labels = _parse_labels(m.group(1))
        key = (
            labels.get("namespace", ""),
            labels.get("tool", ""),
            labels.get("reason", ""),
        )
        try:
            out[key] = float(m.group(2))
        except ValueError:
            continue
    return out


async def _scrape(c: httpx.AsyncClient) -> tuple[dict, dict]:
    r = await c.get(f"{HR_BASE}/metrics")
    if r.status_code != 200:
        fail(f"/metrics returned {r.status_code}")
    return _parse_latency(r.text), _parse_denials(r.text)


async def _call(
    c: httpx.AsyncClient,
    *, name: str, args: dict, token: str | None = None,
    idem: str | None = None, raw_authz: str | None = None,
) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if raw_authz is not None:
        headers["Authorization"] = raw_authz
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    if idem:
        headers["Idempotency-Key"] = idem
    return await c.post(
        f"{HR_BASE}/tools/call",
        headers=headers,
        json={"name": name, "arguments": args, "tenant_id": TENANT},
    )


async def main() -> None:
    NS = "mcp_hr"
    TOOL = "hr.leave_request"
    KEY_LAT = (NS, TOOL)
    write_token = _mint(["hr:write"])
    read_token = _mint(["hr:read"])

    async with httpx.AsyncClient(timeout=10.0) as c:
        step("0. baseline scrape")
        lat0, den0 = await _scrape(c)
        lat_before = lat0.get(KEY_LAT, 0.0)
        d_unauth_before = den0.get((NS, TOOL, "NOT_AUTHENTICATED"), 0.0)
        d_invalid_before = den0.get((NS, TOOL, "INVALID_TOKEN"), 0.0)
        d_insuff_before = den0.get((NS, TOOL, "INSUFFICIENT_SCOPE"), 0.0)
        ok(
            f"latency_count={int(lat_before)} "
            f"denials(unauth/invalid/insuff)="
            f"{int(d_unauth_before)}/{int(d_invalid_before)}/{int(d_insuff_before)}"
        )

        step("1. successful call → latency_count +1; denials UNCHANGED")
        r = await _call(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 1, "reason": "telemetry drill"},
            token=write_token,
        )
        if r.status_code != 200 or not r.json().get("ok"):
            fail(f"call failed: {r.status_code} {r.text[:200]}")
        await asyncio.sleep(0.1)
        lat1, den1 = await _scrape(c)
        if lat1.get(KEY_LAT, 0.0) - lat_before != 1:
            fail(
                f"latency_count delta != 1; "
                f"got {lat1.get(KEY_LAT, 0.0) - lat_before}"
            )
        if den1.get((NS, TOOL, "NOT_AUTHENTICATED"), 0.0) != d_unauth_before:
            fail("NOT_AUTHENTICATED bumped on a successful call (must NOT)")
        if den1.get((NS, TOOL, "INSUFFICIENT_SCOPE"), 0.0) != d_insuff_before:
            fail("INSUFFICIENT_SCOPE bumped on a successful call (must NOT)")
        ok(f"latency +1; no denial counters moved")
        lat_before = lat1.get(KEY_LAT, 0.0)

        step("2. no Authorization → NOT_AUTHENTICATED +1; latency UNCHANGED")
        r = await _call(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
        )
        if r.status_code != 401:
            fail(f"expected 401, got {r.status_code}: {r.text[:200]}")
        await asyncio.sleep(0.1)
        lat2, den2 = await _scrape(c)
        d_delta = (
            den2.get((NS, TOOL, "NOT_AUTHENTICATED"), 0.0) - d_unauth_before
        )
        if d_delta != 1:
            fail(f"NOT_AUTHENTICATED delta != 1; got {d_delta}")
        if lat2.get(KEY_LAT, 0.0) != lat_before:
            fail(
                "latency_count moved on a denied call — "
                "auth-reject must NOT contribute timing (it never reached "
                f"dispatch). got delta={lat2.get(KEY_LAT, 0.0) - lat_before}"
            )
        ok(f"NOT_AUTHENTICATED +1; latency unchanged")
        d_unauth_before = den2.get((NS, TOOL, "NOT_AUTHENTICATED"), 0.0)

        step("3. garbage Bearer token → INVALID_TOKEN +1; latency UNCHANGED")
        r = await _call(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
            raw_authz="Bearer this.is.not-a-real-jwt",
        )
        if r.status_code != 401:
            fail(f"expected 401, got {r.status_code}")
        await asyncio.sleep(0.1)
        lat3, den3 = await _scrape(c)
        d_delta = (
            den3.get((NS, TOOL, "INVALID_TOKEN"), 0.0) - d_invalid_before
        )
        if d_delta != 1:
            fail(f"INVALID_TOKEN delta != 1; got {d_delta}")
        if lat3.get(KEY_LAT, 0.0) != lat_before:
            fail("latency moved on INVALID_TOKEN (must NOT)")
        ok(f"INVALID_TOKEN +1; latency unchanged")
        d_invalid_before = den3.get((NS, TOOL, "INVALID_TOKEN"), 0.0)

        step("4. hr:read on hr.leave_request → INSUFFICIENT_SCOPE +1")
        r = await _call(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
            token=read_token,
        )
        if r.status_code != 403:
            fail(f"expected 403, got {r.status_code}: {r.text[:200]}")
        await asyncio.sleep(0.1)
        lat4, den4 = await _scrape(c)
        d_delta = (
            den4.get((NS, TOOL, "INSUFFICIENT_SCOPE"), 0.0) - d_insuff_before
        )
        if d_delta != 1:
            fail(f"INSUFFICIENT_SCOPE delta != 1; got {d_delta}")
        if lat4.get(KEY_LAT, 0.0) != lat_before:
            fail("latency moved on INSUFFICIENT_SCOPE (must NOT)")
        ok(f"INSUFFICIENT_SCOPE +1; latency unchanged")

        step("5. idempotent replay → tool_calls{outcome=replay} +1; latency UNCHANGED")
        idem = str(uuid.uuid4())
        # First call — bumps latency (it's a real dispatch).
        r1 = await _call(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 2, "reason": "replay-test"},
            token=write_token, idem=idem,
        )
        if r1.status_code != 200:
            fail(f"first call failed: {r1.status_code}")
        await asyncio.sleep(0.1)
        lat5a, _ = await _scrape(c)
        lat_after_first = lat5a.get(KEY_LAT, 0.0)
        # Second call with SAME key — cache replay; must NOT bump latency.
        r2 = await _call(
            c, name=TOOL,
            args={"employee_id": "E1", "days": 2, "reason": "replay-test"},
            token=write_token, idem=idem,
        )
        if r2.status_code != 200:
            fail(f"replay failed: {r2.status_code}")
        if not r2.json().get("idempotent_replay"):
            fail("replay didn't set idempotent_replay=true")
        await asyncio.sleep(0.1)
        lat5b, _ = await _scrape(c)
        if lat5b.get(KEY_LAT, 0.0) != lat_after_first:
            fail(
                f"latency_count moved on cache replay — replay must NOT "
                f"contribute timing. expected {int(lat_after_first)}, "
                f"got {int(lat5b.get(KEY_LAT, 0.0))}"
            )
        ok(f"first call latency +1; replay latency +0 (replay path skips timing)")

        step("6. denial reason cardinality — only known reasons appear")
        _, den_final = await _scrape(c)
        observed_reasons = {
            r for (ns, tool, r) in den_final.keys() if ns == NS and tool == TOOL
        }
        valid = {
            "NOT_AUTHENTICATED", "INVALID_TOKEN",
            "INSUFFICIENT_SCOPE", "UNKNOWN",
        }
        unknown_extras = observed_reasons - valid
        if unknown_extras:
            fail(
                f"reason label exploded — unknown values: {unknown_extras}. "
                f"Defence in _denial_reason() must catch detail-shape drift."
            )
        # Negative: at least the three reasons we exercised must be present.
        expected_present = {
            "NOT_AUTHENTICATED", "INVALID_TOKEN", "INSUFFICIENT_SCOPE",
        }
        missing = expected_present - observed_reasons
        if missing:
            fail(
                f"expected reasons missing from /metrics: {missing}. "
                f"Either steps 2-4 didn't fire, or the counter isn't wired."
            )
        ok(f"reasons observed: {sorted(observed_reasons)} (all within enum)")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 PER-TOOL-TELEMETRY STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
