"""Planner — turns the user request into a phased step list."""
from __future__ import annotations

from agent_cli.core.ollama_client import call_ollama

SYSTEM = (
    "You are the Planner. Decompose the user's request into 3-7 concrete "
    "phases. For each phase output: (a) goal, (b) key risks, (c) acceptance "
    "criteria. Be terse — bullet points, not prose. Do NOT propose code."
)


def run(user_input: str, *, model: str | None = None) -> dict:
    return call_ollama(system_prompt=SYSTEM, user_input=user_input, model=model)
