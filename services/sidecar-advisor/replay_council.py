"""Batched replay of the Sidecar council against persisted events.

Phase 2A3: closes the --no-council escape hatch from Phase 2A2.
Events that landed in advisor_events without a corresponding
advisor_council_runs row need the council fired against them
eventually - either:

  * Phase 2A2 --no-council fast-bootstrap commits (Ollama wasn't
    up yet)
  * Phase 2A2 chair-error fallback (LLM provider had a transient
    failure)
  * Bulk imports of historical commits

This module composes:

  AdvisorMemory.find_events_without_council_run (Phase 1A)
    -> events to review (oldest-first, capped by limit)
  DispatchPool (Phase 3B)
    -> bounded concurrency across N events
  PrReviewCouncil OR Advisor (Phase 2D)
    -> the actual LLM work, 7 calls per event
  AdvisorMemory.record_council_run (Phase 2E)
    -> persistence per-event

Per-event error isolation: a single event's council raising does
NOT sink the batch. The result list reports per-event success/
failure for operator triage.

Phase 2A3+ adds: cron-scheduled batched replay (cron 0 5 * * *
fires `python3 scripts/replay_council_against_events.py --apply
--limit 200`) so the backlog drains overnight.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


# DispatchPool lives in libs/py/documind_core - load via importlib
# (same pattern as council.py).
def _load_dispatch_pool():
    repo = Path(__file__).resolve().parents[2]
    p = repo / "libs" / "py" / "documind_core" / "dispatch_pool.py"
    spec = importlib.util.spec_from_file_location(
        "_dp_for_replay", p,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_dp_for_replay"] = mod
    spec.loader.exec_module(mod)
    return mod


_dp = _load_dispatch_pool()
DispatchPool = _dp.DispatchPool


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of replaying one event through the council."""

    event_id: int
    success: bool                  # council ran AND record_council_run succeeded
    council_run_id: int | None     # populated on success
    risk_level: str | None
    error: str | None
    duration_s: float


@dataclass
class ReplayBatchStats:
    """Aggregate stats from one batch."""

    submitted: int
    succeeded: int
    failed: int
    duration_s: float
    risk_counts: dict[str, int] = field(default_factory=dict)
    failed_event_ids: list[int] = field(default_factory=list)


async def replay_council_for_events(
    *,
    events: list[dict],
    advisor,                       # Advisor with pr_review route wired
    memory,                        # AdvisorMemory
    max_concurrent: int = 4,
    per_event_timeout_s: float = 180.0,
) -> tuple[list[ReplayResult], ReplayBatchStats]:
    """Fire the council against each event, persist outcomes.

    Args:
        events: rows from advisor_events (typically the result of
            find_events_without_council_run).
        advisor: Advisor instance. Must support
            await advisor.review(event_type="pr_review", content=...)
        memory: AdvisorMemory instance for record_council_run writes.
        max_concurrent: cap on simultaneous in-flight reviews
            (passed to DispatchPool). Default 4.
        per_event_timeout_s: per-event deadline. Default 180s -
            7 LLM calls × ~25s each = 175s upper bound.

    Returns: (per_event_results, batch_stats).
    """
    t_start = time.monotonic()

    async def _replay_one(event: dict) -> ReplayResult:
        event_id = event["id"]
        t0 = time.monotonic()
        try:
            parsed, raw, model_used, dur, telemetry = await advisor.review(
                event_type="pr_review",
                content=event["content"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "replay_council_failed event_id=%d err=%s",
                event_id, exc,
            )
            return ReplayResult(
                event_id=event_id, success=False,
                council_run_id=None, risk_level=None,
                error=f"council_error: {type(exc).__name__}: {exc}",
                duration_s=time.monotonic() - t0,
            )

        if telemetry is None:
            return ReplayResult(
                event_id=event_id, success=False,
                council_run_id=None, risk_level=None,
                error="no telemetry returned from advisor.review",
                duration_s=time.monotonic() - t0,
            )

        # Persist
        try:
            council_run_id = memory.record_council_run(
                event_id=event_id, telemetry=telemetry,
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                "replay_record_council_run_failed event_id=%d err=%s",
                event_id, exc,
            )
            return ReplayResult(
                event_id=event_id, success=False,
                council_run_id=None,
                risk_level=parsed.risk_level if parsed else None,
                error=f"record_failed: {type(exc).__name__}: {exc}",
                duration_s=time.monotonic() - t0,
            )

        return ReplayResult(
            event_id=event_id, success=True,
            council_run_id=council_run_id,
            risk_level=parsed.risk_level if parsed else None,
            error=None,
            duration_s=time.monotonic() - t0,
        )

    pool = DispatchPool(
        worker_fn=_replay_one,
        max_parallel=max_concurrent,
        per_task_timeout_s=per_event_timeout_s,
    )
    task_results, _ = await pool.dispatch_all(events)

    # Unwrap TaskResult -> ReplayResult. Defensive: if our worker
    # itself raised (shouldn't, since we catch internally), the
    # pool has TaskResult.error set.
    results: list[ReplayResult] = []
    for tr in task_results:
        if tr.result is not None:
            results.append(tr.result)
        else:
            results.append(ReplayResult(
                event_id=tr.task["id"] if tr.task else 0,
                success=False, council_run_id=None,
                risk_level=None,
                error=tr.error or "worker_raised",
                duration_s=tr.duration_s,
            ))

    # Aggregate stats
    risk_counts: dict[str, int] = {}
    failed_ids: list[int] = []
    for r in results:
        if r.risk_level:
            risk_counts[r.risk_level] = risk_counts.get(r.risk_level, 0) + 1
        if not r.success:
            failed_ids.append(r.event_id)

    stats = ReplayBatchStats(
        submitted=len(events),
        succeeded=len(events) - len(failed_ids),
        failed=len(failed_ids),
        duration_s=time.monotonic() - t_start,
        risk_counts=risk_counts,
        failed_event_ids=failed_ids,
    )
    return results, stats
