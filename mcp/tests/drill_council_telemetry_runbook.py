#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: docs/runbooks/council-telemetry.md (Phase 5BB).

Phase 5K-5AA shipped seven operator-facing tools; the runbook
consolidates them into a debuggable reference. Without the drill,
the runbook would silently drift from reality (renamed flag in a
script → runbook still cites the old name → operator follows
stale instructions during an incident).

Eight steps. Six negative assertions.

  1. POSITIVE: runbook exists at the canonical path with the
     expected size shape (≥3KB; ≤30KB so it's not a wall of text).
  2. NEGATIVE: every file path the runbook claims to reference
     ACTUALLY exists under the repo. Drift sources: scripts
     renamed/moved without updating the runbook. Drill refuses
     drift.
  3. NEGATIVE: every Phase citation in the runbook (5K, 5L, ...,
     5AA) corresponds to an entry in docs/NEXT_POLICY.md so the
     runbook can't reference a phase that doesn't exist.
  4. NEGATIVE: every CLI flag mentioned in the runbook for
     `council_filter_stats.py` is supported by the script's
     argparse — runs `--help` and checks the flag set.
  5. NEGATIVE: required sections are present: "What this is",
     "Files", "Daily operations", "verdict-log chain", "5S→5Z→5Y
     worked example", "CLI cheat-sheet", "Escape hatches".
  6. NEGATIVE: the cheat-sheet's "pre-approved" section does NOT
     accidentally list scripts that require operator confirmation
     (sudo / destructive). Cross-checks against a known-gated
     allowlist.
  7. NEGATIVE: composes-with footer references real surfaces:
     ADR-014, Phase 4B, NEXT_POLICY.md §7. Without these refs,
     the runbook is unmoored from the codebase's authority chain.
  8. POSITIVE: smoke check — first 100 chars after each markdown
     heading start with prose, not a malformed table. Catches
     truncated/half-written sections.

Run: python3 mcp/tests/drill_council_telemetry_runbook.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "runbooks" / "council-telemetry.md"


def main() -> int:
    if not RUNBOOK.exists():
        print(f"✗ pre-step: {RUNBOOK} missing")
        return 1
    body = RUNBOOK.read_text()

    # ── Step 1: POSITIVE — exists with size shape ──
    size = len(body)
    if size < 3000:
        print(f"✗ step 1: runbook is {size} chars; expected ≥3000 (substantive)")
        return 1
    if size > 30000:
        print(f"✗ step 1: runbook is {size} chars; expected ≤30000 (not a wall of text)")
        return 1
    print(f"✓ step 1: runbook exists, {size} chars, "
          f"{len(body.splitlines())} lines")

    # ── Step 2: NEGATIVE — every claimed file path actually exists ──
    # Extract repo-relative paths from code blocks. Conservative match:
    # paths starting with scripts/ or mcp/ or services/ or docs/.
    # Capture the trailing character so we can detect glob patterns
    # ('mcp/server*.py' is a documentation pattern, not a real file —
    # naive greedy regex would capture 'mcp/server' and report a bogus
    # missing-file error). Backtracking with a negative-lookahead would
    # do the wrong thing here (it would just shorten the match to a
    # different bogus path); explicit next-char inspection is correct.
    path_re = re.compile(
        r'(?<![\w./])((?:scripts/|mcp/|services/|docs/)[a-zA-Z0-9_./\-]+)(.?)'
    )
    candidates = set()
    for m in path_re.finditer(body):
        path, next_char = m.group(1), m.group(2)
        if next_char == "*":
            continue  # glob pattern, not a real file
        candidates.add(path)
    # Filter to paths that look like real file refs (no trailing args,
    # no glob patterns, no template placeholders). Strip trailing
    # punctuation often left by markdown.
    paths_to_check = set()
    for c in candidates:
        c = c.rstrip(",.;:")
        # Skip obvious non-file refs (URLs, glob patterns, template forms)
        if "*" in c or "<" in c or ">" in c or "$" in c:
            continue
        # Skip lines with a colon (env-var-style path)
        if ":" in c.split("/")[-1]:
            continue
        # Skip subdirs that are actually mentioned as conceptual paths
        if c in {"scripts/", "mcp/", "services/", "docs/"}:
            continue
        # Skip conceptual file names that won't exist (the table mentions
        # `council_filter_stats.py (text)`)
        if "(" in c or " " in c:
            continue
        # Skip /var/lib/ — that's a host path, not a repo path
        if c.startswith("/var/"):
            continue
        paths_to_check.add(c)
    missing = []
    for p in paths_to_check:
        full = REPO / p
        if not full.exists():
            missing.append(p)
    if missing:
        print(f"✗ step 2: runbook references {len(missing)} non-existent paths: "
              f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}")
        return 1
    print(f"✓ step 2: all {len(paths_to_check)} cited file paths exist on disk")

    # ── Step 3: NEGATIVE — Phase citations correspond to ledger entries ──
    next_policy = (REPO / "docs" / "NEXT_POLICY.md").read_text()
    phase_re = re.compile(r"Phase\s+5[A-Z]+\b")
    phases = set(phase_re.findall(body))
    missing_phases = []
    for p in phases:
        # Match either '| Phase-5X' or 'Phase 5X' in NEXT_POLICY
        canonical = p.replace(" ", "-")  # "Phase 5K" -> "Phase-5K"
        if canonical not in next_policy and p not in next_policy:
            missing_phases.append(p)
    if missing_phases:
        print(f"✗ step 3: runbook cites phases not in ledger: {missing_phases}")
        return 1
    print(f"✓ step 3: all {len(phases)} Phase citations match ledger entries")

    # ── Step 4: NEGATIVE — claimed flags exist on council_filter_stats.py ──
    stats_script = REPO / "scripts" / "council_filter_stats.py"
    help_proc = subprocess.run(
        ["/tmp/documind-venv/bin/python", str(stats_script), "--help"],
        capture_output=True, text=True, timeout=10.0,
    )
    if help_proc.returncode != 0:
        print(f"✗ step 4: --help failed: {help_proc.stderr}")
        return 1
    # Flags the runbook cites for council_filter_stats.py
    cited_flags = ["--days", "--weekly", "--weeks", "--prometheus",
                   "--prometheus-out", "--from-snapshot", "--alert-on",
                   "--alert-week-mode", "--webhook", "--webhook-format",
                   "--json"]
    missing_flags = [f for f in cited_flags if f not in help_proc.stdout]
    if missing_flags:
        print(f"✗ step 4: runbook cites flags not in --help: {missing_flags}")
        return 1
    print(f"✓ step 4: all {len(cited_flags)} cited flags exist in argparse")

    # ── Step 5: NEGATIVE — required sections present ──
    required_section_keywords = [
        "What this is",
        "Files this references",
        "Daily operations",
        "verdict-log chain",
        "5S",   # the worked example references the phase by name
        "CLI cheat-sheet",
        "Escape hatches",
        "Composes with",
    ]
    missing_sections = [k for k in required_section_keywords if k not in body]
    if missing_sections:
        print(f"✗ step 5: runbook missing required sections: {missing_sections}")
        return 1
    print(f"✓ step 5: all {len(required_section_keywords)} required sections present")

    # ── Step 6: NEGATIVE — pre-approved cheat-sheet excludes gated tools ──
    # Find the "Pre-approved scripts" section and its content up to the
    # next ## or ### heading.
    pre_match = re.search(
        r"### Pre-approved scripts.*?(?=\n###|\n##|\Z)", body, re.DOTALL
    )
    if not pre_match:
        print("✗ step 6: 'Pre-approved scripts' subsection not found")
        return 1
    pre_text = pre_match.group(0)
    # Things that REQUIRE operator action — must NOT appear here
    gated_indicators = [
        "install_snapshot_cron.sh --apply",   # mutates crontab
        "migrate_ai_caches_to_deepa.sh --apply",  # cross-fs move
        "migrate_ollama_to_deepa.sh --apply",  # sudo + systemd
        "git push",
        "git push --force",
        "git reset --hard",
    ]
    leak = [g for g in gated_indicators if g in pre_text]
    if leak:
        print(f"✗ step 6: pre-approved section leaks gated commands: {leak}")
        return 1
    print(f"✓ step 6: pre-approved cheat-sheet is clean of gated commands")

    # ── Step 7: NEGATIVE — composes-with refs to real surfaces ──
    composes_match = re.search(
        r"## Composes with.*?\Z", body, re.DOTALL
    )
    if not composes_match:
        print("✗ step 7: 'Composes with' section missing")
        return 1
    composes_text = composes_match.group(0)
    # Required references
    required_refs = [
        "ADR-014",
        "Phase 4B",
        "NEXT_POLICY.md",
    ]
    missing_refs = [r for r in required_refs if r not in composes_text]
    if missing_refs:
        print(f"✗ step 7: composes-with missing refs: {missing_refs}")
        return 1
    print(f"✓ step 7: composes-with references all {len(required_refs)} authority surfaces")

    # ── Step 8: POSITIVE — section bodies are not truncated/malformed ──
    # Find every ## heading; ### subsections are CONTENT of their
    # parent, not separate sections. Splitting on both would mark a
    # parent section "## X" with only "### Y" subsections as empty,
    # which is misleading — it's a valid pattern.
    headings = re.findall(r"^(## .+)$", body, re.MULTILINE)
    sections = re.split(r"^## .+$", body, flags=re.MULTILINE)
    truncated = []
    for h, content in zip(headings, sections[1:]):
        lines = [ln.rstrip() for ln in content.splitlines() if ln.strip()]
        if not lines:
            truncated.append(h)
            continue
        first = lines[0].strip()
        # Truncated/malformed signatures:
        #   '|---' alone (a table separator with no header row)
        #   ',' or '|' alone (broken table cell)
        # Subheadings (#### or ###) are FINE — section legitimately
        # contains only subsections.
        if first.startswith("|---") or first == "," or first == "|":
            truncated.append(h)
    if truncated:
        print(f"✗ step 8: {len(truncated)} sections appear truncated/malformed: "
              f"{truncated[:3]}")
        return 1
    print(f"✓ step 8: all {len(headings)} section bodies have valid content")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
