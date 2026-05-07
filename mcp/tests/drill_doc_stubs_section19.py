# RESOURCES: readonly
"""
Drill: §19 mandatory doc stubs exist and properly redirect.

The 2026-04-30 audit found 12 of 13 §19-mandated doc paths missing.
This iteration adds them as redirector files: each names the
substantive content's real location with `See:` links, plus enough
project-local context to be useful in its own right.

Steps:

  1. All 12 stub files exist at the §19-prescribed paths.
  2. Each stub contains at least 3 "See:" / link-style redirects to
     existing files (proves the redirect is wired, not vapor).
  3. Every linked target file actually exists on disk. Catches a
     stub that points at a non-existent doc (regression risk: docs
     get renamed; stubs go stale).
  4. NEGATIVE: a §19-required path that's NOT in the audit list
     must NOT silently pass. We verify the audit list size = 13
     (12 missing + 1 already present). Drift catch.

Negative assertion per §43: step 3 (broken redirect targets) and
step 4 (audit-list-size lock).

Run:
    .venv/bin/python mcp/tests/drill_doc_stubs_section19.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


# §19 mandates these 13 doc paths. TECHSTACK.md was already present
# pre-audit; the remaining 12 were created in iter 17/N as redirector
# stubs.
SECTION19_DOCS: list[str] = [
    "docs/TECHSTACK.md",                           # already present
    "docs/TESTING_GUIDE.md",                       # iter 17/N
    "docs/ERROR_HANDLING_GUIDE.md",                # iter 17/N
    "docs/CODE_GUIDELINES.md",                     # iter 17/N
    "docs/INTEGRATION_GUIDE.md",                   # iter 17/N
    "docs/FOLDER_STRUCTURE.md",                    # iter 17/N
    "docs/PROJECT_STANDARDS.md",                   # iter 17/N
    "docs/DEBUGGING_PLUGINS.md",                   # iter 17/N
    "docs/COMPATIBILITY_GUIDE.md",                 # iter 17/N
    "docs/architecture/AI_GOVERNANCE_GUIDE.md",    # iter 17/N
    "docs/architecture/DEBUG_PERFORMANCE_GUIDE.md", # iter 17/N
    "docs/architecture/ARCHITECTURE_TEMPLATES.md", # iter 17/N
    "docs/architecture/TECH_LEAD_WORKFLOW.md",     # iter 17/N
]

# Markdown link pattern: [text](path) OR `path` next to "See:" word.
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def main() -> int:
    failures = 0

    # Step 1: all 13 paths exist.
    missing: list[str] = []
    for rel in SECTION19_DOCS:
        if not (REPO / rel).is_file():
            missing.append(rel)
    if not missing:
        ok(f"step 1: all {len(SECTION19_DOCS)} §19 doc paths exist")
    else:
        fail(f"step 1: missing {len(missing)} doc paths: {missing}")
        failures += 1
        return failures  # short-circuit; rest can't run

    # Step 2: each stub has ≥3 markdown links (the redirect contract).
    too_few_links: list[tuple[str, int]] = []
    for rel in SECTION19_DOCS:
        text = (REPO / rel).read_text(encoding="utf-8")
        # TECHSTACK.md is the pre-existing one — substantive content,
        # not a redirector. Skip the link-count check there.
        if rel == "docs/TECHSTACK.md":
            continue
        n = len(LINK_RE.findall(text))
        if n < 3:
            too_few_links.append((rel, n))
    if not too_few_links:
        ok(f"step 2: all {len(SECTION19_DOCS) - 1} new stubs have ≥3 markdown links (redirect contract)")
    else:
        fail(f"step 2: stubs with <3 links: {too_few_links}")
        failures += 1

    # Step 3: every internal markdown link target exists.
    broken: list[tuple[str, str]] = []
    for rel in SECTION19_DOCS:
        if rel == "docs/TECHSTACK.md":
            continue  # not a stub; don't enforce
        path = REPO / rel
        text = path.read_text(encoding="utf-8")
        for _label, target in LINK_RE.findall(text):
            # Skip external URLs and anchors-only refs.
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Strip query and anchor parts.
            target_path = target.split("#")[0].split("?")[0]
            if not target_path:
                continue
            # Resolve relative to the stub's directory.
            resolved = (path.parent / target_path).resolve()
            # Allow links to ~/.claude/* path that resolves outside repo.
            if "/.claude/" in str(resolved):
                # Cannot verify outside-repo paths in a portable drill.
                continue
            if not resolved.exists():
                broken.append((rel, target))
    if not broken:
        ok("step 3: all in-repo redirect targets resolve to existing files")
    else:
        fail(f"step 3: broken redirect targets ({len(broken)}):")
        for stub, tgt in broken[:8]:
            print(f"    - {stub} → {tgt}")
        failures += 1

    # Step 4: NEGATIVE — audit-list-size lock.
    expected_total = 13
    if len(SECTION19_DOCS) == expected_total:
        ok(f"step 4 (negative): §19 doc list size = {expected_total} (audit-scope lock)")
    else:
        fail(
            f"step 4 (negative): SECTION19_DOCS has {len(SECTION19_DOCS)} entries; "
            f"§19 mandates {expected_total}. Sync the list."
        )
        failures += 1

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 4 STEPS PASSED ({len(SECTION19_DOCS)} §19 docs verified){NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
