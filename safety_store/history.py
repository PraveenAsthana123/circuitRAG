"""History + Rollback engine — every change/delete writes to SQLite first.

HARD RULE (codified): no delete or change is allowed unless the OLD
version was first written to ``history_events`` with timestamp, actor,
reason, and rollback_id. Callers MUST go through ``with_history()`` —
direct DB writes bypass the rule.

Tables (created by ``ensure_schema()`` — idempotent):
- history_events:    every snapshot (create/update/delete)
- rollback_points:   redundant index of rollback_ids for fast lookup
- audit_events:      who did what (actor + approver + reason)
- deleted_items:     soft-deletes (entity_type, entity_id, deleted_at)
- approval_events:   human approval evidence

Schema follows the user's spec literally.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parent / "history.db"
DB_PATH = Path(os.getenv("SAFETY_STORE_DB", str(DEFAULT_DB)))

DEFAULT_ROLLBACK_DAYS = 30


SCHEMA = """
CREATE TABLE IF NOT EXISTS history_events (
    history_id        TEXT PRIMARY KEY,
    entity_type       TEXT NOT NULL,
    entity_id         TEXT NOT NULL,
    action            TEXT NOT NULL,
    old_value_json    TEXT,
    new_value_json    TEXT,
    actor             TEXT NOT NULL,
    approved_by       TEXT,
    reason            TEXT,
    rollback_id       TEXT NOT NULL UNIQUE,
    rollback_allowed  INTEGER NOT NULL DEFAULT 1,
    rollback_until    TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_entity   ON history_events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_history_actor    ON history_events(actor);
CREATE INDEX IF NOT EXISTS idx_history_action   ON history_events(action);

CREATE TABLE IF NOT EXISTS rollback_points (
    rollback_id   TEXT PRIMARY KEY,
    history_id    TEXT NOT NULL UNIQUE,
    used_at       TEXT,
    used_by       TEXT,
    FOREIGN KEY (history_id) REFERENCES history_events(history_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_id    TEXT PRIMARY KEY,
    history_id  TEXT,
    action      TEXT NOT NULL,
    actor       TEXT NOT NULL,
    approver    TEXT,
    reason      TEXT,
    risk_level  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deleted_items (
    entity_type   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    deleted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    history_id    TEXT NOT NULL UNIQUE,
    PRIMARY KEY (entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS approval_events (
    approval_id   TEXT PRIMARY KEY,
    history_id    TEXT,
    approver      TEXT NOT NULL,
    decision      TEXT NOT NULL,
    note          TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@dataclass
class HistoryRecord:
    history_id: str
    entity_type: str
    entity_id: str
    action: str
    old_value: Any
    new_value: Any
    actor: str
    approved_by: str | None
    reason: str | None
    rollback_id: str
    rollback_allowed: bool
    rollback_until: str
    created_at: str


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    c.row_factory = sqlite3.Row
    return c


def ensure_schema() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def save_history(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: Any,
    new_value: Any,
    actor: str,
    reason: str | None = None,
    approved_by: str | None = None,
    rollback_allowed: bool = True,
    rollback_days: int = DEFAULT_ROLLBACK_DAYS,
) -> HistoryRecord:
    """Write one snapshot. ``action`` ∈ {create, update, delete, status_update, ...}.

    Returns the persisted record (including rollback_id). Callers should
    NOT mutate the entity until this function returns successfully.
    """
    if not entity_type or not entity_id or not actor:
        raise ValueError("entity_type, entity_id, actor are required")
    ensure_schema()
    history_id = _new_id("HIST")
    rollback_id = _new_id("RB")
    until = datetime.now(UTC) + timedelta(days=rollback_days)
    record = HistoryRecord(
        history_id=history_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        actor=actor,
        approved_by=approved_by,
        reason=reason,
        rollback_id=rollback_id,
        rollback_allowed=rollback_allowed,
        rollback_until=until.isoformat(timespec="seconds"),
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    with _conn() as c:
        c.execute(
            """
            INSERT INTO history_events
              (history_id, entity_type, entity_id, action,
               old_value_json, new_value_json, actor, approved_by,
               reason, rollback_id, rollback_allowed, rollback_until, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.history_id, record.entity_type, record.entity_id,
                record.action,
                json.dumps(record.old_value) if record.old_value is not None else None,
                json.dumps(record.new_value) if record.new_value is not None else None,
                record.actor, record.approved_by, record.reason,
                record.rollback_id, int(record.rollback_allowed),
                record.rollback_until, record.created_at,
            ),
        )
        c.execute(
            "INSERT INTO rollback_points (rollback_id, history_id) VALUES (?, ?)",
            (record.rollback_id, record.history_id),
        )
        c.execute(
            "INSERT INTO audit_events (audit_id, history_id, action, actor, approver, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_new_id("AUDIT"), record.history_id, action, actor, approved_by, reason),
        )
        if action == "delete":
            c.execute(
                "INSERT INTO deleted_items (entity_type, entity_id, history_id) "
                "VALUES (?, ?, ?)",
                (entity_type, entity_id, record.history_id),
            )
    return record


def list_history(
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    limit: int = 100,
) -> list[HistoryRecord]:
    ensure_schema()
    sql = "SELECT * FROM history_events WHERE 1=1"
    params: list[Any] = []
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        sql += " AND entity_id = ?"
        params.append(entity_id)
    if actor:
        sql += " AND actor = ?"
        params.append(actor)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    out: list[HistoryRecord] = []
    with _conn() as c:
        for row in c.execute(sql, params).fetchall():
            out.append(_row_to_record(row))
    return out


def get_by_rollback_id(rollback_id: str) -> HistoryRecord | None:
    ensure_schema()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM history_events WHERE rollback_id = ?",
            (rollback_id,),
        ).fetchone()
    return _row_to_record(row) if row else None


def _row_to_record(row: sqlite3.Row) -> HistoryRecord:
    return HistoryRecord(
        history_id=row["history_id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        action=row["action"],
        old_value=json.loads(row["old_value_json"]) if row["old_value_json"] else None,
        new_value=json.loads(row["new_value_json"]) if row["new_value_json"] else None,
        actor=row["actor"],
        approved_by=row["approved_by"],
        reason=row["reason"],
        rollback_id=row["rollback_id"],
        rollback_allowed=bool(row["rollback_allowed"]),
        rollback_until=row["rollback_until"],
        created_at=row["created_at"],
    )


class RollbackError(Exception):
    pass


def rollback(rollback_id: str, *, actor: str, note: str | None = None) -> HistoryRecord:
    """Restore the OLD value from the named rollback point.

    Raises:
      RollbackError if the rollback_id is unknown, expired, disallowed,
      or has already been used.

    Side effect: writes a NEW history row with action='rollback', and
    marks the rollback point as used.
    """
    record = get_by_rollback_id(rollback_id)
    if record is None:
        raise RollbackError(f"unknown rollback_id={rollback_id}")
    if not record.rollback_allowed:
        raise RollbackError(f"rollback disallowed for {rollback_id}")
    until = datetime.fromisoformat(record.rollback_until)
    if datetime.now(UTC) > until:
        raise RollbackError(f"rollback expired (until={record.rollback_until})")
    with _conn() as c:
        used = c.execute(
            "SELECT used_at FROM rollback_points WHERE rollback_id = ?",
            (rollback_id,),
        ).fetchone()
        if used and used["used_at"]:
            raise RollbackError(f"rollback {rollback_id} already used at {used['used_at']}")

    # Record the rollback as a NEW history event (audit trail of the
    # rollback itself). The "new_value" of the rollback is the OLD
    # value of the original change.
    new_record = save_history(
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        action="rollback",
        old_value=record.new_value,
        new_value=record.old_value,
        actor=actor,
        reason=note or f"rollback of {rollback_id}",
        approved_by=actor,
        rollback_allowed=False,  # rollbacks are not themselves rollbackable
    )
    with _conn() as c:
        c.execute(
            "UPDATE rollback_points SET used_at = ?, used_by = ? WHERE rollback_id = ?",
            (datetime.now(UTC).isoformat(timespec="seconds"), actor, rollback_id),
        )
    return new_record


# ---------------------------------------------------------------------------
# CRITICAL: forbidden operations
# ---------------------------------------------------------------------------
# History rows MUST NOT be deleted by application code. SQLite has no
# DELETE-protection at the schema level, but we expose ZERO public
# delete function — and we drill against any code path that tries.
# Operators who need to purge for legal reasons do it via the SQLite
# CLI directly, leaving an out-of-band note. There is no API for it.

def with_history(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: Any,
    new_value: Any,
    actor: str,
    reason: str | None = None,
    approved_by: str | None = None,
    apply_fn=None,
):
    """Pre-write history → apply mutation → return (record, apply_result).

    If ``apply_fn`` raises, the history row stays (proves an attempt
    happened) but is marked with new_value=None and a 'failed' tag.
    Rollback points still work because old_value is intact.

    Usage::

        record, _ = with_history(
            entity_type="task", entity_id=t["id"],
            action="status_update",
            old_value={"status": old_status},
            new_value={"status": new_status},
            actor="agent_orchestrator",
            apply_fn=lambda: db.execute("UPDATE ..."),
        )
    """
    record = save_history(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        actor=actor,
        reason=reason,
        approved_by=approved_by,
    )
    if apply_fn is None:
        return record, None
    try:
        result = apply_fn()
    except Exception:
        save_history(
            entity_type=entity_type,
            entity_id=entity_id,
            action=f"{action}.failed",
            old_value=record.new_value,
            new_value=None,
            actor=actor,
            reason="apply_fn raised",
            rollback_allowed=False,
        )
        raise
    return record, result


__all__ = [
    "DEFAULT_ROLLBACK_DAYS",
    "HistoryRecord",
    "RollbackError",
    "ensure_schema",
    "get_by_rollback_id",
    "list_history",
    "rollback",
    "save_history",
    "with_history",
]
