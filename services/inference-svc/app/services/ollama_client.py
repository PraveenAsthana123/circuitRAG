"""
Ollama LLM client — wrapped in a circuit breaker.

Supports streaming (SSE) and non-streaming generation. Counts tokens in
the response for FinOps reporting.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from documind_core.circuit_breaker import CircuitBreaker
from documind_core.exceptions import ExternalServiceError

log = logging.getLogger(__name__)


# Prometheus token counter — closes the convergence-shortlist
# "token-cost metric" item (3× cited across rag-data-layers, AIOps,
# enterprise gap reviews). Two cardinality-bounded labels:
#   * ``model`` — finite set (one per configured model)
#   * ``kind`` ∈ {"prompt", "completion"}
# Tenant intentionally NOT a label — `inference_complete` log lines
# carry tenant for forensics; per-tenant cost rollups should be
# computed offline from logs (Grafana Loki) or via a separate
# tenant-bucket gauge if cost-by-tenant becomes a hot need.
#
# PromQL recipes
#   rate(documind_inference_tokens_total[5m])
#     → tokens/sec, fleet-wide
#   sum by(model) (rate(documind_inference_tokens_total[5m]))
#     → spend distribution by model
#   sum by(kind) (rate(documind_inference_tokens_total[5m]))
#     → input vs output token-rate (proxy for cost shape)
try:
    from prometheus_client import Counter as _PromCounter

    _inference_tokens_total = _PromCounter(
        "documind_inference_tokens_total",
        "LLM tokens consumed (input + output) by model and kind. "
        "Bounded cardinality: model ∈ configured set, kind ∈ "
        "{prompt, completion}.",
        labelnames=["model", "kind"],
    )
except ImportError:  # pragma: no cover — prometheus_client is optional
    _inference_tokens_total = None


def _record_tokens(*, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Bump the token counter; no-op if prometheus_client missing."""
    if _inference_tokens_total is None:
        return
    if prompt_tokens > 0:
        _inference_tokens_total.labels(model=model, kind="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        _inference_tokens_total.labels(model=model, kind="completion").inc(completion_tokens)


@dataclass
class GenerationResult:
    text: str
    tokens_prompt: int
    tokens_completion: int
    model: str


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._model = model
        self._breaker = CircuitBreaker(
            "ollama-llm",
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=(httpx.HTTPError, ExternalServiceError),
        )

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.1,
        max_new_tokens: int = 1024,
        model: str | None = None,
    ) -> GenerationResult:
        async def _call() -> GenerationResult:
            resp = await self._client.post(
                "/api/chat",
                json={
                    "model": model or self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_new_tokens,
                    },
                },
            )
            if resp.status_code != 200:
                log.error("ollama_chat_status=%d body=%s", resp.status_code, resp.text[:200])
                raise ExternalServiceError(
                    f"Ollama /api/chat returned {resp.status_code}",
                    details={"status": resp.status_code},
                )
            data = resp.json()
            result = GenerationResult(
                text=data["message"]["content"],
                tokens_prompt=int(data.get("prompt_eval_count", 0)),
                tokens_completion=int(data.get("eval_count", 0)),
                model=model or self._model,
            )
            # Record tokens AFTER successful response — never count
            # tokens for failed calls. Bumping inside ``_call`` (vs
            # outside) means circuit-breaker rejections (CircuitOpenError)
            # also don't increment the counter, which is the right
            # semantic: rejected calls didn't consume tokens.
            _record_tokens(
                model=result.model,
                prompt_tokens=result.tokens_prompt,
                completion_tokens=result.tokens_completion,
            )
            return result

        return await self._breaker.call_async(_call)

    async def stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.1,
        max_new_tokens: int = 1024,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Yield response chunks as they arrive. Each yielded string is a
        partial token sequence. NB: no circuit breaker on streaming — the
        caller wraps the whole stream in try/except and reports failures.
        """
        async with self._client.stream(
            "POST",
            "/api/chat",
            json={
                "model": model or self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": True,
                "options": {"temperature": temperature, "num_predict": max_new_tokens},
            },
        ) as resp:
            if resp.status_code != 200:
                raise ExternalServiceError(
                    f"Ollama stream {resp.status_code}",
                )
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", {})
                content = msg.get("content", "")
                if content:
                    yield content
                if obj.get("done"):
                    break

    async def aclose(self) -> None:
        await self._client.aclose()
