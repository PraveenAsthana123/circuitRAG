# RESOURCES: none
"""
Drill: JWT verifier rejects malformed-but-decodable tokens early.

A token signed with the right key but carrying a malformed claim
(sub as int, roles as string instead of list, tenant_id="alice")
used to pass ``pyjwt.decode`` and propagate into request.state. Then
something downstream — RLS cast in audit_log INSERT, scope check on
require_roles, rate limiter keyed by tenant — would fail in a way
that didn't tell the operator the issuer was emitting bad shapes.

This drill mints a valid token for each malformed-claim case, runs
it through ``JWTVerifier.verify``, and asserts InvalidTokenError
with a useful message. Plus a positive control: a well-formed token
passes.

Each step is a negative assertion: "token X SHALL NOT be accepted."

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_jwt_identity_contract.py
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from documind_core.auth import JWTVerifier  # noqa: E402

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"
PRIV = (REPO / "scripts" / "dev-keys" / "jwt-private.pem").read_bytes()
PUB_PATH = str(REPO / "scripts" / "dev-keys" / "jwt-public.pem")
ISS, AUD = "documind-local", "documind-services"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _mint(**overrides) -> str:
    """Mint a baseline token, override any claim. Used to build malformed cases."""
    now = int(time.time())
    claims: dict = {
        "iss": ISS,
        "aud": AUD,
        "sub": "alice@example.com",
        "tenant_id": "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
        "roles": ["hr:read"],
        "kind": "access",
        "iat": now, "nbf": now, "exp": now + 900,
        "jti": uuid.uuid4().hex,
    }
    # Overrides MAY use a sentinel ``__delete__`` to remove a key entirely.
    for k, v in overrides.items():
        if v == "__delete__":
            claims.pop(k, None)
        else:
            claims[k] = v
    return pyjwt.encode(claims, PRIV, algorithm="RS256")


def _expect_reject(verifier: JWTVerifier, token: str, must_mention: str) -> None:
    try:
        verifier.verify(token)
    except pyjwt.InvalidTokenError as exc:
        if must_mention.lower() not in str(exc).lower():
            fail(
                f"rejected, but error doesn't mention {must_mention!r}: {exc}"
            )
        return
    fail(f"token was accepted but should have been rejected ({must_mention})")


def main() -> None:
    v = JWTVerifier(public_key_path=PUB_PATH, issuer=ISS, audience=AUD)

    step("1. Positive control — a well-formed token passes")
    claims = v.verify(_mint())
    if claims.get("sub") != "alice@example.com":
        fail(f"baseline accepted but claims wrong: {claims}")
    if claims.get("roles") != ["hr:read"]:
        fail(f"baseline roles unexpected: {claims['roles']!r}")
    ok("baseline token verified — sub + tenant_id + roles round-trip cleanly")

    step("2. sub claim is rejected when not a non-empty string")
    # Integer sub
    _expect_reject(v, _mint(sub=42), "sub")
    # Empty string sub
    _expect_reject(v, _mint(sub=""), "sub")
    # Missing sub entirely
    _expect_reject(v, _mint(sub="__delete__"), "sub")
    # Sub that's a list
    _expect_reject(v, _mint(sub=["alice"]), "sub")
    ok("sub: int / empty / missing / list all rejected")

    step("3. tenant_id rejected when not a UUID")
    _expect_reject(v, _mint(tenant_id="alice"), "tenant_id")
    _expect_reject(v, _mint(tenant_id="not-a-uuid"), "tenant_id")
    _expect_reject(v, _mint(tenant_id=42), "tenant_id")
    # Empty string tenant_id is allowed (means "unspecified") — verify that:
    claims = v.verify(_mint(tenant_id=""))
    if claims.get("tenant_id") != "":
        fail("empty tenant_id should be allowed (treated as unset)")
    # Missing tenant_id entirely is allowed (e.g. service tokens):
    claims = v.verify(_mint(tenant_id="__delete__"))
    if "tenant_id" in claims:
        fail("missing tenant_id should not get auto-added")
    ok("tenant_id: non-UUID strings + ints rejected; empty / absent allowed")

    step("4. roles rejected when shape is wrong")
    # roles as string (very common bug — ``"hr:write"`` instead of ``["hr:write"]``)
    _expect_reject(v, _mint(roles="hr:write"), "roles")
    # roles as dict
    _expect_reject(v, _mint(roles={"hr": "write"}), "roles")
    # role string with bad shape
    _expect_reject(v, _mint(roles=["NOT_A_ROLE"]), "shape")
    _expect_reject(v, _mint(roles=["hr write"]), "shape")  # space, not :
    # Empty role string
    _expect_reject(v, _mint(roles=[""]), "role")
    # Too many roles
    _expect_reject(v, _mint(roles=[f"a:b{i}" for i in range(33)]), "exceeds")
    # Missing roles is allowed (zero scopes):
    claims = v.verify(_mint(roles="__delete__"))
    if claims.get("roles") not in (None, []):
        # Either is fine — depends on whether pyjwt strips missing keys.
        pass
    ok("roles: string / dict / bad shape / empty / >cap rejected; missing allowed")

    step("5. kind enforced explicitly (defence-in-depth on top of expected_kind)")
    _expect_reject(v, _mint(kind="__delete__"), "kind")
    _expect_reject(v, _mint(kind="refresh"), "kind")  # refresh ≠ expected access
    _expect_reject(v, _mint(kind=42), "kind")
    _expect_reject(v, _mint(kind="garbage"), "kind")
    ok("kind: missing / wrong / non-string all rejected")

    step("6. Forged signature still 401 (regression check on standard pyjwt path)")
    # This existed before — proves the new validator didn't bypass signature.
    valid = _mint()
    forged = valid[:-10] + "AAAAAAAAAA"
    try:
        v.verify(forged)
    except pyjwt.InvalidTokenError:
        ok("forged-signature token rejected as before (validator didn't break sig check)")
    else:
        fail("forged signature was accepted — auth is BROKEN, halt deploy")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 IDENTITY-CONTRACT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
