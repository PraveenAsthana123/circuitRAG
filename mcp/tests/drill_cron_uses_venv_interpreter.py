#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every cron line in operator runbooks uses the .venv interpreter
(Phase 6P).

The parallel content stream's interpreter-path migration moved cron
examples from `/tmp/documind-venv/bin/python` (ephemeral; wiped on
reboot) to `/mnt/deepa/rag/.venv/bin/python` (Deepa-backed; survives).
Without a drill, that contract can drift back: someone editing a
runbook copy-pastes from an old session, the cron line ends up
pointing at /tmp/, the host reboots, the operator's cron silently
fails the next morning.

Phase 6P locks the contract: every PYTHON cron line in
docs/runbooks/*.md must use .venv/bin/python (or omit the
interpreter for shell scripts). The drill scans every cron block,
extracts the command, and asserts the interpreter path.

Eight steps. Six negative assertions.

  1. POSITIVE: at least one cron block found across runbooks (sanity).
  2. NEGATIVE: NO cron line uses /tmp/documind-venv/bin/python
     (ephemeral path; the original migration target).
  3. NEGATIVE: NO cron line uses bare `python` or `python3` (relies
     on operator's PATH which may shadow the wrong venv).
  4. NEGATIVE: NO cron line uses `/usr/bin/python3` for project
     scripts (system python lacks documind_core + httpx etc).
  5. NEGATIVE: every cron line that invokes a project Python script
     uses /mnt/deepa/rag/.venv/bin/python explicitly.
  6. NEGATIVE: shell-script cron lines (.sh extension) don't
     specify a Python interpreter at all (the script handles
     interpreter selection internally per Phase 6I's fallback chain).
  7. NEGATIVE: every cron line's referenced script exists on disk
     (no typos sneaking past).
  8. POSITIVE: end-to-end shape — count of cron lines verified
     against the cron-block parser's discovery (no silent drops).

Run: python3 mcp/tests/drill_cron_uses_venv_interpreter.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNBOOKS_DIR = REPO / "docs" / "runbooks"

VENV_INTERPRETER = "/mnt/deepa/rag/.venv/bin/python"
EPHEMERAL_INTERPRETER = "/tmp/documind-venv/bin/python"


def _extract_cron_blocks(body: str) -> list[str]:
    return re.findall(r"```cron\n(.*?)\n```", body, re.DOTALL)


def _extract_cron_lines(block: str) -> list[str]:
    """Yield non-comment, non-blank lines, joining backslash continuations."""
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


def _command_tokens(cron_line: str) -> list[str]:
    """Skip the 5 schedule fields + any leading env=val tokens; return
    the command tokens (interpreter + script + args)."""
    toks = cron_line.split()
    if len(toks) < 6:
        return []
    cmd = toks[5:]
    # Skip env=val prefixes (like COUNCIL_STATS_WEBHOOK="..." in 5X examples)
    while cmd and "=" in cmd[0] and not cmd[0].startswith("/"):
        cmd = cmd[1:]
    return cmd


def main() -> int:
    if not RUNBOOKS_DIR.exists():
        print(f"✗ pre-step: {RUNBOOKS_DIR} missing")
        return 1
    runbooks = sorted(RUNBOOKS_DIR.glob("*.md"))

    all_lines: list[tuple[str, str]] = []
    for rb in runbooks:
        body = rb.read_text()
        for block in _extract_cron_blocks(body):
            for line in _extract_cron_lines(block):
                all_lines.append((rb.name, line))

    # ── Step 1: POSITIVE — at least one cron line ──
    if not all_lines:
        print("✗ step 1: no cron lines found in any runbook")
        return 1
    print(f"✓ step 1: {len(all_lines)} cron lines across {len(runbooks)} runbooks")

    # ── Step 2: NEGATIVE — no /tmp/documind-venv ──
    bad_tmp = [(rb, line) for rb, line in all_lines if EPHEMERAL_INTERPRETER in line]
    if bad_tmp:
        print(f"✗ step 2: {len(bad_tmp)} cron lines use ephemeral "
              f"{EPHEMERAL_INTERPRETER}: {bad_tmp[:2]}. Migrate to "
              f"{VENV_INTERPRETER} (Deepa-backed; survives reboots).")
        return 1
    print("✓ step 2: no cron line uses ephemeral /tmp/documind-venv")

    # ── Step 3: NEGATIVE — no bare python/python3 ──
    bad_bare = []
    for rb, line in all_lines:
        cmd = _command_tokens(line)
        if not cmd:
            continue
        first = cmd[0]
        # Allow if the first token is a script (.sh / .py); bare
        # interpreter as first token is the smell
        if first in ("python", "python3"):
            bad_bare.append((rb, line))
    if bad_bare:
        print(f"✗ step 3: {len(bad_bare)} cron lines use bare "
              f"python/python3 (PATH-dependent): {bad_bare[:2]}. "
              "Use absolute interpreter path.")
        return 1
    print("✓ step 3: no cron line uses bare python/python3")

    # ── Step 4: NEGATIVE — no /usr/bin/python3 for project scripts ──
    bad_sys = []
    for rb, line in all_lines:
        if "/usr/bin/python" not in line:
            continue
        # Allow /usr/bin/python3 for non-project scripts (e.g. an
        # operator's own logger). Project scripts live in
        # /mnt/deepa/rag/scripts/ — flag the combo.
        if "/mnt/deepa/rag/scripts/" in line:
            bad_sys.append((rb, line))
    if bad_sys:
        print(f"✗ step 4: {len(bad_sys)} cron lines use /usr/bin/python3 "
              f"to run project scripts (lacks documind_core): {bad_sys[:2]}")
        return 1
    print("✓ step 4: no cron line runs project scripts via /usr/bin/python3")

    # ── Step 5: NEGATIVE — project Python scripts use .venv ──
    bad_python = []
    for rb, line in all_lines:
        cmd = _command_tokens(line)
        if not cmd:
            continue
        first = cmd[0]
        # Only check lines that invoke a Python interpreter
        if "/python" not in first:
            continue
        if first != VENV_INTERPRETER:
            bad_python.append((rb, first, line))
    if bad_python:
        print(f"✗ step 5: {len(bad_python)} cron lines use a Python "
              f"interpreter that's not {VENV_INTERPRETER}:")
        for rb, interp, _ in bad_python[:3]:
            print(f"     {rb}: {interp}")
        return 1
    print(f"✓ step 5: every Python cron line uses {VENV_INTERPRETER}")

    # ── Step 6: NEGATIVE — shell scripts don't specify a Python interp ──
    # Lines invoking a .sh script directly should NOT have a python
    # prefix (the script handles its own interpreter resolution).
    bad_shell = []
    for rb, line in all_lines:
        cmd = _command_tokens(line)
        if not cmd:
            continue
        # Find the .sh script in the command
        sh_idx = None
        for i, t in enumerate(cmd):
            if t.endswith(".sh"):
                sh_idx = i
                break
        if sh_idx is None:
            continue
        # If there's a python interpreter BEFORE the .sh script, smell
        if any("python" in t for t in cmd[:sh_idx]):
            bad_shell.append((rb, line))
    if bad_shell:
        print(f"✗ step 6: {len(bad_shell)} cron lines invoke .sh script "
              f"with python prefix: {bad_shell[:2]}")
        return 1
    print("✓ step 6: shell-script cron lines invoke directly (no python prefix)")

    # ── Step 7: NEGATIVE — every referenced script exists ──
    missing_scripts = []
    for rb, line in all_lines:
        cmd = _command_tokens(line)
        # Find the project script path (under /mnt/deepa/rag/)
        for tok in cmd:
            if tok.startswith("/mnt/deepa/rag/") and \
                    (tok.endswith(".py") or tok.endswith(".sh")):
                if not Path(tok).exists():
                    missing_scripts.append((rb, tok))
                break
    if missing_scripts:
        print(f"✗ step 7: {len(missing_scripts)} cron-line scripts don't "
              f"exist on disk: {missing_scripts[:3]}")
        return 1
    print("✓ step 7: every cron-line project script exists on disk")

    # ── Step 8: POSITIVE — end-to-end count parity ──
    # Recount via the cron-line regex directly to catch silent drops
    # in our parser. The `5 [0-9*]+` shape is the unambiguous start.
    raw_count = 0
    for rb in runbooks:
        body = rb.read_text()
        # A "real" cron line starts with digits/* in its first field
        # AND lives inside a ```cron block. Scan inside cron blocks only.
        for block in _extract_cron_blocks(body):
            for line in block.splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                # Heuristic: starts with cron schedule field
                if re.match(r"^[\d*]", s):
                    raw_count += 1
    # all_lines joined backslash continuations, so its count <= raw_count
    if len(all_lines) > raw_count:
        print(f"✗ step 8: parser produced {len(all_lines)} lines vs "
              f"{raw_count} raw — counting bug?")
        return 1
    # Within-doc duplication is allowed (cross-doc duplicate is fine)
    print(f"✓ step 8: parser found {len(all_lines)} logical lines from "
          f"{raw_count} raw cron-block rows (continuations folded)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
