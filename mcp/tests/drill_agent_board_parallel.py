#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: AgentBoard — parallel author / reviewer / advisor contracts.

The board pattern is the multi-agent equivalent of map/reduce:

    task → [N authors in parallel] → drafts
         → [N×K reviewers in parallel, bounded] → reviews
         → [advisor, single sequential synth] → final advice

This drill locks in seven invariants. Four are NEGATIVE — they
prove the board *rejects* the failure mode, not just that the happy
path works.

  1. Authors run in parallel.
     Assert: 4 authors at 100ms each finish in <250ms wall time
     (sequential would take >=400ms). NEGATIVE: regressing to
     sequential would balloon p95 by ~Nx — caught here.
  2. Reviews run in parallel under the shared semaphore.
     Assert: drafts × reviewers cross-product is bounded by
     max_parallel, not unbounded.
  3. Ordering is deterministic. Despite parallel completion, the
     drafts list comes out sorted by author_id and reviews by
     (draft_author_id, reviewer_id). NEGATIVE: a regression that
     returned asyncio.gather order would be non-deterministic for
     dict-sized > 7 (CPython's hash randomisation kicks in for sets
     but author dicts preserve insertion order — still, this drill
     locks the explicit contract regardless of upstream ordering).
  4. NEGATIVE: a single author raising does NOT sink the board.
     The other authors' drafts still surface; the failed author
     gets a Draft with .error set; failed_authors records it.
  5. NEGATIVE: a single reviewer raising does NOT sink the board.
     Other reviewers of the same draft still produce reviews.
  6. NEGATIVE: drafts that errored are SKIPPED by reviewers — the
     reviewer is not invoked with empty text. Reviewing an empty
     draft would mask the upstream author error and burn LLM cost.
  7. NEGATIVE: advisor failure triggers the highest-scored-draft
     fallback, not an empty result. BoardResult.error captures the
     exception so operations can detect degraded mode.

Step counts the negative assertions explicitly because that's the
discipline §43.6 enforces: "Every drill needs at least one negative
assertion." This drill has four.

Tag: readonly — the drill is pure-Python, no I/O, runs in tier 1.

