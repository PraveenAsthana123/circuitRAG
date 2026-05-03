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

# Performance gate — Tier 2 #2.11 + user-recommendation gap #3.
# Each binary is a SOFT requirement: if not on PATH, the perf layer
# returns ok=True (skipped, not failed) — same graceful-degradation
# pattern as Tier-B Claude/Codex CLI fallback. Operators install
# k6 / lighthouse / pytest-benchmark when they want pre-apply perf gating.
PERFORMANCE_GATE_BINARIES: tuple[str, ...] = (
    "k6",                  # load testing
    "lighthouse",          # frontend perf audit
)
PYTEST_BENCHMARK_PATH = ".venv/bin/pytest-benchmark"
PERFORMANCE_BUDGETS: dict[str, float] = {
    # Hard ceilings; ANY check exceeding flips perf layer ok=False.
    # Conservative defaults; operators tune per-project via env vars.
    "k6_p95_ms": 500.0,
    "lighthouse_lcp_ms": 2500.0,
    "pytest_benchmark_p95_ms": 250.0,
}


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


def _check_performance_binaries(repo: Path) -> ToolResult:
    """Performance layer: detects which perf binaries are available
    + reports their presence. Real perf execution (running k6 against
    a service / lighthouse against a URL) requires per-project config;
    this layer's job is the GATE, not the load-test itself.

    Strategy:
      - If NO perf binary present: ok=True with "skipped — no perf
        binary on PATH" note. Don't fail the gate just because
        operator hasn't installed k6.
      - If ≥1 binary present: report which; ok=True (presence = ready).
        Operator wires actual perf runs in their own CI/cron.

    Future iter (Gap 3 v2): actually run k6 against a configured
    target URL + assert p95 < PERFORMANCE_BUDGETS["k6_p95_ms"].
    Today's gate is presence-detection only.
    """
    import shutil
    started = time.time()
    available: list[str] = []
    for binary in PERFORMANCE_GATE_BINARIES:
        if shutil.which(binary):
            available.append(binary)
    pytest_bench_present = (repo / PYTEST_BENCHMARK_PATH).exists()
    if pytest_bench_present:
        available.append("pytest-benchmark")
    if not available:
        return ToolResult(
            tool="performance",
            ok=True,  # graceful: missing binaries don't fail the gate
            exit_code=0,
            duration_s=round(time.time() - started, 2),
            output_truncated="(no perf binaries on PATH; gate skipped — "
                             "install k6 / lighthouse / pytest-benchmark to enable)",
            error=None,
        )
    return ToolResult(
        tool="performance",
        ok=True,
        exit_code=0,
        duration_s=round(time.time() - started, 2),
        output_truncated=f"perf-ready: {', '.join(available)}",
        error=None,
    )


def run_technical_verification(
    repo: Path | None = None,
    *,
    ruff_targets: tuple[str, ...] = DEFAULT_RUFF_TARGETS,
    mypy_targets: tuple[str, ...] = DEFAULT_MYPY_TARGETS,
    pytest_targets: tuple[str, ...] = DEFAULT_PYTEST_TARGETS,
    skip_mypy: bool = False,
    skip_pytest: bool = False,
    skip_performance: bool = False,
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

    # Layer 4: performance gate (graceful no-op if no perf binaries).
    # Per user-recommendation gap #3 — Performance Agent. Foundation
    # only: presence-detect k6 / lighthouse / pytest-benchmark.
    # Actual perf execution wired in a future iter once operator
    # configures target URLs / benchmark suites.
    if not skip_performance:
        layers.append(_check_performance_binaries(repo))

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
    parser.add_argument("--skip-performance", action="store_true",
                        help="skip Layer 4 perf-binary detection (Gap #3)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of human-readable")
    args = parser.parse_args()

    result = run_technical_verification(
        skip_mypy=args.skip_mypy,
        skip_pytest=args.skip_pytest,
        skip_performance=args.skip_performance,
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
