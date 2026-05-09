#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: BGE reranker protected by NativeComputeWrapper — Stage-2 wiring.

Locks the Stage-2 promotion that:
  - bge_reranker_protected.py exists as a SEPARATE module (not modifying
    bge_reranker or native_compute_wrapper)
  - Composes Stage-1 BGE adapter + Stage-1 NativeComputeWrapper
  - Default-deny: BOTH BGE_RERANKER_ENABLED=1 AND
    NATIVE_COMPUTE_WRAPPER_ENABLED=1 must be set
  - protected_rerank() returns RRF order on disabled / timeout / error /
    breaker-open (NEVER raises — silent pass-through preserves caller pipeline)
  - Wrapper instance cached at module level (per-process breaker state)
  - status() reports stage=2 + composed snapshot from both Stage-1 adapters
    and truthful Stage-4 empirical next step after hot-path wiring exists
  - Drill imports module top-level cleanly without crashing

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROTECTED = REPO / "services" / "retrieval-svc" / "app" / "services" / "bge_reranker_protected.py"
BGE = REPO / "services" / "retrieval-svc" / "app" / "services" / "bge_reranker.py"
WRAPPER = REPO / "scripts" / "native_compute_wrapper.py"


def _load_module(path: Path, name: str | None = None):
    spec = importlib.util.spec_from_file_location(name or path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name or path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: bge_reranker_protected.py exists + non-trivial --")
    if not PROTECTED.exists():
        print(f"x {PROTECTED} missing")
        return 1
    src = PROTECTED.read_text(encoding="utf-8")
    if len(src) < 3500:
        print(f"x protected module too short ({len(src)} chars)")
        return 1
    print(f"  ok: bge_reranker_protected present ({len(src)} chars)")

    print("-- 2. NEGATIVE: BGE Stage-1 + NativeComputeWrapper sources UNCHANGED --")
    bge_src = BGE.read_text(encoding="utf-8")
    wrap_src = WRAPPER.read_text(encoding="utf-8")
    if (
        "from app.services.bge_reranker_protected" in bge_src
        or "import bge_reranker_protected" in bge_src
        or "protected_rerank(" in bge_src
    ):
        print("x bge_reranker.py has Stage-2 wiring leakage — must be a separate module")
        return 1
    if "bge_reranker_protected" in wrap_src or "protected_rerank" in wrap_src:
        print("x native_compute_wrapper.py has Stage-2 leakage")
        return 1
    print("  ok: both Stage-1 modules unchanged (Stage-2 is purely additive)")

    print("-- 3. POSITIVE: composes both Stage-1 adapter imports --")
    # The protected module must import from both. Done lazily inside
    # _get_wrapper(); top-level import only typing helpers.
    if "from native_compute_wrapper import NativeComputeWrapper" not in src:
        print("x must import NativeComputeWrapper from native_compute_wrapper")
        return 1
    if "from app.services import bge_reranker" not in src and "import bge_reranker" not in src:
        print("x must import bge_reranker (Stage-1 BGE adapter)")
        return 1
    print("  ok: composes both Stage-1 adapters")

    print("-- 4. NEGATIVE: requires BOTH env flags (default-deny composition) --")
    # Stage-2 inherits Stage-1 default-deny posture from BOTH parents.
    # Setting only one flag must NOT enable the protected wrapper.
    os.environ.pop("BGE_RERANKER_ENABLED", None)
    os.environ.pop("NATIVE_COMPUTE_WRAPPER_ENABLED", None)
    mod, spec = _load_module(PROTECTED, "bge_reranker_protected")
    if mod.is_available():
        print("x is_available() must be False when both env flags unset")
        return 1
    # Set only ONE flag
    os.environ["BGE_RERANKER_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    if mod.is_available():
        print("x is_available() must require BOTH env flags; got True with only BGE flag")
        return 1
    os.environ.pop("BGE_RERANKER_ENABLED", None)
    os.environ["NATIVE_COMPUTE_WRAPPER_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    if mod.is_available():
        print("x is_available() must require BOTH env flags; got True with only wrapper flag")
        return 1
    os.environ.pop("NATIVE_COMPUTE_WRAPPER_ENABLED", None)
    print("  ok: requires BOTH BGE_RERANKER_ENABLED + NATIVE_COMPUTE_WRAPPER_ENABLED")

    print("-- 5. NEGATIVE: protected_rerank silent-passes when disabled (no exception) --")
    # Stage-2 contract: don't break the caller's pipeline when adapters
    # are off. Return the original chunks (RRF order) unchanged. NEVER
    # raise — that would break callers that expect Stage-2 to be a
    # transparent enhancement.
    spec.loader.exec_module(mod)
    raised = False
    try:
        out = mod.protected_rerank("test", [{"text": "a"}, {"text": "b"}])
        if not isinstance(out, list) or len(out) != 2:
            print(f"x silent-pass must return list of same length; got {out!r}")
            return 1
    except Exception as exc:
        raised = True
        print(f"x protected_rerank must NOT raise when disabled; got: {exc}")
        return 1
    if raised:
        return 1
    print("  ok: silent pass-through preserves chunks when disabled")

    print("-- 6. NEGATIVE: top_k truncation works on the disabled path too --")
    out = mod.protected_rerank("test", [{"text": "a"}, {"text": "b"}, {"text": "c"}], top_k=2)
    if len(out) != 2:
        print(f"x top_k=2 must return 2 chunks; got {len(out)}")
        return 1
    print("  ok: top_k truncation works on silent-pass path")

    print("-- 7. NEGATIVE: timeout config is operator-overridable via env --")
    # Sanity: Stage-2 wrapper params come from env so ops can tune
    # production timeout/threshold/recovery without code changes.
    if "BGE_WRAPPER_TIMEOUT_MS" not in src:
        print("x wrapper timeout must be env-overridable via BGE_WRAPPER_TIMEOUT_MS")
        return 1
    if "BGE_WRAPPER_THRESHOLD" not in src:
        print("x wrapper threshold must be env-overridable via BGE_WRAPPER_THRESHOLD")
        return 1
    if "BGE_WRAPPER_RECOVERY_S" not in src:
        print("x wrapper recovery must be env-overridable via BGE_WRAPPER_RECOVERY_S")
        return 1
    print("  ok: 3 wrapper params all env-overridable")

    print("-- 8. POSITIVE: status() reports stage=2 + Stage-4 empirical next path --")
    s = mod.status()
    if s.get("stage") != 2:
        print(f"x stage must be 2; got {s.get('stage')}")
        return 1
    for key in ("both_opted_in", "available", "timeout_ms",
                "threshold", "recovery_s", "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-4" not in s["next_stage"]:
        print("x next_stage must reference Stage-4 empirical promotion path")
        return 1
    if "RAG-test" not in s["next_stage"] and "precision" not in s["next_stage"].lower():
        print("x next_stage must mention empirical RAG-test/precision evaluation")
        return 1
    if "BGE_RERANKER_IN_HOT_PATH" not in s["wiring_status"]:
        print("x wiring_status must mention the hot-path opt-in flag")
        return 1
    print("  ok: status reports stage=2 + Stage-4 empirical next step")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
