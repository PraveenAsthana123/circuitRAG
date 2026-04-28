#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Phase 2A3 batched replay of the Sidecar council.

Exercises the worklist query (memory.find_events_without_council_run)
and the batched-fire path (replay_council_for_events) with a stub
advisor + real AdvisorMemory.

Eight steps. Six negative assertions.

  1. find_events_without_council_run returns events lacking a
     council_run; ordered oldest-first.
  2. NEGATIVE: events WITH a council_run row are excluded.
  3. NEGATIVE: events of a different event_type (e.g. "code") are
     excluded - only pr_review goes through the council.
  4. NEGATIVE: limit caps the result count.
  5. replay_council_for_events fires council on each event;
     persists council_run rows; per-event ReplayResult populated.
  6. NEGATIVE: per-event council failure does NOT sink siblings;
     batch stats partition success/failure correctly.
  7. NEGATIVE: idempotent - after a successful replay, a re-run's
     find_events_without_council_run returns zero pending events.
  8. NEGATIVE: max_concurrent cap respected (even when N events
     could fire all at once, peak in-flight stays bounded).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import tempfile
import types

REPO = pathlib.Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def _load_mod(rel: str, name: str):
    p = REPO / rel
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Set up package context for advisor + council relative imports
_pkg = types.ModuleType("sidecar_advisor_pkg")
_pkg.__path__ = [str(REPO / "services" / "sidecar-advisor")]
sys.modules["sidecar_advisor_pkg"] = _pkg

memory_mod = _load_mod(
    "services/sidecar-advisor/memory.py",
    "sidecar_advisor_pkg.memory",
)
sys.modules["sidecar_advisor_pkg.memory"] = memory_mod
advisor_mod = _load_mod(
    "services/sidecar-advisor/advisor.py",
    "sidecar_advisor_pkg.advisor",
)
sys.modules["sidecar_advisor_pkg.advisor"] = advisor_mod
council_mod = _load_mod(
    "services/sidecar-advisor/council.py",
    "sidecar_advisor_pkg.council",
)
sys.modules["sidecar_advisor_pkg.council"] = council_mod
replay_mod = _load_mod(
    "services/sidecar-advisor/replay_council.py",
    "sidecar_advisor_pkg.replay_council",
)

AdvisorMemory = memory_mod.AdvisorMemory
Advisor = advisor_mod.Advisor


def _seed_event(mem, *, event_type="pr_review", content="x"):
    return mem.record_event(
        event_type=event_type, source="manual",
        content=content, model_used=None, advisor_output=None,
    )


def _make_stub_advisor(policy, *, fail_for_event_ids=None):
    """Build an Advisor whose generate_fn returns canned chair JSON.
    fail_for_event_ids: events whose content matches a sentinel
    string trigger a chair total-failure (degraded path). The
    advisor doesn't see event_ids directly, so we encode failure
    via content prefix."""
    async def gen(model, prompt, timeout_s):
        if "FAIL_THIS_REVIEW" in prompt and prompt.rstrip().endswith("JSON:"):
            raise RuntimeError("simulated chair failure")
        if prompt.rstrip().endswith("JSON:"):
            return ('{"summary":"ok","risk_level":"LOW",'
                    '"top_3_advice":["a","b","c"],"confidence":0.7}')
        if "SCORE: <integer 0-10>" in prompt:
            return "ok\nSCORE: 7"
        return f"draft from {model}"
    return Advisor(policy, generate_fn=gen)


