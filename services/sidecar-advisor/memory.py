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
from datetime import UTC, datetime, timedelta
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class AdvisorMemory:
    """Thin SQLite wrapper. Pure synchronous — Phase 1 caller is
    a Next.js BFF endpoint or a CLI; the volume is one event per user paste,
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

    def rate_event(
        self,
        event_id: int,
        rating: str,
        *,
        rated_by: str | None = None,
        rating_notes: str | None = None,
    ) -> bool:
        """Set the user_rating on an event. Returns True if a row was
        updated. Rating must be 'useful' or 'not_useful' — the column
        is text-typed but the caller is required to enforce the enum."""
        if rating not in ("useful", "not_useful"):
            raise ValueError(
                f"rating must be 'useful' or 'not_useful', got {rating!r}"
            )
        actor = rated_by.strip()[:120] if rated_by and rated_by.strip() else None
        notes = (
            rating_notes.strip()[:2000]
            if rating_notes and rating_notes.strip()
            else None
        )
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE advisor_events
                SET user_rating = ?, rated_at = ?, rated_by = ?, rating_notes = ?
                WHERE id = ?
                """,
                (rating, _utcnow_iso(), actor, notes, event_id),
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

    # ── Council audit rows (Phase 2E) ───────────────────────────
    def record_council_run(
        self,
        *,
        event_id: int | None,
        telemetry: dict,
    ) -> int:
        """Persist the council telemetry from a pr_review invocation.

        Args:
            event_id: the advisor_events.id for the user-visible
                summary, or None for council runs without a parent
                (operator-triggered backfills, future replay tooling).
            telemetry: the raw_board dict produced by
                PrReviewCouncil.review — must contain the keys this
                method reads (outcome, prompt_version, duration_s,
                drafts, reviews, failed_authors, advisor_error).
                Missing keys default to safe sentinels rather than
                raise — the audit row should land even if telemetry
                is partial.

        Returns:
            The advisor_council_runs.id of the inserted row.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO advisor_council_runs (
                    event_id, created_at, outcome, advisor_id,
                    prompt_version, duration_s, advisor_error,
                    failed_authors, drafts_json, reviews_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    _utcnow_iso(),
                    str(telemetry.get("outcome", "unknown")),
                    str(telemetry.get("advisor_id", "")),
                    str(telemetry.get("prompt_version", "")),
                    float(telemetry.get("duration_s", 0.0)),
                    telemetry.get("advisor_error"),
                    json.dumps(telemetry.get("failed_authors", [])),
                    json.dumps(telemetry.get("drafts", [])),
                    json.dumps(telemetry.get("reviews", [])),
                ),
            )
            return cur.lastrowid or 0

    def get_council_runs(
        self,
        *,
        event_id: int | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Read council audit rows. Optional filters by event_id (the
        natural join) or outcome (for the dashboard's failure-mode
        filter)."""
        sql = "SELECT * FROM advisor_council_runs"
        clauses: list[str] = []
        params: list = []
        if event_id is not None:
            clauses.append("event_id = ?")
            params.append(event_id)
        if outcome is not None:
            clauses.append("outcome = ?")
            params.append(outcome)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_event_advisor_output(
        self,
        event_id: int,
        *,
        advisor_output: dict | None,
        model_used: str | None = None,
        duration_s: float | None = None,
    ) -> bool:
        """Backfill the advisor_output / model_used / duration_s on an
        event row that was recorded BEFORE the council fired.

        capture_and_review's contract: record the event with
        advisor_output=None up-front (so the audit row exists even
        if the council crashes), then update with the council's
        result if it succeeds. Without this method the event row
        stays advisor_output=None forever and the dashboard can't
        show the summary.
        """
        sets: list[str] = []
        params: list = []
        if advisor_output is not None:
            sets.append("advisor_output = ?")
            params.append(json.dumps(advisor_output))
        if model_used is not None:
            sets.append("model_used = ?")
            params.append(model_used)
        if duration_s is not None:
            sets.append("duration_s = ?")
            params.append(duration_s)
        if not sets:
            return False
        params.append(event_id)
        with self._connect() as conn:
            # S608 false-positive: `sets` contains LITERAL column-
            # assignment strings built above from hardcoded column
            # names ("advisor_output = ?", "model_used = ?",
            # "duration_s = ?"). All values are bound via `params`.
            # No user input reaches the f-string.
            cur = conn.execute(
                f"UPDATE advisor_events SET {', '.join(sets)} "  # noqa: S608
                f"WHERE id = ?",
                params,
            )
            return cur.rowcount > 0

    def find_events_without_council_run(
        self,
        *,
        event_type: str = "pr_review",
        limit: int = 50,
    ) -> list[dict]:
        """Events that have no corresponding advisor_council_runs row.

        Used by the batched-replay flow: events captured via Phase 2A2
        with --no-council mode (or with a chair-error fallback) need
        the council fired against them later. This query is the
        worklist.

        Args:
            event_type: only return events of this type. Default
                "pr_review" - the only event_type the council
                processes.
            limit: cap on rows returned. Default 50 - one batch
                worth of work without overwhelming the LLM provider.

        Returns: list of event row dicts in oldest-first order so
        the operator can FIFO-process the backlog.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.* FROM advisor_events e
                LEFT JOIN advisor_council_runs c ON c.event_id = e.id
                WHERE e.event_type = ?
                  AND c.id IS NULL
                ORDER BY e.created_at ASC
                LIMIT ?
                """,
                (event_type, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def prune_council_runs(
        self,
        *,
        older_than_days: int = 90,
        dry_run: bool = True,
    ) -> dict:
        """Delete advisor_council_runs rows older than N days.

        The drafts_json + reviews_json columns can be 10-50 KB
        each; without retention the table grows unbounded. This
        method is the operator-controlled prune.

        Args:
            older_than_days: rows with created_at < (now - N days)
                are eligible for deletion. Default 90 - 3 months
                of council telemetry is enough for most forensic
                lookups; older data lives in cold archives or
                git's commit history.
            dry_run: when True (default), counts what WOULD be
                deleted but doesn't actually delete. Operator
                runs with dry_run=False to apply.

        Returns: {
            "would_delete": N if dry_run else 0,
            "deleted": N if not dry_run else 0,
            "kept": M,
            "threshold_iso": "2026-01-28T...",
            "dry_run": bool,
        }

        Companion advisor_events rows are NOT pruned by this
        method - they're cheap (small KB each), preserve the
        "we reviewed X commits at time Y" audit trail, and
        Phase 2F+ can add a separate event-retention if needed.
        """
        if older_than_days < 0:
            raise ValueError(
                f"older_than_days must be >= 0, got {older_than_days}"
            )
        threshold_dt = datetime.now(UTC) - timedelta(days=older_than_days)
        threshold_iso = threshold_dt.isoformat(timespec="seconds")

        with self._connect() as conn:
            # Count by partition (older / newer-or-equal)
            cur = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_council_runs "
                "WHERE created_at < ?",
                (threshold_iso,),
            )
            to_delete = int(cur.fetchone()["n"])
            cur = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_council_runs "
                "WHERE created_at >= ?",
                (threshold_iso,),
            )
            to_keep = int(cur.fetchone()["n"])

            if not dry_run and to_delete > 0:
                conn.execute(
                    "DELETE FROM advisor_council_runs "
                    "WHERE created_at < ?",
                    (threshold_iso,),
                )

        return {
            "would_delete": to_delete if dry_run else 0,
            "deleted": to_delete if not dry_run else 0,
            "kept": to_keep,
            "threshold_iso": threshold_iso,
            "older_than_days": older_than_days,
            "dry_run": dry_run,
        }

    def record_pattern_use(self, pattern_ids: list[int]) -> int:
        """Bump use_count + set last_used_at for each cited pattern.
        Called by the advisor when patterns get folded into a prompt.
        Returns the number of rows updated."""
        if not pattern_ids:
            return 0
        now = _utcnow_iso()
        # `placeholders` is a string of literal `?` separators (e.g.
        # "?,?,?"). All actual pattern_id values are parameter-bound
        # via the tuple. Canonical safe IN-list pattern.
        placeholders = ",".join("?" * len(pattern_ids))
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE advisor_memory
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id IN ({placeholders})
                """,  # noqa: S608 — placeholders is literal "?" string; values parameterized
                (now, *pattern_ids),
            )
            return cur.rowcount
