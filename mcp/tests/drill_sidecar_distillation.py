#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Sidecar Advisor — rated-event → memory pattern distillation.

Locks the Phase 2C contract:

  rated events (advisor_events.user_rating IN useful|not_useful)
    → distill() heuristic
    → DistilledPattern proposals (preference | mistake)
    → memory.add_pattern OR append_pattern_sources (idempotent)
    → next advisor.review() injects patterns as prompt preamble
    → cited patterns get use_count + last_used_at bumped

Eight steps. Five negative assertions.

  1. Distillation: 5 useful ratings of "add tests" produce a single
     preference pattern with confidence > 0.7.
  2. Distillation: 3 not_useful ratings of "rename foo to bar"
     produce a mistake pattern.
  3. NEGATIVE: 2 useful ratings (below MIN_FREQUENCY=3) DO NOT
     produce a pattern. The threshold prevents spurious patterns
     from a single accidental thumbs-up.
  4. NEGATIVE: mixed-polarity advice (3 useful + 3 not_useful)
     produces NO pattern (the user is inconsistent on this; better
     to leave it alone than promote conflicting signal).
  5. NEGATIVE: idempotency — running distill() twice on the same
     events does NOT duplicate patterns. The second run's
     proposals filter out events the existing pattern already cites.
  6. format_for_prompt renders preferences + mistakes correctly,
     bounded to top-3 per kind.
  7. Advisor.review with memory wired: prompt CONTAINS the preamble.
     NEGATIVE — without injection, all the rated history is wasted.
  8. NEGATIVE: cited patterns get use_count incremented + last_used_at
     timestamped after the prompt is built. Without this, operators
     can't tell which patterns are stale vs. live.

Tag: readonly. Pure-Python — runs in tier 1.