async def main():
    import yaml
    policy = yaml.safe_load(
        (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
    )

    # Step 1: find returns unreviewed events oldest-first
    step("1. find_events_without_council_run returns unreviewed, oldest-first")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        # 3 unreviewed pr_review events
        e1 = _seed_event(mem, content="def first(): pass")
        e2 = _seed_event(mem, content="def second(): pass")
        e3 = _seed_event(mem, content="def third(): pass")
        pending = mem.find_events_without_council_run()
        if len(pending) != 3:
            fail(f"expected 3 pending, got {len(pending)}")
        ids = [e["id"] for e in pending]
        if ids != [e1, e2, e3]:
            fail(f"order should be oldest-first: {ids}")
        ok(f"3 pending events in oldest-first order: {ids}")

    # Step 2: events WITH council_run filtered out
    step("2. NEGATIVE: events WITH a council_run row are excluded")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        e1 = _seed_event(mem, content="reviewed")
        e2 = _seed_event(mem, content="not_reviewed")
        # Mark e1 as reviewed
        mem.record_council_run(event_id=e1, telemetry={
            "outcome": "ok", "advisor_id": "chair", "prompt_version": "v",
            "duration_s": 1.0, "drafts": [], "reviews": [],
            "failed_authors": [], "advisor_error": None,
        })
        pending = mem.find_events_without_council_run()
        if len(pending) != 1:
            fail(f"expected 1 pending, got {len(pending)}")
        if pending[0]["id"] != e2:
            fail(f"wrong event surfaced: {pending[0]['id']} (expected {e2})")
        ok(f"reviewed event excluded; only e{e2} pending")

    # Step 3: non-pr_review events excluded
    step("3. NEGATIVE: non-pr_review event_type events excluded")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        pr = _seed_event(mem, event_type="pr_review", content="diff")
        cd = _seed_event(mem, event_type="code", content="def f(): pass")
        ar = _seed_event(mem, event_type="architecture", content="ADR-001")
        pending = mem.find_events_without_council_run(event_type="pr_review")
        if len(pending) != 1:
            fail(f"expected 1 pr_review event pending, got {len(pending)}: "
                  f"{[e['id'] for e in pending]}")
        if pending[0]["id"] != pr:
            fail(f"wrong event surfaced: {pending[0]['id']}")
        ok(f"only pr_review event surfaced; code + architecture filtered")

    # Step 4: limit caps result count
    step("4. NEGATIVE: limit caps result count")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        for i in range(10):
            _seed_event(mem, content=f"def f{i}(): pass")
        pending = mem.find_events_without_council_run(limit=3)
        if len(pending) != 3:
            fail(f"limit=3 should give 3, got {len(pending)}")
        # default limit=50 returns all 10
        all_pending = mem.find_events_without_council_run()
        if len(all_pending) != 10:
            fail(f"default limit should give 10, got {len(all_pending)}")
        ok(f"limit=3 -> 3 events; default -> 10 events")

    # Step 5: replay fires council + persists council_run rows
    step("5. replay_council_for_events fires council; persists council_runs")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        e1 = _seed_event(mem, content="def aaa(): pass")
        e2 = _seed_event(mem, content="def bbb(): pass")
        e3 = _seed_event(mem, content="def ccc(): pass")
        pending = mem.find_events_without_council_run()
        advisor = _make_stub_advisor(policy)
        results, stats = await replay_mod.replay_council_for_events(
            events=pending, advisor=advisor, memory=mem,
            max_concurrent=4,
        )
        if len(results) != 3:
            fail(f"expected 3 results, got {len(results)}")
        if stats.succeeded != 3:
            fail(f"expected 3 succeeded, got {stats.succeeded}")
        if stats.failed != 0:
            fail(f"expected 0 failed, got {stats.failed}")
        # Each event should now have a council_run row
        for eid in [e1, e2, e3]:
            runs = mem.get_council_runs(event_id=eid)
            if len(runs) != 1:
                fail(f"event {eid} council_run count != 1: {len(runs)}")
        ok(f"3 reviewed; 3 council_runs persisted; risk_counts={stats.risk_counts}")

    # Step 6: per-event advisor failure isolated
    step(
        "6. NEGATIVE: per-event advisor.review raise -> failure isolated; "
        "siblings complete"
    )
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        e_ok1 = _seed_event(mem, content="def good1(): pass")
        e_bad = _seed_event(mem, content="def bad(): pass FAIL_REVIEW")
        e_ok2 = _seed_event(mem, content="def good2(): pass")
        pending = mem.find_events_without_council_run()

        # Wrapper advisor that bypasses the council's graceful
        # degradation by raising directly. Simulates an end-to-end
        # advisor failure (e.g. advisor's network layer entirely
        # down, not just one LLM call timing out within the
        # council's degradation envelope).
        base = _make_stub_advisor(policy)

        class _FailingForOneAdvisor:
            async def review(self, *, event_type, content):
                if "FAIL_REVIEW" in content:
                    raise RuntimeError("simulated end-to-end advisor failure")
                return await base.review(
                    event_type=event_type, content=content,
                )

        results, stats = await replay_mod.replay_council_for_events(
            events=pending,
            advisor=_FailingForOneAdvisor(),
            memory=mem,
        )
        if stats.succeeded != 2:
            fail(f"expected 2 succeeded, got {stats.succeeded}")
        if stats.failed != 1:
            fail(f"expected 1 failed, got {stats.failed}")
        if e_bad not in stats.failed_event_ids:
            fail(f"failed event missing from stats: {stats.failed_event_ids}")
        for eid in [e_ok1, e_ok2]:
            runs = mem.get_council_runs(event_id=eid)
            if len(runs) != 1:
                fail(f"good event {eid}: council_run missing")
        bad_runs = mem.get_council_runs(event_id=e_bad)
        if len(bad_runs) != 0:
            fail(
                f"failed event {e_bad} should have NO council_run row "
                f"(advisor raised before telemetry produced); "
                f"got {len(bad_runs)}"
            )
        bad_result = next(r for r in results if r.event_id == e_bad)
        if "simulated end-to-end" not in (bad_result.error or ""):
            fail(f"failure error lost: {bad_result.error}")
        ok(
            f"2 succeeded ({e_ok1},{e_ok2}); 1 failed ({e_bad}); "
            f"failed_result.error captured"
        )

    # Step 7: idempotent - re-run after success returns 0 pending
    step("7. NEGATIVE: idempotent; after replay, find returns 0 pending")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        for i in range(3):
            _seed_event(mem, content=f"def i{i}(): pass")
        pending_1 = mem.find_events_without_council_run()
        if len(pending_1) != 3:
            fail(f"first find: expected 3, got {len(pending_1)}")
        advisor = _make_stub_advisor(policy)
        await replay_mod.replay_council_for_events(
            events=pending_1, advisor=advisor, memory=mem,
        )
        # After successful replay, none should remain pending
        pending_2 = mem.find_events_without_council_run()
        if len(pending_2) != 0:
            fail(f"after replay, expected 0 pending, got {len(pending_2)}")
        ok(f"first run: 3 pending; after replay: 0 pending (idempotent)")

    # Step 8: max_concurrent bounded across events
    step("8. NEGATIVE: max_concurrent caps in-flight (DispatchPool composes)")
    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "advisor.db"
        mem = AdvisorMemory(db)
        mem.set_policy_version("v1")
        for i in range(8):
            _seed_event(mem, content=f"def m{i}(): pass")
        pending = mem.find_events_without_council_run()

        # Build an advisor whose generate_fn tracks in-flight count
        in_flight = [0]
        peak = [0]

        async def tracking_gen(model, prompt, timeout_s):
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
            await asyncio.sleep(0.01)
            try:
                if prompt.rstrip().endswith("JSON:"):
                    return ('{"summary":"x","risk_level":"LOW",'
                            '"top_3_advice":["a"],"confidence":0.5}')
                if "SCORE: <integer 0-10>" in prompt:
                    return "ok\nSCORE: 7"
                return f"draft from {model}"
            finally:
                in_flight[0] -= 1

        advisor = Advisor(policy, generate_fn=tracking_gen)
        results, stats = await replay_mod.replay_council_for_events(
            events=pending, advisor=advisor, memory=mem,
            max_concurrent=2,
        )
        # Each event = 7 LLM calls. With max_concurrent=2 events, at
        # most 2 events x internal-council-parallelism in flight.
        # The Sidecar council uses max_parallel=3 by default per
        # PrReviewCouncil, so ~2 * 3 = 6 LLM calls peak. Without the
        # outer cap (max_concurrent=2), 8 events would each fire up
        # to 3 internal -> 24 LLM calls peak.
        if stats.succeeded != 8:
            fail(f"expected 8 succeeded, got {stats.succeeded}")
        # Peak in-flight depends on internal council concurrency too,
        # but the cap MUST keep it well below 8*3 = 24. If max_concurrent
        # is enforced, peak should be roughly 2*3 = 6 or so.
        if peak[0] > 8:
            fail(
                f"peak in-flight LLM calls = {peak[0]}; max_concurrent=2 "
                f"events should keep it bounded (2 events * 3 internal = ~6). "
                f"Without DispatchPool composition, 8 events could fire 24."
            )
        ok(f"all 8 succeeded; peak LLM calls = {peak[0]} (capped)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 REPLAY-COUNCIL-EVENTS STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
