#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: runtime sidecar rating route.

Runs the frontend Vitest suite for the `/api/v1/sidecar/events/[eventId]/rating`
route so the sidecar write surface is covered end-to-end without booting a
full Next.js server.

Negative assertions cover: rating route accepts valid POST payload,
rejects missing/malformed fields with the expected status codes,
and persists through the advisor.record_rating path. Without these,
the rating button is a UI placebo — clicks succeed but state never
mutates. The drill also asserts on subprocess returncode != 0 to
fail loudly when Vitest reports test failures.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = REPO / "services" / "frontend"
TEST_FILE = "tests/sidecar-rating-route.test.ts"


def main() -> None:
    # NEGATIVE: Vitest run must exit 0; non-zero return surfaces here
    # via raise SystemExit(proc.returncode), failing the drill loudly.
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
    print("ALL 1 SIDECAR-RATING-ROUTE STEPS PASSED")


if __name__ == "__main__":
    main()
