#!/usr/bin/env python3
"""ChatXAI → ChatOllama fallback CLI when XAI_API_KEY absent.

Per CLAUDE.md §38 (governance), §52 row 4 (operator API gap),
§55.3 (outcome contract). Iter 10 (`fa7358d`) installed
langchain-xai for Grok-via-API. Iter 21 (this) ships an operator
CLI that USES the integration with graceful fallback:

  - When XAI_API_KEY is set:    routes to api.x.ai via ChatXAI
  - When XAI_API_KEY is unset:  routes to local Ollama via ChatOllama
                                using qwen2.5:latest as Grok-class
                                proxy

Brutal-honesty: ChatXAI fallback to Ollama is NOT semantically
identical to Grok. It's the closest LOCAL substitute. Operators
who need REAL Grok responses MUST set XAI_API_KEY; this script's
honest_gap surfaces that.

Usage:
    # Interactive prompt:
    python3 scripts/chatxai_fallback.py "Explain RLS in Postgres"

    # Force Ollama path (smoke-test the fallback):
    XAI_API_KEY= python3 scripts/chatxai_fallback.py "test"

    # Use the real xAI API:
    XAI_API_KEY=xai-... python3 scripts/chatxai_fallback.py "test"

Drilled at mcp/tests/drill_chatxai_fallback.py.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:latest")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def is_xai_key_set() -> bool:
    """True if XAI_API_KEY is non-empty in env."""
    key = os.environ.get("XAI_API_KEY", "").strip()
    return bool(key)


def call_xai(prompt: str, *, model: str = "grok-2-latest") -> tuple[str | None, str]:
    """Call api.x.ai via langchain-xai. Returns (response, route_reason)."""
    try:
        from langchain_xai import ChatXAI
    except ImportError as exc:
        return None, f"langchain_xai not importable: {exc}"

    try:
        client = ChatXAI(model=model)
        response = client.invoke(prompt)
        text = getattr(response, "content", str(response))
        return str(text), f"xai:api ({model})"
    except Exception as exc:  # noqa: BLE001
        return None, f"xai_call_failed: {type(exc).__name__}: {str(exc)[:80]}"


def call_ollama_fallback(prompt: str) -> tuple[str | None, str]:
    """Call local Ollama via langchain-ollama. Returns (response, route_reason)."""
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        return None, f"langchain_ollama not importable: {exc}"

    try:
        client = ChatOllama(model=OLLAMA_FALLBACK_MODEL, base_url=OLLAMA_BASE)
        response = client.invoke(prompt)
        text = getattr(response, "content", str(response))
        return str(text), f"ollama:fallback ({OLLAMA_FALLBACK_MODEL})"
    except Exception as exc:  # noqa: BLE001
        return None, f"ollama_call_failed: {type(exc).__name__}: {str(exc)[:80]}"


def evaluate(prompt: str) -> dict:
    """Route + invoke. Returns full audit row.

    Routes ALWAYS chosen at evaluation time based on env state at the
    moment of the call. NOT cached — env can flip between calls.
    """
    started = time.time()
    has_key = is_xai_key_set()
    route = "xai" if has_key else "ollama_fallback"

    if has_key:
        text, reason = call_xai(prompt)
        if text is None:
            # xAI failed — try Ollama as escape hatch (per §47 resilience)
            text2, reason2 = call_ollama_fallback(prompt)
            if text2 is not None:
                return {
                    "route": "ollama_fallback (after xai_failed)",
                    "reason": f"{reason} → {reason2}",
                    "response": text2,
                    "honest_gap": "xAI call failed; used local Ollama proxy",
                    "latency_s": round(time.time() - started, 3),
                }
            return {
                "route": "failed",
                "reason": f"{reason} AND {reason2}",
                "response": None,
                "honest_gap": "BOTH xAI + Ollama paths failed",
                "latency_s": round(time.time() - started, 3),
            }
        return {
            "route": route,
            "reason": reason,
            "response": text,
            "honest_gap": None,
            "latency_s": round(time.time() - started, 3),
        }

    # No key — go straight to Ollama
    text, reason = call_ollama_fallback(prompt)
    return {
        "route": route,
        "reason": reason,
        "response": text,
        "honest_gap": (
            "XAI_API_KEY not set — using local Ollama qwen2.5 as Grok-class "
            "proxy. Set XAI_API_KEY to route to actual Grok."
        ),
        "latency_s": round(time.time() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "prompt", nargs="?", default=None,
        help="Prompt to send (omit to print routing diagnostic only)",
    )
    parser.add_argument(
        "--diagnostic-only", action="store_true",
        help="Just print env routing decision; don't call any LLM",
    )
    args = parser.parse_args()

    has_key = is_xai_key_set()
    print(f"XAI_API_KEY set:    {has_key}", file=sys.stderr)
    print(f"Route:              {'xai (api.x.ai)' if has_key else f'ollama:{OLLAMA_FALLBACK_MODEL}'}",
          file=sys.stderr)

    if args.diagnostic_only or args.prompt is None:
        print(f"Honest gap:         {'none' if has_key else 'no API key — local proxy active'}",
              file=sys.stderr)
        return 0

    result = evaluate(args.prompt)
    if result["honest_gap"]:
        print(f"\n[honest_gap] {result['honest_gap']}\n", file=sys.stderr)
    if result["response"]:
        print(result["response"])
        return 0
    print(f"FAIL: {result['reason']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
