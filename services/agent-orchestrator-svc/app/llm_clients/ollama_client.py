"""Ollama HTTP client adapted to the LlmClient Protocol.

Wraps Ollama's /api/generate endpoint. Tier-A (local, free).

Backward compat: app/ollama_client.py keeps the original
OllamaGenerateClient class for existing callers; this module exposes a
Protocol-compliant variant that the router (A3) consumes.
"""
from __future__ import annotations

from typing import Any

import httpx

from .protocol import LlmCallResult, LlmClientUnavailable


class OllamaHttpClient:
    backend = "ollama"
    tier = "tier_a"

    def __init__(self, *, base_url: str = "http://localhost:11434", timeout_seconds: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        timeout_seconds: float = 60.0,
        metadata: dict[str, Any] | None = None,
    ) -> LlmCallResult:
        try:
            response = await self._client.post(
                f"{self._base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise LlmClientUnavailable(f"ollama unreachable at {self._base_url}: {exc}") from exc

        payload = response.json()
        text = str(payload.get("response", "")).strip()
        if not text:
            # Empty response is treated as a soft failure — explicit, not silent.
            # Router catches LlmClientUnavailable and tries the next tier.
            raise LlmClientUnavailable(f"ollama returned empty response for model {model!r}")

        tokens_in = int(payload.get("prompt_eval_count") or 0)
        tokens_out = int(payload.get("eval_count") or 0)
        return LlmCallResult(
            text=text,
            model=model,
            tier="tier_a",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd_cents=0,  # local = free
            backend=self.backend,
            raw_metadata={"prompt_eval_duration_ns": payload.get("prompt_eval_duration")},
        )

    async def close(self) -> None:
        await self._client.aclose()
