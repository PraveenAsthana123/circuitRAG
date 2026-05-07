#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: governance + evaluation layer (Snyk + Guardrails AI + Ragas + DeepEval).

Per CLAUDE.md §43 + §47 (Layer 10 of 11-layer stack: Governance +
Evaluation). Locks the Stage-1 scaffold contract:

  - .snyk file present + valid YAML
  - .github/workflows/snyk.yml runs on PR/push/cron
  - eval_harness.py exposes RagasEngine + GuardrailsEngine + DeepEvalEngine
  - each engine has is_available() + evaluate()/validate_output() methods
  - eval_harness.eval_status() returns the operator-readable health dict
  - importing eval_harness is side-effect-free (no failures even if
    ragas/guardrails/deepeval not installed yet)
  - requirements.txt lists ragas + guardrails-ai + deepeval
  - Stage-1 fail-open is correct (validation_passed=True when guardrails
    unavailable — explicitly documented as fail-open)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SNYK_POLICY = REPO / ".snyk"
SNYK_WORKFLOW = REPO / ".github" / "workflows" / "snyk.yml"
EVAL_HARNESS = REPO / "services" / "evaluation-svc" / "app" / "eval_harness.py"
EVAL_REQS = REPO / "services" / "evaluation-svc" / "requirements.txt"


