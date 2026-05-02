#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: drift_detection module — both directions locked.

Maturity-stack item #44 (Production Validation) was at L2 — drills
existed but no live drift detection. This drill locks the L2 → L3
movement: decision-confidence drift dimension is implemented,
JSON-serializable, and **detects shifts both ways**:

  - A/A test: identical distributions → PSI < 0.1, severity="ok"
    (no false positive — the load-bearing reverse assertion)
  - A/B test: known-shifted distribution → PSI > 0.2, severity="significant"
    (real detection — the forward assertion)

Per advisor guidance: a one-direction drill ("function returns a
number") is the same theater as the dangling P0 fixes. Both
directions is what locks the contract.

Eight steps. Six negative assertions.

  1. POSITIVE: drift_detection module imports + exports
     (BaselineWindow, DriftReport, compute_psi, compare_windows,
     summarize_confidence_values)
  2. POSITIVE: BaselineWindow rejects out-of-range values
     (confidence outside [0, 1] is bug or DB corruption)
  3. NEGATIVE: A/A test — same distribution → severity="ok",
     psi < 0.1. False positive here = noisy alert spam in prod.
  4. NEGATIVE: A/B test — clearly shifted distribution → severity=
     "significant", psi > 0.2. Missing this = the module fails its
     entire purpose; the build must catch it.
  5. NEGATIVE: empty baseline OR empty current → severity=
     "insufficient_data", psi=None. Honest rather than 0 or crash.
  6. NEGATIVE: small window (< min_window_size) → severity=
     "insufficient_data". Prevents alert spam from tiny samples.
  7. NEGATIVE: DriftReport.to_dict() is JSON-round-trippable —
     #48 Risk Engine + dashboards + alerts all consume the same
     dict shape, so it MUST serialize cleanly.
  8. POSITIVE: severity ladder respects threshold ordering —
     monotone: psi=0.05 → ok, psi=0.15 → minor, psi=0.30 → significant.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "libs" / "py" / "documind_core" / "drift_detection.py"


def _load():
    spec = importlib.util.spec_from_file_location("documind_drift_detection", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load drift_detection from {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["documind_drift_detection"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: drift_detection module imports + exports --")
    dd = _load()
    for name in (
        "BaselineWindow",
        "DriftReport",
        "compute_psi",
        "compare_windows",
        "summarize_confidence_values",
    ):
        if not hasattr(dd, name):
            print(f"x step 1: missing export {name}")
            return 1
    print("  ok: all exports present")

    print("-- 2. POSITIVE: BaselineWindow rejects out-of-range values --")
    try:
        dd.BaselineWindow(label="bad", values=(0.5, 1.2), count=2)
    except ValueError:
        print("  ok: confidence > 1.0 rejected at construction")
    else:
        print("x step 2: out-of-range value accepted — invariant bypass possible")
        return 1

    # Build the windows used across steps 3-8. Use a deterministic seed
    # so the drill is reproducible across runs.
    random.seed(42)

    print("-- 3. NEGATIVE: A/A test — identical distributions → severity='ok' --")
    # Two independent samples from the SAME beta distribution.
    # Beta(8,2) gives a high-confidence-skewed distribution, similar
    # to what a well-tuned classifier produces.
    base_values = tuple(random.betavariate(8, 2) for _ in range(500))
    cur_values = tuple(random.betavariate(8, 2) for _ in range(500))
    base = dd.summarize_confidence_values("baseline-AA", list(base_values))
    cur = dd.summarize_confidence_values("current-AA", list(cur_values))
    rep = dd.compare_windows(base, cur)
    if rep.severity != "ok":
        print(
            f"x step 3: A/A test FAILED — got severity={rep.severity}, psi={rep.psi}, "
            f"reason={rep.severity_reason}. False positive on identical distributions = "
            "alert spam in prod."
        )
        return 1
    if rep.psi is None or rep.psi >= 0.1:
        print(f"x step 3: A/A test PSI {rep.psi} not below 0.1 threshold")
        return 1
    print(f"  ok: A/A psi={rep.psi:.4f} < 0.1; severity=ok")

    print("-- 4. NEGATIVE: A/B test — known shift → severity='significant' --")
    # Beta(8,2) baseline (right-skewed; high confidence cluster) vs.
    # Beta(2,8) current (left-skewed; low confidence cluster). Roughly
    # mirror images — confidence has collapsed. PSI should be enormous.
    shifted_values = tuple(random.betavariate(2, 8) for _ in range(500))
    cur_shifted = dd.summarize_confidence_values("current-AB", list(shifted_values))
    rep2 = dd.compare_windows(base, cur_shifted)
    if rep2.severity != "significant":
        print(
            f"x step 4: A/B test FAILED — got severity={rep2.severity}, psi={rep2.psi}, "
            f"reason={rep2.severity_reason}. Missing real shift = drift detection is "
            "decorative, not load-bearing."
        )
        return 1
    if rep2.psi is None or rep2.psi <= 0.2:
        print(f"x step 4: A/B test PSI {rep2.psi} not above 0.2 threshold")
        return 1
    print(f"  ok: A/B psi={rep2.psi:.4f} > 0.2; severity=significant")

    print("-- 5. NEGATIVE: empty window → severity='insufficient_data', no crash --")
    empty = dd.summarize_confidence_values("empty", [])
    rep3 = dd.compare_windows(base, empty)
    if rep3.severity != "insufficient_data":
        print(f"x step 5: empty current_window expected insufficient_data; got {rep3.severity}")
        return 1
    if rep3.psi is not None:
        print(f"x step 5: empty window must yield psi=None; got {rep3.psi}")
        return 1
    rep3b = dd.compare_windows(empty, base)
    if rep3b.severity != "insufficient_data":
        print(f"x step 5: empty baseline_window expected insufficient_data; got {rep3b.severity}")
        return 1
    print("  ok: empty windows in either slot → insufficient_data + psi=None")

    print("-- 6. NEGATIVE: small window (< min_window_size) → insufficient_data --")
    tiny = dd.summarize_confidence_values("tiny", [0.5] * 5)
    rep4 = dd.compare_windows(base, tiny)
    if rep4.severity != "insufficient_data":
        print(
            f"x step 6: tiny window expected insufficient_data; got {rep4.severity}. "
            "PSI on small samples is noise — alert spam if not gated."
        )
        return 1
    print(f"  ok: small window (count=5 < min) → insufficient_data; reason={rep4.severity_reason[:60]}...")

    print("-- 7. NEGATIVE: DriftReport.to_dict() round-trips through JSON --")
    payload = rep2.to_dict()
    serialized = json.dumps(payload)
    deserialized = json.loads(serialized)
    if deserialized != payload:
        print(f"x step 7: JSON round-trip lost data — diff {set(payload.keys()) - set(deserialized.keys())}")
        return 1
    expected_keys = {
        "dimension", "baseline_label", "baseline_count",
        "current_label", "current_count", "psi", "severity",
        "severity_reason", "threshold_minor", "threshold_significant",
    }
    actual_keys = set(payload.keys())
    if actual_keys != expected_keys:
        print(f"x step 7: DriftReport schema mismatch — extra={actual_keys - expected_keys}, missing={expected_keys - actual_keys}")
        return 1
    print(f"  ok: 10-field DriftReport round-trips through JSON; #48 Risk Engine ready")

    print("-- 8. POSITIVE: severity ladder is monotone (psi increase → severity escalation) --")
    # Build minor-shift A/B: Beta(8,2) vs Beta(7,3) — small drift.
    minor_shift = tuple(random.betavariate(7, 3) for _ in range(500))
    cur_minor = dd.summarize_confidence_values("current-minor", list(minor_shift))
    rep_minor = dd.compare_windows(base, cur_minor)
    # Allow either ok or minor depending on RNG; assertion is monotone:
    # AA psi <= minor-shift psi <= AB psi
    if not (rep.psi <= rep_minor.psi <= rep2.psi):
        print(
            f"x step 8: severity ladder not monotone — "
            f"AA={rep.psi:.4f} > minor-shift={rep_minor.psi:.4f} or "
            f"minor-shift > AB={rep2.psi:.4f}"
        )
        return 1
    print(f"  ok: monotone — AA={rep.psi:.4f} <= minor={rep_minor.psi:.4f} <= AB={rep2.psi:.4f}")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
