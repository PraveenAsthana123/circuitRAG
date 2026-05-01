# RESOURCES: readonly
"""
Drill: §27 Production Readiness Checker.

The checker (scripts/production-checker.js) runs 15 heuristic checks
against the repo before deployment. This drill verifies:

  1. Checker runs and emits valid JSON when PROD_CHECK_JSON=1
  2. Exactly 15 checks are registered (matches §27.1 mandate)
  3. Current repo state passes all ERROR-severity checks (exit 0)
  4. NEGATIVE: a temp file injected with a known-bad pattern
     (hardcoded http://localhost in a non-skip-pattern context) is
     caught — the count of localhost-URL findings goes UP.
  5. NEGATIVE: after the temp file is removed, the count returns to
     baseline (no leak from the injection).

Negative assertions per §43 are steps 4 and 5 — they prove:
  - The checker actually scans the filesystem (not a cached result)
  - The checker doesn't fabricate findings (count returns to baseline
    after injection cleanup)

Run:
    .venv/bin/python mcp/tests/drill_production_checker.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "scripts" / "production-checker.js"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def run_checker() -> tuple[int, dict]:
    """Run the checker with PROD_CHECK_JSON=1 and parse the trailing JSON."""
    env = os.environ.copy()
    env["PROD_CHECK_JSON"] = "1"
    result = subprocess.run(
        ["node", str(CHECKER)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    text = result.stdout
    # The script prints "--JSON--\n{...}" at the end.
    marker = "--JSON--\n"
    if marker not in text:
        return result.returncode, {}
    payload = text.split(marker, 1)[1].strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return result.returncode, {}
    return result.returncode, data


def localhost_finding_count(results: list[dict]) -> int:
    """Pull the 'count' for the localhost-URL check from the results
    array. Returns the integer count even when the check passes."""
    for r in results:
        if "localhost" in r.get("name", "").lower():
            return r.get("count", 0)
    return -1  # check not found at all


def main() -> int:
    failures = 0

    # 1. Run + valid JSON output.
    rc, data = run_checker()
    if data and "results" in data:
        ok(f"step 1: checker ran (exit {rc}); JSON parsed ({data.get('total')} checks)")
    else:
        fail(f"step 1: checker JSON parse failed (rc={rc})")
        return 1  # can't do anything else

    # 2. Exactly 15 checks (§27.1 mandate).
    if data["total"] == 15:
        ok("step 2: exactly 15 checks (§27.1 mandate)")
    else:
        fail(f"step 2: expected 15 checks, got {data['total']}")
        failures += 1

    # 3. Repo currently passes all ERROR checks (exit 0).
    if rc == 0:
        warns = data.get("warnings", 0)
        ok(f"step 3: 0 ERROR-severity failures; {warns} warning(s)")
    else:
        fail(
            f"step 3: checker exited {rc} with {data.get('errors')} error(s). "
            f"Fix the errors before this drill can pass."
        )
        failures += 1

    # 4. NEGATIVE — inject a bad pattern, run again, expect count to rise.
    baseline = localhost_finding_count(data["results"])
    inject_path = REPO / "services" / "frontend" / "lib" / "drill_inject_temp.ts"
    inject_content = (
        "// Drill-injected sentinel — DO NOT COMMIT.\n"
        "// Tests that production-checker.js catches hardcoded localhost.\n"
        "export const SENTINEL_BAD_URL = 'http://localhost:9999/test';\n"
    )
    try:
        inject_path.write_text(inject_content, encoding="utf-8")
        _, data2 = run_checker()
        post_count = localhost_finding_count(data2["results"])
        if post_count > baseline:
            ok(
                f"step 4 (negative): injected bad pattern caught "
                f"(localhost-URL count {baseline} → {post_count})"
            )
        else:
            fail(
                f"step 4 (negative): inject did NOT increase localhost-URL count "
                f"(baseline={baseline}, post={post_count}). Checker is not "
                f"reading the live filesystem."
            )
            failures += 1
    finally:
        # Always clean up — even if the assertion failed.
        if inject_path.exists():
            inject_path.unlink()

    # 5. NEGATIVE — count returned to baseline after cleanup.
    _, data3 = run_checker()
    final_count = localhost_finding_count(data3["results"])
    if final_count == baseline:
        ok(f"step 5 (negative): post-cleanup count {final_count} matches baseline {baseline}")
    else:
        fail(
            f"step 5 (negative): post-cleanup count {final_count} != baseline {baseline}. "
            f"Either drill leaked the temp file or checker has hidden state."
        )
        failures += 1

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL 5 STEPS PASSED{NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
