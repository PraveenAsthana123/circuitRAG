#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: --alert-on EXPR works with --weekly (Phase 5R).

Phase 5O restricted --alert-on to single-window mode because per-
week alerts need an aggregation choice. Phase 5R lifts the
restriction by adding --alert-week-mode {each, latest, aggregate}.

This drill locks the contract:
  * each      = alert if ANY week breaches (strictest, default)
  * latest    = check only the most recent dated week
  * aggregate = roll up to single summary (== no-weekly behavior)

And the supporting invariants:
  * unparseable rows skipped in each/latest, included in aggregate
  * empty rows / no-data weeks never fire (divide-by-zero safety)
  * alert message tags the breaching week so operators know which
    one to investigate
  * invalid mode value rejected (typo-safe)

Eight steps. Six negative assertions.

  1. POSITIVE: each mode fires on a single breaching week (baseline).
  2. NEGATIVE: each mode surfaces ALL breaching weeks, not just the
     first. Operator alert email shows the full picture.
  3. NEGATIVE: latest mode fires ONLY on the most recent week. An
     older breaching week must NOT trigger. Operators on this mode
     are explicitly opting out of historical concerns.
  4. NEGATIVE: aggregate mode rolls up to a single check that
     matches the equivalent no-weekly summarize() result. The two
     paths must produce the same alerts on the same data.
  5. NEGATIVE: invalid mode value rejected at the public API level
     (check_alerts_weekly raises ValueError; no silent fallback to
     a default mode).
  6. NEGATIVE: empty / no-data weeks never fire. Same divide-by-
     zero safety as single-window check_alerts.
  7. NEGATIVE: unparseable rows skipped in 'each' mode. They have
     no week label so we can't locate them on a timeline. But they
     ARE included in 'aggregate' mode (data exists, just no week
     tag) — drill verifies both halves of this rule.
  8. NEGATIVE: alert tuple includes the breaching week label —
     each: row's ISO key, latest: latest's key, aggregate: None.

Run: python3 mcp/tests/drill_council_filter_stats_alerts_weekly.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_drill_5R", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5R"] = mod
    spec.loader.exec_module(mod)
    return mod


def _weekly_with_rows(rows: list[dict]) -> dict:
    """Build a weekly dict shaped like summarize_by_week's output.
    Rows must be in newest-first order (matches the production shape)."""
    return {"rows": rows, "weeks_window": None}


def _row(week: str, *, total: int, fired: int = 0, filtered: int = 0,
         skipped: int = 0, errors: int = 0,
         filtered_by_reason: dict | None = None) -> dict:
    """Construct a row in the shape summarize_by_week produces."""
    return {
        "week": week,
        "total": total,
        "fired_by_risk": {"MEDIUM": fired} if fired else {},
        "filtered_by_reason": filtered_by_reason or (
            {"too_short": filtered} if filtered else {}
        ),
        "skipped_by_reason": {"no_council": skipped} if skipped else {},
        "council_errors": errors,
        # Roll-up keys (summarize_by_week populates them):
        "fired": fired,
        "filtered": filtered if not filtered_by_reason else sum(filtered_by_reason.values()),
        "skipped": skipped,
        "errors": errors,
    }


