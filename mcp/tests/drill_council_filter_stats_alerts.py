#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/council_filter_stats.py --alert-on EXPR (Phase 5O).

Phase 5O lets operators / CI fail a job when a filter dominates:
    --alert-on too_short>0.5      # too_short rate above 50%
    --alert-on filtered>0.8       # overall filter rate above 80%
    --alert-on fired<0.3          # fire rate dropped below 30%

This drill locks the contract — expression parser strictness, meta-
bucket semantics, threshold comparison, divide-by-zero safety, and
the multi-alert pipeline.

Eight steps. Six negative assertions.

  1. parse_alert_expr accepts every valid form (each canonical
     filter, each meta-bucket, each comparison operator).
  2. NEGATIVE: parse_alert_expr rejects bad forms — unknown bucket,
     missing op, bad threshold, threshold out of [0.0, 1.0]. Six
     bad shapes; ALL must raise ValueError. Without strict parse,
     a typo in a CI alert fires silently.
  3. NEGATIVE: AlertExpr.evaluate uses STRICT operators — '>' fires
     ONLY when observed strictly greater (not equal).
  4. NEGATIVE: empty log → no alert fires (divide-by-zero safety).
     Without this, every CI run on a fresh repo would fail.
  5. NEGATIVE: meta-bucket 'filtered' sums all filter buckets,
     not just one. Operator who writes 'filtered>0.8' expects the
     OVERALL filter rate, not skip_token specifically.
  6. NEGATIVE: meta-bucket 'fired' counts fired_by_risk total,
     not the legacy 'fired' boolean. The bucket maps to the
     summary roll-up, not to the per-entry flag.
  7. NEGATIVE: check_alerts returns ALL fired, not just the first.
     Multiple --alert-on expressions surface every match so
     operators see the full picture in one CI run.
  8. POSITIVE: integration with summarize() — real summary
     structure flows through evaluate() correctly.

Run: python3 mcp/tests/drill_council_filter_stats_alerts.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_drill_5O", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5O"] = mod
    spec.loader.exec_module(mod)
    return mod


def _entry(*, fired: bool = True, filtered: bool = False,
           reason: str = "council_completed risk=MEDIUM",
           risk_level: str = "MEDIUM") -> dict:
    return {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "fired": fired, "filtered": filtered,
        "reason": reason, "risk_level": risk_level,
    }


def _write_log(tmpdir: Path, entries: list[dict]) -> Path:
    p = tmpdir / "council_runs.log"
    with p.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return p


