#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: audit_*.py survey schema contract.

The renamed survey audits are operator-facing reports, not gates.
They must keep a stable shape so dashboards and scripts can parse
their output without guessing. This drill locks the shared schema:

  1. every audit_*.py has a module docstring
  2. NEGATIVE: every audit_*.py self-declares "audit" and exit-zero
     semantics in its docstring
  3. NEGATIVE: every audit_*.py defines an async `main()`
  4. NEGATIVE: every audit_*.py prints a roll-up section
  5. NEGATIVE: every audit_*.py prints a completion banner
  6. NEGATIVE: every audit_*.py uses at least one structured list
     item shape (`BROKEN`, `✓`, or `⚠`) rather than free-form prose
  7. NEGATIVE: every audit_*.py exits via asyncio.run(main())
  8. POSITIVE: only the renamed frontend surveys currently live in
     audit_*.py namespace, so the schema lock is intentionally narrow

Run: python3 mcp/tests/drill_audit_schema.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
AUDIT_DIR = REPO / "mcp" / "tests"
AUDITS = sorted(AUDIT_DIR.glob("audit_*.py"))

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


def _docstring(text: str) -> str:
    m = re.search(r'"""(.*?)"""', text, re.DOTALL)
    if not m:
        m = re.search(r"'''(.*?)'''", text, re.DOTALL)
    return m.group(1) if m else ""


def main() -> int:
    step("1. audit_*.py files exist and have module docstrings")
    if not AUDITS:
        fail("no audit_*.py files found")
    docs = {path.name: _docstring(path.read_text()) for path in AUDITS}
    missing = [name for name, doc in docs.items() if not doc.strip()]
    if missing:
        fail(f"missing module docstring: {missing}")
    ok(f"{len(AUDITS)} audit files with module docstrings")

    step("2. NEGATIVE: docstrings declare audit semantics and exit-0 behavior")
    offenders = []
    for name, doc in docs.items():
        lowered = doc.lower()
        declares_exit_zero = (
            "exit 0" in lowered
            or "exits 0" in lowered
            or "always passes" in lowered
        )
        if "audit" not in lowered or not declares_exit_zero:
            offenders.append(name)
    if offenders:
        fail(f"audit semantics missing from docstrings: {offenders}")
    ok("all audit docstrings mention audit + exit-zero semantics")

    step("3. NEGATIVE: every audit defines async main()")
    offenders = []
    for path in AUDITS:
        text = path.read_text()
        if "async def main()" not in text:
            offenders.append(path.name)
    if offenders:
        fail(f"async main() missing: {offenders}")
    ok("async main() present in every audit")

    step("4. NEGATIVE: every audit prints a roll-up section")
    offenders = []
    for path in AUDITS:
        if 'step("roll-up")' not in path.read_text():
            offenders.append(path.name)
    if offenders:
        fail(f"roll-up section missing: {offenders}")
    ok("roll-up section present in every audit")

    step("5. NEGATIVE: every audit prints a completion banner")
    offenders = []
    for path in AUDITS:
        text = path.read_text()
        if "COMPLETE" not in text.upper():
            offenders.append(path.name)
    if offenders:
        fail(f"completion banner missing: {offenders}")
    ok("completion banner present in every audit")

    step("6. NEGATIVE: every audit uses structured finding markers")
    offenders = []
    markers = ("BROKEN", "✓", "⚠")
    for path in AUDITS:
        text = path.read_text()
        if not any(marker in text for marker in markers):
            offenders.append(path.name)
    if offenders:
        fail(f"no structured finding markers found: {offenders}")
    ok("structured finding markers present")

    step("7. NEGATIVE: every audit exits via asyncio.run(main())")
    offenders = []
    for path in AUDITS:
        text = path.read_text()
        if "asyncio.run(main())" not in text:
            offenders.append(path.name)
    if offenders:
        fail(f"asyncio.run(main()) missing: {offenders}")
    ok("asyncio.run(main()) present")

    step("8. POSITIVE: audit namespace intentionally narrow")
    actual = [path.name for path in AUDITS]
    expected = [
        "audit_frontend_link.py",
        "audit_frontend_template_coverage.py",
    ]
    if actual != expected:
        fail(f"unexpected audit namespace members: actual={actual} expected={expected}")
    ok(f"audit namespace matches expected renamed surveys: {actual}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 AUDIT-SCHEMA STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
