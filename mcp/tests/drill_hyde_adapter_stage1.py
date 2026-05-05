#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: HyDE adapter Stage-1 (per §43 + §56).

Locks the Stage-1 HyDE adapter that closes the rag-deep-test recall
gap (Q1 + Q2 returned 0 useful chunks against off-topic corpus).

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "scripts" / "hyde_adapter.py"
RETRIEVER = REPO / "services" / "retrieval-svc" / "app" / "services" / "hybrid_retriever.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: hyde_adapter.py exists + non-trivial size --")
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing")
        return 1
    src = ADAPTER.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x hyde_adapter too short ({len(src)} chars)")
        return 1
    print(f"  ok: hyde_adapter present ({len(src)} chars)")

    print("-- 2. NEGATIVE: HybridRetriever UNCHANGED (Stage-2 wires) --")
    if RETRIEVER.exists():
        ret_src = RETRIEVER.read_text(encoding="utf-8")
        if "hyde_adapter" in ret_src or "HyDEResult" in ret_src:
            print("x HybridRetriever has HyDE reference — Stage-2 hasn't landed yet")
            return 1
    print("  ok: HybridRetriever unchanged (Stage-1 purely additive)")

    print("-- 3. POSITIVE: 4 contract surfaces exported --")
    os.environ.pop("HYDE_ENABLED", None)
    mod, spec = _load_module(ADAPTER)
    for name in ("is_available", "status", "generate", "HyDEResult", "HyDEDisabled"):
        if not hasattr(mod, name):
            print(f"x hyde_adapter.{name} missing")
            return 1
    print("  ok: 5 surfaces exported (is_available, status, generate, HyDEResult, HyDEDisabled)")

    print("-- 4. NEGATIVE: default-deny — generate() raises when env unset --")
    os.environ.pop("HYDE_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.generate("test query")
    except mod.HyDEDisabled as exc:
        raised = True
        if "HYDE_ENABLED" not in str(exc):
            print(f"x error msg must cite HYDE_ENABLED; got: {exc}")
            return 1
    if not raised:
        print("x generate() should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites HYDE_ENABLED)")

    print("-- 5. NEGATIVE: HyDEResult exposes ok + hypothetical + error fields --")
    r = mod.HyDEResult(
        ok=False, hypothetical="", original_query="q",
        elapsed_ms=0, model="x",
    )
    for fname in ("ok", "hypothetical", "original_query", "elapsed_ms", "model", "error"):
        if not hasattr(r, fname):
            print(f"x HyDEResult missing field: {fname}")
            return 1
    print("  ok: HyDEResult has ok + hypothetical + original_query + elapsed_ms + model + error")

    print("-- 6. NEGATIVE: lazy httpx (NOT at module top) --")
    # The HyDE adapter shouldn't pay httpx import cost at module load
    # for callers that don't use it.
    lines_before_def = src[:src.find("def is_available")]
    if re.search(r"^import httpx\b", lines_before_def, re.MULTILINE):
        print("x httpx must NOT be imported at module top")
        return 1
    if re.search(r"^from httpx\b", lines_before_def, re.MULTILINE):
        print("x httpx must NOT be 'from'-imported at module top")
        return 1
    print("  ok: httpx lazy-imported inside generate()")

    print("-- 7. NEGATIVE: transport error returns ok=False (NOT raises) --")
    # Per the contract: generate() raises ONLY on disabled-flag. All
    # other errors (Ollama down, timeout, empty response) return
    # ok=False + .error so caller can fall back to original-query
    # retrieval. This is the failsafe shape.
    os.environ["HYDE_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    # Point at an unreachable Ollama host to force transport failure
    os.environ["OLLAMA_HOST"] = "http://127.0.0.1:1"
    spec.loader.exec_module(mod)
    raised_t = False
    try:
        result = mod.generate("test query")
    except Exception:
        raised_t = True
    if raised_t:
        print("x generate() must NOT raise on transport error; should return ok=False")
        return 1
    if result.ok:
        print(f"x unreachable host should yield ok=False; got ok={result.ok}")
        return 1
    if not result.error:
        print("x failed result must populate .error field")
        return 1
    os.environ.pop("OLLAMA_HOST", None)
    print(f"  ok: transport error → ok=False, error={result.error[:50]!r}")

    print("-- 8. POSITIVE: status() reports stage=1 + heuristic + Stage-2 path --")
    os.environ["HYDE_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "available", "model", "max_tokens",
                "timeout_s", "ollama_host", "wiring_status",
                "next_stage", "heuristic"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2")
        return 1
    if "HybridRetriever" not in s["next_stage"]:
        print("x next_stage must mention HybridRetriever (Stage-2 wiring site)")
        return 1
    if "min_score" not in s["next_stage"].lower() and "empty" not in s["next_stage"].lower():
        print("x next_stage must mention the min_score-empty heuristic trigger")
        return 1
    if "easy queries" not in s["heuristic"].lower() and "latency" not in s["heuristic"].lower():
        print("x heuristic field must explain WHEN to fire HyDE (not always)")
        return 1
    print("  ok: status reports stage=1 + Stage-2 wiring + heuristic")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
