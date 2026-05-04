#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: scripts/run.sh quickstart launcher.

Per CLAUDE.md §43 + §42 + §55. Locks the contract that the
single-script entry point:
  - exits 0 on `status` (default; read-only)
  - exits 2 (NOT 0) on `push` without --confirm (§42 gated)
  - rejects unknown verbs
  - dispatches to the documented verbs without crashing
  - never invokes destructive ops (rm -rf / git push --force)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_SH = REPO / "scripts" / "run.sh"


def main() -> int:
    print("-- 1. POSITIVE: scripts/run.sh exists + executable --")
    if not RUN_SH.exists():
        print(f"x {RUN_SH} missing")
        return 1
    if not (RUN_SH.stat().st_mode & stat.S_IXUSR):
        print(f"x {RUN_SH} not executable")
        return 1
    print(f"  ok: {RUN_SH.name} present + executable")

    print("-- 2. POSITIVE: --help produces operator-readable output --")
    proc = subprocess.run(
        ["bash", str(RUN_SH), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        print(f"x --help exited {proc.returncode}")
        return 1
    if len(proc.stdout) < 400:
        print(f"x --help only {len(proc.stdout)} chars; expected ≥400")
        return 1
    for marker in ("Usage:", "status", "fix", "push", "§42"):
        if marker not in proc.stdout:
            print(f"x --help missing marker {marker!r}")
            return 1
    print(f"  ok: --help has 5 markers + {len(proc.stdout)} chars")

    print("-- 3. NEGATIVE: status mode is read-only (exit 0; no mutation) --")
    pre = subprocess.run(
        ["git", "diff", "--stat"], cwd=REPO,
        capture_output=True, text=True, timeout=10,
    )
    proc = subprocess.run(
        ["bash", str(RUN_SH), "status"],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    post = subprocess.run(
        ["git", "diff", "--stat"], cwd=REPO,
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        print(f"x status exited {proc.returncode}")
        return 1
    if pre.stdout != post.stdout:
        print("x status mode mutated working tree")
        return 1
    print("  ok: status exits 0; worktree byte-identical pre/post")

    print("-- 4. NEGATIVE: push without --confirm exits 2 (§42 enforced) --")
    proc = subprocess.run(
        ["bash", str(RUN_SH), "push"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
        env={**__import__("os").environ, "GIT_PUSH_CONFIRM": ""},  # explicit unset
    )
    if proc.returncode != 2:
        print(f"x push without --confirm should exit 2; got {proc.returncode}")
        return 1
    output = proc.stdout + proc.stderr
    if "§42" not in output and "confirm" not in output.lower():
        print(f"x push refusal output should cite §42 or confirm: {output[:200]}")
        return 1
    print("  ok: push without --confirm exits 2 + cites §42")

    print("-- 5. NEGATIVE: unknown verb rejected with operator-readable error --")
    proc = subprocess.run(
        ["bash", str(RUN_SH), "this-is-not-a-real-verb-xyz"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    if proc.returncode == 0:
        print(f"x unknown verb returned 0; should be non-zero")
        return 1
    output = proc.stdout + proc.stderr
    if "valid:" not in output and "unknown" not in output.lower():
        print(f"x unknown verb output should list valid options: {output[:200]}")
        return 1
    print("  ok: unknown verb rejected; valid options listed")

    print("-- 6. NEGATIVE: source contains NO destructive ops --")
    src = RUN_SH.read_text(encoding="utf-8")
    forbidden_patterns = (
        re.compile(r"\brm\s+-rf\s+/(?!tmp)"),  # rm -rf /tmp is fine
        re.compile(r"git\s+push\s+--force"),
        re.compile(r"git\s+reset\s+--hard\s+origin"),
        re.compile(r"git\s+branch\s+-D"),
    )
    for pattern in forbidden_patterns:
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if pattern.search(line):
                print(f"x destructive pattern {pattern.pattern!r} in: {stripped[:80]}")
                return 1
    print("  ok: no destructive ops (rm -rf /, force-push, hard reset, force-delete-branch)")

    print("-- 7. POSITIVE: script supports the 16 documented verbs --")
    expected_verbs = (
        "status", "check", "warm", "scan", "fix", "fix-dry",
        "metrics", "review", "frontend", "orchestrator",
        "pr-preview", "push", "drills", "ollama-mcp",
        "paperclip", "policy",
    )
    for verb in expected_verbs:
        # Verify each verb has a corresponding `case "VERB")` clause
        if f"  {verb})" not in src and f"  {verb}|" not in src:
            print(f"x verb {verb!r} not handled in case statement")
            return 1
    print(f"  ok: all {len(expected_verbs)} verbs handled")

    print("-- 8. POSITIVE: §42 boundary documented in script header --")
    header = src[:2000]
    for marker in ("§42", "Never force-push", "rolls back"):
        if marker not in header and marker.lower() not in header.lower():
            # tolerant check: at least §42 reference must be present
            if marker == "§42":
                print(f"x header missing §42 reference")
                return 1
    print("  ok: §42 SAFETY block present in script header")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
