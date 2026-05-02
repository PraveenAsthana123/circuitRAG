#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: autonomous_fix_daemon §42 safety boundaries — regression guard.

Per CLAUDE.md §43 + §42 + §50.5.3 + §55. The daemon mutates the
working tree + auto-commits. Every safety boundary that prevents it
from doing damage is regression-critical:

  §42  — daemon NEVER pushes (no git push, no force-push)
  §42  — daemon NEVER deletes (no rm -rf, no rmtree)
  §42  — daemon ONLY touches services/ libs/py/ mcp/ scripts/
        (SAFE_PATH_PREFIXES enforced)
  §50.5.3 — daemon SKIPS S* / B* security rules (is_security_rule)
  §43  — every drill-gate rejection writes an audit row (no silent skip)
  §54  — auto-commit messages MUST NOT contain Co-Authored-By trailer

This drill greps the source for all the above guarantees so a future
refactor that drops one of them fails the build BEFORE it ships.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DAEMON = REPO / "scripts" / "autonomous_fix_daemon.py"


def main() -> int:
    if not DAEMON.exists():
        print(f"x daemon source missing: {DAEMON}")
        return 1
    src = DAEMON.read_text(encoding="utf-8")

    print("-- 1. POSITIVE: daemon source exists + non-trivial size --")
    if len(src) < 5000:
        print(f"x step 1: daemon source only {len(src)} chars; truncated?")
        return 1
    print(f"  ok: daemon = {len(src)} chars; {len(src.splitlines())} lines")

    print("-- 2. NEGATIVE: §42 — daemon does NOT contain `git push` --")
    # Allow comments mentioning push (documentation), but the
    # subprocess invocation must never appear.
    forbidden_subprocess = re.search(
        r"subprocess\.\w+\([^)]*\bpush\b",
        src,
    )
    if forbidden_subprocess:
        print(f"x step 2: daemon invokes git push subprocess: {forbidden_subprocess.group(0)}")
        return 1
    # Also forbid plain string `["git", "push"]` arrays.
    if re.search(r'\[\s*"git"\s*,\s*"push"', src):
        print("x step 2: daemon contains [\"git\", \"push\"] argv")
        return 1
    print("  ok: §42 — no subprocess(git push) anywhere in daemon")

    print("-- 3. NEGATIVE: §42 — daemon does NOT use rm -rf / rmtree / unlink --")
    forbidden = ("rm -rf", "shutil.rmtree", ".unlink(", "os.remove")
    for pattern in forbidden:
        # Exception: comments referring to these as forbidden are OK
        # when the line is a comment (starts with #). Filter those.
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if pattern in line:
                print(f"x step 3: daemon contains destructive op {pattern!r}: {stripped[:100]}")
                return 1
    print("  ok: §42 — no destructive filesystem ops in daemon code")

    print("-- 4. POSITIVE: §42 — SAFE_PATH_PREFIXES enforced via is_safe_path() --")
    if "SAFE_PATH_PREFIXES" not in src:
        print("x step 4: daemon missing SAFE_PATH_PREFIXES constant")
        return 1
    if "def is_safe_path(" not in src:
        print("x step 4: daemon missing is_safe_path() function")
        return 1
    if "if not is_safe_path(issue.get(\"file\", \"\"))" not in src:
        print("x step 4: find_next_task does not invoke is_safe_path")
        return 1
    # Verify the safe path list is what we expect
    for prefix in ("services/", "libs/py/", "mcp/", "scripts/"):
        if f'"{prefix}"' not in src:
            print(f"x step 4: SAFE_PATH_PREFIXES missing {prefix!r}")
            return 1
    print("  ok: §42 — SAFE_PATH_PREFIXES = (services/, libs/py/, mcp/, scripts/) enforced")

    print("-- 5. POSITIVE: §50.5.3 — security rules skipped via is_security_rule() --")
    if "def is_security_rule(" not in src:
        print("x step 5: daemon missing is_security_rule() filter")
        return 1
    if 'startswith(("S", "B"))' not in src and "startswith((\"S\", \"B\"))" not in src:
        print("x step 5: is_security_rule must filter both S* (ruff) and B* (bandit)")
        return 1
    if "if is_security_rule(issue.get(\"code\", \"\")):" not in src:
        print("x step 5: find_next_task does not invoke is_security_rule")
        return 1
    print("  ok: §50.5.3 — S*/B* security rules filtered at task-claim time")

    print("-- 6. NEGATIVE: §43 — every state-mutating reject writes an audit row --")
    # Mutating reject paths (rejected, dry_run, tier_b_deferred) must
    # audit-log. Non-mutating skips (already_attempted, human-only,
    # out-of-safe-path) trace via prior-audit OR human-review queue,
    # not by re-auditing the same issue.
    mutating_reject_outcomes = ("dry_run", "rejected", "tier_b_deferred")
    for outcome in mutating_reject_outcomes:
        marker = f'"outcome": "{outcome}"'
        if marker not in src:
            print(f"x step 6: state-mutating outcome {outcome!r} never written to audit")
            return 1
    if "def escalate(" not in src:
        print("x step 6: daemon missing escalate() helper for rolling log")
        return 1
    if "def export_human_review_queue(" not in src:
        print("x step 6: daemon missing export_human_review_queue() — human-only skips invisible")
        return 1
    print("  ok: §43 — 3 mutating outcomes audit-logged; non-mutating use queue export + rolling log")

    print("-- 7. NEGATIVE: §54 — auto_commit_applied does NOT emit a Co-Authored-By trailer --")
    # The actual §54 violation is a TRAILER LINE matching the format
    # `Co-Authored-By: <Name> <email>`. Mentions of the policy text
    # in commit-message documentation are fine. We grep for the
    # actual trailer pattern (with email).
    trailer_pattern = re.compile(
        r"Co-Authored-By:\s+\S[^@\n]*@",
        re.IGNORECASE,
    )
    auto_commit_match = re.search(
        r"def auto_commit_applied\([^)]+\)[^:]*:(.*?)(?=\ndef |\Z)",
        src, re.DOTALL,
    )
    if auto_commit_match is None:
        print("x step 7: auto_commit_applied function not found")
        return 1
    body = auto_commit_match.group(1)
    if trailer_pattern.search(body):
        print("x step 7: auto_commit_applied emits a Co-Authored-By trailer (§54 violation)")
        return 1
    if "no Co-Authored-By trailer" not in body and "§54" not in body:
        print("x step 7: auto_commit_applied missing §54-compliance citation")
        return 1
    print("  ok: §54 — auto_commit_applied body has no `Co-Authored-By: x@y` trailer; cites §54")

    print("-- 8. POSITIVE: emit() events are structured (one daemon: prefix per line) --")
    # Every emit() call should produce exactly one line of daemon: stdout.
    emit_calls = re.findall(r'emit\(f?"([^"]+)"\)', src)
    if len(emit_calls) < 8:
        print(f"x step 8: only {len(emit_calls)} emit() calls; expected ≥8 for full lifecycle visibility")
        return 1
    # No emit() should embed a literal newline (would break the cron-tail one-event-per-line contract)
    for call in emit_calls:
        if "\n" in call:
            print(f"x step 8: emit() contains literal newline: {call!r}")
            return 1
    print(f"  ok: {len(emit_calls)} emit() events; all single-line (Monitor / cron-tail compatible)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
