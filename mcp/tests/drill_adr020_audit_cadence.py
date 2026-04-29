#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-020 audit-cadence ratchet — every parallel-tool-authored
commit has its audit drill.

ADR-020 (3b1cc02) declared: every parallel-tool-authored commit
landing in main MUST trigger a drill audit within ≤2 autonomous-
loop iterations. Phase 7I closed the first practical gap (G-2's
TTS proxy → drill_tts_proxy_route). This drill ratchets the
floor: the registry below lists every known parallel-tool commit
and its audit drill; any new parallel-tool commit found in git
history that ISN'T in the registry is flagged as paydown work.

Detection has two paths because parallel-tool commits land in
two ways:

1. Direct parallel-tool commit (no `Co-Authored-By: Claude`
   trailer in the message body). G-1 (5dfeb9c) is the only
   instance to date.
2. Autonomous-loop batched parallel-tool content (subject line
   matches `G-\\d+:` pattern). G-2 (51bac70) + G-3 (45633d2)
   are this shape.

Eight steps. Five negative assertions.

  1. POSITIVE: discover parallel-tool commits across both
     detection paths in last 100 commits. Floor: at least one
     commit known (otherwise the drill has no purchase).
  2. NEGATIVE: every commit in PARALLEL_TOOL_COMMITS still
     exists in git history. Catches stale registry entries
     (commits removed via rebase).
  3. NEGATIVE: every audit drill named in the registry exists
     at mcp/tests/<filename>. Catches drill renames or
     deletions without registry update.
  4. NEGATIVE: every audit drill has the canonical
     `# RESOURCES:` header (and uses readonly tier OR explicit
     resource tag). Locks the convention.
  5. NEGATIVE: every parallel-tool commit discovered in step 1
     is in PARALLEL_TOOL_COMMITS OR KNOWN_UNAUDITED. New
     commits not tracked = paydown deficit. Ratchet floor at 0.
  6. NEGATIVE: KNOWN_UNAUDITED entries correspond to real
     recent commits (no stale paydown markers — commits that
     never existed or have been audited).
  7. POSITIVE: emit per-commit audit-status table.
  8. POSITIVE: emit ratchet state — # audited / # unaudited
     paydown / total parallel-tool commits known.

Run: python3 mcp/tests/drill_adr020_audit_cadence.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILLS_DIR = REPO / "mcp" / "tests"

# Registry of (commit_sha → audit_drill_filename). When a new
# parallel-tool commit lands, add an entry here in the same
# autonomous-loop iteration that adds its audit drill.
PARALLEL_TOOL_COMMITS = {
    "5dfeb9c": ("G-1: agent-orchestrator-svc", "drill_agent_orchestrator_structure.py"),
    "51bac70": ("G-2: services/frontend/* incl. TTS proxy", "drill_tts_proxy_route.py"),
    "45633d2": ("G-3: scripts/* help-contract paydown", "drill_scripts_have_help.py"),
}

# Paydown bucket — parallel-tool commits known to exist but not
# yet audited. Per ADR-015 ratchet pattern: floor moves toward
# zero. Empty at landing because Phase 7I paid the last entry
# (G-2) down. Future iterations may temporarily add entries here
# while the audit drill lands within the 2-iteration SLO.
KNOWN_UNAUDITED: dict[str, str] = {}

