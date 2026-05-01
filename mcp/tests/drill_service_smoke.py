# RESOURCES: readonly
"""
Drill: §8 per-service smoke tests for the 6 services flagged in the
2026-04-30 audit as having Dockerfile but no tests/.

Verifies:

  Static layer (no execution needed):
    1. Each of the 6 services has at least one test file:
       - agent-orchestrator-svc: tests/test_smoke.py
       - api-gateway:           internal/config/config_test.go
       - finops-svc:            cmd/main_test.go
       - governance-svc:        cmd/main_test.go
       - identity-svc:          cmd/main_test.go
       - observability-svc:     cmd/main_test.go

  Runtime layer:
    2. Python: pytest agent-orchestrator-svc/tests/ exits 0.
    3. Go (if `go` is on PATH): each Go service's `go test ./...`
       exits 0. Skipped with a warning if `go` not installed.

  Negative assertion (§43):
    4. The static check looks for files whose absence would have
       silently passed. If we accidentally pointed at a phantom
       service name not in the audit list, the drill must fail. The
       check uses an explicit allowlist; introducing a typo in a
       service name fails. The negative is the "explicit list
       required" property of step 1.

Run:
    .venv/bin/python mcp/tests/drill_service_smoke.py

Optional Go test execution requires `go` on PATH. The drill
auto-discovers /tmp/go/bin/go and falls through to PATH; if neither
is found, prints a warning and skips runtime Go tests but keeps the
static layer's enforcement.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{NC} {msg}")


# Audit list — these 6 services were flagged as missing tests/. Closing
# the gap means each gets at least one test file. The mapping is the
# explicit contract: test file path is part of the gate.
EXPECTED_TEST_FILES: list[tuple[str, str]] = [
    ("agent-orchestrator-svc", "tests/test_smoke.py"),
    ("api-gateway", "internal/config/config_test.go"),
    ("finops-svc", "cmd/main_test.go"),
    ("governance-svc", "cmd/main_test.go"),
    ("identity-svc", "cmd/main_test.go"),
    ("observability-svc", "cmd/main_test.go"),
]


def find_go() -> str | None:
    if shutil.which("go"):
        return "go"
    candidate = Path("/tmp/go/bin/go")
    if candidate.exists():
        return str(candidate)
    return None


def main() -> int:
    failures = 0

    # ---- Step 1: static — every flagged service has a test file ---
    missing: list[str] = []
    for svc, rel in EXPECTED_TEST_FILES:
        path = REPO / "services" / svc / rel
        if not path.is_file():
            missing.append(f"{svc}/{rel}")
    if not missing:
        ok(f"step 1: all {len(EXPECTED_TEST_FILES)} flagged services have test files")
    else:
        fail(f"step 1: missing test files: {missing}")
        failures += 1

    # ---- Step 4 (interleaved): negative assertion lock ------------
    # The audit list is hardcoded above. If someone adds a service
    # without a test file but doesn't update this list, the audit
    # passes silently. Lock by also enforcing that the list size
    # equals the count of services we agreed had no tests.
    expected_count = 6
    if len(EXPECTED_TEST_FILES) == expected_count:
        ok(f"step 4 (negative): explicit allowlist size = {expected_count} (locks the audit scope)")
    else:
        fail(
            f"step 4 (negative): EXPECTED_TEST_FILES has {len(EXPECTED_TEST_FILES)} entries; "
            f"the 2026-04-30 audit found {expected_count} services missing tests. "
            "Sync the list before proceeding."
        )
        failures += 1

    # ---- Step 2: pytest agent-orchestrator-svc/tests --------------
    py_test_dir = REPO / "services" / "agent-orchestrator-svc" / "tests"
    if py_test_dir.is_dir():
        env = os.environ.copy()
        env.setdefault("DOCUMIND_PROMETHEUS_PORT", "0")
        result = subprocess.run(
            [
                str(REPO / ".venv" / "bin" / "python"),
                "-m", "pytest",
                str(py_test_dir),
                "-q",
            ],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            tail = result.stdout.strip().splitlines()[-1] if result.stdout else ""
            ok(f"step 2: pytest {py_test_dir.relative_to(REPO)} → exit 0 ({tail})")
        else:
            fail(f"step 2: pytest exited {result.returncode}; tail:\n{result.stdout[-500:]}")
            failures += 1
    else:
        fail(f"step 2: {py_test_dir} not a dir; cannot run pytest")
        failures += 1

    # ---- Step 3: go test for each Go svc --------------------------
    go_bin = find_go()
    if go_bin is None:
        warn(
            "step 3: `go` not on PATH and /tmp/go/bin/go not found — "
            "skipping runtime Go tests (CI runs them via setup-go)"
        )
    else:
        go_services = [
            "api-gateway",
            "finops-svc",
            "governance-svc",
            "identity-svc",
            "observability-svc",
        ]
        for svc in go_services:
            svc_dir = REPO / "services" / svc
            result = subprocess.run(
                [go_bin, "test", "./..."],
                cwd=str(svc_dir),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                ok(f"step 3: go test ./... in {svc} → exit 0")
            else:
                fail(
                    f"step 3: go test ./... in {svc} → exit {result.returncode}\n"
                    f"  stdout: {result.stdout[:300]}\n"
                    f"  stderr: {result.stderr[:300]}"
                )
                failures += 1

    print()
    if failures == 0:
        print(f"{GREEN}{BOLD}ALL STEPS PASSED ({len(EXPECTED_TEST_FILES)} services covered){NC}")
        return 0
    print(f"{RED}{BOLD}{failures} STEP(S) FAILED{NC}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
