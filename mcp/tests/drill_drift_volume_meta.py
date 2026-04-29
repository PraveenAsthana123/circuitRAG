#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: drift volume meta-metric — total grandfathered entries
across all KNOWN_* ratchets in the drill catalog.

ADR-015's ratchet pattern works by:
  * KNOWN_X = current grandfathered drift (the floor)
  * Drill asserts: count(observed) <= count(KNOWN_X)
  * Future iterations pay down KNOWN_X toward zero
  * Growth requires explicit operator extension of KNOWN_X

This drill measures the total paydown burden across the catalog
by walking every drill_*.py file and AST-extracting every
KNOWN_* assignment (both Assign and AnnAssign nodes). Per-drill
counts and total are emitted; thresholds catch runaway growth.

The metric distinguishes intent:
  * KNOWN_X with intent-to-shrink (KNOWN_NO_HELP, KNOWN_LATE_AUDITS,
    KNOWN_UNAUDITED) — should trend to 0
  * KNOWN_X with intent-to-allowlist (KNOWN_TEST_FIXTURES) — small,
    stable; growth requires deliberate op review

Both shapes are counted; the drill emits the per-set count so
operators can see WHERE the burden lives. Total is the headline
number for trend-watching across sessions.

Eight steps. Five negative assertions.

  1. POSITIVE: discover drill files (>= 80 floor — drill cannot
     trivially pass on empty catalog).
  2. NEGATIVE: at least MIN_RATCHET_DRILLS drills have at least
     one KNOWN_* assignment. Catalog without ratchets means the
     ADR-015 pattern isn't in use; surfaces a structural issue.
  3. NEGATIVE: total grandfathered count <= TOTAL_BURDEN_FLOOR.
     Floor matches observed at landing; ratchet pattern gates
     growth. Future shrinkage moves the floor down (good).
  4. NEGATIVE: no single drill grandfathers > MAX_PER_DRILL
     entries. A KNOWN_X bigger than this threshold has
     graduated from "ratchet" to "permanent allowlist" — should
     be renamed (e.g., to ALLOWLIST_X) and removed from the
     drift-counting scope.
  5. NEGATIVE: every KNOWN_* is at module level (not function-
     local). Function-local ratchets are invisible to this drill
     and to operator review. ADR-015 + this drill require
     module-level visibility.
  6. NEGATIVE: every KNOWN_* literal value parses cleanly to a
     concrete container (Set / List / Tuple / Dict / frozenset()
     / set()). Dynamic computation (e.g., `KNOWN_X = some_function()`)
     hides the actual count.
  7. POSITIVE: emit per-drill paydown table.
  8. POSITIVE: emit overall paydown summary + trend marker.

Run: python3 mcp/tests/drill_drift_volume_meta.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILLS_DIR = REPO / "mcp" / "tests"

MIN_DRILLS = 80
MIN_RATCHET_DRILLS = 1  # at least one drill must have a KNOWN_*
TOTAL_BURDEN_FLOOR = 5  # observed at landing: 3 (KNOWN_LATE_AUDITS) + 1 (KNOWN_TEST_FIXTURES) + 1 buffer
MAX_PER_DRILL = 50      # sanity ceiling

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _count_literal(node: ast.AST) -> int | None:
    """Count elements in a concrete container literal. None means
    we couldn't parse — drill flags this as step 6 violation."""
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return len(node.elts)
    if isinstance(node, ast.Dict):
        return len(node.keys)
    if isinstance(node, ast.Call):
        # frozenset({...}) / set([...]) / dict({...})
        callee = ""
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        if callee in ("set", "frozenset", "dict", "list", "tuple"):
            if not node.args:
                return 0
            inner = node.args[0]
            return _count_literal(inner)
        # range(a, b) → b - a items (best-effort static analysis)
        if callee == "range" and node.args:
            try:
                vals = [a.value for a in node.args if isinstance(a, ast.Constant)]
                if len(vals) == len(node.args):
                    return len(list(range(*vals)))
            except (TypeError, ValueError):
                pass
    return None


def _scan_drill(path: Path) -> list[tuple[str, int | None]]:
    """Return [(name, count_or_None)] for every module-level KNOWN_*
    assignment in the file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return []
    out: list[tuple[str, int | None]] = []
    for node in tree.body:  # module-level only
        targets: list[str] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    targets.append(tgt.id)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                targets.append(node.target.id)
            value = node.value
        else:
            continue
        for name in targets:
            if not name.startswith("KNOWN_"):
                continue
            if value is None:
                out.append((name, None))
            else:
                out.append((name, _count_literal(value)))
    return out


def _scan_drill_function_local(path: Path) -> list[str]:
    """Return KNOWN_* names found INSIDE function bodies (which would
    fail step 5). Catches misplaced ratchets."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return []
    bad: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Assign):
                for tgt in sub.targets:
                    if isinstance(tgt, ast.Name) and tgt.id.startswith("KNOWN_"):
                        bad.append(tgt.id)
            elif isinstance(sub, ast.AnnAssign):
                if isinstance(sub.target, ast.Name) and sub.target.id.startswith("KNOWN_"):
                    bad.append(sub.target.id)
    return bad


def main() -> int:
    step("1. POSITIVE: discover drill files (>= MIN_DRILLS floor)")
    drills = sorted(DRILLS_DIR.glob("drill_*.py"))
    if len(drills) < MIN_DRILLS:
        fail(
            f"only {len(drills)} drills; floor is {MIN_DRILLS}. "
            "Drill cannot trivially pass on empty catalog."
        )
    ok(f"discovered {len(drills)} drill files")

    per_drill: list[tuple[str, list[tuple[str, int | None]]]] = []
    for p in drills:
        items = _scan_drill(p)
        if items:
            per_drill.append((p.name, items))

    step("2. NEGATIVE: at least MIN_RATCHET_DRILLS drills carry a KNOWN_*")
    if len(per_drill) < MIN_RATCHET_DRILLS:
        fail(
            f"only {len(per_drill)} drills have any KNOWN_* — ADR-015 "
            "ratchet pattern is not in use across the catalog. Either "
            "the pattern was abandoned or my scanner is broken."
        )
    ok(f"{len(per_drill)} drills have at least one KNOWN_* ratchet")

    # Compute total burden, ignoring entries with None (those fail step 6).
    total_burden = sum(
        count for _, items in per_drill
        for _, count in items if count is not None
    )

    step("3. NEGATIVE: total grandfathered count <= TOTAL_BURDEN_FLOOR")
    if total_burden > TOTAL_BURDEN_FLOOR:
        fail(
            f"total KNOWN_* entries={total_burden} > "
            f"{TOTAL_BURDEN_FLOOR}. Paydown burden grew; investigate "
            "or extend TOTAL_BURDEN_FLOOR explicitly with rationale."
        )
    ok(f"total KNOWN_* entries = {total_burden} (<= {TOTAL_BURDEN_FLOOR})")

    step("4. NEGATIVE: no single drill grandfathers > MAX_PER_DRILL entries")
    over_ceiling: list[tuple[str, str, int]] = []
    for name, items in per_drill:
        for set_name, count in items:
            if count is not None and count > MAX_PER_DRILL:
                over_ceiling.append((name, set_name, count))
    if over_ceiling:
        fail(
            f"{len(over_ceiling)} KNOWN_* sets exceed per-drill ceiling "
            f"({MAX_PER_DRILL}): {over_ceiling[:3]}. Rename to "
            "ALLOWLIST_* if it has graduated from ratchet to permanent."
        )
    ok(f"no per-drill KNOWN_* exceeds {MAX_PER_DRILL} entries")

    step("5. NEGATIVE: every KNOWN_* is at module level (not function-local)")
    function_local: list[tuple[str, str]] = []
    for p in drills:
        for nm in _scan_drill_function_local(p):
            function_local.append((p.name, nm))
    if function_local:
        fail(
            f"{len(function_local)} KNOWN_* found inside function "
            f"bodies: {function_local[:3]}. Lift to module level for "
            "operator visibility."
        )
    ok("all KNOWN_* sets are module-level")

    step("6. NEGATIVE: every KNOWN_* literal parses to a concrete container")
    unparseable: list[tuple[str, str]] = []
    for name, items in per_drill:
        for set_name, count in items:
            if count is None:
                unparseable.append((name, set_name))
    if unparseable:
        fail(
            f"{len(unparseable)} KNOWN_* values aren't concrete "
            f"literals: {unparseable[:3]}. Dynamic computation hides "
            "the count from operator review."
        )
    ok("all KNOWN_* literals parse to concrete containers")

    step("7. POSITIVE: per-drill paydown table")
    for name, items in per_drill:
        line = ", ".join(f"{n}={c}" for n, c in items if c is not None)
        ok(f"  {name}: {line}")

    step("8. POSITIVE: overall paydown summary")
    payable_zero = sum(
        1 for _, items in per_drill
        for _, count in items if count == 0
    )
    payable_nonzero = sum(
        1 for _, items in per_drill
        for _, count in items if count is not None and count > 0
    )
    total_sets = payable_zero + payable_nonzero
    ok(
        f"DRIFT VOLUME: total={total_burden} entries across "
        f"{len(per_drill)} drills with ratchets; {total_sets} KNOWN_* "
        f"sets total ({payable_zero} empty, {payable_nonzero} non-empty)"
    )
    if payable_nonzero == 0:
        ok("  ratchet state: ALL CLEAN — every KNOWN_* set is empty")
    elif total_burden <= 5:
        ok(f"  ratchet state: HEALTHY ({total_burden} entries grandfathered)")
    else:
        ok(f"  ratchet state: ELEVATED ({total_burden} entries — paydown candidates)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 DRIFT-VOLUME-META STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 3, 4, 5, 6){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
