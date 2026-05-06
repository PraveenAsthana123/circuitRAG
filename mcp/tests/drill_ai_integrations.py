# RESOURCES: readonly
"""
Drill: AI provider integrations — CrewAI / ChatOllama / ChatXAI.

Per CLAUDE.md §38 (governance), §43 (drill discipline), §52 row 4
(operator API gap), §55.3 (outcome-based contract).

Operator asked to "download grok model, crew AI, chatollama, chatxai"
in a single instruction. Brutal-honesty translation:

  CrewAI:        pip-installable. Drill-locked here.
  ChatOllama:    pip-installable as `langchain-ollama`. Drill-locked.
  ChatXAI:       pip-installable as `langchain-xai`. Requires
                 XAI_API_KEY to actually call. Drill verifies the
                 import + the gap-surfacing on missing key.
  Grok model:    NOT on Ollama registry. xAI has not released
                 distillable Grok weights. The drill verifies that
                 the ai_integrations honest_gap surfaces this fact
                 so future operators don't re-attempt.

Locks (positive):
  L1. crewai is importable; Agent + Task + Crew classes accessible
  L2. langchain_ollama is importable; ChatOllama + OllamaEmbeddings
      classes accessible
  L3. langchain_xai is importable; ChatXAI class accessible
  L4. Paperclip aggregate_ai_integrations() returns documented shape
  L5. ai_integrations is a top-level key in paperclip snapshot v10+

Locks (negative — ≥3 per §43):
  N1. langchain_xai imported AND XAI_API_KEY unset → honest_gap
      explicitly says ChatXAI instantiation will fail. Operator
      misconfig (forgot the key) MUST surface in the dashboard,
      not silently waste calls.

  N2. Grok-not-on-Ollama-registry honest_gap is ALWAYS present
      regardless of integration state. Future change that drops
      this honest_gap would let operators re-discover it the hard
      way. The drill greps for the exact phrase.

  N3. aggregate_ai_integrations does NOT make any actual API calls.
      Drill greps the function source for forbidden invocations
      (.invoke, .ainvoke, .chat, ChatXAI(, ChatOllama(). Snapshot
      surfaces should be liveness probes, not paid-call generators.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ===================================================================
    # Step 1 — crewai importable + key classes accessible
    # ===================================================================
    step("1. crewai importable (Agent + Task + Crew)")
    try:
        crewai = importlib.import_module("crewai")
    except ImportError as exc:
        fail(f"crewai not importable: {exc}")
    for attr in ("Agent", "Task", "Crew"):
        if not hasattr(crewai, attr):
            fail(f"crewai.{attr} missing — install incomplete or version mismatch")
    ver = getattr(crewai, "__version__", "unknown")
    ok(f"crewai version={ver}; Agent/Task/Crew accessible")

    # ===================================================================
    # Step 2 — langchain_ollama importable
    # ===================================================================
    step("2. langchain_ollama importable (ChatOllama + OllamaEmbeddings)")
    try:
        lo = importlib.import_module("langchain_ollama")
    except ImportError as exc:
        fail(f"langchain_ollama not importable: {exc}")
    for attr in ("ChatOllama", "OllamaEmbeddings"):
        if not hasattr(lo, attr):
            fail(f"langchain_ollama.{attr} missing")
    ver = getattr(lo, "__version__", "unknown")
    ok(f"langchain_ollama version={ver}; ChatOllama/OllamaEmbeddings present")

    # ===================================================================
    # Step 3 — langchain_xai importable
    # ===================================================================
    step("3. langchain_xai importable (ChatXAI)")
    try:
        lx = importlib.import_module("langchain_xai")
    except ImportError as exc:
        fail(f"langchain_xai not importable: {exc}")
    if not hasattr(lx, "ChatXAI"):
        fail("langchain_xai.ChatXAI missing")
    ok("langchain_xai loaded; ChatXAI class present")

    # ===================================================================
    # Step 4 — Paperclip aggregator returns documented shape
    # ===================================================================
    step("4. paperclip aggregate_ai_integrations() returns documented shape")
    sys.path.insert(0, str(REPO / "scripts"))
    from scripts import paperclip_manager  # noqa: E402
    if not callable(getattr(paperclip_manager, "aggregate_ai_integrations", None)):
        fail("aggregate_ai_integrations missing from paperclip_manager")
    result = paperclip_manager.aggregate_ai_integrations()
    expected_keys = {"installed_libs", "ollama", "xai_api", "honest_gaps"}
    if not expected_keys.issubset(set(result.keys())):
        fail(f"missing keys: {expected_keys - set(result.keys())}")
    if "crewai" not in result["installed_libs"]:
        fail(f"crewai missing from installed_libs: {result['installed_libs']}")
    ok(f"shape OK: {len(result['installed_libs'])} libs, "
       f"{len(result['honest_gaps'])} honest_gaps")

    # ===================================================================
    # Step 5 — ai_integrations top-level in paperclip snapshot
    # ===================================================================
    step("5. ai_integrations top-level key in paperclip snapshot")
    snap = paperclip_manager.snapshot(window_days=7)
    if "ai_integrations" not in snap:
        fail("ai_integrations missing from snapshot")
    if not isinstance(snap["ai_integrations"], dict):
        fail("ai_integrations must be a dict")
    ok("ai_integrations present at snapshot top level")

    # ===================================================================
    # Step 6 — NEGATIVE: missing XAI_API_KEY surfaces honest_gap
    # ===================================================================
    step("6. NEGATIVE: missing XAI_API_KEY → honest_gap surfaces (not silent)")
    saved = os.environ.pop("XAI_API_KEY", None)
    try:
        ai = paperclip_manager.aggregate_ai_integrations()
        if ai["xai_api"]["key_set"]:
            fail("xai_api.key_set should be False when env unset")
        gap_about_key = any("XAI_API_KEY" in g for g in ai["honest_gaps"])
        if not gap_about_key:
            fail(f"missing honest_gap about XAI_API_KEY: {ai['honest_gaps']}")
    finally:
        if saved is not None:
            os.environ["XAI_API_KEY"] = saved
    ok("missing XAI_API_KEY → honest_gap surfaces 'XAI_API_KEY' phrase")

    # ===================================================================
    # Step 7 — NEGATIVE: Grok-not-on-Ollama honest_gap is ALWAYS present
    # ===================================================================
    step("7. NEGATIVE: Grok-not-on-Ollama-registry honest_gap is constant")
    ai = paperclip_manager.aggregate_ai_integrations()
    grok_gap_present = any(
        "Grok" in g and ("Ollama registry" in g or "ollama registry" in g.lower())
        for g in ai["honest_gaps"]
    )
    if not grok_gap_present:
        fail(
            "Grok-not-on-Ollama honest_gap dropped — operators will re-attempt "
            "`ollama pull grok` and waste time. Re-add the gap."
        )
    ok("Grok-not-on-Ollama-registry honest_gap present (locked invariant)")

    # ===================================================================
    # Step 8 — NEGATIVE: aggregate_ai_integrations makes NO API calls
    # ===================================================================
    step("8. NEGATIVE: aggregate_ai_integrations source has no API call verbs")
    src = (REPO / "scripts" / "paperclip_manager.py").read_text(encoding="utf-8")
    m = re.search(
        r"def aggregate_ai_integrations.*?(?=\ndef \w)",
        src, re.DOTALL,
    )
    if m is None:
        fail("could not locate aggregate_ai_integrations function body")
    body = m.group(0)
    # Forbidden patterns that would indicate a paid API call
    forbidden = (
        ".invoke(",
        ".ainvoke(",
        ".chat(",
        "ChatXAI(",
        "ChatOllama(",
        "Crew(",
        "Agent(",
    )
    leaks = [p for p in forbidden if p in body]
    if leaks:
        fail(
            f"aggregate_ai_integrations contains API-call constructs: {leaks}. "
            f"Snapshot surfaces must be liveness probes, NOT paid-call generators."
        )
    ok("aggregate_ai_integrations is pure-introspection; no API calls")

    # ===================================================================
    # Step 9 — Ollama probe is a single GET (not pull/load)
    # ===================================================================
    step("9. Ollama probe uses GET /api/tags + /api/ps only (no pull/load)")
    if "/api/tags" not in body or "/api/ps" not in body:
        fail("Ollama probe should hit /api/tags + /api/ps")
    if "/api/pull" in body or "/api/generate" in body or "/api/chat" in body:
        fail(
            "aggregate_ai_integrations references /api/pull, /api/generate, or "
            "/api/chat — paperclip MUST NOT trigger model loads or inferences"
        )
    ok("/api/tags + /api/ps only; no /api/pull, /api/generate, /api/chat")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
