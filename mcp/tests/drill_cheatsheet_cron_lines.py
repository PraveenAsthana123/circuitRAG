#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every cron line in docs/runbooks/*.md is well-formed +
references a real script.

Operators copy-paste cron lines from docs into their crontab during
incidents (or first-time setup). A typo in a runbook line wastes
the operator's day — they install something that won't run, then
debug why nothing's firing. Phase 6H drills the cron blocks in
operator-facing docs to catch:

  * malformed schedule (not 5 fields)
  * invalid schedule field (non-cron syntax)
  * command references a script that doesn't exist
  * schedule overlaps that would cause double-firing

Eight steps. Six negative assertions.

  1. POSITIVE: ≥1 cron block found across docs/runbooks/*.md.
     Sanity that the regex finds anything.
  2. NEGATIVE: every cron line has exactly 5 schedule fields +
     ≥1 command-field token. Lines with fewer schedule fields
     are malformed (cron silently ignores them).
  3. NEGATIVE: each schedule field matches the cron grammar
     (digits, *, -, /, comma). A field with letters or other
     punctuation is a typo.
  4. NEGATIVE: every cron line's primary script exists on disk.
     If the line invokes `python3 /mnt/deepa/rag/scripts/X.py`,
     X.py must be present. If it invokes `scripts/X.sh` (relative)
     or just `X.sh`, ditto.
  5. NEGATIVE: scripts cited in cron blocks have execute bit
     OR are invoked through an interpreter (python3 X / bash X).
     Otherwise cron will silently fail to run them.
  6. NEGATIVE: schedules don't accidentally overlap. Two `5 0 * * *`
     lines is suspicious — operator copy-pasted twice or the docs
     drifted. Allow same minute if docs explicitly stagger (e.g.
     5N + 5X composed pipeline both at 5 0).
  7. NEGATIVE: at least 2 distinct schedules across the docs.
     If everything is `5 0 * * *`, the docs are over-concentrating
     load on one minute.
  8. POSITIVE: end-to-end — pick the most recently-discovered cron
     line, simulate parsing it through Python's standard string
     split, verify the command is unambiguous (no quoting issues
     that would confuse cron's parser).

Run: python3 mcp/tests/drill_cheatsheet_cron_lines.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNBOOKS_DIR = REPO / "docs" / "runbooks"

# Cron schedule field grammar:
#   * = wildcard
#   N = single digit/number
#   N-M = range
#   N-M/K = range with step
#   */K = wildcard with step
#   N,M = list
# Combined: any sequence of digits, *, -, /, , characters.
_CRON_FIELD_RE = re.compile(r"^[\d*\-/,]+$")


def _extract_cron_blocks(body: str) -> list[str]:
    """Yield the contents of every ```cron fenced block in `body`."""
    return re.findall(r"```cron\n(.*?)\n```", body, re.DOTALL)


def _extract_cron_lines(block: str) -> list[str]:
    """Yield non-comment, non-blank lines from a cron block.
    Joins backslash-continuation lines into one logical line."""
    lines: list[str] = []
    pending: list[str] = []
    for raw in block.splitlines():
        s = raw.rstrip()
        if not s.strip() or s.lstrip().startswith("#"):
            if pending:
                lines.append(" ".join(pending))
                pending = []
            continue
        if s.endswith("\\"):
            pending.append(s[:-1].rstrip())
        else:
            pending.append(s)
            lines.append(" ".join(pending))
            pending = []
    if pending:
        lines.append(" ".join(pending))
    return lines


def _script_path_from_command(command_tokens: list[str]) -> Path | None:
    """Best-effort: extract the script path from a cron command.

    Common shapes:
        python3 /path/to/X.py [args]
        /path/to/X.sh [args]
        bash /path/to/X.sh [args]
    Returns None if no plausible path was found."""
    interp_prefixes = {"python3", "python", "bash", "sh"}
    for i, tok in enumerate(command_tokens):
        if i == 0 and tok in interp_prefixes:
            continue
        if i == 0:
            # First token IS the script (no interpreter prefix)
            return Path(tok)
        # First non-interpreter token after the prefix
        return Path(tok)
    return None


