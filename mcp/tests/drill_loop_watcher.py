#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: LoopWatcher applies policy_approver's rules deterministically.

The policy_approver agent (services/sidecar-advisor/agents/
policy_approver.py) declares 5 rules. The LoopWatcher (services/
sidecar-advisor/loop_watcher.py) implements them as pure-Python
gating without an LLM call.

Eight steps. Six negative assertions.

  1. APPROVE: pre-approved files + green drills + no thrash.
  2. NEGATIVE: rule 1 - drill failed -> REJECT, rule_fired=1.
  3. NEGATIVE: rule 2 - 'never' file (.env) -> REJECT, rule_fired=2.
  4. NEGATIVE: rule 3 - 'gated' file without scope ext -> HOLD,
     rule_fired=3.
  5. APPROVE: gated file WITH scope-extension granted in §7.
  6. NEGATIVE: rule 5 - same file in 3+ consecutive commits -> HOLD,
     rule_fired=5.
  7. NEGATIVE: empty files_touched -> APPROVE (no crash).
  8. NEGATIVE: rule order priority - drill_failed AND never-file
     simultaneous: REJECT with rule_fired=1 (drill is first rule).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def _load_watcher():
    p = REPO / "services" / "sidecar-advisor" / "loop_watcher.py"
    spec = importlib.util.spec_from_file_location("loop_watcher", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loop_watcher"] = mod
    spec.loader.exec_module(mod)
    return mod


lw = _load_watcher()
LoopWatcher = lw.LoopWatcher
CommitContext = lw.CommitContext
DrillContext = lw.DrillContext
file_disposition = lw.file_disposition


def main():
    # Step 1: happy path
    step("1. APPROVE: pre-approved files + green drills + no thrash")
    watcher = LoopWatcher()
    decision = watcher.decide(
        commit=CommitContext(
            sha="abc123",
            message="feat: add new agent",
            files_touched=[
                "services/sidecar-advisor/agents/new_agent.py",
                "mcp/tests/drill_new_agent.py",
                "docs/NEXT_POLICY.md",
            ],
        ),
        drills=DrillContext(failed_drills=[], total_drills=27),
    )
    if decision.verdict != "APPROVE":
        fail(f"expected APPROVE, got {decision.verdict}: {decision.reason}")
    if decision.rule_fired != 6:
        fail(f"rule_fired should be 6 (default), got {decision.rule_fired}")
    ok(f"verdict={decision.verdict} rule_fired={decision.rule_fired}")

    # Step 2: NEGATIVE - rule 1 drill failed
    step("2. NEGATIVE: rule 1 - drill failed -> REJECT, rule_fired=1")
    decision = watcher.decide(
        commit=CommitContext(
            sha="def456",
            message="feat: add thing",
            files_touched=["services/sidecar-advisor/foo.py"],
        ),
        drills=DrillContext(
            failed_drills=["drill_sidecar_advisor"],
            total_drills=27,
        ),
    )
    if decision.verdict != "REJECT":
        fail(f"expected REJECT on drill failure, got {decision.verdict}")
    if decision.rule_fired != 1:
        fail(f"rule_fired should be 1, got {decision.rule_fired}")
    if "drill_failed" not in decision.reason:
        fail(f"reason missing 'drill_failed': {decision.reason}")
    if "drill_sidecar_advisor" not in decision.reason:
        fail(f"reason should name failed drill: {decision.reason}")
    ok(f"verdict={decision.verdict} reason={decision.reason!r}")

    # Step 3: NEGATIVE - rule 2 'never' file
    step("3. NEGATIVE: rule 2 - 'never' file (.env) -> REJECT")
    decision = watcher.decide(
        commit=CommitContext(
            sha="evil1",
            message="oops: committed env",
            files_touched=[
                "services/sidecar-advisor/foo.py",
                ".env.production",   # NEVER
            ],
        ),
        drills=DrillContext(failed_drills=[], total_drills=27),
    )
    if decision.verdict != "REJECT":
        fail(f"expected REJECT on .env, got {decision.verdict}")
    if decision.rule_fired != 2:
        fail(f"rule_fired should be 2, got {decision.rule_fired}")
    if ".env.production" not in decision.blocking_files:
        fail(f".env.production should be in blocking_files: {decision.blocking_files}")
    if "absolute_block" not in decision.reason:
        fail(f"reason should say 'absolute_block': {decision.reason}")
    ok(f"verdict={decision.verdict} blocking={decision.blocking_files}")

    # Step 4: NEGATIVE - rule 3 'gated' without scope ext
    step("4. NEGATIVE: rule 3 - 'gated' file (frontend/) without scope ext -> HOLD")
    decision = watcher.decide(
        commit=CommitContext(
            sha="gat1",
            message="feat: change frontend",
            files_touched=[
                "services/frontend/app/foo.tsx",  # GATED
            ],
        ),
        drills=DrillContext(failed_drills=[], total_drills=27),
    )
    if decision.verdict != "HOLD":
        fail(f"expected HOLD on gated, got {decision.verdict}")
    if decision.rule_fired != 3:
        fail(f"rule_fired should be 3, got {decision.rule_fired}")
    if "services/frontend/app/foo.tsx" not in decision.blocking_files:
        fail(f"frontend file should block: {decision.blocking_files}")
    ok(f"verdict={decision.verdict} blocking={decision.blocking_files}")

    # Step 5: APPROVE - gated file WITH scope extension granted
    step("5. APPROVE: gated file with §7 scope-extension granted")
    # Write a synthetic policy file with a granted scope extension
    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", delete=False,
    ) as tmp:
        tmp.write("""# NEXT_POLICY

## 7. Scope-extension log

| Date | Request | Disposition |
|---|---|---|
| 2026-04-28 | Allow frontend edits for Phase 1B Next.js UI | **Granted** |

## 8. Brutal rules
""")
        tmp_path = pathlib.Path(tmp.name)
    try:
        watcher_with_ext = LoopWatcher(policy_path=tmp_path)
        decision = watcher_with_ext.decide(
            commit=CommitContext(
                sha="ext1",
                message="feat(frontend): Next.js UI per scope ext",
                files_touched=["services/frontend/app/admin/sidecar/page.tsx"],
            ),
            drills=DrillContext(failed_drills=[], total_drills=27),
        )
        if decision.verdict != "APPROVE":
            fail(
                f"expected APPROVE with scope ext, got {decision.verdict}: "
                f"{decision.reason}"
            )
        ok(f"verdict={decision.verdict} (scope ext granted overrides rule 3)")
    finally:
        tmp_path.unlink()

    # Step 6: NEGATIVE - rule 5 thrash detection
    step("6. NEGATIVE: rule 5 - same file 3+ consecutive commits -> HOLD")
    # Recent 3 commits all touched docs/NEXT_POLICY.md
    decision = watcher.decide(
        commit=CommitContext(
            sha="thrash1",
            message="docs: update policy AGAIN",
            files_touched=["docs/NEXT_POLICY.md"],
        ),
        drills=DrillContext(failed_drills=[], total_drills=27),
        recent_files_per_commit=[
            ["docs/NEXT_POLICY.md", "other.py"],
            ["docs/NEXT_POLICY.md", "stuff.py"],
            ["docs/NEXT_POLICY.md"],
        ],
    )
    if decision.verdict != "HOLD":
        fail(f"expected HOLD on thrash, got {decision.verdict}: {decision.reason}")
    if decision.rule_fired != 5:
        fail(f"rule_fired should be 5, got {decision.rule_fired}")
    if "iteration_thrash" not in decision.reason:
        fail(f"reason missing 'iteration_thrash': {decision.reason}")
    if "docs/NEXT_POLICY.md" not in decision.blocking_files:
        fail(f"thrash file should block: {decision.blocking_files}")
    ok(f"verdict={decision.verdict} reason={decision.reason!r}")

    # Step 7: NEGATIVE - empty files_touched
    step("7. NEGATIVE: empty files_touched -> APPROVE (no crash)")
    decision = watcher.decide(
        commit=CommitContext(sha="empty1", message="empty", files_touched=[]),
        drills=DrillContext(failed_drills=[], total_drills=27),
    )
    if decision.verdict != "APPROVE":
        fail(f"empty files should APPROVE, got {decision.verdict}")
    ok(f"empty files_touched -> APPROVE")

    # Step 8: NEGATIVE - rule order priority (drill_failed wins over never)
    step(
        "8. NEGATIVE: rule order - drill_failed (rule 1) wins over "
        "never-file (rule 2)"
    )
    decision = watcher.decide(
        commit=CommitContext(
            sha="both1",
            message="catastrophic",
            files_touched=[".env", "secrets.json"],   # NEVER
        ),
        drills=DrillContext(
            failed_drills=["drill_x"],   # ALSO failed
            total_drills=27,
        ),
    )
    if decision.verdict != "REJECT":
        fail(f"both should REJECT, got {decision.verdict}")
    # Drill rule fires first (rule 1), not the never rule (rule 2)
    if decision.rule_fired != 1:
        fail(
            f"expected rule_fired=1 (drill priority), got "
            f"{decision.rule_fired}. The drill failure must take "
            f"priority over the never-file check - drill failure is "
            f"the more pressing alert."
        )
    ok(f"rule order: rule 1 (drill) fires before rule 2 (never)")

    # Final sanity: file_disposition function directly
    step("Bonus: file_disposition function spot-check")
    cases = [
        ("services/sidecar-advisor/foo.py", "pre-approved"),
        ("libs/py/documind_core/x.py", "pre-approved"),
        ("mcp/tests/drill_x.py", "pre-approved"),
        ("docs/anything.md", "pre-approved"),
        (".env", "never"),
        (".env.local", "never"),
        ("foo.key", "never"),
        ("services/frontend/x.tsx", "gated"),
        ("services/governance-svc/y.py", "gated"),
        (".github/workflows/ci.yml", "gated"),
        ("random/unknown/path.py", "unknown"),
    ]
    for path, expected in cases:
        actual = file_disposition(path)
        if actual != expected:
            fail(f"file_disposition({path!r}) = {actual!r}, expected {expected!r}")
    ok(f"file_disposition: {len(cases)}/{len(cases)} paths classified correctly")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 LOOP-WATCHER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
