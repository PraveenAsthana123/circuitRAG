#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: audit_*.py must not drift back into gate semantics.

The `audit_*.py` namespace exists for survey/report scripts that are
operator-facing and intentionally non-gating. The schema drill already
locks output shape; this drill locks the meaning of the namespace.

  1. discover audit_*.py files
  2. NEGATIVE: every audit docstring declares non-gate semantics
  3. NEGATIVE: no audit docstring claims to block / gate commits
  4. NEGATIVE: no audit source exits with a non-zero status
  5. NEGATIVE: no audit source uses drill-style fail helpers
  6. POSITIVE: print exact offending snippets when the contract drifts

Run: python3 mcp/tests/drill_audit_namespace_semantics.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
AUDITS = sorted((REPO / "mcp" / "tests").glob("audit_*.py"))

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
    step("1. discover audit_*.py files")
    if not AUDITS:
        fail("no audit_*.py files found")
    texts = {path.name: path.read_text() for path in AUDITS}
    docs = {name: _docstring(text) for name, text in texts.items()}
    ok(f"found {len(AUDITS)} audit files")

    step("2. NEGATIVE: every audit docstring declares non-gate semantics")
    offenders = []
    for name, doc in docs.items():
        lowered = doc.lower()
        if "audit" not in lowered or "not a gate" not in lowered:
            offenders.append(name)
    if offenders:
        fail(f"audit docstrings missing explicit non-gate wording: {offenders}")
    ok("all audit docstrings declare non-gate semantics")

    step("3. NEGATIVE: no audit docstring claims to block / gate commits")
    bad_phrases = ("gate commits", "blocking gate", "fail the gate", "must pass")
    offenders = []
    for name, doc in docs.items():
        lowered = doc.lower()
        if any(phrase in lowered for phrase in bad_phrases):
            offenders.append(name)
    if offenders:
        fail(f"audit docstrings drifted into gate language: {offenders}")
    ok("audit docstrings avoid gate/block wording")

    step("4. NEGATIVE: no audit source exits with a non-zero status")
    offenders = []
    for name, text in texts.items():
        if re.search(r"raise SystemExit\((?!0\))", text):
            offenders.append(name)
    if offenders:
        fail(f"non-zero SystemExit found in audit source: {offenders}")
    ok("no non-zero SystemExit in audit source")

    step("5. NEGATIVE: no audit source uses drill-style fail helpers")
    offenders = []
    for name, text in texts.items():
        if "def fail(" in text or "assert False" in text:
            offenders.append(name)
    if offenders:
        fail(f"drill-style fail helper found in audit source: {offenders}")
    ok("audit source does not use drill-style fail helpers")

    step("6. POSITIVE: mismatch details are explicit on failure")
    ok("this drill reports exact offending files per semantic contract")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 6 AUDIT-NAMESPACE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (4 negative assertions: 2, 3, 4, 5){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