Run:
    python3 mcp/tests/drill_sidecar_distillation.py
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


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# ── Module loader ────────────────────────────────────────────────
def _load_mod(rel: str, name: str):
    p = REPO / rel
    spec = importlib.util.spec_from_file_location(name, p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load spec from {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Set up package context so advisor.py's relative imports resolve
_pkg = types.ModuleType("sidecar_advisor_pkg")
_pkg.__path__ = [str(REPO / "services" / "sidecar-advisor")]
sys.modules["sidecar_advisor_pkg"] = _pkg

memory_mod = _load_mod(
    "services/sidecar-advisor/memory.py",
    "sidecar_advisor_pkg.memory",
)
sys.modules["sidecar_advisor_pkg.memory"] = memory_mod
distillation_mod = _load_mod(
    "services/sidecar-advisor/distillation.py",
    "sidecar_advisor_pkg.distillation",
)
sys.modules["sidecar_advisor_pkg.distillation"] = distillation_mod
advisor_mod = _load_mod(
    "services/sidecar-advisor/advisor.py",
    "sidecar_advisor_pkg.advisor",
)
sys.modules["sidecar_advisor_pkg.advisor"] = advisor_mod

AdvisorMemory = memory_mod.AdvisorMemory
distill = distillation_mod.distill
format_for_prompt = distillation_mod.format_for_prompt
Advisor = advisor_mod.Advisor


# ── Helpers ──────────────────────────────────────────────────────
def _seed_event(
    mem: AdvisorMemory,
    *,
    event_type: str,
    advice: list[str],
    rating: str | None,
    content: str = "x",
) -> int:
    """Insert one event row + optionally rate it."""
    eid = mem.record_event(
        event_type=event_type,
        source="manual",
        content=content,
        model_used="codegemma:7b-instruct",
        advisor_output={
            "summary": "summary",
            "risk_level": "LOW",
            "top_3_advice": advice,
            "confidence": 0.5,
        },
    )
    if rating:
        mem.rate_event(eid, rating)
    return eid


def _make_recording_generator():
    """Stub generator that records every prompt it sees."""
    calls: list[tuple[str, str, float]] = []

    async def _gen(model: str, prompt: str, timeout_s: float) -> str:
        calls.append((model, prompt, timeout_s))
        return (
            '{"summary":"x","risk_level":"LOW","top_3_advice":["a","b","c"],'
            '"confidence":0.5}'
        )
    return _gen, calls


# ── Drill ────────────────────────────────────────────────────────
async def main() -> None:
    # ── Step 1: 5 useful ratings → preference pattern ───────────
    step(
        "1. 5 useful ratings of the same advice → preference pattern, "
        "confidence > 0.7"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "p1.db")
        mem.set_policy_version("v1")
        for _ in range(5):
            _seed_event(
                mem, event_type="code",
                advice=["add tests", "rename var", "extract helper"],
                rating="useful",
            )
        events = mem.recent_events(limit=100, rated_only=True)
        proposals = distill(events)
        prefs = [p for p in proposals if p.pattern_kind == "preference"]
        if not prefs:
            fail(f"no preference patterns produced from 5 useful ratings: {proposals}")
        # "add tests" should appear (5 useful occurrences)
        add_tests = [p for p in prefs if p.pattern_text == "add tests"]
        if len(add_tests) != 1:
            fail(f"expected 1 'add tests' preference, got {len(add_tests)}")
        if add_tests[0].confidence < 0.7:
            fail(
                f"5 unanimous useful ratings should give confidence >= 0.7; "
                f"got {add_tests[0].confidence}"
            )
        ok(
            f"preference 'add tests' confidence={add_tests[0].confidence}; "
            f"sources={len(add_tests[0].source_event_ids)} events"
        )

    # ── Step 2: 3 not_useful ratings → mistake pattern ──────────
    step("2. 3 not_useful ratings of the same advice → mistake pattern")
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "p2.db")
        mem.set_policy_version("v1")
        for _ in range(3):
            _seed_event(
                mem, event_type="code",
                advice=["rename foo to bar"],
                rating="not_useful",
            )
        events = mem.recent_events(limit=100, rated_only=True)
        proposals = distill(events)
        mistakes = [p for p in proposals if p.pattern_kind == "mistake"]
        if not mistakes:
            fail(f"no mistake patterns from 3 not_useful: {proposals}")
        if mistakes[0].pattern_text != "rename foo to bar":
            fail(f"unexpected mistake text: {mistakes[0].pattern_text!r}")
        ok(f"mistake '{mistakes[0].pattern_text}' confidence={mistakes[0].confidence}")

    # ── Step 3: NEGATIVE — below MIN_FREQUENCY → no pattern ─────
    step(
        "3. NEGATIVE: 2 useful ratings (below MIN_FREQUENCY=3) → "
        "NO pattern (threshold prevents spurious promotion)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "p3.db")
        mem.set_policy_version("v1")
        _seed_event(
            mem, event_type="code", advice=["lonely advice"], rating="useful",
        )
        _seed_event(
            mem, event_type="code", advice=["lonely advice"], rating="useful",
        )
        events = mem.recent_events(limit=100, rated_only=True)
        proposals = distill(events)
        lonely = [p for p in proposals if p.pattern_text == "lonely advice"]
        if lonely:
            fail(
                f"2 useful ratings produced a pattern (should be filtered "
                f"by MIN_FREQUENCY=3): {lonely}"
            )
        ok("2 ratings below threshold → no pattern (correct)")

    # ── Step 4: NEGATIVE — mixed-polarity → no pattern ──────────
    step(
        "4. NEGATIVE: 3 useful + 3 not_useful ratings of the same advice "
        "→ NO pattern (mixed signal would fire conflicting injections)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "p4.db")
        mem.set_policy_version("v1")
        for _ in range(3):
            _seed_event(
                mem, event_type="code",
                advice=["controversial advice"], rating="useful",
            )
        for _ in range(3):
            _seed_event(
                mem, event_type="code",
                advice=["controversial advice"], rating="not_useful",
            )
        events = mem.recent_events(limit=100, rated_only=True)
        proposals = distill(events)
        mixed = [p for p in proposals if p.pattern_text == "controversial advice"]
        if mixed:
            fail(
                f"mixed-polarity advice produced a pattern: {mixed}. "
                f"With 50/50 useful/not_useful neither polarity meets "
                f"MIN_CONSISTENCY=0.66 — should be skipped."
            )
        ok("mixed signal → no pattern (drift on signal kept out of memory)")

    # ── Step 5: NEGATIVE — idempotent re-distill ────────────────
    step(
        "5. NEGATIVE: distill() is idempotent — re-running on the same "
        "events does NOT propose duplicates"
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "p5.db")
        mem.set_policy_version("v1")
        for _ in range(4):
            _seed_event(
                mem, event_type="code",
                advice=["repeating advice"], rating="useful",
            )
        events = mem.recent_events(limit=100, rated_only=True)

        # First run — populate memory
        proposals_1 = distill(events)
        for p in proposals_1:
            mem.add_pattern(
                pattern_kind=p.pattern_kind,
                pattern_text=p.pattern_text,
                source_event_ids=p.source_event_ids,
                confidence=p.confidence,
            )

        # Second run — should propose nothing new for the same events
        existing = mem.get_patterns()
        proposals_2 = distill(events, existing_patterns=existing)
        new_event_ids = sum(len(p.source_event_ids) for p in proposals_2)
        if new_event_ids != 0:
            fail(
                f"idempotency broken: re-distill proposed {new_event_ids} "
                f"new event_ids. Should be 0 — every event was already "
                f"cited in the existing pattern."
            )
        # Also check we don't have duplicate patterns in DB
        all_patterns = mem.get_patterns()
        seen = set()
        for p in all_patterns:
            key = (p["pattern_kind"], p["pattern_text"])
            if key in seen:
                fail(
                    f"duplicate pattern in DB after re-distill: {key}. "
                    f"add_pattern shouldn't be called for already-existing "
                    f"(kind, text) — that's idempotency caller-side."
                )
            seen.add(key)
        ok(f"re-distill: 0 new event_ids; {len(all_patterns)} patterns in DB")

    # ── Step 6: format_for_prompt renders preview correctly ─────
    step(
        "6. format_for_prompt renders top-3 preferences + top-3 mistakes "
        "as a clean preamble"
    )
    fake_patterns = [
        {"pattern_kind": "preference", "pattern_text": "add tests",
         "confidence": 0.9},
        {"pattern_kind": "preference", "pattern_text": "use type hints",
         "confidence": 0.85},
        {"pattern_kind": "mistake", "pattern_text": "rename for style",
         "confidence": 0.75},
    ]
    rendered = format_for_prompt(fake_patterns)
    if "User preferences" not in rendered:
        fail(f"render missing 'User preferences' header: {rendered!r}")
    if "Avoid suggesting" not in rendered:
        fail(f"render missing 'Avoid suggesting' header: {rendered!r}")
    if "add tests" not in rendered:
        fail("render missing 'add tests' preference text")
    if "rename for style" not in rendered:
        fail("render missing 'rename for style' mistake text")
    if "(confidence=0.90)" not in rendered:
        fail(f"confidence not rendered: {rendered!r}")
    # Empty patterns → empty string
    if format_for_prompt([]) != "":
        fail("format_for_prompt([]) should return ''")
    ok("preferences + mistakes rendered with confidences")

    # ── Step 7: advisor with memory injects preamble into prompt ─
    step(
        "7. NEGATIVE: Advisor.review with memory wired injects the "
        "preamble into the prompt"
    )
    import yaml
    policy = yaml.safe_load(
        (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
    )
    with tempfile.TemporaryDirectory() as tmp:
        mem = AdvisorMemory(pathlib.Path(tmp) / "p7.db")
        mem.set_policy_version("v1")
        # Seed memory with one preference + one mistake (so preamble has both)
        pref_id = mem.add_pattern(
            pattern_kind="preference",
            pattern_text="always add tests",
            source_event_ids=[1, 2, 3],
            confidence=0.9,
        )
        mistake_id = mem.add_pattern(
            pattern_kind="mistake",
            pattern_text="rename for style",
            source_event_ids=[4, 5, 6],
            confidence=0.8,
        )
        gen_fn, calls = _make_recording_generator()
        advisor = Advisor(policy, generate_fn=gen_fn, memory=mem)
        # Use 'code' route — single-agent path (council bypasses preamble)
        await advisor.review(event_type="code", content="def foo(): pass")
        if not calls:
            fail("generator wasn't called")
        sent_prompt = calls[0][1]
        if "User preferences" not in sent_prompt:
            fail(
                f"prompt missing memory preamble (User preferences): "
                f"first 300 chars = {sent_prompt[:300]!r}"
            )
        if "always add tests" not in sent_prompt:
            fail("preference text not in prompt")
        if "Avoid suggesting" not in sent_prompt:
            fail("mistakes header not in prompt")
        if "rename for style" not in sent_prompt:
            fail("mistake text not in prompt")
        # Sanity: the original prompt body still present
        if "def foo(): pass" not in sent_prompt:
            fail("user content lost from prompt")
        ok(
            f"prompt contains preamble + content "
            f"({len(sent_prompt)} chars total)"
        )

        # ── Step 8: NEGATIVE — use_count + last_used_at bumped ──
        step(
            "8. NEGATIVE: cited patterns get use_count incremented + "
            "last_used_at timestamped after prompt build"
        )
        # Re-read patterns; they should both have use_count=1 (single
        # prior advisor.review call).
        prefs_after = mem.get_patterns(kind="preference")
        mistakes_after = mem.get_patterns(kind="mistake")
        pref_after = next(p for p in prefs_after if p["id"] == pref_id)
        mistake_after = next(p for p in mistakes_after if p["id"] == mistake_id)
        if pref_after["use_count"] != 1:
            fail(
                f"preference use_count not bumped: {pref_after['use_count']}. "
                f"Operators can't tell live patterns from stale ones."
            )
        if mistake_after["use_count"] != 1:
            fail(f"mistake use_count not bumped: {mistake_after['use_count']}")
        if pref_after["last_used_at"] is None:
            fail("preference last_used_at not set")
        if mistake_after["last_used_at"] is None:
            fail("mistake last_used_at not set")
        ok(
            f"both patterns: use_count=1, "
            f"last_used_at={pref_after['last_used_at']}"
        )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 DISTILLATION STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 3, 4, 5, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
