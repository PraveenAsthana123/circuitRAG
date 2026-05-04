#!/usr/bin/env python3
"""LiteLLM adapter — Stage-1 contract for the call_ollama() swap.

Per the 2026-05-04 tool-evaluation finding (docs/admin/tool-evaluation):
LiteLLM is the #1 actionable adoption — replaces direct curl invocation
in scripts/local_council.py call_ollama() with provider-agnostic
litellm.completion(). Adds cost tracking + retry + fallback chains.

Stage-1 (this commit): the ADAPTER CONTRACT.
  - is_available() — does pip have litellm installed?
  - complete() — same signature as call_ollama, drop-in swap target
  - LiteLLMUnavailable exception — distinct from runtime errors
  - PolisAI gate fires BEFORE litellm.completion (preserves §47 ordering)

Stage-2 (next commit, ~2hr): wire `complete()` as a fallback path
inside call_ollama() guarded by LITELLM_ENABLED=1 env var. Keep
direct-curl as default until empirical eval confirms parity.

Stage-3 (future): make litellm the default; keep curl as fallback
when LITELLM_DISABLE=1 set.

The §44 discipline: each stage lands as its own commit + drill update.
This module's contract is locked NOW; behavior swaps later.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

logger = logging.getLogger(__name__)

# Stage-1 opt-in (kept for parity with KAFKA_PUBLISH pattern). When 0,
# complete() raises LiteLLMUnavailable even if the lib is installed —
# treats this as a feature flag.
LITELLM_ENABLED = os.getenv("LITELLM_ENABLED", "").strip() == "1"


class LiteLLMUnavailable(RuntimeError):
    """Raised when litellm is not installed OR the feature flag is off.

    Distinct from RuntimeError so callers can detect and fall back to
    the direct-curl path:

        try:
            text, tokens = litellm_complete(...)
        except LiteLLMUnavailable:
            text, tokens = call_ollama(...)
    """


def is_available() -> bool:
    """Check if litellm is importable AND the feature flag is set."""
    if not LITELLM_ENABLED:
        return False
    try:
        import litellm  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


def _polisai_gate(actor: str) -> None:
    """Same PolisAI gate as call_ollama — preserves §47 ordering.

    LiteLLM swap MUST keep this gate. Stage-1 contract: any future
    integration that reorders gate-after-completion would silently
    let denied calls leak network requests.
    """
    try:
        from policy_check import evaluate as _policy_evaluate  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(REPO / "scripts"))
        from policy_check import evaluate as _policy_evaluate  # noqa: PLC0415

    decision = _policy_evaluate(
        actor=actor,
        tool="ollama:generate",
        scopes_granted=["ollama:call"],
        persist_audit=True,
    )
    if not decision.allow:
        # Re-raise as the same exception type call_ollama uses, so
        # the swap is signature-compatible.
        try:
            from local_council import OllamaPolicyDenied  # noqa: PLC0415
            raise OllamaPolicyDenied(decision)
        except ImportError:
            # If local_council isn't loadable yet, fall back to a
            # generic RuntimeError that carries the decision.
            raise RuntimeError(  # noqa: B904
                f"PolisAI denied ollama:generate for actor={decision.actor!r}: "
                f"{decision.reason} (rule={decision.rule_matched})"
            )


def complete(
    model: str,
    system: str,
    prompt: str,
    timeout: float = 180.0,
    *,
    actor: str = "council:unknown",
    _skip_gate: bool = False,
) -> tuple[str, int]:
    """LiteLLM completion — drop-in replacement for call_ollama().

    Public signature matches call_ollama(model, system, prompt, timeout, actor)
    for clean swap. The internal `_skip_gate` kwarg (underscore-prefixed
    by convention) is for trusted callers who already gated; bypassing
    requires the caller to assert the gate fired upstream.

    Returns (response_text, tokens_used).

    Raises:
      LiteLLMUnavailable — litellm not installed OR feature flag off
      OllamaPolicyDenied — PolisAI rejected the call (when _skip_gate=False)
      RuntimeError       — actual litellm/provider error

    The model arg uses litellm's provider-prefix convention:
      ollama/<name>     — local Ollama (e.g., "ollama/deepseek-coder:6.7b-instruct")
      anthropic/<name>  — Anthropic API (Stage-3 fallback)
      openai/<name>     — OpenAI API (Stage-3 fallback)

    Stage-3 _skip_gate consolidation: when call_ollama falls through to
    this adapter, it has ALREADY gated upstream (line 174 in
    local_council.py). The Stage-2 fallback fired the gate twice —
    harmless (same actor/tool/scopes → same decision) but produced
    duplicate audit rows. Stage-3 eliminates the duplicate by passing
    _skip_gate=True from the fallback dispatcher. Drill enforces:
    public callers must NOT pass _skip_gate (signature is keyword-only
    + underscore-prefix-conventional).
    """
    if not is_available():
        raise LiteLLMUnavailable(
            "litellm not available (LITELLM_ENABLED=0 OR pip install litellm needed). "
            "Stage-1 ships the adapter contract; Stage-2 wires the swap."
        )

    # PolisAI gate fires BEFORE the litellm call — same §47 invariant
    # the direct-curl path enforces. Drill locks this ordering.
    # Stage-3: _skip_gate=True bypasses gate (caller must have gated
    # upstream). Drill enforces _skip_gate is NOT in the public-call
    # signature (keyword-only + underscore-prefix marks it as internal).
    if not _skip_gate:
        _polisai_gate(actor)

    # Lazy import — only loaded when the feature flag + lib are present
    import litellm  # noqa: PLC0415

    # Map a bare ollama model name to litellm's provider-prefix form
    if "/" not in model:
        model = f"ollama/{model}"

    try:
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            timeout=timeout,
            api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    except Exception as exc:  # noqa: BLE001 — wrap as RuntimeError for parity
        raise RuntimeError(f"litellm call failed: {str(exc)[:200]}") from exc

    # Extract response text + token count from litellm's response shape
    try:
        text = response.choices[0].message.content or ""
        tokens = int(response.usage.completion_tokens or 0)
        return text, tokens
    except (AttributeError, IndexError) as exc:
        raise RuntimeError(
            f"litellm response shape unexpected: {str(exc)[:100]}"
        ) from exc


def status() -> dict[str, Any]:
    """Operator-readable health/config dump."""
    return {
        "stage": 1,
        "available": is_available(),
        "feature_flag": LITELLM_ENABLED,
        "litellm_installed": _is_pip_installed(),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "note": (
            "Stage-1 — ships the adapter contract. complete() raises "
            "LiteLLMUnavailable when LITELLM_ENABLED!=1 OR litellm not installed. "
            "Stage-2 wires complete() as fallback inside call_ollama() (~2hr work)."
        ),
    }


def _is_pip_installed() -> bool:
    try:
        import litellm  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="litellm_adapter")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show adapter status")
    p_test = sub.add_parser("test", help="Try a completion (Stage-1: will raise)")
    p_test.add_argument("--actor", default="council:author")
    p_test.add_argument("--model", default="deepseek-coder:6.7b-instruct")

    args = parser.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0

    if args.cmd == "test":
        try:
            text, tokens = complete(
                model=args.model,
                system="You are a helpful coding assistant.",
                prompt="Say 'ok' in one word.",
                timeout=30.0,
                actor=args.actor,
            )
            print(json.dumps(
                {"ok": True, "text": text[:200], "tokens": tokens},
                indent=2,
            ))
            return 0
        except LiteLLMUnavailable as exc:
            print(json.dumps({
                "ok": False,
                "error_code": "LITELLM_UNAVAILABLE",
                "message": str(exc),
            }, indent=2))
            return 2
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({
                "ok": False,
                "error_code": "LITELLM_RUNTIME_ERROR",
                "message": str(exc)[:300],
            }, indent=2))
            return 3

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
