"""Session-token issuance + validation — operator browser-session continuity.

The pattern-cache (approval_agent.session_cache) keyed approvals by
COMMAND PATTERN. This module adds a second key: WHICH OPERATOR is
making the approval. Two operators on the same admin instance can
have their own session-cache views without leaking approvals between
sessions.

Token format:
    <token_id_uuid>.<base64(payload_json)>.<base64(hmac_sha256)>

Payload fields:
    token_id        — UUID4 (the canonical revocation key)
    operator_id     — opaque string set by the issuing surface
    issued_at       — epoch seconds
    expires_at      — epoch seconds
    scopes          — list of strings (e.g. ['approve', 'reject'])

Security invariants (drill-locked):
    1. HMAC over (token_id, operator_id, issued_at, expires_at, scopes)
       using DOCUMIND_SESSION_TOKEN_SECRET. Tampering with any field
       invalidates the signature.
    2. Expired token → ``validate()`` returns None.
    3. Revoked token (token_id in revocation set) → ``validate()`` None.
    4. Unknown secret (env var unset) → ``issue()`` raises; never
       fall back to a default secret (would let attackers forge
       tokens against a known-default-secret deployment).
    5. ``validate()`` is constant-time on signature comparison
       (hmac.compare_digest) — drilled.

Per CLAUDE.md §38 (governance), §42 (operational autonomy), §47
(architecture: auth at boundary), §52 row 4 (operator API gap),
§55.3 (outcome-based contract). Composes with existing
session_cache + command_orchestrator without breaking the
backwards-compat (token=None falls back to anonymous flow).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVOCATION_PATH = REPO_ROOT / ".loop" / "approval_token_revocations.json"
DEFAULT_TTL_SECONDS = 8 * 60 * 60  # 8h operator workday
SECRET_ENV = "DOCUMIND_SESSION_TOKEN_SECRET"  # noqa: S105 - env var NAME, not value


class TokenError(Exception):
    """Base exception for token-related failures."""


class TokenSecretMissing(TokenError):
    """Raised when DOCUMIND_SESSION_TOKEN_SECRET is unset.

    Never silently fall back to a default — attackers with knowledge
    of the default could forge tokens against any deployment that
    forgot to set the env var.
    """


class TokenInvalid(TokenError):
    """Raised when a token signature, expiry, or shape fails."""


@dataclass(frozen=True)
class SessionToken:
    """One issued + signed session token. Immutable, audit-ready."""

    token_id: str
    operator_id: str
    issued_at: float
    expires_at: float
    scopes: tuple[str, ...] = field(default_factory=tuple)

    def is_expired(self, *, now: float | None = None) -> bool:
        return (now or time.time()) >= self.expires_at

    def to_payload(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "operator_id": self.operator_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "scopes": list(self.scopes),
        }


def _get_secret() -> bytes:
    secret = os.environ.get(SECRET_ENV)
    if not secret:
        raise TokenSecretMissing(
            f"{SECRET_ENV} env var unset. Set to a random ≥32-byte string. "
            "NEVER use a hardcoded default — that would let attackers forge "
            "tokens against any deployment with a known default."
        )
    if len(secret) < 32:
        log.warning(
            "%s is shorter than 32 bytes (got %d). Use a longer random secret.",
            SECRET_ENV, len(secret),
        )
    return secret.encode("utf-8")


def _b64encode(data: bytes) -> str:
    """URL-safe base64 without padding (token-friendly)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign_payload(payload: dict[str, Any], secret: bytes) -> tuple[str, str]:
    """Returns (payload_b64, signature_b64). Stable JSON — keys sorted."""
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_b64 = _b64encode(payload_json.encode("utf-8"))
    sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return payload_b64, _b64encode(sig)


