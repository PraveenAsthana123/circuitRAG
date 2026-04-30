#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: CI strict-gate contract.

Locks .github/workflows/ci.yml so future drift can't soft-fail
critical lint/type/security gates. Specifically:
  - mypy step MUST NOT carry `|| true` (was non-blocking; clean
    since d0c1a1f, now blocking)
  - ruff step MUST run as a hard gate (no `|| true`)
  - bandit step MUST run as a hard gate (no `|| true`)
  - pip-audit MAY remain soft (third-party CVE drift is
    eventually-consistent; soft is the correct choice)

Negative assertions cover: ci.yml absent; mypy step soft; ruff
step soft; bandit step soft; mypy step calling against a smaller
target than libs/py/documind_core (would silently shrink coverage).
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: ci.yml exists --")
    if not CI.exists():
        raise AssertionError(f"missing {CI.relative_to(REPO)}")
    text = CI.read_text(encoding="utf-8")
    print("  ok: ci.yml present")

    print("-- 2. POSITIVE: mypy step exists + targets libs/py/documind_core --")
    require(text, "mypy --ignore-missing-imports libs/py/documind_core",
            "mypy command targeting documind_core")
    print("  ok: mypy step + correct target")

    print("-- 3. NEGATIVE: mypy step MUST NOT carry || true (hard gate) --")
    # Find the mypy line and assert no || true on it.
    for line in text.splitlines():
        if "mypy --ignore-missing-imports libs/py/documind_core" in line:
            if "|| true" in line:
                raise AssertionError(
                    f"mypy step is non-blocking ('|| true' present): {line!r}; "
                    "clean since d0c1a1f — drill enforces hard gate"
                )
    print("  ok: mypy is a hard gate")

    print("-- 4. NEGATIVE: ruff step MUST be a hard gate --")
    for line in text.splitlines():
        if line.strip().startswith("run: ruff check"):
            if "|| true" in line:
                raise AssertionError(
                    f"ruff step is non-blocking: {line!r}; "
                    "ruff is at 0 errors and must stay there"
                )
    print("  ok: ruff is a hard gate")

    print("-- 5. NEGATIVE: bandit step MUST be a hard gate --")
    for line in text.splitlines():
        if line.strip().startswith("run: bandit -r"):
            if "|| true" in line:
                raise AssertionError(
                    f"bandit step is non-blocking: {line!r}; "
                    "bandit findings must fail CI (operator review path "
                    "documented in scripts/issue_dispatcher.py)"
                )
    print("  ok: bandit is a hard gate")

    print("-- 6. NEGATIVE: mypy target MUST NOT silently shrink --")
    # If someone changes the target to e.g. libs/py/documind_core/foo.py,
    # most modules go uncovered. Drill enforces directory-scope target.
    m = re.search(
        r"mypy --ignore-missing-imports\s+(\S+)",
        text,
    )
    if not m:
        raise AssertionError("mypy command not parseable")
    target = m.group(1)
    if "/" not in target:
        raise AssertionError(
            f"mypy target is too narrow: {target!r}; expected a "
            f"directory path like libs/py/documind_core"
        )
    if not target.endswith("documind_core"):
        raise AssertionError(
            f"mypy target shrank: {target!r}; must end with 'documind_core' "
            f"to keep all 22 source files in scope"
        )
    print(f"  ok: mypy targets {target}")

    print("-- 7. POSITIVE: pip-audit may remain non-blocking --")
    # CVE drift is eventually-consistent across upstream feeds; treating
    # it as hard creates flake. Document that pip-audit |  true is
    # INTENTIONAL by checking the step still has the comment marker.
    pip_audit_present = any(
        "pip-audit" in line and "non-blocking" in line
        for line in text.splitlines()
    )
    if not pip_audit_present:
        # Either pip-audit absent (fine) or step name lost the
        # "non-blocking" marker. Don't fail; just note.
        print("  note: pip-audit step or non-blocking marker not found "
              "(check if intentional)")
    else:
        print("  ok: pip-audit step preserved as non-blocking (intentional)")

    print("\nALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
