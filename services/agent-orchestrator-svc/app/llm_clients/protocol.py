"""LlmClient Protocol — uniform interface for Ollama / Claude CLI / Codex CLI.

Tier-A (local Ollama): cost_usd_cents = 0; tokens approximate from byte count.
Tier-B (cloud via local CLI): tokens reported by SDK; cost computed per model rate.

Contract: every implementation MUST raise LlmClientUnavailable when the backend
is unreachable. Returning an empty string masks failures and breaks the
fallback chain in app/model_router.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class LlmCallResult:
    text: str
    model: str
    tier: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd_cents: int = 0
    backend: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class LlmClientUnavailable(RuntimeError):
    """Backend wired but unreachable. Router catches this and tries fallback tier."""


@runtime_checkable
class LlmClient(Protocol):
    backend: str
    tier: str

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        timeout_seconds: float = 60.0,
        metadata: dict[str, Any] | None = None,
    ) -> LlmCallResult: ...

    async def close(self) -> None: ...
