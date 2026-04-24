"""
RagInferenceService — end-to-end glue for the read path.

Flow:

1. Retrieve top-K chunks via retrieval-svc.
2. Build a versioned prompt (system + user) from a template.
3. Call Ollama (wrapped in a circuit breaker).
4. Run guardrails over the response.
5. Assemble the response with citations + confidence + debug info.

Everything is logged with correlation + tenant IDs. FinOps gets token
counts via a Kafka event (elided here — see docs/design-areas/29-finops.md).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from documind_core.exceptions import ExternalServiceError
from documind_core.breakers import (
    CognitiveCircuitBreaker,
    CognitiveInterrupt,
    CitationDeadlineSignal,
    ForbiddenPatternSignal,
    LogprobConfidenceSignal,
    RepetitionSignal,
    TokenCircuitBreaker,
)

from app.schemas import AskRequest, AskResponse, Citation

from .guardrails import GuardrailChecker
from .ollama_client import OllamaClient
from .prompt_builder import PromptBuilder
from .retrieval_client import RetrievalClient

log = logging.getLogger(__name__)


class RagInferenceService:
    def __init__(
        self,
        *,
        retrieval: RetrievalClient,
        ollama: OllamaClient,
        prompts: PromptBuilder,
        guardrails: GuardrailChecker,
        default_prompt: str = "rag_answer_v1",
        max_new_tokens: int = 1024,
        temperature: float = 0.1,
        # Token budget breaker — pre-flight pass. If a tenant is over budget
        # we reject BEFORE paying for retrieval + LLM generation.
        token_breaker: TokenCircuitBreaker | None = None,
        # Default per-tenant budgets used when governance hasn't set them.
        # In production these come from finops.budgets.
        default_daily_token_budget: int = 200_000,
        default_monthly_token_budget: int = 4_000_000,
    ) -> None:
        self._retrieval = retrieval
        self._ollama = ollama
        self._prompts = prompts
        self._guardrails = guardrails
        self._default_prompt = default_prompt
        self._max_new_tokens = max_new_tokens
        self._temperature = temperature
        self._token_breaker = token_breaker or TokenCircuitBreaker(
            max_tokens_per_request=32_000, warn_percent=0.8,
        )
        self._default_daily = default_daily_token_budget
        self._default_monthly = default_monthly_token_budget

    # ------------------------------------------------------------------
    # Factory: build the CCB signal set for this tenant
    # ------------------------------------------------------------------
    @staticmethod
    def _build_ccb(*, forbidden_patterns: list[str] | None = None) -> CognitiveCircuitBreaker:
        """
        Default signal set for RAG answering:

        * Repetition — catch model degeneracy (loops).
        * CitationDeadline — if no [Source: ...] tag by ~400 tokens, we're
          hallucinating.
        * ForbiddenPattern — optional allow/deny regex list (tenant policy).
        * LogprobConfidence — best-effort; fires only if logprobs are wired.

        Calibration note: thresholds below are demo defaults. Production
        should backfill these per-tenant from eval regressions — a tenant
        whose corpus has fewer citations per paragraph may need a larger
        deadline, etc.
        """
        return CognitiveCircuitBreaker(
            signals=[
                RepetitionSignal(ngram=6, max_repeats=3),
                CitationDeadlineSignal(deadline_tokens=400, min_citations=1),
                ForbiddenPatternSignal(patterns=forbidden_patterns or []),
                LogprobConfidenceSignal(min_avg_logprob=-3.0, window=3),
            ],
            check_every_tokens=32,
            max_warnings_before_block=4,
        )

    async def ask(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        request: AskRequest,
        include_debug: bool = False,
    ) -> AskResponse:
        # 0. Token budget pre-flight — reject BEFORE we spend on retrieval.
        # Rough estimate: user query + retrieval context + completion budget.
        estimated = len(request.query.split()) * 2 + 2000 + self._max_new_tokens
        await self._token_breaker.check_or_raise(
            tenant_id=tenant_id,
            estimated_tokens=estimated,
            daily_budget=self._default_daily,
            monthly_budget=self._default_monthly,
        )

        # 1. Retrieve
        chunks = await self._retrieval.retrieve(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            query=request.query,
            top_k=request.top_k,
            strategy=request.strategy,
        )
        if not chunks:
            raise ExternalServiceError(
                "No chunks retrieved — is the corpus empty?",
                details={"tenant_id": tenant_id},
            )

        # 2. Prompt
        system, user, citation_map = self._prompts.build(
            template_name=self._default_prompt,
            query=request.query,
            chunks=chunks,
        )

        # 3. Generate with Cognitive Circuit Breaker active during streaming.
        # We pull the stream so the CCB can interrupt mid-flight. On interrupt,
        # we swap the model's partial output for a safe fallback — never
        # surface an aborted hallucination to the user.
        ccb = self._build_ccb()
        ccb.start()
        ccb_snapshot: dict | None = None

        try:
            collected: list[str] = []
            async for delta in self._ollama.stream(
                system=system,
                user=user,
                temperature=self._temperature,
                max_new_tokens=self._max_new_tokens,
                model=request.model,
            ):
                collected.append(delta)
                ccb.on_tokens(delta)   # may raise CognitiveInterrupt
            answer_text = "".join(collected)
            # Token counts aren't in the streaming API; estimate for FinOps.
            gen_tokens_prompt = len(user.split()) + len(system.split())
            gen_tokens_completion = len(answer_text.split())
            gen_model = request.model or self._ollama.model
        except CognitiveInterrupt as exc:
            ccb_snapshot = ccb.snapshot()
            log.warning(
                "cognitive_interrupt reasons=%s partial_len=%d tenant=%s",
                exc.reasons, len(exc.partial), tenant_id,
            )
            answer_text = (
                "I don't have enough confidence in the answer I was generating. "
                "The retrieved documents may not cover this topic well. "
                "Please rephrase your question or upload more relevant documents."
            )
            gen_tokens_prompt = len(user.split()) + len(system.split())
            gen_tokens_completion = len(answer_text.split())
            gen_model = request.model or self._ollama.model

        # Wrap the result in the same shape ollama.generate would return,
        # so downstream code stays identical regardless of CCB path.
        from dataclasses import dataclass as _dc

        @_dc
        class _GenResult:
            text: str
            tokens_prompt: int
            tokens_completion: int
            model: str
        gen = _GenResult(
            text=answer_text,
            tokens_prompt=gen_tokens_prompt,
            tokens_completion=gen_tokens_completion,
            model=gen_model,
        )

        # Feed the token breaker what we actually used.
        await self._token_breaker.record_usage(
            tenant_id=tenant_id,
            prompt_tokens=gen.tokens_prompt,
            completion_tokens=gen.tokens_completion,
        )

        # 4. Guardrails
        scores = [c.get("score", 0.0) for c in chunks]
        guard = self._guardrails.check(
            answer=gen.text, citation_map=citation_map, retrieval_scores=scores
        )

        # 5. Citations for response (only those the LLM actually cited OR
        #    the top 3 if the LLM elided them — pragmatic default)
        returned_citations: list[Citation] = []
        for c in citation_map[: max(3, len(citation_map))]:
            if c["label"] in gen.text or len(returned_citations) < 3:
                returned_citations.append(
                    Citation(
                        chunk_id=UUID(c["chunk_id"]) if isinstance(c["chunk_id"], str) else c["chunk_id"],
                        document_id=UUID(c["document_id"]) if isinstance(c["document_id"], str) else c["document_id"],
                        page_number=c["page_number"],
                        snippet=c["snippet"],
                    )
                )

        log.info(
            "inference_complete tenant=%s guardrails_passed=%s confidence=%.2f tokens=%d/%d",
            tenant_id, guard.passed, guard.confidence, gen.tokens_prompt, gen.tokens_completion,
        )

        debug: dict[str, Any] | None = None
        if include_debug:
            debug = {
                "retrieval_count": len(chunks),
                "retrieval_strategy": request.strategy,
                "retrieval_top_score": max(scores, default=0.0),
                "prompt_version": self._default_prompt,
                "guardrail_violations": guard.violations,
                "guardrail_details": guard.details,
                "cognitive_breaker": ccb_snapshot or ccb.snapshot(),
            }

        return AskResponse(
            answer=gen.text,
            citations=returned_citations,
            model=gen.model,
            prompt_version=self._default_prompt,
            tokens_prompt=gen.tokens_prompt,
            tokens_completion=gen.tokens_completion,
            confidence=guard.confidence,
            correlation_id=correlation_id,
            debug=debug,
        )
