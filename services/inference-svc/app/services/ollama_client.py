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
            return GenerationResult(
                text=data["message"]["content"],
                tokens_prompt=int(data.get("prompt_eval_count", 0)),
                tokens_completion=int(data.get("eval_count", 0)),
                model=model or self._model,
            )

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
