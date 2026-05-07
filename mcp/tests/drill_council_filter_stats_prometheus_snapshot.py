#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: --prometheus --from-snapshot date-keyed exposition (Phase 5W).

Phase 5N writes one daily snapshot row per UTC date to
.loop/council_stats_daily.jsonl. Phase 5W reads that file and emits
prom samples keyed by `date` so Grafana queries can graph multi-month
history WITHOUT re-parsing council_runs.log every scrape — and the
data survives even if council_runs.log gets rotated.

Eight steps. Six negative assertions.

  1. POSITIVE: render_prometheus_snapshots emits per-date samples
     for every metric (total + fired + filtered + skipped + errors).
  2. NEGATIVE: empty snapshot list → HELP+TYPE only, 0 samples
     (scrapable; dashboards don't 404 in pre-bootstrap state).
  3. NEGATIVE: per-date zero-padding for KNOWN_FILTERS + standard
     risks (so date×category Grafana panels stay continuous).
  4. NEGATIVE: dedup-by-date reused from 5N's read_snapshots. If
     two snapshots exist for the same date, only the LATER one
     contributes to the prom output. Without reuse, 5W could
     drift from 5N's contract.
  5. NEGATIVE: --from-snapshot + --weekly rejected at CLI layer
     (mutually exclusive — snapshot is already per-day).
  6. NEGATIVE: --snapshot-source without --from-snapshot prints a
     warning. Operator typo'd a flag that does nothing; we surface
     it instead of silently ignoring.
  7. NEGATIVE: missing snapshot file → empty list → empty output
     (still scrapable). Pre-bootstrap path; cron survives day 1.
  8. POSITIVE: end-to-end via subprocess — write a synthetic
     snapshot file, invoke the script with --prometheus
     --from-snapshot --snapshot-source, verify the rendered output
     contains the expected date-keyed samples.

Run: python3 mcp/tests/drill_council_filter_stats_prometheus_snapshot.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "council_filter_stats.py"


def _load_stats():
    spec = importlib.util.spec_from_file_location("_stats_drill_5W", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5W"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_snapshot(date: str, *, total: int = 0,
                   fired: dict | None = None,
                   filtered: dict | None = None,
                   skipped: dict | None = None,
                   errors: int = 0,
                   taken_at: str = "") -> dict:
    return {
        "date": date,
        "iso_week": "",  # unused by the renderer
        "total": total,
        "fired_by_risk": fired or {},
        "filtered_by_reason": filtered or {},
        "skipped_by_reason": skipped or {},
        "council_errors": errors,
        "snapshot_taken_at": taken_at or f"{date}T01:00:00+00:00",
    }


def _write_snapshot_file(tmpdir: Path, snapshots: list[dict]) -> Path:
    p = tmpdir / "council_stats_daily.jsonl"
    with p.open("w") as f:
        for s in snapshots:
            f.write(json.dumps(s) + "\n")
    return p


def main() -> int:
    stats = _load_stats()

    # ── Step 1: POSITIVE — full structure for two days ──
    snaps = [
        _make_snapshot("2026-04-28", total=10, fired={"MEDIUM": 7},
                       filtered={"too_short": 2},
                       skipped={"no_council": 1}),
        _make_snapshot("2026-04-27", total=5, fired={"MEDIUM": 5}),
    ]
    out = stats.render_prometheus_snapshots(snaps)
    required = [
        'council_filter_total{date="2026-04-28"} 10',
        'council_filter_total{date="2026-04-27"} 5',
        'council_filter_fired{date="2026-04-28",risk="MEDIUM"} 7',
        'council_filter_filtered{date="2026-04-28",reason="too_short"} 2',
        'council_filter_skipped{date="2026-04-28",reason="no_council"} 1',
        'council_filter_council_errors{date="2026-04-28"} 0',
        'council_filter_council_errors{date="2026-04-27"} 0',
    ]
    for s in required:
        if s not in out:
            print(f"✗ step 1: missing sample {s!r}\n{out}")
            return 1
    print(f"✓ step 1: per-date samples emitted for {len(required)} expected lines")

    # ── Step 2: NEGATIVE — empty snapshots emits HELP+TYPE only ──
    empty_out = stats.render_prometheus_snapshots([])
    samples = [ln for ln in empty_out.splitlines()
               if ln and not ln.startswith("#")]
    if samples:
        print(f"✗ step 2: empty snapshots produced {len(samples)} samples")
        return 1
    # All 5 metrics' HELP must still be present
    for metric in ("council_filter_total", "council_filter_fired",
                   "council_filter_filtered", "council_filter_skipped",
                   "council_filter_council_errors"):
        if f"# HELP {metric}" not in empty_out:
            print(f"✗ step 2: empty snapshots missing HELP for {metric}")
            return 1
    print("✓ step 2: empty snapshots emits HELP+TYPE only (scrapable, dashboards ok)")

    # ── Step 3: NEGATIVE — per-date zero-padding ──
    snaps = [_make_snapshot("2026-04-28", total=5, fired={"MEDIUM": 5})]
    out = stats.render_prometheus_snapshots(snaps)
    # Every standard risk for this date even at 0
    for risk in ("LOW", "MEDIUM", "HIGH", "UNKNOWN"):
        if f'date="2026-04-28",risk="{risk}"' not in out:
            print(f"✗ step 3: missing zero-pad risk={risk!r}")
            return 1
    # Every KNOWN_FILTERS for this date
    for filt in stats.KNOWN_FILTERS:
        if f'date="2026-04-28",reason="{filt}"' not in out:
            print(f"✗ step 3: missing zero-pad filter={filt!r}")
            return 1
    print(f"✓ step 3: zero-padding per-date for 4 risks + {len(stats.KNOWN_FILTERS)} filters")

    # ── Step 4: NEGATIVE — dedup-by-date reused from 5N ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # Two snapshots for same date — older has total=1, newer has total=99.
        # The CLI loads via _load_read_snapshots() which reuses 5N's logic;
        # only the latest snapshot_taken_at should win.
        snaps_disk = [
            _make_snapshot("2026-04-28", total=1,
                           taken_at="2026-04-29T01:00:00+00:00"),
            _make_snapshot("2026-04-28", total=99,
                           taken_at="2026-04-29T05:00:00+00:00"),
        ]
        snap_path = _write_snapshot_file(tmpdir, snaps_disk)
        # Use the same loader the CLI uses to verify behavior is shared.
        read_snapshots = stats._load_read_snapshots()
        loaded = read_snapshots(snap_path)
        if len(loaded) != 1:
            print(f"✗ step 4: read_snapshots returned {len(loaded)} rows, "
                  "expected 1 (dedup broken)")
            return 1
        if loaded[0]["total"] != 99:
            print(f"✗ step 4: dedup kept total={loaded[0]['total']}, expected 99 "
                  "(latest snapshot_taken_at should win)")
            return 1
        out = stats.render_prometheus_snapshots(loaded)
        if 'council_filter_total{date="2026-04-28"} 99' not in out:
            print("✗ step 4: rendered output didn't reflect deduped row")
            return 1
        print("✓ step 4: dedup-by-date reused from 5N (latest snapshot_taken_at wins)")

    # ── Step 5: NEGATIVE — --from-snapshot + --weekly rejected ──
    rc = subprocess.call(
        [sys.executable, str(SCRIPT),
         "--prometheus", "--from-snapshot", "--weekly"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(REPO),
    )
    if rc != 1:
        print(f"✗ step 5: --from-snapshot + --weekly exit {rc}, expected 1")
        return 1
    print("✓ step 5: --from-snapshot + --weekly rejected with exit 1")

    # ── Step 6: NEGATIVE — orphan --snapshot-source warns ──
    proc = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--prometheus", "--snapshot-source", "/tmp/never-exists.jsonl"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    if proc.returncode != 0:
        print(f"✗ step 6: orphan --snapshot-source exit {proc.returncode}, expected 0")
        return 1
    if "snapshot-source has no effect" not in proc.stderr:
        print(f"✗ step 6: orphan --snapshot-source missing warning. stderr:\n{proc.stderr}")
        return 1
    print("✓ step 6: orphan --snapshot-source emits warning, doesn't silently ignore")

    # ── Step 7: NEGATIVE — missing snapshot file → empty output ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        missing = tmpdir / "no-such.jsonl"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--prometheus", "--from-snapshot",
             "--snapshot-source", str(missing)],
            capture_output=True, text=True, cwd=str(REPO),
        )
        if proc.returncode != 0:
            print(f"✗ step 7: missing snapshot file exit {proc.returncode}, "
                  f"expected 0 (cron-safe). stderr={proc.stderr}")
            return 1
        # Output must still be scrapable (HELP/TYPE blocks)
        if "# HELP council_filter_total" not in proc.stdout:
            print("✗ step 7: missing file output not scrapable")
            return 1
        # No samples
        sample_lines = [ln for ln in proc.stdout.splitlines()
                        if ln and not ln.startswith("#")]
        if sample_lines:
            print(f"✗ step 7: missing file produced {len(sample_lines)} samples, "
                  "expected 0")
            return 1
    print("✓ step 7: missing snapshot file → 0 samples, scrapable, exit 0 (cron-safe)")

    # ── Step 8: POSITIVE — end-to-end via subprocess ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        snaps_disk = [
            _make_snapshot("2026-04-28", total=10, fired={"MEDIUM": 7}),
            _make_snapshot("2026-04-27", total=5, fired={"MEDIUM": 3, "LOW": 2}),
            _make_snapshot("2026-04-26", total=8, fired={"MEDIUM": 5},
                           filtered={"too_short": 3}),
        ]
        snap_path = _write_snapshot_file(tmpdir, snaps_disk)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--prometheus", "--from-snapshot",
             "--snapshot-source", str(snap_path)],
            capture_output=True, text=True, cwd=str(REPO),
        )
        if proc.returncode != 0:
            print(f"✗ step 8: end-to-end exit {proc.returncode}: {proc.stderr}")
            return 1
        for sample in [
            'council_filter_total{date="2026-04-28"} 10',
            'council_filter_total{date="2026-04-27"} 5',
            'council_filter_total{date="2026-04-26"} 8',
            'council_filter_fired{date="2026-04-27",risk="LOW"} 2',
            'council_filter_filtered{date="2026-04-26",reason="too_short"} 3',
        ]:
            if sample not in proc.stdout:
                print(f"✗ step 8: missing sample {sample!r}\n{proc.stdout}")
                return 1
        print("✓ step 8: end-to-end via subprocess produced expected 3-day output")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
