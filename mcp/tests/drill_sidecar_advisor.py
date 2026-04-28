#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Sidecar Advisor — Phase 1 backend pieces (classifier + memory
+ advisor with stub generator).

Locks the Phase 1 contract:

  paste → classify → policy.routes lookup → advisor.review →
  AdvisorOutput parsed → memory.record_event → memory.rate_event

Eight steps. Five negative assertions.

  1. Classifier rules: PROMPT default; CODE on def/import; DEBUG on
     traceback; ARCHITECTURE on ADR; PR_REVIEW on diff hunk header.
     A regression that mis-routes any of these silently sends the
     wrong agent at the wrong model.
  2. Classifier priority: Python traceback contains BOTH
     `File "x.py"` AND `def foo()`. The DEBUG rule MUST outrank the
     CODE rule. NEGATIVE — if reordered, every error paste would be
     reviewed by the code_reviewer (wrong model, wrong prompt).
  3. AdvisorOutput.parse handles ```json fences AND prose-wrapped JSON
     AND plain JSON. NEGATIVE — a strict parser breaks against every
     real model output (LLMs are not strict JSON-emitters).
  4. AdvisorOutput.parse returns None for non-recoverable junk.
     NEGATIVE — a parser that returns a default-filled object on bad
     input would mask model failure modes.
  5. Advisor.review with stub generator: returns parsed output for
     every supported event_type from the policy.
  6. Advisor.review on unknown route returns a placeholder + risk=LOW.
     NEGATIVE — falling back to the default model on unknown routes
     would silently mis-route un-classified events.
  7. memory.record_event + rate_event roundtrip: insert, rate,
     read back. policy_version + content_hash both populated.
     NEGATIVE — empty policy_version means the event isn't
     attributable to a specific policy edit.
  8. memory.stats() returns the right rated_pct after mixed
     ratings. NEGATIVE — division-by-zero crash on empty DB would
     break the dashboard footer.

Tag: readonly. Pure-Python — runs in tier 1 (drills-fast).

Run:
    python3 mcp/tests/drill_sidecar_advisor.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import tempfile

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


# ── Module loader (avoid heavy package __init__.py imports) ─────
def _load_mod(rel: str, name: str):
    p = REPO / rel
    spec = importlib.util.spec_from_file_location(name, p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load spec from {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


classifier = _load_mod(
    "services/sidecar-advisor/classifier.py", "sidecar_classifier",
)
memory_mod = _load_mod(
    "services/sidecar-advisor/memory.py", "sidecar_memory",
)
advisor_mod = _load_mod(
    "services/sidecar-advisor/advisor.py", "sidecar_advisor",
)
EventType = classifier.EventType


def _load_policy() -> dict:
    """Load policy.yaml. PyYAML is already a dep elsewhere in the repo
    (ingestion-svc requirements) so this drill assumes it. If it's
    missing in your env: `pip install pyyaml`."""
    import yaml
    p = REPO / "services" / "sidecar-advisor" / "policy.yaml"
    return yaml.safe_load(p.read_text())


# ── Stub generator (no Ollama needed) ───────────────────────────
def _make_stub_generator(canned_response: str):
    """Return a generate_fn that always returns canned_response."""
    async def _gen(model: str, prompt: str, timeout_s: float) -> str:
        return canned_response
    return _gen


GOOD_JSON_RESPONSE = """\
Here is my analysis:
```json
{
  "summary": "test summary",
  "risk_level": "MEDIUM",
  "top_3_advice": ["a1", "a2", "a3"],
  "better_prompt_or_code": "improved",
  "next_action": "do thing",
  "confidence": 0.7
}
```
"""

PROSE_WRAPPED_JSON = (
    'I think the prompt could use some work. Here you go:\n\n'
    '{"summary": "needs constraints", "risk_level": "LOW", '
    '"top_3_advice": ["add tests", "clarify input"], '
    '"better_prompt_or_code": "Write a Python function that...", '
    '"next_action": "rerun", "confidence": 0.8}\n\n'
    'Hope this helps.'
)

JUNK_RESPONSE = "I don't know how to answer that. Sorry!"


# ── Drill ────────────────────────────────────────────────────────
async def main() -> None:
    # ── Step 1: classifier hits each rule ────────────────────────
    step("1. classifier routes each canonical paste shape correctly")
    cases = [
        ("Write me a function that sums a list", EventType.PROMPT),
        ("def foo():\n    return 42", EventType.CODE),
        ("import os\nprint(os.getcwd())", EventType.CODE),
        (
            'Traceback (most recent call last):\n  File "x.py", line 5, in <module>\n'
            "    1/0\nZeroDivisionError: division by zero",
            EventType.DEBUG,
        ),
        (
            "ADR-007: We will use Postgres for the audit log because "
            "RLS gives us per-tenant isolation.",
            EventType.ARCHITECTURE,
        ),
        (
            "diff --git a/foo.py b/foo.py\n@@ -1,3 +1,3 @@\n-old\n+new",
            EventType.PR_REVIEW,
        ),
    ]
    for paste, expected in cases:
        actual = classifier.classify_input(paste)
        if actual != expected:
            fail(
                f"classifier mis-routed: {paste[:40]!r} → {actual.value!r}, "
                f"expected {expected.value!r}"
            )
    ok(f"all 6 canonical shapes route to expected event_type")

    # ── Step 2: NEGATIVE — DEBUG outranks CODE ──────────────────
    step("2. NEGATIVE: traceback containing 'def' MUST classify as DEBUG, not CODE")
    tricky = (
        "Traceback (most recent call last):\n"
        '  File "/app/foo.py", line 7, in foo\n'
        "    def bar():  # this would match code rule\n"
        "        return 1/0\n"
        "ZeroDivisionError: division by zero"
    )
    actual = classifier.classify_input(tricky)
    if actual != EventType.DEBUG:
        fail(
            f"priority broken: traceback → {actual.value!r}; expected DEBUG. "
            f"A regression here would route every error paste to "
            f"code_reviewer agent at the wrong model."
        )
    ok(f"traceback with embedded 'def' → DEBUG (rule priority preserved)")

    # ── Step 3: parser handles fences, prose-wrap, plain JSON ───
    step(
        "3. AdvisorOutput.parse handles ```json fences AND prose-wrapped "
        "JSON AND plain JSON"
    )
    for label, raw in [
        ("fence", GOOD_JSON_RESPONSE),
        ("prose_wrap", PROSE_WRAPPED_JSON),
        ("plain", '{"summary":"plain","risk_level":"HIGH",'
                  '"top_3_advice":["x"],"confidence":0.5}'),
    ]:
        out = advisor_mod.AdvisorOutput.parse(raw, model_used="test:7b")
        if out is None:
            fail(f"parse failed on {label}: {raw[:80]!r}")
        if not out.summary:
            fail(f"parse {label}: summary empty")
        if out.risk_level not in {"LOW", "MEDIUM", "HIGH"}:
            fail(f"parse {label}: bad risk_level {out.risk_level!r}")
        if not 0.0 <= out.confidence <= 1.0:
            fail(f"parse {label}: confidence {out.confidence} out of [0,1]")
    ok("fence + prose-wrapped + plain all parsed cleanly")

    # ── Step 4: NEGATIVE — non-recoverable input returns None ───
    step(
        "4. NEGATIVE: parser returns None for unrecoverable junk "
        "(not a default-filled placeholder)"
    )
    out = advisor_mod.AdvisorOutput.parse(JUNK_RESPONSE, model_used="test:7b")
    if out is not None:
        fail(
            f"parser returned {out!r} on junk input. A default-filled "
            f"placeholder masks model failure — the caller must see None "
            f"to know the response was unparseable."
        )
    ok("junk → None (caller can detect parse failure)")

    # ── Step 5: advisor.review for each supported event_type ────
    step(
        "5. Advisor.review with stub generator parses output for every "
        "supported event_type from policy"
    )
    policy = _load_policy()
    routes = policy["advisor_policy"]["routes"]
    if not {"prompt", "code", "architecture", "pr_review", "debug"} <= set(routes):
        fail(
            f"policy missing required routes: present={list(routes)}. "
            f"All Phase 1 routes must be in policy.yaml."
        )
    advisor = advisor_mod.Advisor(
        policy,
        generate_fn=_make_stub_generator(GOOD_JSON_RESPONSE),
    )
    for event_type in ["prompt", "code", "architecture", "pr_review", "debug"]:
        parsed, raw, model_used, duration = await advisor.review(
            event_type=event_type, content="test content",
        )
        if parsed is None:
            fail(
                f"advisor.review returned None for known event_type "
                f"{event_type!r}. raw={raw!r}"
            )
        if parsed.summary != "test summary":
            fail(f"advisor.review {event_type!r}: wrong summary {parsed.summary!r}")
        if not model_used:
            fail(f"advisor.review {event_type!r}: model_used empty")
    ok(f"all 5 routes parsed cleanly via stub generator")

    # ── Step 6: NEGATIVE — unknown route → placeholder, no fallthrough ─
    step(
        "6. NEGATIVE: unknown event_type returns placeholder, NOT silent "
        "fallthrough to default model"
    )
    parsed, raw, model_used, duration = await advisor.review(
        event_type="not_a_real_route", content="x",
    )
    if parsed is None:
        fail("unknown route returned None; expected placeholder")
    if parsed.risk_level != "LOW":
        fail(
            f"unknown route should yield risk_level=LOW (placeholder), "
            f"got {parsed.risk_level!r}. Otherwise un-classified events "
            f"silently affect risk metrics."
        )
    if model_used:
        fail(
            f"unknown route should NOT pick a model (model_used={model_used!r}). "
            f"Silent fallthrough to default_model is a routing bug, not a feature."
        )
    ok(f"unknown route → placeholder (summary={parsed.summary!r})")

    # ── Step 7: memory roundtrip + policy_version present ───────
    step(
        "7. memory.record_event → rate_event → recent_events roundtrip; "
        "NEGATIVE: policy_version + content_hash MUST be populated"
    )
    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "test_advisor.db"
        mem = memory_mod.AdvisorMemory(db_path)
        mem.set_policy_version("test_policy_v_abc")

        event_id = mem.record_event(
            event_type="prompt",
            source="manual",
            content="hello world",
            model_used="codegemma:7b-instruct",
            advisor_output={
                "summary": "test", "risk_level": "LOW",
                "top_3_advice": ["a"], "confidence": 0.5,
            },
            duration_s=1.5,
        )
        if event_id <= 0:
            fail(f"record_event returned bad id {event_id}")

        if not mem.rate_event(event_id, "useful"):
            fail("rate_event returned False; row not updated")

        events = mem.recent_events(limit=5)
        if len(events) != 1:
            fail(f"expected 1 event, got {len(events)}")
        ev = events[0]
        if ev["policy_version"] != "test_policy_v_abc":
            fail(
                f"policy_version not persisted: {ev['policy_version']!r}. "
                f"Without it, audit can't attribute behaviour to a "
                f"specific policy edit."
            )
        if not ev["content_hash"] or len(ev["content_hash"]) != 16:
            fail(
                f"content_hash missing or wrong length: {ev['content_hash']!r}"
            )
        if ev["user_rating"] != "useful":
            fail(f"rating not persisted: {ev['user_rating']!r}")
        if not ev["rated_at"]:
            fail("rated_at not set after rate_event()")
        ok(
            f"event id={event_id}, policy_version={ev['policy_version']}, "
            f"content_hash={ev['content_hash']}, rating={ev['user_rating']}"
        )

    # ── Step 8: NEGATIVE — stats() doesn't crash on empty DB ────
    step(
        "8. NEGATIVE: stats() returns rated_pct=0.0 on empty DB "
        "(no division-by-zero crashing the dashboard)"
    )
    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "empty.db"
        mem = memory_mod.AdvisorMemory(db_path)
        s = mem.stats()
        if s["total_events"] != 0:
            fail(f"empty DB total_events != 0: {s}")
        if s["rated_pct"] != 0.0:
            fail(
                f"empty DB rated_pct != 0.0: {s['rated_pct']}. "
                f"Division-by-zero would crash the UI footer."
            )
        ok(f"empty DB stats: {s}")

    # Mixed ratings (sanity check)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "mixed.db"
        mem = memory_mod.AdvisorMemory(db_path)
        mem.set_policy_version("v1")
        for i in range(4):
            eid = mem.record_event(
                event_type="prompt", source="manual",
                content=f"content {i}",
                model_used="codegemma:7b-instruct",
                advisor_output={"summary": "x", "risk_level": "LOW",
                                 "top_3_advice": ["a"], "confidence": 0.5},
            )
            if i < 2:
                mem.rate_event(eid, "useful")
            elif i == 2:
                mem.rate_event(eid, "not_useful")
            # i==3 left unrated
        s = mem.stats()
        if s["total_events"] != 4 or s["useful"] != 2 or s["not_useful"] != 1:
            fail(f"mixed stats wrong: {s}")
        # rated_pct = (2 useful + 1 not_useful) / 4 = 75%
        if s["rated_pct"] != 75.0:
            fail(f"rated_pct should be 75.0, got {s['rated_pct']}")
        ok(f"mixed-rating stats correct: {s}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 SIDECAR-ADVISOR STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 4, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
