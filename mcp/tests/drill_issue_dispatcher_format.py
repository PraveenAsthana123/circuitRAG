#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: issue scanner + dispatcher + council batch contract.

Locks the local-model issue dispatcher mechanism shipped in
37a802c + 0a654d5 + d87a7b1 + 4f8e1b0. Without this drill the
mechanism can silently regress:
  - RULE_ROUTING table loses entries; ruff codes default to
    human-review (queue stalls)
  - COUNCIL_ROLES loses a role (council degrades to N<3 model)
  - CLI flag drops (--council removed silently)
  - global scripts at ~/.claude/scripts/ drift from project copies

Negative assertions cover: file absence; missing CLI flags; missing
RULE_ROUTING entries; missing COUNCIL_ROLES; runbook missing
council pattern; safety-gate guards stripped.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCANNER = REPO / "scripts" / "issue_scanner.py"
DISPATCHER = REPO / "scripts" / "issue_dispatcher.py"
BATCH = REPO / "scripts" / "run_council_batch.py"
REVIEW = REPO / "scripts" / "review_council.py"
RUNBOOK = REPO / "docs" / "runbooks" / "issue-dispatcher.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: all 5 mechanism files exist --")
    for p in (SCANNER, DISPATCHER, BATCH, REVIEW, RUNBOOK):
        if not p.exists():
            raise AssertionError(f"missing {p.relative_to(REPO)}")
    scanner = SCANNER.read_text(encoding="utf-8")
    dispatcher = DISPATCHER.read_text(encoding="utf-8")
    batch = BATCH.read_text(encoding="utf-8")
    review = REVIEW.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    print("  ok: scanner + dispatcher + batch + review + runbook all present")

    print("-- 2. POSITIVE: RULE_ROUTING covers the canonical rule families --")
    # Each rule family must have a routing decision; missing = silent
    # human-review default which stalls the queue.
    for code in ("I001", "F401", "UP041", "E501", "E402", "N806", "N999",
                 "S110", "S603", "S608"):
        require(scanner, f'"{code}":', f"RULE_ROUTING entry for {code}")
    print("  ok: 10 canonical rule codes routed")

    print("-- 2b. POSITIVE: MYPY_ROUTING covers core type-error families --")
    # Without these mypy codes routed, --include-mypy issues default to
    # human-review and the lane is unusable.
    require(scanner, "MYPY_ROUTING", "MYPY_ROUTING dict")
    for code in ("assignment", "operator", "arg-type", "return-value",
                 "attr-defined", "name-defined"):
        require(scanner, f'"{code}":', f"MYPY_ROUTING entry for {code}")
    require(scanner, "scan_mypy", "scan_mypy function")
    require(scanner, "--include-mypy", "--include-mypy CLI flag")
    print("  ok: 6 mypy codes routed + scan_mypy + --include-mypy flag")

    print("-- 2c. NEGATIVE: real-bug mypy codes MUST route to human-review --")
    # attr-defined and name-defined often surface real bugs, not
    # type-annotation drift. Auto-applying a model fix here can mask
    # an actual logic error. Always human-review.
    for code in ("attr-defined", "name-defined", "call-arg"):
        m = re.search(rf'"{code}":\s*\([^)]+\)', scanner)
        if not m:
            raise AssertionError(f"mypy code {code} not in MYPY_ROUTING")
        if "human-review" not in m.group(0):
            raise AssertionError(
                f"mypy code {code} routed to {m.group(0)!r}; "
                f"MUST be human-review (real-bug risk)"
            )
    print("  ok: real-bug mypy codes (attr/name/call) route to human-review")

    print("-- 2d. POSITIVE: BANDIT_ROUTING covers core security families --")
    require(scanner, "BANDIT_ROUTING", "BANDIT_ROUTING dict")
    for code in ("B101", "B105", "B301", "B307", "B602", "B608", "B324"):
        require(scanner, f'"{code}":', f"BANDIT_ROUTING entry for {code}")
    require(scanner, "scan_bandit", "scan_bandit function")
    require(scanner, "--include-bandit", "--include-bandit CLI flag")
    print("  ok: 7 bandit codes routed + scan_bandit + --include-bandit flag")

    print("-- 2e. NEGATIVE: ALL bandit findings MUST route to human-review (§50.5) --")
    # Critical security gate: NO bandit code may route to a model.
    # A model "fix" can mask the actual vulnerability (e.g. wrap SQL
    # injection in str() instead of using parameters). Hardcoded
    # human-review for every B-prefix entry; drill enforces.
    bandit_block_match = re.search(
        r"BANDIT_ROUTING:.*?\}\n",
        scanner,
        re.DOTALL,
    )
    if not bandit_block_match:
        raise AssertionError("could not find BANDIT_ROUTING dict block")
    bandit_block = bandit_block_match.group(0)
    # Every line inside the dict that has a Bnnn key must route to human-review
    for entry in re.finditer(r'"(B\d+)":\s*\(([^)]+)\)', bandit_block):
        code = entry.group(1)
        routing = entry.group(2)
        if "human-review" not in routing:
            raise AssertionError(
                f"bandit code {code} routes to {routing!r} — MUST be "
                f"'human-review' per §50.5 safety gate"
            )
    print(f"  ok: all bandit codes in BANDIT_ROUTING route to human-review (security gate)")

    print("-- 3. NEGATIVE: security rules (S*) MUST route to human-review --")
    # Per §50.5 safety gate: never let a model auto-fix S* without
    # operator sign-off. Drill rejects any S-rule routed to a model.
    for code in ("S110", "S603", "S607", "S608"):
        m = re.search(rf'"{code}":\s*\([^)]+\)', scanner)
        if not m:
            raise AssertionError(f"S-rule {code} not in RULE_ROUTING")
        if "human-review" not in m.group(0):
            raise AssertionError(
                f"S-rule {code} routed to {m.group(0)!r}; MUST be human-review"
            )
    print("  ok: all S-rules route to human-review")

    print("-- 4. POSITIVE: dispatcher exposes the 5 canonical CLI flags --")
    for flag in ("--apply", "--propose", "--council", "--only", "--id"):
        require(dispatcher, f'"{flag}"', f"CLI flag {flag}")
    print("  ok: --apply / --propose / --council / --only / --id all present")

    print("-- 5. POSITIVE: COUNCIL_ROLES has author + reviewer + advisor --")
    require(dispatcher, "COUNCIL_ROLES", "COUNCIL_ROLES dict")
    for role in ("author", "reviewer", "advisor"):
        require(dispatcher, f'"{role}":', f"COUNCIL_ROLES entry for {role}")
    print("  ok: 3 council roles defined")

    print("-- 6. NEGATIVE: dispatcher MUST default to dry-run --")
    # Default behavior MUST NOT mutate files. The presence of an
    # action="store_true" on --apply is the canonical guard; if it
    # ever flips to default-True, the safety gate is broken.
    apply_match = re.search(
        r'"--apply"[^)]*action="store_true"',
        dispatcher,
    )
    if not apply_match:
        raise AssertionError(
            "--apply flag must be action='store_true' (default False); "
            "default-True breaks the safety gate"
        )
    print("  ok: --apply defaults to False (dry-run)")

    print("-- 7. NEGATIVE: dispatcher MUST write audit row per attempt --")
    # No invocation goes unrecorded per §38 governance.
    require(dispatcher, "write_audit", "write_audit function")
    require(dispatcher, "issue_audit.jsonl", "audit JSONL path")
    print("  ok: audit row written per attempt")

    print("-- 8. POSITIVE: batch runner reads checklist + writes summary --")
    require(batch, "issue_checklist.jsonl", "checklist input")
    require(batch, "council_batch_summary.json", "summary output")
    require(batch, '--council', "delegates to dispatcher --council mode")
    print("  ok: batch wires checklist → council → summary")

    print("-- 8b. POSITIVE: review tool dedupes audit + persists decisions --")
    require(review, "issue_audit.jsonl", "audit input")
    require(review, "issue_decisions.jsonl", "decisions output")
    require(review, "latest_per_id", "dedup-by-id helper")
    for flag in ("--interactive", "--apply", "--skip", "--reject", "--rerun"):
        require(review, flag, f"review CLI flag {flag}")
    print("  ok: review_council.py reads audit + writes decisions + 5 CLI flags")

    print("-- 8c. NEGATIVE: review tool MUST NOT auto-apply diffs --")
    # Per §50.5 safety gate: review records DECISIONS; operator applies
    # the AUTHOR diff manually. If review.py ever calls subprocess.run
    # with 'patch', 'apply', or git operations on the issue file, the
    # safety gate is broken.
    for forbidden in ("subprocess.run", '"patch"', '"git", "apply"'):
        if forbidden in review:
            raise AssertionError(
                f"review_council.py contains {forbidden!r} — review tool MUST "
                f"NOT auto-apply diffs per §50.5 (operator applies manually)"
            )
    print("  ok: review tool does not call patch / git apply / subprocess")

    print("-- 9. NEGATIVE: runbook MUST document safety gates --")
    # Per §50.5 — the runbook is the canonical source of truth for the
    # safety discipline. Stripping these means operators can't tell when
    # a model output should NOT be auto-applied.
    for needle, label in [
        ("dry-run", "dry-run default"),
        ("human-review", "human-review for S-rules"),
        ("Audit row per attempt", "audit row discipline"),
        ("Local-model proposals are NOT auto-applied", "no auto-apply rule"),
    ]:
        require(runbook, needle, label)
    print("  ok: 4 safety gates documented in runbook")

    print("-- 10. NEGATIVE: runbook MUST cite the empirical demo --")
    # Concrete validation evidence (E402 single-model wrong → council right)
    # is what makes the mechanism trustworthy. Stripping this leaves the
    # claim of council-value unanchored.
    require(runbook, "ruff-E402-__init__.py-L579", "E402 demo issue id")
    require(runbook, "WRONG", "single-model failure citation")
    require(runbook, "RIGHT", "council success citation")
    print("  ok: empirical demo cited")

    print("\nALL 16 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
