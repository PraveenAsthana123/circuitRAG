#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: --prometheus + --weekly per-week labels (Phase 5V).

Phase 5U emitted single-window prom samples. Phase 5V adds a `week`
label dimension so Grafana can graph filter rates per ISO week
natively. Metric NAMES are unchanged — operators roll up across
weeks with `sum without (week) (council_filter_filtered)`.

Eight steps. Six negative assertions.

  1. POSITIVE: render_prometheus_weekly emits one sample per
     (week, bucket) tuple for every metric.
  2. NEGATIVE: same metric NAMES as single-window output. A
     dashboard switched between modes shouldn't have to rename
     anything; only the label dimension changes. (Drill checks
     for council_filter_total / _fired / _filtered / _skipped
     / _council_errors.)
  3. NEGATIVE: zero-padding happens PER WEEK that has entries.
     A week with at least one entry must emit zeros for missing
     KNOWN_FILTERS / standard risks. Without this, week-over-
     week Grafana panels would have gaps.
  4. NEGATIVE: weeks with NO entries don't appear at all. Phantom
     padding past the data range would produce false zeros in
     trend graphs.
  5. NEGATIVE: 'unparseable' rows surface as week="unparseable"
     samples — visible to operators (so they can fix upstream)
     but distinct from real ISO weeks.
  6. NEGATIVE: empty weekly (no rows) emits HELP + TYPE only,
     no samples. Still scrapable; dashboards don't 404.
  7. NEGATIVE: every non-comment line matches the prom sample
     regex with the new `week` label included.
  8. POSITIVE: end-to-end via summarize_by_week → render_prometheus_weekly
     on multiple weeks of data verifies all metrics appear with
     correct counts.

Run: python3 mcp/tests/drill_council_filter_stats_prometheus_weekly.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_drill_5V", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5V"] = mod
    spec.loader.exec_module(mod)
    return mod


def _entry(timestamp: str, *, fired: bool = True, filtered: bool = False,
           reason: str = "council_completed risk=MEDIUM",
           risk_level: str = "MEDIUM") -> dict:
    return {"timestamp": timestamp, "fired": fired, "filtered": filtered,
            "reason": reason, "risk_level": risk_level}


def _write_log(tmpdir: Path, entries: list[dict]) -> Path:
    p = tmpdir / "council_runs.log"
    with p.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return p


