"""Single-purpose Ollama chat call. Stream disabled for sequential pipeline."""
from __future__ import annotations

import os
import time
from typing import Any

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
DEFAULT_MODEL = os.getenv("AGENT_CLI_MODEL", "llama3.1:8b")
DEFAULT_TIMEOUT_S = 180


def call_ollama(
    *,
    system_prompt: str,
    user_input: str,
    model: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Returns ``{response, model, tokens, latency_ms}``. Raises on HTTP error."""
    payload = {
        "model": model or DEFAULT_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
    }
    if options:
        payload["options"] = options
    started = time.time()
    r = requests.post(OLLAMA_URL, json=payload, timeout=DEFAULT_TIMEOUT_S)
    latency_ms = int((time.time() - started) * 1000)
    r.raise_for_status()
    body = r.json()
    return {
        "response": body["message"]["content"],
        "model": payload["model"],
        "tokens": body.get("eval_count", 0),
        "latency_ms": latency_ms,
    }
