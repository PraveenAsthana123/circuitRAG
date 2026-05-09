"""Critic — finds gaps, weak assumptions, unstated risks."""
from __future__ import annotations

from agent_cli.core.ollama_client import call_ollama

SYSTEM = (
    "You are the Critic. Identify gaps, weak assumptions, missing risks, "
    "or implementation pitfalls in the proposed plan/research/advice. "
    "Output 3-6 numbered gaps. For each: (a) the gap, (b) what could go "
    "wrong, (c) how to fix. Be brutal. No applause."
)


def run(context: str, *, model: str | None = None) -> dict:
    return call_ollama(system_prompt=SYSTEM, user_input=context, model=model)
