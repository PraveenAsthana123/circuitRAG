"""
Ollama-backed embedder.

Ollama exposes an OpenAI-compatible API. We call ``/api/embed`` with a batch
of texts; Ollama returns one vector per text. Wrapped in a circuit breaker
so a flaky Ollama doesn't cascade.
"""
from __future__ import annotations

import logging

import httpx

from documind_core.circuit_breaker import CircuitBreaker
from documind_core.exceptions import ExternalServiceError

from .base import EmbeddingProvider

log = logging.getLogger(__name__)

#: Known dimensions for the embedding models we support. Update when adding a model.
_MODEL_DIMENSIONS = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "bge-m3": 1024,
    "all-minilm": 384,
}


class OllamaEmbedder(EmbeddingProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = _MODEL_DIMENSIONS.get(model.split(":", 1)[0], 768)
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout_seconds
        )
        self._breaker = breaker or CircuitBreaker(
            "ollama-embed",
            failure_threshold=5,
            recovery_timeout=30.0,
            expected_exception=(httpx.HTTPError, ExternalServiceError),
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async def _call() -> list[list[float]]:
            resp = await self._client.post(
                "/api/embed",
                json={"model": self._model, "input": texts},
            )
            if resp.status_code != 200:
                log.error("ollama_embed_status=%d body=%s", resp.status_code, resp.text[:200])
                raise ExternalServiceError(
                    f"Ollama /api/embed returned {resp.status_code}",
                    details={"status": resp.status_code},
                )
            data = resp.json()
            return data["embeddings"]

        vectors = await self._breaker.call_async(_call)
        if len(vectors) != len(texts):
            raise ExternalServiceError(
                "Ollama returned wrong number of embeddings",
                details={"requested": len(texts), "got": len(vectors)},
            )
        return vectors

    async def aclose(self) -> None:
        await self._client.aclose()
