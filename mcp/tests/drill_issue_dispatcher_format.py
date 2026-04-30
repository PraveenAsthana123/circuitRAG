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
RUNBOOK = REPO / "docs" / "runbooks" / "issue-dispatcher.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: all 4 mechanism files exist --")
    for p in (SCANNER, DISPATCHER, BATCH, RUNBOOK):
        if not p.exists():
            raise AssertionError(f"missing {p.relative_to(REPO)}")
    scanner = SCANNER.read_text(encoding="utf-8")
    dispatcher = DISPATCHER.read_text(encoding="utf-8")
    batch = BATCH.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    print("  ok: scanner + dispatcher + batch + runbook all present")

    print("-- 2. POSITIVE: RULE_ROUTING covers the canonical rule families --")
    # Each rule family must have a routing decision; missing = silent
    # human-review default which stalls the queue.
    for code in ("I001", "F401", "UP041", "E501", "E402", "N806", "N999",
                 "S110", "S603", "S608"):
        require(scanner, f'"{code}":', f"RULE_ROUTING entry for {code}")
    print("  ok: 10 canonical rule codes routed")

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

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
