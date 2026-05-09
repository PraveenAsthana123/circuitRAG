"""Advisor — recommends one path with explicit trade-offs."""
from __future__ import annotations

from agent_cli.core.ollama_client import call_ollama

SYSTEM = (
    "You are the Advisor. Pick ONE recommended approach. Output: "
    "1) chosen path (one sentence), 2) why over the alternatives "
    "(2-3 bullets), 3) the single biggest trade-off you accept. "
    "No hedging. No 'it depends'."
)


def run(user_input: str, *, model: str | None = None) -> dict:
    return call_ollama(system_prompt=SYSTEM, user_input=user_input, model=model)
