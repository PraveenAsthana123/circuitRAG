#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: best_config_history reader Stage-1 (per §38 + §43 + §51).

Locks the audit-trail projection contract. Operators read this to
answer "what was promoted/rejected over the last N days, and why?"

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
READER = REPO / "scripts" / "best_config_history.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def _make_history(tmp: Path, rows: list[dict]) -> Path:
    p = tmp / "history.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def main() -> int:
    print("-- 1. POSITIVE: reader.py exists + non-trivial --")
    if not READER.exists():
        print(f"x {READER} missing")
        return 1
    src = READER.read_text(encoding="utf-8")
    if len(src) < 3000:
        print(f"x reader too short ({len(src)} chars)")
        return 1
    print(f"  ok: reader present ({len(src)} chars)")

    print("-- 2. POSITIVE: 6 contract surfaces present --")
    os.environ["BEST_CONFIG_HISTORY_ENABLED"] = "1"
    mod, spec = _load_module(READER)
    for name in ("load_history", "summarize", "latest",
                 "is_available", "status", "HistorySummary"):
        if not hasattr(mod, name):
            print(f"x best_config_history.{name} missing")
            return 1
    print("  ok: 6 surfaces present")

    print("-- 3. NEGATIVE: missing file → empty list (§47 fail-safe) --")
    rows = mod.load_history(path="/nonexistent/path.jsonl")
    if rows != []:
        print(f"x missing file must yield []; got {rows!r}")
        return 1
    summary = mod.summarize(rows)
    if summary.total_attempts != 0:
        print(f"x empty rows → 0 attempts; got {summary.total_attempts}")
        return 1
    print("  ok: missing file safe-defaults to empty")

    print("-- 4. NEGATIVE: malformed JSON line → SKIPPED, not raised --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        bad = tmp_p / "history.jsonl"
        bad.write_text(
            json.dumps({"promoted": True, "decided_at_ts": time.time()}) + "\n"
            "not-json-{{{\n"
            + json.dumps({"promoted": False, "reason": "rejected — pass_rate", "decided_at_ts": time.time()}) + "\n",
            encoding="utf-8",
        )
        rows = mod.load_history(path=str(bad))
        if len(rows) != 2:
            print(f"x malformed line should be skipped; expected 2 valid rows, got {len(rows)}")
            return 1
    print("  ok: malformed JSON line skipped; valid rows preserved")

    print("-- 5. NEGATIVE: window cutoff REJECTS old rows --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        # 2 rows: one inside window, one 30d old
        now = time.time()
        rows_data = [
            {"promoted": True, "decided_at_ts": now, "reason": "promoted"},
            {"promoted": True, "decided_at_ts": now - 30 * 86400, "reason": "promoted"},
        ]
        hp = _make_history(tmp_p, rows_data)
        rows = mod.load_history(path=str(hp))
        # Window 7 days → should only count 1
        s = mod.summarize(rows, days=7)
        if s.total_attempts != 1:
            print(f"x 7d window must include only 1 row; got {s.total_attempts}")
            return 1
        # Window negative → all rows
        s_all = mod.summarize(rows, days=-1)
        if s_all.total_attempts != 2:
            print(f"x days=-1 must include all rows; got {s_all.total_attempts}")
            return 1
    print("  ok: window cutoff filters correctly")

    print("-- 6. NEGATIVE: gates_failed_counts aggregate by GATE TYPE not raw text --")
    # Two different rejections both due to pass_rate (different actual
    # values) MUST aggregate under the same key 'pass_rate'.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        now = time.time()
        rows_data = [
            {
                "promoted": False,
                "reason": "rejected — gates failed: pass_rate=0.3 < min=0.5",
                "decided_at_ts": now,
                "gates_failed": ["pass_rate=0.3 < min=0.5"],
            },
            {
                "promoted": False,
                "reason": "rejected — gates failed: pass_rate=0.4 < min=0.5",
                "decided_at_ts": now,
                "gates_failed": ["pass_rate=0.4 < min=0.5"],
            },
            {
                "promoted": False,
                "reason": "rejected — gates failed: margin=0.01 < min=0.05",
                "decided_at_ts": now,
                "gates_failed": ["margin=0.01 < min=0.05"],
            },
        ]
        hp = _make_history(tmp_p, rows_data)
        rows = mod.load_history(path=str(hp))
        s = mod.summarize(rows, days=7)
        if s.gates_failed_counts.get("pass_rate") != 2:
            print(f"x pass_rate must aggregate to 2; got {s.gates_failed_counts}")
            return 1
        if s.gates_failed_counts.get("margin") != 1:
            print(f"x margin must aggregate to 1; got {s.gates_failed_counts}")
            return 1
    print("  ok: gate-type aggregation correct")

    print("-- 7. NEGATIVE: latest() returns the row with HIGHEST decided_at_ts --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        now = time.time()
        rows_data = [
            {"id": "old", "decided_at_ts": now - 100, "promoted": False},
            {"id": "newest", "decided_at_ts": now, "promoted": True},
            {"id": "middle", "decided_at_ts": now - 50, "promoted": True},
        ]
        hp = _make_history(tmp_p, rows_data)
        rows = mod.load_history(path=str(hp))
        latest_row = mod.latest(rows)
        if latest_row is None or latest_row.get("id") != "newest":
            print(f"x latest() must return newest by ts; got {latest_row}")
            return 1
        # latest of empty list = None
        if mod.latest([]) is not None:
            print("x latest([]) must return None")
            return 1
    print("  ok: latest() picks max decided_at_ts; empty → None")

    print("-- 8. NEGATIVE: classification — skipped vs rejected disambiguated --")
    # 'skipped' and 'rejected' are different states; the gate's
    # contract is: skipped when env unset / file missing / no rows;
    # rejected when gates fail. The reader MUST distinguish.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        now = time.time()
        rows_data = [
            {"promoted": False, "reason": "skipped — disabled", "decided_at_ts": now},
            {"promoted": False, "reason": "rejected — gates failed", "decided_at_ts": now,
             "gates_failed": ["pass_rate=0.3"]},
            {"promoted": True, "reason": "promoted — all gates passed", "decided_at_ts": now},
        ]
        hp = _make_history(tmp_p, rows_data)
        rows = mod.load_history(path=str(hp))
        s = mod.summarize(rows, days=7)
        if s.promoted != 1 or s.rejected != 1 or s.skipped != 1:
            print(f"x classification wrong: promoted={s.promoted} rejected={s.rejected} skipped={s.skipped}")
            return 1
    print("  ok: skipped/rejected/promoted classification distinct")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