class SessionTokenStore:
    """In-memory + file-persisted revocation list.

    The store does NOT persist issued tokens — those live in operator-
    side cookies. The store ONLY persists token_ids that have been
    revoked, so a re-presented token can be rejected even after a
    process restart.
    """

    def __init__(self, *, revocation_path: Path | str | None = None) -> None:
        self._path = Path(revocation_path) if revocation_path else DEFAULT_REVOCATION_PATH
        self._revoked: set[str] = set()
        self._load_from_disk()

    @property
    def path(self) -> Path:
        return self._path

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("revocation_load_failed path=%s err=%s — empty start",
                        self._path, exc)
            return
        if isinstance(data, dict) and "revoked" in data:
            for tid in data["revoked"]:
                if isinstance(tid, str):
                    self._revoked.add(tid)

    def _save_to_disk(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"revoked": sorted(self._revoked), "version": 1}
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("revocation_save_failed path=%s err=%s",
                        self._path, exc)

    def issue(
        self,
        *,
        operator_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        scopes: tuple[str, ...] = ("approve",),
    ) -> tuple[str, SessionToken]:
        """Issue a new token. Returns (encoded_token_string, SessionToken).

        Raises TokenSecretMissing if the env secret is unset.
        """
        if not operator_id:
            raise TokenError("operator_id must be non-empty")
        secret = _get_secret()
        token_id = str(uuid.uuid4())
        now = time.time()
        st = SessionToken(
            token_id=token_id,
            operator_id=str(operator_id),
            issued_at=now,
            expires_at=now + int(ttl_seconds),
            scopes=tuple(scopes),
        )
        payload_b64, sig_b64 = _sign_payload(st.to_payload(), secret)
        encoded = f"{token_id}.{payload_b64}.{sig_b64}"
        return encoded, st

    def validate(self, encoded: str | None) -> SessionToken | None:
        """Validate an encoded token. Returns the SessionToken on success,
        None on any failure (expired / revoked / tampered / malformed).

        NEVER raises — the orchestrator calls this on every request and
        must not be derailed by a malformed token; instead it falls
        back to anonymous behavior.
        """
        if not encoded:
            return None
        parts = encoded.split(".")
        if len(parts) != 3:
            return None
        token_id, payload_b64, sig_b64 = parts
        if token_id in self._revoked:
            return None
        try:
            secret = _get_secret()
        except TokenSecretMissing:
            log.warning("session_token_secret_missing — all validations fail")
            return None

        # Verify signature first (constant-time).
        expected_sig = _b64encode(
            hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig_b64, expected_sig):
            return None

        # Parse payload only after signature verification.
        try:
            payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(payload, dict):
            return None
        try:
            st = SessionToken(
                token_id=str(payload["token_id"]),
                operator_id=str(payload["operator_id"]),
                issued_at=float(payload["issued_at"]),
                expires_at=float(payload["expires_at"]),
                scopes=tuple(str(s) for s in payload.get("scopes", [])),
            )
        except (KeyError, TypeError, ValueError):
            return None
        # Verify token_id in payload matches the prefix
        if st.token_id != token_id:
            return None
        if st.is_expired():
            return None
        return st

    def revoke(self, token_id: str) -> bool:
        """Add a token_id to the revocation set. Returns True if newly revoked."""
        if not token_id:
            return False
        if token_id in self._revoked:
            return False
        self._revoked.add(token_id)
        self._save_to_disk()
        return True

    def is_revoked(self, token_id: str) -> bool:
        return token_id in self._revoked

    def stats(self) -> dict[str, Any]:
        return {
            "revoked_count": len(self._revoked),
            "revocation_path": str(self._path),
            "secret_set": bool(os.environ.get(SECRET_ENV)),
        }

    def clear_revocations(self) -> int:
        """Drop the revocation set (test-only / operator panic-button)."""
        n = len(self._revoked)
        self._revoked = set()
        self._save_to_disk()
        return n


def generate_dev_secret() -> str:
    """Helper for operators bootstrapping a dev environment.

    Prints to stdout AND returns. NEVER auto-set into the env — that
    would propagate a secret the operator didn't choose into their
    process.
    """
    return secrets.token_hex(32)


__all__ = [
    "SessionToken",
    "SessionTokenStore",
    "TokenError",
    "TokenSecretMissing",
    "TokenInvalid",
    "DEFAULT_TTL_SECONDS",
    "SECRET_ENV",
    "generate_dev_secret",
]
