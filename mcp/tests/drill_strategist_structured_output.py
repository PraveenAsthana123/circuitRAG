#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Strategist agent — Pydantic structured output + enhanced prompt.

Pilot iteration of the agent-framework migration. Per advisor guidance,
this drill exercises BOTH directions:
  - valid LLM output → Pydantic schema parses cleanly, no fields lost
  - malformed LLM output → falls back to None (caller heuristic),
    NOT silent fabrication that drops fields

The current bracket-aware regex's bug-tolerance was the gap: it would
accept a payload with `complexity="quantum"` (invalid enum) or extra
hallucinated fields. The Pydantic schema rejects both. This drill
proves the new path is tighter, not just different.

Eight steps. Six negative assertions.

  1. POSITIVE: agent_schemas module imports + 4 exports
  2. POSITIVE: well-formed JSON parses + all fields preserved (round-trip)
  3. NEGATIVE: invalid enum value (complexity='quantum') → None
     (the regex extractor would have ACCEPTED this — proves the
     migration tightens the contract)
  4. NEGATIVE: missing required field (no overall_novelty) → None
  5. NEGATIVE: extra hallucinated field ('reasoning') → None
     (extra='forbid' on the model_config)
  6. NEGATIVE: empty string / no-JSON output → None (no crash)
  7. NEGATIVE: valid JSON wrapped in markdown fences → still parses
     (model often wraps despite "no markdown" rule — fences MUST
     be stripped to honor the prompt's stated intent)
  8. POSITIVE: enhanced prompt has all the rule + example markers
     (regression guard — refactor that drops examples flunks step 8
     before silent prompt-quality drift)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "libs" / "py"))
sys.path.insert(0, str(SVC))


def main() -> int:
    print("-- 1. POSITIVE: agent_schemas module imports + exports --")
    from app.agent_schemas import (
        StrategistOutput,
        StepClassification,
        validate_strategist_output,
        strategist_schema_text,
    )
    print("  ok: 4 exports present")

    print("-- 2. POSITIVE: valid JSON round-trips through validator --")
    valid_payload = {
        "steps": [
            {
                "step_id": "implement",
                "complexity": "medium",
                "novelty": "routine",
                "needs_research": False,
            },
        ],
        "overall_complexity": "medium",
        "overall_novelty": "routine",
        "needs_research": False,
        "summary": "single-step bug fix",
    }
    raw = json.dumps(valid_payload)
    result = validate_strategist_output(raw)
    assert result is not None, f"valid payload rejected: {raw}"
    assert result.overall_complexity == "medium"
    assert result.overall_novelty == "routine"
    assert result.needs_research is False
    assert len(result.steps) == 1
    assert result.steps[0].step_id == "implement"
    print(f"  ok: 5-field schema parses; steps={len(result.steps)}")

    print("-- 3. NEGATIVE: invalid enum value rejected --")
    bad_enum = json.dumps({
        **valid_payload,
        "overall_complexity": "quantum",  # not in {trivial, medium, high}
    })
    result3 = validate_strategist_output(bad_enum)
    assert result3 is None, (
        f"invalid enum 'quantum' was accepted — Pydantic Literal not enforced. "
        "The old regex extractor would have accepted this; the migration "
        "is supposed to tighten the contract."
    )
    print("  ok: complexity='quantum' rejected")

    print("-- 4. NEGATIVE: missing required field rejected --")
    missing_field = json.dumps({
        "steps": valid_payload["steps"],
        "overall_complexity": "medium",
        # overall_novelty MISSING
        "needs_research": False,
        "summary": "incomplete",
    })
    result4 = validate_strategist_output(missing_field)
    assert result4 is None, "missing overall_novelty was accepted — required-field guard broken"
    print("  ok: missing overall_novelty rejected")

    print("-- 5. NEGATIVE: extra hallucinated field rejected --")
    extra_field = json.dumps({
        **valid_payload,
        "reasoning": "I think this should be medium because...",
    })
    result5 = validate_strategist_output(extra_field)
    assert result5 is None, (
        "extra field 'reasoning' was accepted — model_config extra='forbid' "
        "not enforced. Models often hallucinate this field; rejecting forces "
        "the prompt to be tightened rather than silent drift."
    )
    print("  ok: extra 'reasoning' field rejected")

    print("-- 6. NEGATIVE: empty / no-JSON input → None, no crash --")
    assert validate_strategist_output("") is None
    assert validate_strategist_output("I'm sorry, I don't know how to do that.") is None
    assert validate_strategist_output("{this is not json}") is None
    print("  ok: empty / non-JSON / malformed input all return None")

    print("-- 7. NEGATIVE: markdown-fenced JSON parses (fence-stripping required) --")
    fenced = "```json\n" + json.dumps(valid_payload) + "\n```"
    result7 = validate_strategist_output(fenced)
    assert result7 is not None, (
        "markdown-fenced JSON failed to parse; fence-stripping not working. "
        "Models often wrap despite 'no markdown' rule — must be tolerated."
    )
    assert result7.overall_complexity == "medium"
    print("  ok: ```json fence stripped + payload parsed")

    print("-- 8. POSITIVE: enhanced Strategist prompt has all rule + example markers --")
    from app.agent_registry import DEFAULT_AGENT_SPECS
    strategist = next(s for s in DEFAULT_AGENT_SPECS if s.role_id == "strategist")
    prompt = strategist.prompt_template
    for marker in (
        "<role>", "<goal>", "<context>", "<rules>", "<examples>",
        "<output_spec>", "<edge_cases>",
        "Example 1", "Example 2",
        "deploy", "auth", "needs_research",
        "DO NOT add extra fields",
    ):
        assert marker in prompt, (
            f"prompt missing marker {marker!r} — refactor regression. "
            "Enhanced prompt structure (role/goal/context/rules/examples/"
            "output_spec/edge_cases) is what drives reliable structured "
            "output on smaller open models."
        )
    # Length floor: enhanced prompt is much larger than the previous one
    # (~5x). Drift below 1500 chars suggests reverted.
    assert len(prompt) > 1500, (
        f"prompt is only {len(prompt)} chars; enhanced version was much "
        "larger. Likely reverted to short-form prompt."
    )
    print(f"  ok: prompt has 7-section structure + 2 few-shots; {len(prompt)} chars")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
