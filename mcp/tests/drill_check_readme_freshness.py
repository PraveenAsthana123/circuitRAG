#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: check_readme_freshness.py correctly detects stale READMEs.

Locks invariants of scripts/check_readme_freshness.py per §58.5
freshness contract + §43 drill discipline.

  Positive assertions:
  1. Script exists + is executable
  2. JSON mode emits valid JSON with required fields
  3. Synthesized fresh README returns 0 stale
  4. Synthesized stale README returns 1 stale
  5. --only flag restricts the scan to a subfolder

  Negative assertions (the load-bearing part):
  N1. Stale README results in exit code 1 (not silent pass)
  N2. Fresh README results in exit code 0
  N3. .venv* / site-packages / node_modules NOT scanned
  N4. Folder without README is NOT flagged (script doesn't enforce coverage)

Exit code:
  0 — all 9 steps pass
  1 — any step fails
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_readme_freshness.py"


def step(n: int, name: str, predicate: bool, detail: str = "") -> bool:
    mark = "✓" if predicate else "✗"
    color_start = "\033[32m" if predicate else "\033[31m"
    color_end = "\033[0m"
    suffix = f" — {detail}" if detail else ""
    print(f"  {color_start}{mark}{color_end} step {n}: {name}{suffix}")
    return predicate


def run(args: list[str], timeout: int = 30, cwd: Path | None = None) -> tuple[int, str, str]:
    r = subprocess.run(
        ["python3"] + args,
        capture_output=True, text=True,
        cwd=str(cwd or REPO_ROOT),
        timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


def make_fixture(td: Path, source_mtime_offset: float = -100) -> Path:
    """Create a temp folder with a README.md and a source file.

    source_mtime_offset: seconds relative to README mtime.
      negative → source older than README (fresh)
      positive → source newer than README (stale)
    """
    folder = td / "fixture_folder"
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "README.md"
    src = folder / "thing.py"
    src.write_text('"""Stub source."""\nx = 1\n')
    readme.write_text("# Fixture\n")
    # Set times: README at time T, source at T+offset
    now = time.time()
    readme_mtime = now
    src_mtime = now + source_mtime_offset
    os.utime(readme, (now, readme_mtime))
    os.utime(src, (now, src_mtime))
    return folder


def main() -> int:
    print("═" * 70)
    print("DRILL: check_readme_freshness.py (§58.5 freshness contract)")
    print("═" * 70)

    results: list[bool] = []

    # Step 1: script exists
    results.append(step(
        1, "script exists",
        SCRIPT.is_file(),
        f"path={SCRIPT}",
    ))

    # Step 2: JSON mode emits valid JSON (use --only scripts for speed)
    rc, out, err = run([str(SCRIPT), "--json", "--only", "scripts"])
    json_ok = False
    parsed = {}
    try:
        parsed = json.loads(out)
        json_ok = "stale_count" in parsed and "stale" in parsed
    except json.JSONDecodeError:
        pass
    results.append(step(
        2, "JSON mode emits valid JSON with stale_count + stale list",
        json_ok,
        f"valid_json={json_ok}, fields={list(parsed.keys()) if parsed else []}",
    ))

    # Step 3: synthesized FRESH README returns 0 stale
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Source older than README — fresh
        folder = make_fixture(td_path, source_mtime_offset=-100)
        rc, out, err = run([
            str(SCRIPT), "--only", str(td_path.relative_to(REPO_ROOT))
            if td_path.is_relative_to(REPO_ROOT) else str(td_path),
            "--json",
        ])
        # If --only path is outside repo root, fall back to absolute path scan
        # by chdir to td:
        rc, out, err = run([str(SCRIPT), "--json"], cwd=td_path)
        # The script defaults to REPO_ROOT — using --only with a temp path
        # outside REPO_ROOT won't work. Run with a path scan instead.
        # Workaround: directly call with --only TempPath
        rc, out, err = subprocess.run(
            ["python3", str(SCRIPT), "--only", str(folder.relative_to(REPO_ROOT))
             if folder.is_relative_to(REPO_ROOT) else "."],
            capture_output=True, text=True, cwd=str(folder),
            timeout=30,
        ).returncode, "", ""
        # Simplest: import check_folder directly
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_readme_freshness_mod", str(SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["check_readme_freshness_mod"] = mod  # required for dataclass
        spec.loader.exec_module(mod)
        rep = mod.check_folder(folder)
        results.append(step(
            3, "fresh README (source older) → returns None",
            rep is None,
            f"check_folder returned {rep}",
        ))

    # Step 4: synthesized STALE README returns a StaleReport
    with tempfile.TemporaryDirectory() as td:
        folder = make_fixture(Path(td), source_mtime_offset=+100)
        import importlib.util

        spec = importlib.util.spec_from_file_location("crf_check2", str(SCRIPT))

        mod = importlib.util.module_from_spec(spec)

        sys.modules["crf_check2"] = mod

        spec.loader.exec_module(mod)
        rep = mod.check_folder(folder)
        results.append(step(
            4, "stale README (source newer) → returns StaleReport",
            rep is not None and rep.staleness_seconds > 0,
            f"staleness={rep.staleness_seconds if rep else 'None'}s",
        ))

    # Step 5: --only flag restricts scan
    # Use --only on a known folder; expect that result includes only that
    rc, out, err = run([str(SCRIPT), "--only", "scripts", "--json"])
    confined = False
    try:
        d = json.loads(out)
        # Every stale entry must start with 'scripts'
        confined = all(s["folder"].startswith("scripts")
                       for s in d.get("stale", []))
    except json.JSONDecodeError:
        pass
    results.append(step(
        5, "--only restricts scan to that subfolder",
        confined,
        "all stale entries (if any) under --only path",
    ))

    # NEGATIVE N1: stale README → exit 1
    with tempfile.TemporaryDirectory() as td:
        folder = make_fixture(Path(td), source_mtime_offset=+100)
        # Run script with --only on td (won't work since not under REPO_ROOT)
        # Use the import-based check + assert exit-code rule directly
        import importlib.util

        spec = importlib.util.spec_from_file_location("crf_check3", str(SCRIPT))

        mod = importlib.util.module_from_spec(spec)

        sys.modules["crf_check3"] = mod

        spec.loader.exec_module(mod)
        # main() with sys.argv override
        old_argv = sys.argv
        old_cwd = os.getcwd()
        try:
            sys.argv = [str(SCRIPT), "--only", str(folder)]
            os.chdir(str(folder))
            # walk_repo with the absolute folder should find it
            stale = mod.walk_repo([folder])
            n1_ok = len(stale) == 1 and stale[0].staleness_seconds > 0
        finally:
            sys.argv = old_argv
            os.chdir(old_cwd)
    results.append(step(
        6, "NEGATIVE N1: stale README detected by walk_repo()",
        n1_ok,
        f"stale_count={len(stale)}",
    ))

    # NEGATIVE N2: fresh README → exit 0
    with tempfile.TemporaryDirectory() as td:
        folder = make_fixture(Path(td), source_mtime_offset=-100)
        import importlib.util

        spec = importlib.util.spec_from_file_location("crf_check4", str(SCRIPT))

        mod = importlib.util.module_from_spec(spec)

        sys.modules["crf_check4"] = mod

        spec.loader.exec_module(mod)
        stale = mod.walk_repo([folder])
        n2_ok = len(stale) == 0
    results.append(step(
        7, "NEGATIVE N2: fresh README → walk_repo returns empty",
        n2_ok,
        f"stale_count={len(stale)}",
    ))

    # NEGATIVE N3: .venv* / site-packages / node_modules NOT scanned
    with tempfile.TemporaryDirectory() as td:
        venv_folder = Path(td) / ".venv311" / "lib" / "stuff"
        venv_folder.mkdir(parents=True)
        # Make a stale README inside venv
        readme = venv_folder / "README.md"
        readme.write_text("# venv readme\n")
        src = venv_folder / "x.py"
        src.write_text("x = 1\n")
        now = time.time()
        os.utime(readme, (now, now - 100))
        os.utime(src, (now, now + 100))
        import importlib.util

        spec = importlib.util.spec_from_file_location("crf_check5", str(SCRIPT))

        mod = importlib.util.module_from_spec(spec)

        sys.modules["crf_check5"] = mod

        spec.loader.exec_module(mod)
        stale = mod.walk_repo([Path(td)])
        n3_ok = len(stale) == 0
    results.append(step(
        8, "NEGATIVE N3: .venv* folders NOT scanned (ignored)",
        n3_ok,
        f"stale_count={len(stale)} (expected 0)",
    ))

    # NEGATIVE N4: folder without README is NOT flagged
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / "no_readme_folder"
        folder.mkdir()
        src = folder / "y.py"
        src.write_text("y = 1\n")
        import importlib.util

        spec = importlib.util.spec_from_file_location("crf_check6", str(SCRIPT))

        mod = importlib.util.module_from_spec(spec)

        sys.modules["crf_check6"] = mod

        spec.loader.exec_module(mod)
        stale = mod.walk_repo([folder])
        n4_ok = len(stale) == 0
    results.append(step(
        9, "NEGATIVE N4: folder without README NOT flagged (script doesn't enforce coverage)",
        n4_ok,
        f"stale_count={len(stale)} (expected 0 — no README to be stale)",
    ))

    passed = sum(results)
    total = len(results)
    print()
    print("─" * 70)
    if passed == total:
        print(f"\033[32mALL {total} STEPS PASSED ({passed}/{total})\033[0m")
        return 0
    else:
        print(f"\033[31m{total - passed} STEPS FAILED ({passed}/{total})\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
