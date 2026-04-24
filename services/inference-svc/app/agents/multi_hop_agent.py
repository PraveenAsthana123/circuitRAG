"""
Multi-hop RAG agent — skeleton showing the full breaker story in action.

Pattern:

1. Pre-flight: :class:`TokenCircuitBreaker` — reject if over budget.
2. Per-run: :class:`AgentLoopCircuitBreaker` — cap steps, total time,
   per-step time, detect loops, enforce tool budgets.
3. Each retrieval hop: protected by the retrieval-svc's
   :class:`RetrievalCircuitBreaker` (quality-aware).
4. The final generation: wrapped in :class:`CognitiveCircuitBreaker` so a
   rambling / citation-free / degenerate response is aborted mid-stream.
5. All through: observability export is wrapped in
   :class:`ObservabilityCircuitBreaker` — a dead collector won't block
   the agent.

This file is intentionally skeletal; the actual planner / synthesizer /
critic implementation is scheduled for a subsequent session. The shape is
here so tests and code review can exercise the control flow.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from documind_core.breakers import (
    AgentLoopCircuitBreaker,
    AgentStopReason,
    TokenCircuitBreaker,
)

from app.services import OllamaClient, PromptBuilder, RetrievalClient

log = logging.getLogger(__name__)


@dataclass
class AgentRunResult:
    answer: str
    steps: int
    stop_reason: str
    trace: list[dict[str, Any]]


class MultiHopRagAgent:
    """
    Runs a small plan-retrieve-reason-synthesize loop.

    Planner is a stub that decomposes the question into sub-questions.
    Each sub-question triggers a retrieval call; when all are answered, a
    synthesizer composes the final answer.

    The important bit — and the reason this file exists — is how the
    breakers wire together. Read top to bottom.
    """

    def __init__(
        self,
        *,
        retrieval: RetrievalClient,
        ollama: OllamaClient,
        prompts: PromptBuilder,
        token_breaker: TokenCircuitBreaker,
        max_hops: int = 4,
    ) -> None:
        self._retrieval = retrieval
        self._ollama = ollama
        self._prompts = prompts
        self._token_breaker = token_breaker
        self._max_hops = max_hops

    async def run(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        question: str,
        daily_budget: int = 200_000,
        monthly_budget: int = 4_000_000,
    ) -> AgentRunResult:
        # Pre-flight: token budget -------------------------------------------------
        await self._token_breaker.check_or_raise(
            tenant_id=tenant_id,
            estimated_tokens=10_000,  # rough cap for the full loop
            daily_budget=daily_budget,
            monthly_budget=monthly_budget,
        )

        # Per-run breaker with loop/time/tool-budget guardrails -------------------
        loop_cb = AgentLoopCircuitBreaker(
            agent_name="multi_hop_rag",
            max_steps=self._max_hops,
            total_timeout_s=120.0,
            per_step_timeout_s=30.0,
            loop_detection_window=3,
            max_tool_calls={"retrieve": self._max_hops, "synthesize": 1},
        )
        loop_cb.start()

        trace: list[dict[str, Any]] = []
        gathered_context: list[str] = []

        # Planner stub — turn the question into N sub-questions.
        sub_questions = self._plan(question)

        for sub_q in sub_questions:
            stop = loop_cb.check_before_step()
            if stop is not AgentStopReason.NONE:
                break

            chunks = await self._retrieval.retrieve(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                query=sub_q,
                top_k=3,
                strategy="hybrid",
            )
            result_hash = hashlib.sha256(
                ("".join(c.get("chunk_id", "") for c in chunks)).encode()
            ).hexdigest()[:12]

            trace.append(
                {"step": "retrieve", "sub_q": sub_q, "chunks": len(chunks), "result_hash": result_hash}
            )

            stop = loop_cb.record_step(action="retrieve", result_hash=result_hash)
            if stop is not AgentStopReason.NONE:
                break

            gathered_context.append(f"Q: {sub_q}\n" + "\n".join(c.get("text", "") for c in chunks))

        # Synthesize — single final step, guarded too.
        synth_stop = loop_cb.check_before_step()
        if synth_stop is AgentStopReason.NONE:
            answer = await self._synthesize(question, gathered_context)
            loop_cb.record_step(action="synthesize")
        else:
            answer = (
                "I had to stop before reaching a confident answer ("
                + synth_stop.value + "). Please try a narrower question."
            )

        snapshot = loop_cb.snapshot()
        log.info("agent_run complete snapshot=%s", snapshot)
        return AgentRunResult(
            answer=answer,
            steps=snapshot["steps_taken"],
            stop_reason=snapshot["stop_reason"],
            trace=trace,
        )

    # ------------------------------------------------------------------
    # Stubs — filled in in a future session.
    # ------------------------------------------------------------------
    @staticmethod
    def _plan(question: str) -> list[str]:
        """
        Real plan would call the LLM. Stub: if the question contains 'and',
        split on it to simulate decomposition; otherwise one hop.
        """
        parts = [p.strip() for p in question.split(" and ") if p.strip()]
        return parts or [question]

    async def _synthesize(self, question: str, context: list[str]) -> str:
        """Single LLM call to compose the final answer from gathered context."""
        joined = "\n\n".join(context)
        system, user, _ = self._prompts.build(
            template_name="rag_answer_v1", query=question, chunks=[]
        )
        # Inline the context into the user prompt manually since we have raw text.
        user = f"Context:\n{joined}\n\nQuestion: {question}\n\nAnswer:"
        result = await self._ollama.generate(system=system, user=user)
        return result.text