def main() -> int:
    stats = _load_stats()

    # ── Step 1: POSITIVE — full structure for two-week data ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            _entry("2026-04-22T10:00:00+00:00"),  # 2026-W17 fired MEDIUM
            _entry("2026-04-28T10:00:00+00:00"),  # 2026-W18 fired MEDIUM
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        out = stats.render_prometheus_weekly(weekly)
        if "council_filter_total" not in out:
            print("✗ step 1: missing council_filter_total")
            return 1
        # Both weeks must have a total sample
        if 'council_filter_total{week="2026-W17"} 1' not in out:
            print("✗ step 1: missing W17 total")
            return 1
        if 'council_filter_total{week="2026-W18"} 1' not in out:
            print("✗ step 1: missing W18 total")
            return 1
        print("✓ step 1: per-week samples emitted for total + each metric")

    # ── Step 2: NEGATIVE — same metric names as single-window ──
    # The test: build a single-window summary and a weekly summary
    # from the same data; the metric NAMES (the part before `{`)
    # must match between render_prometheus and render_prometheus_weekly.
    s = {"total": 5, "fired_by_risk": {"MEDIUM": 5},
         "filtered_by_reason": {}, "skipped_by_reason": {},
         "council_errors": 0}
    single = stats.render_prometheus(s)
    weekly_for_compat = {"rows": [{"week": "2026-W18", **s,
                                    "fired": 5, "filtered": 0,
                                    "skipped": 0, "errors": 0}],
                         "weeks_window": None}
    week = stats.render_prometheus_weekly(weekly_for_compat)
    # Extract metric names from each output
    name_re = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)(?:\{|\s)', re.MULTILINE)
    single_names = set(name_re.findall(single))
    week_names = set(name_re.findall(week))
    if not single_names <= week_names:
        missing = single_names - week_names
        print(f"✗ step 2: weekly missing metrics from single: {missing}")
        return 1
    if not week_names <= single_names:
        extra = week_names - single_names
        print(f"✗ step 2: weekly has metric not in single: {extra} "
              "(metric names must match for sum-without rollups)")
        return 1
    print(f"✓ step 2: {len(single_names)} metric names match between modes")

    # ── Step 3: NEGATIVE — zero-padding PER WEEK ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # One week with only MEDIUM entries
        entries = [
            _entry("2026-04-28T10:00:00+00:00"),
            _entry("2026-04-28T11:00:00+00:00"),
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        out = stats.render_prometheus_weekly(weekly)
        # Every standard risk must appear FOR THIS WEEK even at 0
        for risk in ("LOW", "MEDIUM", "HIGH", "UNKNOWN"):
            if f'week="2026-W18",risk="{risk}"' not in out:
                print(f"✗ step 3: W18 missing risk={risk!r} (zero-pad failed)")
                return 1
        # Every KNOWN_FILTERS bucket must appear for this week even at 0
        for filt in stats.KNOWN_FILTERS:
            if f'week="2026-W18",reason="{filt}"' not in out:
                print(f"✗ step 3: W18 missing filter={filt!r}")
                return 1
        print(f"✓ step 3: all 4 risks + {len(stats.KNOWN_FILTERS)} filters "
              "zero-padded for W18")

    # ── Step 4: NEGATIVE — weeks with no entries don't phantom-pad ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # Only W18 has entries
        entries = [_entry("2026-04-28T10:00:00+00:00")]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        out = stats.render_prometheus_weekly(weekly)
        # No phantom W17 / W16 / earlier weeks
        for ghost in ("2026-W17", "2026-W16", "2025-W52", "2026-W19"):
            if f'week="{ghost}"' in out:
                print(f"✗ step 4: phantom week {ghost!r} appeared in output")
                return 1
        print("✓ step 4: only weeks with data appear (no phantom padding)")

    # ── Step 5: NEGATIVE — unparseable timestamps surface ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            _entry("2026-04-28T10:00:00+00:00"),
            _entry("not-a-timestamp"),
            _entry(""),
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        out = stats.render_prometheus_weekly(weekly)
        if 'week="unparseable"' not in out:
            print("✗ step 5: unparseable bucket missing from prom output")
            return 1
        if 'council_filter_total{week="unparseable"} 2' not in out:
            print("✗ step 5: unparseable count wrong (expected 2)")
            return 1
        print("✓ step 5: unparseable surfaces as week=\"unparseable\" (count=2)")

    # ── Step 6: NEGATIVE — empty weekly emits HELP+TYPE only ──
    empty = {"rows": [], "weeks_window": None}
    out = stats.render_prometheus_weekly(empty)
    # Must include HELP and TYPE for each metric so dashboards
    # don't 404 in pre-bootstrap state
    for metric in ("council_filter_total", "council_filter_fired",
                   "council_filter_filtered", "council_filter_skipped",
                   "council_filter_council_errors"):
        if f"# HELP {metric}" not in out:
            print(f"✗ step 6: empty output missing HELP for {metric}")
            return 1
    # And no sample lines (sample = non-comment, non-empty)
    samples = [ln for ln in out.splitlines()
               if ln and not ln.startswith("#")]
    if samples:
        print(f"✗ step 6: empty weekly produced {len(samples)} samples, "
              f"expected 0: {samples}")
        return 1
    print("✓ step 6: empty weekly = HELP+TYPE only, 0 samples (scrapable)")

    # ── Step 7: NEGATIVE — every non-comment line is valid ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            _entry("2026-04-28T10:00:00+00:00"),
            _entry("2026-04-22T10:00:00+00:00", risk_level="LOW"),
            _entry("2026-04-22T11:00:00+00:00", fired=False, filtered=True,
                   reason="filtered: too_short (payload=2, files=1)"),
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        out = stats.render_prometheus_weekly(weekly)
        sample_re = re.compile(
            r'^[a-zA-Z_][a-zA-Z0-9_]*'
            r'\{[a-zA-Z_][a-zA-Z0-9_]*="[^"]*"(?:,[a-zA-Z_][a-zA-Z0-9_]*="[^"]*")*\}'
            r' \d+(?:\.\d+)?$'
        )
        # council_filter_council_errors uses {week=...} only and is
        # also a valid samples; council_filter_total ditto. Both have
        # at least the `week` label, so they match the regex above.
        for line in out.splitlines():
            if not line or line.startswith("#"):
                continue
            if not sample_re.match(line):
                print(f"✗ step 7: malformed sample line: {line!r}")
                return 1
        print("✓ step 7: every non-comment line matches Prom sample regex")

    # ── Step 8: POSITIVE — end-to-end multi-week ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            # W18: 1 fired MEDIUM, 1 filtered too_short
            _entry("2026-04-28T10:00:00+00:00"),
            _entry("2026-04-28T11:00:00+00:00", fired=False, filtered=True,
                   reason="filtered: too_short (payload=2, files=1)"),
            # W17: 2 fired MEDIUM, 1 fired LOW, 1 council_error
            _entry("2026-04-22T10:00:00+00:00"),
            _entry("2026-04-22T11:00:00+00:00"),
            _entry("2026-04-22T12:00:00+00:00", risk_level="LOW"),
            _entry("2026-04-22T13:00:00+00:00", reason="council_error: ImportError"),
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        out = stats.render_prometheus_weekly(weekly)
        # Verify exact non-zero samples appear
        expected = [
            'council_filter_total{week="2026-W18"} 2',
            'council_filter_total{week="2026-W17"} 4',
            'council_filter_fired{week="2026-W17",risk="MEDIUM"} 2',
            'council_filter_fired{week="2026-W17",risk="LOW"} 1',
            'council_filter_fired{week="2026-W18",risk="MEDIUM"} 1',
            'council_filter_filtered{week="2026-W18",reason="too_short"} 1',
            'council_filter_council_errors{week="2026-W17"} 1',
            'council_filter_council_errors{week="2026-W18"} 0',
        ]
        for sample in expected:
            if sample not in out:
                print(f"✗ step 8: missing sample {sample!r}\n{out}")
                return 1
        print(f"✓ step 8: end-to-end 2-week data → {len(expected)} expected samples present")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
