#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: runtime-status route behavior.

Runs the frontend Vitest suite for `/app-meta/runtime-status` so the
monitoring page depends on a real, tested JSON contract rather than a
best-effort local shell shim.

Negative assertions cover:
- degraded docker compose path must not crash the route
- degraded systemctl / ollama path must still emit warnings
- docker stats failure must not erase service visibility

NEGATIVE: if the Vitest subprocess exits non-zero, this drill must fail
loudly and surface the captured stdout/stderr instead of pretending the
route contract is healthy.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = REPO / "services" / "frontend"
TEST_FILE = "tests/runtime-status-route.test.ts"


def main() -> None:
    # NEGATIVE: Vitest run must exit 0; any non-zero subprocess result
    # surfaces here as a hard drill failure.
    cmd = [
        "npm",
        "exec",
        "--",
        "vitest",
        "run",
        TEST_FILE,
    ]
    proc = subprocess.run(
        cmd,
        cwd=FRONTEND,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    sys.stdout.write(proc.stdout)
    print("ALL 1 RUNTIME-STATUS-ROUTE STEPS PASSED")


if __name__ == "__main__":
    main()
