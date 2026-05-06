"""Session-scoped approval cache — pattern-keyed TTL.

The brutal-honesty mechanism behind "approve similar for 30 minutes":
when an operator approves an ASK_ONCE pattern, store the pattern (not
the exact command) with a TTL so subsequent commands matching the
SAME pattern auto-approve until the TTL expires.

Critical invariants (drill-locked):

  - The cache NEVER promotes a command from BLOCK or ALWAYS_ASK to
    AUTO_APPROVE. Cache-hit logic only applies when classify() returns
    ASK_ONCE. drill_approval_batching.py asserts both directions.

  - Cache key is the matched_pattern from CommandDecision, NOT the
    command itself. This is what gives "approve similar" semantics:
    one approval covers the whole pattern, not just one literal.

  - Storage is in-memory + file-persisted with atomic write. Process
    restarts → cache reloads. File-corruption → cache empties (fail-
    closed; operator will be re-prompted, no incorrect auto-approves).

  - TTL is enforced at lookup time, not by a sweeper thread. Lazy
    expiry keeps the module sync-only and easy to drill.

Composes with:
  - approval_agent.command_policy.classify — input direction
  - approval_agent.command_orchestrator      — integration point
  - paperclip_manager.aggregate_approval_engine — surfaces hit-rate
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = REPO_ROOT / ".loop" / "approval_session_cache.json"

# Per session_ttl_minutes in YAML policy. Module default = 30 min, but
# the orchestrator passes the actual policy value through.
DEFAULT_TTL_SECONDS = 30 * 60


@dataclass
class CachedApproval:
    """One cache entry. Frozen at insert time except for hit_count."""

    pattern: str
    approved_by: str
    approved_at: float
    expires_at: float
    hit_count: int = 0

    def is_expired(self, *, now: float | None = None) -> bool:
        return (now or time.time()) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CachedApproval:
        return cls(
            pattern=str(d["pattern"]),
            approved_by=str(d.get("approved_by", "operator")),
            approved_at=float(d["approved_at"]),
            expires_at=float(d["expires_at"]),
            hit_count=int(d.get("hit_count", 0)),
        )


class SessionCache:
    """Pattern-keyed TTL cache. Thread-safe-ish (single-writer assumption).

    File-persisted with atomic write so process restarts don't lose state
    mid-session. The drill simulates restart by instantiating two caches
    sharing the same path.

    Hard rule: cache mutations go through ``store()`` and ``invalidate()``
    only — there is no public field assignment. This keeps the file
    invariant safe under all callers.
    """

    def __init__(
        self,
        *,
        path: Path | str | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._path = Path(path) if path else DEFAULT_CACHE_PATH
        self._ttl_seconds = int(ttl_seconds)
        self._cache: dict[str, CachedApproval] = {}
        self._load_from_disk()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    @property
    def path(self) -> Path:
        return self._path

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("session_cache_load_failed path=%s err=%s — empty start",
                        self._path, exc)
            return
        if not isinstance(data, dict):
            return
        for pat, raw in data.items():
            try:
                self._cache[pat] = CachedApproval.from_dict(raw)
            except Exception as exc:  # noqa: BLE001
                log.debug("session_cache_skip_malformed_entry pat=%s err=%s", pat, exc)
        # Drop expired on load to keep the file small
        now = time.time()
        self._cache = {p: c for p, c in self._cache.items() if not c.is_expired(now=now)}

    def _save_to_disk(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {p: c.to_dict() for p, c in self._cache.items()}
            # Atomic write — temp file then rename
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=self._path.parent, prefix=".session_cache_", suffix=".tmp",
            )
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp_path, self._path)
        except Exception as exc:  # noqa: BLE001
            log.warning("session_cache_save_failed path=%s err=%s",
                        self._path, exc)

    def store(self, pattern: str, *, approved_by: str = "operator") -> CachedApproval:
        """Approve a pattern for this session. Overwrites existing entry."""
        now = time.time()
        entry = CachedApproval(
            pattern=pattern,
            approved_by=approved_by,
            approved_at=now,
            expires_at=now + self._ttl_seconds,
            hit_count=0,
        )
        self._cache[pattern] = entry
        self._save_to_disk()
        return entry

    def lookup(self, pattern: str | None) -> CachedApproval | None:
        """Return a non-expired entry for ``pattern``, or None.

        Increments hit_count on hit AND persists — so the drill can verify
        ``hit_count`` reflects actual cache usage. Returns None for
        ``pattern is None`` (defensive: ASK_ONCE without a matched
        pattern can't be cached).
        """
        if not pattern:
            return None
        entry = self._cache.get(pattern)
        if entry is None:
            return None
        if entry.is_expired():
            del self._cache[pattern]
            self._save_to_disk()
            return None
        entry.hit_count += 1
        self._save_to_disk()
        return entry

    def invalidate(self, pattern: str) -> bool:
        """Force-expire one pattern. Returns True if a row was removed."""
        if pattern in self._cache:
            del self._cache[pattern]
            self._save_to_disk()
            return True
        return False

    def stats(self) -> dict[str, Any]:
        """Operator-readable summary. Used by paperclip aggregator."""
        now = time.time()
        active = [c for c in self._cache.values() if not c.is_expired(now=now)]
        total_hits = sum(c.hit_count for c in active)
        return {
            "active_count": len(active),
            "total_hits": total_hits,
            "ttl_seconds": self._ttl_seconds,
            "patterns": [
                {
                    "pattern": c.pattern,
                    "approved_by": c.approved_by,
                    "expires_in_s": int(c.expires_at - now),
                    "hit_count": c.hit_count,
                }
                for c in sorted(active, key=lambda x: x.expires_at)
            ],
        }

    def clear_all(self) -> int:
        """Drop every entry. For tests + operator panic-button only."""
        n = len(self._cache)
        self._cache = {}
        self._save_to_disk()
        return n


__all__ = ["SessionCache", "CachedApproval", "DEFAULT_TTL_SECONDS"]
