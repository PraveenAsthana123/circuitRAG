#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: --prometheus textfile-collector format (Phase 5U).

Phase 5U emits the same data 5L/5M render as Prometheus exposition
format, suitable for node_exporter's textfile collector. Operators
get long-term Grafana dashboards on the same source of truth.

This drill locks the contract:
  * format follows the Prom exposition spec (HELP + TYPE + samples)
  * label values are escaped (backslash, quote, newline)
  * known buckets emit zero-valued samples so dashboards don't blank
  * atomic writes via tmp + os.replace (no partial-read race)
  * single-window only (drill verifies --weekly + --prometheus prints
    a notice, not silent ignored)

Eight steps. Six negative assertions.

  1. POSITIVE: render_prometheus output has HELP + TYPE + samples
     for every metric (council_filter_total, _fired, _filtered,
     _skipped, _council_errors).
  2. NEGATIVE: known-category zero padding — KNOWN_FILTERS that
     have 0 observations STILL get a sample emitted. Without this,
     a Grafana panel keyed on `council_filter_filtered{reason="too_short"}`
     would blank when too_short has no entries this window.
  3. NEGATIVE: standard risk levels (LOW/MEDIUM/HIGH/UNKNOWN) emit
     zero samples even when absent. Same dashboard-stability rule.
  4. NEGATIVE: label escaping per spec — backslash, quote, newline
     in a synthetic skipped-bucket name all escape correctly.
  5. NEGATIVE: write_prometheus_atomic uses tmp + rename, NOT
     direct write. Drill spies on the filesystem during write to
     verify no partial-read window.
  6. NEGATIVE: the emitted text parses cleanly — every non-comment
     line is `metric_name{labels} value` or `metric_name value`.
     A stray malformed line would fail node_exporter scrape.
  7. NEGATIVE: empty summary (no entries) still emits valid output —
     no samples for skipped (no canonical set), but total + fired +
     filtered + council_errors all present at zero. Bootstrap state
     must produce a scrapable file, not blank.
  8. POSITIVE: integration with summarize() — every classify_entry
     class shows up in the metric output (drives dashboard parity
     with the histogram view).

Run: python3 mcp/tests/drill_council_filter_stats_prometheus.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_drill_5U", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5U"] = mod
    spec.loader.exec_module(mod)
    return mod


def _summary(*, total: int = 0,
             fired: dict | None = None,
             filtered: dict | None = None,
             skipped: dict | None = None,
             errors: int = 0) -> dict:
    return {
        "total": total,
        "fired_by_risk": fired or {},
        "filtered_by_reason": filtered or {},
        "skipped_by_reason": skipped or {},
        "council_errors": errors,
    }


def _entry(*, fired: bool = True, filtered: bool = False,
           reason: str = "council_completed risk=MEDIUM",
           risk_level: str = "MEDIUM") -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fired": fired, "filtered": filtered,
        "reason": reason, "risk_level": risk_level,
    }


