"""LlmClientPool — dispatch-by-backend with fallback-chain execution.

The pool holds one client per backend ('ollama', 'claude_cli', 'codex_cli')
and exposes execute(decision, prompt) that walks the chosen handle plus its
fallback chain until one succeeds or all raise LlmClientUnavailable.

This is where §10.3 'never silent fallback' is enforced for the LLM layer:
every fallback transition is appended to RouteOutcome.fallback_log, which
the agent then writes into the task audit_events stream.

Why a pool, not separate client args on each agent: the router decides at
call time which backend to use; agents shouldn't statically know about
backends. The pool is a backend-by-name registry the router results
unambiguously map into.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .protocol import LlmCallResult, LlmClient, LlmClientUnavailable


@dataclass(frozen=True)
class RouteOutcome:
    """Result of pool.execute() — wraps the LlmCallResult with the routing
    trail for audit/explainability per §47/§48."""
    result: LlmCallResult
    handle_used: dict[str, str]                 # final handle that succeeded
    fallback_log: list[dict[str, Any]] = field(default_factory=list)
    # Each entry: {handle, error, kind} for handles tried before success.


class AllBackendsUnavailable(LlmClientUnavailable):
    """Raised when chosen + entire fallback_chain all failed.

    Carries .errors as list[(handle_dict, str)] so the audit row can
    reconstruct which combinations were attempted.
    """

    def __init__(self, errors: list[tuple[dict[str, str], str]]) -> None:
        self.errors = errors
        first = errors[0][1] if errors else "no attempts recorded"
        super().__init__(
            f"all {len(errors)} backend attempts failed; first error: {first}"
        )


class LlmClientPool:
    """Backend registry. Build with whichever clients you want available;
    a missing entry just means the router's fallback chain skips that tier
    transparently. Empty pool → no LLM calls succeed (drill case)."""

    def __init__(self, clients: dict[str, LlmClient]) -> None:
        self._clients: dict[str, LlmClient] = dict(clients)

    def has(self, backend: str) -> bool:
        return backend in self._clients

    def has_tier_b(self) -> bool:
        return "claude_cli" in self._clients or "codex_cli" in self._clients

    async def close(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:  # noqa: BLE001, S110
                # Closing must never raise; the agent loop is shutting down.
                pass

    async def execute(
        self,
        *,
        decision,  # RouteDecision (avoid hard import to keep pool standalone)
        prompt: str,
        timeout_seconds: float = 60.0,
    ) -> RouteOutcome:
        """Try decision.chosen, then each fallback in order.

        On LlmClientUnavailable, append to fallback_log and try next.
        On any other exception, propagate (it's a bug, not a backend issue).
        After exhausting the chain, raise AllBackendsUnavailable.
        """
        attempts: list[tuple[dict[str, str], str]] = []
        fallback_log: list[dict[str, Any]] = []
        chain = [decision.chosen, *decision.fallback_chain]

        for idx, handle in enumerate(chain):
            client = self._clients.get(handle.backend)
            if client is None:
                attempts.append((handle.to_dict(), f"backend not in pool: {handle.backend!r}"))
                fallback_log.append({
                    "handle": handle.to_dict(),
                    "error": f"backend {handle.backend!r} not registered in pool",
                    "kind": "missing_backend",
                    "step": idx,
                })
                continue
            try:
                result = await client.generate(
                    model=handle.model,
                    prompt=prompt,
                    timeout_seconds=timeout_seconds,
                )
                return RouteOutcome(
                    result=result,
                    handle_used=handle.to_dict(),
                    fallback_log=fallback_log,
                )
            except LlmClientUnavailable as exc:
                attempts.append((handle.to_dict(), str(exc)))
                fallback_log.append({
                    "handle": handle.to_dict(),
                    "error": str(exc),
                    "kind": "llm_client_unavailable",
                    "step": idx,
                })
                continue

        raise AllBackendsUnavailable(attempts)
