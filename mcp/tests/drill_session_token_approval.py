# RESOURCES: readonly
"""
Drill: session-token issuance + validation + revocation.

Per CLAUDE.md §38 (governance), §42 (operational autonomy boundary),
§43 (drill discipline), §47 (architecture: auth at boundary),
§52 row 4 (operator API gap), §55.3 (outcome-based contract).

The session-token surface adds operator-attribution to the existing
command-approval orchestrator. Tokens are HMAC-SHA256 signed; the
secret comes from DOCUMIND_SESSION_TOKEN_SECRET. The drill locks
the security invariants AND the backwards-compat (anonymous flow
when no token is presented).

Locks (positive):
  L1. issue() returns a 3-part token + a SessionToken dataclass
  L2. validate() returns the SessionToken when fresh + signed correctly
  L3. orchestrator.evaluate(cmd, session_token=valid) tags
      EvaluatedCommand.operator_id correctly
  L4. orchestrator.evaluate(cmd) without token → anonymous status
      (backwards-compat path NEVER changed)

Locks (negative — ≥3 per §43, this drill ships 6):
  N1. Tampered token (any byte changed in payload or signature) →
      validate() returns None; orchestrator status='invalid'.
  N2. Expired token → validate() returns None; orchestrator
      status='expired' (distinct from 'invalid' for audit clarity).
  N3. Revoked token → validate() returns None; orchestrator
      status='revoked' (revocation persists across process restart
      via the JSON file).
  N4. Missing DOCUMIND_SESSION_TOKEN_SECRET → issue() raises
      TokenSecretMissing; validate() returns None (NEVER falls back
      to a default secret — that would let attackers forge tokens
      against any deployment that forgot to set the env var).
  N5. Token presented to an orchestrator with NO token_store →
      status='invalid' (operator misconfig surfaces, not silently
      coerced to anonymous).
  N6. Token signature comparison is constant-time (uses
      hmac.compare_digest, not == operator) — prevents timing
      attacks. Drill greps source for compare_digest usage.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from approval_agent.batcher import ApprovalBatcher  # noqa: E402
from approval_agent.command_orchestrator import (  # noqa: E402
    CommandApprovalOrchestrator,
)
from approval_agent.session_cache import SessionCache  # noqa: E402
from approval_agent.session_token import (  # noqa: E402
    SECRET_ENV,
    SessionTokenStore,
    TokenSecretMissing,
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def _make_orch(td: Path, *, with_token_store: bool = True) -> CommandApprovalOrchestrator:
    cache = SessionCache(path=td / "cache.json", ttl_seconds=1800)
    batcher = ApprovalBatcher(path=td / "batch.jsonl", flush_interval_seconds=900)
    store = (
        SessionTokenStore(revocation_path=td / "revocations.json")
        if with_token_store else None
    )
    return CommandApprovalOrchestrator(
        cache=cache,
        batcher=batcher,
        token_store=store,
        audit_path=td / "audit.jsonl",
    )


def main() -> int:
    # Use a deterministic test secret throughout; restore at end.
    orig_secret = os.environ.get(SECRET_ENV)
    test_secret = "test-secret-32-bytes-or-more-aaaaaaaaaaaaaaaa"
    os.environ[SECRET_ENV] = test_secret

    try:
        # ===============================================================
        # Step 1 — module surface + secret env var contract
        # ===============================================================
        step("1. session_token module exposes issue/validate/revoke + uses env secret")
        from approval_agent import session_token as sts
        for name in ("SessionToken", "SessionTokenStore", "TokenSecretMissing",
                     "SECRET_ENV", "DEFAULT_TTL_SECONDS"):
            if not hasattr(sts, name):
                fail(f"missing public name: {name}")
        if sts.SECRET_ENV != "DOCUMIND_SESSION_TOKEN_SECRET":
            fail(f"unexpected env var name: {sts.SECRET_ENV}")
        ok(f"module exports the 5 documented public names; env={sts.SECRET_ENV}")

        # ===============================================================
        # Step 2 — issue() returns a 3-part token + SessionToken
        # ===============================================================
        step("2. issue() returns encoded 3-part token + dataclass")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            store = SessionTokenStore(revocation_path=td / "rev.json")
            encoded, st = store.issue(operator_id="alice", ttl_seconds=300)
            if encoded.count(".") != 2:
                fail(f"token must be 3-part dotted, got {encoded.count('.') + 1}")
            if st.operator_id != "alice":
                fail(f"operator_id roundtrip failed: {st.operator_id}")
            if st.is_expired():
                fail("freshly-issued token already expired")
            ok(f"3-part token issued for alice; expires_in={int(st.expires_at - time.time())}s")

        # ===============================================================
        # Step 3 — validate() round-trip works on fresh token
        # ===============================================================
        step("3. validate() returns the token on a fresh issuance")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            store = SessionTokenStore(revocation_path=td / "rev.json")
            encoded, _ = store.issue(operator_id="bob", ttl_seconds=300)
            v = store.validate(encoded)
            if v is None:
                fail("fresh token validation returned None")
            if v.operator_id != "bob":
                fail(f"validated operator_id wrong: {v.operator_id}")
        ok("fresh token round-trips cleanly through validate()")

        # ===============================================================
        # Step 4 — orchestrator stamps operator_id on valid token
        # ===============================================================
        step("4. orchestrator.evaluate(cmd, token=valid) → operator_id stamped")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            orch = _make_orch(td)
            encoded, _ = orch.token_store.issue(operator_id="carol", ttl_seconds=300)
            r = orch.evaluate("docker compose ps", session_token=encoded)
            if r.operator_id != "carol":
                fail(f"operator_id not stamped: {r.operator_id}")
            if r.token_status != "valid":
                fail(f"expected status=valid, got {r.token_status}")
        ok("valid token → operator_id='carol' on AUTO_APPROVE row")

        # ===============================================================
        # Step 5 — anonymous backwards-compat: no token → status=anonymous
        # ===============================================================
        step("5. evaluate() WITHOUT token → status='anonymous' (backwards-compat)")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            orch = _make_orch(td)
            r = orch.evaluate("git status")
            if r.token_status != "anonymous":
                fail(f"no-token path should be anonymous, got {r.token_status}")
            if r.operator_id is not None:
                fail(f"operator_id should be None when anonymous, got {r.operator_id!r}")
        ok("no-token path → anonymous; operator_id=None; backwards-compat preserved")

        # ===============================================================
        # Step 6 — NEGATIVE: tampered signature → status='invalid'
        # ===============================================================
        step("6. NEGATIVE: tampered token signature → status='invalid'")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            orch = _make_orch(td)
            encoded, _ = orch.token_store.issue(operator_id="dave")
            tid, payload, sig = encoded.split(".")
            tampered = f"{tid}.{payload}.{sig[:-2]}AA"  # flip last 2 chars
            r = orch.evaluate("git status", session_token=tampered)
            if r.token_status != "invalid":
                fail(f"tampered token should be invalid, got {r.token_status}")
            if r.operator_id is not None:
                fail(f"tampered token must not stamp operator_id: {r.operator_id!r}")

            # Also tamper the payload (adds 'admin: true' equivalent)
            tampered_payload = payload[:-4] + "AAAA"
            tampered2 = f"{tid}.{tampered_payload}.{sig}"
            r2 = orch.evaluate("git status", session_token=tampered2)
            if r2.token_status != "invalid":
                fail(f"payload-tampered token should be invalid, got {r2.token_status}")
        ok("signature + payload tampering both → status='invalid'; no operator_id leak")

        # ===============================================================
        # Step 7 — NEGATIVE: expired token → status='expired'
        # ===============================================================
        step("7. NEGATIVE: expired token → status='expired' (distinct from invalid)")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            orch = _make_orch(td)
            # Issue with 0-second TTL
            encoded, _ = orch.token_store.issue(operator_id="eve", ttl_seconds=0)
            time.sleep(0.01)
            r = orch.evaluate("git status", session_token=encoded)
            if r.token_status != "expired":
                fail(f"expired token should be 'expired', got {r.token_status}")
            if r.operator_id is not None:
                fail(f"expired token must not stamp operator_id: {r.operator_id!r}")
        ok("expired token → status='expired' (audit-distinguishable from invalid)")

        # ===============================================================
        # Step 8 — NEGATIVE: revoked token → status='revoked' (persists)
        # ===============================================================
        step("8. NEGATIVE: revoked token → status='revoked'; persists across reload")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            orch = _make_orch(td)
            encoded, st = orch.token_store.issue(operator_id="frank", ttl_seconds=3600)
            # Pre-revoke verification: still valid
            r1 = orch.evaluate("git status", session_token=encoded)
            if r1.token_status != "valid":
                fail(f"pre-revoke status should be valid, got {r1.token_status}")
            # Revoke
            if not orch.token_store.revoke(st.token_id):
                fail("revoke() returned False on first call")
            # Post-revoke: status = revoked
            r2 = orch.evaluate("git status", session_token=encoded)
            if r2.token_status != "revoked":
                fail(f"post-revoke status should be 'revoked', got {r2.token_status}")
            # Persistence: fresh store reading the same revocation file
            store2 = SessionTokenStore(revocation_path=td / "revocations.json")
            if not store2.is_revoked(st.token_id):
                fail("revocation didn't persist across store reload")
        ok("revocation enforced + persisted across process restart")

        # ===============================================================
        # Step 9 — NEGATIVE: missing secret → issue() raises; validate() None
        # ===============================================================
        step("9. NEGATIVE: missing DOCUMIND_SESSION_TOKEN_SECRET → no fallback")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            store = SessionTokenStore(revocation_path=td / "rev.json")
            # Save current secret, drop env
            saved = os.environ.pop(SECRET_ENV, None)
            try:
                try:
                    store.issue(operator_id="grace")
                    fail("issue() must raise TokenSecretMissing without env secret")
                except TokenSecretMissing:
                    pass
                # validate() must return None silently (NOT raise)
                if store.validate("anything.at.all") is not None:
                    fail("validate() must return None when secret missing")
            finally:
                if saved is not None:
                    os.environ[SECRET_ENV] = saved
        ok("missing secret: issue() raises TokenSecretMissing; validate() returns None")

        # ===============================================================
        # Step 10 — NEGATIVE: orchestrator with no token_store + token →
        # status='invalid' (operator-misconfig surface, not silent-OK)
        # ===============================================================
        step("10. NEGATIVE: token presented to no-store orch → status='invalid'")
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            # Build store separately to issue a real token
            real_store = SessionTokenStore(revocation_path=td / "real.json")
            encoded, _ = real_store.issue(operator_id="heidi")
            # Orchestrator created WITHOUT token_store
            orch = _make_orch(td, with_token_store=False)
            r = orch.evaluate("git status", session_token=encoded)
            if r.token_status != "invalid":
                fail(f"no-store + token should be 'invalid', got {r.token_status}")
        ok("orchestrator without store + valid token → 'invalid' (operator misconfig surfaces)")

        # ===============================================================
        # Step 11 — NEGATIVE: signature compare uses constant-time hmac
        # ===============================================================
        step("11. NEGATIVE: source uses hmac.compare_digest (constant-time)")
        src = (REPO / "approval_agent" / "session_token.py").read_text(encoding="utf-8")
        if "hmac.compare_digest" not in src:
            fail(
                "session_token.py does not use hmac.compare_digest — "
                "vulnerable to timing-attack on signature comparison"
            )
        # Also check it's not bypassed by a == fallback below
        if "== expected_sig" in src or "expected_sig ==" in src:
            fail("source uses == on signatures somewhere — timing leak")
        ok("hmac.compare_digest used; no == on signatures")

        # ===============================================================
        # Step 12 — audit row carries operator_id + token_status
        # ===============================================================
        step("12. audit row carries operator_id + token_status")
        import json as _json
        with tempfile.TemporaryDirectory() as tdname:
            td = Path(tdname)
            orch = _make_orch(td)
            encoded, _ = orch.token_store.issue(operator_id="ivan")
            orch.evaluate("docker compose ps", session_token=encoded)
            orch.evaluate("rm something", session_token=None)  # anonymous
            audit_path = td / "audit.jsonl"
            lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
            if len(lines) != 2:
                fail(f"expected 2 audit rows, got {len(lines)}")
            row1 = _json.loads(lines[0])
            row2 = _json.loads(lines[1])
            if row1.get("operator_id") != "ivan":
                fail(f"audit row 1 operator_id wrong: {row1.get('operator_id')}")
            if row1.get("token_status") != "valid":
                fail(f"audit row 1 token_status wrong: {row1.get('token_status')}")
            if row2.get("operator_id") is not None:
                fail(f"audit row 2 (anonymous) should have operator_id=None: {row2.get('operator_id')}")
            if row2.get("token_status") != "anonymous":
                fail(f"audit row 2 token_status wrong: {row2.get('token_status')}")
        ok("audit rows carry operator_id + token_status correctly")

        print(f"\n{GREEN}{BOLD}ALL 12 STEPS PASSED{NC}")
        return 0

    finally:
        # Restore secret env
        if orig_secret is None:
            os.environ.pop(SECRET_ENV, None)
        else:
            os.environ[SECRET_ENV] = orig_secret


if __name__ == "__main__":
    sys.exit(main())
