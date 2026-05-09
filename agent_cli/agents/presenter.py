"""Presenter — final synthesis into structured output."""
from __future__ import annotations

from agent_cli.core.ollama_client import call_ollama

SYSTEM = (
    "You are the Presenter. Combine the inputs into ONE structured answer "
    "for an enterprise architect. Required sections in order:\n"
    "1. Final answer (3-5 bullets)\n"
    "2. Plan (table: phase | goal | risks | acceptance)\n"
    "3. Recommended stack (table: layer | choice | why)\n"
    "4. Top 3 gaps to close\n"
    "5. Acceptance criteria (numbered list)\n"
    "Use markdown tables. Skip empty sections."
)


def run(context: str, *, model: str | None = None) -> dict:
    return call_ollama(system_prompt=SYSTEM, user_input=context, model=model)
