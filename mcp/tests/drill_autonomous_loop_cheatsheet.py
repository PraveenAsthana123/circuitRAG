#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: docs/runbooks/autonomous-loop-cheatsheet.md (Phase 6A).

Phase 6A is the session-wide companion to 5BB's telemetry-specific
runbook: pre-approved/gated split, escape hatches, recommended cron
lines, debugging commands. Without the drill it would silently drift
from the policy doc + CLAUDE.md + the actual scripts on disk.

Eight steps. Six negative assertions.

  1. POSITIVE: cheatsheet exists at the canonical path with the
     expected size shape (≥3KB, ≤25KB).
  2. NEGATIVE: every file path in the cheatsheet that points to a
     repo file actually exists. Drift sources: scripts renamed,
     directory restructure. Drill refuses drift.
  3. NEGATIVE: required sections present — activation phrases,
     stop conditions, pre-approved, gated, drill discipline,
     hook chain, cron lines, escape hatches, debugging commands,
     composes-with.
  4. NEGATIVE: pre-approved table does NOT contain known-gated
     verbs. The cheatsheet is the source of truth operators
     reference; if it claims something is pre-approved that
     actually requires confirmation, the operator is misled.
  5. NEGATIVE: gated table covers the high-blast-radius operations
     enumerated in CLAUDE.md §42 (force-push, rm -rf on root dirs,
     prod data drop, external messages, package publish, billing
     mods). Missing one means an operator might assume it's safe.
  6. NEGATIVE: every cron line in the cheatsheet uses a script
     that exists. A typo in a cron line copy-paste wastes the
     operator's day.
  7. NEGATIVE: composes-with footer references the THREE authority
     sources: autonomous-feature-loop.md policy, CLAUDE.md, ADR-014.
     Without these, the cheatsheet is unmoored.
  8. POSITIVE: the cheatsheet's debugging commands include AT LEAST
     three with `tail` / `grep` / `git` (operator's three reflexes
     for any incident). Without these primitives, the cheatsheet
     loses operator value.

Run: python3 mcp/tests/drill_autonomous_loop_cheatsheet.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHEAT = REPO / "docs" / "runbooks" / "autonomous-loop-cheatsheet.md"


