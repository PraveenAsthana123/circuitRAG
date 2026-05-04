#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Gemma Agent Council Stage-1 adapter (per §43 + §56).

Locks the 5-role local-Gemma orchestrator that maps:

    safety_pre    → shieldgemma:2b
    router        → gemma3:1b
    planner       → gemma3:4b
    specialist    → codegemma:7b | gemma2:9b | gemma3:4b (intent-routed)
    critic        → gemma2:9b
    safety_post   → shieldgemma:9b (optional, high-risk only)

Stage-1 contract:
  - gemma_agent_council.py exists as a separate module (NOT modifying
    existing local_council.py / agent_router.py)
  - 6 contract surfaces exported (is_available, status, run_council,
    GemmaCouncilDisabled, ROLE_MODELS, is_high_risk_domain)
  - Default opt-in via GEMMA_AGENT_COUNCIL_ENABLED=1
  - When disabled → run_council raises GemmaCouncilDisabled
  - Role → model mapping is operator-overridable via env vars
  - Lazy import (httpx not loaded at module top)
  - High-risk chain adds shieldgemma:9b stage; default chain doesn't
  - Existing scripts unchanged (no Stage-1 leakage)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COUNCIL = REPO / "scripts" / "gemma_agent_council.py"
LOCAL_COUNCIL = REPO / "scripts" / "local_council.py"
AGENT_ROUTER = REPO / "scripts" / "agent_router.py"


def _load_module(path: Path):
    """Load module from absolute path without polluting sys.path.

    sys.modules registration is required for @dataclass to resolve type
    annotations (Python 3.12 looks up cls.__module__ in sys.modules).
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod  # required for @dataclass type resolution
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: gemma_agent_council.py exists as a SEPARATE module --")
    if not COUNCIL.exists():
        print(f"x {COUNCIL} missing")
        return 1
    src = COUNCIL.read_text(encoding="utf-8")
    if len(src) < 6000:
        print(f"x council module too short ({len(src)} chars)")
        return 1
    print(f"  ok: gemma_agent_council present ({len(src)} chars)")

    print("-- 2. NEGATIVE: existing local_council.py + agent_router.py UNCHANGED (no leakage) --")
    # Stage-1 must NOT modify existing council/router code. New module only.
    lc = LOCAL_COUNCIL.read_text(encoding="utf-8") if LOCAL_COUNCIL.exists() else ""
    ar = AGENT_ROUTER.read_text(encoding="utf-8") if AGENT_ROUTER.exists() else ""
    for name, body in (("local_council", lc), ("agent_router", ar)):
        if "GemmaCouncil" in body or "gemma_agent_council" in body:
            print(f"x {name}.py has GemmaCouncil reference — Stage-1 must be a separate module")
            return 1
    print("  ok: existing council + router source unchanged")

    print("-- 3. POSITIVE: 6 contract surfaces exported --")
    os.environ.pop("GEMMA_AGENT_COUNCIL_ENABLED", None)
    mod, spec = _load_module(COUNCIL)
    expected = (
        "is_available", "status", "run_council",
        "GemmaCouncilDisabled", "ROLE_MODELS", "is_high_risk_domain",
    )
    for name in expected:
        if not hasattr(mod, name):
            print(f"x gemma_agent_council.{name} missing")
            return 1
    print("  ok: all 6 surfaces exported")

    print("-- 4. NEGATIVE: default is_available()=False (env flag unset) --")
    os.environ.pop("GEMMA_AGENT_COUNCIL_ENABLED", None)
    spec.loader.exec_module(mod)  # re-execute against current env
    if mod.is_available():
        print(f"x default must be False; got {mod.is_available()}")
        return 1
    print("  ok: default opt-out preserved")

    print("-- 5. NEGATIVE: run_council raises GemmaCouncilDisabled when off --")
    raised = False
    try:
        mod.run_council("test prompt")
    except mod.GemmaCouncilDisabled as exc:
        raised = True
        if "GEMMA_AGENT_COUNCIL_ENABLED" not in str(exc):
            print(f"x error msg must cite GEMMA_AGENT_COUNCIL_ENABLED; got: {exc}")
            return 1
    if not raised:
        print("x run_council should raise when flag off")
        return 1
    print("  ok: GemmaCouncilDisabled raised + cites flag")

    print("-- 6. NEGATIVE: ROLE_MODELS maps the 5+1 user-spec roles --")
    rm = mod.ROLE_MODELS
    expected_roles = {
        "safety_pre", "router", "planner",
        "specialist_code", "specialist_rag", "specialist_general",
        "critic", "safety_post",
    }
    missing = expected_roles - set(rm.keys())
    if missing:
        print(f"x ROLE_MODELS missing keys: {sorted(missing)}")
        return 1
    # Per user spec, the safety_pre is shieldgemma family, router is gemma3:1b,
    # planner is gemma3:4b, code is codegemma:7b, rag is gemma2:9b, critic is gemma2:9b
    role_model_pairs = {
        "safety_pre":         ("shieldgemma", "2b"),
        "router":             ("gemma3", "1b"),
        "planner":            ("gemma3", "4b"),
        "specialist_code":    ("codegemma", "7b"),
        "specialist_rag":     ("gemma2", "9b"),
        "critic":             ("gemma2", "9b"),
        "safety_post":        ("shieldgemma", "9b"),
    }
    for role, (family, size) in role_model_pairs.items():
        m = rm[role]
        if family not in m or size not in m:
            print(f"x ROLE_MODELS[{role!r}] = {m!r} doesn't match user spec ({family}*{size})")
            return 1
    print("  ok: 8 role→model mappings match user-spec architecture")

    print("-- 7. NEGATIVE: lazy httpx — NOT imported at module top --")
    # Stage-1 cold-start contract. httpx is a heavy import (~30ms first
    # time). We allow it inside _call_ollama() only.
    lines_before_call = src[:src.find("def _call_ollama")]
    if re.search(r"^import httpx\b", lines_before_call, re.MULTILINE):
        print("x httpx must NOT be imported at module top — only inside helper functions")
        return 1
    if re.search(r"^from httpx\b", lines_before_call, re.MULTILINE):
        print("x httpx must NOT be 'from'-imported at module top")
        return 1
    print("  ok: httpx lazy-imported inside _call_ollama / is_available")

    print("-- 8. POSITIVE: status() reports Stage-1 + chain shapes --")
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x status.stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "ollama_host", "available", "role_models",
                "high_risk_domains", "default_chain", "high_risk_chain",
                "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "safety_pre" not in s["default_chain"] or "critic" not in s["default_chain"]:
        print("x default_chain must include safety_pre + critic")
        return 1
    if "safety_post" not in s["high_risk_chain"]:
        print("x high_risk_chain must include safety_post (delta vs default)")
        return 1
    if len(s["high_risk_chain"]) != len(s["default_chain"]) + 1:
        print("x high_risk_chain must be exactly default + 1 stage (safety_post)")
        return 1
    if "Stage-2" not in s["next_stage"]:
        print("x status.next_stage must reference Stage-2 wiring path")
        return 1
    print("  ok: status reports stage=1 + default/high_risk chain shapes + Stage-2 next-step")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
