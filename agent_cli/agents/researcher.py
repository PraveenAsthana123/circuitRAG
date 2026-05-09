"""Researcher — surfaces relevant tools, frameworks, prior art."""
from __future__ import annotations

from agent_cli.core.ollama_client import call_ollama

SYSTEM = (
    "You are the Researcher. List ONLY the tools / frameworks / patterns "
    "directly relevant to the request. Output format: a small markdown "
    "table with columns: Tool/Pattern | Why it fits | Caveats. Maximum 6 "
    "rows. No filler prose."
)


def run(user_input: str, *, model: str | None = None) -> dict:
    return call_ollama(system_prompt=SYSTEM, user_input=user_input, model=model)
