#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Advisor.record_rating delegates to AdvisorMemory.rate_event and
preserves the current schema contract.

This locks the sidecar write surface before the UI/API layer is added.

Four steps. Three negative assertions.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
SIDECAR = REPO / "services" / "sidecar-advisor"


def _load(name: str, rel: str):
    path = SIDECAR / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


advisor_mod = _load("sidecar_advisor_rating", "advisor.py")
memory_mod = _load("sidecar_memory_rating", "memory.py")

Advisor = advisor_mod.Advisor
AdvisorMemory = memory_mod.AdvisorMemory


def ok(msg: str) -> None:
    print(f"  \033[32m✓ {msg}\033[0m")


def fail(msg: str) -> None:
    print(f"  \033[31m✗ {msg}\033[0m")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n\033[1m── {title} ──\033[0m")


def main() -> None:
    tmp = tempfile.NamedTemporaryFile(prefix="advisor-rating-", suffix=".db", delete=False)
    tmp.close()
    mem = AdvisorMemory(tmp.name)
    advisor = Advisor({"advisor_policy": {"routes": {}}}, memory=mem)
    event_id = mem.record_event(
        event_type="prompt",
        source="manual",
        content="rate this suggestion",
        model_used="stub-model",
        advisor_output={"summary": "ok"},
        duration_s=0.01,
    )

    step("1. Advisor.record_rating returns True for an existing event")
    if not advisor.record_rating(event_id=event_id, rating="useful"):
        fail("record_rating should return True for an existing event")
    ok("record_rating updates an existing event")

    step("2. NEGATIVE: recent_events reflects stored user_rating")
    events = mem.recent_events(limit=5)
    row = next((event for event in events if event["id"] == event_id), None)
    if row is None:
        fail("rated event missing from recent_events")
    if row["user_rating"] != "useful":
        fail(f"user_rating drifted, expected 'useful', got {row['user_rating']!r}")
    if not row["rated_at"]:
        fail("rated_at not set by record_rating")
    ok("user_rating + rated_at persisted through advisor wrapper")

    step("3. NEGATIVE: invalid rating still raises ValueError")
    try:
        advisor.record_rating(event_id=event_id, rating="maybe")
    except ValueError:
        ok("invalid rating rejected with ValueError")
    else:
        fail("invalid rating should raise ValueError")

    step("4. NEGATIVE: advisor without memory raises RuntimeError")
    no_mem_advisor = Advisor({"advisor_policy": {"routes": {}}})
    try:
        no_mem_advisor.record_rating(event_id=event_id, rating="useful")
    except RuntimeError:
        ok("advisor without memory rejects record_rating")
    else:
        fail("record_rating without memory should raise RuntimeError")

    print("\n\033[1;32m════════════════════════════════════════\033[0m")
    print("\033[1;32m  ALL 4 SIDECAR-ADVISOR-RATING STEPS PASSED\033[0m")
    print("\033[1;32m════════════════════════════════════════\033[0m")


if __name__ == "__main__":
    main()
