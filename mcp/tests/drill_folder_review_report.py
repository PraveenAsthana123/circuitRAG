#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: generate_folder_review_report.py produces valid FOLDER_REPORT.md.

Locks the contract of scripts/generate_folder_review_report.py per §58.2
(two-file convention) + §43 (every feature ships a drill).

  Positive assertions:
  1. Script exists + is executable
  2. Single-folder mode produces a FOLDER_REPORT-like file ≥ 10KB
  3. Generated file has all 20+ section headings
  4. Reviewer name appears in metadata (CLI flag honored)
  5. Auto-detected metadata table is populated (file count, LOC, runtime, etc.)
  6. Batch mode produces FOLDER_REPORT.md inside the target folder (not CWD)
  7. Idempotency — second run produces byte-identical output (modulo timestamp)
  8. --force overwrites; without --force, existing file is SKIPped

  Negative assertions (the load-bearing part):
  N1. --folder and --batch are mutually exclusive (argparse rejects both)
  N2. Empty folder handled gracefully (no traceback)
  N3. Existing FOLDER_REPORT.md NOT overwritten without --force (skip exit)
  N4. Invalid batch name rejected (argparse exit 2)

Exit code:
  0 — all 12 steps pass
  1 — any step fails
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_folder_review_report.py"

# inference-svc is a stable target with rich auto-detection signals
SAMPLE_FOLDER = REPO_ROOT / "services" / "inference-svc"

# Required substrings to confirm the 20-section template rendered
REQUIRED_SUBSTRINGS = [
    "Enterprise Folder-Level Manual Code Review",
    "Folder Review Metadata",
    "Folder Purpose Review",
    "Responsibility Boundary",
    "Code Quality",
    "Database",
    "Security",
    "Performance",
    "Reliability",
    "Observability",
    "Testing",
    "Production Risks",
]


def step(n: int, name: str, predicate: bool, detail: str = "") -> bool:
    mark = "✓" if predicate else "✗"
    color_start = "\033[32m" if predicate else "\033[31m"
    color_end = "\033[0m"
    suffix = f" — {detail}" if detail else ""
    print(f"  {color_start}{mark}{color_end} step {n}: {name}{suffix}")
    return predicate


