"""Thin embedder for queries — reuses the same Ollama API as ingestion."""
from __future__ import annotations

import httpx

from documind_core.circuit_breaker import CircuitBreaker
from documind_core.exceptions import ExternalServiceError


class OllamaEmbedderClient:
    def __init__(self, *, base_url: str, model: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._model = model
        self._breaker = CircuitBreaker(
            "ollama-embed-query",
            failure_threshold=5,
            recovery_timeout=30.0,
            expected_exception=(httpx.HTTPError, ExternalServiceError),
        )

    async def embed_query(self, query: str) -> list[float]:
        async def _call() -> list[float]:
            resp = await self._client.post(
                "/api/embed", json={"model": self._model, "input": [query]}
            )
            if resp.status_code != 200:
                raise ExternalServiceError(f"Ollama /api/embed → {resp.status_code}")
            return resp.json()["embeddings"][0]

        return await self._breaker.call_async(_call)

    async def aclose(self) -> None:
        await self._client.aclose()
