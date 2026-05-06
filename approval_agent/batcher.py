"""Medium-risk approval batcher — collect, then prompt every N minutes.

The pain pattern this fixes (from operator transcript):
  > 1000 approvals → operator clicks each one individually → fatigue
  >                                                       → bypass
  >                                                       → unsafe

Better: enqueue medium-risk approvals; flush the queue every
``batch_interval_minutes`` so the operator gets ONE batched approval
prompt with N items, not N individual prompts. Batching only applies
to medium-risk (ASK_ONCE) — high (ALWAYS_ASK) and critical (BLOCK)
NEVER batch.

Critical invariants (drill-locked):

  - The queue ONLY accepts ASK_ONCE entries. ALWAYS_ASK and BLOCK are
    drilled rejected — the batcher cannot accidentally widen the auto-
    approve surface.

  - Flush is operator-driven. The orchestrator decides when to flush
    (timer expired, queue depth threshold, explicit operator command).
    No background thread — that would make the drill rely on timing.

  - Queue is JSONL-persisted. Process restart recovers pending entries.
    File-corruption → start with empty queue (fail-closed).

  - One queue entry = one (pattern, command, requested_at) triple. The
    same pattern can appear multiple times in the queue if the operator
    wants to see frequency before approving the pattern session-wide.

Composes with:
  - approval_agent.command_policy.classify  — ASK_ONCE classifier
  - approval_agent.session_cache.SessionCache — flush approvals into cache
  - approval_agent.command_orchestrator       — integration point
  - paperclip_manager.aggregate_approval_engine — surfaces queue depth
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .command_policy import ASK_ONCE

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_PATH = REPO_ROOT / ".loop" / "approval_batch_queue.jsonl"

DEFAULT_FLUSH_INTERVAL_SECONDS = 15 * 60


@dataclass
class BatchEntry:
    pattern: str
    command: str
    decision: str
    risk: str
    requested_at: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "pattern": self.pattern,
            "command": self.command,
            "decision": self.decision,
            "risk": self.risk,
            "requested_at": self.requested_at,
            "metadata": self.metadata,
        })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BatchEntry:
        return cls(
            pattern=str(d["pattern"]),
            command=str(d["command"]),
            decision=str(d["decision"]),
            risk=str(d["risk"]),
            requested_at=float(d["requested_at"]),
            metadata=dict(d.get("metadata") or {}),
        )


class ApprovalBatcher:
    """In-memory + JSONL-persisted queue for medium-risk approvals.

    Operator workflow:
      1. command arrives → orchestrator classifies → ASK_ONCE
      2. orchestrator calls ``batcher.enqueue(...)``
      3. operator either:
         a. flushes manually (clicks "Approve N pending similar")
         b. timer fires (orchestrator calls ``flush_due()``)
      4. flush returns the entries; operator approves them as a batch
      5. orchestrator calls ``session_cache.store(pattern)`` for each
    """

    def __init__(
        self,
        *,
        path: Path | str | None = None,
        flush_interval_seconds: int = DEFAULT_FLUSH_INTERVAL_SECONDS,
    ) -> None:
        self._path = Path(path) if path else DEFAULT_QUEUE_PATH
        self._flush_interval_seconds = int(flush_interval_seconds)
        self._queue: list[BatchEntry] = []
        self._last_flush_at = time.time()
        self._load_from_disk()

    @property
    def flush_interval_seconds(self) -> int:
        return self._flush_interval_seconds

    @property
    def path(self) -> Path:
        return self._path

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    self._queue.append(BatchEntry.from_dict(json.loads(line)))
                except Exception as exc:  # noqa: BLE001
                    log.debug("batcher_skip_malformed_line err=%s", exc)
                    continue
        except Exception as exc:  # noqa: BLE001
            log.warning("batcher_load_failed path=%s err=%s — empty start",
                        self._path, exc)

    def _save_to_disk(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=self._path.parent, prefix=".batch_queue_", suffix=".tmp",
            )
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                for entry in self._queue:
                    f.write(entry.to_json() + "\n")
            os.replace(tmp_path, self._path)
        except Exception as exc:  # noqa: BLE001
            log.warning("batcher_save_failed path=%s err=%s",
                        self._path, exc)

    def enqueue(
        self,
        *,
        pattern: str,
        command: str,
        decision: str,
        risk: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Add a medium-risk entry to the queue. Returns True on accept.

        Rejects (returns False) any non-ASK_ONCE decision — drill-locked.
        Operator misconfiguration cannot leak high-risk into the batch.
        """
        if decision != ASK_ONCE:
            log.warning("batcher_reject decision=%s — only ASK_ONCE may batch",
                        decision)
            return False
        entry = BatchEntry(
            pattern=pattern,
            command=command,
            decision=decision,
            risk=risk,
            requested_at=time.time(),
            metadata=metadata or {},
        )
        self._queue.append(entry)
        self._save_to_disk()
        return True

    def is_due(self, *, now: float | None = None) -> bool:
        """Has the flush interval elapsed since the last flush?"""
        return (now or time.time()) - self._last_flush_at >= self._flush_interval_seconds

    def queue_depth(self) -> int:
        return len(self._queue)

    def flush_due(self, *, now: float | None = None) -> list[BatchEntry]:
        """Return the queued entries IF the interval has elapsed. Empty
        list otherwise.

        After flush, the queue is empty and ``last_flush_at`` resets.
        Operator UI should display the returned entries grouped by
        pattern for batched approval.
        """
        if not self.is_due(now=now):
            return []
        return self.flush_now(now=now)

    def flush_now(self, *, now: float | None = None) -> list[BatchEntry]:
        """Force-flush regardless of interval. Operator-initiated path."""
        entries = list(self._queue)
        self._queue = []
        self._last_flush_at = now or time.time()
        self._save_to_disk()
        return entries

    def stats(self) -> dict[str, Any]:
        now = time.time()
        by_pattern: dict[str, int] = {}
        for e in self._queue:
            by_pattern[e.pattern] = by_pattern.get(e.pattern, 0) + 1
        return {
            "queue_depth": len(self._queue),
            "next_flush_in_s": max(
                0,
                int(self._last_flush_at + self._flush_interval_seconds - now),
            ),
            "is_due": self.is_due(now=now),
            "by_pattern": by_pattern,
            "flush_interval_seconds": self._flush_interval_seconds,
        }


__all__ = [
    "ApprovalBatcher", "BatchEntry",
    "DEFAULT_FLUSH_INTERVAL_SECONDS",
]
