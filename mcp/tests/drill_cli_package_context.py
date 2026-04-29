#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: CLI scripts use the sidecar_advisor_pkg context for relative
imports — the regression-catch that should have been here BEFORE
commit 87e1c02 shipped a broken capture_and_review.py.

Background: services/sidecar-advisor/advisor.py does
`from .council import PrReviewCouncil` lazily inside
_get_or_build_council(). For that relative import to resolve at
runtime, the advisor module MUST be loaded as
"sidecar_advisor_pkg.advisor" (with sys.modules["sidecar_advisor_pkg"]
set first), NOT as a top-level "_capture_advisor_mod".

The drills had been exercising this code path with proper package
context. Production CLI scripts (loaded via post-commit hook
subprocess) hadn't been verified — until 573e223 fixed
capture_and_review.py to match the drill pattern. This drill locks
the contract for both existing CLI scripts AND any future ones.

Five exercised steps in this local drill shape. Six negative assertions.

  1. Both CLI scripts that load sidecar modules exist.
  2. NEGATIVE: capture_and_review.py sets sys.modules
     ["sidecar_advisor_pkg"] BEFORE loading memory or advisor.
  3. NEGATIVE: capture_and_review.py loads memory as
     "sidecar_advisor_pkg.memory" (NOT a top-level name).
  4. NEGATIVE: capture_and_review.py loads advisor as
     "sidecar_advisor_pkg.advisor".
  5. NEGATIVE: replay_council_against_events.py uses the same
     pkg-namespace pattern (consistency across CLI scripts).
  6. NEGATIVE: BOTH scripts use IDENTICAL package name
     ("sidecar_advisor_pkg") — a future refactor changing one
     would break the contract silently.
  7. NEGATIVE: NO regressed names ("_capture_memory_mod" etc.)
     appear anywhere in the scripts. The pre-fix bug used such
     names; the regression check ensures they don't return.
  8. NEGATIVE: the package context setup happens BEFORE
     spec_from_file_location for memory/advisor (otherwise the
     loader wouldn't see the package context yet).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
CAPTURE = REPO / "scripts" / "capture_and_review.py"
REPLAY = REPO / "scripts" / "replay_council_against_events.py"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def main():
    # 1. Both CLI scripts exist
    step("1. capture_and_review.py + replay_council_against_events.py exist")
    if not CAPTURE.exists():
        fail(f"missing: {CAPTURE}")
    if not REPLAY.exists():
        fail(f"missing: {REPLAY}")
    capture_text = CAPTURE.read_text()
    replay_text = REPLAY.read_text()
    ok(f"both scripts present "
       f"({len(capture_text)} + {len(replay_text)} chars)")

    # 2. NEGATIVE: capture_and_review sets sys.modules pkg before loading
    step(
        "2. NEGATIVE: capture_and_review.py sets "
        "sys.modules['sidecar_advisor_pkg'] before loading memory/advisor"
    )
    pkg_pos = capture_text.find('sys.modules["sidecar_advisor_pkg"] = pkg')
    if pkg_pos < 0:
        # Try with single quotes
        pkg_pos = capture_text.find("sys.modules['sidecar_advisor_pkg'] = pkg")
    if pkg_pos < 0:
        fail(
            "capture_and_review.py doesn't set sys.modules['sidecar_advisor_pkg']. "
            "Without that, advisor's `from .council import` raises "
            "ImportError on every council fire."
        )
    # Find positions of memory + advisor module-loader calls
    mem_load_pos = capture_text.find('"sidecar_advisor_pkg.memory"')
    adv_load_pos = capture_text.find('"sidecar_advisor_pkg.advisor"')
    if pkg_pos > mem_load_pos or pkg_pos > adv_load_pos:
        fail(
            f"package context set AFTER module load (pos pkg={pkg_pos}, "
            f"memory={mem_load_pos}, advisor={adv_load_pos}). "
            f"Loaders must see the package in sys.modules first."
        )
    ok(f"pkg context set at {pkg_pos}; before mem ({mem_load_pos}) + adv ({adv_load_pos})")

    # 3. NEGATIVE: memory loaded as sidecar_advisor_pkg.memory
    step("3. NEGATIVE: memory module loaded as 'sidecar_advisor_pkg.memory'")
    if '"sidecar_advisor_pkg.memory"' not in capture_text:
        fail(
            "capture_and_review.py doesn't load memory as "
            "'sidecar_advisor_pkg.memory'. Top-level naming would "
            "make any future relative-import in memory.py fail."
        )
    ok("memory uses pkg-namespaced name")

    # 4. NEGATIVE: advisor loaded as sidecar_advisor_pkg.advisor
    step("4. NEGATIVE: advisor module loaded as 'sidecar_advisor_pkg.advisor'")
    if '"sidecar_advisor_pkg.advisor"' not in capture_text:
        fail(
            "capture_and_review.py doesn't load advisor as "
            "'sidecar_advisor_pkg.advisor'. Without this, "
            "advisor.py's lazy `from .council import` raises ImportError."
        )
    ok("advisor uses pkg-namespaced name")

    # 5. NEGATIVE: replay_council uses same pkg-namespace pattern
    step("5. NEGATIVE: replay_council_against_events.py uses same pattern")
    if '"sidecar_advisor_pkg"' not in replay_text:
        fail("replay_council script doesn't use sidecar_advisor_pkg")
    if '"sidecar_advisor_pkg.memory"' not in replay_text:
        fail("replay_council doesn't load memory under pkg namespace")
    if '"sidecar_advisor_pkg.advisor"' not in replay_text:
        fail("replay_council doesn't load advisor under pkg namespace")
    ok("replay_council uses identical pkg-namespace pattern")

    # 6. NEGATIVE: identical package name in BOTH scripts
    step("6. NEGATIVE: BOTH scripts use identical package name")
    capture_pkg = re.findall(
        r'sys\.modules\[["\']([a-z_]+)["\']\]\s*=', capture_text,
    )
    replay_pkg = re.findall(
        r'sys\.modules\[["\']([a-z_]+)["\']\]\s*=', replay_text,
    )
    capture_pkgs = {p for p in capture_pkg if "sidecar" in p}
    replay_pkgs = {p for p in replay_pkg if "sidecar" in p}
    if capture_pkgs != replay_pkgs:
        fail(
            f"package names diverged: capture uses {capture_pkgs}, "
            f"replay uses {replay_pkgs}. Drills + future scripts "
            f"must agree on the name 'sidecar_advisor_pkg' for "
            f"sys.modules to share state."
        )
    if "sidecar_advisor_pkg" not in capture_pkgs:
        fail(
            f"both scripts diverged from 'sidecar_advisor_pkg'; "
            f"got {capture_pkgs}. The drills use that exact name."
        )
    ok(f"both scripts use 'sidecar_advisor_pkg' (consistent)")

    # 7. NEGATIVE: no regressed legacy names
    step(
        "7. NEGATIVE: no regressed legacy module names "
        "('_capture_*_mod', '_sidecar_pkg', etc.)"
    )
    forbidden = [
        '"_capture_memory_mod"',
        '"_capture_advisor_mod"',
        '"_sidecar_pkg"',
    ]
    leaked = [name for name in forbidden if name in capture_text]
    if leaked:
        fail(
            f"capture_and_review.py contains regressed names: "
            f"{leaked}. The pre-fix code used these and broke. "
            f"Use 'sidecar_advisor_pkg.<module>' instead."
        )
    leaked_replay = [name for name in forbidden if name in replay_text]
    if leaked_replay:
        fail(f"replay_council contains regressed names: {leaked_replay}")
    ok("no legacy name regressions in either script")

    # 8. NEGATIVE: pkg context setup BEFORE any spec_from_file_location
    step(
        "8. NEGATIVE: pkg context setup precedes ALL "
        "spec_from_file_location calls in cli()"
    )
    # Find the cli() function body in capture_and_review
    cli_match = re.search(
        r"def cli\(\)[^{]*?:\s*(.*?)(?=\n\ndef |\Z)",
        capture_text, re.DOTALL,
    )
    if not cli_match:
        fail("can't find cli() function body in capture_and_review.py")
    cli_body = cli_match.group(1)
    # Within cli() body, the first sys.modules["sidecar_advisor_pkg"]
    # assignment must come BEFORE any spec_from_file_location call.
    pkg_pos_cli = cli_body.find('sys.modules["sidecar_advisor_pkg"]')
    spec_pos_cli = cli_body.find("spec_from_file_location")
    if pkg_pos_cli < 0 or spec_pos_cli < 0:
        fail(
            f"cli() missing pkg setup ({pkg_pos_cli}) or spec_from_file_location ({spec_pos_cli})"
        )
    if pkg_pos_cli > spec_pos_cli:
        fail(
            f"pkg setup at {pkg_pos_cli} comes AFTER spec call at "
            f"{spec_pos_cli}. Loaders must see the package context "
            f"first or relative imports inside the loaded module fail."
        )
    ok(f"pkg setup ({pkg_pos_cli}) precedes spec_from_file_location ({spec_pos_cli})")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 CLI-PACKAGE-CONTEXT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
