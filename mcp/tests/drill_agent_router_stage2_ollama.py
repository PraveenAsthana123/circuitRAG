#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Agent Router Stage-2 — Ollama-backed classifier with heuristic fallback.

Per CLAUDE.md §43 + §44 + §47. Locks Stage-2 promotion of agent_router:

  - AGENT_ROUTER_OLLAMA_ENABLED env-var opt-in (default off)
  - When OFF: classify() goes directly to heuristic (Stage-1 behavior)
  - When ON: classify() tries _classify_via_ollama() FIRST
  - On _OllamaClassifierUnavailable → fall through to heuristic
  - Heuristic ALWAYS works (no regression — Stage-1 contract preserved)
  - _classify_via_ollama validates output shape + risk + confidence
  - Internal _OllamaClassifierUnavailable exception is leading-underscore

Eight steps. Five negative.
"""
from __future__ import annotations

import importlib
import inspect
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: AGENT_ROUTER_OLLAMA_ENABLED module-level flag exists --")
    os.environ.pop("AGENT_ROUTER_OLLAMA_ENABLED", None)
    import agent_router
    importlib.reload(agent_router)
    if not hasattr(agent_router, "AGENT_ROUTER_OLLAMA_ENABLED"):
        print("x agent_router must expose AGENT_ROUTER_OLLAMA_ENABLED flag")
        return 1
    if agent_router.AGENT_ROUTER_OLLAMA_ENABLED is not False:
        print(f"x default must be False; got {agent_router.AGENT_ROUTER_OLLAMA_ENABLED}")
        return 1
    print("  ok: AGENT_ROUTER_OLLAMA_ENABLED exposed; default False")

    print("-- 2. POSITIVE: _classify_via_ollama function + _OllamaClassifierUnavailable --")
    if not hasattr(agent_router, "_classify_via_ollama"):
        print("x _classify_via_ollama function missing")
        return 1
    if not hasattr(agent_router, "_OllamaClassifierUnavailable"):
        print("x _OllamaClassifierUnavailable internal exception missing")
        return 1
    # Both must be underscore-prefixed (internal API markers)
    sig = inspect.signature(agent_router._classify_via_ollama)
    if list(sig.parameters.keys()) != ["message"]:
        print(f"x _classify_via_ollama signature wrong: {list(sig.parameters.keys())}")
        return 1
    print("  ok: _classify_via_ollama + _OllamaClassifierUnavailable (underscore-internal)")

    print("-- 3. NEGATIVE: flag OFF → classify() never calls Ollama path --")
    # Default state: flag unset. Classify should reach heuristic only.
    importlib.reload(agent_router)
    ollama_called = {"hit": False}

    def fake_ollama(_message):
        ollama_called["hit"] = True
        raise agent_router._OllamaClassifierUnavailable("should not be called")

    with patch.object(agent_router, "_classify_via_ollama", side_effect=fake_ollama):
        result = agent_router.classify("explain something", persist_audit=False)
    if ollama_called["hit"]:
        print("x flag OFF should not invoke _classify_via_ollama")
        return 1
    if result.intent != "explain":
        print(f"x heuristic should classify 'explain'; got {result.intent!r}")
        return 1
    print("  ok: flag OFF → heuristic only (Ollama path never called)")

    print("-- 4. POSITIVE: flag ON → classify() tries Ollama FIRST --")
    os.environ["AGENT_ROUTER_OLLAMA_ENABLED"] = "1"
    importlib.reload(agent_router)
    ollama_called["hit"] = False

    def fake_ollama_success(_message):
        ollama_called["hit"] = True
        return agent_router.RouterDecision(
            intent="custom_intent",
            risk="medium",
            recommended_actor="council:author",
            recommended_tool="ollama:generate",
            confidence=0.92,
            reasons=["ollama:qwen2.5", "test"],
            timestamp=0.0,
            message_hash="abc",
        )

    with patch.object(agent_router, "_classify_via_ollama", side_effect=fake_ollama_success):
        result = agent_router.classify("anything", persist_audit=False)
    if not ollama_called["hit"]:
        print("x flag ON should invoke _classify_via_ollama")
        return 1
    if result.intent != "custom_intent":
        print(f"x Ollama result should propagate; got intent={result.intent!r}")
        return 1
    if result.confidence != 0.92:
        print(f"x Ollama confidence should propagate; got {result.confidence}")
        return 1
    print("  ok: flag ON → Ollama path fires; result propagates")

    print("-- 5. NEGATIVE: flag ON + Ollama-unavailable → falls back to heuristic --")
    importlib.reload(agent_router)
    fallback_via_heuristic = {"hit": False}

    def fake_ollama_fail(_message):
        raise agent_router._OllamaClassifierUnavailable("simulated network error")

    # Hook into the heuristic path by counting pattern matches
    original_classify = agent_router.classify

    with patch.object(agent_router, "_classify_via_ollama", side_effect=fake_ollama_fail):
        result = agent_router.classify("explain how this works", persist_audit=False)
    # The fallback should produce heuristic 'explain' classification
    if result.intent != "explain":
        print(f"x heuristic fallback should classify 'explain'; got {result.intent!r}")
        return 1
    if "ollama" in (result.reasons[0] if result.reasons else "").lower():
        print(f"x fallback decision should NOT cite ollama; got reasons={result.reasons}")
        return 1
    print("  ok: Ollama-fail → heuristic fallback (Stage-1 behavior preserved)")

    print("-- 6. NEGATIVE: source has try/except _OllamaClassifierUnavailable --")
    src = (SCRIPTS / "agent_router.py").read_text(encoding="utf-8")
    if "except _OllamaClassifierUnavailable" not in src:
        print("x source must catch _OllamaClassifierUnavailable")
        return 1
    # The Ollama path must fire BEFORE heuristic loop
    classify_idx = src.find("def classify(")
    classify_end = src.find("\ndef ", classify_idx + 10)
    body = src[classify_idx:classify_end if classify_end != -1 else len(src)]

    ollama_pos = body.find("AGENT_ROUTER_OLLAMA_ENABLED")
    heuristic_pos = body.find("for pattern_list")
    if ollama_pos == -1 or heuristic_pos == -1:
        print(f"x cannot locate ordering markers (ollama={ollama_pos}, heuristic={heuristic_pos})")
        return 1
    if ollama_pos > heuristic_pos:
        print(f"x Ollama-path check ({ollama_pos}) must precede heuristic loop ({heuristic_pos})")
        return 1
    print("  ok: Ollama path fires BEFORE heuristic loop")

    print("-- 7. NEGATIVE: empty input bypasses Ollama (conservative default) --")
    # Empty input must hit conservative_default path BEFORE Ollama is called.
    importlib.reload(agent_router)
    ollama_called["hit"] = False
    with patch.object(agent_router, "_classify_via_ollama", side_effect=fake_ollama_success):
        result = agent_router.classify("", persist_audit=False)
    if ollama_called["hit"]:
        print("x empty input should NOT call Ollama (conservative default first)")
        return 1
    if result.intent != "unknown":
        print(f"x empty input should default to 'unknown'; got {result.intent!r}")
        return 1
    print("  ok: empty input → conservative default; Ollama not invoked")

    print("-- 8. POSITIVE: existing Stage-1 drill still passes (no regression) --")
    # Verify the heuristic path still works for all the Stage-1 patterns.
    os.environ.pop("AGENT_ROUTER_OLLAMA_ENABLED", None)
    importlib.reload(agent_router)
    test_cases = [
        ("delete the user table", "high"),
        ("explain this", "low"),
        ("fix the ruff lint errors", "medium"),
        ("xyzqwert nonsense", "high"),  # conservative default
    ]
    for msg, expected_risk in test_cases:
        d = agent_router.classify(msg, persist_audit=False)
        if d.risk != expected_risk:
            print(f"x Stage-1 regression: {msg!r} expected risk={expected_risk}; got {d.risk}")
            return 1
    print(f"  ok: 4 Stage-1 cases still classified correctly (no regression)")

    # Cleanup
    os.environ.pop("AGENT_ROUTER_OLLAMA_ENABLED", None)

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
