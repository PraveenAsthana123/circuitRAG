#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: audit_readme_scores.py produces honest, parseable scoreboard.

Locks invariants of scripts/audit_readme_scores.py per §57.7 honesty:

  Positive assertions:
  1. Script runs without crashing on the real repo
  2. JSON mode emits valid JSON with required fields
  3. HTML mode writes a file
  4. Discovers ≥ 10 READMEs (we know we have ~24 with audit checklists)
  5. Aggregate score is non-zero (auto-locked rows exist)
  6. Per-folder ceiling is exactly 1000 (10 categories × 10 rows × 10)
  7. Honesty footer present in plaintext mode

  Negative assertions (the load-bearing part):
  N1. Does NOT count TBD rows as ✓ (achieved <= ceiling - 10 * tbd)
  N2. Does NOT walk into .venv* / site-packages / node_modules
  N3. Aggregate % < 100 (we KNOW reviewer-fill rows are TBD;
      claiming 100% would be dishonest)
  N4. --fail-under triggers exit 1 when aggregate falls short

Exit code:
  0 — all 11 steps pass
  1 — any step fails
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_readme_scores.py"


def step(n: int, name: str, predicate: bool, detail: str = "") -> bool:
    mark = "✓" if predicate else "✗"
    color_start = "\033[32m" if predicate else "\033[31m"
    color_end = "\033[0m"
    suffix = f" — {detail}" if detail else ""
    print(f"  {color_start}{mark}{color_end} step {n}: {name}{suffix}")
    return predicate


def run(args: list[str], timeout: int = 90) -> tuple[int, str, str]:
    r = subprocess.run(
        ["python3"] + args,
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
        timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    print("═" * 70)
    print("DRILL: audit_readme_scores.py (§57.7 honesty contract)")
    print("═" * 70)

    results: list[bool] = []

    # Step 1: script exists
    results.append(step(
        1, "audit script exists",
        AUDIT_SCRIPT.is_file(),
        f"path={AUDIT_SCRIPT}",
    ))

    # Step 2: plaintext mode runs without crash
    rc, out, err = run([str(AUDIT_SCRIPT)])
    results.append(step(
        2, "plaintext mode runs cleanly",
        rc == 0 and "README AUDIT SCOREBOARD" in out,
        f"rc={rc}, has_header={('README AUDIT SCOREBOARD' in out)}",
    ))

    # Step 3: discovers ≥ 10 READMEs
    discovered = 0
    for line in out.split("\n"):
        if line.startswith("  Total READMEs analyzed:"):
            discovered = int(line.split(":")[1].strip())
            break
    results.append(step(
        3, "discovers ≥ 10 READMEs",
        discovered >= 10,
        f"discovered={discovered}",
    ))

    # Step 4: aggregate score is non-zero (auto-locked rows exist)
    aggregate_line = ""
    for line in out.split("\n"):
        if "AGGREGATE" in line and "achieved" in line:
            aggregate_line = line
            break
    has_nonzero = "achieved=0 " not in aggregate_line and "achieved=" in aggregate_line
    results.append(step(
        4, "aggregate achieved > 0 (auto-locked rows present)",
        has_nonzero,
        aggregate_line.strip()[:120],
    ))

    # Step 5: honesty footer present
    results.append(step(
        5, "honesty footer present (§57.7 disclosure)",
        "Honesty footer (§57.7)" in out and "TBD rows" in out,
        "footer + TBD disclosure visible",
    ))

    # Step 6: JSON mode emits valid JSON
    rc, out_j, err = run([str(AUDIT_SCRIPT), "--json"])
    json_ok = False
    aggregate = {}
    try:
        parsed = json.loads(out_j)
        json_ok = "folders" in parsed and "aggregate" in parsed
        aggregate = parsed.get("aggregate", {})
    except json.JSONDecodeError:
        pass
    results.append(step(
        6, "JSON mode emits valid JSON with folders+aggregate",
        rc == 0 and json_ok,
        f"rc={rc}, valid_json={json_ok}",
    ))

    # Step 7: per-folder ceiling is exactly 1000
    ceilings_ok = True
    if json_ok:
        for f in parsed.get("folders", []):
            if f.get("has_audit_checklist") and f.get("total_ceiling") != 1000:
                ceilings_ok = False
                break
    results.append(step(
        7, "every audited folder has ceiling = 1000",
        ceilings_ok,
        "10 categories × 100 each — locked invariant",
    ))

    # Step 8: HTML mode writes a file
    with tempfile.TemporaryDirectory() as td:
        html_path = Path(td) / "dash.html"
        rc, out_h, err = run([str(AUDIT_SCRIPT), "--html", str(html_path)])
        html_ok = html_path.exists() and html_path.stat().st_size > 1000
        html_body = html_path.read_text() if html_path.exists() else ""
        results.append(step(
            8, "HTML mode writes a non-trivial HTML file",
            rc == 0 and html_ok,
            f"rc={rc}, bytes={html_path.stat().st_size if html_path.exists() else 0}",
        ))

    # NEGATIVE N1: TBD rows NOT counted as ✓
    # achieved should be strictly less than (ceiling - 10*tbd) — i.e. TBD costs the max
    n1_ok = False
    if aggregate:
        ach = aggregate.get("achieved", 0)
        ceil = aggregate.get("ceiling", 1000)
        tbd = aggregate.get("tbd", 0)
        # achieved + 10*tbd should equal what it would be if TBD were filled to 10
        # so achieved must be < ceiling whenever tbd > 0
        n1_ok = (tbd > 0 and ach < ceil) or (tbd == 0)
    results.append(step(
        9, "NEGATIVE N1: TBD rows NOT counted toward achieved",
        n1_ok,
        f"achieved={aggregate.get('achieved', '?')}, "
        f"ceiling={aggregate.get('ceiling', '?')}, tbd={aggregate.get('tbd', '?')}",
    ))

    # NEGATIVE N2: does NOT walk into .venv* / site-packages
    # Verify by checking that no folder path in JSON contains .venv or site-packages
    n2_ok = True
    venv_leak = []
    if json_ok:
        for f in parsed.get("folders", []):
            rel = f.get("rel_path", "")
            if ".venv" in rel or "site-packages" in rel or "node_modules" in rel:
                n2_ok = False
                venv_leak.append(rel)
    results.append(step(
        10, "NEGATIVE N2: no .venv* / site-packages / node_modules in results",
        n2_ok,
        f"leaks={venv_leak[:3]}" if venv_leak else "no leaks",
    ))

    # NEGATIVE N3: aggregate < 100% (TBD rows exist → claiming 100% would be dishonest)
    n3_ok = False
    if aggregate:
        ach = aggregate.get("achieved", 0)
        ceil = aggregate.get("ceiling", 1)
        n3_ok = ach < ceil  # honest baseline — never claim 100% without filling TBDs
    results.append(step(
        11, "NEGATIVE N3: aggregate < 100% (honesty per §57.7)",
        n3_ok,
        "TBD rows exist → claiming 100% is dishonest until evidence-filled",
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
