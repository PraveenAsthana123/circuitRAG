#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: NativeComputeWrapper Stage-1 (per §43 + §47 + §56).

Locks the LLVM/MLIR + Circuit Breaker integration pattern from the
operator-supplied spec:

    LLVM/MLIR        = performance engine
    Circuit Breaker  = reliability shield (this wrapper)
    Agent Council    = decision brain
    Observability    = truth layer
    Fallback         = survival path

Contract:
  - Wrapper class accepts (name, native_fn, fallback_fn, timeout_ms)
  - 3 states: closed / open / half-open (per operator spec)
  - On native success: state stays closed, returns native output
  - On native timeout: record_failure(kind=timeout), dispatch fallback,
    return path_taken="fallback:timeout"
  - On native exception: record_failure(kind=error), dispatch fallback
  - On breaker OPEN: skip native entirely, fallback only
  - HALF-OPEN: allow ONE probe; success → close; failure → re-open
  - status() reports breaker_state + counters + Stage-2 next-step

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WRAPPER = REPO / "scripts" / "native_compute_wrapper.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def _native_fast(_query: str) -> str:
    """Stand-in for an LLVM-compiled fast function — instant return."""
    return "native"


def _native_slow(_query: str) -> str:
    """Stand-in for a hung native call — exceeds timeout."""
    time.sleep(2.0)
    return "native_slow"


def _native_broken(_query: str) -> str:
    """Stand-in for a crashing native call."""
    raise RuntimeError("kernel SIGSEGV")


def _fallback(_query: str) -> str:
    """Stand-in for the survival path — pure Python."""
    return "fallback"


def main() -> int:
    print("-- 1. POSITIVE: native_compute_wrapper.py exists + non-trivial --")
    if not WRAPPER.exists():
        print(f"x {WRAPPER} missing")
        return 1
    src = WRAPPER.read_text(encoding="utf-8")
    if len(src) < 5000:
        print(f"x wrapper module too short ({len(src)} chars)")
        return 1
    print(f"  ok: wrapper present ({len(src)} chars)")

    print("-- 2. POSITIVE: 4 contract surfaces exported --")
    os.environ["NATIVE_COMPUTE_WRAPPER_ENABLED"] = "1"
    mod, spec = _load_module(WRAPPER)
    for name in ("NativeComputeWrapper", "NativeComputeWrapperDisabled",
                 "WrapperResult", "is_available"):
        if not hasattr(mod, name):
            print(f"x native_compute_wrapper.{name} missing")
            return 1
    print("  ok: 4 surfaces exported")

    print("-- 3. NEGATIVE: default-deny — instantiation raises when env unset --")
    os.environ.pop("NATIVE_COMPUTE_WRAPPER_ENABLED", None)
    spec.loader.exec_module(mod)  # re-execute against current env
    raised = False
    try:
        mod.NativeComputeWrapper(
            name="test", native_fn=_native_fast, fallback_fn=_fallback,
        )
    except mod.NativeComputeWrapperDisabled as exc:
        raised = True
        if "NATIVE_COMPUTE_WRAPPER_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x instantiation should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites env flag)")

    # Re-enable for the rest of the test
    os.environ["NATIVE_COMPUTE_WRAPPER_ENABLED"] = "1"
    spec.loader.exec_module(mod)

    print("-- 4. POSITIVE: native success path returns path_taken='native' --")
    w = mod.NativeComputeWrapper(
        name="t1", native_fn=_native_fast, fallback_fn=_fallback,
        timeout_ms=500, threshold=3,
    )
    r = w.run("hello")
    if not r.ok or r.output != "native" or r.path_taken != "native":
        print(f"x native success failed: ok={r.ok} output={r.output!r} path={r.path_taken}")
        return 1
    if r.native_latency_ms < 0:
        print(f"x native_latency_ms must be >=0; got {r.native_latency_ms}")
        return 1
    print(f"  ok: native call → ok=True path=native latency={r.native_latency_ms}ms")

    print("-- 5. NEGATIVE: timeout → fallback path, breaker counts the failure --")
    w = mod.NativeComputeWrapper(
        name="t2", native_fn=_native_slow, fallback_fn=_fallback,
        timeout_ms=200, threshold=10,  # high threshold so we don't open after 1
    )
    r = w.run("hello")
    if r.path_taken != "fallback:timeout":
        print(f"x expected path=fallback:timeout; got {r.path_taken}")
        return 1
    if r.output != "fallback":
        print(f"x expected fallback output; got {r.output!r}")
        return 1
    s = w.status()
    if s["counters"]["timeout"] != 1:
        print(f"x timeout counter must be 1; got {s['counters']['timeout']}")
        return 1
    if s["counters"]["fallback_used"] != 1:
        print(f"x fallback_used counter must be 1; got {s['counters']['fallback_used']}")
        return 1
    print("  ok: timeout → fallback; counters incremented")

    print("-- 6. NEGATIVE: native exception → fallback path, breaker tracks error --")
    w = mod.NativeComputeWrapper(
        name="t3", native_fn=_native_broken, fallback_fn=_fallback,
        timeout_ms=500, threshold=10,
    )
    r = w.run("hello")
    if r.path_taken != "fallback:error":
        print(f"x expected path=fallback:error; got {r.path_taken}")
        return 1
    if r.error is None or "SIGSEGV" not in r.error:
        print(f"x error must capture native crash msg; got {r.error!r}")
        return 1
    print("  ok: native exception → fallback:error; error captured")

    print("-- 7. NEGATIVE: breaker OPENs after threshold failures --")
    w = mod.NativeComputeWrapper(
        name="t4", native_fn=_native_broken, fallback_fn=_fallback,
        timeout_ms=500, threshold=3, recovery_s=10,
    )
    # 3 failures → breaker opens
    for _ in range(3):
        w.run("hello")
    if w.state != "open":
        print(f"x breaker should be open after 3 failures; got {w.state}")
        return 1
    # Next call goes straight to fallback (no native call)
    r = w.run("hello")
    if r.path_taken != "fallback:open":
        print(f"x expected fallback:open while breaker open; got {r.path_taken}")
        return 1
    print("  ok: breaker OPEN after threshold; subsequent calls bypass native")

    print("-- 8. POSITIVE: status() reports stage=1 + 3-state breaker contract --")
    s = w.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("name", "enabled_env", "breaker_state", "timeout_ms",
                "threshold", "recovery_s", "counters", "wiring_status",
                "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if s["breaker_state"] not in ("closed", "open", "half-open"):
        print(f"x breaker_state must be in 3-state set; got {s['breaker_state']}")
        return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2 wiring path")
        return 1
    if "BGE" not in s["next_stage"] and "reranker" not in s["next_stage"].lower():
        print("x next_stage must mention BGE/reranker (the canonical use case)")
        return 1
    print("  ok: status reports stage=1 + 3-state breaker + Stage-2 path")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
