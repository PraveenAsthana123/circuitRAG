"""SQLite-backed memory for the Sidecar Advisor.

One table for events (paste + advice + rating), one for distilled
patterns. WAL mode + busy_timeout for concurrent UI/CLI access.

Migration runner is intentionally minimal — no Alembic, just a list of
SQL files numbered N_*.sql under ./migrations. Re-applying a migration
is a no-op (CREATE TABLE IF NOT EXISTS).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class AdvisorMemory:
    """Thin SQLite wrapper. Pure synchronous — Phase 1 caller is
    Streamlit (sync) or a CLI; the volume is one event per user paste,
    not high-throughput."""

    def __init__(self, db_path: str | Path = "advisor.db") -> None:
        self._db_path = str(db_path)
        self._policy_version = "unset"
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            isolation_level=None,           # autocommit; we manage txn
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        # §7.3: WAL mode + busy_timeout for concurrent reader (UI) +
        # writer (CLI capture) safety.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            applied = {
                row["name"]
                for row in conn.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='_migrations'
                """).fetchall()
            }
            # If _migrations table doesn't exist yet, both queries below
            # need to be safe.
            existing: set[str] = set()
            if applied:
                existing = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM _migrations"
                    ).fetchall()
                }

            for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
                name = sql_file.name
                if name in existing:
                    continue
                conn.executescript(sql_file.read_text())
                conn.execute(
                    "INSERT OR IGNORE INTO _migrations(name, applied_at) "
                    "VALUES (?, ?)",
                    (name, _utcnow_iso()),
                )

    def set_policy_version(self, version: str) -> None:
        """Caller hashes policy.yaml once at startup and pins it here so
        every record_event() call tags the right version."""
        self._policy_version = version

    # ── Event lifecycle ─────────────────────────────────────────
    def record_event(
        self,
        *,
        event_type: str,
        source: str,
        content: str,
        model_used: str | None,
        advisor_output: dict | None,
        advisor_output_raw: str | None = None,
        duration_s: float = 0.0,
    ) -> int:
        """Insert a new event row. Returns the row id."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO advisor_events (
                    created_at, event_type, source,
                    content_hash, content,
                    model_used, policy_version,
                    advisor_output, advisor_output_raw,
                    duration_s
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utcnow_iso(),
                    event_type,
                    source,
                    _content_hash(content),
                    content,
                    model_used,
                    self._policy_version,
                    json.dumps(advisor_output) if advisor_output else None,
                    advisor_output_raw,
                    duration_s,
                ),
            )
            return cur.lastrowid or 0

    def rate_event(self, event_id: int, rating: str) -> bool:
        """Set the user_rating on an event. Returns True if a row was
        updated. Rating must be 'useful' or 'not_useful' — the column
        is text-typed but the caller is required to enforce the enum."""
        if rating not in ("useful", "not_useful"):
            raise ValueError(
                f"rating must be 'useful' or 'not_useful', got {rating!r}"
            )
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE advisor_events
                SET user_rating = ?, rated_at = ?
                WHERE id = ?
                """,
                (rating, _utcnow_iso(), event_id),
            )
            return cur.rowcount > 0

    def recent_events(
        self,
        limit: int = 50,
        event_type: str | None = None,
        rated_only: bool = False,
    ) -> list[dict]:
        """Return the N most recent events. Used by the UI's
        'audit history' panel."""
        sql = "SELECT * FROM advisor_events"
        clauses: list[str] = []
        params: list = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if rated_only:
            clauses.append("user_rating IS NOT NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """Quick aggregate stats for the dashboard footer."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_events"
            ).fetchone()["n"]
            useful = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_events "
                "WHERE user_rating = 'useful'"
            ).fetchone()["n"]
            not_useful = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_events "
                "WHERE user_rating = 'not_useful'"
            ).fetchone()["n"]
        return {
            "total_events": total,
            "useful": useful,
            "not_useful": not_useful,
            "rated_pct": (
                round(100 * (useful + not_useful) / total, 1)
                if total else 0.0
            ),
        }

    # ── Memory patterns ─────────────────────────────────────────
    def add_pattern(
        self,
        *,
        pattern_kind: str,
        pattern_text: str,
        source_event_ids: list[int],
        confidence: float = 0.5,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO advisor_memory (
                    created_at, pattern_kind, pattern_text,
                    confidence, source_events
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    _utcnow_iso(),
                    pattern_kind,
                    pattern_text,
                    confidence,
                    json.dumps(source_event_ids),
                ),
            )
            return cur.lastrowid or 0

    def get_patterns(
        self,
        kind: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        """Read patterns. event_type filter is best-effort — patterns
        currently aren't tagged with event_type at the schema level
        (Phase 2C+ adds the column). For now the caller filters by
        scanning."""
        sql = "SELECT * FROM advisor_memory"
        params: list = []
        if kind:
            sql += " WHERE pattern_kind = ?"
            params.append(kind)
        sql += " ORDER BY confidence DESC, last_used_at DESC"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def get_pattern_by_text(
        self, *, pattern_kind: str, pattern_text: str,
    ) -> dict | None:
        """Look up a single pattern by its (kind, text) — the natural
        idempotency key for distillation. Returns None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM advisor_memory
                WHERE pattern_kind = ? AND pattern_text = ?
                LIMIT 1
                """,
                (pattern_kind, pattern_text),
            ).fetchone()
        return dict(row) if row else None

    def append_pattern_sources(
        self,
        pattern_id: int,
        new_event_ids: list[int],
        *,
        new_confidence: float | None = None,
    ) -> bool:
        """Merge new source_event_ids into an existing pattern's
        source_events JSON list. Used by distill() when a re-run
        finds events that contributed to an already-known pattern.

        new_confidence (optional): replace the confidence with the
        recomputed value. Pass None to leave it unchanged."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT source_events FROM advisor_memory WHERE id = ?",
                (pattern_id,),
            ).fetchone()
            if row is None:
                return False
            try:
                existing = json.loads(row["source_events"])
                if not isinstance(existing, list):
                    existing = []
            except (json.JSONDecodeError, TypeError):
                existing = []
            merged = sorted(set(existing) | set(new_event_ids))
            if new_confidence is not None:
                conn.execute(
                    """
                    UPDATE advisor_memory
                    SET source_events = ?, confidence = ?
                    WHERE id = ?
                    """,
                    (json.dumps(merged), new_confidence, pattern_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE advisor_memory
                    SET source_events = ?
                    WHERE id = ?
                    """,
                    (json.dumps(merged), pattern_id),
                )
        return True

    def record_pattern_use(self, pattern_ids: list[int]) -> int:
        """Bump use_count + set last_used_at for each cited pattern.
        Called by the advisor when patterns get folded into a prompt.
        Returns the number of rows updated."""
        if not pattern_ids:
            return 0
        now = _utcnow_iso()
        placeholders = ",".join("?" * len(pattern_ids))
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE advisor_memory
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id IN ({placeholders})
                """,
                (now, *pattern_ids),
            )
            return cur.rowcount
