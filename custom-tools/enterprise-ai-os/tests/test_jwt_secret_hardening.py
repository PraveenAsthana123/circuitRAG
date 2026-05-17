# Negative drill for the P0 JWT-secret-default fix in
# identity/jwt_auth.py (2026-05-17).
#
# Each test asserts a NEGATIVE case — JWTAuth() MUST refuse to
# construct when given a weak/missing/default secret. These tests
# would all FAIL against the pre-fix version which silently
# defaulted to "change-me".

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from identity.jwt_auth import JWTAuth, TokenInvalidError


VALID_SECRET = "x" * 64  # 64 chars, well above the 32 minimum


def test_unset_env_refuses_to_construct(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        JWTAuth()


def test_default_change_me_refuses_to_construct(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me")
    with pytest.raises(RuntimeError, match="insecure default"):
        JWTAuth()


def test_well_known_insecure_secret_refuses_to_construct(monkeypatch):
    for weak in ["secret", "password", "changeme", "CHANGE-ME", "  Change-Me  "]:
        monkeypatch.setenv("JWT_SECRET_KEY", weak)
        with pytest.raises(RuntimeError, match="insecure default"):
            JWTAuth()


def test_empty_string_refuses_to_construct(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="insecure default"):
        JWTAuth()


def test_short_secret_refuses_to_construct(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "abc123")  # only 6 chars
    with pytest.raises(RuntimeError, match=r"minimum is 32"):
        JWTAuth()


def test_valid_long_secret_constructs_successfully(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    auth = JWTAuth()
    assert auth.secret_key == VALID_SECRET
    assert auth.algorithm == "HS256"


def test_round_trip_with_valid_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    auth = JWTAuth()
    token = auth.create_token({"user_id": "u1", "tenant_id": "t1"})
    claims = auth.verify_token(token)
    assert claims["user_id"] == "u1"
    assert claims["tenant_id"] == "t1"


def test_invalid_token_raises_domain_exception(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    auth = JWTAuth()

    with pytest.raises(TokenInvalidError):
        auth.verify_token("not-a-valid-token")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