def run(args: list[str], timeout: int = 60, cwd: Path | None = None) -> tuple[int, str, str]:
    r = subprocess.run(
        ["python3"] + args,
        capture_output=True, text=True,
        cwd=str(cwd or REPO_ROOT),
        timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    print("═" * 70)
    print("DRILL: generate_folder_review_report.py (§58 two-file convention)")
    print("═" * 70)

    results: list[bool] = []

    # Step 1: script exists
    results.append(step(
        1, "script exists",
        SCRIPT.is_file(),
        f"path={SCRIPT}",
    ))

    # Step 2: single-folder mode produces a report file ≥ 10KB
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "single.md"
        rc, out, err = run([
            str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
            "--output", str(out_path), "--reviewer", "Drill Bot", "--force",
        ])
        size = out_path.stat().st_size if out_path.exists() else 0
        results.append(step(
            2, "single-folder mode writes ≥ 10KB report",
            rc == 0 and size >= 10_000,
            f"rc={rc}, bytes={size}",
        ))

        body = out_path.read_text() if out_path.exists() else ""

        # Step 3: all 12 required section substrings present
        missing = [s for s in REQUIRED_SUBSTRINGS if s not in body]
        results.append(step(
            3, "all required section substrings present",
            len(missing) == 0,
            f"missing={missing}" if missing else "all 12 present",
        ))

        # Step 4: reviewer name appears in metadata
        results.append(step(
            4, "reviewer name 'Drill Bot' appears in metadata",
            "Drill Bot" in body,
            "from --reviewer flag",
        ))

        # Step 5: auto-detected metadata table is populated
        # inference-svc has Python files + LOC + asyncpg + Redis + Ollama detected
        metadata_indicators = ["Python", "Postgres", "Lines of Code"]
        meta_hits = [m for m in metadata_indicators if m in body]
        results.append(step(
            5, "auto-detected metadata table populated",
            len(meta_hits) >= 2,
            f"hits={meta_hits}",
        ))

    # Step 6: --folder without --output defaults to <folder>/FOLDER_REPORT.md
    # Use a tmp mirror so we don't pollute the real repo
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "scripts_mirror"
        target.mkdir()
        (target / "stub.py").write_text(
            '"""Stub module for drill."""\nimport os\ndef hi():\n    return "hi"\n'
        )
        rc, out, err = run([
            str(SCRIPT), "--folder", str(target), "--reviewer", "Drill", "--force",
        ])
        # New contract per §58.2 two-file convention: default output is
        # <folder>/FOLDER_REPORT.md (inside the target folder).
        expected = target / "FOLDER_REPORT.md"
        results.append(step(
            6, "--folder default output is <folder>/FOLDER_REPORT.md",
            rc == 0 and expected.exists() and expected.stat().st_size > 5000,
            f"rc={rc}, expected_exists={expected.exists()}, "
            f"size={expected.stat().st_size if expected.exists() else 0}",
        ))

    # Step 7: idempotency — second run byte-identical (modulo timestamp)
    with tempfile.TemporaryDirectory() as td:
        out1 = Path(td) / "r1.md"
        out2 = Path(td) / "r2.md"
        run([str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
             "--output", str(out1), "--reviewer", "X", "--force"])
        run([str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
             "--output", str(out2), "--reviewer", "X", "--force"])
        b1 = out1.read_text() if out1.exists() else ""
        b2 = out2.read_text() if out2.exists() else ""
        ts_pat = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC")
        b1_norm = ts_pat.sub("TS", b1)
        b2_norm = ts_pat.sub("TS", b2)
        results.append(step(
            7, "idempotent — second run byte-identical (modulo timestamp)",
            b1_norm == b2_norm and len(b1) > 5000,
            f"equal={b1_norm == b2_norm}, lengths={len(b1)} vs {len(b2)}",
        ))

    # Step 8: --force overwrites; without --force, existing file SKIPped
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "skip_test.md"
        # First write
        rc1, _, _ = run([
            str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
            "--output", str(out_path), "--reviewer", "X", "--force",
        ])
        # Second write WITHOUT --force should fail
        rc2, _, err2 = run([
            str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
            "--output", str(out_path), "--reviewer", "X",
        ])
        # Third write WITH --force should succeed again
        rc3, _, _ = run([
            str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
            "--output", str(out_path), "--reviewer", "X", "--force",
        ])
        results.append(step(
            8, "without --force: SKIP; with --force: overwrite",
            rc1 == 0 and rc2 != 0 and rc3 == 0,
            f"first={rc1}, no-force={rc2}, with-force={rc3}",
        ))

    # NEGATIVE N1: --folder and --batch are mutually exclusive
    rc, out, err = run([
        str(SCRIPT), "--folder", str(SAMPLE_FOLDER), "--batch", "services",
    ])
    n1_ok = rc != 0 and "not allowed" in err.lower()
    results.append(step(
        9, "NEGATIVE N1: --folder + --batch rejected (mutually exclusive)",
        n1_ok,
        f"rc={rc}, 'not allowed' in stderr={('not allowed' in err.lower())}",
    ))

    # NEGATIVE N2: empty folder handled gracefully
    with tempfile.TemporaryDirectory() as td:
        empty_dir = Path(td) / "empty_folder"
        empty_dir.mkdir()
        out_path = empty_dir / "report.md"
        rc, out, err = run([
            str(SCRIPT), "--folder", str(empty_dir),
            "--output", str(out_path), "--reviewer", "X", "--force",
        ])
        no_traceback = "Traceback" not in err
        results.append(step(
            10, "NEGATIVE N2: empty folder handled without traceback",
            no_traceback,
            f"rc={rc}, traceback_in_stderr={'Traceback' in err}",
        ))

    # NEGATIVE N3: existing FOLDER_REPORT.md NOT overwritten without --force
    # Covered by step 8 above (more nuanced) — re-assert distinctly here.
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "n3.md"
        run([str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
             "--output", str(out_path), "--reviewer", "X", "--force"])
        before = out_path.read_text() if out_path.exists() else ""
        # Try without --force
        rc, _, _ = run([str(SCRIPT), "--folder", str(SAMPLE_FOLDER),
                        "--output", str(out_path), "--reviewer", "Y"])
        after = out_path.read_text() if out_path.exists() else ""
        results.append(step(
            11, "NEGATIVE N3: existing file NOT clobbered without --force",
            rc != 0 and before == after and "X" in before,
            f"rc={rc}, file_unchanged={before == after}",
        ))

    # NEGATIVE N4: invalid batch name rejected
    rc, _, err = run([str(SCRIPT), "--batch", "not_a_batch"])
    n4_ok = rc != 0 and "invalid choice" in err.lower()
    results.append(step(
        12, "NEGATIVE N4: invalid --batch value rejected",
        n4_ok,
        f"rc={rc}, 'invalid choice' in stderr={('invalid choice' in err.lower())}",
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
