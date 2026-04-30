#!/usr/bin/env python3
"""Capture the latest git diff + send it through the Sidecar council.

Phase 2A2: closes the auto-feed loop. Composes:

  * Phase 2A capture_diff() / is_likely_pr_review()
  * Phase 2D PrReviewCouncil (3 authors + reviewer + chair)
  * Phase 2E memory.record_event + memory.record_council_run

Runs from the post-commit hook (after Phase 4B's LoopWatcher).
Operator can also invoke manually for ad-hoc review:

    python3 scripts/capture_and_review.py
    python3 scripts/capture_and_review.py --staged   # preview pre-commit
    python3 scripts/capture_and_review.py --no-council  # just record, skip LLM

The capture_and_record() function is the testable seam - drill
calls it with stub advisor + memory; production uses real Ollama.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO / "advisor.db"
DEFAULT_COUNCIL_LOG = REPO / ".loop" / "council_runs.log"

log = logging.getLogger("capture_and_review")


@dataclass(frozen=True)
class CaptureResult:
    """Outcome of one capture-and-review pass."""

    fired: bool                  # was the council actually invoked?
    filtered: bool               # did the heuristic filter the diff out?
    reason: str                  # human-readable explanation
    event_id: int | None         # advisor_events.id, if recorded
    council_run_id: int | None   # advisor_council_runs.id, if recorded
    duration_s: float
    risk_level: str | None       # LOW|MEDIUM|HIGH from chair, if fired
    files_touched: list[str]


# ── Module loaders (avoid heavy package imports) ────────────────
def _load_git_capture():
    p = REPO / "services" / "sidecar-advisor" / "git_capture.py"
    spec = importlib.util.spec_from_file_location("_gc_for_pipeline", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gc_for_pipeline"] = mod
    spec.loader.exec_module(mod)
    return mod


def _append_log(log_path: Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


async def capture_and_record(
    *,
    repo: Path,
    advisor,                     # Advisor or None when fire_council=False
    memory,                      # AdvisorMemory or None
    council_log_path: Path,
    fire_council: bool = True,
    staged: bool = False,
) -> CaptureResult:
    """Capture the latest git diff. If meaningful, record an event
    and (optionally) fire the council. Always appends one log line.

    Never raises. On any internal failure (capture, advisor,
    memory write), surfaces the error in CaptureResult.reason and
    logs it. The post-commit hook can't block the commit anyway,
    so the function's contract is: do best-effort and log.
    """
    t_start = time.monotonic()
    gc = _load_git_capture()

    capture = gc.capture_diff(repo=repo, staged=staged)

    # ── Filter path: capture errored OR diff is noise ───────────
    if capture.error:
        result = CaptureResult(
            fired=False, filtered=True,
            reason=f"capture_error: {capture.error[:120]}",
            event_id=None, council_run_id=None,
            duration_s=time.monotonic() - t_start,
            risk_level=None, files_touched=[],
        )
        _append_log(council_log_path, {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "fired": False,
            "filtered": True,
            "reason": result.reason,
            "files": [],
            "risk_level": None,
            "duration_s": result.duration_s,
        })
        return result

    filter_reason = gc.pr_review_filter_reason(capture)
    if filter_reason is not None:
        # Heuristic says "noise" - skip both event + council.
        # We still log the skip so operators can see the filter
        # working (and eyeball misclassifications). The reason
        # names the SPECIFIC filter that tripped (Phase 5K) — old
        # format dumped all signals, which left operators guessing.
        result = CaptureResult(
            fired=False, filtered=True,
            reason=(
                f"filtered: {filter_reason} "
                f"(payload={capture.payload_lines}, "
                f"files={len(capture.files_touched)}, "
                f"binary={capture.has_binary})"
            ),
            event_id=None, council_run_id=None,
            duration_s=time.monotonic() - t_start,
            risk_level=None,
            files_touched=list(capture.files_touched),
        )
        _append_log(council_log_path, {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "fired": False,
            "filtered": True,
            "reason": result.reason,
            "files": list(capture.files_touched),
            "risk_level": None,
            "duration_s": result.duration_s,
        })
        return result

    # ── Record the event (whether or not we fire the council) ──
    event_id: int | None = None
    if memory is not None:
        try:
            event_id = memory.record_event(
                event_type="pr_review",
                source="git-diff",
                content=capture.content,
                model_used=None,           # filled in below if council fires
                advisor_output=None,
                duration_s=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("capture_record_event_failed err=%s", exc)
            event_id = None

    # ── --no-council path: record event only ────────────────────
    if not fire_council or advisor is None:
        result = CaptureResult(
            fired=False, filtered=False,
            reason="no_council requested" if not fire_council
                   else "no advisor wired",
            event_id=event_id, council_run_id=None,
            duration_s=time.monotonic() - t_start,
            risk_level=None,
            files_touched=list(capture.files_touched),
        )
        _append_log(council_log_path, {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "fired": False, "filtered": False,
            "reason": result.reason,
            "event_id": event_id,
            "files": list(capture.files_touched),
            "risk_level": None,
            "duration_s": result.duration_s,
        })
        return result

    # ── Fire the council ───────────────────────────────────────
    try:
        parsed, raw, model_used, council_duration, telemetry = \
            await advisor.review(event_type="pr_review", content=capture.content)
    except Exception as exc:  # noqa: BLE001
        log.error("capture_council_failed err=%s", exc)
        result = CaptureResult(
            fired=True, filtered=False,
            reason=f"council_error: {type(exc).__name__}: {exc}",
            event_id=event_id, council_run_id=None,
            duration_s=time.monotonic() - t_start,
            risk_level=None,
            files_touched=list(capture.files_touched),
        )
        _append_log(council_log_path, {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "fired": True, "filtered": False,
            "reason": result.reason,
            "event_id": event_id,
            "files": list(capture.files_touched),
            "risk_level": None,
            "duration_s": result.duration_s,
        })
        return result

    # ── Persist council telemetry ──────────────────────────────
    council_run_id: int | None = None
    if memory is not None and telemetry is not None:
        try:
            council_run_id = memory.record_council_run(
                event_id=event_id, telemetry=telemetry,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("capture_record_council_run_failed err=%s", exc)

    # ── Backfill the event row with advisor_output ─────────────
    # The event was recorded with advisor_output=None up-front
    # (the "always record before council" safety contract). Now
    # that the council succeeded, update with the parsed output so
    # downstream readers (dashboard, audit) see the summary.
    if (memory is not None and event_id is not None
            and parsed is not None):
        try:
            memory.update_event_advisor_output(
                event_id,
                advisor_output=parsed.to_dict(),
                model_used=model_used,
                duration_s=council_duration,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("capture_update_event_failed err=%s", exc)

    risk = parsed.risk_level if parsed else None
    result = CaptureResult(
        fired=True, filtered=False,
        reason=f"council_completed risk={risk}",
        event_id=event_id, council_run_id=council_run_id,
        duration_s=time.monotonic() - t_start,
        risk_level=risk,
        files_touched=list(capture.files_touched),
    )
    _append_log(council_log_path, {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "fired": True, "filtered": False,
        "reason": result.reason,
        "event_id": event_id,
        "council_run_id": council_run_id,
        "files": list(capture.files_touched),
        "risk_level": risk,
        "model_used": model_used,
        "duration_s": result.duration_s,
    })
    return result


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument(
        "--council-log", default=str(DEFAULT_COUNCIL_LOG),
        help="where to append per-invocation result",
    )
    parser.add_argument(
        "--no-council", action="store_true",
        help="record the diff event but skip LLM review",
    )
    parser.add_argument(
        "--staged", action="store_true",
        help="capture staged diff instead of HEAD",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Lazy build advisor + memory only when we actually need them.
    # The wire-up uses the same package-context pattern as the drills
    # so advisor.py's lazy `from .council import` resolves correctly
    # when run as a CLI subprocess (e.g. from the post-commit hook).
    advisor = None
    memory = None
    if not args.no_council:
        try:
            import types
            pkg = types.ModuleType("sidecar_advisor_pkg")
            pkg.__path__ = [str(REPO / "services" / "sidecar-advisor")]
            sys.modules["sidecar_advisor_pkg"] = pkg

            import yaml
            policy = yaml.safe_load(
                (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
            )

            # Load memory + advisor under the package namespace so
            # advisor's `from .council import PrReviewCouncil`
            # (called lazily in _get_or_build_council) resolves.
            mem_path = REPO / "services" / "sidecar-advisor" / "memory.py"
            mem_spec = importlib.util.spec_from_file_location(
                "sidecar_advisor_pkg.memory", mem_path,
            )
            mem_mod = importlib.util.module_from_spec(mem_spec)
            sys.modules["sidecar_advisor_pkg.memory"] = mem_mod
            mem_spec.loader.exec_module(mem_mod)

            adv_path = REPO / "services" / "sidecar-advisor" / "advisor.py"
            adv_spec = importlib.util.spec_from_file_location(
                "sidecar_advisor_pkg.advisor", adv_path,
            )
            adv_mod = importlib.util.module_from_spec(adv_spec)
            sys.modules["sidecar_advisor_pkg.advisor"] = adv_mod
            adv_spec.loader.exec_module(adv_mod)

            memory = mem_mod.AdvisorMemory(args.db)
            memory.set_policy_version("default")
            advisor = adv_mod.Advisor(policy)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "capture_advisor_setup_failed err=%s; falling back to "
                "--no-council mode", exc,
            )
            advisor = None
            memory = None

    result = asyncio.run(capture_and_record(
        repo=REPO,
        advisor=advisor,
        memory=memory,
        council_log_path=Path(args.council_log),
        fire_council=(not args.no_council),
        staged=args.staged,
    ))

    print(
        f"[capture_and_review] fired={result.fired} "
        f"filtered={result.filtered} risk={result.risk_level} "
        f"reason={result.reason} duration={result.duration_s:.2f}s",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
