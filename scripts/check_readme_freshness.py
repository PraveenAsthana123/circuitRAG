#!/usr/bin/env python3
"""
Check that every folder's README.md is fresher than its newest source file.

Per global §58.5 freshness contract: any source-file change in a folder
SHOULD trigger a re-run of the generators. This script is the fast
detector — walks every Python folder + compares README.md mtime to
the newest source file's mtime. Exits 1 on stale README.

Why fast: the §58.6 CI gate (.github/workflows/readme-freshness.yml)
runs the full regen-and-diff, which takes ~5 minutes. This script
runs in <1 second on a typical repo by reading mtimes. Use as a
pre-commit hook + a CI smoke-step before the full freshness job.

Per §57.7 honesty contract: only flags FOLDERS WITH A README that
have source-file mtimes newer than the README mtime. Folders without
a README are not flagged (the §58 standard says "should have" but
this script doesn't enforce coverage — see scripts/audit_readme_scores.py
for that).

Usage:
  python3 scripts/check_readme_freshness.py            # walk repo
  python3 scripts/check_readme_freshness.py --fix      # auto-regen stale ones
  python3 scripts/check_readme_freshness.py --json     # machine-readable
  python3 scripts/check_readme_freshness.py --only services/

Exit codes:
  0  — every README is fresh (or no README in scope)
  1  — at least one README is stale
  2  — script error (bad arg, IO failure)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

IGNORE_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", ".venv-redteam",
    "dist", "build", ".next", ".loop", ".archive-shims", ".tools",
    "mlruns", "data", ".pytest_cache",
}

# Source extensions whose mtime invalidates the README
SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go",
               ".java", ".rs", ".sh", ".sql", ".proto"}


@dataclass
class StaleReport:
    folder: str                      # repo-relative folder path
    readme_mtime: float
    newest_source: str               # repo-relative
    newest_source_mtime: float
    staleness_seconds: float
    newest_source_basename: str


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts) or any(
        part.startswith(".venv") for part in path.parts
    )


def _newest_source_mtime(folder: Path) -> tuple[Optional[Path], float]:
    """Return (path, mtime) of the newest source file in folder.

    Walks recursively. Skips IGNORE_DIRS. Returns (None, 0.0) if
    nothing source-like is found.
    """
    best_path: Optional[Path] = None
    best_mtime: float = 0.0
    for p in folder.rglob("*"):
        if not p.is_file() or _is_ignored(p):
            continue
        if p.suffix not in SOURCE_EXTS:
            continue
        # Skip the README itself
        if p.name == "README.md":
            continue
        try:
            m = p.stat().st_mtime
        except (PermissionError, OSError):
            continue
        if m > best_mtime:
            best_mtime = m
            best_path = p
    return best_path, best_mtime


def check_folder(folder: Path) -> Optional[StaleReport]:
    """Return a StaleReport if the folder's README is older than its
    newest source file. Returns None if README is fresh or absent."""
    readme = folder / "README.md"
    if not readme.exists():
        return None
    try:
        readme_mtime = readme.stat().st_mtime
    except (PermissionError, OSError):
        return None
    newest_path, newest_mtime = _newest_source_mtime(folder)
    if newest_path is None or newest_mtime <= readme_mtime:
        return None
    rel_folder = str(folder.relative_to(REPO_ROOT)) if folder.is_relative_to(REPO_ROOT) else str(folder)
    rel_source = str(newest_path.relative_to(REPO_ROOT)) if newest_path.is_relative_to(REPO_ROOT) else str(newest_path)
    return StaleReport(
        folder=rel_folder,
        readme_mtime=readme_mtime,
        newest_source=rel_source,
        newest_source_mtime=newest_mtime,
        staleness_seconds=newest_mtime - readme_mtime,
        newest_source_basename=newest_path.name,
    )


def walk_repo(only: List[Path] = None) -> List[StaleReport]:
    """Walk the repo (or the --only subfolders) and return all stale folders."""
    stale: List[StaleReport] = []
    roots = [REPO_ROOT / p for p in only] if only else [REPO_ROOT]
    visited: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for folder in [root] + sorted(root.rglob("*")):
            if not folder.is_dir() or _is_ignored(folder):
                continue
            if folder in visited:
                continue
            visited.add(folder)
            rep = check_folder(folder)
            if rep is not None:
                stale.append(rep)
    return stale


def fix_one(folder: Path) -> tuple[bool, str]:
    """Re-run the per-folder README generator on this folder."""
    gen = REPO_ROOT / "scripts" / "generate_folder_report.py"
    if not gen.exists():
        return False, f"generator not found: {gen}"
    try:
        r = subprocess.run(
            ["python3", str(gen), "--folder", str(folder), "--force"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            return False, f"rc={r.returncode}: {r.stderr.strip()[:200]}"
        return True, r.stdout.strip().split("\n")[-1] if r.stdout else "ok"
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def render_text(stale: List[StaleReport]) -> str:
    if not stale:
        return "✓ All README files are fresh.\n"
    lines = [
        "═" * 80,
        "  README FRESHNESS REPORT",
        "═" * 80,
        f"  {len(stale)} folder(s) have stale README.md",
        f"  (newest source file is newer than README mtime)",
        "─" * 80,
    ]
    for r in sorted(stale, key=lambda s: -s.staleness_seconds):
        age_hours = r.staleness_seconds / 3600
        lines.append(
            f"  • {r.folder}"
        )
        lines.append(
            f"      README.md       {datetime.fromtimestamp(r.readme_mtime, tz=timezone.utc):%Y-%m-%d %H:%M UTC}"
        )
        lines.append(
            f"      newest source   {datetime.fromtimestamp(r.newest_source_mtime, tz=timezone.utc):%Y-%m-%d %H:%M UTC}"
            f"  ({r.newest_source_basename})"
        )
        lines.append(
            f"      stale by        {age_hours:.1f}h ({int(r.staleness_seconds)}s)"
        )
    lines.append("─" * 80)
    lines.append("  To fix:")
    lines.append("    python3 scripts/check_readme_freshness.py --fix")
    lines.append("  Or regenerate everything:")
    lines.append("    bash scripts/regen_all_docs.sh --reviewer 'Your Name'")
    lines.append("═" * 80)
    return "\n".join(lines) + "\n"


def render_json(stale: List[StaleReport]) -> str:
    return json.dumps({
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "stale_count": len(stale),
        "stale": [asdict(r) for r in stale],
    }, indent=2)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check README.md mtime vs newest source file in each folder.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--only", type=Path, action="append", default=[],
                   help="Only scan these subfolders (repeatable).")
    p.add_argument("--fix", action="store_true",
                   help="Auto-regen each stale README (calls generate_folder_report.py).")
    p.add_argument("--json", action="store_true",
                   help="Emit JSON to stdout instead of human-readable text.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    stale = walk_repo(args.only)
    if args.json:
        print(render_json(stale))
    else:
        print(render_text(stale), end="")
    if args.fix and stale:
        print("\nRunning --fix:", file=sys.stderr)
        ok_count = 0
        for r in stale:
            ok, msg = fix_one(REPO_ROOT / r.folder)
            mark = "✓" if ok else "✗"
            print(f"  {mark} {r.folder}: {msg}", file=sys.stderr)
            if ok:
                ok_count += 1
        print(f"\nFixed: {ok_count}/{len(stale)}", file=sys.stderr)
        # After fix, re-walk to confirm
        remaining = walk_repo(args.only)
        if remaining:
            print(f"WARNING: {len(remaining)} folder(s) still stale after fix",
                  file=sys.stderr)
            return 1
        return 0
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
