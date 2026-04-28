#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/council_filter_stats.py — outcome histogram contract.

Phase 5L lets operators answer "what's the breakdown of council outcomes
last week?" by bucketing council_runs.log entries into mutually-exclusive
outcome classes (fired / filtered / skipped / council_errors).

This drill locks the bucketing contract — a future refactor that silently
drops a class or merges two buckets would break operator runbooks.

Eight steps. Six negative assertions.

  1. parse_filter_reason returns canonical names for each Phase-5K
     filter (skip_token / too_short / all_binary / doc_only / etc).
  2. NEGATIVE: parse_filter_reason returns 'legacy' for the pre-5K
     'filtered: payload_lines=...' format. Backward-compat is the
     contract for old log entries — without it, history vanishes.
  3. NEGATIVE: too_short with payload tail is normalized to
     'too_short' (no payload-count splintering across buckets).
  4. NEGATIVE: total = sum of all 4 outcome classes + council_errors.
     Every entry must land in EXACTLY ONE class — no double-counting,
     no silent drops. This is the invariant operators rely on.
  5. NEGATIVE: --days N filter excludes entries outside the window.
     Without this, weekly reports include all-time data.
  6. NEGATIVE: malformed JSON line is skipped (not crash). Council
     log is append-only from multiple processes; partial writes
     are possible during a crash.
  7. NEGATIVE: missing log file produces total=0, no crash. Pre-
     bootstrap state is valid.
  8. NEGATIVE: bad timestamp on an entry doesn't drop the entry —
     we keep the data, just can't filter by window. Don't lose data
     because of one malformed field.

Run: python3 mcp/tests/drill_council_filter_stats.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_drill_5L", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5L"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_log(tmpdir: Path, entries: list[dict]) -> Path:
    """Write entries one-JSON-per-line into a temp file (the council_runs.log shape)."""
    p = tmpdir / "council_runs.log"
    with p.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return p


def _ts(offset_minutes: int = 0) -> str:
    """Build an ISO timestamp `offset_minutes` ago (negative = past)."""
    t = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return t.isoformat(timespec="seconds")


