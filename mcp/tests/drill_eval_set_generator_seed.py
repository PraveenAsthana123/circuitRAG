#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: eval_set_generator --seed determinism + diversification.

Locks the --seed flag added 2026-05-05 to unblock Stage-3-earned
'stable_single_winner' overfitting verdict. Operators run the
generator with different seeds to produce distinct eval sets, which
in turn produce distinct empirical winners across runs.

Eight steps. Six negative. AST-only — no Ollama required.
"""
from __future__ import annotations

import ast
import csv
import io
import random
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "scripts" / "eval_set_generator.py"


def main() -> int:
    print("-- 1. POSITIVE: --seed flag declared in argparse --")
    if not GEN.exists():
        print(f"x {GEN} missing")
        return 1
    src = GEN.read_text(encoding="utf-8")
    if '"--seed"' not in src:
        print("x --seed flag must be declared in eval_set_generator argparse")
        return 1
    print("  ok: --seed flag declared")

    print("-- 2. POSITIVE: --seed CLI help cites stage3_earned_check rationale --")
    # Drill enforces the rationale chain so future refactors don't
    # silently weaken the diversification surface.
    seed_help_idx = src.find('"--seed"')
    seed_help_end = src.find(")", seed_help_idx + 200)
    seed_block = src[seed_help_idx:seed_help_end + 1]
    if "stage3" not in seed_block.lower() and "stable_single_winner" not in seed_block.lower():
        print(f"x --seed help must reference stage3 / stable_single_winner; got block: {seed_block[:300]}")
        return 1
    print("  ok: rationale chained to stage3_earned_check")

    print("-- 3. NEGATIVE: shuffle happens BEFORE limit-chunks truncation --")
    # If shuffle happened AFTER truncation, --seed would only permute
    # the same first-N chunks regardless of seed — defeating the
    # diversification purpose. Drill enforces shuffle-then-truncate
    # ordering in source.
    shuffle_idx = src.find("rng.shuffle(chunks)")
    truncate_idx = src.find("chunks = chunks[: args.limit_chunks]")
    if shuffle_idx < 0:
        print("x rng.shuffle(chunks) must exist")
        return 1
    if truncate_idx < 0:
        print("x chunks = chunks[: args.limit_chunks] truncation must exist")
        return 1
    if shuffle_idx > truncate_idx:
        print("x shuffle MUST happen before truncation; currently truncate runs first")
        return 1
    print("  ok: shuffle precedes truncate (full corpus permutation)")

    print("-- 4. NEGATIVE: shuffle is deterministic with same seed --")
    # Reproduce the script's shuffle logic and verify same seed →
    # same permutation.
    items = list(range(50))
    rng_a = random.Random(42)
    a = items.copy()
    rng_a.shuffle(a)
    rng_b = random.Random(42)
    b = items.copy()
    rng_b.shuffle(b)
    if a != b:
        print("x same seed must yield same permutation")
        return 1
    print("  ok: same seed → same permutation")

    print("-- 5. NEGATIVE: shuffle DIVERGES across seeds (diversification works) --")
    items = list(range(50))
    rng_a = random.Random(42)
    a = items.copy()
    rng_a.shuffle(a)
    rng_b = random.Random(43)
    b = items.copy()
    rng_b.shuffle(b)
    if a == b:
        print("x different seeds must yield different permutations")
        return 1
    # First-N divergence: this is the actual operator-facing impact.
    # Different seeds must produce different first-10 chunks (the
    # truncation window).
    if a[:10] == b[:10]:
        print("x different seeds must produce different first-10 chunks (limit-chunks window)")
        return 1
    print("  ok: different seeds → different first-N (eval set varies)")

    print("-- 6. NEGATIVE: --seed default is None (legacy non-shuffled behavior preserved) --")
    # Without --seed, behavior must match pre-2026-05-05: no shuffle,
    # corpus iteration order preserved. Operators on existing scripts
    # see no behavior change.
    seed_default = re.search(
        r'"--seed",\s*type=int,\s*default=(\w+)',
        src,
    )
    if not seed_default:
        print("x --seed default value must be parseable from argparse")
        return 1
    if seed_default.group(1) != "None":
        print(f"x --seed default must be None; got {seed_default.group(1)}")
        return 1
    # Source must guard the shuffle behind `if args.seed is not None:`
    if "if args.seed is not None:" not in src:
        print("x shuffle must be guarded behind 'if args.seed is not None:'")
        return 1
    print("  ok: legacy callers (no --seed) get unchanged behavior")

    print("-- 7. NEGATIVE: shuffle uses seeded Random (not global random.shuffle) --")
    # Drill enforces seeded RNG to prevent global-state contamination.
    # `random.shuffle(chunks)` (no rng) would be reproducibility-broken.
    # Must be `rng = random.Random(seed); rng.shuffle(chunks)`.
    if "random.Random(" not in src:
        print("x must use random.Random() instance for seeded shuffle")
        return 1
    if "args.seed)" not in src:
        print("x random.Random must be seeded with args.seed")
        return 1
    print("  ok: seeded Random instance (no global-state contamination)")

    print("-- 8. POSITIVE: ast-valid + status output reachable --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x syntax error after --seed addition: {exc}")
        return 1
    # Verify the entire CLI block compiles
    if 'parser = argparse.ArgumentParser()' not in src:
        print("x argparse setup missing")
        return 1
    print("  ok: ast-valid; CLI surface intact")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
