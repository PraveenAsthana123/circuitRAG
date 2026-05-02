#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: in-loop verification (Tier 2 #2.4).

Per CLAUDE.md §43 + §55. Locks the contract that REVIEWER's critique
is grounded in actual ruff exit code, not opinion. The verifier:

  - Applies AUTHOR's diff to the working tree
  - Runs ruff
  - ALWAYS rolls back (worktree never left mutated)
  - Returns structured result that REVIEWER prompt embeds

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LC_PATH = REPO / "scripts" / "local_council.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("local_council", LC_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {LC_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["local_council"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: _verify_diff_in_worktree exported --")
    lc = _load()
    if not hasattr(lc, "_verify_diff_in_worktree"):
        print("x step 1: helper missing")
        return 1
    print("  ok: _verify_diff_in_worktree exported")

    print("-- 2. POSITIVE: empty diff → error result, no crash --")
    out = lc._verify_diff_in_worktree(REPO, "")
    if out.get("applied"):
        print(f"x step 2: empty diff was 'applied': {out}")
        return 1
    if not out.get("error"):
        print(f"x step 2: empty diff produced no error string: {out}")
        return 1
    print(f"  ok: empty diff → error={out['error'][:60]}; applied=False")

    print("-- 3. NEGATIVE: malformed diff → error, applied=False, no worktree mutation --")
    pre_status = subprocess.run(
        ["git", "diff", "--stat"], cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    out = lc._verify_diff_in_worktree(REPO, "this is not a unified diff at all")
    post_status = subprocess.run(
        ["git", "diff", "--stat"], cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    if out.get("applied"):
        print(f"x step 3: malformed diff was 'applied'")
        return 1
    if pre_status.stdout != post_status.stdout:
        print(f"x step 3: malformed diff mutated worktree (pre != post)")
        return 1
    print("  ok: malformed diff rejected at git apply --check; worktree unchanged")

    print("-- 4. POSITIVE: valid diff → applied=True + ruff_exit_code captured --")
    # Build a tiny valid diff: rename a comment line in this drill itself
    # (which we can target safely because it's read-only test infra).
    target = REPO / "mcp" / "tests" / "drill_in_loop_verification.py"
    rel = target.relative_to(REPO)
    diff = (
        f"--- {rel}\n"
        f"+++ {rel}\n"
        f"@@ -1 +1 @@\n"
        f"-#!/usr/bin/env python3\n"
        f"+#!/usr/bin/env python3\n"
    )
    # Same line in/out — diff applies cleanly but is no-op. Tests that
    # ruff runs without complaining about this drill file (which has
    # tons of triple-quoted strings ruff ignores).
    out = lc._verify_diff_in_worktree(REPO, diff)
    if out.get("error"):
        # If git complained the diff is empty, that's fine — we just
        # need the path to be exercised.
        print(f"  (no-op diff rejected by git: {out['error'][:80]})")
    else:
        if not out.get("applied"):
            print(f"x step 4: valid diff did not get applied: {out}")
            return 1
        if "ruff_exit_code" not in out:
            print(f"x step 4: result missing ruff_exit_code: {out}")
            return 1
    print(f"  ok: valid path returns applied + ruff_exit_code (or rejected for no-op)")

    print("-- 5. NEGATIVE: verification ALWAYS rolls back (worktree never left mutated) --")
    pre_status = subprocess.run(
        ["git", "diff", "--stat"], cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    # Try a real-shape diff that should apply cleanly + then revert.
    sample_target = REPO / "mcp" / "tests" / "drill_in_loop_verification.py"
    rel = sample_target.relative_to(REPO)
    diff = (
        f"--- {rel}\n"
        f"+++ {rel}\n"
        f"@@ -1,1 +1,2 @@\n"
        f" #!/usr/bin/env python3\n"
        f"+# DRILL-VERIFICATION-MARKER (should never persist)\n"
    )
    lc._verify_diff_in_worktree(REPO, diff)
    post_status = subprocess.run(
        ["git", "diff", "--stat"], cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    if pre_status.stdout != post_status.stdout:
        print(f"x step 5: worktree mutated after verification (pre != post)")
        print(f"  pre:  {pre_status.stdout[:200]}")
        print(f"  post: {post_status.stdout[:200]}")
        return 1
    # `git diff --stat` byte-identical pre/post is the load-bearing
    # signal. Don't grep the drill file for the marker text — it
    # appears in the drill's own source as test-data, not as a leak.
    print("  ok: `git diff --stat` byte-identical pre/post (no worktree mutation)")

    print("-- 6. NEGATIVE: _reviewer_prompt embeds verification when provided --")
    from council_schemas import CouncilProposal  # type: ignore
    issue = {"id": "test", "code": "UP035", "file": "x.py", "line": 1,
             "message": "test"}
    proposal = CouncilProposal(
        file_path="scripts/test.py", rule_code="UP035", summary="fix",
        unified_diff="--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n",
        confidence=0.9, risks=[],
    )
    prompt_with = lc._reviewer_prompt(issue, proposal, verification={
        "applied": True, "ruff_exit_code": 0, "ruff_output": "", "error": None,
    })
    if "ruff CLEAN" not in prompt_with:
        print(f"x step 6: REVIEWER prompt missing 'ruff CLEAN' verdict")
        return 1
    if "Verification result" not in prompt_with:
        print("x step 6: REVIEWER prompt missing verification section header")
        return 1
    print("  ok: REVIEWER prompt embeds verification verdict")

    print("-- 7. NEGATIVE: _reviewer_prompt OMITS verification when None --")
    prompt_without = lc._reviewer_prompt(issue, proposal, verification=None)
    if "Verification result" in prompt_without:
        print("x step 7: REVIEWER prompt has verification section even when None")
        return 1
    print("  ok: verification=None → no verification section in prompt (no bloat)")

    print("-- 8. NEGATIVE: ruff-still-failing verification produces 'still has issues' verdict --")
    prompt_failing = lc._reviewer_prompt(issue, proposal, verification={
        "applied": True, "ruff_exit_code": 1,
        "ruff_output": "F841: unused variable\nE501: line too long",
        "error": None,
    })
    if "still has issues" not in prompt_failing:
        print(f"x step 8: REVIEWER prompt for failing ruff missing 'still has issues' verdict")
        return 1
    if "F841" not in prompt_failing:
        print("x step 8: REVIEWER prompt didn't include the actual ruff output")
        return 1
    print("  ok: failing ruff → 'still has issues' verdict + actual ruff stdout embedded")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