def main() -> int:
    stats = _load_stats()

    # ── Step 1: canonical filter names ──
    cases = [
        ("filtered: skip_token (payload=200, files=3, binary=False)", "skip_token"),
        ("filtered: all_binary (payload=20, files=2, binary=True)", "all_binary"),
        ("filtered: doc_only (payload=80, files=3, binary=False)", "doc_only"),
        ("filtered: empty_diff (payload=0, files=0, binary=False)", "empty_diff"),
        ("filtered: capture_error (payload=0, files=0, binary=False)", "capture_error"),
    ]
    for reason, expected in cases:
        got = stats.parse_filter_reason(reason)
        if got != expected:
            print(f"✗ step 1: {reason!r} → {got!r}, expected {expected!r}")
            return 1
    print(f"✓ step 1: {len(cases)} canonical filter names parsed correctly")

    # ── Step 2: NEGATIVE — pre-5K legacy format ──
    legacy = "filtered: payload_lines=242, files=3, binary=True"
    got = stats.parse_filter_reason(legacy)
    if got != "legacy":
        print(f"✗ step 2: legacy format → {got!r}, expected 'legacy'. "
              "History from before Phase 5K won't render correctly.")
        return 1
    print("✓ step 2: pre-5K format buckets as 'legacy' (history preserved)")

    # ── Step 3: NEGATIVE — too_short with payload tail normalized ──
    variants = [
        "filtered: too_short (payload=2, files=1, binary=False)",
        "filtered: too_short (payload=4, files=2, binary=False)",
        "filtered: too_short (payload=0, files=0, binary=False)",
    ]
    for reason in variants:
        got = stats.parse_filter_reason(reason)
        if got != "too_short":
            print(f"✗ step 3: {reason!r} → {got!r}, expected 'too_short'. "
                  "Different payload counts creating different buckets "
                  "would splinter the histogram.")
            return 1
    print(f"✓ step 3: {len(variants)} too_short variants all normalize to one bucket")

    # ── Step 4: NEGATIVE — every entry in exactly one class ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            # fired (3 normal completions)
            {"timestamp": _ts(0), "fired": True, "filtered": False,
             "reason": "council_completed risk=MEDIUM", "risk_level": "MEDIUM"},
            {"timestamp": _ts(0), "fired": True, "filtered": False,
             "reason": "council_completed risk=LOW", "risk_level": "LOW"},
            {"timestamp": _ts(0), "fired": True, "filtered": False,
             "reason": "council_completed risk=HIGH", "risk_level": "HIGH"},
            # filtered (2)
            {"timestamp": _ts(0), "fired": False, "filtered": True,
             "reason": "filtered: skip_token (payload=200, files=3, binary=False)"},
            {"timestamp": _ts(0), "fired": False, "filtered": True,
             "reason": "filtered: doc_only (payload=80, files=3, binary=False)"},
            # skipped (2 — operator opt-out paths)
            {"timestamp": _ts(0), "fired": False, "filtered": False,
             "reason": "no_council requested"},
            {"timestamp": _ts(0), "fired": False, "filtered": False,
             "reason": "no advisor wired"},
            # council_error (1)
            {"timestamp": _ts(0), "fired": True, "filtered": False,
             "reason": "council_error: ImportError"},
        ]
        log_path = _write_log(tmpdir, entries)
        s = stats.summarize(log_path, days=None)
        fired_total = sum(s["fired_by_risk"].values())
        filtered_total = sum(s["filtered_by_reason"].values())
        skipped_total = sum(s["skipped_by_reason"].values())
        accounted = fired_total + filtered_total + skipped_total + s["council_errors"]
        if s["total"] != len(entries):
            print(f"✗ step 4: total={s['total']}, expected {len(entries)}")
            return 1
        if accounted != s["total"]:
            print(f"✗ step 4: accounted={accounted} != total={s['total']}. "
                  f"fired={fired_total}, filtered={filtered_total}, "
                  f"skipped={skipped_total}, errors={s['council_errors']}. "
                  "An entry was double-counted or silently dropped.")
            return 1
        # Specific bucket checks: 3 risks, 2 filters, 2 skip kinds, 1 error
        if fired_total != 3 or filtered_total != 2 or skipped_total != 2 \
                or s["council_errors"] != 1:
            print(f"✗ step 4: bucket counts wrong. fired={fired_total} (want 3), "
                  f"filtered={filtered_total} (want 2), "
                  f"skipped={skipped_total} (want 2), "
                  f"errors={s['council_errors']} (want 1)")
            return 1
        print(f"✓ step 4: {len(entries)} entries → "
              f"{fired_total} fired + {filtered_total} filtered + "
              f"{skipped_total} skipped + {s['council_errors']} errors "
              f"(every entry in exactly one class)")

    # ── Step 5: NEGATIVE — --days window excludes old entries ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            # 10 days ago (outside 7d window)
            {"timestamp": _ts(-10 * 24 * 60), "fired": True, "filtered": False,
             "reason": "council_completed risk=MEDIUM", "risk_level": "MEDIUM"},
            # 1 day ago (inside)
            {"timestamp": _ts(-24 * 60), "fired": True, "filtered": False,
             "reason": "council_completed risk=LOW", "risk_level": "LOW"},
        ]
        log_path = _write_log(tmpdir, entries)
        s_all = stats.summarize(log_path, days=None)
        s_7d = stats.summarize(log_path, days=7)
        if s_all["total"] != 2:
            print(f"✗ step 5: all-time total={s_all['total']}, expected 2")
            return 1
        if s_7d["total"] != 1:
            print(f"✗ step 5: --days 7 total={s_7d['total']}, expected 1. "
                  "Window filter not excluding the 10-day-old entry.")
            return 1
        print("✓ step 5: --days N excludes entries outside the window")

    # ── Step 6: NEGATIVE — malformed JSON line is skipped ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "council_runs.log"
        log_path.write_text(
            json.dumps({"timestamp": _ts(0), "fired": True, "filtered": False,
                        "reason": "council_completed risk=LOW",
                        "risk_level": "LOW"}) + "\n"
            + "{this is not json\n"   # malformed line
            + json.dumps({"timestamp": _ts(0), "fired": False, "filtered": True,
                          "reason": "filtered: skip_token (payload=200, files=3)"})
            + "\n"
        )
        try:
            s = stats.summarize(log_path, days=None)
        except Exception as exc:
            print(f"✗ step 6: malformed JSON crashed summarize: "
                  f"{type(exc).__name__}: {exc}")
            return 1
        if s["total"] != 2:
            print(f"✗ step 6: total={s['total']}, expected 2 "
                  "(2 valid lines, 1 malformed skipped)")
            return 1
        print("✓ step 6: malformed JSON line skipped, neighbors counted (2/2 valid)")

    # ── Step 7: NEGATIVE — missing log file is safe ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        missing = tmpdir / "does-not-exist.log"
        try:
            s = stats.summarize(missing, days=None)
        except Exception as exc:
            print(f"✗ step 7: missing file crashed: "
                  f"{type(exc).__name__}: {exc}")
            return 1
        if s["total"] != 0:
            print(f"✗ step 7: missing file total={s['total']}, expected 0")
            return 1
        print("✓ step 7: missing log file → total=0, no crash (pre-bootstrap state)")

    # ── Step 8: NEGATIVE — bad timestamp doesn't drop the entry ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            {"timestamp": "not-a-real-timestamp", "fired": True,
             "filtered": False, "reason": "council_completed risk=MEDIUM",
             "risk_level": "MEDIUM"},
            {"timestamp": _ts(0), "fired": True, "filtered": False,
             "reason": "council_completed risk=LOW", "risk_level": "LOW"},
        ]
        log_path = _write_log(tmpdir, entries)
        # With days=7, the bad-timestamp entry can't be filtered out by
        # window (we can't parse its time), so we INCLUDE it. Don't lose
        # data because of a single malformed field.
        s = stats.summarize(log_path, days=7)
        if s["total"] != 2:
            print(f"✗ step 8: bad-timestamp entry was dropped. total={s['total']}, expected 2. "
                  "Single malformed field shouldn't lose data.")
            return 1
        print("✓ step 8: bad timestamp doesn't drop entry (data preservation)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
