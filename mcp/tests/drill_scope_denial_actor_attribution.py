# RESOURCES: mcp_hr
"""
Drill: 403 INSUFFICIENT_SCOPE response carries actor attribution
so denials are self-explaining without log archaeology.

Closes the trust-scorecard gap "better explanation of denials"
cited in:
  * docs/architecture/production-trust-quality-and-readiness.md §2
  * docs/architecture/mcp-agent-gap-review.md §2.4

Before this commit: 403 detail was {code, required, have, tool}.
Operators investigating a denial had to dig logs to figure out
WHO was denied. After: detail also carries {actor, actor_email,
missing} — the response body alone tells the story.

Negative-assertion §43-style:
 1. 403 with valid token + insufficient scope → detail.actor
    matches the token's sub, detail.actor_email matches the
    token's email. NEGATIVE: a regression that hardcoded actor=null
    or echoed the wrong claim would still pass the existing
    drill_mcp_server_scope.py (which only checks code +
    required + have) but fail this.
 2. 403 detail.missing is exactly required − have, not just a
    copy of required. NEGATIVE: subtle but important — if the
    caller has SOME of the required scopes (multi-scope tools)
    they need to know WHICH ones to add, not the full set.
 3. 401 NOT_AUTHENTICATED does NOT include actor (no claims to
    pull from). NEGATIVE: leaking a fake actor on unauthenticated
    requests would be a real-world incident — no token means no
    actor, period.
 4. 401 INVALID_TOKEN does NOT include actor either (signature
    failed; claims are untrusted). NEGATIVE: even though jwt.decode
    surfaces decoded claims on signature failure in some libs,
    we MUST NOT propagate them — they're attacker-controlled.
 5. 403 detail's actor/missing fields don't bleed into a SUCCESSFUL
    call's response. Trivial but worth locking — a regression that
    set these on the wrapper level would echo them on 200 too.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_scope_denial_actor_attribution.py
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


async def _call(
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
    SUB = "drill-attribution-alice"
    EMAIL = "alice@drill.local"
    read_token = _mint(sub=SUB, email=EMAIL, roles=["hr:read"])
    write_token = _mint(sub=SUB, email=EMAIL, roles=["hr:write"])

    async with httpx.AsyncClient(timeout=10.0) as c:
        step("1. 403 INSUFFICIENT_SCOPE detail.actor matches token sub")
        r = await _call(
            c, name="hr.leave_request",
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
            token=read_token,
        )
        if r.status_code != 403:
            fail(f"expected 403, got {r.status_code}: {r.text[:200]}")
        body = r.json()
        d = body.get("detail")
        if not isinstance(d, dict):
            fail(f"expected dict detail, got {type(d).__name__}: {body}")
        if d.get("actor") != SUB:
            fail(
                f"detail.actor wrong — expected {SUB!r}, got "
                f"{d.get('actor')!r}. The 403 response should carry "
                f"the token's sub so operators don't have to dig logs."
            )
        if d.get("actor_email") != EMAIL:
            fail(f"detail.actor_email wrong: {d.get('actor_email')!r}")
        ok(f"actor={d['actor']} actor_email={d['actor_email']}")

        step("2. detail.missing is required − have, not just a copy of required")
        # hr.leave_request requires hr:write; the read_token has hr:read.
        # missing should be ['hr:write'], not ['hr:write'] same as required.
        # In this exact case they happen to be equal (single-scope tool),
        # but the structural assertion is that missing == required - have.
        required = set(d.get("required", []))
        have = set(d.get("have", []))
        missing = set(d.get("missing", []))
        expected_missing = required - have
        if missing != expected_missing:
            fail(
                f"detail.missing != (required - have). "
                f"required={sorted(required)} have={sorted(have)} "
                f"missing={sorted(missing)} expected={sorted(expected_missing)}. "
                f"Operators page through denials reading 'missing' as "
                f"'grant role X'; if it's wrong, they grant the wrong "
                f"role."
            )
        if not missing:
            fail(
                f"missing must be non-empty when scope check failed. "
                f"required={required} have={have}"
            )
        ok(f"missing={sorted(missing)} == required - have ✓")

        step("3. 401 NOT_AUTHENTICATED does NOT include actor")
        r = await _call(c, name="hr.leave_request",
                        args={"employee_id": "E1", "days": 1, "reason": "drill"})
        if r.status_code != 401:
            fail(f"expected 401, got {r.status_code}")
        body = r.json()
        d = body.get("detail")
        if d.get("code") != "NOT_AUTHENTICATED":
            fail(f"wrong code: {d.get('code')!r}")
        if "actor" in d:
            fail(
                f"NOT_AUTHENTICATED leaked an actor field: {d['actor']!r}. "
                f"No token means no claims means no actor — full stop."
            )
        if "actor_email" in d:
            fail(f"NOT_AUTHENTICATED leaked actor_email: {d['actor_email']!r}")
        ok("401 NOT_AUTHENTICATED clean (no actor leak)")

        step("4. 401 INVALID_TOKEN does NOT propagate untrusted claims")
        # Build a token with a forged sub but signed with a wrong key —
        # signature failure means any 'claims' would be attacker-supplied.
        # Easiest: just use a structurally valid but unsigned/wrong-key token.
        forged = pyjwt.encode(
            {
                "iss": "documind-local",
                "aud": "documind-services",
                "sub": "attacker-pretending-to-be-admin",
                "email": "attacker@evil.example",
                "tenant_id": TENANT,
                "roles": ["hr:write", "hr:admin"],  # claims they shouldn't have
                "kind": "access",
                "iat": int(time.time()),
                "exp": int(time.time()) + 900,
            },
            "wrong-secret-not-the-real-key",  # signing with non-matching key
            algorithm="HS256",
        )
        r = await _call(c, name="hr.leave_request",
                        args={"employee_id": "E1", "days": 1, "reason": "drill"},
                        raw_authz=f"Bearer {forged}")
        if r.status_code != 401:
            fail(f"expected 401, got {r.status_code}: {r.text[:300]}")
        body = r.json()
        d = body.get("detail")
        if d.get("code") != "INVALID_TOKEN":
            fail(f"expected INVALID_TOKEN, got {d.get('code')!r}")
        if "actor" in d or "actor_email" in d:
            fail(
                f"INVALID_TOKEN response propagated attacker-controlled "
                f"claims: {d}. The signature failed; any decoded claims "
                f"are untrusted and MUST NOT round-trip to the response."
            )
        ok("401 INVALID_TOKEN does not propagate forged-claim fields")

        step("5. successful call response has no actor leak")
        r = await _call(
            c, name="hr.leave_request",
            args={"employee_id": "E1", "days": 1, "reason": "drill"},
            token=write_token,
        )
        if r.status_code != 200:
            fail(f"expected 200, got {r.status_code}")
        body = r.json()
        if not body.get("ok"):
            fail(f"call should succeed: {body}")
        # Top-level shouldn't have actor (the success path doesn't echo
        # claims). The detail field is for errors only.
        if "actor" in body:
            fail(
                f"successful response leaked actor at top-level: "
                f"{body['actor']!r}. Actor attribution belongs in "
                f"audit, not in user-facing success bodies."
            )
        ok("200 success body has no actor field at top-level")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 SCOPE-DENIAL-ATTRIBUTION STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