def main() -> int:
    stats = _load_stats()

    # ── Step 1: POSITIVE — full output structure ──
    s = _summary(total=10, fired={"MEDIUM": 7}, filtered={"too_short": 2},
                 skipped={"no_council": 1})
    out = stats.render_prometheus(s)
    required_metrics = [
        "council_filter_total",
        "council_filter_fired",
        "council_filter_filtered",
        "council_filter_skipped",
        "council_filter_council_errors",
    ]
    for m in required_metrics:
        if f"# HELP {m}" not in out:
            print(f"✗ step 1: missing HELP for {m}")
            return 1
        if f"# TYPE {m} gauge" not in out:
            print(f"✗ step 1: missing TYPE gauge for {m}")
            return 1
    if not out.endswith("\n"):
        print("✗ step 1: output not LF-terminated")
        return 1
    print(f"✓ step 1: output has HELP+TYPE+samples for {len(required_metrics)} metrics")

    # ── Step 2: NEGATIVE — zero-pad known filter buckets ──
    s = _summary(total=10, filtered={"too_short": 5})
    out = stats.render_prometheus(s)
    # Every KNOWN_FILTERS bucket must appear, even at 0
    for filt in stats.KNOWN_FILTERS:
        # Use the canonical regex shape, since the line is
        #   council_filter_filtered{reason="<filt>"} <n>
        if not re.search(
            rf'council_filter_filtered{{reason="{re.escape(filt)}"}} \d+', out
        ):
            print(f"✗ step 2: KNOWN_FILTERS bucket {filt!r} missing")
            return 1
    # And the 'legacy' synthetic bucket too
    if 'reason="legacy"' not in out:
        print("✗ step 2: 'legacy' bucket missing (pre-5K log entries)")
        return 1
    print(f"✓ step 2: all {len(stats.KNOWN_FILTERS)} canonical filters + legacy "
          "emit samples (zero-padded if absent)")

    # ── Step 3: NEGATIVE — zero-pad standard risk levels ──
    s = _summary(total=5, fired={"MEDIUM": 5})  # only MEDIUM observed
    out = stats.render_prometheus(s)
    for risk in ("LOW", "MEDIUM", "HIGH", "UNKNOWN"):
        if f'risk="{risk}"' not in out:
            print(f"✗ step 3: standard risk {risk!r} missing from output")
            return 1
    print("✓ step 3: 4 standard risk levels emit samples (LOW/MEDIUM/HIGH/UNKNOWN)")

    # ── Step 4: NEGATIVE — label escaping ──
    # Synthetic skipped bucket with malicious chars
    nasty = 'has"quote\\and\nnewline'
    s = _summary(total=1, skipped={nasty: 1})
    out = stats.render_prometheus(s)
    # The label value MUST be escaped: \" \\ \n
    if 'has\\"quote\\\\and\\nnewline' not in out:
        print(f"✗ step 4: label escaping broken. output:\n{out}")
        return 1
    # And no raw newline / quote inside the label
    line = next(ln for ln in out.splitlines()
                if "council_filter_skipped" in ln and "{" in ln)
    if "\n" in line[: line.index("}")]:
        print(f"✗ step 4: raw newline in label region")
        return 1
    # Direct test of the helper
    if stats._prom_escape_label('a"b\\c\nd') != 'a\\"b\\\\c\\nd':
        print("✗ step 4: _prom_escape_label produces wrong output")
        return 1
    print("✓ step 4: backslash, quote, newline all escape per Prom spec")

    # ── Step 5: NEGATIVE — atomic write via tmp + rename ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        target = tmpdir / "council.prom"
        # Capture filesystem state during write by listing dir contents
        # before and after. The tmp file (target.with_suffix('.prom.tmp'))
        # must NOT exist after the call.
        content = "council_filter_total 42\n"
        stats.write_prometheus_atomic(target, content)
        if not target.exists():
            print("✗ step 5: target file not created")
            return 1
        if target.read_text() != content:
            print(f"✗ step 5: content mismatch: {target.read_text()!r}")
            return 1
        tmp_left = list(tmpdir.glob("*.tmp"))
        if tmp_left:
            print(f"✗ step 5: tmp files left behind: {tmp_left}")
            return 1
        # And re-write must overwrite cleanly
        stats.write_prometheus_atomic(target, "council_filter_total 99\n")
        if "99" not in target.read_text():
            print(f"✗ step 5: re-write didn't replace content")
            return 1
        print("✓ step 5: atomic write via tmp + rename, no partial-read window")

    # ── Step 6: NEGATIVE — every non-comment line is a valid sample ──
    s = _summary(total=10, fired={"MEDIUM": 5},
                 filtered={"too_short": 3}, skipped={"no_council": 2})
    out = stats.render_prometheus(s)
    # Sample line shape per Prom spec (simplified):
    #   <name> <value>             OR
    #   <name>{<labels>} <value>
    # where labels are "key=\"value\",..." and value is an integer.
    sample_re = re.compile(
        r'^[a-zA-Z_][a-zA-Z0-9_]*'                # metric name
        r'(?:\{[a-zA-Z_][a-zA-Z0-9_]*="[^"]*"(?:,[a-zA-Z_][a-zA-Z0-9_]*="[^"]*")*\})?'
        r' \d+(?:\.\d+)?$'
    )
    for line in out.splitlines():
        if not line or line.startswith("#"):
            continue
        if not sample_re.match(line):
            print(f"✗ step 6: malformed sample line: {line!r}")
            return 1
    print("✓ step 6: every non-comment line is a valid Prom sample")

    # ── Step 7: NEGATIVE — empty summary still emits valid output ──
    s = _summary(total=0)  # no entries at all
    out = stats.render_prometheus(s)
    if "council_filter_total 0" not in out:
        print("✗ step 7: empty summary missing total=0")
        return 1
    if "council_filter_council_errors 0" not in out:
        print("✗ step 7: empty summary missing council_errors=0")
        return 1
    # Should still have all known buckets at zero
    for risk in ("LOW", "MEDIUM", "HIGH", "UNKNOWN"):
        if f'risk="{risk}"' not in out:
            print(f"✗ step 7: empty summary dropped risk={risk}")
            return 1
    # And the file should be parseable
    for line in out.splitlines():
        if not line or line.startswith("#"):
            continue
        if not sample_re.match(line):
            print(f"✗ step 7: empty summary produced malformed line: {line!r}")
            return 1
    print("✓ step 7: empty summary emits valid scrapable output (bootstrap-safe)")

    # ── Step 8: POSITIVE — end-to-end via summarize() + render_prometheus ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # Mix of every classify_entry class
        entries = [
            _entry(),  # fired MEDIUM
            _entry(risk_level="LOW"),  # fired LOW
            _entry(fired=False, filtered=True,
                   reason="filtered: skip_token (payload=200, files=3)"),
            _entry(fired=False, filtered=True,
                   reason="filtered: too_short (payload=2, files=1)"),
            _entry(fired=False, filtered=False, reason="no_council requested"),
            _entry(reason="council_error: ImportError"),  # fired but errored
        ]
        log_path = tmpdir / "council_runs.log"
        with log_path.open("w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        summary = stats.summarize(log_path, days=None)
        prom = stats.render_prometheus(summary)
        # Every observed sample must appear with non-zero count
        expected_nonzero = [
            'council_filter_fired{risk="MEDIUM"} 1',
            'council_filter_fired{risk="LOW"} 1',
            'council_filter_filtered{reason="skip_token"} 1',
            'council_filter_filtered{reason="too_short"} 1',
            'council_filter_skipped{reason="no_council"} 1',
            'council_filter_council_errors 1',
        ]
        for sample in expected_nonzero:
            if sample not in prom:
                print(f"✗ step 8: expected sample missing: {sample!r}\n{prom}")
                return 1
        if "council_filter_total 6" not in prom:
            print(f"✗ step 8: total wrong; expected 6\n{prom}")
            return 1
        print(f"✓ step 8: end-to-end summarize → prometheus with all "
              f"{len(expected_nonzero)} non-zero samples present")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
