# ⚠️ SECURITY (P0): THIS ROUTE IS A BACKDOOR — DO NOT EXPOSE IT.
#
#     The endpoint accepts arbitrary `user_id`, `tenant_id`, and `roles`
#     from the client and signs a token containing whatever was sent.
#     There is NO password check, NO MFA, NO email-link confirmation,
#     NO rate limit, and NO audit row.
#
#     A caller can POST `{"user_id": "anyone", "tenant_id": "any",
#     "roles": ["admin"]}` and receive a valid admin token.
#
#     This file is verbatim from Tool Set 35 §7 source. It is here for
#     fidelity. NEVER include it in a router that gets mounted on a
#     network-reachable interface.
#
#     A real /auth/token endpoint must:
#       1. Authenticate the caller (password / OAuth / OIDC / SAML /
#          mTLS / API key)
#       2. Look up `user_id` server-side from the auth result
#       3. Look up `roles` server-side from RoleAssignment (NOT trust
#          the client)
#       4. Look up `tenant_id` server-side from UserStore (NOT trust
#          the client)
#       5. Rate-limit per IP and per identity
#       6. Write an audit row (login attempt, success/failure, IP, UA)
#       7. Reject if user.status != "active" or tenant.status != "active"

from fastapi import APIRouter
from pydantic import BaseModel
from identity.jwt_auth import JWTAuth

router = APIRouter(prefix="/auth", tags=["auth"])

auth = JWTAuth()


class LoginRequest(BaseModel):
    user_id: str
    tenant_id: str
    roles: list[str]


@router.post("/token")
def create_token(request: LoginRequest):
    # ⚠️ DO NOT TRUST request.roles / request.user_id / request.tenant_id
    # in any real implementation. See file header for the safe pattern.
    token = auth.create_token({
        "user_id": request.user_id,
        "tenant_id": request.tenant_id,
        "roles": request.roles
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }
