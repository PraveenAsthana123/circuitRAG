# RESOURCES: readonly
"""
Drill: 5-role aliasing layer for the local council.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous
loop one-thing-per-iter), §45.4 (no checkbox flips without code),
§47 (architecture: explicit aliases stay reversible).

Architecture matrix listed Agent Council / 5-role rename
(Planner/Retriever/Risk/Evaluator/Writer) as ⚠️ PLANNED. Iter-34 ships
the aliasing layer:

  Planner   → author    Risk      → reviewer
  Retriever → researcher Evaluator → advisor
  Writer    → author    (5th role; same model lane as Planner,
                         splittable later without rewiring callers)

Locks (positive):
  L1. resolve_role() exists + is callable
  L2. All 5 alias names resolve to their canonical 4-role keys
  L3. The 4-role canonical keys still resolve identity (back-compat)

Locks (negative — ≥3 per §43):
  N1. Unknown role label raises KeyError (no silent fallback —
      typos must surface)
  N2. The alias map has EXACTLY 5 entries (the 5-role contract;
      growth is a deliberate ADR change)
  N3. Each canonical target IS a real key in COUNCIL_ROLES
      (alias pointing at a phantom role would make resolve_role
      pass static checks but blow up on actual council runs)
  N4. Aliases are case-insensitive (operator UX; "planner" ==
      "Planner" == "PLANNER")
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    import local_council  # type: ignore[import-not-found]

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: resolve_role() exists + is callable
    # ------------------------------------------------------------------
    step("1. resolve_role() exists in local_council")
    if not callable(getattr(local_council, "resolve_role", None)):
        fail("local_council.resolve_role is missing or not callable")
    ok("resolve_role() is callable")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: all 5 aliases resolve to canonical 4-role keys
    # ------------------------------------------------------------------
    step("2. all 5 aliases resolve to their canonical 4-role keys")
    expected = {
        "Planner": "author",
        "Retriever": "researcher",
        "Risk": "reviewer",
        "Evaluator": "advisor",
        "Writer": "author",
    }
    for alias, canonical in expected.items():
        got = local_council.resolve_role(alias)
        if got != canonical:
            fail(
                f"alias {alias!r} resolved to {got!r}, expected {canonical!r}"
            )
    ok(f"5/5 aliases resolve correctly: {expected}")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: 4-role canonical keys are identity (back-compat)
    # ------------------------------------------------------------------
    step("3. 4-role canonical keys resolve to themselves (identity)")
    for canonical in ("researcher", "author", "reviewer", "advisor"):
        got = local_council.resolve_role(canonical)
        if got != canonical:
            fail(f"canonical {canonical!r} resolved to {got!r} (identity broken)")
    ok("4-role canonical keys preserve identity (back-compat held)")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: unknown label raises KeyError (no silent fallback)
    # ------------------------------------------------------------------
    step("4. NEGATIVE: unknown role label raises KeyError")
    try:
        local_council.resolve_role("Architect")  # not in 4-role or 5-role
        fail("resolve_role('Architect') did NOT raise — silent fallback?")
    except KeyError as exc:
        msg = str(exc)
        if "Architect" not in msg:
            fail(f"KeyError doesn't mention the unknown name: {msg[:200]}")
        # Should also list the valid roles for operator UX
        if "5-role" not in msg or "4-role" not in msg:
            fail(
                f"KeyError doesn't list valid 4-role + 5-role options; "
                f"operator can't recover. msg: {msg[:300]}"
            )
        ok("KeyError raised with valid-options hint")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: alias map has EXACTLY 5 entries
    # ------------------------------------------------------------------
    step("5. NEGATIVE: COUNCIL_ROLE_ALIASES has exactly 5 entries (5-role)")
    actual_count = len(local_council.COUNCIL_ROLE_ALIASES)
    if actual_count != 5:
        fail(
            f"COUNCIL_ROLE_ALIASES has {actual_count} entries, expected 5. "
            f"Adding/removing requires a deliberate ADR change."
        )
    ok("alias map has exactly 5 entries (Planner/Retriever/Risk/Evaluator/Writer)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: each canonical target is a real COUNCIL_ROLES key
    # ------------------------------------------------------------------
    step("6. NEGATIVE: every alias target is a real COUNCIL_ROLES key")
    valid_keys = set(local_council.COUNCIL_ROLES)
    for alias, canonical in local_council.COUNCIL_ROLE_ALIASES.items():
        if canonical not in valid_keys:
            fail(
                f"alias {alias!r} → {canonical!r}, but {canonical!r} "
                f"is NOT in COUNCIL_ROLES ({sorted(valid_keys)}). Phantom "
                f"target would blow up on actual council runs."
            )
    ok("all 5 aliases point at real COUNCIL_ROLES keys")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: aliases are case-insensitive
    # ------------------------------------------------------------------
    step("7. NEGATIVE: aliases are case-insensitive (operator UX)")
    for variant in ("planner", "PLANNER", "Planner", "PlAnNeR"):
        got = local_council.resolve_role(variant)
        if got != "author":
            fail(
                f"case variant {variant!r} resolved to {got!r}, expected 'author'"
            )
    ok("case variants planner/PLANNER/Planner/PlAnNeR all resolve to 'author'")

    print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