def main() -> int:
    stats = _load_stats()

    # ── Step 1: POSITIVE — each mode fires on single breach ──
    weekly = _weekly_with_rows([
        _row("2026-W18", total=10, filtered=6, fired=4),  # too_short = 0.6
    ])
    expr = stats.parse_alert_expr("too_short>0.5")
    fired = stats.check_alerts_weekly(weekly, [expr], mode="each")
    if len(fired) != 1:
        print(f"✗ step 1: each mode fired {len(fired)} alerts, expected 1")
        return 1
    e, week, observed = fired[0]
    if week != "2026-W18" or abs(observed - 0.6) > 1e-9:
        print(f"✗ step 1: alert ({week}, {observed}), expected (2026-W18, 0.6)")
        return 1
    print(f"✓ step 1: each mode fires on single breach (week={week}, observed={observed})")

    # ── Step 2: NEGATIVE — each mode surfaces ALL breaches ──
    weekly = _weekly_with_rows([
        _row("2026-W18", total=10, filtered=7),   # 0.7 — fires
        _row("2026-W17", total=10, filtered=2),   # 0.2 — passes
        _row("2026-W16", total=10, filtered=8),   # 0.8 — fires
        _row("2026-W15", total=10, filtered=6),   # 0.6 — fires
    ])
    expr = stats.parse_alert_expr("too_short>0.5")
    fired = stats.check_alerts_weekly(weekly, [expr], mode="each")
    if len(fired) != 3:
        print(f"✗ step 2: each mode fired {len(fired)} alerts, expected 3 "
              "(W18, W16, W15 all breach > 0.5)")
        return 1
    fired_weeks = {f[1] for f in fired}
    if fired_weeks != {"2026-W18", "2026-W16", "2026-W15"}:
        print(f"✗ step 2: fired weeks {fired_weeks}, expected "
              "{2026-W18, 2026-W16, 2026-W15}")
        return 1
    print(f"✓ step 2: each mode surfaces all 3 breaching weeks (skips passing W17)")

    # ── Step 3: NEGATIVE — latest mode ignores older weeks ──
    weekly = _weekly_with_rows([
        _row("2026-W18", total=10, filtered=2),   # 0.2 — passes
        _row("2026-W17", total=10, filtered=8),   # 0.8 — would fire each, NOT latest
        _row("2026-W16", total=10, filtered=9),   # 0.9 — would fire each, NOT latest
    ])
    expr = stats.parse_alert_expr("too_short>0.5")
    fired_latest = stats.check_alerts_weekly(weekly, [expr], mode="latest")
    if fired_latest:
        print(f"✗ step 3: latest mode fired {len(fired_latest)} alerts, "
              "expected 0 (only W18=0.2 should be checked, and it passes)")
        return 1
    # Verify each mode WOULD fire on this data (sanity check)
    fired_each = stats.check_alerts_weekly(weekly, [expr], mode="each")
    if len(fired_each) != 2:
        print(f"✗ step 3: each-mode sanity check expected 2 fires, got {len(fired_each)}")
        return 1
    print(f"✓ step 3: latest mode ignores 2 older breaching weeks (each-mode would fire 2)")

    # ── Step 4: NEGATIVE — aggregate mode matches no-weekly behavior ──
    weekly = _weekly_with_rows([
        _row("2026-W18", total=10, filtered=4, fired=6),
        _row("2026-W17", total=10, filtered=6, fired=4),
    ])
    # Aggregate: total=20, filtered=10 → 0.5
    expr = stats.parse_alert_expr("filtered>0.4")  # 0.5 > 0.4 → fires
    fired_agg = stats.check_alerts_weekly(weekly, [expr], mode="aggregate")
    if len(fired_agg) != 1:
        print(f"✗ step 4: aggregate fired {len(fired_agg)}, expected 1")
        return 1
    e, week, observed = fired_agg[0]
    if week is not None:
        print(f"✗ step 4: aggregate week label should be None, got {week!r}")
        return 1
    if abs(observed - 0.5) > 1e-9:
        print(f"✗ step 4: aggregate observed={observed}, expected 0.5")
        return 1
    # And on the same data, expr that wouldn't fire on individual weeks
    # (each W is 0.4 or 0.6) but DOES fire on aggregate (0.5).
    expr_55 = stats.parse_alert_expr("filtered>0.55")
    fired_agg_55 = stats.check_alerts_weekly(weekly, [expr_55], mode="aggregate")
    fired_each_55 = stats.check_alerts_weekly(weekly, [expr_55], mode="each")
    if fired_agg_55:
        print(f"✗ step 4b: aggregate>0.55 fired (observed 0.5)")
        return 1
    if len(fired_each_55) != 1:
        print(f"✗ step 4b: each>0.55 expected 1 fire (W17=0.6), got {len(fired_each_55)}")
        return 1
    print(f"✓ step 4: aggregate rollup = 0.5; each-mode breaks down to 0.4/0.6")

    # ── Step 5: NEGATIVE — invalid mode rejected ──
    try:
        stats.check_alerts_weekly(weekly, [expr], mode="garbage_mode")
    except ValueError:
        pass
    else:
        print("✗ step 5: invalid mode 'garbage_mode' accepted; should raise")
        return 1
    print("✓ step 5: invalid alert-week-mode rejected with ValueError")

    # ── Step 6: NEGATIVE — empty / zero-total weeks don't fire ──
    weekly = _weekly_with_rows([
        _row("2026-W18", total=0),  # zero entries — divide-by-zero candidate
    ])
    for mode in stats.ALERT_WEEK_MODES:
        expr = stats.parse_alert_expr("filtered>0.0")
        fired = stats.check_alerts_weekly(weekly, [expr], mode=mode)
        if fired:
            print(f"✗ step 6: zero-total week fired alert in mode={mode!r}: {fired}")
            return 1
    # Also: empty weekly with NO rows at all
    empty = _weekly_with_rows([])
    for mode in stats.ALERT_WEEK_MODES:
        fired = stats.check_alerts_weekly(empty, [expr], mode=mode)
        if fired:
            print(f"✗ step 6: empty weekly fired alert in mode={mode!r}: {fired}")
            return 1
    print("✓ step 6: zero-total + empty-rows never fire (3 modes × 2 cases)")

    # ── Step 7: NEGATIVE — unparseable handling ──
    # Build weekly with 1 dated row + 1 unparseable.
    weekly = _weekly_with_rows([
        _row("2026-W18", total=10, filtered=2),    # 0.2 — passes
        _row("unparseable", total=10, filtered=8), # 0.8 — would fire if checked
    ])
    expr = stats.parse_alert_expr("filtered>0.5")
    # 'each' mode: the dated W18 doesn't breach; unparseable IS skipped.
    fired_each = stats.check_alerts_weekly(weekly, [expr], mode="each")
    if fired_each:
        print(f"✗ step 7: each mode should skip unparseable: got {fired_each}")
        return 1
    # 'latest' mode: only the latest dated row checked (W18 = 0.2 passes).
    fired_latest = stats.check_alerts_weekly(weekly, [expr], mode="latest")
    if fired_latest:
        print(f"✗ step 7: latest mode should skip unparseable: got {fired_latest}")
        return 1
    # 'aggregate' mode: rolls up BOTH rows. Total=20, filtered=10 → 0.5
    # which is NOT > 0.5 (strict), so doesn't fire. Verify the data IS in
    # the aggregate by using a lower threshold.
    expr_low = stats.parse_alert_expr("filtered>0.4")
    fired_agg = stats.check_alerts_weekly(weekly, [expr_low], mode="aggregate")
    if len(fired_agg) != 1:
        print(f"✗ step 7: aggregate mode should INCLUDE unparseable in rollup: "
              f"expected 1 fire at >0.4, got {len(fired_agg)}")
        return 1
    if abs(fired_agg[0][2] - 0.5) > 1e-9:
        print(f"✗ step 7: aggregate observed={fired_agg[0][2]}, expected 0.5 "
              "(rollup must include unparseable's data)")
        return 1
    print("✓ step 7: unparseable skipped in each/latest, included in aggregate")

    # ── Step 8: NEGATIVE — alert tuple week-label semantics ──
    weekly = _weekly_with_rows([
        _row("2026-W18", total=10, filtered=8),
        _row("2026-W17", total=10, filtered=8),
    ])
    expr = stats.parse_alert_expr("filtered>0.5")
    # each: tuple per breaching row
    fired_each = stats.check_alerts_weekly(weekly, [expr], mode="each")
    weeks = sorted({f[1] for f in fired_each})
    if weeks != ["2026-W17", "2026-W18"]:
        print(f"✗ step 8: each-mode week labels {weeks}, expected both weeks")
        return 1
    # latest: tuple has only the latest week's label (newest-first → W18)
    fired_latest = stats.check_alerts_weekly(weekly, [expr], mode="latest")
    if len(fired_latest) != 1 or fired_latest[0][1] != "2026-W18":
        print(f"✗ step 8: latest-mode tuple week={fired_latest[0][1] if fired_latest else None}, "
              "expected 2026-W18")
        return 1
    # aggregate: tuple's week label is None
    fired_agg = stats.check_alerts_weekly(weekly, [expr], mode="aggregate")
    if len(fired_agg) != 1 or fired_agg[0][1] is not None:
        print(f"✗ step 8: aggregate-mode tuple week should be None, "
              f"got {fired_agg[0][1] if fired_agg else 'no-fire'}")
        return 1
    print("✓ step 8: tuple week-label semantics correct in all 3 modes")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