Run:
    python3 mcp/tests/drill_agent_board_parallel.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import time

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
# Bypass services/inference-svc/app/agents/__init__.py — it pulls
# the heavy multi_hop_agent which needs documind_core. We only want
# agent_board.py.
def _load_agent_board():
    p = REPO / "libs" / "py" / "documind_core" / "agent_board.py"
    spec = importlib.util.spec_from_file_location("agent_board_mod", p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load spec from {p}")
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec, so @dataclass(frozen=True)
    # can resolve cls.__module__ when it walks the namespace.
    sys.modules["agent_board_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


ab = _load_agent_board()
AgentBoard = ab.AgentBoard
make_agent = ab.make_agent


# ── Helper agents ────────────────────────────────────────────────
def slow_author(author_id: str, hold_s: float = 0.1):
    """Author that sleeps then returns 'draft from <id>'. Tag the
    draft text with the id so we can verify ordering."""

    async def _agent(prompt: str) -> str:
        await asyncio.sleep(hold_s)
        return f"draft from {author_id}: {prompt}"

    return make_agent(_agent)


def failing_author(author_id: str, exc_class=RuntimeError, message: str = "boom"):
    async def _agent(prompt: str) -> str:
        await asyncio.sleep(0.01)
        raise exc_class(f"{author_id}: {message}")

    return make_agent(_agent)


def scoring_reviewer(reviewer_id: str, score: int = 7, hold_s: float = 0.1):
    """Reviewer that emits a SCORE: <n> trailer the board parses."""

    async def _agent(prompt: str) -> str:
        await asyncio.sleep(hold_s)
        return f"reviewer {reviewer_id} thinks this is fine.\nSCORE: {score}"

    return make_agent(_agent)


def failing_reviewer(reviewer_id: str):
    async def _agent(prompt: str) -> str:
        raise RuntimeError(f"reviewer {reviewer_id} failed")

    return make_agent(_agent)


class CountingReviewer:
    """Reviewer that records every prompt it sees. Lets the drill
    assert 'reviewer was NOT called for the errored draft'."""

    def __init__(self, reviewer_id: str, score: int = 8):
        self.reviewer_id = reviewer_id
        self.score = score
        self.invocations: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.invocations.append(prompt)
        return f"counting {self.reviewer_id}\nSCORE: {self.score}"


class ConcurrencyTracker:
    """Records start + end timestamps so the drill can assert
    'simultaneously in-flight count never exceeded max_parallel'."""

    def __init__(self, agent_id: str, hold_s: float = 0.05):
        self.agent_id = agent_id
        self.hold_s = hold_s
        self.events: list[tuple[float, str]] = []

    async def __call__(self, prompt: str) -> str:
        t0 = time.monotonic()
        self.events.append((t0, "start"))
        await asyncio.sleep(self.hold_s)
        t1 = time.monotonic()
        self.events.append((t1, "end"))
        return f"tracked {self.agent_id}\nSCORE: 6"


def good_advisor():
    async def _agent(prompt: str) -> str:
        await asyncio.sleep(0.01)
        return f"FINAL: synth of {prompt[:30]}"

    return make_agent(_agent)


def failing_advisor():
    async def _agent(prompt: str) -> str:
        raise RuntimeError("advisor crashed")

    return make_agent(_agent)


# ── Drill ────────────────────────────────────────────────────────
async def main() -> None:
    # ── Step 1: authors run in parallel ─────────────────────────
    step(
        "1. authors run in parallel "
        "(4 authors × 100ms must finish in <250ms wall)"
    )
    # 4 authors, each holding 100ms. Parallel: ~100ms. Sequential: ~400ms.
    # max_parallel=4 means all four can be in flight at once.
    board = AgentBoard(
        authors={f"a{i}": slow_author(f"a{i}", 0.1) for i in range(4)},
        reviewers={"r1": scoring_reviewer("r1", 7, 0.01)},
        advisor=good_advisor(),
        max_parallel=4,
    )
    t0 = time.monotonic()
    result = await board.run("test parallelism")
    elapsed = time.monotonic() - t0
    if elapsed > 0.30:
        fail(
            f"authors appear sequential: 4×100ms took {elapsed * 1000:.0f}ms "
            f"(parallel target <250ms; sequential would be ~400ms)"
        )
    if len(result.drafts) != 4 or any(d.error for d in result.drafts):
        fail(f"expected 4 successful drafts, got {result.drafts}")
    ok(f"4 authors at 100ms each finished in {elapsed * 1000:.0f}ms (parallel)")

    # ── Step 2: bounded concurrency under the semaphore ─────────
    step(
        "2. semaphore caps in-flight calls "
        "(max_parallel=2, 6 total calls, peak in-flight must be <=2)"
    )
    # 3 authors × 2 reviewers = 3 author calls + 6 review calls = 9 total.
    # max_parallel=2 means at most 2 simultaneously in flight ACROSS phases.
    a_trackers = [ConcurrencyTracker(f"a{i}", 0.05) for i in range(3)]
    r_trackers = [ConcurrencyTracker(f"r{i}", 0.05) for i in range(2)]
    board = AgentBoard(
        authors={t.agent_id: t for t in a_trackers},
        reviewers={t.agent_id: t for t in r_trackers},
        advisor=good_advisor(),
        max_parallel=2,
    )
    await board.run("bounded test")

    # Compute peak in-flight: collect all (timestamp, +1/-1) events
    # across both phases and sweep.
    events: list[tuple[float, int]] = []
    for tracker in a_trackers + r_trackers:
        for ts, ev in tracker.events:
            events.append((ts, +1 if ev == "start" else -1))
    events.sort()
    peak, current = 0, 0
    for _ts, delta in events:
        current += delta
        peak = max(peak, current)
    if peak > 2:
        fail(
            f"semaphore breached: peak in-flight={peak}, max_parallel=2. "
            f"Authors+reviewers should share one semaphore."
        )
    if peak < 1:
        fail(f"no concurrency observed (peak={peak}); something didn't run")
    ok(f"peak in-flight = {peak} (within max_parallel=2)")

    # ── Step 3: ordering is deterministic ───────────────────────
    step("3. drafts sorted by author_id; reviews by (author_id, reviewer_id)")
    # Authors with delays in REVERSE order — z is fastest, a slowest.
    # Without explicit sort, completion order would be z,m,a.
    # Board MUST return them as a, m, z.
    board = AgentBoard(
        authors={
            "z_author": slow_author("z_author", 0.01),
            "m_author": slow_author("m_author", 0.05),
            "a_author": slow_author("a_author", 0.1),
        },
        reviewers={
            "z_rev": scoring_reviewer("z_rev", 5, 0.01),
            "a_rev": scoring_reviewer("a_rev", 9, 0.01),
        },
        advisor=good_advisor(),
        max_parallel=8,
    )
    result = await board.run("ordering test")
    draft_ids = [d.author_id for d in result.drafts]
    if draft_ids != ["a_author", "m_author", "z_author"]:
        fail(f"drafts not sorted by author_id: {draft_ids}")
    review_keys = [(r.draft_author_id, r.reviewer_id) for r in result.reviews]
    expected_keys = [
        ("a_author", "a_rev"), ("a_author", "z_rev"),
        ("m_author", "a_rev"), ("m_author", "z_rev"),
        ("z_author", "a_rev"), ("z_author", "z_rev"),
    ]
    if review_keys != expected_keys:
        fail(f"reviews not sorted by (author_id, reviewer_id): {review_keys}")
    ok(f"drafts {draft_ids}; reviews {len(review_keys)} entries in lex order")

    # ── Step 4: NEGATIVE — author error doesn't sink the board ──
    step(
        "4. NEGATIVE: one author raising does NOT sink other drafts"
    )
    board = AgentBoard(
        authors={
            "good_a": slow_author("good_a", 0.01),
            "bad_a": failing_author("bad_a", RuntimeError, "deliberate"),
            "good_b": slow_author("good_b", 0.01),
        },
        reviewers={"r1": scoring_reviewer("r1", 7, 0.01)},
        advisor=good_advisor(),
        max_parallel=4,
    )
    result = await board.run("error isolation test")
    if len(result.drafts) != 3:
        fail(f"expected 3 drafts (incl. errored one), got {len(result.drafts)}")
    bad = next((d for d in result.drafts if d.author_id == "bad_a"), None)
    if bad is None or bad.error is None:
        fail(
            f"bad_a draft missing or error not captured: {bad!r}. "
            f"Author exceptions must surface as Draft.error, not propagate."
        )
    if "deliberate" not in (bad.error or ""):
        fail(f"error message lost: {bad.error!r}")
    good_ids = [d.author_id for d in result.drafts if d.error is None]
    if sorted(good_ids) != ["good_a", "good_b"]:
        fail(f"sibling authors lost: {good_ids}")
    if "bad_a" not in result.failed_authors:
        fail(f"failed_authors not surfaced: {result.failed_authors}")
    ok(
        f"bad_a captured as errored Draft; "
        f"siblings {good_ids} survived; failed_authors={result.failed_authors}"
    )

    # ── Step 5: NEGATIVE — reviewer error doesn't sink the board ─
    step(
        "5. NEGATIVE: one reviewer raising does NOT sink other reviews"
    )
    board = AgentBoard(
        authors={"a1": slow_author("a1", 0.01)},
        reviewers={
            "good_rev": scoring_reviewer("good_rev", 8, 0.01),
            "bad_rev": failing_reviewer("bad_rev"),
            "other_rev": scoring_reviewer("other_rev", 6, 0.01),
        },
        advisor=good_advisor(),
        max_parallel=4,
    )
    result = await board.run("reviewer error isolation")
    if len(result.reviews) != 3:
        fail(f"expected 3 reviews (incl. errored), got {len(result.reviews)}")
    bad_review = next((r for r in result.reviews if r.reviewer_id == "bad_rev"), None)
    if bad_review is None or bad_review.error is None:
        fail(f"bad_rev review missing or error not captured: {bad_review!r}")
    good_reviews = [r for r in result.reviews if r.error is None]
    if sorted(r.reviewer_id for r in good_reviews) != ["good_rev", "other_rev"]:
        fail(f"sibling reviewers lost: {[r.reviewer_id for r in good_reviews]}")
    # failed_reviews tuple shape: (draft_author_id, reviewer_id)
    if ("a1", "bad_rev") not in result.failed_reviews:
        fail(f"failed_reviews not surfaced: {result.failed_reviews}")
    ok(
        f"bad_rev errored cleanly; "
        f"siblings {[r.reviewer_id for r in good_reviews]} survived"
    )

    # ── Step 6: NEGATIVE — errored drafts skipped by reviewers ──
    step(
        "6. NEGATIVE: reviewers are NOT invoked for errored drafts "
        "(would mask author failure + burn LLM cost)"
    )
    counter = CountingReviewer("counter", 7)
    board = AgentBoard(
        authors={
            "ok_a": slow_author("ok_a", 0.01),
            "fail_a": failing_author("fail_a", RuntimeError, "skip me"),
        },
        reviewers={"counter": counter},
        advisor=good_advisor(),
        max_parallel=4,
    )
    result = await board.run("review-skip test")
    if len(counter.invocations) != 1:
        fail(
            f"reviewer invoked {len(counter.invocations)} times, "
            f"expected exactly 1 (only ok_a). Reviewing the errored "
            f"draft masks the author failure and wastes LLM cost."
        )
    # The reviewer's prompt should reference ok_a's draft text, not empty.
    if "ok_a" not in counter.invocations[0]:
        fail(
            f"reviewer prompt didn't include ok_a's draft text: "
            f"{counter.invocations[0][:80]!r}"
        )
    # The skipped review record must still exist with error set.
    skipped = [r for r in result.reviews if r.draft_author_id == "fail_a"]
    if not skipped:
        fail("skipped review record absent — board lost trace of fail_a×counter")
    if skipped[0].error is None or "upstream_author_error" not in skipped[0].error:
        fail(
            f"skipped review error not tagged 'upstream_author_error': "
            f"{skipped[0].error!r}"
        )
    ok(
        f"reviewer invoked exactly once (only ok_a); "
        f"fail_a×counter recorded as upstream_author_error"
    )

    # ── Step 7: NEGATIVE — advisor failure → fallback to top draft ─
    step(
        "7. NEGATIVE: advisor failure → fallback to highest-scored "
        "draft (not empty result)"
    )

    # Three authors, three different reviewer scores. Author 'middle'
    # should win because its reviewer score (9) is the highest.
    async def author_a(prompt: str) -> str:
        await asyncio.sleep(0.01)
        return "draft-low"

    async def author_b(prompt: str) -> str:
        await asyncio.sleep(0.01)
        return "draft-MIDDLE-WINNER"

    async def author_c(prompt: str) -> str:
        await asyncio.sleep(0.01)
        return "draft-mid"

    # Use a single reviewer that returns scores keyed off the draft text
    async def discriminating_reviewer(prompt: str) -> str:
        if "MIDDLE-WINNER" in prompt:
            return "best one\nSCORE: 9"
        if "draft-low" in prompt:
            return "worst\nSCORE: 2"
        return "ok\nSCORE: 5"

    board = AgentBoard(
        authors={
            "a_low": make_agent(author_a),
            "b_mid_winner": make_agent(author_b),
            "c_mid": make_agent(author_c),
        },
        reviewers={"r1": make_agent(discriminating_reviewer)},
        advisor=failing_advisor(),
        max_parallel=4,
    )
    result = await board.run("advisor failure test")
    if result.error is None or "advisor crashed" not in result.error:
        fail(
            f"BoardResult.error should capture advisor exception: "
            f"{result.error!r}"
        )
    if not result.final_advice:
        fail("final_advice empty — fallback should produce SOMETHING")
    if "MIDDLE-WINNER" not in result.final_advice:
        fail(
            f"fallback didn't pick highest-scored draft "
            f"(b_mid_winner@9). Got: {result.final_advice[:120]!r}"
        )
    if "advisor failed" not in result.final_advice.lower():
        fail(
            f"fallback advice didn't tag itself as degraded: "
            f"{result.final_advice[:120]!r}"
        )
    ok(
        f"advisor crash captured in BoardResult.error; "
        f"fallback returned 'b_mid_winner' (score 9)"
    )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 AGENT-BOARD STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (4 negative assertions: 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    asyncio.run(main())
