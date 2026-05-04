#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: LiteLLM adapter Stage-1 contract.

Per CLAUDE.md §43 + the 2026-05-04 tool-evaluation finding (LiteLLM
verdict=integrate). Locks the contract that:

  - Module exposes is_available() / complete() / status() / LiteLLMUnavailable
  - complete() signature matches call_ollama() exactly (drop-in swap target)
  - Default behavior is no-op: complete() raises LiteLLMUnavailable
    when LITELLM_ENABLED unset (the §44 opt-in pattern)
  - PolisAI gate fires BEFORE litellm.completion (same §47 invariant
    as call_ollama; drill catches a refactor that re-orders)
  - Module import is side-effect-free (no Kafka-style network calls)
  - status() reflects feature_flag + installed-ness honestly
  - LiteLLMUnavailable subclasses RuntimeError (callers can catch it
    + fall back to direct-curl)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: module exports the 4 contract surfaces --")
    # Ensure clean env (no LITELLM_ENABLED leak from another drill)
    os.environ.pop("LITELLM_ENABLED", None)
    import litellm_adapter  # noqa: E402
    importlib.reload(litellm_adapter)
    for name in ("is_available", "complete", "status", "LiteLLMUnavailable"):
        if not hasattr(litellm_adapter, name):
            print(f"x litellm_adapter.{name} missing")
            return 1
    print("  ok: 4 surfaces exported")

    print("-- 2. POSITIVE: complete() public signature matches call_ollama() --")
    # Drop-in swap requires the PUBLIC signature to match. Stage-3
    # adds `_skip_gate` (underscore-prefix internal) — drill ALLOWS
    # underscore-prefixed extras as long as they're keyword-only +
    # have safe defaults (False / None).
    import inspect
    sig_complete = inspect.signature(litellm_adapter.complete)
    public_params = [
        p for p in sig_complete.parameters.keys() if not p.startswith("_")
    ]
    expected_public = ["model", "system", "prompt", "timeout", "actor"]
    if public_params != expected_public:
        print(f"x public signature mismatch — expected {expected_public}, got {public_params}")
        return 1
    # actor must be keyword-only (matches call_ollama)
    actor_param = sig_complete.parameters["actor"]
    if actor_param.kind != inspect.Parameter.KEYWORD_ONLY:
        print(f"x actor param must be keyword-only; kind={actor_param.kind}")
        return 1
    if actor_param.default != "council:unknown":
        print(f"x actor default must be 'council:unknown'; got {actor_param.default!r}")
        return 1
    # Underscore-prefix internal kwargs MUST be keyword-only with
    # falsy defaults (so callers omitting them get safe behavior)
    for name, param in sig_complete.parameters.items():
        if name.startswith("_"):
            if param.kind != inspect.Parameter.KEYWORD_ONLY:
                print(f"x internal kwarg {name!r} must be keyword-only")
                return 1
            if param.default not in (False, None, 0, ""):
                print(f"x internal kwarg {name!r} must have falsy default; got {param.default!r}")
                return 1
    print(f"  ok: 5 public params + {len([p for p in sig_complete.parameters if p.startswith('_')])} internal underscore-kwargs")

    print("-- 3. NEGATIVE: default is_available() = False (LITELLM_ENABLED unset) --")
    if litellm_adapter.is_available():
        print("x default is_available should be False (feature flag opt-in)")
        return 1
    print("  ok: feature flag opt-in posture preserved")

    print("-- 4. NEGATIVE: complete() raises LiteLLMUnavailable when disabled --")
    raised = False
    try:
        litellm_adapter.complete(
            model="deepseek-coder:6.7b-instruct",
            system="x", prompt="x",
            actor="council:author",
        )
    except litellm_adapter.LiteLLMUnavailable as exc:
        raised = True
        # Error message must be operator-readable + cite the feature flag
        if "LITELLM_ENABLED" not in str(exc):
            print(f"x error must cite LITELLM_ENABLED; got: {str(exc)[:200]}")
            return 1
    except Exception as exc:
        print(f"x wrong exception type — expected LiteLLMUnavailable; got {type(exc).__name__}")
        return 1
    if not raised:
        print("x complete() should have raised LiteLLMUnavailable")
        return 1
    print("  ok: LiteLLMUnavailable raised + cites feature flag")

    print("-- 5. NEGATIVE: LiteLLMUnavailable subclasses RuntimeError --")
    # Callers need this so try/except RuntimeError catches it as a fallback
    # boundary. Drill enforces the inheritance.
    if not issubclass(litellm_adapter.LiteLLMUnavailable, RuntimeError):
        print("x LiteLLMUnavailable must subclass RuntimeError")
        return 1
    print("  ok: LiteLLMUnavailable subclasses RuntimeError")

    print("-- 6. NEGATIVE: PolisAI gate fires BEFORE litellm.completion --")
    # Inspect source to ensure the ordering invariant is preserved.
    src = (SCRIPTS / "litellm_adapter.py").read_text(encoding="utf-8")
    func_start = src.find("def complete(")
    func_end = src.find("\ndef ", func_start + 10)
    body = src[func_start:func_end if func_end != -1 else len(src)]
    gate_pos = body.find("_polisai_gate(")
    completion_pos = body.find("litellm.completion(")
    if gate_pos == -1:
        print("x complete() must call _polisai_gate")
        return 1
    if completion_pos == -1:
        print("x complete() must call litellm.completion")
        return 1
    if gate_pos > completion_pos:
        print(f"x _polisai_gate must precede litellm.completion (gate@{gate_pos} > completion@{completion_pos})")
        return 1
    print(f"  ok: _polisai_gate (pos {gate_pos}) precedes litellm.completion (pos {completion_pos})")

    print("-- 7. NEGATIVE: module import is side-effect-free (no Kafka/HTTP/litellm load) --")
    # Stage-1: import must be cheap. The litellm import is lazy (only
    # fires inside complete() when ENABLED). Drill via subprocess.
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{SCRIPTS}'); "
         f"import time; t0 = time.time(); "
         f"import litellm_adapter; "
         f"print(f'IMPORT_OK {{(time.time() - t0):.3f}}')"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
        env={**os.environ, "LITELLM_ENABLED": ""},
    )
    if proc.returncode != 0:
        print(f"x import failed: {proc.stderr[:200]}")
        return 1
    if "IMPORT_OK" not in proc.stdout:
        print(f"x sentinel missing: {proc.stdout[:200]}")
        return 1
    m = re.search(r"IMPORT_OK\s+([\d.]+)", proc.stdout)
    if m:
        elapsed = float(m.group(1))
        if elapsed > 1.0:
            print(f"x import took {elapsed:.3f}s; expected <1s (lazy litellm import)")
            return 1
        print(f"  ok: import {elapsed:.3f}s; lazy litellm")
    else:
        print("  ok: import succeeded (timing not parsed)")

    print("-- 8. POSITIVE: status() reflects feature_flag + installed honestly --")
    s = litellm_adapter.status()
    for key in ("stage", "available", "feature_flag", "litellm_installed",
                "ollama_base_url", "note"):
        if key not in s:
            print(f"x status() missing key: {key!r}")
            return 1
    if s["stage"] != 1:
        print(f"x stage should be 1; got {s['stage']}")
        return 1
    # Feature flag is False (default), available must also be False
    if s["feature_flag"] is False and s["available"] is True:
        print("x available cannot be True when feature_flag is False")
        return 1
    if "Stage-1" not in s["note"]:
        print("x note must label this as Stage-1")
        return 1
    print(f"  ok: status() honest; stage=1, available={s['available']}, "
          f"flag={s['feature_flag']}, installed={s['litellm_installed']}")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
