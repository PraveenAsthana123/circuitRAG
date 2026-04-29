from __future__ import annotations

import httpx


class OllamaGenerateClient:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def generate(self, *, model: str, prompt: str) -> str:
        response = await self._client.post(
            f"{self._base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("response", "")).strip()

    async def close(self) -> None:
        await self._client.aclose()

