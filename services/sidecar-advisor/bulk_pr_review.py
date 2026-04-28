"""Bulk PR review - run the Sidecar council across N files in one shot.

Composes:
  * DispatchPool (libs/py/documind_core/dispatch_pool.py) - bounded
    concurrency across files
  * PrReviewCouncil (services/sidecar-advisor/council.py) - 3 authors
    + 1 reviewer + 1 chair per file

Why a separate module instead of just calling council.review() in a
loop:

  * Each council.review() makes 7 LLM calls (3 authors + 3 reviews +
    1 chair). Across N files that's 7N calls. Without a pool-level
    cap, a 50-file PR would fire 350 LLM calls in flight against
    Ollama or any rate-limited provider. The pool's max_parallel
    caps the union.
  * Per-file error isolation: a single file's council crashing
    must not sink the bulk review. The pool's worker_fn try/except
    wraps the council, returning a placeholder result for the
    failed file.
  * Aggregate stats: operators want "X of N files approved, Y need
    review" without re-walking the per-file results. BulkPrReview
    computes this from advisor_output.risk_level.

Phase 3C lands the foundation. Phase 4+ wires this into a CI/CD
pre-merge hook that runs against every PR.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .advisor import AdvisorOutput

log = logging.getLogger(__name__)


# Locate DispatchPool from libs/py/documind_core (same fallback
# pattern as council.py uses for AgentBoard).
def _load_dispatch_pool():
    repo = Path(__file__).resolve().parents[2]
    p = repo / "libs" / "py" / "documind_core" / "dispatch_pool.py"
    spec = importlib.util.spec_from_file_location(
        "documind_core_dispatch_pool", p,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["documind_core_dispatch_pool"] = mod
    spec.loader.exec_module(mod)
    return mod


_dp = _load_dispatch_pool()
DispatchPool = _dp.DispatchPool


@dataclass(frozen=True)
class BulkFileResult:
    """One file's outcome from a bulk review."""

    path: str
    advisor_output: AdvisorOutput | None
    telemetry: dict | None        # raw_board from council; None on error
    error: str | None             # the council itself raised
    duration_s: float

    @property
    def risk_level(self) -> str:
        """Convenience: LOW|MEDIUM|HIGH for non-errored files,
        UNKNOWN for errored files. The aggregate stats key off this."""
        if self.advisor_output is None:
            return "UNKNOWN"
        return self.advisor_output.risk_level


@dataclass
class BulkStats:
    """Aggregate stats across the bulk review."""

    total_files: int
    risk_counts: dict[str, int]   # {LOW, MEDIUM, HIGH, UNKNOWN -> N}
    failed_files: int             # files where the council itself raised
    duration_s: float
    avg_per_file_s: float = 0.0
    max_per_file_s: float = 0.0
    failed_paths: list[str] = field(default_factory=list)

    @property
    def approved(self) -> int:
        return self.risk_counts.get("LOW", 0)

    @property
    def needs_review(self) -> int:
        return (
            self.risk_counts.get("MEDIUM", 0)
            + self.risk_counts.get("HIGH", 0)
        )

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.total_files - self.failed_files) / self.total_files


class BulkPrReview:
    """Run the PR-review council across many files in one bulk pass.

    Args:
        council: a configured PrReviewCouncil instance. The bulk
            reviewer reuses ONE council across all files - the
            council itself is stateless from this caller's
            perspective (each .review() builds a fresh AgentBoard).
        max_concurrent_files: cap on how many files' councils run
            simultaneously. Default 4 - with 7 LLM calls per council,
            4 in flight = 28 LLM calls in flight, which is the
            sweet spot for local Ollama (the daemon serializes
            past 1-2 anyway, so going above 4 wastes coordination).
    """

    def __init__(
        self,
        *,
        council,
        max_concurrent_files: int = 4,
    ) -> None:
        self._council = council
        self._max_concurrent_files = max_concurrent_files

    async def review_files(
        self,
        files: list[tuple[str, str]],
    ) -> tuple[list[BulkFileResult], BulkStats]:
        """Review N files via the council, bounded by
        max_concurrent_files.

        Args:
            files: list of (path, content) tuples. Submission order
                is preserved in the returned list - results[0] is
                files[0], regardless of which file's council
                completed first.

        Returns:
            (results, stats). Both surface to the caller for the
            audit row + the dashboard's "X approved, Y need review"
            summary.
        """
        t_start = time.monotonic()

        async def _worker(file_input: tuple[str, str]) -> BulkFileResult:
            path, content = file_input
            t0 = time.monotonic()
            try:
                advisor_output, telemetry = await self._council.review(content)
                return BulkFileResult(
                    path=path,
                    advisor_output=advisor_output,
                    telemetry=telemetry,
                    error=None,
                    duration_s=time.monotonic() - t0,
                )
            except Exception as exc:  # noqa: BLE001
                # The council itself raised (rare - council usually
                # degrades gracefully). Surface as an errored
                # BulkFileResult so the bulk run still completes for
                # the other files.
                log.error(
                    "bulk_pr_review_council_raised path=%s err=%s",
                    path, exc,
                )
                return BulkFileResult(
                    path=path,
                    advisor_output=None,
                    telemetry=None,
                    error=f"{type(exc).__name__}: {exc}",
                    duration_s=time.monotonic() - t0,
                )

        pool = DispatchPool(
            worker_fn=_worker,
            max_parallel=self._max_concurrent_files,
        )
        task_results, pool_stats = await pool.dispatch_all(files)

        # Unwrap TaskResult -> BulkFileResult. The pool's per-task
        # error capture wraps OUR worker; if our worker itself
        # raised (shouldn't, since we catch internally), the pool
        # surfaces error on TaskResult.error.
        bulk_results: list[BulkFileResult] = []
        for tr in task_results:
            if tr.result is not None:
                bulk_results.append(tr.result)
            else:
                # Worker itself crashed - shouldn't happen given the
                # try/except above, but be defensive.
                path = tr.task[0] if tr.task else "<unknown>"
                bulk_results.append(BulkFileResult(
                    path=path,
                    advisor_output=None,
                    telemetry=None,
                    error=tr.error or "unknown_worker_failure",
                    duration_s=tr.duration_s,
                ))

        # Aggregate stats
        risk_counter: Counter[str] = Counter()
        durations: list[float] = []
        failed_paths: list[str] = []
        for r in bulk_results:
            risk_counter[r.risk_level] += 1
            durations.append(r.duration_s)
            if r.error is not None:
                failed_paths.append(r.path)

        duration = time.monotonic() - t_start
        stats = BulkStats(
            total_files=len(bulk_results),
            risk_counts=dict(risk_counter),
            failed_files=len(failed_paths),
            duration_s=duration,
            avg_per_file_s=(
                sum(durations) / len(durations) if durations else 0.0
            ),
            max_per_file_s=max(durations) if durations else 0.0,
            failed_paths=failed_paths,
        )

        log.info(
            "bulk_pr_review_done files=%d approved=%d needs_review=%d "
            "failed=%d duration_s=%.2f",
            stats.total_files, stats.approved, stats.needs_review,
            stats.failed_files, stats.duration_s,
        )
        return bulk_results, stats
