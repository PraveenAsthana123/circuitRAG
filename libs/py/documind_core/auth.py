"""
JWT auth verifier + FastAPI dependency for Python services.

Identity-svc (Go) mints RS256 access tokens with a payload that looks
like this (see ``services/identity-svc/internal/jwt/jwt.go``):

    {
      "iss": "documind-local",
      "aud": "documind-services",
      "sub": "<user-uuid>",
      "tenant_id": "<tenant-uuid>",
      "email": "alice@example.com",
      "roles": ["hr:read", "hr:write"],
      "kind": "access",
      "jti": "<uuid>",
      "iat": ..., "nbf": ..., "exp": ...
    }

Python services only need to *verify* — not mint. The verifier loads
the public key at startup and, for each request, validates signature,
issuer, audience, expiry, and that ``kind=access``.

Config keys (inherited from ``CoreSettings``):
  * ``jwt_public_key_path``
  * ``jwt_issuer``
  * ``jwt_audience``

Runtime env:
  * ``DOCUMIND_AUTH_REQUIRED=true`` — enforce auth on every protected
    endpoint. If false (default in dev), the middleware parses the
    Authorization header if present but does not reject unauthenticated
    requests; ``require_roles`` still enforces roles when a protected
    endpoint is hit, returning 401 when no token was supplied.

Design decisions
----------------
* **Opt-in by default.** Dev convenience trumps ambient enforcement —
  drills, curl explorations, and the admin scripts still work with the
  ``X-Tenant-ID`` header. In staging/prod, flip ``DOCUMIND_AUTH_REQUIRED``.
* **Deny-list not wired here.** The Go issuer supports Redis-backed
  revocation; Python verification today does not re-check the deny list
  on every call. Acceptable while every token is 15-minute lifespan —
  add when the dev key rotation story lands.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

import jwt as pyjwt
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

log = logging.getLogger(__name__)


class JWTVerifier:
    """RS256 verifier. Mirrors identity-svc's Issuer.Verify."""

    def __init__(
        self,
        *,
        public_key_path: str,
        issuer: str,
        audience: str,
        expected_kind: str = "access",
    ) -> None:
        p = Path(public_key_path)
        if not p.exists():
            raise FileNotFoundError(f"JWT public key not found: {public_key_path}")
        self._public_key = p.read_bytes()
        self._issuer = issuer
        self._audience = audience
        self._expected_kind = expected_kind

    def verify(self, raw_token: str) -> dict[str, Any]:
        """Parse + validate. Returns the claims dict on success.

        Raises :class:`jwt.InvalidTokenError` (or a subclass) on any
        validation failure — callers translate that to 401.
        """
        claims = pyjwt.decode(
            raw_token,
            self._public_key,
            algorithms=["RS256"],
            issuer=self._issuer,
            audience=self._audience,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        kind = claims.get("kind")
        if self._expected_kind and kind != self._expected_kind:
            raise pyjwt.InvalidTokenError(
                f"wrong token kind: got {kind!r} want {self._expected_kind!r}"
            )
        return claims


# ---------------------------------------------------------------------------
# Middleware — extracts claims, populates request.state, never rejects
# ---------------------------------------------------------------------------
class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Parse the ``Authorization: Bearer <token>`` header (if any) and
    populate ``request.state.tenant_id``, ``user_id``, ``roles``.

    This middleware never rejects: enforcement is scoped to protected
    endpoints via the ``require_roles`` dependency below. An endpoint
    that doesn't opt in stays publicly reachable, which keeps
    ``/health``, ``/api/v1/ask`` etc. honest about their auth posture.

    When ``auth_required=True`` AND a valid token is present, the
    middleware still sets roles; the only thing that changes is that
    ``require_roles`` rejects unauthenticated callers. (A future
    strict-mode could reject here, but today dev drills + operator
    scripts benefit from "auth present if available".)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        verifier: JWTVerifier,
        auth_required: bool = False,
    ) -> None:
        super().__init__(app)
        self._verifier = verifier
        self._required = auth_required

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        # Default empty auth context — so downstream code can always
        # read request.state.roles without hasattr() checks.
        request.state.roles = []
        request.state.auth_user_id = ""
        request.state.token_present = False

        raw = _extract_bearer(request)
        if not raw:
            return await call_next(request)

        request.state.token_present = True
        try:
            claims = self._verifier.verify(raw)
        except pyjwt.InvalidTokenError as exc:
            # Bad token is *always* a 401 — even with auth_required=False
            # it's a positive signal of intent to authenticate, and we
            # never want to silently grant access to an attacker with a
            # forged token.
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "code": "INVALID_TOKEN",
                        "message": str(exc),
                    }
                },
            )

        # Populate. tenant_id from JWT takes precedence over the header —
        # the token IS the source of truth once it's valid.
        claim_tenant = claims.get("tenant_id") or ""
        if claim_tenant:
            request.state.tenant_id = claim_tenant
        request.state.auth_user_id = claims.get("sub", "")
        request.state.user_id = request.state.auth_user_id
        request.state.roles = list(claims.get("roles") or [])
        return await call_next(request)


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


# ---------------------------------------------------------------------------
# Dependency — call from a route to enforce at least one role
# ---------------------------------------------------------------------------
def require_roles(*roles: str) -> Callable[[Request], None]:
    """
    FastAPI dependency that enforces ANY of the given roles.

    * 401 ``NOT_AUTHENTICATED`` — no valid token presented.
    * 403 ``INSUFFICIENT_SCOPE`` — token valid but roles don't match.

    Use via::

        @router.post(
            "/api/v1/drafts/{id}/resolve",
            dependencies=[Depends(require_roles("hr:write"))],
        )

    If *zero* roles are supplied this is a pure "must be authenticated"
    check — useful for endpoints that don't care which role you have.
    """
    required = set(roles)

    def dep(request: Request) -> None:
        token_present = getattr(request.state, "token_present", False)
        if not token_present:
            raise HTTPException(
                status_code=401,
                detail={"code": "NOT_AUTHENTICATED", "message": "Bearer token required"},
            )
        if not required:
            return
        have = set(getattr(request.state, "roles", []) or [])
        if required.isdisjoint(have):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INSUFFICIENT_SCOPE",
                    "required": sorted(required),
                    "have": sorted(have),
                },
            )

    return dep


def required_role_for_tool(tool: str) -> str:
    """
    Derive the minimum role needed to execute (or replay) an MCP tool.

    Convention: ``<namespace>.<verb>`` → ``<namespace>:write``. So
    ``hr.leave_request`` → ``hr:write``. A read-only namespace could
    use ``hr:read``, but replaying a tool is a write-side action, so
    we always require ``:write``.
    """
    namespace = tool.split(".", 1)[0] if "." in tool else tool
    return f"{namespace}:write"


__all__ = [
    "JWTAuthMiddleware",
    "JWTVerifier",
    "require_roles",
    "required_role_for_tool",
]
