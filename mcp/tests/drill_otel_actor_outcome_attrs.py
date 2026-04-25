# RESOURCES: mcp_hr
"""
Drill: handle_tool_call sets actor identity + outcome on its OTel
span (and emits a matching log line) so operators can filter Jaeger
by actor + outcome without reading server logs.

Closes one row of the OTel tool-level coverage scorecard
(docs/architecture/otel-tool-level-coverage-scorecard-and-tracker.md):
"MCP servers — add richer tool-dispatch spans and clearer outcome
attributes." This commit lifts the score for that row.

Span attributes added in handle_tool_call:
  * mcp.actor.id          — claims['sub'] (set when auth on)
  * mcp.actor.email       — claims['email'] (set when present)
  * mcp.outcome           — ok | error | replay | conflict |
                            in_progress | http_<status>
  * mcp.idempotent_replay — already existed; preserved

Verification strategy: span-level OTel attributes can't be cheaply
asserted from the drill side (they ride to OTLP). The drill verifies
the equivalent `<service>_actor_identified` log line that's emitted
in the same code path with the same data. If the log line carries
the actor info, the span attribute does too — they share one source
of truth (the validated `claims` dict).

Negative-assertion §43-style:
 1. Authenticated call → access log carries actor_identified line
    with sub + email matching the token. NEGATIVE: a regression
    that lost the claim-capture would emit no such line.
 2. Unauthenticated 401 → NO actor_identified line for that
    correlation_id. NEGATIVE: emitting an actor line for a 401
    would be a security-shaped bug (no token = no actor; logging
    the absence creates phantom audit trails).
 3. Insufficient-scope 403 → NO actor_identified line for that
    correlation_id either, because the function raises BEFORE
    reaching the log statement. NEGATIVE: this is the right
    behavior — a denied call is not the same as an executed one,
    and operators need to be able to count "actor-identified"
    log lines as the count of REAL dispatches.
 4. Successful call's correlation_id appears EXACTLY ONCE in the
    actor log lines. NEGATIVE: duplication would mean the
    enforce_scope wrapper got called twice, breaking the
    "one call, one identification" invariant.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_otel_actor_outcome_attrs.py
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
LOG_PATH = Path(os.getenv("MCP_HR_LOG", "/tmp/mcp_hr.log"))

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _mint(*, sub: str, email: str, roles: list[str]) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": "documind-local",
            "aud": "documind-services",
            "sub": sub,
            "email": email,
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


def _read_log_tail(lines: int = 200) -> str:
    if not LOG_PATH.exists():
        return ""
    with LOG_PATH.open("r", errors="replace") as f:
        return "".join(f.readlines()[-lines:])


def _count_actor_lines(log: str, *, corr: str) -> list[str]:
    """Return all `<service>_actor_identified ... corr=<corr>` lines."""
    pattern = re.compile(
        rf"\b\w+_actor_identified [^\n]*corr={re.escape(corr)}\b",
    )
    return pattern.findall(log)


async def _call(
    c: httpx.AsyncClient,
    *, name: str, args: dict, token: str | None = None,
    raw_authz: str | None = None, corr: str,
) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        # Use X-Correlation-ID via the request body's correlation_id.
        # The MCP server prefers req.correlation_id; both work.
    }
    if raw_authz is not None:
        headers["Authorization"] = raw_authz
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    return await c.post(
        f"{HR_BASE}/tools/call",
        headers=headers,
        json={
            "name": name,
            "arguments": args,
            "tenant_id": TENANT,
            "correlation_id": corr,
        },
    )


async def main() -> None:
    SUB = "drill-otel-alice"
    EMAIL = "alice@otel-drill.local"
    write_token = _mint(sub=SUB, email=EMAIL, roles=["hr:write"])
    read_token = _mint(sub=SUB, email=EMAIL, roles=["hr:read"])

    cid_ok = str(uuid.uuid4())
    cid_unauth = str(uuid.uuid4())
    cid_insuff = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=10.0) as c:
        step("0. sanity — log file is readable")
        if not LOG_PATH.exists():
            fail(f"log file missing: {LOG_PATH}")
        ok(f"log file present at {LOG_PATH}")

        step("1. authenticated call → actor_identified line with sub + email")
        r = await _call(
            c, name="hr.leave_request",
            args={"employee_id": "E1", "days": 1, "reason": "otel drill"},
            token=write_token, corr=cid_ok,
        )
        if r.status_code != 200 or not r.json().get("ok"):
            fail(f"call failed: {r.status_code} {r.text[:200]}")
        # Brief sleep so the log line is flushed.
        await asyncio.sleep(0.2)
        log = _read_log_tail()
        actor_lines = _count_actor_lines(log, corr=cid_ok)
        if len(actor_lines) != 1:
            fail(
                f"expected exactly 1 actor_identified line for cid={cid_ok}, "
                f"got {len(actor_lines)}. Either the line wasn't emitted "
                f"(claim capture broken) or the call was wrapped twice."
            )
        line = actor_lines[0]
        if SUB not in line:
            fail(f"actor_identified line missing sub={SUB}: {line}")
        if EMAIL not in line:
            fail(f"actor_identified line missing email={EMAIL}: {line}")
        ok(f"actor_identified line: {line}")

        step("2. unauthenticated 401 → NO actor_identified line for that cid")
        r = await _call(
            c, name="hr.leave_request",
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
            corr=cid_unauth,
        )
        if r.status_code != 401:
            fail(f"expected 401, got {r.status_code}")
        await asyncio.sleep(0.2)
        log = _read_log_tail()
        actor_lines = _count_actor_lines(log, corr=cid_unauth)
        if actor_lines:
            fail(
                f"401 NOT_AUTHENTICATED leaked an actor_identified "
                f"line: {actor_lines}. No token means no actor; "
                f"logging an actor for a denied call would create "
                f"a phantom audit trail."
            )
        ok(f"no actor_identified for unauthenticated 401 (correct)")

        step("3. insufficient-scope 403 → NO actor_identified line either")
        r = await _call(
            c, name="hr.leave_request",
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
            token=read_token, corr=cid_insuff,
        )
        if r.status_code != 403:
            fail(f"expected 403, got {r.status_code}")
        await asyncio.sleep(0.2)
        log = _read_log_tail()
        actor_lines = _count_actor_lines(log, corr=cid_insuff)
        if actor_lines:
            fail(
                f"403 INSUFFICIENT_SCOPE leaked actor_identified: "
                f"{actor_lines}. The line is emitted only AFTER "
                f"successful scope intersection — a denied call should "
                f"not appear in the actor-identified count, since that "
                f"count is operators' proxy for 'real dispatches'."
            )
        ok(f"no actor_identified for 403 INSUFFICIENT_SCOPE (correct)")

        step("4. successful cid_ok appears EXACTLY ONCE across full log")
        log = _read_log_tail(lines=1000)
        all_for_cid = _count_actor_lines(log, corr=cid_ok)
        if len(all_for_cid) != 1:
            fail(
                f"cid_ok appeared {len(all_for_cid)} times (expected 1). "
                f"Duplication would mean enforce_scope ran twice — "
                f"breaks 'one call, one identification' invariant."
            )
        ok(f"cid_ok identified exactly once across full tail")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 OTEL-ACTOR-OUTCOME-ATTR STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
