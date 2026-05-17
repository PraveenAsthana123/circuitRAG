# Negative drills for Iter 12 (2026-05-17): JWT iss/aud/nbf/iat validation.

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


VALID_SECRET = "x" * 64


@pytest.fixture
def auth_with_iss_aud(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    monkeypatch.setenv("JWT_ISSUER", "https://ai-os.example.com")
    monkeypatch.setenv("JWT_AUDIENCE", "ai-os-api")
    monkeypatch.setenv("JWT_LEEWAY_SECONDS", "5")
    from identity.jwt_auth import JWTAuth
    return JWTAuth()


@pytest.fixture
def auth_no_iss_aud(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    monkeypatch.delenv("JWT_ISSUER", raising=False)
    monkeypatch.delenv("JWT_AUDIENCE", raising=False)
    from identity.jwt_auth import JWTAuth
    return JWTAuth()


# ---------- POSITIVE: legit round-trip ----------

def test_round_trip_with_iss_and_aud(auth_with_iss_aud):
    auth = auth_with_iss_aud
    token = auth.create_token({"user_id": "u"})
    claims = auth.verify_token(token)
    assert claims["user_id"] == "u"
    assert claims["iss"] == "https://ai-os.example.com"
    assert claims["aud"] == "ai-os-api"
    assert "iat" in claims
    assert "nbf" in claims


# ---------- NEGATIVE: missing or wrong claims ----------

def test_token_signed_without_iss_rejected_by_iss_required_verifier(
    auth_with_iss_aud, monkeypatch
):
    """A verifier that requires iss MUST reject a token that lacks one."""
    from identity.jwt_auth import TokenInvalidError, JWTAuth
    from jose import jwt

    # Forge a token with the right secret but NO iss/aud claims.
    forged = jwt.encode(
        {
            "user_id": "u",
            "iat": datetime.now(timezone.utc),
            "nbf": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        VALID_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenInvalidError):
        auth_with_iss_aud.verify_token(forged)


def test_wrong_issuer_rejected(auth_with_iss_aud, monkeypatch):
    """Token from a different issuer must be rejected (BACKDOOR CHECK)."""
    from identity.jwt_auth import TokenInvalidError
    from jose import jwt
    forged = jwt.encode(
        {
            "user_id": "u",
            "iss": "https://attacker.example.com",  # WRONG issuer
            "aud": "ai-os-api",
            "iat": datetime.now(timezone.utc),
            "nbf": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        VALID_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenInvalidError):
        auth_with_iss_aud.verify_token(forged)


def test_wrong_audience_rejected(auth_with_iss_aud):
    """Token meant for a different audience must be rejected."""
    from identity.jwt_auth import TokenInvalidError
    from jose import jwt
    forged = jwt.encode(
        {
            "user_id": "u",
            "iss": "https://ai-os.example.com",
            "aud": "different-service",  # WRONG audience
            "iat": datetime.now(timezone.utc),
            "nbf": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        VALID_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenInvalidError):
        auth_with_iss_aud.verify_token(forged)


def test_nbf_in_future_rejected_beyond_leeway(auth_with_iss_aud):
    """Token usable only in the future (replay-by-rewind) must be rejected."""
    from identity.jwt_auth import TokenInvalidError
    from jose import jwt
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    forged = jwt.encode(
        {
            "user_id": "u",
            "iss": "https://ai-os.example.com",
            "aud": "ai-os-api",
            "iat": future,
            "nbf": future,
            "exp": future + timedelta(minutes=5),
        },
        VALID_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenInvalidError):
        auth_with_iss_aud.verify_token(forged)


def test_expired_token_rejected(auth_with_iss_aud):
    """Token past its exp must be rejected."""
    from identity.jwt_auth import TokenInvalidError
    from jose import jwt
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    forged = jwt.encode(
        {
            "user_id": "u",
            "iss": "https://ai-os.example.com",
            "aud": "ai-os-api",
            "iat": past,
            "nbf": past,
            "exp": past + timedelta(minutes=5),  # still in the past
        },
        VALID_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenInvalidError):
        auth_with_iss_aud.verify_token(forged)


def test_iss_aud_check_skipped_when_env_not_set(auth_no_iss_aud):
    """Backwards-compat: with no iss/aud env, tokens without them work."""
    auth = auth_no_iss_aud
    token = auth.create_token({"user_id": "u"})
    claims = auth.verify_token(token)
    assert claims["user_id"] == "u"


def test_token_missing_iat_rejected(auth_no_iss_aud):
    """Even without iss/aud, iat is required per the verifier options."""
    from identity.jwt_auth import TokenInvalidError
    from jose import jwt
    forged = jwt.encode(
        {
            "user_id": "u",
            # no iat
            "nbf": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        VALID_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenInvalidError):
        auth_no_iss_aud.verify_token(forged)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
