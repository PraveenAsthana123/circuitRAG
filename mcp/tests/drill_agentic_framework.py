#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Agentic engineering framework (Tier 1 #1.0) — both directions.

Per CLAUDE.md §43 + §55. Locks the meta-template that every agent
in the system MUST conform to. Empirically prevents future Tier 5
subsystems from drifting into bespoke agent shapes.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "libs" / "py" / "documind_core" / "agentic_framework.py"


def _load():
    spec = importlib.util.spec_from_file_location("agentic_framework", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agentic_framework"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: agentic_framework imports + 5 exports --")
    af = _load()
    for name in ("AgentSpec", "ObservabilityHooks", "validate_agent",
                 "validate_agent_or_raise", "COUNCIL_AGENT_SPECS"):
        if not hasattr(af, name):
            print(f"x step 1: missing export {name}")
            return 1
    print(f"  ok: 5 exports; {len(af.COUNCIL_AGENT_SPECS)} reference agents catalogued")

    print("-- 2. POSITIVE: all 4 council reference specs validate --")
    for spec_dict in af.COUNCIL_AGENT_SPECS:
        try:
            spec = af.AgentSpec.model_validate(spec_dict)
        except Exception as e:
            print(f"x step 2: reference spec {spec_dict['name']!r} fails Pydantic: {e}")
            return 1
        failures = af.validate_agent(spec, repo_root=REPO)
        if failures:
            print(f"x step 2: reference spec {spec_dict['name']!r} repo-validation: {failures}")
            return 1
    print(f"  ok: all 4 council specs (researcher/author/reviewer/advisor) validate")

    print("-- 3. NEGATIVE: invalid role_type → ValidationError --")
    bad_dict = dict(af.COUNCIL_AGENT_SPECS[0])
    bad_dict["role_type"] = "magician"  # not in Literal
    try:
        af.AgentSpec.model_validate(bad_dict)
    except Exception:
        print("  ok: role_type='magician' rejected by Literal type")
    else:
        print("x step 3: invalid role_type accepted")
        return 1

    print("-- 4. NEGATIVE: empty constraints list → repo-validate failure --")
    bad_dict = dict(af.COUNCIL_AGENT_SPECS[0])
    bad_dict["constraints"] = []
    spec = af.AgentSpec.model_validate(bad_dict)
    failures = af.validate_agent(spec, repo_root=REPO)
    if not any("constraints" in f for f in failures):
        print(f"x step 4: empty constraints not flagged: {failures}")
        return 1
    print("  ok: empty constraints rejected (every agent MUST have ≥1 'never do X')")

    print("-- 5. NEGATIVE: phantom drill_path → repo-validate failure --")
    bad_dict = dict(af.COUNCIL_AGENT_SPECS[0])
    bad_dict["drill_path"] = "mcp/tests/drill_does_not_exist.py"
    spec = af.AgentSpec.model_validate(bad_dict)
    failures = af.validate_agent(spec, repo_root=REPO)
    if not any("drill_path does not exist" in f for f in failures):
        print(f"x step 5: phantom drill_path not flagged: {failures}")
        return 1
    print("  ok: phantom drill_path rejected (every agent MUST have a real drill)")

    print("-- 6. NEGATIVE: invalid name (uppercase) → ValidationError --")
    bad_dict = dict(af.COUNCIL_AGENT_SPECS[0])
    bad_dict["name"] = "Researcher"  # uppercase rejected by pattern
    try:
        af.AgentSpec.model_validate(bad_dict)
    except Exception:
        print("  ok: uppercase 'Researcher' rejected by name pattern (kebab/snake only)")
    else:
        print("x step 6: uppercase name accepted")
        return 1

    print("-- 7. NEGATIVE: extra hallucinated field → ValidationError (extra='forbid') --")
    bad_dict = dict(af.COUNCIL_AGENT_SPECS[0])
    bad_dict["operator_email"] = "praveen@example.com"  # extra
    try:
        af.AgentSpec.model_validate(bad_dict)
    except Exception:
        print("  ok: extra 'operator_email' rejected; PII contamination blocked")
    else:
        print("x step 7: extra field accepted")
        return 1

    print("-- 8. POSITIVE: validate_agent_or_raise raises on bad spec --")
    bad_dict = dict(af.COUNCIL_AGENT_SPECS[0])
    bad_dict["drill_path"] = "mcp/tests/drill_phantom.py"
    spec = af.AgentSpec.model_validate(bad_dict)
    try:
        af.validate_agent_or_raise(spec, repo_root=REPO)
    except ValueError as e:
        if "AgentSpec invalid" not in str(e):
            print(f"x step 8: raise message mismatch: {e}")
            return 1
        print("  ok: validate_agent_or_raise raises ValueError with failure list")
    else:
        print("x step 8: validate_agent_or_raise did NOT raise on phantom drill_path")
        return 1

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
