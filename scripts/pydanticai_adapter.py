#!/usr/bin/env python3
"""PydanticAI adapter — Stage-1 contract for the AUTHOR validator swap.

Per the 2026-05-04 tool-evaluation finding (commit 7391a85): PydanticAI
is the #2 actionable adoption — formalize the AUTHOR proposal validator
using PydanticAI's tool-call framework instead of our hand-rolled
bracket-aware JSON extractor.

Stage-1 (this commit): the ADAPTER CONTRACT.
  - is_available()              — pip-installed + PYDANTICAI_ENABLED=1
  - validate(text, schema_cls)  — alternate path for validate_council_proposal
  - PydanticAIUnavailable        — RuntimeError subclass (callers can fall back)
  - status() / main()            — operator inspection

Stage-2 (next): wire validate() as a fallback inside
council_schemas.validate_council_proposal — when bracket-aware extraction
fails, try PydanticAI; if PydanticAI also fails, return None as today.

Stage-3 (future): if empirical eval shows PydanticAI extracts cleaner
than the regex path, flip the default — PydanticAI first, regex fallback.

The §44 discipline: each stage lands as its own commit + drill update.

Why PydanticAI (vs another framework):
  - We already use Pydantic for CouncilProposal; PydanticAI extends the
    schema-as-contract discipline to tool-calls
  - Type-safe + validated tool inputs (no string-prompt-engineering glue)
  - Natural fit for §55 Tier 1 (schema-as-contract upgrade)
  - MIT license; from the Pydantic team itself; rock-solid Pydantic dep
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

# Stage-1 opt-in (mirrors LITELLM_ENABLED + KAFKA_PUBLISH pattern).
PYDANTICAI_ENABLED = os.getenv("PYDANTICAI_ENABLED", "").strip() == "1"


class PydanticAIUnavailable(RuntimeError):
    """Raised when pydantic-ai is not installed OR feature flag is off.

    Callers detect + fall back:

        try:
            obj = pydanticai_validate(text, CouncilProposal)
        except PydanticAIUnavailable:
            obj = validate_council_proposal(text)  # existing regex path
    """


def is_available() -> bool:
    """Check if pydantic-ai is importable AND the feature flag is set."""
    if not PYDANTICAI_ENABLED:
        return False
    try:
        import pydantic_ai  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


def validate(text: str, schema_cls: type) -> Any:
    """PydanticAI-based validation — drop-in alternate for
    council_schemas.validate_council_proposal.

    Args:
      text:       raw LLM output (may contain prose + JSON + fences)
      schema_cls: Pydantic model class to validate against

    Returns:
      Instance of schema_cls on success.

    Raises:
      PydanticAIUnavailable — pydantic-ai not installed OR flag off
      ValueError            — schema validation failed (schema_cls.parse_raw fails)

    Stage-1 contract: when not enabled, ALWAYS raise PydanticAIUnavailable.
    Stage-2 wires real validation behavior.
    """
    if not is_available():
        raise PydanticAIUnavailable(
            "pydantic-ai not available (PYDANTICAI_ENABLED=0 OR pip install "
            "pydantic-ai needed). Stage-1 ships the adapter contract; "
            "Stage-2 wires the validator swap."
        )

    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be non-empty string")
    if not isinstance(schema_cls, type):
        raise TypeError(f"schema_cls must be a class; got {type(schema_cls).__name__}")

    # Lazy import — only fires when feature flag + lib present
    import pydantic_ai  # noqa: PLC0415, F401

    # Stage-1 implementation note: pydantic-ai's Agent.run_sync expects
    # a model client (LLM endpoint). For Stage-1 contract validation
    # we just validate the schema directly via the Pydantic class —
    # this gives the SAME parse-validate behavior our regex path
    # provides, but using Pydantic's strict JSON parsing.
    #
    # Stage-2 will wire the real pydantic_ai.Agent flow: model picks
    # the schema as a tool, generates a structured output, validation
    # is built into the tool-call protocol (no JSON parsing at all).
    #
    # Until Stage-2, validate() falls back to schema_cls.model_validate_json
    # which is what Pydantic does anyway. The difference is the contract:
    # callers use this entry point so Stage-2 swap is transparent.
    try:
        return schema_cls.model_validate_json(text)
    except Exception as exc:  # noqa: BLE001 — re-wrap as ValueError for parity
        raise ValueError(f"PydanticAI validation failed: {str(exc)[:200]}") from exc


def status() -> dict[str, Any]:
    """Operator-readable health/config dump."""
    return {
        "stage": 1,
        "available": is_available(),
        "feature_flag": PYDANTICAI_ENABLED,
        "pydantic_ai_installed": _is_pip_installed(),
        "note": (
            "Stage-1 — ships the adapter contract. validate() raises "
            "PydanticAIUnavailable when PYDANTICAI_ENABLED!=1 OR not "
            "installed. Stage-2 wires validate() as fallback inside "
            "council_schemas.validate_council_proposal (~6hr work)."
        ),
    }


def _is_pip_installed() -> bool:
    try:
        import pydantic_ai  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="pydanticai_adapter")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show adapter status")

    args = parser.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
