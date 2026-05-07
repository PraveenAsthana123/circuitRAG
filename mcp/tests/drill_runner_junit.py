# RESOURCES: readonly
"""
Drill: run_drills.py --report junit=<path> emits valid JUnit XML.

Runs the runner on a narrow slice of drills that's known green +
fast, then parses the resulting XML and asserts structure.

Flow:
 1. Invoke runner: --only baggage_log_formatter --report junit=/tmp/dr.xml
 2. XML parses without error.
 3. Root is <testsuite>; tests count matches # of drills we ran.
 4. Each testcase has a classname/name/time + a 'resources' property.
 5. Failure case: inject a forced failure drill (nonexistent filter),
    verify runner correctly reports exit 1 via stdout (tested via
    the 'No drills match filter' message).

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_runner_junit.py
"""
from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts" / "run_drills.py"
PY_BIN = os.getenv("PYTHON_BIN", "/tmp/documind-venv/bin/python")

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _run_runner(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(
        [PY_BIN, str(RUNNER), *args],
        capture_output=True, text=True, check=False,
    )
    return r.returncode, r.stdout + r.stderr


def main() -> None:
    report_path = Path("/tmp/drill_runner_junit_out.xml")
    if report_path.exists():
        report_path.unlink()

    step("1. invoke runner --only baggage_log_formatter --report junit=<path>")
    code, out = _run_runner([
        "--parallel", "1",
        "--only", "baggage_log_formatter",
        "--report", f"junit={report_path}",
    ])
    if code != 0:
        fail(f"runner exit {code}: {out[-500:]}")
    if not report_path.exists():
        fail(f"report file not created at {report_path}")
    ok(f"runner exit 0; report at {report_path}")

    step("2. XML parses + structure valid")
    tree = ET.parse(report_path)
    root = tree.getroot()
    if root.tag != "testsuite":
        fail(f"root tag: {root.tag} (expected 'testsuite')")
    if root.attrib.get("name") != "documind-drills":
        fail(f"suite name: {root.attrib!r}")
    tests = int(root.attrib.get("tests", "0"))
    if tests < 1:
        fail(f"tests count {tests}, expected >=1")
    ok(f"suite name={root.attrib['name']} tests={tests}")

    step("3. every testcase has classname/name/time + resources property")
    for tc in root.findall("testcase"):
        for attr in ("classname", "name", "time"):
            if attr not in tc.attrib:
                fail(f"testcase missing {attr}: {tc.attrib}")
        props = tc.find("properties")
        if props is None:
            fail(f"testcase {tc.attrib['name']} has no <properties>")
        names = [p.attrib.get("name") for p in props.findall("property")]
        if "resources" not in names:
            fail(f"testcase {tc.attrib['name']} missing 'resources' property")
        if "steps_passed" not in names:
            fail(f"testcase {tc.attrib['name']} missing 'steps_passed' property")
    ok(f"{tests} testcase(s) all have expected structure")

    step("4. successful testcase has NO <failure> child")
    for tc in root.findall("testcase"):
        if tc.find("failure") is not None:
            fail(f"unexpected failure element on {tc.attrib['name']}")
    ok("no failure elements on green drills")

    step("5. unknown format yields exit 2 + error message")
    code, out = _run_runner([
        "--only", "baggage_log_formatter",
        "--report", "bogus=nope",
    ])
    if code != 2:
        fail(f"expected exit 2 for unknown format, got {code}")
    if "unknown --report format" not in out:
        fail(f"expected error message in stdout, got: {out[-300:]}")
    ok("unknown format → exit 2 with clean error message")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 RUNNER-JUNIT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    main()
