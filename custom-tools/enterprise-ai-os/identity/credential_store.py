# Added 2026-05-17 as part of Iteration 2/5 (§44 autonomous fix loop).
# Pairs with UserStore + RoleAssignment to give /auth/token a real
# server-side password verification flow. Without this, the existing
# /auth/token route was a backdoor (any client could claim any role).
#
# In-memory only (passwords stored hashed) — see GAPS.md for the
# production fix (Postgres `credentials` table with column-level
# encryption + write-restricted role).

from typing import Dict, Optional
from passlib.context import CryptContext


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class CredentialStore:
    def __init__(self):
        self._password_hashes: Dict[str, str] = {}

    def set_password(self, user_id: str, plaintext_password: str) -> None:
        if not plaintext_password or len(plaintext_password) < 8:
            raise ValueError(
                "Password must be at least 8 characters."
            )
        self._password_hashes[user_id] = _pwd_context.hash(plaintext_password)

    def verify_password(self, user_id: str, candidate_password: str) -> bool:
        stored = self._password_hashes.get(user_id)
        if stored is None:
            # Constant-time-ish reject — still hash the candidate to
            # avoid revealing user existence via timing.
            _pwd_context.dummy_verify()
            return False
        return _pwd_context.verify(candidate_password, stored)

    def has_credentials(self, user_id: str) -> bool:
        return user_id in self._password_hashes
