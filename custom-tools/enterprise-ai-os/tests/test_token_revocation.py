# Negative drills for Iter 23 (2026-05-17): JWT token revocation.

import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


VALID_SECRET = "x" * 64


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    monkeypatch.delenv("JWT_ISSUER", raising=False)
    monkeypatch.delenv("JWT_AUDIENCE", raising=False)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")
    from identity.jwt_auth import JWTAuth
    return JWTAuth()


def test_unrevoked_token_validates(auth):
    token = auth.create_token({"user_id": "alice"})
    claims = auth.verify_token(token)
    assert claims["user_id"] == "alice"
    assert "jti" in claims  # Iter 23: every token gets a jti


def test_BACKDOOR_CHECK_revoked_token_rejected(auth):
    """Pre-fix: there was no revocation surface — logout couldn't
    actually log a user out until token expiry."""
    from identity.jwt_auth import TokenInvalidError
    token = auth.create_token({"user_id": "alice"})
    auth.revoke_token(token)
    with pytest.raises(TokenInvalidError, match="revoked"):
        auth.verify_token(token)


def test_revoke_other_tokens_unaffected(auth):
    token1 = auth.create_token({"user_id": "alice"})
    token2 = auth.create_token({"user_id": "bob"})
    auth.revoke_token(token1)
    # token2 was issued separately (different jti); must still work.
    claims = auth.verify_token(token2)
    assert claims["user_id"] == "bob"


def test_revoke_garbage_token_throws_not_pollutes_blacklist(auth):
    """Cannot revoke a malformed token — protects the blacklist
    from being filled with attacker-controlled jtis."""
    from identity.jwt_auth import TokenInvalidError
    with pytest.raises(TokenInvalidError):
        auth.revoke_token("not.a.real.token")
    assert auth.revocation_list.size() == 0


def test_revocation_list_purge_expired(auth):
    from identity.token_revocation import TokenRevocationList
    rl = TokenRevocationList()
    rl.revoke("old-jti", datetime.now(timezone.utc).timestamp() - 100)
    rl.revoke("fresh-jti", datetime.now(timezone.utc).timestamp() + 3600)
    purged = rl.purge_expired()
    assert purged == 1
    assert rl.size() == 1
    assert rl.is_revoked("fresh-jti")
    assert not rl.is_revoked("old-jti")


def test_is_revoked_returns_false_for_missing_jti(auth):
    # A token without a jti claim (legacy) is treated as not revoked
    # rather than as an error — backcompat.
    assert auth.revocation_list.is_revoked(None) is False
    assert auth.revocation_list.is_revoked("") is False


def test_revoke_requires_nonempty_jti():
    from identity.token_revocation import TokenRevocationList
    rl = TokenRevocationList()
    with pytest.raises(ValueError):
        rl.revoke("", 999999.0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
