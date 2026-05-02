"""Verifiability framework — Tier 2 #2.11.

Per CLAUDE.md §50 + §55. The §55.3 outcome contract demands
verifiable proof that an applied fix actually resolves the issue
without breaking anything else. Today the daemon's drill-gate runs
ONLY `ruff check`. That misses:

  - mypy regressions (a fix can pass ruff but break type checks)
  - pytest regressions (a fix can pass static checks but break runtime)
  - drill regressions (a fix can land cleanly but break the §43 catalog)

This module is the multi-tool gate. After AUTHOR's diff applies, the
daemon calls run_technical_verification() which runs:

  TECHNICAL layer (this commit):
    1. ruff check          — style + lint (existing)
    2. mypy check          — type errors
    3. pytest smoke        — runtime (services/agent-orchestrator-svc/tests/)

  BUSINESS layer (deferred to v2 — requires golden-set + eval harness):
    4. Regression eval against operator-curated golden test set
    5. Per-rule accept-rate scorecard against historical baseline

ALL-PASS gate: ANY failing layer rejects the apply. Operator can
override via the daemon's --skip-mypy / --skip-pytest flags (future
iteration); today: all required.

USAGE FROM daemon
==================

  from verifiability_framework import run_technical_verification
  result = run_technical_verification(REPO, files_touched=["x.py"])
  if not result.all_pass:
    rollback(diff)
    return False, result.failure_summary()

Drilled by mcp/tests/drill_verifiability_framework.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


REPO = Path(__file__).resolve().parent.parent

# Default scope — what the gate checks. Tightly scoped to the
# autonomous-fix-bot's safe-path prefixes so we don't spend 30s
# checking the entire repo on every cycle.
DEFAULT_RUFF_TARGETS: tuple[str, ...] = (
    "services/agent-orchestrator-svc/app/",
    "libs/py/",
)
DEFAULT_MYPY_TARGETS: tuple[str, ...] = (
    "services/agent-orchestrator-svc/app/",
    "libs/py/documind_core/",
)
DEFAULT_PYTEST_TARGETS: tuple[str, ...] = (
    "services/agent-orchestrator-svc/tests/",
)

VENV_PYTHON = ".venv/bin/python3"
VENV_RUFF = ".venv/bin/ruff"
VENV_MYPY = ".venv/bin/mypy"
VENV_PYTEST = ".venv/bin/pytest"

DEFAULT_TIMEOUT_S: float = 60.0


@dataclass(frozen=True)
class ToolResult:
    """One tool's verdict in the multi-layer gate."""

    tool: str
    ok: bool
    exit_code: int
    duration_s: float
    output_truncated: str  # max 2KB; full output on disk if needed
    error: str | None

    model_config: ClassVar[dict] = {"frozen": True}


@dataclass(frozen=True)
class VerificationResult:
    """Aggregate technical-layer verdict for one apply."""

    timestamp: str
    layers: tuple[ToolResult, ...]
    all_pass: bool
    total_duration_s: float

    def failure_summary(self) -> str:
        """Operator-readable summary of failing layers."""
        failed = [layer for layer in self.layers if not layer.ok]
        if not failed:
            return "(no failures)"
        lines = []
        for layer in failed:
            lines.append(f"  {layer.tool}: exit={layer.exit_code} ({layer.duration_s:.1f}s)")
            if layer.error:
                lines.append(f"    error: {layer.error[:120]}")
            preview = (layer.output_truncated or "").strip()[:300]
            if preview:
                lines.append(f"    output: {preview!r}")
        return "\n".join(lines)


def _run_tool(
    *,
    tool: str,
    cmd: list[str],
    cwd: Path,
    timeout: float,
) -> ToolResult:
    started = time.time()
    err: str | None = None
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        ok = proc.returncode == 0
        rc = proc.returncode
        out = ((proc.stdout or "") + (proc.stderr or ""))[:2000]
    except subprocess.TimeoutExpired:
        ok = False
        rc = -1
        out = ""
        err = f"timed out after {timeout}s"
    except FileNotFoundError as exc:
        ok = False
        rc = -2
        out = ""
        err = f"tool binary not found: {exc.filename}"
    return ToolResult(
        tool=tool,
        ok=ok,
        exit_code=rc,
        duration_s=round(time.time() - started, 2),
        output_truncated=out,
        error=err,
    )


def run_technical_verification(
    repo: Path | None = None,
    *,
    ruff_targets: tuple[str, ...] = DEFAULT_RUFF_TARGETS,
    mypy_targets: tuple[str, ...] = DEFAULT_MYPY_TARGETS,
    pytest_targets: tuple[str, ...] = DEFAULT_PYTEST_TARGETS,
    skip_mypy: bool = False,
    skip_pytest: bool = False,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> VerificationResult:
    """Run the multi-tool gate. Returns VerificationResult.

    Tools run sequentially (ruff first because it's fastest);
    operator-readable order in the result. Future iteration can
    parallelize via asyncio if total wall-clock matters.
    """
    repo = repo or REPO
    started = time.time()
    layers: list[ToolResult] = []

    # Layer 1: ruff
    layers.append(_run_tool(
        tool="ruff",
        cmd=[VENV_RUFF, "check", *ruff_targets],
        cwd=repo, timeout=timeout,
    ))

    # Layer 2: mypy (skippable per operator flag)
    if not skip_mypy:
        layers.append(_run_tool(
            tool="mypy",
            cmd=[VENV_MYPY, "--ignore-missing-imports", *mypy_targets],
            cwd=repo, timeout=timeout * 2,  # mypy is slower than ruff
        ))

    # Layer 3: pytest smoke (skippable per operator flag)
    if not skip_pytest:
        env_pythonpath = f"{repo}:libs/py:services/agent-orchestrator-svc"
        layers.append(_run_tool(
            tool="pytest",
            cmd=[VENV_PYTEST, "-q", "--no-header", *pytest_targets],
            cwd=repo, timeout=timeout * 2,
        ))

    all_pass = all(layer.ok for layer in layers)
    return VerificationResult(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        layers=tuple(layers),
        all_pass=all_pass,
        total_duration_s=round(time.time() - started, 2),
    )


def main() -> int:
    """CLI: run the technical-layer gate ad-hoc."""
    parser = argparse.ArgumentParser(prog="verifiability_framework.py", description=__doc__)
    parser.add_argument("--skip-mypy", action="store_true")
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of human-readable")
    args = parser.parse_args()

    result = run_technical_verification(
        skip_mypy=args.skip_mypy,
        skip_pytest=args.skip_pytest,
        timeout=args.timeout,
    )

    if args.json:
        payload = {
            "timestamp": result.timestamp,
            "all_pass": result.all_pass,
            "total_duration_s": result.total_duration_s,
            "layers": [
                {
                    "tool": layer.tool, "ok": layer.ok, "exit_code": layer.exit_code,
                    "duration_s": layer.duration_s,
                    "output": layer.output_truncated[:500],
                    "error": layer.error,
                }
                for layer in result.layers
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        verdict = "✓ ALL PASS" if result.all_pass else "✗ FAILED"
        print(f"=== Technical verification: {verdict} ({result.total_duration_s}s) ===")
        for layer in result.layers:
            mark = "✓" if layer.ok else "✗"
            print(f"  {mark} {layer.tool:<8} exit={layer.exit_code:<3} ({layer.duration_s}s)")
        if not result.all_pass:
            print(f"\nFailures:\n{result.failure_summary()}")
    return 0 if result.all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
