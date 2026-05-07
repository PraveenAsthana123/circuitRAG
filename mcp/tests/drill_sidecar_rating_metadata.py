#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: sidecar rating metadata migration + persistence.

Locks the Phase 1B-2 extension that adds rated_by + rating_notes to
advisor_events and verifies the Python memory layer persists them.

Two negative assertions cover: (1) the migration adds both columns
to advisor_events with the correct types, and (2) the memory layer
round-trips a rate_event call so rated_by + rating_notes survive
to the next read. Without these, the rating metadata is dropped
on persistence — operator-invisible regression.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDECAR = REPO / "services" / "sidecar-advisor"


def _load(name: str, rel: str):
    path = SIDECAR / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


memory_mod = _load("sidecar_memory_rating_metadata", "memory.py")
AdvisorMemory = memory_mod.AdvisorMemory


def fail(msg: str) -> None:
    print(f"x {msg}")
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"ok {msg}")


def main() -> None:
    # NEGATIVE: rating metadata columns must exist + round-trip; missing
    # either is silent state loss.
    tmp = tempfile.NamedTemporaryFile(prefix="advisor-rating-meta-", suffix=".db", delete=False)  # noqa: SIM115 (closed on next line)
    tmp.close()
    mem = AdvisorMemory(tmp.name)

    with sqlite3.connect(tmp.name) as conn:
      cols = {row[1] for row in conn.execute("PRAGMA table_info(advisor_events)").fetchall()}
    for col in ("rated_by", "rating_notes"):
        if col not in cols:
            fail(f"advisor_events missing {col}")
    ok("migration adds rated_by + rating_notes")

    event_id = mem.record_event(
        event_type="prompt",
        source="manual",
        content="metadata test",
        model_used="stub-model",
        advisor_output={"summary": "ok"},
        duration_s=0.01,
    )
    if not mem.rate_event(
        event_id,
        "useful",
        rated_by="praveen",
        rating_notes="kept the scope tight",
    ):
        fail("rate_event should update the inserted row")

    row = next((event for event in mem.recent_events(limit=5) if event["id"] == event_id), None)
    if row is None:
        fail("rated row missing from recent_events")
    if row["rated_by"] != "praveen":
        fail(f"rated_by mismatch: {row['rated_by']!r}")
    if row["rating_notes"] != "kept the scope tight":
        fail(f"rating_notes mismatch: {row['rating_notes']!r}")
    ok("memory layer persists rating metadata")

    print("ALL 2 SIDECAR-RATING-METADATA STEPS PASSED")


if __name__ == "__main__":
    main()