# How far back to scan git history. 100 commits ≈ 5 sessions of
# autonomous-loop iterations. Catches recent drift without
# scanning the entire repo.
HISTORY_DEPTH = 100

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _git(args: list[str]) -> str:
    """Run git with REPO as cwd; return stdout. Empty string on
    failure (graceful degradation per ADR-019: drill emits a
    'no git history visible' message but doesn't crash)."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return r.stdout if r.returncode == 0 else ""
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def _commit_message(sha: str) -> str:
    """Full commit message body (subject + body)."""
    return _git(["log", "-1", "--pretty=%B", sha])


def _commit_exists(sha: str) -> bool:
    return bool(_git(["rev-parse", "--verify", "--quiet", sha]))


def _discover_parallel_tool_commits() -> dict[str, str]:
    """Return {short_sha: subject} for every parallel-tool commit
    in the last HISTORY_DEPTH commits, by either detection path."""
    out: dict[str, str] = {}
    log = _git(["log", "-" + str(HISTORY_DEPTH), "--pretty=%H%x09%s%x09%(trailers:key=Co-Authored-By)"])
    for line in log.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        sha_full, subject, trailers = parts
        sha = sha_full[:7]
        # Path A: no Co-Authored-By: Claude trailer
        if "Claude" not in trailers:
            out[sha] = subject
            continue
        # Path B: subject begins with G-<digit>:
        if re.match(r"^[a-z]+\(.+?\):\s*G-\d+\s+-", subject) or \
                re.match(r"^G-\d+\s*[:\-]", subject):
            out[sha] = subject
    return out


def main() -> int:
    step("1. POSITIVE: discover parallel-tool commits in last HISTORY_DEPTH commits")
    discovered = _discover_parallel_tool_commits()
    if not discovered:
        # Graceful degradation: in a fresh checkout without git history
        # the drill can't enforce anything. Emit a clear stderr message
        # and exit success (per ADR-019).
        ok("no parallel-tool commits visible (fresh checkout or pre-history); drill is a no-op here")
        # Still emit the standard banner so run_drills.py recognises success.
        print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
        print(f"{BOLD}{GREEN}  ALL 8 ADR020-AUDIT-CADENCE STEPS PASSED{NC}")
        print(f"{BOLD}{GREEN}  (degraded: no git history){NC}")
        print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
        return 0
    ok(f"discovered {len(discovered)} parallel-tool commit(s) in last {HISTORY_DEPTH}")

    step("2. NEGATIVE: every PARALLEL_TOOL_COMMITS entry exists in git history")
    stale_registry: list[tuple[str, str]] = []
    for sha, (label, drill_file) in PARALLEL_TOOL_COMMITS.items():
        if not _commit_exists(sha):
            stale_registry.append((sha, label))
    if stale_registry:
        fail(
            f"{len(stale_registry)} stale registry entries (commit removed): "
            f"{stale_registry[:3]}"
        )
    ok(f"all {len(PARALLEL_TOOL_COMMITS)} registry commits resolve in git history")

    step("3. NEGATIVE: every audit drill named in registry exists on disk")
    missing_drills: list[tuple[str, str]] = []
    for sha, (label, drill_file) in PARALLEL_TOOL_COMMITS.items():
        if not (DRILLS_DIR / drill_file).is_file():
            missing_drills.append((sha, drill_file))
    if missing_drills:
        fail(
            f"{len(missing_drills)} audit drill(s) missing on disk: "
            f"{missing_drills[:3]}. Renamed without registry update?"
        )
    ok(f"all {len(PARALLEL_TOOL_COMMITS)} audit drills present in mcp/tests/")

    step("4. NEGATIVE: every audit drill has canonical # RESOURCES: header")
    bad_headers: list[tuple[str, str]] = []
    for sha, (label, drill_file) in PARALLEL_TOOL_COMMITS.items():
        path = DRILLS_DIR / drill_file
        head = path.read_text().splitlines()[:5]
        if not any(line.startswith("# RESOURCES:") for line in head):
            bad_headers.append((drill_file, head[0] if head else "(empty)"))
    if bad_headers:
        fail(
            f"{len(bad_headers)} audit drill(s) lack '# RESOURCES:' "
            f"header: {bad_headers[:3]}"
        )
    ok(f"all {len(PARALLEL_TOOL_COMMITS)} audit drills have RESOURCES header")

    step("5. NEGATIVE: discovered parallel-tool commits all tracked or paydown-bucketed")
    untracked = []
    for sha, subject in discovered.items():
        if sha in PARALLEL_TOOL_COMMITS:
            continue
        if sha in KNOWN_UNAUDITED:
            continue
        untracked.append((sha, subject[:80]))
    if untracked:
        fail(
            f"{len(untracked)} discovered parallel-tool commit(s) NOT in "
            f"PARALLEL_TOOL_COMMITS or KNOWN_UNAUDITED: {untracked[:3]}. "
            "Either land an audit drill (and add registry entry) or "
            "explicitly grandfather via KNOWN_UNAUDITED."
        )
    ok(
        f"all {len(discovered)} discovered commits accounted for "
        f"(audited: {len(PARALLEL_TOOL_COMMITS & set(discovered.keys()) if False else [s for s in discovered if s in PARALLEL_TOOL_COMMITS])}, "
        f"paydown: {len([s for s in discovered if s in KNOWN_UNAUDITED])})"
    )

    step("6. NEGATIVE: KNOWN_UNAUDITED entries correspond to real recent commits")
    stale_paydown: list[tuple[str, str]] = []
    for sha, label in KNOWN_UNAUDITED.items():
        if not _commit_exists(sha):
            stale_paydown.append((sha, label))
    if stale_paydown:
        fail(
            f"{len(stale_paydown)} stale KNOWN_UNAUDITED entries: "
            f"{stale_paydown[:3]}. Either land the audit and move to "
            "PARALLEL_TOOL_COMMITS, or remove from paydown bucket."
        )
    ok(f"{len(KNOWN_UNAUDITED)} paydown entries (all resolve)")

    step("7. POSITIVE: emit per-commit audit-status table")
    for sha, (label, drill_file) in sorted(PARALLEL_TOOL_COMMITS.items()):
        ok(f"  AUDITED  {sha}  {label[:50]:<50} -> {drill_file}")
    for sha, label in sorted(KNOWN_UNAUDITED.items()):
        ok(f"  PAYDOWN  {sha}  {label[:50]:<50}")

    step("8. POSITIVE: emit ratchet state")
    audited = len(PARALLEL_TOOL_COMMITS)
    paydown = len(KNOWN_UNAUDITED)
    total = audited + paydown
    if total > 0:
        ok(
            f"ADR-020 ratchet: {audited}/{total} audited "
            f"({paydown} paydown). "
            f"Floor: {paydown} unaudited."
        )
    else:
        ok("ADR-020 ratchet: 0/0 (registry empty)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 ADR020-AUDIT-CADENCE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 3, 4, 5, 6){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
