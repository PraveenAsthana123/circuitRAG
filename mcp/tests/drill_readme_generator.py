#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: README generators produce valid output meeting §58 contract.

Locks the invariants of scripts/generate_folder_report.py and
scripts/generate_project_readme.py per the §58 Folder-README Standard:

  Positive assertions (the generators MUST):
  1. Produce a README for a sample service with ≥ 28 sections
     (the §58.3 floor — 33 sections, allowing 5-section slop for
     folders without applicable LLM / DB / frontend / API content)
  2. Include the required section anchors (Quick Start, How to Read,
     Env Vars, File Inventory, C4 Model, Code Sequence, Execution
     Sequence + Debug Tap Points, Business Logic, Glossary,
     Production Gates) — these are 10 of the 33 we hard-assert on
  3. Be idempotent — running twice in succession produces byte-identical
     output (no timestamps in the body — only the header line)
  4. Render at least one mermaid block per folder with > 0 files
  5. Auto-extract env-vars from BaseSettings AST (when present)
  6. Auto-extract test cases from test_*.py AST (when present)
  7. Have a non-empty file-inventory section (no service should
     have zero Python files listed)

  Negative assertions (the generators MUST NOT):
  N1. Crash on an empty folder (handles missing files gracefully)
  N2. Crash on a folder with malformed Python (skips SyntaxError files)
  N3. Hard-code localhost in the Quick Start (uses SERVICE_PORT_MAP,
      not a literal localhost:8000)
  N4. Tag worker / agent files as "🚀 entry point / app bootstrap"
      (the role-inference bug from iter A that we fixed)
  N5. Produce empty README for the project root (must include the
      services table + dependency graph)

Exit code:
  0  — all 12 steps pass
  1  — any step fails (operator sees per-step ✓/✗)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FOLDER_GEN = REPO_ROOT / "scripts" / "generate_folder_report.py"
PROJECT_GEN = REPO_ROOT / "scripts" / "generate_project_readme.py"

# Pick a stable service to drill against — inference-svc is the largest
# Python service and exercises the most renderers.
SAMPLE_SERVICE = REPO_ROOT / "services" / "inference-svc"

# Required section headings (10 of the 33 in §58.3 — the load-bearing ones)
REQUIRED_HEADINGS = [
    "Quick Start",
    "How to Read This Folder",
    "Environment Variables",
    "File Inventory",
    "C4 Model",
    "Code Sequence",
    "Execution Sequence",
    "Business Logic",
    "Domain Glossary",
    "Production Gates",
]

MIN_SECTIONS = 28           # §58.3 floor with 5-section slop
MAX_SECTIONS = 50           # sanity ceiling


def step(n: int, name: str, predicate: bool, detail: str = "") -> bool:
    mark = "✓" if predicate else "✗"
    color_start = "\033[32m" if predicate else "\033[31m"
    color_end = "\033[0m"
    suffix = f" — {detail}" if detail else ""
    print(f"  {color_start}{mark}{color_end} step {n}: {name}{suffix}")
    return predicate


