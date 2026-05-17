# ✅ P0 FIXED (Iter 1, 2026-05-17): JWTAuth refuses to construct if
#     JWT_SECRET_KEY is unset/insecure/short. (See test_jwt_secret_hardening.)
# ✅ P1 FIXED (Iter 12, 2026-05-17): iss/aud/nbf/iat now enforced.
#     - iss: required if JWT_ISSUER is set; verify_token rejects
#       tokens with a different issuer.
#     - aud: required if JWT_AUDIENCE is set; verify_token rejects
#       tokens with a different audience.
#     - nbf: tokens minted include a `nbf` claim equal to `iat`;
#       tokens used before `nbf` (clock skew, replay) are rejected
#       within a tolerance window (JWT_LEEWAY_SECONDS, default 30).
#     - iat: every token now carries an `iat` claim.
#
#     Negative drill: tests/test_jwt_claims_validation.py
#
# ✅ P1 FIXED (Iter 23, 2026-05-17): token revocation via jti
#     blacklist. Tokens now carry a `jti` (UUID) claim; verify_token
#     checks the revocation list and rejects revoked tokens. Default
#     revocation list is in-memory; production should inject a
#     Redis-backed implementation (same is_revoked/revoke surface).
#
# ⚠️ STILL REQUIRED before real deployment (see GAPS.md Tool Set 35):
#     - Move to RS256 / EdDSA with a JWKS endpoint (HS256 is symmetric)

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from jose import jwt, JWTError

from identity.token_revocation import TokenRevocationList


_INSECURE_SECRETS = {"change-me", "changeme", "secret", "password", ""}
_MIN_SECRET_LENGTH = 32


class TokenInvalidError(Exception):
    pass


class JWTAuth:
    def __init__(self, revocation_list: Optional[TokenRevocationList] = None):
        # Iter 23: optional revocation list injection. If omitted,
        # uses a fresh in-memory instance. Production: inject a
        # Redis-backed implementation.
        self.revocation_list = revocation_list or TokenRevocationList()

        secret = os.getenv("JWT_SECRET_KEY")

        if secret is None:
            raise RuntimeError(
                "JWT_SECRET_KEY environment variable is not set. "
                "Refusing to construct JWTAuth with an insecure default. "
                "Set JWT_SECRET_KEY to a high-entropy value (>= 32 chars) "
                "before constructing this class."
            )

        if secret.strip().lower() in _INSECURE_SECRETS:
            raise RuntimeError(
                f"JWT_SECRET_KEY is set to a well-known insecure default "
                f"({secret!r}). Refusing to construct JWTAuth. "
                f"Set JWT_SECRET_KEY to a high-entropy value (>= 32 chars)."
            )

        if len(secret) < _MIN_SECRET_LENGTH:
            raise RuntimeError(
                f"JWT_SECRET_KEY is {len(secret)} chars; minimum is "
                f"{_MIN_SECRET_LENGTH}. Refusing to construct JWTAuth."
            )

        self.secret_key = secret
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

        # Optional but recommended for production. Leaving them None
        # disables that specific check (compat with the pre-fix shape).
        self.issuer: Optional[str] = os.getenv("JWT_ISSUER") or None
        self.audience: Optional[str] = os.getenv("JWT_AUDIENCE") or None
        self.leeway_seconds = int(os.getenv("JWT_LEEWAY_SECONDS", "30"))

    def create_token(self, payload: Dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        claims = payload.copy()
        claims["iat"] = now
        claims["nbf"] = now
        claims["exp"] = now + timedelta(minutes=self.expire_minutes)
        # Iter 23: jti for revocation. Caller may override (e.g.,
        # binding the token to a session_id); default is a fresh UUID.
        if "jti" not in claims:
            claims["jti"] = str(uuid.uuid4())
        if self.issuer is not None:
            claims["iss"] = self.issuer
        if self.audience is not None:
            claims["aud"] = self.audience

        return jwt.encode(
            claims,
            self.secret_key,
            algorithm=self.algorithm
        )

    def verify_token(self, token: str) -> Dict[str, Any]:
        # python-jose puts leeway INSIDE options (not a top-level
        # kwarg, unlike PyJWT). iss/aud go top-level.
        decode_kwargs: Dict[str, Any] = {
            "algorithms": [self.algorithm],
            "options": {
                "require_exp": True,
                "require_iat": True,
                "require_nbf": True,
                "verify_iat": True,
                "verify_nbf": True,
                "verify_exp": True,
                "leeway": self.leeway_seconds,
            },
        }
        if self.issuer is not None:
            decode_kwargs["issuer"] = self.issuer
            decode_kwargs["options"]["require_iss"] = True
        if self.audience is not None:
            decode_kwargs["audience"] = self.audience
            decode_kwargs["options"]["require_aud"] = True

        try:
            claims = jwt.decode(token, self.secret_key, **decode_kwargs)
        except JWTError as exc:
            raise TokenInvalidError(f"Invalid or expired token: {exc}") from exc

        # Iter 23: revocation check AFTER signature + temporal claims
        # pass — keeps the revocation list from being consulted on
        # garbage input.
        if self.revocation_list.is_revoked(claims.get("jti")):
            raise TokenInvalidError("Token has been revoked")

        return claims

    def revoke_token(self, token: str) -> None:
        """Add this token's jti to the revocation list. Useful for
        logout endpoints. Verifies the token first so a malformed
        token can't pollute the blacklist."""
        claims = self.verify_token(token)
        jti = claims.get("jti")
        exp = claims.get("exp")
        if not jti or not exp:
            raise TokenInvalidError(
                "Token lacks jti/exp; cannot revoke"
            )
        # exp is an epoch seconds int after jose decode
        self.revocation_list.revoke(jti, float(exp))
