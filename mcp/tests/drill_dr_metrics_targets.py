#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: DR-metrics targets are defined, sane, and tier-consistent.

Maturity-stack item #35 (DR Metrics) was at L1 — no targets defined,
recovery was hope rather than engineering. This drill locks the
L1 → L2 transition: targets exist, are sane, are tier-ordered,
and break loudly on any future regression that tries to weaken them.

Eight steps. Six negative assertions.

  1. POSITIVE: dr_metrics module imports + exports DrTargets +
     DEFAULT_TIER_TARGETS + get_targets + all_targets
  2. POSITIVE: all 3 tiers (critical/important/standard) are defined
  3. NEGATIVE: every tier has rto_seconds > 0 — no zero-RTO escape
  4. NEGATIVE: every tier has mttr_seconds <= rto_seconds (consistency)
  5. NEGATIVE: tier RTO ordering is monotonically increasing —
     critical < important < standard. Reordering this is a P0
     governance regression.
  6. NEGATIVE: instantiating DrTargets with rto_seconds=0 raises
     ValueError. The dataclass invariant cannot be silently bypassed.
  7. NEGATIVE: instantiating DrTargets with mttr > rto raises
     ValueError. Self-inconsistent targets cannot pass through.
  8. POSITIVE: critical tier has rpo_seconds == 0 (synchronous
     replication). Loosening this requires an explicit ADR per §38.

Per CLAUDE.md §43.1 every drill exercises real code, not mocks.
The module is loaded by absolute path so the drill works whether
or not the libs/py path is on sys.path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "libs" / "py" / "documind_core" / "dr_metrics.py"


def _load():
    spec = importlib.util.spec_from_file_location("documind_dr_metrics", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load dr_metrics from {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    # Python 3.13 dataclass(frozen=True) needs the module registered in
    # sys.modules during exec_module — the @dataclass decorator looks up
    # cls.__module__ in sys.modules to resolve KW_ONLY sentinels.
    sys.modules["documind_dr_metrics"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: dr_metrics module loads with exports --")
    dr = _load()
    for name in ("DrTargets", "DEFAULT_TIER_TARGETS", "get_targets", "all_targets"):
        if not hasattr(dr, name):
            print(f"x step 1: missing export {name}")
            return 1
    print("  ok: DrTargets + DEFAULT_TIER_TARGETS + get_targets + all_targets present")

    print("-- 2. POSITIVE: 3 tiers defined --")
    expected = {"critical", "important", "standard"}
    actual = set(dr.DEFAULT_TIER_TARGETS.keys())
    if actual != expected:
        print(f"x step 2: tier set mismatch — expected {expected}, got {actual}")
        return 1
    print(f"  ok: tiers = {sorted(actual)}")

    print("-- 3. NEGATIVE: every tier has rto_seconds > 0 --")
    for tier_name, t in dr.DEFAULT_TIER_TARGETS.items():
        if t.rto_seconds <= 0:
            print(f"x step 3: tier {tier_name} has non-positive rto_seconds={t.rto_seconds}")
            return 1
    print("  ok: every tier rto_seconds > 0")

    print("-- 4. NEGATIVE: mttr_seconds <= rto_seconds for every tier --")
    for tier_name, t in dr.DEFAULT_TIER_TARGETS.items():
        if t.mttr_seconds > t.rto_seconds:
            print(
                f"x step 4: tier {tier_name} mttr_seconds={t.mttr_seconds} "
                f"> rto_seconds={t.rto_seconds}"
            )
            return 1
    print("  ok: mttr <= rto for every tier")

    print("-- 5. NEGATIVE: tier RTO ordering critical < important < standard --")
    crit = dr.get_targets("critical").rto_seconds
    imp = dr.get_targets("important").rto_seconds
    std = dr.get_targets("standard").rto_seconds
    if not (crit < imp < std):
        print(f"x step 5: RTO ordering violated — critical={crit} important={imp} standard={std}")
        return 1
    print(f"  ok: RTO ordering critical={crit}s < important={imp}s < standard={std}s")

    print("-- 6. NEGATIVE: DrTargets(rto_seconds=0) raises ValueError --")
    try:
        dr.DrTargets(
            tier="critical",
            rto_seconds=0,
            rpo_seconds=0,
            mttd_seconds=60,
            mttr_seconds=60,
            failover_seconds=60,
            description="bypass-attempt",
        )
    except ValueError:
        print("  ok: zero-RTO bypass rejected at construction")
    else:
        print("x step 6: DrTargets accepted rto_seconds=0 — invariant bypass possible")
        return 1

    print("-- 7. NEGATIVE: DrTargets(mttr > rto) raises ValueError --")
    try:
        dr.DrTargets(
            tier="standard",
            rto_seconds=60,
            rpo_seconds=0,
            mttd_seconds=10,
            mttr_seconds=120,
            failover_seconds=10,
            description="self-inconsistent",
        )
    except ValueError:
        print("  ok: mttr > rto bypass rejected at construction")
    else:
        print("x step 7: DrTargets accepted mttr > rto — self-inconsistent targets allowed")
        return 1

    print("-- 8. POSITIVE: critical tier has rpo_seconds == 0 (synchronous replication) --")
    crit_target = dr.get_targets("critical")
    if crit_target.rpo_seconds != 0:
        print(
            f"x step 8: critical tier rpo_seconds={crit_target.rpo_seconds}, "
            "expected 0 (synchronous replication). Loosening requires explicit ADR."
        )
        return 1
    print("  ok: critical tier rpo_seconds=0 (synchronous replication contract)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
