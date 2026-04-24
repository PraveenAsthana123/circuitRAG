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
    ) -> None:
        self._retrieval = retrieval
        self._ollama = ollama
        self._prompts = prompts
        self._guardrails = guardrails
        self._default_prompt = default_prompt
        self._max_new_tokens = max_new_tokens
        self._temperature = temperature

    async def ask(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        request: AskRequest,
        include_debug: bool = False,
    ) -> AskResponse:
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

        # 3. Generate
        gen = await self._ollama.generate(
            system=system,
            user=user,
            temperature=self._temperature,
            max_new_tokens=self._max_new_tokens,
            model=request.model,
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
