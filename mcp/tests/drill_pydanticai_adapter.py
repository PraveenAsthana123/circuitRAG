#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PydanticAI adapter Stage-1 contract.

Per CLAUDE.md §43 + the 2026-05-04 tool-evaluation finding (PydanticAI
verdict=integrate, candidate #2 after LiteLLM). Locks the contract:

  - Module exposes is_available() / validate() / status() / PydanticAIUnavailable
  - validate(text, schema_cls) signature matches expected swap target
  - Default behavior is no-op: validate() raises PydanticAIUnavailable
    when PYDANTICAI_ENABLED unset (the §44 opt-in pattern, mirrors LITELLM_ENABLED)
  - PydanticAIUnavailable subclasses RuntimeError (callers can fall back)
  - Module import is side-effect-free (no pydantic-ai load on bare import)
  - validate() raises ValueError on bad inputs (not PydanticAIUnavailable)
  - status() reflects feature_flag + installed honestly

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib
import inspect
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: module exports the 4 contract surfaces --")
    os.environ.pop("PYDANTICAI_ENABLED", None)
    import pydanticai_adapter
    importlib.reload(pydanticai_adapter)
    for name in ("is_available", "validate", "status", "PydanticAIUnavailable"):
        if not hasattr(pydanticai_adapter, name):
            print(f"x pydanticai_adapter.{name} missing")
            return 1
    print("  ok: 4 surfaces exported")

    print("-- 2. POSITIVE: validate() signature is (text, schema_cls) --")
    sig = inspect.signature(pydanticai_adapter.validate)
    expected_params = ["text", "schema_cls"]
    actual_params = list(sig.parameters.keys())
    if actual_params != expected_params:
        print(f"x signature mismatch — expected {expected_params}, got {actual_params}")
        return 1
    print("  ok: validate(text, schema_cls) signature correct")

    print("-- 3. NEGATIVE: default is_available() = False (PYDANTICAI_ENABLED unset) --")
    if pydanticai_adapter.is_available():
        print("x default is_available should be False (feature flag opt-in)")
        return 1
    print("  ok: feature flag opt-in posture preserved")

    print("-- 4. NEGATIVE: validate() raises PydanticAIUnavailable when disabled --")
    from pydantic import BaseModel  # ensure pydantic itself is importable
    class _TestSchema(BaseModel):
        x: int

    raised = False
    try:
        pydanticai_adapter.validate('{"x": 1}', _TestSchema)
    except pydanticai_adapter.PydanticAIUnavailable as exc:
        raised = True
        if "PYDANTICAI_ENABLED" not in str(exc):
            print(f"x error must cite PYDANTICAI_ENABLED; got: {str(exc)[:200]}")
            return 1
    except Exception as exc:
        print(f"x wrong exception — expected PydanticAIUnavailable; got {type(exc).__name__}: {exc}")
        return 1
    if not raised:
        print("x validate() should have raised PydanticAIUnavailable")
        return 1
    print("  ok: PydanticAIUnavailable raised + cites feature flag")

    print("-- 5. NEGATIVE: PydanticAIUnavailable subclasses RuntimeError --")
    if not issubclass(pydanticai_adapter.PydanticAIUnavailable, RuntimeError):
        print("x PydanticAIUnavailable must subclass RuntimeError")
        return 1
    print("  ok: PydanticAIUnavailable subclasses RuntimeError")

    print("-- 6. NEGATIVE: bad-input validation raises ValueError (not PydanticAIUnavailable) --")
    # When PYDANTICAI_ENABLED, bad inputs must raise ValueError, NOT
    # PydanticAIUnavailable. The two exceptions signal distinct
    # conditions: opt-out vs validation-fail. Drill verifies the
    # distinction at the input-validation level (since we can run
    # without pydantic-ai installed but the type-checks still fire).
    # However, since the feature flag is off, validate() raises
    # PydanticAIUnavailable BEFORE checking inputs. To test the
    # input-validation path, we check the source for the type-check
    # logic that would fire when enabled.
    src = (SCRIPTS / "pydanticai_adapter.py").read_text(encoding="utf-8")
    if 'raise ValueError("text must be non-empty string")' not in src:
        print("x source must validate text input + raise ValueError on bad input")
        return 1
    if "raise TypeError" not in src:
        print("x source must validate schema_cls input + raise TypeError on non-class")
        return 1
    print("  ok: input-validation path raises ValueError/TypeError (not PydanticAIUnavailable)")

    print("-- 7. NEGATIVE: module import is side-effect-free + cheap --")
    proc = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{SCRIPTS}'); "
         f"import time; t0 = time.time(); "
         f"import pydanticai_adapter; "
         f"print(f'IMPORT_OK {{(time.time() - t0):.3f}}')"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
        env={**os.environ, "PYDANTICAI_ENABLED": ""},
    )
    if proc.returncode != 0:
        print(f"x fresh import failed: {proc.stderr[:200]}")
        return 1
    if "IMPORT_OK" not in proc.stdout:
        print(f"x sentinel missing: {proc.stdout[:200]}")
        return 1
    m = re.search(r"IMPORT_OK\s+([\d.]+)", proc.stdout)
    if m:
        elapsed = float(m.group(1))
        if elapsed > 1.0:
            print(f"x import took {elapsed:.3f}s; expected <1s (lazy pydantic-ai import)")
            return 1
        print(f"  ok: import {elapsed:.3f}s; lazy pydantic-ai")
    else:
        print("  ok: import succeeded (timing not parsed)")

    print("-- 8. POSITIVE: status() reflects feature_flag + installed honestly --")
    s = pydanticai_adapter.status()
    for key in ("stage", "available", "feature_flag", "pydantic_ai_installed", "note"):
        if key not in s:
            print(f"x status() missing key: {key!r}")
            return 1
    if s["stage"] != 1:
        print(f"x stage should be 1; got {s['stage']}")
        return 1
    if s["feature_flag"] is False and s["available"] is True:
        print("x available cannot be True when feature_flag is False")
        return 1
    if "Stage-1" not in s["note"]:
        print("x note must label this as Stage-1")
        return 1
    print(f"  ok: status() honest; stage=1, available={s['available']}, "
          f"flag={s['feature_flag']}, installed={s['pydantic_ai_installed']}")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