def main() -> int:
    if not CHEAT.exists():
        print(f"✗ pre-step: {CHEAT} missing")
        return 1
    body = CHEAT.read_text()

    # ── Step 1: POSITIVE — exists with size shape ──
    size = len(body)
    if size < 3000:
        print(f"✗ step 1: cheatsheet is {size} chars; expected ≥3000")
        return 1
    if size > 25000:
        print(f"✗ step 1: cheatsheet is {size} chars; expected ≤25000 "
              "(should fit on one operator screen, not be a manual)")
        return 1
    print(f"✓ step 1: cheatsheet exists ({size} chars, "
          f"{len(body.splitlines())} lines)")

    # ── Step 2: NEGATIVE — cited file paths exist ──
    # Capture path + trailing char to skip glob patterns (5BB lesson).
    path_re = re.compile(
        r'(?<![\w./])((?:scripts/|mcp/|services/|docs/)'
        r'[a-zA-Z0-9_./\-]+)(.?)'
    )
    paths_to_check = set()
    for m in path_re.finditer(body):
        path, next_char = m.group(1), m.group(2)
        if next_char == "*":
            continue
        path = path.rstrip(",.;:")
        # Skip lines with parentheses or angle brackets — those are
        # documentation-format references, not file refs
        if "(" in path or " " in path:
            continue
        if path in {"scripts/", "mcp/", "services/", "docs/"}:
            continue
        paths_to_check.add(path)
    missing = [p for p in paths_to_check if not (REPO / p).exists()]
    if missing:
        print(f"✗ step 2: cheatsheet references {len(missing)} non-existent "
              f"paths: {sorted(missing)[:5]}")
        return 1
    print(f"✓ step 2: all {len(paths_to_check)} cited file paths exist")

    # ── Step 3: NEGATIVE — required sections ──
    required_keywords = [
        "Activation phrases",
        "Stop conditions",
        "Pre-approved actions",
        "Gated actions",
        "Drill discipline",
        "Pre-commit + post-commit hook chain",
        "Recommended cron lines",
        "Escape hatches",
        "Common debugging commands",
        "Composes with",
    ]
    missing_sections = [k for k in required_keywords if k not in body]
    if missing_sections:
        print(f"✗ step 3: missing required sections: {missing_sections}")
        return 1
    print(f"✓ step 3: all {len(required_keywords)} required sections present")

    # ── Step 4: NEGATIVE — pre-approved doesn't leak gated verbs ──
    # Find the "Pre-approved actions" section (## or ###) and its body.
    pre_match = re.search(
        r"## Pre-approved actions.*?(?=\n## |\Z)", body, re.DOTALL
    )
    if not pre_match:
        print("✗ step 4: 'Pre-approved actions' section not found")
        return 1
    pre_text = pre_match.group(0)
    # Verbs / commands that MUST NOT be in pre-approved
    leaks_to_check = [
        "force-push",
        "force push",
        "rm -rf /",
        "DROP TABLE",
        "DROP DATABASE",
        "git push --force",
        "git push origin main",
        "kubectl delete",
        "terraform destroy",
        "npm publish",
        "pip upload",
        "docker push",
        "send email",
        "post to slack",
        "create PR",
    ]
    # Case-insensitive match
    leaks = [
        v for v in leaks_to_check
        if re.search(re.escape(v), pre_text, re.IGNORECASE)
    ]
    if leaks:
        print(f"✗ step 4: pre-approved section claims gated verbs as safe: "
              f"{leaks}")
        return 1
    print(f"✓ step 4: pre-approved section does NOT leak gated verbs "
          f"(checked {len(leaks_to_check)} red flags)")

    # ── Step 5: NEGATIVE — gated section covers HBR operations ──
    gated_match = re.search(
        r"## Gated actions.*?(?=\n## |\Z)", body, re.DOTALL
    )
    if not gated_match:
        print("✗ step 5: 'Gated actions' section not found")
        return 1
    gated_text = gated_match.group(0).lower()
    # Each of these CONCEPTS must appear in the gated table somewhere.
    # Use loose substring matches because the cheatsheet is prose-y.
    required_concepts = [
        "force-push",          # destructive history
        "rm -rf",              # destructive scope
        "prod",                # prod data
        "external",            # external messaging
        "publish",             # package publish
        "billing",             # billing/auth/secret
    ]
    gated_missing = [c for c in required_concepts if c not in gated_text]
    if gated_missing:
        print(f"✗ step 5: gated section missing HBR concepts: {gated_missing}")
        return 1
    print(f"✓ step 5: gated section covers all {len(required_concepts)} HBR "
          "concepts (operator can't be misled into thinking these are safe)")

    # ── Step 6: NEGATIVE — cron lines reference real scripts ──
    # Find every line in a code block that looks like a cron entry
    # (5 fields + a command). Capture the script path.
    cron_re = re.compile(
        r"^\s*(?:[\d*\-/,]+\s+){5}.*?(/?[\w/_.-]+/[\w_.-]+\.(?:sh|py))",
        re.MULTILINE,
    )
    cron_scripts = set()
    for m in cron_re.finditer(body):
        path = m.group(1)
        # Strip leading absolute prefix to get repo-relative
        if "/mnt/deepa/rag/" in path:
            path = path.split("/mnt/deepa/rag/", 1)[1]
        cron_scripts.add(path)
    if not cron_scripts:
        print("✗ step 6: no cron-line scripts detected in cheatsheet "
              "(parse failure or section moved)")
        return 1
    cron_missing = [p for p in cron_scripts if not (REPO / p).exists()]
    if cron_missing:
        print(f"✗ step 6: cron lines reference non-existent scripts: "
              f"{cron_missing}")
        return 1
    print(f"✓ step 6: all {len(cron_scripts)} cron-line scripts exist on disk")

    # ── Step 7: NEGATIVE — composes-with refs ──
    composes_match = re.search(
        r"## Composes with.*?\Z", body, re.DOTALL
    )
    if not composes_match:
        print("✗ step 7: 'Composes with' section missing")
        return 1
    composes_text = composes_match.group(0)
    required_refs = [
        "autonomous-feature-loop.md",   # the policy
        "CLAUDE.md",                     # the global instructions
        "ADR-014",                       # the advisory contract
    ]
    missing_refs = [r for r in required_refs if r not in composes_text]
    if missing_refs:
        print(f"✗ step 7: composes-with missing authority refs: {missing_refs}")
        return 1
    print(f"✓ step 7: composes-with references all {len(required_refs)} "
          "authority surfaces")

    # ── Step 8: POSITIVE — debugging section has tail/grep/git primitives ──
    debug_match = re.search(
        r"## Common debugging commands.*?(?=\n## |\Z)", body, re.DOTALL
    )
    if not debug_match:
        print("✗ step 8: 'Common debugging commands' section missing")
        return 1
    debug_text = debug_match.group(0)
    primitives = ["tail", "grep", "git"]
    missing_primitives = [
        p for p in primitives if p not in debug_text
    ]
    if missing_primitives:
        print(f"✗ step 8: debugging section missing operator primitives: "
              f"{missing_primitives}")
        return 1
    # Count the actual command-line invocations of each primitive
    counts = {p: len(re.findall(rf"\b{p}\b", debug_text)) for p in primitives}
    if any(c < 1 for c in counts.values()):
        print(f"✗ step 8: insufficient primitive invocations: {counts}")
        return 1
    print(f"✓ step 8: debugging section uses tail/grep/git primitives "
          f"({sum(counts.values())} invocations across the three)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
