#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Research-agent integration into council (Tier 1 #1.4).

Locks the contract that research-agent (qwen2.5) fires BEFORE
AUTHOR (deepseek-coder) for investigation rules, and that AUTHOR's
prompt embeds the research brief.

Per CLAUDE.md §43 + §55. Empirical session evidence: F841 council
proposed wrong fix (set False instead of remove) because AUTHOR had
no investigation context. The research-agent step closes that gap.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "local_council.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("local_council", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load local_council from {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["local_council"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: COUNCIL_ROLES has 4 entries (researcher + author + reviewer + advisor) --")
    lc = _load()
    expected = {"researcher", "author", "reviewer", "advisor"}
    actual = set(lc.COUNCIL_ROLES.keys())
    if actual != expected:
        print(f"x step 1: roles mismatch — expected {expected}, got {actual}")
        return 1
    print(f"  ok: 4 roles present ({sorted(actual)})")

    print("-- 2. POSITIVE: researcher uses qwen2.5 model --")
    researcher = lc.COUNCIL_ROLES["researcher"]
    if "qwen2.5" not in researcher["model"]:
        print(f"x step 2: researcher must use qwen2.5; got {researcher['model']}")
        return 1
    if "RESEARCHER" not in researcher["system"]:
        print(f"x step 2: researcher system prompt missing 'RESEARCHER' marker")
        return 1
    print(f"  ok: researcher = {researcher['model']}")

    print("-- 3. NEGATIVE: _researcher_prompt embeds context + grep refs + 4 rule fields --")
    issue = {
        "id": "ruff-F841-test_target.py-L42",
        "code": "F841",
        "file": "scripts/test_target.py",
        "line": 42,
        "message": "Local variable `unused_var` is assigned but never used",
    }
    prompt = lc._researcher_prompt(issue, "  42: unused_var = 5", "scripts/foo.py:10:unused_var = 3")
    for marker in ("F841", "scripts/test_target.py:42", "unused_var", "Investigate"):
        if marker not in prompt:
            print(f"x step 3: researcher prompt missing {marker!r}")
            return 1
    if "Reply with 3-6 lines" not in prompt:
        print(f"x step 3: researcher prompt missing reply-format spec")
        return 1
    print(f"  ok: researcher prompt has all rule fields + format directive")

    print("-- 4. NEGATIVE: _author_prompt EMBEDS research_brief when provided --")
    brief = "TEST BRIEF: dead code; safe to delete; no risks"
    prompt = lc._author_prompt(issue, "  42: x = 5", grep_refs="", research_brief=brief)
    if "Research brief" not in prompt:
        print(f"x step 4: AUTHOR prompt missing 'Research brief' section")
        return 1
    if brief not in prompt:
        print(f"x step 4: AUTHOR prompt missing the actual brief content")
        return 1
    print(f"  ok: AUTHOR prompt embeds research brief inside fenced block")

    print("-- 5. NEGATIVE: _author_prompt OMITS research section when brief is empty --")
    prompt = lc._author_prompt(issue, "  42: x = 5", grep_refs="", research_brief="")
    if "Research brief" in prompt:
        print(f"x step 5: AUTHOR prompt has 'Research brief' section even when brief=''")
        return 1
    print(f"  ok: empty brief → no research section in AUTHOR prompt (don't bloat)")

    print("-- 6. NEGATIVE: investigation rules trigger researcher; mechanical do NOT --")
    sys.path.insert(0, str(REPO / "scripts"))
    from rule_fix_strategy import get_strategy  # type: ignore
    if not get_strategy("F841").needs_grep_refs:
        print(f"x step 6: F841 must trigger researcher (needs_grep_refs=True)")
        return 1
    if get_strategy("UP035").needs_grep_refs:
        print(f"x step 6: UP035 must NOT trigger researcher (mechanical rule)")
        return 1
    if get_strategy("E702").needs_grep_refs:
        print(f"x step 6: E702 must NOT trigger researcher (style rule)")
        return 1
    print(f"  ok: F841 → researcher fires; UP035/E702 → researcher skipped (token savings)")

    print("-- 7. NEGATIVE: run_local_council source MUST gate researcher on needs_grep_refs --")
    src = MODULE_PATH.read_text(encoding="utf-8")
    if "if strategy.needs_grep_refs and grep_refs:" not in src:
        print(f"x step 7: run_local_council missing the strategy.needs_grep_refs gate")
        return 1
    if "RESEARCHER" not in src or "research_brief" not in src:
        print(f"x step 7: run_local_council missing RESEARCHER step or research_brief variable")
        return 1
    print(f"  ok: researcher step gated correctly; only fires when strategy demands")

    print("-- 8. POSITIVE: researcher errors fall back to empty brief (AUTHOR still proceeds) --")
    if "research_brief = \"\"  # AUTHOR proceeds without brief" not in src:
        print(f"x step 8: missing graceful fallback comment + behavior")
        return 1
    print(f"  ok: researcher error → empty brief; AUTHOR not blocked (graceful degradation)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
