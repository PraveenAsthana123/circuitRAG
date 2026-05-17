# Negative drill for the P0 /auth/token backdoor fix in
# identity/auth_route_example.py (2026-05-17).
#
# Each test asserts a NEGATIVE case — the route MUST NOT issue
# admin tokens to unauthenticated callers. These tests would all
# FAIL against the pre-fix version which signed whatever the
# client sent.

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


VALID_SECRET = "x" * 64


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)

    from identity.jwt_auth import JWTAuth
    from identity.user_store import UserStore
    from identity.credential_store import CredentialStore
    from identity.role_assignment import RoleAssignment
    from identity.auth_route_example import router, configure_auth_route

    # Seed test data
    users = UserStore()
    users.create_user(user_id="alice", email="alice@example.com", tenant_id="tenant-a")
    users.create_user(user_id="bob", email="bob@example.com", tenant_id="tenant-b", status="inactive")

    creds = CredentialStore()
    creds.set_password("alice", "correct-horse-battery-staple")
    creds.set_password("bob", "another-strong-pw")

    role_assignment = RoleAssignment()
    role_assignment.assign_role("alice", "viewer")
    # Note: alice is deliberately NOT an admin in the role store.

    configure_auth_route(users, creds, role_assignment, JWTAuth())

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _decode_claims(token: str) -> dict:
    from jose import jwt
    return jwt.decode(token, VALID_SECRET, algorithms=["HS256"])


# ---------- POSITIVE: legitimate login works ----------

def test_legitimate_login_succeeds(client):
    res = client.post("/auth/token", json={
        "user_id": "alice",
        "password": "correct-horse-battery-staple",
    })
    assert res.status_code == 200
    token = res.json()["access_token"]
    claims = _decode_claims(token)
    assert claims["user_id"] == "alice"
    assert claims["tenant_id"] == "tenant-a"
    assert claims["roles"] == ["viewer"]


# ---------- NEGATIVE: backdoor scenarios from the pre-fix bug ----------

def test_client_cannot_claim_admin_role(client):
    """The pre-fix bug allowed any caller to claim ['admin'] in the body."""
    res = client.post("/auth/token", json={
        "user_id": "alice",
        "password": "correct-horse-battery-staple",
        "roles": ["admin"],  # body-claimed role
    })
    # New schema rejects extra fields OR ignores them entirely.
    # Either way, the issued token must NOT contain "admin".
    if res.status_code == 200:
        claims = _decode_claims(res.json()["access_token"])
        assert "admin" not in claims["roles"], (
            "BACKDOOR REGRESSED: client-claimed admin role appeared in token"
        )


def test_client_cannot_override_tenant_id(client):
    """The pre-fix bug allowed any caller to claim any tenant_id."""
    res = client.post("/auth/token", json={
        "user_id": "alice",
        "password": "correct-horse-battery-staple",
        "tenant_id": "tenant-b",  # body-claimed tenant
    })
    if res.status_code == 200:
        claims = _decode_claims(res.json()["access_token"])
        assert claims["tenant_id"] == "tenant-a", (
            "BACKDOOR REGRESSED: client-claimed tenant_id overrode server lookup"
        )


def test_wrong_password_rejected(client):
    res = client.post("/auth/token", json={
        "user_id": "alice",
        "password": "definitely-wrong",
    })
    assert res.status_code == 401
    assert "Invalid credentials" in res.json()["detail"]


def test_unknown_user_rejected(client):
    res = client.post("/auth/token", json={
        "user_id": "carol-does-not-exist",
        "password": "anything",
    })
    assert res.status_code == 401


def test_inactive_user_rejected(client):
    res = client.post("/auth/token", json={
        "user_id": "bob",
        "password": "another-strong-pw",
    })
    assert res.status_code == 403


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
