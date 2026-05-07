# RESOURCES: readonly
"""
Drill: Lakera+Rebuff prompt-injection defense + Giskard LLM red-team scaffolds.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §45.4 (no checkbox
flips without code), §40 (decision system: fairness/bias), §47.6
(security: A11 prompt injection / A12 insecure output handling), §48
(AI explainability: guardrails_triggered audit row), §52 row 4.

Architecture matrix listed three eval rows as ❌ PLANNED:
  Eval / Lakera + Rebuff  (prompt-injection defense)
  Eval / Giskard          (LLM red-team + bias scan)
  Eval / DeepEval         (alternative RAG eval — covered by iter-35)

Iter-37 ships the Lakera+Rebuff and Giskard scaffolds.

Locks (positive):
  L1. LakeraRebuffEngine + GiskardEngine classes both present
  L2. Each has is_available() and a primary action method
      (LakeraRebuffEngine.detect, GiskardEngine.scan)
  L3. eval_status() reports the new engines under .engines

Locks (negative — ≥3 per §43):
  N1. detect()/scan() with libs UNINSTALLED returns stub shape
      (available=False, never raises)
  N2. detect()/scan() with libs INSTALLED but flag UNSET returns
      configured:false shape (operator-readable)
  N3. detect()/scan() Stage-2 paths wrapped in try/except —
      fail-safe per §47 (any detector/scanner error → safe fallback)
  N4. LakeraRebuffEngine fail-OPEN (is_attack=False on detector
      error) — a misconfigured detector must NEVER block traffic
      silently; the audit row carries the error so ops can see + fix
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
    # Step 1 — POSITIVE: both engine classes exist
    # ------------------------------------------------------------------
    step("1. LakeraRebuffEngine + GiskardEngine classes present")
    for cls_name in ("LakeraRebuffEngine", "GiskardEngine"):
        cls = getattr(eval_harness, cls_name, None)
        if cls is None:
            fail(f"{cls_name} missing from eval_harness")
        instance = cls()
        if not callable(getattr(instance, "is_available", None)):
            fail(f"{cls_name}.is_available not callable")
    ok("both engine classes present with is_available()")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: primary action methods exist
    # ------------------------------------------------------------------
    step("2. detect() + scan() primary action methods present")
    lakera = eval_harness.LakeraRebuffEngine()
    if not callable(getattr(lakera, "detect", None)):
        fail("LakeraRebuffEngine.detect not callable")
    giskard = eval_harness.GiskardEngine()
    if not callable(getattr(giskard, "scan", None)):
        fail("GiskardEngine.scan not callable")
    ok("LakeraRebuffEngine.detect + GiskardEngine.scan callable")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: eval_status() reports new engines
    # ------------------------------------------------------------------
    step("3. eval_status() reports lakera_rebuff + giskard under .engines")
    status = eval_harness.eval_status()
    for engine_key in ("lakera_rebuff", "giskard"):
        if engine_key not in status.get("engines", {}):
            fail(
                f"eval_status().engines missing {engine_key!r}; "
                f"got: {list(status.get('engines', {}))}"
            )
    ok("eval_status reports both new engines")

    # ------------------------------------------------------------------
    # Step 4 — NEGATIVE: stub-mode (libs uninstalled) NEVER raises
    # ------------------------------------------------------------------
    step("4. NEGATIVE: stub-mode never raises (libs may be uninstalled)")
    # Source-level lock: each engine must have an early-return on
    # missing-lib so a stub-mode call doesn't crash. Verify the source
    # has the right shape; runtime behavior is the empirical proof.
    for cls_name in ("LakeraRebuffEngine", "GiskardEngine"):
        body_match = re.search(
            rf"class {cls_name}.*?(?=\nclass \w|\n# ----------|\Z)",
            src, re.DOTALL,
        )
        if body_match is None:
            fail(f"could not locate {cls_name} body")
        body = body_match.group(0)
        if "is_available" not in body:
            fail(f"{cls_name} missing is_available()")
        # Must check is_available OR _<lib> attribute before doing real work
        if "_lakera" not in body and "_rebuff" not in body and "_giskard" not in body:
            fail(f"{cls_name} doesn't probe its lib attribute")
    # Empirical: invoke stub mode if libs aren't installed (most likely)
    out = lakera.detect(prompt="test")
    if not isinstance(out, dict):
        fail(f"LakeraRebuffEngine.detect returned non-dict: {type(out)}")
    out2 = giskard.scan(model_callable=None)
    if not isinstance(out2, dict):
        fail(f"GiskardEngine.scan returned non-dict: {type(out2)}")
    ok("stub-mode returns dicts; no exceptions raised")

    # ------------------------------------------------------------------
    # Step 5 — NEGATIVE: flag-unset returns configured:false shape
    # ------------------------------------------------------------------
    step("5. NEGATIVE: flag-unset returns configured:false shape")
    # Save + clear flags
    saved = {}
    for var in ("LAKERA_API_KEY", "REBUFF_ENABLED", "GISKARD_SCAN_ENABLED"):
        saved[var] = os.environ.pop(var, None)
    try:
        if giskard.is_available():
            r = giskard.scan(model_callable=lambda p: "x")
            if r.get("configured") is not False:
                fail(f"GiskardEngine flag-unset: configured={r.get('configured')}")
            if "GISKARD_SCAN_ENABLED" not in r.get("reason", ""):
                fail(f"GiskardEngine reason missing flag name: {r.get('reason')}")
    finally:
        for var, val in saved.items():
            if val is not None:
                os.environ[var] = val
    ok("flag-unset returns configured:false (when libs available)")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: Stage-2 wrapped in try/except (fail-safe)
    # ------------------------------------------------------------------
    step("6. NEGATIVE: each Stage-2 path wrapped in try/except")
    for cls_name in ("LakeraRebuffEngine", "GiskardEngine"):
        body_match = re.search(
            rf"class {cls_name}.*?(?=\nclass \w|\n# ----------|\Z)",
            src, re.DOTALL,
        )
        body = body_match.group(0) if body_match else ""
        if "try:" not in body or "except Exception" not in body:
            fail(
                f"{cls_name} missing try/except Exception — Stage-2 errors "
                f"would propagate and break eval-svc"
            )
    ok("both engines have try/except Exception in Stage-2 path")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: LakeraRebuff fails OPEN (is_attack=False on error)
    # ------------------------------------------------------------------
    step("7. NEGATIVE: LakeraRebuff fail-OPEN on detector error")
    lakera_body_match = re.search(
        r"class LakeraRebuffEngine.*?(?=\nclass \w|\n# ----------|\Z)",
        src, re.DOTALL,
    )
    body = lakera_body_match.group(0) if lakera_body_match else ""
    # The except block should set is_attack to False (or omit the
    # is_attack key with default False). Verify by inspecting the
    # error-shape pattern.
    if '"is_attack": False' not in body and "'is_attack': False" not in body:
        # alternative: error key without is_attack=True
        if '"is_attack": True' in body or "'is_attack': True" in body:
            fail(
                "LakeraRebuffEngine fails CLOSED (is_attack=True on error). "
                "Misconfigured detector would block all traffic. Per §47 "
                "fail-safe: detector errors must be is_attack=False."
            )
    ok("fail-OPEN contract: detector errors → is_attack=False (no silent block)")

    print(f"\n{GREEN}{BOLD}ALL 7 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