def main() -> int:
    stats = _load_stats()

    # ── Step 1: parse_alert_expr accepts every valid form ──
    valid = [
        # canonical filters
        "skip_token>0.5",
        "too_short>=0.3",
        "all_binary<0.1",
        "doc_only<=0.2",
        "capture_error=0.0",
        "empty_diff!=0.0",
        # meta-buckets
        "filtered>0.8",
        "fired<0.3",
        "skipped>0.5",
        "council_errors>0.0",
        # legacy synthetic buckets
        "legacy>0.0",
        "unknown>0.0",
    ]
    parsed = []
    for s in valid:
        try:
            expr = stats.parse_alert_expr(s)
        except Exception as exc:
            print(f"✗ step 1: {s!r} rejected: {type(exc).__name__}: {exc}")
            return 1
        if expr.raw != s:
            print(f"✗ step 1: {s!r} parsed but raw={expr.raw!r}")
            return 1
        parsed.append(expr)
    # All 6 ops covered?
    seen_ops = {p.op for p in parsed}
    if seen_ops != {">", ">=", "<", "<=", "=", "!="}:
        print(f"✗ step 1: ops covered {seen_ops}, missing some")
        return 1
    print(f"✓ step 1: {len(valid)} valid expressions parsed (6 ops, "
          f"{len(stats.ALERT_BUCKETS)} bucket names)")

    # ── Step 2: NEGATIVE — parse_alert_expr rejects bad forms ──
    bad = [
        "garbage_bucket>0.5",       # unknown bucket
        "skip_token 0.5",            # no operator (must use >, <, =, etc)
        "skip_token>>0.5",           # invalid operator
        "skip_token>",               # missing threshold
        "skip_token>1.5",            # threshold > 1.0
        "skip_token>-0.1",           # threshold < 0.0 (regex itself rejects '-')
        "",                          # empty
        ">0.5",                      # missing bucket
    ]
    for s in bad:
        try:
            stats.parse_alert_expr(s)
        except ValueError:
            continue
        print(f"✗ step 2: bad form {s!r} accepted; should raise ValueError")
        return 1
    print(f"✓ step 2: {len(bad)} bad forms all rejected with ValueError")

    # ── Step 3: NEGATIVE — strict operators ──
    # Build a synthetic summary where filtered = exactly 0.5 of total.
    summary = {
        "total": 4,
        "fired_by_risk": {"MEDIUM": 2},
        "filtered_by_reason": {"too_short": 2},
        "skipped_by_reason": {},
        "council_errors": 0,
    }
    cases = [
        ("filtered>0.5",  False),  # 0.5 NOT > 0.5 (strict)
        ("filtered>=0.5", True),   # 0.5 >= 0.5
        ("filtered<0.5",  False),
        ("filtered<=0.5", True),
        ("filtered=0.5",  True),
        ("filtered!=0.5", False),
    ]
    for s, expect_fired in cases:
        expr = stats.parse_alert_expr(s)
        is_fired, observed = expr.evaluate(summary)
        if is_fired != expect_fired:
            print(f"✗ step 3: {s!r} fired={is_fired}, expected {expect_fired} "
                  f"(observed={observed})")
            return 1
    print(f"✓ step 3: {len(cases)} operator-edge cases evaluate correctly "
          "(strict > / <)")

    # ── Step 4: NEGATIVE — empty log doesn't fire alerts ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        empty_log = tmpdir / "empty.log"
        empty_log.write_text("")
        s = stats.summarize(empty_log, days=None)
        # Even an alert that would otherwise fire on >0 entries must
        # not fire here. Divide-by-zero must be silent.
        for raw in ["filtered>0.0", "fired>0.0", "skip_token>=0.0"]:
            expr = stats.parse_alert_expr(raw)
            is_fired, observed = expr.evaluate(s)
            if is_fired:
                print(f"✗ step 4: empty log fired alert {raw!r} "
                      f"(observed={observed})")
                return 1
            if observed != 0.0:
                print(f"✗ step 4: empty log observed={observed!r}, expected 0.0")
                return 1
        print("✓ step 4: empty log → no alert fires (divide-by-zero safe)")

    # ── Step 5: NEGATIVE — meta-bucket 'filtered' sums all filters ──
    summary = {
        "total": 10,
        "fired_by_risk": {},
        "filtered_by_reason": {"skip_token": 2, "too_short": 3, "doc_only": 2},
        "skipped_by_reason": {},
        "council_errors": 3,
    }
    expr = stats.parse_alert_expr("filtered>0.6")
    is_fired, observed = expr.evaluate(summary)
    # filtered total = 2+3+2 = 7; observed = 7/10 = 0.7
    if not is_fired or abs(observed - 0.7) > 1e-9:
        print(f"✗ step 5: 'filtered' meta-bucket: observed={observed}, "
              "expected 0.7 (sum of all filter buckets)")
        return 1
    # And a SPECIFIC filter alert with the same threshold must NOT fire
    expr_specific = stats.parse_alert_expr("skip_token>0.6")
    is_fired_specific, observed_specific = expr_specific.evaluate(summary)
    if is_fired_specific:
        print(f"✗ step 5: skip_token>0.6 fired (observed={observed_specific}), "
              "but skip_token is only 2/10 = 0.2")
        return 1
    print(f"✓ step 5: 'filtered' meta-bucket sums to 0.7 "
          f"(specific skip_token={observed_specific:.1f})")

    # ── Step 6: NEGATIVE — meta-bucket 'fired' uses fired_by_risk ──
    summary = {
        "total": 10,
        "fired_by_risk": {"MEDIUM": 3, "LOW": 1},
        "filtered_by_reason": {},
        "skipped_by_reason": {},
        "council_errors": 6,  # fired=True but errored — NOT counted in 'fired'
    }
    expr = stats.parse_alert_expr("fired>0.5")
    is_fired, observed = expr.evaluate(summary)
    # fired count from fired_by_risk = 3+1 = 4; observed = 4/10 = 0.4
    # Even though entry-level 'fired' was True for the 6 council_errors
    # too, the meta-bucket counts only normal completions.
    if abs(observed - 0.4) > 1e-9:
        print(f"✗ step 6: 'fired' meta-bucket observed={observed}, "
              "expected 0.4 (fired_by_risk only, NOT council_errors)")
        return 1
    if is_fired:
        print("✗ step 6: fired>0.5 fired at observed=0.4")
        return 1
    print("✓ step 6: 'fired' meta-bucket = 0.4 "
          "(fired_by_risk only, council_errors separate)")

    # ── Step 7: NEGATIVE — multiple alerts surface ALL fired ──
    summary = {
        "total": 10,
        "fired_by_risk": {"MEDIUM": 1},
        "filtered_by_reason": {"skip_token": 4, "too_short": 4},
        "skipped_by_reason": {"no_council": 1},
        "council_errors": 0,
    }
    exprs = [
        stats.parse_alert_expr("filtered>0.5"),    # 0.8 → fires
        stats.parse_alert_expr("skip_token>0.3"),  # 0.4 → fires
        stats.parse_alert_expr("fired>0.5"),       # 0.1 → does NOT fire
        stats.parse_alert_expr("too_short>0.3"),   # 0.4 → fires
    ]
    fired = stats.check_alerts(summary, exprs)
    if len(fired) != 3:
        print(f"✗ step 7: {len(fired)} alerts fired, expected 3")
        return 1
    fired_buckets = {e.bucket for e, _ in fired}
    if fired_buckets != {"filtered", "skip_token", "too_short"}:
        print(f"✗ step 7: fired buckets {fired_buckets}, "
              "expected {filtered, skip_token, too_short}")
        return 1
    print(f"✓ step 7: check_alerts returns all {len(fired)} fired (not just first)")

    # ── Step 8: POSITIVE — integration with summarize() ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # 10 entries: 6 fired MEDIUM, 4 filtered as too_short
        entries = [_entry() for _ in range(6)]
        for _ in range(4):
            entries.append(_entry(
                fired=False, filtered=True,
                reason="filtered: too_short (payload=2, files=1, binary=False)",
            ))
        log_path = _write_log(tmpdir, entries)
        s = stats.summarize(log_path, days=None)
        if s["total"] != 10:
            print(f"✗ step 8: total={s['total']}, expected 10")
            return 1
        # too_short rate = 4/10 = 0.4 → fires at >0.3, doesn't at >0.5
        e_fires = stats.parse_alert_expr("too_short>0.3")
        e_passes = stats.parse_alert_expr("too_short>0.5")
        if not e_fires.evaluate(s)[0]:
            print("✗ step 8: too_short>0.3 didn't fire on 0.4 observed")
            return 1
        if e_passes.evaluate(s)[0]:
            print("✗ step 8: too_short>0.5 fired on 0.4 observed")
            return 1
        print("✓ step 8: end-to-end summarize() → evaluate() works "
              "(too_short=0.4: fires >0.3, passes >0.5)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
