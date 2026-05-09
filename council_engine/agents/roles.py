"""Council agent roles — each is a one-shot Ollama call with a specific lens.

Phase 1 of the 7-phase plan: 3 agents x 1 round of independent answers.
Each role's system prompt isolates ITS lens (primary expertise / opponent
critique / research-cite). Different model choices per role would add
diversity; for v1 they share the default model + differ in prompts only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
DEFAULT_MODEL = os.getenv("COUNCIL_MODEL", "llama3.1:8b")
DEFAULT_TIMEOUT_S = 240


PROMPTS: dict[str, str] = {
    "primary_expert": (
        "You are the Primary Expert on this topic. State the SINGLE best "
        "approach in 4-6 bullets. Be specific. NO 'it depends' hedging."
    ),
    "opponent": (
        "You are the Devil's Advocate. The user's request hides risks. "
        "List 3-5 concrete failure modes — each with: (a) what fails, "
        "(b) why, (c) how to detect early. NO applause, no agreement."
    ),
    "research": (
        "You are the Research Agent. List 3-5 known patterns / tools / "
        "papers RELEVANT to this question. For each: 1-line summary + "
        "why it applies here. If you can't cite, say 'no source — common practice'."
    ),
}


@dataclass
class AgentResponse:
    role: str
    model: str
    content: str
    tokens: int
    latency_ms: int


def _call(*, system: str, user: str, model: str, timeout_s: int) -> dict:
    import time
    started = time.time()
    r = requests.post(
        OLLAMA_URL,
        json={
            "model": model, "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.4},
        },
        timeout=timeout_s,
    )
    latency_ms = int((time.time() - started) * 1000)
    r.raise_for_status()
    body = r.json()
    return {
        "content": body["message"]["content"],
        "tokens": body.get("eval_count", 0),
        "latency_ms": latency_ms,
    }


def run_role(
    role: str, user_input: str, *,
    model: str | None = None, timeout_s: int = DEFAULT_TIMEOUT_S,
) -> AgentResponse:
    if role not in PROMPTS:
        raise ValueError(f"unknown council role: {role!r}")
    chosen_model = model or DEFAULT_MODEL
    out = _call(
        system=PROMPTS[role], user=user_input,
        model=chosen_model, timeout_s=timeout_s,
    )
    return AgentResponse(
        role=role, model=chosen_model, content=out["content"],
        tokens=out["tokens"], latency_ms=out["latency_ms"],
    )


__all__ = ["AgentResponse", "PROMPTS", "run_role"]
