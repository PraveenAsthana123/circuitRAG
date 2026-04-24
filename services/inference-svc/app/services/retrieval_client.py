"""gRPC/HTTP client for retrieval-svc (using HTTP+JSON here for simplicity)."""
from __future__ import annotations

from typing import Any

import httpx

from documind_core.circuit_breaker import CircuitBreaker
from documind_core.exceptions import ExternalServiceError


class RetrievalClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._breaker = CircuitBreaker(
            "retrieval-svc",
            failure_threshold=5,
            recovery_timeout=30.0,
            expected_exception=(httpx.HTTPError, ExternalServiceError),
        )

    async def retrieve(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        query: str,
        top_k: int,
        strategy: str,
    ) -> list[dict[str, Any]]:
        async def _call() -> list[dict[str, Any]]:
            resp = await self._client.post(
                "/api/v1/retrieve",
                json={"query": query, "top_k": top_k, "strategy": strategy},
                headers={
                    "X-Tenant-ID": tenant_id,
                    "X-Correlation-ID": correlation_id,
                },
            )
            if resp.status_code != 200:
                raise ExternalServiceError(
                    f"retrieval-svc {resp.status_code}",
                    details={"body": resp.text[:200]},
                )
            return resp.json()["chunks"]

        return await self._breaker.call_async(_call)

    async def aclose(self) -> None:
        await self._client.aclose()
