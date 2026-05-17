# ✅ P0 FIXED (2026-05-17): /auth/token no longer accepts arbitrary
#     user_id / tenant_id / roles from the client. The endpoint now:
#       1. Accepts only user_id + password from the request body.
#       2. Looks up the user from UserStore (rejects unknown / inactive).
#       3. Verifies the password against CredentialStore (bcrypt-hashed).
#       4. Looks up tenant_id from the user record (NOT the request).
#       5. Looks up roles from RoleAssignment (NOT the request).
#       6. Signs the JWT with server-derived claims only.
#
#     A caller can no longer POST {"user_id": "x", "tenant_id": "y",
#     "roles": ["admin"]} and receive a valid admin token.
#
#     Negative drill: tests/test_auth_route_no_backdoor.py
#
# ⚠️ STILL REQUIRED before any real deployment (not in scope for this
#     P0 fix, see GAPS.md Tool Set 35):
#     - Real OAuth2 / OIDC / SSO instead of password storage
#     - Per-IP + per-user rate limit (currently relies on upstream
#       middleware that this file does NOT enforce)
#     - MFA / TOTP for human users
#     - Audit row per login attempt (success + failure)
#     - Account-lockout after N failures
#     - Email-link confirmation for new account creation

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from identity.jwt_auth import JWTAuth
from identity.user_store import UserStore
from identity.credential_store import CredentialStore
from identity.role_assignment import RoleAssignment


router = APIRouter(prefix="/auth", tags=["auth"])


# These would normally be constructed at app-startup and injected via
# Depends() factories. Kept module-level here for example simplicity;
# real deployments must use DI.
_user_store: UserStore | None = None
_credential_store: CredentialStore | None = None
_role_assignment: RoleAssignment | None = None
_jwt_auth: JWTAuth | None = None


def configure_auth_route(
    user_store: UserStore,
    credential_store: CredentialStore,
    role_assignment: RoleAssignment,
    jwt_auth: JWTAuth,
) -> None:
    """Wire the route's dependencies. Call at app startup."""
    global _user_store, _credential_store, _role_assignment, _jwt_auth
    _user_store = user_store
    _credential_store = credential_store
    _role_assignment = role_assignment
    _jwt_auth = jwt_auth


def get_user_store() -> UserStore:
    if _user_store is None:
        raise RuntimeError("Auth route not configured. Call configure_auth_route() at startup.")
    return _user_store


def get_credential_store() -> CredentialStore:
    if _credential_store is None:
        raise RuntimeError("Auth route not configured.")
    return _credential_store


def get_role_assignment() -> RoleAssignment:
    if _role_assignment is None:
        raise RuntimeError("Auth route not configured.")
    return _role_assignment


def get_jwt_auth() -> JWTAuth:
    if _jwt_auth is None:
        raise RuntimeError("Auth route not configured.")
    return _jwt_auth


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


@router.post("/token")
def create_token(
    request: LoginRequest,
    users: UserStore = Depends(get_user_store),
    creds: CredentialStore = Depends(get_credential_store),
    roles: RoleAssignment = Depends(get_role_assignment),
    auth: JWTAuth = Depends(get_jwt_auth),
):
    # 1. User must exist
    user = users.get_user(request.user_id)
    if user is None:
        # Same response shape as wrong-password to avoid revealing
        # whether the user exists (timing leak still present without
        # constant-time path; mitigated by CredentialStore.dummy_verify).
        creds.verify_password(request.user_id, request.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 2. User must be active
    if not users.is_active(request.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    # 3. Password must verify
    if not creds.verify_password(request.user_id, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 4. Claims are SERVER-derived, not client-claimed
    server_tenant_id = user["tenant_id"]
    server_roles = roles.get_roles(request.user_id)

    token = auth.create_token({
        "user_id": user["user_id"],
        "tenant_id": server_tenant_id,
        "roles": server_roles,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
    }
