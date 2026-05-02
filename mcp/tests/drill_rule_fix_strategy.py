#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: per-rule fix-strategy table (Tier 1 #1.3) — both directions.

Locks the strategy-table contract per CLAUDE.md §43 + §55.

Empirical session evidence: ONE generic prompt for F841 (real-bug
investigation) and UP035 (mechanical replace) and E702 (literal
split) is wrong; council quality cratered. This module routes each
rule code to a category-specific prompt + appropriate context window.

Eight steps. Six negative assertions covering each empirical
miscategorization mode.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "rule_fix_strategy.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("rule_fix_strategy", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load rule_fix_strategy from {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rule_fix_strategy"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: rule_fix_strategy module imports + 5 exports --")
    rs = _load()
    for name in ("RuleStrategy", "RULE_STRATEGIES", "DEFAULT_STRATEGY",
                 "PROMPT_TEMPLATES", "get_strategy", "get_prompt_template",
                 "is_human_only", "SECURITY_PREFIXES"):
        if not hasattr(rs, name):
            print(f"x step 1: missing export {name}")
            return 1
    print(f"  ok: 8 exports present; {len(rs.RULE_STRATEGIES)} rules in dispatch table")

    print("-- 2. POSITIVE: F841 routes to investigation category --")
    s = rs.get_strategy("F841")
    if s.category != "investigation":
        print(f"x step 2: F841 expected investigation; got {s.category!r}")
        return 1
    if not s.needs_grep_refs:
        print(f"x step 2: F841 must needs_grep_refs=True (real-bug-or-not requires references)")
        return 1
    if s.context_lines < 20:
        print(f"x step 2: F841 needs ≥20 context_lines; got {s.context_lines}")
        return 1
    print(f"  ok: F841 → investigation, ±{s.context_lines} lines, grep_refs=True")

    print("-- 3. POSITIVE: UP035 routes to mechanical_rewrite category --")
    s = rs.get_strategy("UP035")
    if s.category != "mechanical_rewrite":
        print(f"x step 3: UP035 expected mechanical_rewrite; got {s.category!r}")
        return 1
    if s.needs_grep_refs:
        print(f"x step 3: UP035 must NOT need grep_refs (it's literal — wastes tokens)")
        return 1
    if s.context_lines > 10:
        print(f"x step 3: UP035 only needs ≤10 context_lines; got {s.context_lines}")
        return 1
    print(f"  ok: UP035 → mechanical_rewrite, ±{s.context_lines} lines, no grep")

    print("-- 4. NEGATIVE: B110 (bandit) → human-only (NEVER to model) --")
    s = rs.get_strategy("B110")
    if s.model_tier != "human":
        print(f"x step 4: B110 must route to human; got {s.model_tier!r}. "
              "Per §50.5.3 bandit B* NEVER goes to a model.")
        return 1
    if not rs.is_human_only("B110"):
        print(f"x step 4: is_human_only('B110') must be True")
        return 1
    print(f"  ok: B110 (bandit) → human-only via SECURITY_PREFIXES")

    print("-- 5. NEGATIVE: S101 (ruff security) → human-only --")
    s = rs.get_strategy("S101")
    if s.model_tier != "human":
        print(f"x step 5: S101 must route to human; got {s.model_tier!r}")
        return 1
    if not rs.is_human_only("S101"):
        print(f"x step 5: is_human_only('S101') must be True")
        return 1
    print(f"  ok: S101 (ruff security) → human-only via SECURITY_PREFIXES")

    print("-- 6. NEGATIVE: unknown rule code → DEFAULT (conservative fallback) --")
    s = rs.get_strategy("XYZQ999")
    if s.category != "default":
        print(f"x step 6: unknown rule must fall back to default; got {s.category!r}")
        return 1
    if s.model_tier == "human":
        print(f"x step 6: unknown should NOT go to human (only S*/B* should)")
        return 1
    print(f"  ok: unknown rule → default category, model_tier={s.model_tier}")

    print("-- 7. NEGATIVE: get_prompt_template returns each category's template --")
    expected_categories = {"investigation", "mechanical_rewrite", "import_sort",
                           "type_fix", "frontend_jsx", "default"}
    actual = set(rs.PROMPT_TEMPLATES.keys())
    if not expected_categories.issubset(actual):
        missing = expected_categories - actual
        print(f"x step 7: PROMPT_TEMPLATES missing categories: {missing}")
        return 1
    # Each template must have <role>, <goal>, <rules>
    for cat, template in rs.PROMPT_TEMPLATES.items():
        for marker in ("<role>", "<goal>", "<rules>"):
            if marker not in template:
                print(f"x step 7: template {cat!r} missing marker {marker!r}")
                return 1
    print(f"  ok: 6 templates × 3 mandatory markers (<role>/<goal>/<rules>) all present")

    print("-- 8. POSITIVE: empty rule code → DEFAULT (no crash) --")
    s = rs.get_strategy("")
    if s.category != "default":
        print(f"x step 8: empty code must yield default; got {s.category!r}")
        return 1
    s = rs.get_strategy(None)  # type: ignore[arg-type]  # explicit guard
    if s.category != "default":
        print(f"x step 8: None code must yield default; got {s.category!r}")
        return 1
    print("  ok: empty/None rule code → default; no crash")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
