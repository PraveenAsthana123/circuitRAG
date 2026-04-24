"""
At-rest encryption for secrets stored in the database.

Fernet (AES-128-CBC + HMAC-SHA256) from :mod:`cryptography`. Used for
encrypting API keys, OAuth client secrets, webhook signing keys, and any
per-tenant secret before it lands in PostgreSQL.

Design Area 3 — Trust Boundary: even if the DB is compromised, the
encrypted secrets remain useless without the encryption key (which lives
in the process's env var, not in the DB).

Do NOT use this for authentication (password storage) — use a proper
KDF like argon2 via :mod:`passlib` for that.
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from .exceptions import ValidationError

log = logging.getLogger(__name__)

_SENTINEL = "__ENCRYPTED__:"


class Cipher:
    """
    Thin wrapper over Fernet that adds a sentinel prefix so you can tell
    an encrypted string from a plaintext string at a glance in the DB.
    """

    def __init__(self, key: str | bytes) -> None:
        if not key:
            raise ValidationError("Cipher requires a non-empty encryption key")
        key_bytes = key.encode() if isinstance(key, str) else key
        try:
            self._fernet = Fernet(key_bytes)
        except Exception as exc:
            raise ValidationError(
                "Invalid Fernet key. Generate one with: "
                "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt + return a sentinel-prefixed string ready for DB storage."""
        token = self._fernet.encrypt(plaintext.encode()).decode()
        return _SENTINEL + token

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt. If the input is not sentinel-prefixed, return as-is
        (supports migration from plaintext to encrypted). If decryption
        fails, return a marker string instead of raising — callers can
        detect and surface to admins.
        """
        if not ciphertext.startswith(_SENTINEL):
            # Legacy plaintext or already-decoded — let callers decide.
            return ciphertext

        token = ciphertext[len(_SENTINEL):]
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            log.error("cipher_decrypt_failed (wrong key? corrupt payload?)")
            return "***DECRYPTION_FAILED***"


def generate_key() -> str:
    """Generate a new Fernet key. Print, save to env, never commit."""
    return Fernet.generate_key().decode()
