"""
AgentBoard — multi-agent task / review / advise pattern with bounded
parallel execution.

Three roles:

* **Author** — completes the task; produces a Draft.
* **Reviewer** — reviews each Draft; produces a Review with a score
  and a critique. Multiple reviewers per draft, all running in
  parallel.
* **Advisor** — single agent that synthesizes the drafts + reviews
  into a final Advice. Picks the strongest draft, weighting by
  reviewer score, and surfaces dissent if reviewers disagreed.

Execution shape:

    task
      → [N authors in parallel]                     → drafts
      → [for each draft, K reviewers in parallel]   → reviews
      → [single advisor on (drafts, reviews)]       → final advice

Parallelism contracts:

* **Bounded concurrency**: a single ``asyncio.Semaphore`` caps the
  total in-flight calls (authors + reviewers combined), so a large
  N×K cross-product doesn't flood the LLM provider.
* **Per-task error isolation**: a single author or reviewer raising
  does NOT sink the board — the failure is captured on the
  respective Draft / Review object as an ``error`` field, and
  downstream phases skip that record.
* **Ordering preserved**: Drafts are sorted by ``author_id`` and
  Reviews by ``(draft_author_id, reviewer_id)`` BEFORE consumption,
  so the advisor sees a deterministic input regardless of which
  task happened to complete first. Reproducibility matters for
  audit trails.
* **Context propagated**: each parallel task inherits the OTel
  context from the call site via Python's contextvars, so baggage
  (tenant_id, user_id, request_id) flows automatically into every
  agent's outbound calls. No explicit plumbing needed.

Composes with:

* ``mcp/server_common.setup_server_otel`` — propagator wired
  globally, so each agent's outbound httpx call carries baggage to
  whatever LLM endpoint it hits.
* ``libs/py/documind_core/middleware.BaggageContextMiddleware`` —
  the upstream request's tenant_id is already in baggage by the
  time the board is invoked.
* ``services/governance-svc/migrations/audit_log_partitioned`` —
  the BoardResult is the audit-row payload for "AI agent committee
  decision".

The Agent type is a duck-typed Protocol so callers plug in any
async-callable. Production wiring would back the agents with
distinct LLM clients, prompts, or even toolsets.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


@runtime_checkable
class Agent(Protocol):
    """Duck-typed agent. Any async callable that takes a prompt returns text."""

    async def __call__(self, prompt: str) -> str:  # pragma: no cover — Protocol
        ...


@dataclass(frozen=True)
class Draft:
    """One author's output. ``error`` non-None means this author failed —
    downstream phases (reviewers, advisor) skip the draft but the record
    survives for audit."""

    author_id: str
    text: str
    duration_s: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class Review:
    """One reviewer's critique of one draft.

    ``score`` is an optional 0-10 rating the reviewer extracts from its
    own response. The advisor uses scores to weight drafts when
    synthesizing. ``error`` non-None means this review failed —
    other reviews of the same draft are still valid.
    """

    reviewer_id: str
    draft_author_id: str
    critique: str
    score: float | None = None
    error: str | None = None


@dataclass
class BoardResult:
    """Final output of one board run. Captures all intermediate state for
    audit + reproducibility — drafts, reviews, the advisor's final
    advice, and timing."""

    task: str
    drafts: list[Draft]
    reviews: list[Review]
    final_advice: str
    duration_s: float = 0.0
    advisor_id: str = "advisor"
    error: str | None = None
    # Convenience: surfaces which authors / reviews errored out so audit
    # consumers don't re-derive from drafts/reviews.
    failed_authors: list[str] = field(default_factory=list)
    failed_reviews: list[tuple[str, str]] = field(default_factory=list)


class AgentBoard:
    """Multi-agent task / review / advise pattern.

    Construct once with the agents + concurrency bound; call
    :meth:`run` once per task. The board is reusable across many
    tasks — agents are stateless from its perspective.

    Args:
        authors: ``{author_id: Agent}``. The board calls every author
            for every task; ordering of the resulting drafts list is
            by ``author_id`` (sorted), NOT completion order.
        reviewers: ``{reviewer_id: Agent}``. Each reviewer critiques
            each draft, producing N×K reviews total.
        advisor: A single agent that synthesizes. Receives the drafts
            and reviews via a structured prompt; returns the final
            advice text.
        max_parallel: Cap on simultaneously in-flight LLM calls
            across authors + reviewers (advisor is sequential after).
            Default 4 — high enough to amortize latency, low enough
            to not flood a typical LLM provider's per-tenant rate
            limit. Tune based on your provider's tokens-per-minute
            quota.
        review_prompt_template: Format string with placeholders
            ``{draft_text}`` and ``{task}``. The reviewer agent is
            called with this rendered prompt. Override to customize
            the critique format (e.g. "Output: {{score: 0-10,
            critique: ...}}" if you need structured scores).
        advisor_prompt_template: Format string with placeholders
            ``{task}``, ``{drafts_block}``, ``{reviews_block}``.
    """

    DEFAULT_REVIEW_PROMPT = (
        "Review the following draft answer to the task.\n\n"
        "Task: {task}\n\n"
        "Draft:\n{draft_text}\n\n"
        "Provide a critique. End with a line "
        "'SCORE: <integer 0-10>' indicating how well this draft "
        "addresses the task."
    )

    DEFAULT_ADVISOR_PROMPT = (
        "You are the advisor on a multi-agent board. The team produced "
        "the following drafts in response to the task; each draft was "
        "reviewed by multiple reviewers. Synthesize a final answer "
        "that incorporates the strongest points from each draft, "
        "addresses the reviewers' concerns, and surfaces any "
        "unresolved disagreement.\n\n"
        "Task: {task}\n\n"
        "{drafts_block}\n\n"
        "{reviews_block}\n\n"
        "Final answer:"
    )

    def __init__(
        self,
        *,
        authors: dict[str, Agent],
        reviewers: dict[str, Agent],
        advisor: Agent,
        advisor_id: str = "advisor",
        max_parallel: int = 4,
        review_prompt_template: str = DEFAULT_REVIEW_PROMPT,
        advisor_prompt_template: str = DEFAULT_ADVISOR_PROMPT,
    ) -> None:
        if not authors:
            raise ValueError("authors must be non-empty (at least 1 author)")
        if not reviewers:
            raise ValueError("reviewers must be non-empty (at least 1 reviewer)")
        if max_parallel < 1:
            raise ValueError(f"max_parallel must be >= 1, got {max_parallel}")
        self._authors = dict(authors)
        self._reviewers = dict(reviewers)
        self._advisor = advisor
        self._advisor_id = advisor_id
        self._max_parallel = max_parallel
        self._review_prompt = review_prompt_template
        self._advisor_prompt = advisor_prompt_template

    async def run(self, task: str) -> BoardResult:
        """Run one board cycle: draft → review → advise. Returns a
        ``BoardResult`` with all intermediate state for audit."""
        t_start = time.monotonic()
        # Single semaphore shared across the two parallel phases, so
        # the cap applies to the union of in-flight LLM calls. Without
        # one shared semaphore a 4-author × 4-reviewer board would
        # fire 16 concurrent calls while individual phase caps would
        # both report "in bounds".
        sem = asyncio.Semaphore(self._max_parallel)

        # ── Phase 1 — authors draft in parallel ────────────────────
        drafts = await self._authors_phase(task, sem)

        # ── Phase 2 — reviewers critique each draft, all in parallel
        reviews = await self._reviews_phase(task, drafts, sem)

        # ── Phase 3 — advisor synthesizes (single sequential call) ─
        advice, advisor_err = await self._advisor_phase(task, drafts, reviews)

        duration = time.monotonic() - t_start
        failed_authors = [d.author_id for d in drafts if d.error is not None]
        failed_reviews = [
            (r.draft_author_id, r.reviewer_id) for r in reviews if r.error is not None
        ]

        return BoardResult(
            task=task,
            drafts=drafts,
            reviews=reviews,
            final_advice=advice,
            duration_s=duration,
            advisor_id=self._advisor_id,
            error=advisor_err,
            failed_authors=failed_authors,
            failed_reviews=failed_reviews,
        )

    # ── Internal phases ───────────────────────────────────────────
    async def _authors_phase(
        self, task: str, sem: asyncio.Semaphore,
    ) -> list[Draft]:
        async def one(author_id: str, agent: Agent) -> Draft:
            t0 = time.monotonic()
            async with sem:
                try:
                    text = await agent(task)
                    return Draft(
                        author_id=author_id,
                        text=text,
                        duration_s=time.monotonic() - t0,
                    )
                except Exception as exc:  # noqa: BLE001 — error isolation
                    log.warning(
                        "agent_board_author_failed author=%s err=%s",
                        author_id, exc,
                    )
                    return Draft(
                        author_id=author_id,
                        text="",
                        duration_s=time.monotonic() - t0,
                        error=f"{type(exc).__name__}: {exc}",
                    )

        results = await asyncio.gather(*[
            one(aid, agent) for aid, agent in self._authors.items()
        ])
        # Sort by author_id for deterministic downstream consumption.
        # asyncio.gather preserves the input order in its return value
        # ALREADY, but the dict iteration order in Python 3.7+ is
        # insertion order — relying on that across versions is
        # fragile. Explicit sort = explicit contract.
        return sorted(results, key=lambda d: d.author_id)

    async def _reviews_phase(
        self, task: str, drafts: list[Draft], sem: asyncio.Semaphore,
    ) -> list[Review]:
        async def review_one(
            draft: Draft, reviewer_id: str, reviewer: Agent,
        ) -> Review:
            # Skip drafts that errored — reviewing an empty string is
            # noise + would mask the actual upstream failure.
            if draft.error is not None:
                return Review(
                    reviewer_id=reviewer_id,
                    draft_author_id=draft.author_id,
                    critique="(skipped — author errored)",
                    error=f"upstream_author_error: {draft.error}",
                )
            prompt = self._review_prompt.format(
                task=task, draft_text=draft.text,
            )
            async with sem:
                try:
                    critique = await reviewer(prompt)
                    score = self._extract_score(critique)
                    return Review(
                        reviewer_id=reviewer_id,
                        draft_author_id=draft.author_id,
                        critique=critique,
                        score=score,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "agent_board_review_failed reviewer=%s draft=%s err=%s",
                        reviewer_id, draft.author_id, exc,
                    )
                    return Review(
                        reviewer_id=reviewer_id,
                        draft_author_id=draft.author_id,
                        critique="",
                        error=f"{type(exc).__name__}: {exc}",
                    )

        # Build the N×K task list. Each draft × each reviewer = one
        # gather entry. The shared semaphore caps total parallelism.
        tasks = [
            review_one(d, rid, r)
            for d in drafts
            for rid, r in self._reviewers.items()
        ]
        if not tasks:
            return []
        results = await asyncio.gather(*tasks)
        # Stable sort by (author_id, reviewer_id) — deterministic for
        # the advisor + audit consumers.
        return sorted(
            results,
            key=lambda r: (r.draft_author_id, r.reviewer_id),
        )

    async def _advisor_phase(
        self,
        task: str,
        drafts: list[Draft],
        reviews: list[Review],
    ) -> tuple[str, str | None]:
        prompt = self._advisor_prompt.format(
            task=task,
            drafts_block=self._format_drafts(drafts),
            reviews_block=self._format_reviews(reviews),
        )
        try:
            advice = await self._advisor(prompt)
            return advice, None
        except Exception as exc:  # noqa: BLE001
            log.error("agent_board_advisor_failed err=%s", exc)
            # Fall back to the highest-scored non-errored draft so the
            # board still produces SOMETHING. Operations can detect
            # the fallback via BoardResult.error.
            fallback = self._fallback_advice(drafts, reviews)
            return fallback, f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _format_drafts(drafts: list[Draft]) -> str:
        lines = ["=== DRAFTS ==="]
        for d in drafts:
            if d.error is not None:
                lines.append(f"-- {d.author_id} (ERROR: {d.error}) --")
            else:
                lines.append(f"-- {d.author_id} --\n{d.text}")
        return "\n".join(lines)

    @staticmethod
    def _format_reviews(reviews: list[Review]) -> str:
        lines = ["=== REVIEWS ==="]
        for r in reviews:
            if r.error is not None:
                lines.append(
                    f"-- {r.reviewer_id} on {r.draft_author_id} "
                    f"(ERROR: {r.error}) --"
                )
            else:
                score = f"score={r.score}" if r.score is not None else "no-score"
                lines.append(
                    f"-- {r.reviewer_id} on {r.draft_author_id} ({score}) --\n"
                    f"{r.critique}"
                )
        return "\n".join(lines)

    @staticmethod
    def _extract_score(critique: str) -> float | None:
        """Extract 'SCORE: <n>' from a reviewer's critique. Returns
        None if not found — most reviewer agents will include it
        because the default prompt asks for it, but no guarantee."""
        import re
        m = re.search(r"SCORE\s*:\s*(\d+(?:\.\d+)?)", critique, re.IGNORECASE)
        if not m:
            return None
        try:
            score = float(m.group(1))
            return max(0.0, min(10.0, score))
        except ValueError:
            return None

    @staticmethod
    def _fallback_advice(
        drafts: list[Draft], reviews: list[Review],
    ) -> str:
        """When the advisor fails, return the highest-mean-scored
        non-errored draft. Better than empty string; signals to the
        operator (via BoardResult.error) that this is degraded."""
        # Mean score per author across reviewers
        scores: dict[str, list[float]] = {}
        for r in reviews:
            if r.error is None and r.score is not None:
                scores.setdefault(r.draft_author_id, []).append(r.score)
        ranked = [
            (aid, sum(s) / len(s)) for aid, s in scores.items() if s
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        good_drafts = {d.author_id: d for d in drafts if d.error is None}
        for aid, _score in ranked:
            if aid in good_drafts:
                return (
                    f"(advisor failed; falling back to highest-scored draft "
                    f"from {aid})\n\n{good_drafts[aid].text}"
                )
        # No scored drafts; return the first non-errored draft
        for d in drafts:
            if d.error is None:
                return f"(advisor + scoring both failed)\n\n{d.text}"
        return "(advisor failed; all drafts also errored — see BoardResult.failed_authors)"


# ─────────────────────────────────────────────────────────────────
# Convenience: build an agent from a callable
# ─────────────────────────────────────────────────────────────────
def make_agent(fn: Callable[[str], Awaitable[str]]) -> Agent:
    """Wrap any async callable as an Agent. Useful for tests + demos
    where the agent is a one-off lambda."""
    class _CallableAgent:
        async def __call__(self, prompt: str) -> str:
            return await fn(prompt)
    return _CallableAgent()
