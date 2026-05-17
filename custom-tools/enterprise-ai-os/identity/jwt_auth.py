# ⚠️ SECURITY (P0): if JWT_SECRET_KEY is not set in the environment,
#     this class falls back to the literal string "change-me" as the
#     signing secret. Any attacker who reads this file knows the key
#     and can forge tokens with any roles/tenant. NEVER run this
#     module without setting JWT_SECRET_KEY to a real secret (e.g.,
#     loaded from Vault / OpenBao / AWS Secrets Manager).
#
# ⚠️ ADDITIONAL HARDENING NEEDED before any real deployment:
#     - Move to RS256 / EdDSA with a JWKS endpoint (HS256 is symmetric
#       — every verifier holds the signing key)
#     - Validate `iss` (issuer) and `aud` (audience) claims
#     - Add `nbf` (not-before) and `iat` (issued-at) claims
#     - Implement token revocation (blacklist / jti cache)
#     - Add clock-skew tolerance window
#
#     See GAPS.md Tool Set 35 for the full P0/P1 list.

import os
from datetime import datetime, timedelta
from typing import Dict, Any
from jose import jwt, JWTError


class JWTAuth:
    def __init__(self):
        self.secret_key = os.getenv("JWT_SECRET_KEY", "change-me")
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
