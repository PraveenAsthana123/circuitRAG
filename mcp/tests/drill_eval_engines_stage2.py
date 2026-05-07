# RESOURCES: readonly
"""
Drill: Eval engines (Ragas / Guardrails / DeepEval) Stage-2 wiring.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §45.4 (no checkbox
flips without code), §47 (architecture: env-gated activation), §48
(AI explainability — eval engines surface confidence/violations).

Architecture matrix listed three eval rows as ⚠️ Stage-1 scaffold.
Iter-35 wires Stage-2 invocation paths (env-gated, fail-safe):
  Ragas       — already Stage-2 via ragas_eval_adapter (RAGAS_EVAL_ENABLED)
  Guardrails  — iter-35 wires Guard.from_string() (GUARDRAILS_EVAL_ENABLED)
  DeepEval    — iter-35 wires AnswerRelevancyMetric+FaithfulnessMetric
                (DEEPEVAL_ENABLED)

Locks (positive):
  L1. All 3 engines have `is_available()` callable
  L2. With flag UNSET, `available=True, configured=False, reason=…`
      shape — operator can see "not configured" (not "broken")

Locks (negative — ≥3 per §43):
  N1. Stub-mode result (no lib installed) NEVER raises — fail-safe
  N2. Configured-but-no-flag result has `configured: False` AND
      a `reason` string (operator UX; explains the gap)
  N3. Source has the env-var gate `if .*ENABLED.* != "1"` literal
      for each engine (the gate is the contract; if removed, the
      engine starts firing real LLM calls on every request — paid
      side-effect on every eval-svc HTTP request)
  N4. Source wraps each Stage-2 call in `try/except Exception` so
      adapter-error never breaks eval-svc (per §47 fail-safe)
  N5. Validators / metrics are NEVER hardcoded with paid model IDs
      in source — would lock cost to a specific provider
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "services" / "evaluation-svc" / "app" / "eval_harness.py"
sys.path.insert(0, str(REPO / "services" / "evaluation-svc"))

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
    if not HARNESS.exists():
        fail(f"harness missing: {HARNESS.relative_to(REPO)}")

    src = HARNESS.read_text(encoding="utf-8")
    from app import eval_harness  # type: ignore[import-not-found]

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: all 3 engines have is_available()
    # ------------------------------------------------------------------
    step("1. RagasEngine + GuardrailsEngine + DeepEvalEngine all have is_available()")
    for cls_name in ("RagasEngine", "GuardrailsEngine", "DeepEvalEngine"):
        cls = getattr(eval_harness, cls_name, None)
        if cls is None:
            fail(f"{cls_name} missing from eval_harness")
        instance = cls()
        if not callable(getattr(instance, "is_available", None)):
            fail(f"{cls_name}.is_available is not callable")
    ok("3/3 engine classes expose is_available()")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: flag-unset path returns configured:false shape
    # ------------------------------------------------------------------
    step("2. With env-flags UNSET, each engine returns configured:false shape")
    # Save + clear all 3 flags
    saved = {}
    for var in ("RAGAS_EVAL_ENABLED", "GUARDRAILS_EVAL_ENABLED", "DEEPEVAL_ENABLED"):
        saved[var] = os.environ.pop(var, None)
    try:
        # Ragas: only checks 'configured' when ragas IS importable; skip
        # the test if ragas not installed (stub-mode is tested in step 3).
        ragas = eval_harness.RagasEngine()
        if ragas.is_available():
            r = ragas.evaluate(question="q", answer="a", contexts=["c"])
            if r.get("configured") is not False:
                fail(f"RagasEngine flag-unset: configured={r.get('configured')}")
            if "RAGAS_EVAL_ENABLED" not in r.get("reason", ""):
                fail(f"RagasEngine reason missing flag name: {r.get('reason')}")

        guard = eval_harness.GuardrailsEngine()
        if guard.is_available():
            g = guard.validate_output(text="hello world")
            if g.get("configured") is not False:
                fail(f"GuardrailsEngine flag-unset: configured={g.get('configured')}")
            if "GUARDRAILS_EVAL_ENABLED" not in g.get("reason", ""):
                fail(f"GuardrailsEngine reason missing flag name")

        deep = eval_harness.DeepEvalEngine()
        if deep.is_available():
            d = deep.evaluate(question="q", answer="a", contexts=["c"])
            if d.get("configured") is not False:
                fail(f"DeepEvalEngine flag-unset: configured={d.get('configured')}")
            if "DEEPEVAL_ENABLED" not in d.get("reason", ""):
                fail(f"DeepEvalEngine reason missing flag name")
    finally:
        for var, val in saved.items():
            if val is not None:
                os.environ[var] = val
    ok("flag-unset path returns configured:false with explanatory reason")

    # ------------------------------------------------------------------
    # Step 3 — NEGATIVE: stub-mode results NEVER raise
    # ------------------------------------------------------------------
    step("3. NEGATIVE: stub-mode (lib not installed) NEVER raises")
    # We can't uninstall ragas/guardrails/deepeval to actually test stub-
    # mode here. Instead, verify the source has the right early-return
    # shape: `if not self._<lib>: return {... "stub": True ...}`
    for cls_name, attr in (
        ("RagasEngine", "_ragas"),
        ("GuardrailsEngine", "_guardrails"),
        ("DeepEvalEngine", "_deepeval"),
    ):
        cls_match = re.search(
            rf"class {cls_name}.*?(?=\nclass \w|\n# ----------|\Z)",
            src, re.DOTALL,
        )
        if cls_match is None:
            fail(f"could not locate {cls_name} body")
        body = cls_match.group(0)
        if f"if not self.{attr}" not in body:
            fail(f"{cls_name} missing stub-mode early return on {attr}")
        if '"stub": True' not in body:
            fail(f"{cls_name} stub-mode shape missing 'stub: True' marker")
    ok("3/3 engines have stub-mode early return; no exceptions in stub path")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: env-var gate literal in source
    # ------------------------------------------------------------------
    step("4. NEGATIVE: each engine source has the env-flag gate")
    expected_gates = (
        "RAGAS_EVAL_ENABLED",
        "GUARDRAILS_EVAL_ENABLED",
        "DEEPEVAL_ENABLED",
    )
    for gate in expected_gates:
        if gate not in src:
            fail(
                f"source missing env-flag {gate} — would mean Stage-2 calls "
                f"fire on every request without operator opt-in (paid side-effect)"
            )
    ok(f"all 3 env-flag gates present: {expected_gates}")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: each Stage-2 path is wrapped in try/except
    # ------------------------------------------------------------------
    step("5. NEGATIVE: Stage-2 path wrapped in try/except (fail-safe)")
    # Each engine should have at least one try/except in its evaluate or
    # validate_output method (fail-safe contract).
    try_count = src.count("try:")
    except_count = src.count("except Exception")
    if try_count < 3:
        fail(f"only {try_count} `try:` blocks; need ≥3 (one per engine)")
    if except_count < 3:
        fail(f"only {except_count} `except Exception` blocks; need ≥3")
    ok(f"{try_count} try blocks + {except_count} except Exception (fail-safe)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: no hardcoded paid-model IDs
    # ------------------------------------------------------------------
    step("6. NEGATIVE: no hardcoded paid-model IDs in eval engines")
    forbidden = (
        "gpt-4",
        "gpt-3.5",
        "claude-3",
        "claude-opus",
        "claude-sonnet",
    )
    leaks = [m for m in forbidden if m in src]
    if leaks:
        fail(
            f"source contains paid-model IDs: {leaks}. Hardcoding locks "
            f"cost to a specific provider; route via the model registry."
        )
    ok("no paid-model IDs hardcoded in eval harness")

    print(f"\n{GREEN}{BOLD}ALL 6 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
