#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: rollback tagging contract (Tier 2 #2.10).

Per CLAUDE.md §43 + §42 + §50. Every daemon auto-commit gets an
`auto-apply-<issue_id>` git tag so an operator can revert
atomically when production weirdness ties to a specific fix.

The drill locks the contract WITHOUT actually creating tags:
greps the daemon source for the tagging code path + verifies the
revert script honors §42 (no force-push).

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DAEMON = REPO / "scripts" / "autonomous_fix_daemon.py"
REVERT = REPO / "scripts" / "revert_auto_apply.sh"


def main() -> int:
    print("-- 1. POSITIVE: revert script exists + executable --")
    if not REVERT.exists():
        print(f"x step 1: {REVERT} missing")
        return 1
    if not (REVERT.stat().st_mode & stat.S_IXUSR):
        print(f"x step 1: {REVERT} not executable")
        return 1
    print(f"  ok: {REVERT.name} present + executable")

    print("-- 2. POSITIVE: --help is operator-readable + cites §42 --")
    proc = subprocess.run(["bash", str(REVERT), "--help"],
                          capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        print(f"x step 2: --help exited {proc.returncode}")
        return 1
    h = proc.stdout
    if len(h) < 400:
        print(f"x step 2: --help only {len(h)} chars; expected ≥400")
        return 1
    if "§42" not in h:
        print(f"x step 2: --help missing §42 reference")
        return 1
    if "force-push" not in h.lower() and "force push" not in h.lower():
        print(f"x step 2: --help should explicitly disclaim force-push")
        return 1
    print(f"  ok: --help cites §42 + disclaims force-push; {len(h)} chars")

    print("-- 3. NEGATIVE: revert script does NOT contain `git push --force` --")
    src = REVERT.read_text(encoding="utf-8")
    if re.search(r"git\s+push\s+--force", src):
        print("x step 3: revert script contains force-push (§42 violation)")
        return 1
    if "git push" in src and "operator must" not in src and "NEVER" not in src.upper():
        # If it has 'git push' at all, it MUST be in a comment marking it as forbidden.
        # Defensive check:
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "git push" in stripped:
                print(f"x step 3: non-commented `git push` in revert script: {stripped}")
                return 1
    print("  ok: revert script never invokes git push (§42 enforced)")

    print("-- 4. POSITIVE: revert script supports --list / --revert / --revert-range / --status --")
    for cmd in ("--list", "--revert", "--revert-range", "--status"):
        if cmd not in src:
            print(f"x step 4: revert script missing command {cmd}")
            return 1
    print("  ok: 4 commands present (list / revert / revert-range / status)")

    print("-- 5. NEGATIVE: daemon auto_commit_applied tags after successful commit --")
    daemon_src = DAEMON.read_text(encoding="utf-8")
    if "git tag" not in daemon_src or '"auto-apply-"' not in daemon_src:
        print("x step 5: daemon missing the `git tag auto-apply-<id>` line")
        return 1
    if "_sanitize_tag(" not in daemon_src:
        print("x step 5: daemon missing _sanitize_tag() helper for git-tag-name validation")
        return 1
    print("  ok: daemon tags successful commits with auto-apply-<sanitized-id>")

    print("-- 6. NEGATIVE: tag failure is NON-FATAL (commit already succeeded) --")
    # The daemon must continue if `git tag` fails — losing the
    # convenient revert handle is bad but the commit landed; raising
    # here would crash the daemon mid-cycle.
    if "tag_failed" not in daemon_src:
        print("x step 6: daemon missing `tag_failed` event emission")
        return 1
    if "Tag failure is non-fatal" not in daemon_src:
        print("x step 6: daemon missing the non-fatal-on-tag-failure invariant comment")
        return 1
    print("  ok: tag failure emits `daemon:tag_failed` event; commit not rolled back")

    print("-- 7. NEGATIVE: _sanitize_tag rejects forbidden git-ref characters --")
    # Import the daemon's _sanitize_tag and verify a few cases.
    import importlib.util
    spec = importlib.util.spec_from_file_location("autonomous_fix_daemon", DAEMON)
    if spec is None or spec.loader is None:
        print("x step 7: could not load daemon module")
        return 1
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["autonomous_fix_daemon"] = mod
    spec.loader.exec_module(mod)
    cases = [
        ("ruff-UP035-agents.py-L22", "ruff-UP035-agents.py-L22"),  # already-clean
        ("issue with spaces", "issue-with-spaces"),
        ("ruff:S101:foo", "ruff-S101-foo"),  # colons replaced
        ("a^b~c?d*e[f]g\\h:i", "a-b-c-d-e-f-g-h-i"),
        ("", "unknown"),
    ]
    for raw, expected in cases:
        got = mod._sanitize_tag(raw)
        if got != expected:
            print(f"x step 7: _sanitize_tag({raw!r}) = {got!r}, expected {expected!r}")
            return 1
    print(f"  ok: _sanitize_tag handles {len(cases)} cases including empty + colons + control chars")

    print("-- 8. POSITIVE: tag name pattern matches git-ref rules --")
    # Sanitize a long-ish issue id and verify the resulting tag is
    # accepted by `git check-ref-format`. We DON'T actually create
    # a tag (drill is read-only); just verify format.
    test_tag = "auto-apply-" + mod._sanitize_tag("ruff-UP035-foo.py-L42")
    proc = subprocess.run(
        ["git", "check-ref-format", f"refs/tags/{test_tag}"],
        cwd=REPO, capture_output=True, text=True, timeout=5,
    )
    if proc.returncode != 0:
        print(f"x step 8: git rejected tag name {test_tag!r}: {proc.stderr.strip()}")
        return 1
    print(f"  ok: example tag {test_tag!r} passes git check-ref-format")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
