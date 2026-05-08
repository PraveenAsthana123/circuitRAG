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

from documind_core.ai_governance import (
    AdversarialInputFilter,
    AIExplainer,
    Explanation,
    InterpretabilityTrace,
    PIIScanner,
    PromptInjectionDetector,
    ResponsibleAIChecker,
)
from documind_core.breakers import (
    CitationDeadlineSignal,
    CognitiveCircuitBreaker,
    CognitiveInterrupt,
    ForbiddenPatternSignal,
    LogprobConfidenceSignal,
    RepetitionSignal,
    TokenCircuitBreaker,
)
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
            max_tokens_per_request=32_000,
            warn_percent=0.8,
        )
        self._default_daily = default_daily_token_budget
        self._default_monthly = default_monthly_token_budget

        # AI-governance primitives. Cheap, instantiated once, reused per-request.
        self._injection_detector = PromptInjectionDetector()
        self._adversarial = AdversarialInputFilter(max_chars=10_000)
        self._pii = PIIScanner()
        self._responsible = ResponsibleAIChecker()

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
        trace = InterpretabilityTrace()

        # Stage-2 Langfuse trace wire (per scripts/langfuse_tracer.py +
        # docs/architecture/six-plane-audit-2026-05-04.md). Per the
        # OFFLINE-SAFE contract on the Stage-1 adapter, this is a fire-
        # and-forget metadata emission — never blocks the request path,
        # never raises. We emit the top-level trace event up-front so
        # the Langfuse dashboard sees the request even if the rest of
        # ask() takes a long time. Stage-3 will add per-step spans
        # (retrieve / pii / rerank / generate) inside this same trace.
        # Per §38 (audit) + §47 (fail-safe) + §48 (explainability).
        import sys as _sys  # noqa: PLC0415
        _sys.path.insert(0, "/mnt/deepa/rag/scripts")
        try:
            from langfuse_tracer import _get_client as _lf_client
            from langfuse_tracer import is_available as _lf_avail  # noqa: PLC0415
            if _lf_avail():
                _client = _lf_client()
                if _client is not None:
                    _client.trace(
                        id=correlation_id,
                        name="rag.ask",
                        user_id=None,
                        input={"query": request.query[:500],
                               "top_k": request.top_k,
                               "model": request.model},
                        metadata={
                            "tenant_id": tenant_id,
                            "strategy": request.strategy,
                        },
                    )
        except Exception:  # noqa: S110 — intentional fail-safe
            # Offline-safe: NEVER block the request path on observability
            pass  # noqa: S110 — intentional fail-safe (see comment above)

        # -1. Adversarial input heuristics — reject early for length / DoS /
        #     non-printable / URL-burst patterns.
        with trace.step("adversarial_filter") as st:
            st.input(f"query[{len(request.query)}c]")
            self._adversarial.inspect_or_raise(request.query)
            st.output("clean")

        # -0.55. Rebuff Stage-2 wire (per libs/py/documind_core/rebuff_detector.py).
        # Defense-in-depth complement to the regex injection_detector below.
        # When REBUFF_ENABLED=1 + token set, classify() runs heuristic + LLM
        # + vector-DB layers; result lands in trace + audit row but does NOT
        # block on its own (regex layer below is still the gate). Promotion
        # to a blocking signal is a future Stage-3 iteration once the false-
        # positive baseline is calibrated.
        # Fail-OPEN per §47.6 — detector errors NEVER block the request.
        # Per §47.6 (A11 Prompt Injection), §48 (guardrails_triggered audit).
        with trace.step("rebuff_check") as st:
            st.input(f"query[{len(request.query)}c]")
            try:
                import sys as _sys_rb  # noqa: PLC0415
                _sys_rb.path.insert(0, "/mnt/deepa/rag/libs/py")
                from documind_core.rebuff_detector import classify as _rb_classify  # noqa: PLC0415
                from documind_core.rebuff_detector import is_available as _rb_avail  # noqa: PLC0415
                if _rb_avail():
                    _rb = _rb_classify(request.query)
                    st.output(
                        f"is_attack={_rb.is_attack} score={_rb.score:.3f}"
                    )
                    st.meta(
                        rebuff_is_attack=_rb.is_attack,
                        rebuff_score=_rb.score,
                        rebuff_layers=_rb.detection_layers,
                    )
                else:
                    st.output("rebuff_disabled")
            except Exception as _exc_rb:  # noqa: BLE001 — fail-OPEN per §47.6
                st.output(f"rebuff_error: {_exc_rb!s}"[:200])

        # -0.5. Prompt-injection scan on the user's query.
        with trace.step("injection_scan") as st:
            st.input(f"query[{len(request.query)}c]")
            findings = self._injection_detector.scan_or_raise(request.query)
            st.output(f"{len(findings)} suspicious finding(s)")
            st.meta(findings=[f.pattern_id for f in findings])

        # 0. Token budget pre-flight — reject BEFORE we spend on retrieval.
        estimated = len(request.query.split()) * 2 + 2000 + self._max_new_tokens
        with trace.step("token_budget") as st:
            st.input(f"estimated_tokens={estimated}")
            await self._token_breaker.check_or_raise(
                tenant_id=tenant_id,
                estimated_tokens=estimated,
                daily_budget=self._default_daily,
                monthly_budget=self._default_monthly,
            )
            st.output("within_budget")

        # 0.5. Stage-2 best-config defaults (per scripts/best_config_loader.py
        #      + CLAUDE.md §47 + §56). When BEST_CONFIG_LOADER_ENABLED=1 AND
        #      the AskRequest didn't EXPLICITLY set top_k, fall back to the
        #      empirically-best top_k from .loop/best_config.json. Pydantic's
        #      model_fields_set distinguishes "caller omitted field" from
        #      "caller passed the default value" — only the FORMER triggers
        #      the override (caller intent wins).
        #      Per §47 fail-safe: loader errors NEVER block the request path.
        effective_top_k = request.top_k
        with trace.step("best_config_defaults") as st:
            st.input(f"request_top_k={request.top_k} fields_set={sorted(request.model_fields_set)}")
            try:
                import os as _os  # noqa: PLC0415
                if _os.getenv("BEST_CONFIG_LOADER_ENABLED", "").strip() == "1":
                    import sys as _sys  # noqa: PLC0415
                    _sys.path.insert(0, "/mnt/deepa/rag/scripts")
                    from best_config_loader import (  # noqa: PLC0415
                        get_default_top_k as _bc_top_k,
                    )
                    from best_config_loader import (
                        is_available as _bc_avail,
                    )
                    if _bc_avail() and "top_k" not in request.model_fields_set:
                        effective_top_k = _bc_top_k()
                        st.output(f"override top_k={effective_top_k}")
                        st.meta(source="best_config")
                    else:
                        st.output(f"keep request_top_k={request.top_k}")
                else:
                    st.output("disabled")
            except Exception as exc:
                # Offline-safe: NEVER block the request path
                st.output(f"loader_error_keep_request_top_k={request.top_k}")
                st.meta(error=str(exc)[:200])

        # 1. Retrieve
        chunks = await self._retrieval.retrieve(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            query=request.query,
            top_k=effective_top_k,
            strategy=request.strategy,
        )
        if not chunks:
            raise ExternalServiceError(
                "No chunks retrieved — is the corpus empty?",
                details={"tenant_id": tenant_id},
            )

        # Stage-3 PII redaction wire (per CLAUDE.md §39 + §43 + §48 +
        # docs/architecture/six-plane-audit-2026-05-04.md). Symmetric
        # to the ingestion-side wire (commit cd77b0c). When
        # PII_REDACTOR_ENABLED=1, redact PII from each retrieved chunk
        # BEFORE prompt assembly. This protects against PII that
        # entered the corpus before the ingestion-side wire was active
        # (legacy data) AND PII that the ingestion redactor missed
        # (defense in depth). The audit row goes to .loop/pii_audit.jsonl
        # with TYPE+POSITION only — NEVER raw PII (§48.4 invariant).
        # Default off: legacy callers see no behavior change.
        # Per §47 fail-safe: PII errors NEVER block the request path.
        import os as _os  # noqa: PLC0415
        if _os.getenv("PII_REDACTOR_ENABLED", "").strip() == "1":
            try:
                # Lazy import — saga-side hook lives in ingestion-svc; we
                # share the underlying scripts/pii_redactor.py adapter
                # directly to avoid cross-service path coupling.
                import sys as _sys  # noqa: PLC0415
                _sys.path.insert(0, "/mnt/deepa/rag/scripts")
                import pii_redactor as _pii  # noqa: PLC0415
                if _pii.is_available():
                    redacted_count = 0
                    for chunk in chunks:
                        text = chunk.get("text") if isinstance(chunk, dict) else getattr(chunk, "text", None)
                        if not text or not text.strip():
                            continue
                        clean, entities = _pii.redact(text)
                        if entities:
                            redacted_count += 1
                            if isinstance(chunk, dict):
                                chunk["text"] = clean
                            else:
                                chunk.text = clean
                    if redacted_count:
                        log.info(
                            "pii_redact_inference tenant=%s chunks_redacted=%d/%d",
                            tenant_id, redacted_count, len(chunks),
                        )
            except Exception as _exc:
                # Fail-safe: PII error must not block the request.
                log.warning("pii_redact_inference skipped: %s", _exc)

        # 2. Prompt — Stage-7 GEPA canary routing + build
        # Per docs/architecture/gepa-chain-status-and-stage6-blocker.md
        # + commit 4f7289e (select_canary_version helper). When
        # GEPA_CANARY_ENABLED=1 AND GEPA_CANARY_PERCENT > 0 AND a
        # gepa-aliased version exists for self._default_prompt, route
        # this tenant's request to the GEPA-tuned version based on
        # tenant-sticky hash. Default-deny: env unset → returns
        # self._default_prompt unchanged → behavior-preserving for
        # all existing callers.
        # Per §47 fail-safe + §48 explainability: trace step records
        # which version actually fired so operators can attribute
        # canary metrics post-hoc.
        with trace.step("prompt_canary_routing") as st:
            st.input(f"baseline={self._default_prompt} tenant={tenant_id[:12]}…")
            try:
                if hasattr(self._prompts, "select_canary_version"):
                    effective_template = self._prompts.select_canary_version(
                        template_name=self._default_prompt,
                        tenant_id=tenant_id,
                    )
                else:
                    # Builder lacks the helper (e.g. legacy in-code builder
                    # with no canary surface). Fall back to baseline.
                    effective_template = self._default_prompt
            except Exception as _exc:
                # §47 fail-safe: any error in the canary helper falls
                # back to baseline. NEVER blocks the request path.
                effective_template = self._default_prompt
                st.meta(canary_error=str(_exc)[:200])
            cohort = (
                "gepa" if effective_template != self._default_prompt
                else "baseline"
            )
            st.output(f"effective={effective_template} cohort={cohort}")
            st.meta(cohort=cohort, baseline=self._default_prompt,
                    effective=effective_template)

        system, user, citation_map = self._prompts.build(
            template_name=effective_template,
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
                ccb.on_tokens(delta)  # may raise CognitiveInterrupt
            answer_text = "".join(collected)
            # Token counts aren't in the streaming API; estimate for FinOps.
            gen_tokens_prompt = len(user.split()) + len(system.split())
            gen_tokens_completion = len(answer_text.split())
            gen_model = request.model or self._ollama.model
        except CognitiveInterrupt as exc:
            ccb_snapshot = ccb.snapshot()
            log.warning(
                "cognitive_interrupt reasons=%s partial_len=%d tenant=%s",
                exc.reasons,
                len(exc.partial),
                tenant_id,
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
        guard = self._guardrails.check(answer=gen.text, citation_map=citation_map, retrieval_scores=scores)

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
            tenant_id,
            guard.passed,
            guard.confidence,
            gen.tokens_prompt,
            gen.tokens_completion,
        )

        # PII scan + responsibility lens run on the FINAL answer.
        pii_findings = self._pii.scan(gen.text)
        fairness_signals = self._responsible.check(
            question=request.query,
            answer=gen.text,
            has_citations=bool(returned_citations),
        )

        # Packaged explanation (powers the UI's "Why this answer" panel
        # and the HITL reviewer pane).
        explanation: Explanation = AIExplainer.build(
            question=request.query,
            answer=gen.text,
            retrieval_strategy=request.strategy,
            retrieved_chunks=chunks,
            prompt_version=self._default_prompt,
            model=gen.model,
            tokens_prompt=gen.tokens_prompt,
            tokens_completion=gen.tokens_completion,
            confidence=guard.confidence,
            guardrail_violations=guard.violations,
            cognitive_breaker_snapshot=ccb_snapshot or ccb.snapshot(),
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
                # New AI-governance sections
                "explanation": explanation.to_dict(),
                "interpretability_trace": trace.to_dict(),
                "pii_findings": [{"kind": f.kind, "excerpt": f.excerpt} for f in pii_findings],
                "fairness_signals": [
                    {"name": s.name, "score": s.score, "message": s.message} for s in fairness_signals
                ],
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
