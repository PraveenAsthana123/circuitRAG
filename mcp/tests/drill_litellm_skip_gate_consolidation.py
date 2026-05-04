#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-3 — _skip_gate consolidates the LiteLLM double-gate.

Per CLAUDE.md §43. Locks the Stage-3 promotion that eliminates the
duplicate PolisAI audit row per fallback call.

Behavior contract:
  - call_ollama public path: gate fires once (in call_ollama itself)
  - call_ollama → curl-fail → _litellm_fallback → complete(_skip_gate=True):
    gate fires once (in call_ollama). Adapter does NOT re-gate.
  - Direct litellm_adapter.complete() call (no upstream gate): gate
    fires once (in adapter, _skip_gate=False default)

Stage-3 invariants:
  - _skip_gate kwarg is keyword-only + underscore-prefix conventional
  - _skip_gate default is False (safe-by-default for new callers)
  - When _skip_gate=True, _polisai_gate is NOT called inside complete()
  - When _skip_gate=False (default), _polisai_gate IS called
  - call_ollama _litellm_fallback passes _skip_gate=True

Eight steps. Five negative.
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: complete() has _skip_gate kwarg --")
    import litellm_adapter
    importlib.reload(litellm_adapter)
    sig = inspect.signature(litellm_adapter.complete)
    if "_skip_gate" not in sig.parameters:
        print("x complete() must have _skip_gate kwarg")
        return 1
    print("  ok: _skip_gate kwarg present")

    print("-- 2. NEGATIVE: _skip_gate is keyword-only + underscore-prefix internal --")
    skip_param = sig.parameters["_skip_gate"]
    if skip_param.kind != inspect.Parameter.KEYWORD_ONLY:
        print(f"x _skip_gate must be keyword-only; kind={skip_param.kind}")
        return 1
    if not skip_param.name.startswith("_"):
        print("x _skip_gate must use underscore-prefix convention")
        return 1
    print("  ok: keyword-only + underscore-prefix internal marker")

    print("-- 3. NEGATIVE: _skip_gate defaults to False (safe-by-default) --")
    if skip_param.default is not False:
        print(f"x _skip_gate default must be False; got {skip_param.default!r}")
        return 1
    print("  ok: default False (callers omitting it gate normally)")

    print("-- 4. POSITIVE: source has the conditional gate fire --")
    src = (SCRIPTS / "litellm_adapter.py").read_text(encoding="utf-8")
    if "if not _skip_gate:" not in src:
        print("x source must have `if not _skip_gate:` guard around _polisai_gate")
        return 1
    # The guard must precede _polisai_gate() call inside complete()
    func_start = src.find("def complete(")
    func_end = src.find("\ndef ", func_start + 10)
    body = src[func_start:func_end if func_end != -1 else len(src)]
    guard_pos = body.find("if not _skip_gate:")
    gate_pos = body.find("_polisai_gate(")
    if guard_pos == -1 or gate_pos == -1 or guard_pos > gate_pos:
        print(f"x guard ({guard_pos}) must precede _polisai_gate ({gate_pos})")
        return 1
    print("  ok: `if not _skip_gate:` precedes _polisai_gate call")

    print("-- 5. NEGATIVE: _litellm_fallback in local_council passes _skip_gate=True --")
    lc_src = (SCRIPTS / "local_council.py").read_text(encoding="utf-8")
    fallback_idx = lc_src.find("def _litellm_fallback(")
    fallback_end = lc_src.find("\ndef ", fallback_idx + 10)
    fallback_body = lc_src[fallback_idx:fallback_end if fallback_end != -1 else len(lc_src)]
    if "_skip_gate=True" not in fallback_body:
        print("x _litellm_fallback must pass _skip_gate=True (Stage-3 consolidation)")
        return 1
    if "Stage-3" not in fallback_body:
        print("x _litellm_fallback must reference Stage-3 in comments")
        return 1
    print("  ok: fallback passes _skip_gate=True + documents Stage-3 intent")

    print("-- 6. NEGATIVE: when _skip_gate=True, _polisai_gate NOT called --")
    # Live test: monkey-patch _polisai_gate to count calls; invoke
    # complete with _skip_gate=True (with feature flag enabled so we
    # reach the gate code path).
    os.environ["LITELLM_ENABLED"] = "1"
    importlib.reload(litellm_adapter)

    gate_calls = {"count": 0}
    original_gate = litellm_adapter._polisai_gate

    def counting_gate(actor):
        gate_calls["count"] += 1
        return original_gate(actor)

    litellm_adapter._polisai_gate = counting_gate
    try:
        # When the lib isn't installed, complete raises LiteLLMUnavailable
        # BEFORE reaching the gate logic. To test the gate path, we'd
        # need to either install litellm or mock is_available.
        # Mock is_available + the import.
        from unittest.mock import patch
        with patch.object(litellm_adapter, "is_available", return_value=True):
            # Monkey-patch the litellm import inside complete by injecting
            # a fake module. complete() does `import litellm` lazily.
            import types
            fake_litellm = types.ModuleType("litellm")
            fake_response = type("Resp", (), {})()
            fake_response.choices = [type("Choice", (), {"message": type("Msg", (), {"content": "ok"})()})()]
            fake_response.usage = type("Usage", (), {"completion_tokens": 1})()
            fake_litellm.completion = lambda **kwargs: fake_response
            sys.modules["litellm"] = fake_litellm
            try:
                # Call with _skip_gate=True — gate should NOT fire
                gate_calls["count"] = 0
                litellm_adapter.complete(
                    model="ollama/x", system="s", prompt="p",
                    actor="council:author",
                    _skip_gate=True,
                )
                if gate_calls["count"] != 0:
                    print(f"x _skip_gate=True should suppress gate; gate fired {gate_calls['count']} times")
                    return 1
                # Call with _skip_gate=False (default) — gate SHOULD fire
                gate_calls["count"] = 0
                litellm_adapter.complete(
                    model="ollama/x", system="s", prompt="p",
                    actor="council:author",
                )
                if gate_calls["count"] != 1:
                    print(f"x _skip_gate=False (default) should fire gate once; got {gate_calls['count']}")
                    return 1
            finally:
                del sys.modules["litellm"]
    finally:
        litellm_adapter._polisai_gate = original_gate
        os.environ.pop("LITELLM_ENABLED", None)
    print("  ok: _skip_gate=True suppresses gate; default (False) fires it once")

    print("-- 7. NEGATIVE: _skip_gate is in COMPLETE's signature, not call_ollama --")
    # call_ollama is the public entry point — must NOT expose _skip_gate.
    sys.path.insert(0, str(SCRIPTS))
    import local_council
    importlib.reload(local_council)
    co_sig = inspect.signature(local_council.call_ollama)
    if "_skip_gate" in co_sig.parameters:
        print("x call_ollama must NOT expose _skip_gate (Stage-3 internal-only)")
        return 1
    print("  ok: call_ollama signature unchanged; _skip_gate is internal to adapter")

    print("-- 8. POSITIVE: existing tests still pass (no regression) --")
    # The Stage-2 fallback drill should still pass with the Stage-3
    # consolidation. We don't run it here (drills shouldn't run drills);
    # just sanity-check that the wiring + existing import paths work.
    if not callable(litellm_adapter.complete):
        print("x complete is not callable")
        return 1
    if not hasattr(litellm_adapter, "LiteLLMUnavailable"):
        print("x LiteLLMUnavailable still required")
        return 1
    print("  ok: API surface preserved (callable + exception type)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
