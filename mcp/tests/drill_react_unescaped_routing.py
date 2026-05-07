# RESOURCES: readonly
"""
Drill: react/no-unescaped-entities routing post-iter-60 reroute.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-58 detected, iter-59 routed-to-queue framework,
iter-60 reroutes the rule to human-review at the SCANNER level so new
findings stop entering the council retry-storm in the first place),
§45.4 (no checkbox flips without code), §50.5.3 (security/high-failure
rules NEVER to model — go to human-review), §55.3 (outcome contract:
apply rate must trend up; routing the 0%-rule away from the council
will lift council's measured apply rate).

Iter-58's reflection engine found `react_no` rule at 0% apply over 41
attempts. Iter-60 reroutes the scanner so the next 41 attempts don't
happen — the rule lands directly in the human-review bucket.

Locks (positive):
  L1. ESLINT_ROUTING['react/no-unescaped-entities'] is mapped to
      'human-review' (post-iter-60)
  L2. The reroute comment cites iter-58 and iter-60 explicitly so
      future maintainers see WHY the routing changed
  L3. The fix-strategy reference for the rule still exists in
      rule_fix_strategy.py (don't strand the strategy table when
      a future iter ships the deterministic fixer)

Locks (negative — ≥3 per §43):
  N1. Routing target is NOT a model name (no `deepseek-coder:6.7b`,
      `qwen2.5`, `codegemma`, `codellama` — all council lanes are
      explicitly forbidden for this rule until the deterministic
      fixer ships)
  N2. Routing target is NOT 'eslint:autofix' (ESLint deliberately
      does NOT auto-fix this rule — multiple valid replacements;
      claiming auto-fix would silently no-op every attempt)
  N3. The pre-iter-60 council-route comment ('semantic call goes
      to model') is REPLACED, not just commented over — leaving
      both rationales would let a future maintainer revert the
      reroute thinking the prior rationale still held
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCANNER = REPO / "scripts" / "issue_scanner.py"
STRATEGY = REPO / "scripts" / "rule_fix_strategy.py"

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
    if not SCANNER.exists():
        fail(f"missing: {SCANNER.relative_to(REPO)}")
    if not STRATEGY.exists():
        fail(f"missing: {STRATEGY.relative_to(REPO)}")

    src = SCANNER.read_text(encoding="utf-8")
    strategy_src = STRATEGY.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: routing maps to 'human-review'
    # ------------------------------------------------------------------
    step("1. ESLINT_ROUTING['react/no-unescaped-entities'] = 'human-review'")
    # Pattern: '"react/no-unescaped-entities": (..., ..., "human-review")'
    m = re.search(
        r'"react/no-unescaped-entities":\s*\([^,]+,\s*[^,]+,\s*"([^"]+)"\)',
        src,
    )
    if m is None:
        fail(
            "could not locate the react/no-unescaped-entities tuple in "
            "ESLINT_ROUTING — has the routing table refactored?"
        )
    target = m.group(1)
    if target != "human-review":
        fail(
            f"route target is {target!r}, expected 'human-review'. "
            f"Iter-60 reroute was reverted or never landed."
        )
    ok("route target = 'human-review' (council bypass active)")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: reroute comment cites iter-58 + iter-60
    # ------------------------------------------------------------------
    step("2. comment cites iter-58 + iter-60 (provenance preserved)")
    # The reroute comment block must mention BOTH iter-58 (detection)
    # and iter-60 (action) so future maintainers see the chain.
    if "iter-58" not in src:
        fail(
            "no iter-58 reference in source — provenance link to the "
            "reflection-engine finding is missing"
        )
    if "iter-60" not in src:
        fail(
            "no iter-60 reference in source — current-iter provenance "
            "is missing; future maintainers won't know when this "
            "routing changed"
        )
    ok("comment cites iter-58 (finding) + iter-60 (action)")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: fix-strategy entry for the rule still exists
    # ------------------------------------------------------------------
    step("3. rule_fix_strategy.py still has react/no-unescaped-entities entry")
    if "react/no-unescaped-entities" not in strategy_src:
        fail(
            "rule_fix_strategy.py dropped the react/no-unescaped-entities "
            "entry — future iter shipping the deterministic fixer would "
            "have no strategy to attach to. Keep the entry; only the "
            "routing changes."
        )
    ok("strategy entry preserved (future deterministic-fixer iter unblocked)")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: routing target is NOT a model name
    # ------------------------------------------------------------------
    step("4. NEGATIVE: routing target is NOT a council model name")
    forbidden_models = (
        "deepseek-coder",
        "qwen2.5",
        "qwen-",
        "codegemma",
        "codellama",
        "council",
    )
    if any(f in target.lower() for f in forbidden_models):
        fail(
            f"route target {target!r} contains a council model name — "
            f"iter-60's intent was to bypass the council retry storm, "
            f"not redirect to a different model"
        )
    ok("route target is not a model name (council lane bypassed)")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: routing target is NOT 'eslint:autofix'
    # ------------------------------------------------------------------
    step("5. NEGATIVE: route is NOT 'eslint:autofix' (ESLint won't auto-fix this)")
    if target == "eslint:autofix":
        fail(
            "route target = 'eslint:autofix' but ESLint deliberately does "
            "NOT auto-fix react/no-unescaped-entities (multiple valid "
            "replacements). This routing would no-op every attempt and "
            "tank apply_rate without surfacing the issue."
        )
    ok("route is not eslint:autofix (rule isn't ESLint-autofixable)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: prior council-route rationale was REPLACED
    # ------------------------------------------------------------------
    step("6. NEGATIVE: pre-iter-60 'semantic call goes to model' comment is gone")
    # The pre-iter-60 comment said: "semantic call goes to model"
    # If both that comment AND the new 'human-review' comment coexist,
    # a future maintainer could revert thinking the old rationale still
    # held. The iter-60 edit must REPLACE the old rationale.
    if "semantic call goes to model" in src:
        fail(
            "pre-iter-60 rationale 'semantic call goes to model' still in "
            "source — leaving both rationales lets a future maintainer "
            "revert the reroute. The old comment must be REPLACED, not "
            "merely overridden by adjacency."
        )
    ok("prior rationale removed; iter-60 reasoning is the sole source of truth")

    print(f"\n{GREEN}{BOLD}ALL 6 STEPS PASSED (3 positive + 3 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
