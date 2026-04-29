#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: Sidecar Advisor — pr_review delegates to the AgentBoard council.

Locks the contract that:

  pr_review event_type
    → Advisor.review delegates to PrReviewCouncil
    → 3 specialised authors run in parallel against 3 different
      models (DeepSeek, CodeLlama, CodeGemma)
    → 1 reviewer (StarCoder2) scores each draft
    → 1 chair (DeepSeek again) synthesises top-3 advice as JSON
    → AdvisorOutput is returned with model_used = chair's model

Eight steps. Five negative assertions.

  1. PrReviewCouncil builds an AgentBoard with exactly the 3
     specialised authors + 1 reviewer + 1 advisor.
  2. Each author calls the generator with ITS role's model (not
     the same model 3 times).
  3. NEGATIVE: each author's prompt template is role-specific
     (security_auditor's prompt mentions security, NOT tests).
     A regression that pointed all three authors at the same
     prompt would silently collapse the council into
     three-of-the-same-thing.
  4. NEGATIVE: chair gets a JSON-shaped advisor prompt that
     references the drafts + reviews. Without that, the chair
     can't synthesise — it would produce free-form prose, which
     would fail the AdvisorOutput parser and lose top_3_advice.
  5. Council returns a parsed AdvisorOutput when chair emits
     valid JSON. The model_used is the chair's model.
  6. NEGATIVE: chair returns prose (un-parseable). Council MUST
     return a placeholder AdvisorOutput with the prose preserved
     in better_prompt_or_code, NOT raise an exception.
  7. NEGATIVE: one author errors. Other authors' drafts still
     surface; failed_authors records the failure; chair still runs.
  8. Advisor.review delegates the pr_review route to the council
     (not the single-agent path). NEGATIVE: a regression that
     fell through to the single-agent path would call ONE model
     once instead of the council's seven calls.

Tag: readonly. Pure-Python — runs in tier 1.

Run:
    python3 mcp/tests/drill_sidecar_pr_review_council.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

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


# ── Module loader (avoid heavy package __init__) ────────────────
def _load_mod(rel: str, name: str):
    p = REPO / rel
    spec = importlib.util.spec_from_file_location(name, p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load spec from {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-load advisor + council; council relies on advisor at import time.
advisor_mod = _load_mod(
    "services/sidecar-advisor/advisor.py", "sidecar_advisor",
)
# Council does `from .advisor import AdvisorOutput`; that won't resolve
# in the importlib-loaded module. Patch sys.modules so the relative
# import lands on the same object.
sys.modules["sidecar_advisor"].__package__ = "sidecar_advisor_pkg"
import types
_pkg = types.ModuleType("sidecar_advisor_pkg")
_pkg.advisor = advisor_mod
_pkg.__path__ = [str(REPO / "services" / "sidecar-advisor")]
sys.modules["sidecar_advisor_pkg"] = _pkg
sys.modules["sidecar_advisor_pkg.advisor"] = advisor_mod

council_mod = _load_mod(
    "services/sidecar-advisor/council.py",
    "sidecar_advisor_pkg.council",
)
PrReviewCouncil = council_mod.PrReviewCouncil
ROLE_AUTHORS = council_mod.ROLE_AUTHORS
# Canonical chair-model reference. ADVISOR_MODEL = _CHAIR.model in
# services/sidecar-advisor/council.py — sourcing it via the module
# (rather than hardcoding a string) is the ADR-017 structural
# rewrite of the previous hardcoded "deepseek-coder:6.7b-instruct"
# expectation, which broke when the chair was switched to kimi-k2.
ADVISOR_MODEL = council_mod.ADVISOR_MODEL


# ── Stub generator that records every (model, prompt) call ──────
class RecordingGenerator:
    """Captures every LLM call so the drill can assert on the shape
    of what the council issued."""

    def __init__(
        self,
        author_response: str = "draft text from {model}",
        reviewer_response: str = "looks ok\nSCORE: 7",
        chair_response: str = '{"summary":"good","risk_level":"LOW",'
                              '"top_3_advice":["add tests","handle null",'
                              '"document API"],"confidence":0.7}',
    ) -> None:
        self.calls: list[tuple[str, str, float]] = []
        self._author_response = author_response
        self._reviewer_response = reviewer_response
        self._chair_response = chair_response

    async def __call__(self, model: str, prompt: str, timeout_s: float) -> str:
        self.calls.append((model, prompt, timeout_s))
        # Heuristic: pick the response by what kind of prompt it is.
        # The chair prompt asks for JSON — it contains "JSON:" at the
        # tail. The reviewer prompt asks for SCORE: in output.
        if prompt.rstrip().endswith("JSON:"):
            return self._chair_response
        if "SCORE: <integer 0-10>" in prompt:
            return self._reviewer_response
        # Otherwise it's an author prompt
        return self._author_response.replace("{model}", model)


# ── Drill ────────────────────────────────────────────────────────
async def main() -> None:
    # ── Step 1: council builds with right structure ─────────────
    step("1. PrReviewCouncil.build_board produces 3 authors + 1 reviewer + 1 advisor")
    gen = RecordingGenerator()
    council = PrReviewCouncil(generate_fn=gen)
    board = council.build_board()
    if len(board._authors) != 3:
        fail(f"expected 3 authors, got {len(board._authors)}: {list(board._authors)}")
    if len(board._reviewers) != 1:
        fail(f"expected 1 reviewer, got {len(board._reviewers)}")
    expected_authors = {"code_reviewer", "security_auditor", "test_advisor"}
    if set(board._authors) != expected_authors:
        fail(f"author roles wrong: {set(board._authors)} vs {expected_authors}")
    ok(f"board has {list(board._authors)} authors + {list(board._reviewers)} reviewer")

    # ── Step 2: each author uses ITS role's model ──────────────
    step("2. each author calls the generator with the role's specialised model")
    gen.calls.clear()
    council = PrReviewCouncil(generate_fn=gen)
    parsed, raw = await council.review("def foo(): return 1/0")

    # Map (call → role) by checking the prompt template signature.
    author_calls = [
        (model, prompt) for (model, prompt, _t) in gen.calls
        if not prompt.rstrip().endswith("JSON:")
        and "SCORE: <integer 0-10>" not in prompt
    ]
    if len(author_calls) != 3:
        fail(
            f"expected 3 author calls, got {len(author_calls)} "
            f"(total gen calls: {len(gen.calls)})"
        )
    models_used = sorted(m for m, _p in author_calls)
    expected_models = sorted(m for m, _ in ROLE_AUTHORS.values())
    if models_used != expected_models:
        fail(
            f"author models drifted from spec:\n"
            f"  got:      {models_used}\n"
            f"  expected: {expected_models}\n"
            f"Each author MUST call its role's distinct model — "
            f"using the same model for all three collapses the "
            f"council's diversity argument."
        )
    ok(f"3 author calls hit 3 distinct models: {models_used}")

    # ── Step 3: NEGATIVE — each author's prompt is role-specific ─
    step(
        "3. NEGATIVE: each author's prompt template is role-specific "
        "(security prompt mentions security, NOT tests)"
    )
    by_model = {m: p for m, p in author_calls}
    sec_prompt = by_model["codellama:7b-instruct"].lower()
    test_prompt = by_model["codegemma:7b-instruct"].lower()
    code_prompt = by_model["deepseek-coder:6.7b-instruct"].lower()
    if "security" not in sec_prompt or "auth" not in sec_prompt:
        fail(
            f"security_auditor prompt missing 'security' / 'auth' "
            f"keywords: {sec_prompt[:200]!r}"
        )
    if "test" not in test_prompt or "coverage" not in test_prompt:
        fail(
            f"test_advisor prompt missing 'test' / 'coverage' "
            f"keywords: {test_prompt[:200]!r}"
        )
    if "bugs" not in code_prompt and "edge cases" not in code_prompt:
        fail(
            f"code_reviewer prompt missing 'bugs' / 'edge cases' "
            f"keywords: {code_prompt[:200]!r}"
        )
    # NEGATIVE: cross-contamination check — each role's prompt
    # should NOT contain the OTHER roles' primary focus.
    if "test" in sec_prompt and "missing tests" in sec_prompt:
        fail(
            f"security prompt is contaminated with test focus — "
            f"would collapse the council's role specialisation"
        )
    ok("each author's prompt is role-specific (security/test/bugs distinct)")

    # ── Step 4: NEGATIVE — chair prompt is JSON-shaped ──────────
    step(
        "4. NEGATIVE: chair prompt asks for JSON + references drafts + reviews"
    )
    chair_calls = [
        (m, p) for m, p, _ in gen.calls if p.rstrip().endswith("JSON:")
    ]
    if len(chair_calls) != 1:
        fail(f"expected 1 chair call, got {len(chair_calls)}")
    chair_prompt = chair_calls[0][1]
    if "JSON" not in chair_prompt:
        fail("chair prompt didn't request JSON — output won't parse")
    # The advisor template must reference both drafts and reviews
    if "DRAFTS" not in chair_prompt or "REVIEWS" not in chair_prompt:
        fail(
            f"chair prompt missing drafts/reviews context — "
            f"chair would synthesise from nothing. Got: "
            f"{chair_prompt[:300]!r}"
        )
    if "top_3_advice" not in chair_prompt:
        fail("chair prompt didn't ask for top_3_advice in the JSON shape")
    ok("chair prompt requests JSON and references drafts + reviews")

    # ── Step 5: parsed AdvisorOutput; model_used = chair's model ─
    step("5. council returns parsed AdvisorOutput on valid chair JSON")
    if parsed is None:
        fail("council returned None on valid chair JSON")
    if parsed.summary != "good":
        fail(f"summary not parsed correctly: {parsed.summary!r}")
    if parsed.top_3_advice != ["add tests", "handle null", "document API"]:
        fail(f"top_3_advice wrong: {parsed.top_3_advice}")
    if parsed.model_used != ADVISOR_MODEL:
        fail(
            f"model_used should match council.ADVISOR_MODEL "
            f"({ADVISOR_MODEL!r}), got {parsed.model_used!r}"
        )
    ok(f"parsed AdvisorOutput model_used={parsed.model_used}; advice={parsed.top_3_advice}")

    # ── Step 6: NEGATIVE — chair returns prose, council degrades ─
    step(
        "6. NEGATIVE: chair returns un-parseable prose → "
        "council degrades, doesn't crash"
    )
    prose_gen = RecordingGenerator(
        chair_response=(
            "I think the code looks pretty good overall, "
            "though there are a few minor issues."
        ),
    )
    prose_council = PrReviewCouncil(generate_fn=prose_gen)
    parsed2, raw2 = await prose_council.review("code")
    if parsed2 is None:
        fail(
            "council returned None on un-parseable chair output; "
            "should return a degraded-but-usable placeholder so the "
            "UI still renders something."
        )
    if not parsed2.better_prompt_or_code:
        fail(
            "council placeholder didn't carry chair's prose into "
            "better_prompt_or_code; the user loses the chair's text"
        )
    if "looks pretty good" not in parsed2.better_prompt_or_code:
        fail(
            f"chair's prose missing from placeholder: "
            f"{parsed2.better_prompt_or_code[:120]!r}"
        )
    if parsed2.confidence != 0.0:
        fail(
            f"degraded result should report confidence=0.0 to "
            f"signal the unparseable output; got {parsed2.confidence}"
        )
    ok(
        f"prose chair → placeholder w/ prose preserved; confidence={parsed2.confidence}"
    )

    # ── Step 7: NEGATIVE — one author errors, board still runs ──
    step(
        "7. NEGATIVE: one author errors → other drafts surface, "
        "chair still synthesises (failed_authors recorded)"
    )

    class PartialFailGenerator(RecordingGenerator):
        async def __call__(self, model: str, prompt: str, timeout_s: float) -> str:
            self.calls.append((model, prompt, timeout_s))
            if model == "codellama:7b-instruct" and not prompt.rstrip().endswith("JSON:"):
                # Security auditor crashes
                raise RuntimeError("simulated codellama failure")
            if prompt.rstrip().endswith("JSON:"):
                return self._chair_response
            if "SCORE: <integer 0-10>" in prompt:
                return self._reviewer_response
            return self._author_response.replace("{model}", model)

    fail_gen = PartialFailGenerator()
    fail_council = PrReviewCouncil(generate_fn=fail_gen)
    parsed3, raw3 = await fail_council.review("code")

    if "security_auditor" not in raw3["failed_authors"]:
        fail(
            f"failed_authors should include security_auditor; got "
            f"{raw3['failed_authors']}"
        )
    # Other 2 authors should have non-error drafts
    surviving = [
        d for d in raw3["drafts"]
        if d["author_id"] != "security_auditor" and d["error"] is None
    ]
    if len(surviving) != 2:
        fail(
            f"expected 2 surviving drafts, got {len(surviving)}: "
            f"{[d['author_id'] for d in surviving]}"
        )
    if parsed3 is None:
        fail("chair didn't run after partial author failure")
    ok(
        f"security_auditor errored cleanly; "
        f"surviving authors: {[d['author_id'] for d in surviving]}"
    )

    # ── Step 8: Advisor.review delegates pr_review to council ───
    step(
        "8. NEGATIVE: Advisor.review on pr_review delegates to council "
        "(NOT the single-agent path)"
    )
    # Build a fresh advisor with our recording generator so we can count
    # the LLM calls and verify the council was actually used.
    import yaml
    policy = yaml.safe_load(
        (REPO / "services" / "sidecar-advisor" / "policy.yaml").read_text()
    )
    counting_gen = RecordingGenerator()
    advisor = advisor_mod.Advisor(policy, generate_fn=counting_gen)
    parsed4, raw, model_used, duration, telemetry = await advisor.review(
        event_type="pr_review", content="def foo(): pass",
    )
    if parsed4 is None:
        fail(f"Advisor.review returned None on pr_review; raw={raw!r}")
    # Single-agent path = 1 LLM call. Council = 3 authors + 3 reviews + 1 chair = 7 calls.
    if len(counting_gen.calls) < 5:
        fail(
            f"Advisor.review made only {len(counting_gen.calls)} LLM "
            f"calls — likely fell through to single-agent path. "
            f"Council should have made 7."
        )
    ok(
        f"pr_review delegated to council "
        f"({len(counting_gen.calls)} LLM calls, "
        f"model_used={model_used})"
    )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 PR-REVIEW COUNCIL STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 3, 4, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