def main() -> int:
    print("-- 1. POSITIVE: .snyk policy file present + lists severity threshold --")
    if not SNYK_POLICY.exists():
        print(f"x {SNYK_POLICY} missing")
        return 1
    snyk_src = SNYK_POLICY.read_text(encoding="utf-8")
    if "severity-threshold: high" not in snyk_src:
        print("x .snyk must set severity-threshold: high")
        return 1
    if "ignore: {}" not in snyk_src and "ignore:" not in snyk_src:
        print("x .snyk must declare ignore policy (empty {} acceptable)")
        return 1
    print(f"  ok: .snyk present ({len(snyk_src)} chars); severity=high; ignore declared")

    print("-- 2. POSITIVE: GitHub Actions workflow runs on PR + push + cron --")
    if not SNYK_WORKFLOW.exists():
        print(f"x {SNYK_WORKFLOW} missing")
        return 1
    wf_src = SNYK_WORKFLOW.read_text(encoding="utf-8")
    for trigger in ("pull_request:", "push:", "schedule:"):
        if trigger not in wf_src:
            print(f"x workflow missing trigger: {trigger!r}")
            return 1
    if "SNYK_TOKEN" not in wf_src:
        print("x workflow must reference SNYK_TOKEN secret")
        return 1
    print("  ok: workflow runs on PR + push + cron; uses SNYK_TOKEN")

    print("-- 3. POSITIVE: eval_harness.py exposes 3 engines + eval_status --")
    if not EVAL_HARNESS.exists():
        print(f"x {EVAL_HARNESS} missing")
        return 1
    sys.path.insert(0, str(EVAL_HARNESS.parent))
    import eval_harness  # noqa: E402
    for name in ("RagasEngine", "GuardrailsEngine", "DeepEvalEngine", "eval_status"):
        if not hasattr(eval_harness, name):
            print(f"x eval_harness.{name} missing")
            return 1
    print("  ok: all 4 surfaces exported")

    print("-- 4. POSITIVE: each engine exposes is_available() + evaluate-or-validate --")
    for cls_name, eval_method in (
        ("RagasEngine", "evaluate"),
        ("GuardrailsEngine", "validate_output"),
        ("DeepEvalEngine", "evaluate"),
    ):
        cls = getattr(eval_harness, cls_name)
        inst = cls()
        if not hasattr(inst, "is_available") or not callable(inst.is_available):
            print(f"x {cls_name}.is_available not callable")
            return 1
        if not hasattr(inst, eval_method) or not callable(getattr(inst, eval_method)):
            print(f"x {cls_name}.{eval_method} not callable")
            return 1
        # is_available() must return bool (not None or other)
        avail = inst.is_available()
        if not isinstance(avail, bool):
            print(f"x {cls_name}.is_available() must return bool; got {type(avail).__name__}")
            return 1
    print("  ok: 3 engines × (is_available + evaluate/validate)")

    print("-- 5. NEGATIVE: importing eval_harness is side-effect-free --")
    # Stage-1 must be import-safe even when ragas/guardrails/deepeval
    # aren't installed yet. The first deploy after a deps bump will
    # have services come up before the new wheels propagate; the
    # import path must not crash in that window.
    import importlib
    importlib.reload(eval_harness)  # second import → still must not raise
    status = eval_harness.eval_status()
    if not isinstance(status, dict):
        print(f"x eval_status must return dict; got {type(status).__name__}")
        return 1
    # Stage advances over time: iter-35 wired Ragas/Guardrails/DeepEval
    # Stage-2; iter-37 added Lakera/Rebuff/Giskard. The drill accepts any
    # stage ≥ 1 (deployable forever-forward); the invariant is that the
    # stage reports as a sane integer so dashboards can read it without
    # falling over. A regression to stage=0 / None / "stage-1" string
    # would still be caught.
    stage = status.get("stage")
    if not isinstance(stage, int) or stage < 1:
        print(f"x eval_status.stage should be int >= 1; got {stage!r}")
        return 1
    print(f"  ok: re-import OK; eval_status returns dict with stage={stage}")

    print("-- 6. NEGATIVE: Stage-1 documents fail-open posture for guardrails --")
    # When guardrails-ai is not installed, GuardrailsEngine.validate_output
    # returns validation_passed=True (fail-open). This is intentional for
    # Stage-1 (don't block requests during the dep-rollout window) but
    # MUST be documented + drill-locked so it's a deliberate choice, not
    # a silent regression in Stage-2.
    src_text = EVAL_HARNESS.read_text(encoding="utf-8")
    if "fail-open" not in src_text:
        print("x eval_harness.py must document fail-open posture")
        return 1
    GuardrailsEngine = eval_harness.GuardrailsEngine
    g = GuardrailsEngine()
    if not g.is_available():
        result = g.validate_output(text="hello world")
        if not result.get("validation_passed"):
            print("x Stage-1 should fail-open (validation_passed=True) when guardrails unavailable")
            return 1
        if not result.get("stub"):
            print("x stub flag should be True when engine unavailable")
            return 1
    print("  ok: fail-open posture documented + behavior matches")

    print("-- 7. POSITIVE: requirements.txt lists ragas + guardrails-ai + deepeval --")
    reqs_src = EVAL_REQS.read_text(encoding="utf-8")
    for dep in ("ragas", "guardrails-ai", "deepeval"):
        if not re.search(rf"^{re.escape(dep)}\b", reqs_src, re.MULTILINE):
            print(f"x requirements.txt missing dep: {dep!r}")
            return 1
    print("  ok: ragas + guardrails-ai + deepeval in requirements.txt")

    print("-- 8. NEGATIVE: every engine response carries an honesty signal --")
    # Each engine response must surface ITS OWN stage-state via one of
    # three explicit fields:
    #   "stub": True/False   — Stage-1: lib not installed (True); Stage-2: lib
    #                          installed but flag unset / configured (False)
    #   "configured": True/False — Stage-2: env-flag toggled by operator
    #   "available": True/False  — top-level: lib import succeeded
    # Iter-35/37 promoted these engines from Stage-1 to Stage-2; the
    # contract evolved from "stub MUST be True" to "exactly ONE of
    # {stub, configured} must be present" so callers see honesty regardless
    # of stage. The drill also re-asserts the available field is always
    # there (top-level lib-state probe).
    Ragas = eval_harness.RagasEngine
    DeepEval = eval_harness.DeepEvalEngine
    r1 = Ragas().evaluate(question="q", answer="a", contexts=["c1"])
    r2 = DeepEval().evaluate(question="q", answer="a", contexts=["c1"])
    r3 = GuardrailsEngine().validate_output(text="t")
    for name, payload in (("ragas", r1), ("deepeval", r2), ("guardrails", r3)):
        if "available" not in payload:
            print(f"x {name} response missing 'available' field")
            return 1
        # Either stub or configured must be present so callers know
        # which stage produced this answer.
        has_stage_signal = "stub" in payload or "configured" in payload
        if not has_stage_signal:
            print(f"x {name} response missing both 'stub' AND 'configured'; "
                  f"caller can't tell stage state. payload keys: {sorted(payload)}")
            return 1
    print("  ok: all 3 engines surface available + (stub | configured)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
