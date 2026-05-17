# Added Iter 23 (2026-05-17) — in-memory JWT revocation list
# (jti blacklist with TTL = remaining token lifetime).
#
# Per CLAUDE.md §53.5 — production needs Redis with TTL keys so the
# revocation list is shared across replicas. This stub closes the
# logout-doesn't-actually-log-out gap for single-replica deployments
# and gives the right shape for the Redis swap.

from datetime import datetime, timezone
from typing import Dict, Optional


class TokenRevocationList:
    """Mark tokens (by jti) as revoked until their exp; verify_token
    in jwt_auth.py is expected to call is_revoked(jti) and reject.
    """

    def __init__(self):
        # jti -> exp_epoch_seconds
        self._revoked: Dict[str, float] = {}

    def revoke(self, jti: str, exp_epoch_seconds: float) -> None:
        if not jti:
            raise ValueError("jti is required to revoke a token")
        self._revoked[jti] = exp_epoch_seconds

    def is_revoked(self, jti: Optional[str]) -> bool:
        if not jti:
            return False
        exp = self._revoked.get(jti)
        if exp is None:
            return False
        # Auto-prune entries past their natural expiry — no point
        # holding the jti in memory after the token would have
        # expired anyway.
        if datetime.now(timezone.utc).timestamp() > exp:
            self._revoked.pop(jti, None)
            return False
        return True

    def size(self) -> int:
        return len(self._revoked)

    def purge_expired(self, now_epoch: Optional[float] = None) -> int:
        now = now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp()
        purged = 0
        for jti, exp in list(self._revoked.items()):
            if exp <= now:
                self._revoked.pop(jti)
                purged += 1
        return purged
