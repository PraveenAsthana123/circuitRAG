#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: CouncilProposal Pydantic schema — both directions locked.

Tier 1 #1 of the brutal-feedback list. The session's empirical evidence
showed 0 of 6 council attempts produced applicable diffs through the
old regex-extraction path. This iteration moved AUTHOR output through
a Pydantic CouncilProposal schema; the drill locks both directions:

  - valid AUTHOR JSON → typed CouncilProposal with all fields
  - every empirically-observed failure mode → None (rejected)

Eight steps. Six negative assertions.

  1. POSITIVE: council_schemas module imports + 4 exports
  2. POSITIVE: well-formed JSON parses cleanly (round-trip)
  3. NEGATIVE: tokenizer artifact in file_path → None
     (closes the empirical 2/5 deepseek failure)
  4. NEGATIVE: tokenizer artifact in unified_diff → None
  5. NEGATIVE: unified_diff missing `--- `/`+++ `/`@@` markers → None
     (closes the "model wrote prose claiming a fix" failure)
  6. NEGATIVE: extra hallucinated field ('reasoning') → None
     (closes the model_config extra='forbid' contract)
  7. NEGATIVE: phantom file_path (path doesn't resolve) → None
     when repo= is provided
  8. POSITIVE: PROMPT_ADDENDUM has all the rule markers + schema
     embedded (regression guard against silent prompt drift)
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "scripts" / "council_schemas.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("council_schemas", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load council_schemas from {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["council_schemas"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_valid_payload() -> dict:
    return {
        "file_path": "scripts/council_schemas.py",  # this file exists
        "rule_code": "UP035",
        "summary": "swap typing.Callable to collections.abc.Callable",
        "unified_diff": (
            "--- scripts/council_schemas.py\n"
            "+++ scripts/council_schemas.py\n"
            "@@ -1 +1 @@\n"
            "-from typing import Callable\n"
            "+from collections.abc import Callable\n"
        ),
        "confidence": 0.9,
        "risks": [],
    }


def main() -> int:
    print("-- 1. POSITIVE: council_schemas module imports + exports --")
    cs = _load()
    for name in (
        "CouncilProposal",
        "validate_council_proposal",
        "PROMPT_ADDENDUM",
        "proposal_schema_text",
    ):
        if not hasattr(cs, name):
            print(f"x step 1: missing export {name}")
            return 1
    print("  ok: 4 exports present")

    print("-- 2. POSITIVE: valid AUTHOR JSON parses + all fields preserved --")
    raw = json.dumps(_make_valid_payload())
    result = cs.validate_council_proposal(raw, repo=REPO)
    if result is None:
        print(f"x step 2: valid payload rejected. payload={raw[:200]}")
        return 1
    assert result.rule_code == "UP035"
    assert result.confidence == 0.9
    assert "Callable" in result.unified_diff
    print(f"  ok: 6-field schema parsed; file_path={result.file_path}")

    print("-- 3. NEGATIVE: tokenizer artifact in file_path → rejected --")
    bad_payload = _make_valid_payload()
    bad_payload["file_path"] = "scripts/<｜begin▁of▁sentence｜>schemas.py"
    result3 = cs.validate_council_proposal(json.dumps(bad_payload))
    if result3 is not None:
        print("x step 3: tokenizer artifact in file_path was accepted")
        return 1
    print("  ok: deepseek tokenizer artifact rejected at field validator")

    print("-- 4. NEGATIVE: tokenizer artifact in unified_diff → rejected --")
    bad_payload = _make_valid_payload()
    bad_payload["unified_diff"] = bad_payload["unified_diff"].replace(
        "scripts/", "<｜begin▁of▁sentence｜>scripts/"
    )
    result4 = cs.validate_council_proposal(json.dumps(bad_payload))
    if result4 is not None:
        print("x step 4: tokenizer artifact in diff was accepted")
        return 1
    print("  ok: tokenizer artifact in diff rejected")

    print("-- 5. NEGATIVE: diff missing unified-diff markers → rejected --")
    bad_payload = _make_valid_payload()
    bad_payload["unified_diff"] = "Sure, I'll add a semicolon to fix the error"
    result5 = cs.validate_council_proposal(json.dumps(bad_payload))
    if result5 is not None:
        print("x step 5: diff without `--- `/`+++ `/`@@` markers was accepted")
        return 1
    print("  ok: prose-without-markers rejected (catches model 'I'll fix it' replies)")

    print("-- 6. NEGATIVE: extra hallucinated field → rejected (extra=forbid) --")
    bad_payload = _make_valid_payload()
    bad_payload["reasoning"] = "I think this fix is correct because..."
    result6 = cs.validate_council_proposal(json.dumps(bad_payload))
    if result6 is not None:
        print("x step 6: extra 'reasoning' field was accepted")
        return 1
    print("  ok: extra field rejected; forces prompt to be source of truth")

    print("-- 7. NEGATIVE: phantom file_path → rejected when repo= provided --")
    bad_payload = _make_valid_payload()
    bad_payload["file_path"] = "scripts/this_file_does_not_exist_anywhere.py"
    result7 = cs.validate_council_proposal(json.dumps(bad_payload), repo=REPO)
    if result7 is not None:
        print("x step 7: phantom file_path was accepted")
        return 1
    print("  ok: phantom path rejected at filesystem check")

    print("-- 8. POSITIVE: PROMPT_ADDENDUM has rule markers + schema --")
    addendum = cs.PROMPT_ADDENDUM
    for marker in (
        "<output_spec>", "</output_spec>",
        "file_path", "rule_code", "summary", "unified_diff",
        "confidence", "risks",
        "git apply -p0",
        "DO NOT include any extra fields",
        "DO NOT use markdown code fences",
    ):
        if marker not in addendum:
            print(f"x step 8: PROMPT_ADDENDUM missing marker {marker!r}")
            return 1
    if len(addendum) < 600:
        print(f"x step 8: PROMPT_ADDENDUM is only {len(addendum)} chars; likely truncated")
        return 1
    print(f"  ok: addendum has 11 markers + {len(addendum)} chars")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