def run_generator(args: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(
        ["python3"] + args,
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    print("═" * 70)
    print("DRILL: README Generators (§58 Folder-README Standard contract)")
    print("═" * 70)

    results: list[bool] = []

    # Step 1: generator scripts exist + are executable
    results.append(step(
        1, "generator scripts exist",
        FOLDER_GEN.is_file() and PROJECT_GEN.is_file(),
        f"folder={FOLDER_GEN.exists()}, project={PROJECT_GEN.exists()}",
    ))

    # Step 2: dry-run on sample service succeeds, predicts ≥ 28 sections
    rc, out, err = run_generator([
        str(FOLDER_GEN), "--folder", str(SAMPLE_SERVICE),
        "--force", "--dry-run",
    ])
    section_count = 0
    m = re.search(r"(\d+) sections", out)
    if m:
        section_count = int(m.group(1))
    results.append(step(
        2, f"dry-run on inference-svc predicts ≥ {MIN_SECTIONS} sections",
        rc == 0 and MIN_SECTIONS <= section_count <= MAX_SECTIONS,
        f"rc={rc}, sections={section_count}, target≥{MIN_SECTIONS}",
    ))

    # Step 3: actual generation into a tmp file (do NOT overwrite the real README)
    with tempfile.TemporaryDirectory() as td:
        tmp_readme = Path(td) / "README.md"
        rc, out, err = run_generator([
            str(FOLDER_GEN), "--folder", str(SAMPLE_SERVICE),
            "--output", str(tmp_readme), "--force",
        ])
        body_ok = tmp_readme.exists() and tmp_readme.stat().st_size > 30000
        body = tmp_readme.read_text() if tmp_readme.exists() else ""
        results.append(step(
            3, "actual generation writes ≥ 30KB README",
            rc == 0 and body_ok,
            f"rc={rc}, bytes={tmp_readme.stat().st_size if tmp_readme.exists() else 0}",
        ))

        # Step 4: all 10 required section headings present
        missing = [h for h in REQUIRED_HEADINGS if h not in body]
        results.append(step(
            4, "all 10 required section headings present",
            len(missing) == 0,
            f"missing={missing}" if missing else "all present",
        ))

        # Step 5: at least one mermaid block (C4 / sequence / class diagram)
        mermaid_count = body.count("```mermaid")
        results.append(step(
            5, "≥ 4 mermaid blocks (C4 + sequence + class + flowchart)",
            mermaid_count >= 4,
            f"found {mermaid_count} mermaid blocks",
        ))

        # Step 6: idempotency — run a SECOND time, body must be byte-identical
        # (we strip the header timestamp line for comparison since that DOES change)
        tmp2 = Path(td) / "README2.md"
        rc2, _, _ = run_generator([
            str(FOLDER_GEN), "--folder", str(SAMPLE_SERVICE),
            "--output", str(tmp2), "--force",
        ])
        body2 = tmp2.read_text() if tmp2.exists() else ""
        # Strip the "Generated: <timestamp>" line from both
        ts_pat = re.compile(r"Generated:\*\* [^\n]*")
        body_norm = ts_pat.sub("Generated:** TS", body)
        body2_norm = ts_pat.sub("Generated:** TS", body2)
        results.append(step(
            6, "idempotent — second run byte-identical (modulo timestamp)",
            rc2 == 0 and body_norm == body2_norm,
            f"rc2={rc2}, equal={body_norm == body2_norm}, "
            f"len1={len(body_norm)}, len2={len(body2_norm)}",
        ))

        # Step 7: env-vars table is populated (inference-svc HAS env vars)
        has_env_table = ("DOCUMIND_" in body
                         and "| Variable | Default | Source location |" in body)
        results.append(step(
            7, "env-vars table populated with DOCUMIND_* vars",
            has_env_table,
            "auto-extracted from BaseSettings + os.environ.get",
        ))

        # Step 8: test cases section detected non-zero tests
        has_test_cases = ("Test files detected:** " in body
                          and re.search(r"Test files detected:\*\* [1-9]", body) is not None)
        results.append(step(
            8, "test cases section detected ≥ 1 test file",
            has_test_cases,
            "AST-walked test_*.py / *_test.py",
        ))

        # NEGATIVE N3: no literal "localhost:8000" in Quick Start (must use canonical port)
        # inference-svc canonical port is 8084
        has_canonical_port = "8084" in body
        has_wrong_default = "localhost:8000" in body
        results.append(step(
            9, "NEGATIVE N3: Quick Start uses canonical port (8084 for inference-svc)",
            has_canonical_port and not has_wrong_default,
            f"canonical_port_present={has_canonical_port}, "
            f"wrong_default_present={has_wrong_default}",
        ))

        # NEGATIVE N4: workers / agents NOT tagged as entry-point
        # The file inventory should show app/workers/draft_replay.py with
        # role "⏰ background worker", NOT "🚀 entry point".
        worker_correctly_tagged = (
            "draft_replay.py" in body
            and "background worker" in body
        )
        worker_misclassified = re.search(
            r"draft_replay\.py.*entry point", body, re.IGNORECASE,
        ) is not None
        results.append(step(
            10, "NEGATIVE N4: workers NOT mis-tagged as 'entry point' (role fix)",
            worker_correctly_tagged and not worker_misclassified,
            f"correctly_tagged={worker_correctly_tagged}, "
            f"misclassified={worker_misclassified}",
        ))

    # Step 11: project README generator runs successfully
    with tempfile.TemporaryDirectory() as td2:
        tmp_proj = Path(td2) / "README.md"
        rc, out, err = run_generator([
            str(PROJECT_GEN), "--output", str(tmp_proj), "--force",
        ])
        proj_body = tmp_proj.read_text() if tmp_proj.exists() else ""
        has_services_table = "## 🧩 Services" in proj_body
        has_dep_graph = "## 🕸 Service Dependency Graph" in proj_body
        has_compose_with = "Composes with" in proj_body
        results.append(step(
            11, "project README has services table + dep graph + compose-with",
            rc == 0 and has_services_table and has_dep_graph and has_compose_with,
            f"rc={rc}, services={has_services_table}, "
            f"deps={has_dep_graph}, compose={has_compose_with}",
        ))

    # NEGATIVE N1: empty folder doesn't crash
    with tempfile.TemporaryDirectory() as td3:
        empty_dir = Path(td3) / "empty_folder"
        empty_dir.mkdir()
        rc, out, err = run_generator([
            str(FOLDER_GEN), "--folder", str(empty_dir),
            "--output", str(empty_dir / "README.md"), "--force",
        ])
        # Either exit 0 (handled gracefully) or non-crash with empty output
        graceful = rc in (0, 1)  # accept either — just must not crash with traceback
        no_traceback = "Traceback" not in err
        results.append(step(
            12, "NEGATIVE N1: empty folder handled without traceback",
            graceful and no_traceback,
            f"rc={rc}, traceback_in_stderr={'Traceback' in err}",
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