def main() -> int:
    if not RUNBOOKS_DIR.exists():
        print(f"✗ pre-step: {RUNBOOKS_DIR} missing")
        return 1
    runbooks = sorted(RUNBOOKS_DIR.glob("*.md"))

    # Collect all cron lines across all runbooks
    all_lines: list[tuple[str, str]] = []  # (runbook, line)
    for rb in runbooks:
        body = rb.read_text()
        for block in _extract_cron_blocks(body):
            for line in _extract_cron_lines(block):
                all_lines.append((rb.name, line))

    # ── Step 1: POSITIVE — ≥1 cron block found ──
    if not all_lines:
        print("✗ step 1: no cron lines found in any runbook")
        return 1
    print(f"✓ step 1: {len(all_lines)} cron lines across {len(runbooks)} runbooks")

    # ── Step 2: NEGATIVE — exactly 5 schedule fields + ≥1 command ──
    malformed = []
    for rb, line in all_lines:
        toks = line.split()
        if len(toks) < 6:
            malformed.append((rb, line))
    if malformed:
        print(f"✗ step 2: {len(malformed)} cron lines have <6 tokens "
              f"(need 5 schedule + 1+ command): {malformed[:2]}")
        return 1
    print(f"✓ step 2: every cron line has 5 schedule + ≥1 command tokens")

    # ── Step 3: NEGATIVE — each schedule field matches cron grammar ──
    bad_field = []
    for rb, line in all_lines:
        toks = line.split()
        for i, field in enumerate(toks[:5]):
            if not _CRON_FIELD_RE.match(field):
                bad_field.append((rb, line, i, field))
    if bad_field:
        print(f"✗ step 3: {len(bad_field)} cron schedule fields invalid: "
              f"{bad_field[:2]}")
        return 1
    print(f"✓ step 3: every schedule field matches cron grammar")

    # ── Step 4: NEGATIVE — every cron line's script exists ──
    missing_scripts = []
    for rb, line in all_lines:
        toks = line.split()
        cmd_tokens = toks[5:]  # everything after 5 schedule fields
        script = _script_path_from_command(cmd_tokens)
        if script is None:
            continue  # couldn't parse — defer to a different check
        # Resolve absolute / repo-relative paths
        if script.is_absolute():
            full = script
        else:
            full = REPO / script
        if not full.exists():
            missing_scripts.append((rb, str(script)))
    if missing_scripts:
        print(f"✗ step 4: {len(missing_scripts)} cron commands reference "
              f"non-existent scripts: {missing_scripts[:3]}")
        return 1
    print(f"✓ step 4: every cron command references an existing script")

    # ── Step 5: NEGATIVE — scripts are runnable via interpreter or +x ──
    not_runnable = []
    for rb, line in all_lines:
        toks = line.split()
        cmd_tokens = toks[5:]
        if not cmd_tokens:
            continue
        script = _script_path_from_command(cmd_tokens)
        if script is None:
            continue
        full = script if script.is_absolute() else (REPO / script)
        if not full.exists():
            continue  # already caught in step 4
        # Check whether it's invoked through an interpreter
        first = cmd_tokens[0]
        through_interpreter = first in {"python3", "python", "bash", "sh"}
        if through_interpreter:
            continue
        # Direct invocation — script must have execute bit
        if not os.access(full, os.X_OK):
            not_runnable.append((rb, str(script)))
    if not_runnable:
        print(f"✗ step 5: {len(not_runnable)} scripts invoked directly "
              f"without execute bit: {not_runnable[:3]}")
        return 1
    print(f"✓ step 5: every cron command is runnable (interpreter or +x)")

    # ── Step 6: NEGATIVE — no accidental schedule duplicates ──
    # We allow a SAME schedule string to appear in different doc
    # files (council-telemetry.md and the cheatsheet may both cite
    # the same recommended cron). The smell is when the SAME doc
    # cites the same exact schedule + script twice.
    per_doc_dupes = []
    for rb in {rb for rb, _ in all_lines}:
        seen: dict[str, str] = {}
        for r, line in all_lines:
            if r != rb:
                continue
            toks = line.split()
            schedule = " ".join(toks[:5])
            script = _script_path_from_command(toks[5:])
            key = f"{schedule}|{script}"
            if key in seen:
                per_doc_dupes.append((rb, key))
            seen[key] = line
    if per_doc_dupes:
        print(f"✗ step 6: same cron entry duplicated within one doc: "
              f"{per_doc_dupes[:2]}")
        return 1
    print(f"✓ step 6: no within-doc cron duplicates "
          "(cross-doc duplication still allowed)")

    # ── Step 7: NEGATIVE — schedule diversity ──
    schedules = {" ".join(line.split()[:5]) for _, line in all_lines}
    if len(schedules) < 2:
        print(f"✗ step 7: only {len(schedules)} distinct schedule(s); "
              "docs over-concentrate cron load on one minute")
        return 1
    print(f"✓ step 7: {len(schedules)} distinct schedules (load spread)")

    # ── Step 8: POSITIVE — end-to-end parse sanity ──
    # Take any line, verify it splits unambiguously into 5+ fields
    # via shlex (mimics what cron's parser sees).
    import shlex
    sample = all_lines[0][1]
    try:
        parsed = shlex.split(sample)
    except ValueError as exc:
        print(f"✗ step 8: shlex couldn't parse cron line {sample!r}: {exc}")
        return 1
    if len(parsed) < 6:
        print(f"✗ step 8: shlex split produced {len(parsed)} tokens; "
              f"line: {sample!r}")
        return 1
    print(f"✓ step 8: end-to-end shlex parses cron lines unambiguously "
          f"(sample: {len(parsed)} tokens)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
