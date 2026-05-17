# ✅ P0 FIXED (2026-05-17): JWTAuth refuses to construct if
#     JWT_SECRET_KEY is unset, equals the literal "change-me", or is
#     shorter than 32 chars. Forging tokens against this module now
#     requires the real env-injected secret, not a hardcoded fallback.
#     Negative drill: tests/test_jwt_secret_hardening.py
#
# ⚠️ STILL REQUIRED before real deployment (not in scope for this P0
#     fix, see GAPS.md Tool Set 35):
#     - Move to RS256 / EdDSA with a JWKS endpoint (HS256 is symmetric
#       — every verifier holds the signing key)
#     - Validate `iss` (issuer) and `aud` (audience) claims
#     - Add `nbf` (not-before) and `iat` (issued-at) claims
#     - Implement token revocation (blacklist / jti cache)
#     - Add clock-skew tolerance window

import os
from datetime import datetime, timedelta
from typing import Dict, Any
from jose import jwt, JWTError


_INSECURE_SECRETS = {"change-me", "changeme", "secret", "password", ""}
_MIN_SECRET_LENGTH = 32


class JWTAuth:
    def __init__(self):
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

    def create_token(self, payload: Dict[str, Any]) -> str:
        claims = payload.copy()
        claims["exp"] = datetime.utcnow() + timedelta(minutes=self.expire_minutes)

        return jwt.encode(
            claims,
            self.secret_key,
            algorithm=self.algorithm
        )

    def verify_token(self, token: str) -> Dict[str, Any]:
        try:
            return jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
        except JWTError as exc:
            raise PermissionError("Invalid or expired token") from exc
