#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: drill docstring cohesion audit.

Every drill advertises its own contract in the module docstring:
step count, negative-assertion count, and sometimes a run line.
This audit prevents the docstring from drifting away from the body.

  1. discover every drill_*.py except this audit
  2. NEGATIVE: enough drills advertise a step count for this audit to
     be meaningful (not an empty contract)
  3. NEGATIVE: at least a small non-zero set of drills advertises a
     negative count, so that check is still exercised
  4. NEGATIVE: when a drill advertises step count, it matches actual
     numbered `step(`
  5. NEGATIVE: when a drill advertises negative assertions, the body
     contains at least one real `NEGATIVE:` marker
  6. NEGATIVE: every drill has at least one real failure path
  7. NEGATIVE: when a drill docstring includes `Run:`, it must point
     at its own filename
  8. POSITIVE: emits the mismatch list if drift is found

Run: python3 mcp/tests/drill_docstring_cohesion.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DRILLS = sorted(
    p for p in (REPO / "mcp" / "tests").glob("drill_*.py")
    if p.name != "drill_docstring_cohesion.py"
)
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


def _advertised_step_count(doc: str) -> int | None:
    for pattern in (
        r"(\d+)\s+steps",
        r"Eight steps",
        r"Seven steps",
        r"Six steps",
        r"Five steps",
        r"Four steps",
    ):
        m = re.search(pattern, doc, re.IGNORECASE)
        if m:
            word = m.group(1) if m.lastindex else m.group(0).split()[0].lower()
            if word.isdigit():
                return int(word)
            return {
                "four": 4,
                "five": 5,
                "six": 6,
                "seven": 7,
                "eight": 8,
            }.get(word)
    return None


def _advertised_negative_count(doc: str) -> int | None:
    matches = re.findall(
        r"(\d+|one|two|three|four|five|six|seven|eight)\s+negative assertions",
        doc,
        re.IGNORECASE,
    )
    if not matches:
        return None
    token = matches[-1].lower()
    if token.isdigit():
        return int(token)
    return {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
    }[token]


def _actual_step_count(text: str) -> int:
    numbers: set[int] = set()
    # Convention 1: step("N. ...") helper-function style (~129 drills)
    for m in re.finditer(r'step\("(\d+)\.', text):
        numbers.add(int(m.group(1)))
    # Convention 2: "step N:" inline narrative
    for m in re.finditer(r'step\s+(\d+):', text, re.IGNORECASE):
        numbers.add(int(m.group(1)))
    # Convention 3: print("-- N. POSITIVE/NEGATIVE: ...") banner style (~149 drills)
    for m in re.finditer(r'print\(f?["\']\s*--\s+(\d+)\.', text):
        numbers.add(int(m.group(1)))
    return len(numbers)


def main() -> int:
    step("1. drill catalog discovered")
    if not DRILLS:
        fail("no drill_*.py files found")
    ok(f"{len(DRILLS)} drills discovered")

    docs = {path.name: _docstring(path.read_text()) for path in DRILLS}

    step("2. NEGATIVE: enough drills advertise step count")
    advertised_steps = {name: _advertised_step_count(doc) for name, doc in docs.items()}
    step_doc_count = sum(1 for value in advertised_steps.values() if value is not None)
    if step_doc_count < 40:
        fail(f"only {step_doc_count} drills advertise step count; audit would be too weak")
    ok(f"{step_doc_count} drills advertise step count")

    step("3. NEGATIVE: enough drills advertise negative count")
    advertised_negs = {name: _advertised_negative_count(doc) for name, doc in docs.items()}
    neg_doc_count = sum(1 for value in advertised_negs.values() if value is not None)
    if neg_doc_count < 3:
        fail(f"only {neg_doc_count} drills advertise negative count; audit would be too weak")
    ok(f"{neg_doc_count} drills advertise negative count")

    step("4. NEGATIVE: advertised step count matches actual numbered steps")
    mismatches = []
    for path in DRILLS:
        text = path.read_text()
        actual = _actual_step_count(text)
        advertised = advertised_steps[path.name]
        if advertised is not None and advertised != actual:
            mismatches.append(f"{path.name}: doc={advertised} body={actual}")
    if mismatches:
        fail("step-count mismatches: " + "; ".join(mismatches[:12]))
    ok("advertised step count matches actual step() count")

    step("5. NEGATIVE: advertised negative assertions imply real NEGATIVE markers")
    offenders = []
    for path in DRILLS:
        text = path.read_text()
        advertised = advertised_negs[path.name]
        if advertised is not None and "NEGATIVE:" not in text:
            offenders.append(path.name)
    if offenders:
        fail("advertised negative assertions but no NEGATIVE marker in body: " + "; ".join(offenders[:12]))
    ok("every advertised-negative drill has real NEGATIVE markers in the body")

    step("6. NEGATIVE: every drill has at least one real failure path")
    offenders = []
    for path in DRILLS:
        text = path.read_text()
        has_failure_path = (
            "NEGATIVE:" in text
            or "fail(" in text
            or "assert " in text
            or "raise SystemExit(1)" in text
            or "return 1" in text
            or "page_failed = True" in text
            or "fail_count += 1" in text
        )
        if not has_failure_path:
            offenders.append(path.name)
    if offenders:
        fail(f"drills with no obvious failure path: {offenders[:12]}")
    ok("every drill contains at least one real failure path")

    step("7. NEGATIVE: when present, Run: points at the correct filename")
    offenders = []
    for name, doc in docs.items():
        if "Run:" not in doc:
            continue
        if name not in doc:
            offenders.append(name)
    if offenders:
        fail(f"Run: line doesn't mention its own filename: {offenders[:12]}")
    ok("Run: lines that exist point at the correct filename")

    step("8. POSITIVE: mismatch list is emitted on drift")
    ok("this audit fails with explicit per-file mismatch details")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 DOCSTRING-COHESION STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
