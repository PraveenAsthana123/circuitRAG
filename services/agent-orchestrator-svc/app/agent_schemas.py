"""Pydantic schemas for agent structured output.

Per CLAUDE.md §43 + the §44 drift-detection iteration's pattern of
"schema is the contract": replaces the brittle bracket-aware regex
extractor in `agents.py::StrategistAgent._parse_json_classification`
with a Pydantic-validated round-trip.

This module is the **pilot** for §52 row-1 closure on the agent
sub-system — one agent migrated to structured output, eight remain
on `prompt_template` + regex extraction. The pilot ships with:

  * Schema-as-contract: every field typed, every enum-like field a
    `Literal[...]`, every list element a nested model.
  * Validator helper: `validate_strategist_output()` that returns
    a typed `StrategistOutput` on success or `None` on failure.
    The caller (StrategistAgent) decides what to do with `None`
    (falls back to heuristic — same behaviour as the regex path).
  * `model_json_schema()` callable: the prompt embeds the schema as
    JSON-Schema text so the model has the shape spec inline. This
    is the model-agnostic equivalent of LangChain's
    `with_structured_output()` — works on Claude / Ollama / local
    models without depending on tool-calling support.

Why Pydantic + JSON-mode rather than LangChain's
`with_structured_output()`:

  qwen2.5:latest (the Strategist's default model) is unreliable with
  tool-calling-style structured output on Ollama. The advisor flagged
  this; falling back to JSON mode + Pydantic validation gives the
  same contract win without depending on a tool-calling model.

Drilled by `mcp/tests/drill_strategist_structured_output.py`:
  - valid JSON → typed model with all fields
  - malformed JSON → None (no silent fabrication)
  - invalid enum value → None (rejection visible)
  - missing required field → None
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError


Complexity = Literal["trivial", "medium", "high"]
Novelty = Literal["routine", "novel"]


class StepClassification(BaseModel):
    """Single pipeline step's complexity / novelty classification."""

    step_id: str = Field(min_length=1, description="Operator-readable step name (e.g. 'design', 'implement', 'deploy')")
    complexity: Complexity = Field(description="trivial = mechanical edit; medium = real engineering; high = multi-system")
    novelty: Novelty = Field(description="routine = pattern-known; novel = unfamiliar territory or untested integration")
    needs_research: bool = Field(description="true when novelty=novel OR domain knowledge is unclear; false otherwise")


class StrategistOutput(BaseModel):
    """Top-level output of the Strategist agent.

    Mirrors the expected shape consumed by `langgraph_flow.py` —
    rolled-up metrics drive routing tier (Tier-A vs. Tier-B) for
    every downstream node.
    """

    steps: list[StepClassification] = Field(min_length=1, description="At least one step; complex tasks fan out")
    overall_complexity: Complexity = Field(description="Highest complexity across steps")
    overall_novelty: Novelty = Field(description="novel if ANY step is novel")
    needs_research: bool = Field(description="true if any step needs research")
    summary: str = Field(min_length=1, max_length=500, description="One-sentence rollup")

    model_config = {
        # Reject extra fields — the model occasionally hallucinates
        # an `explanation` field; rejecting forces the prompt to be
        # tightened rather than silently ignoring drift.
        "extra": "forbid",
    }


def validate_strategist_output(raw_text: str) -> StrategistOutput | None:
    """Parse + validate raw LLM output text against StrategistOutput.

    Strategy:
      1. Strip markdown code fences (```json / ```).
      2. Find the FIRST balanced {...} substring (handles models that
         pre/post-amble the JSON despite "respond with ONLY JSON").
      3. Validate via Pydantic; return typed model on success.

    Returns None for ANY failure mode — caller (StrategistAgent)
    falls back to its deterministic heuristic. None > silent
    fabrication, same honesty pattern as the §35 dashboard.
    """
    if not raw_text:
        return None
    cleaned = raw_text
    # Strip markdown fences (model often wraps despite "no markdown" rule).
    for fence in ("```json", "```"):
        cleaned = cleaned.replace(fence, "")
    cleaned = cleaned.strip()

    # Find the first balanced { ... } substring.
    candidate = _first_balanced_object(cleaned)
    if candidate is None:
        return None
    try:
        return StrategistOutput.model_validate_json(candidate)
    except ValidationError:
        return None
    except json.JSONDecodeError:
        return None


def _first_balanced_object(text: str) -> str | None:
    """Return the first {...} substring whose braces balance.

    Walks every '{' position, scans forward counting braces while
    respecting strings + escapes. Same shape as the existing
    bracket-aware extractor — kept here so the schema validator
    is self-contained.
    """
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def strategist_schema_text() -> str:
    """JSON-Schema string for embedding in the Strategist prompt.

    The model sees the same schema the validator enforces, which is
    the structured-output trick — no tool-calling needed.
    """
    return json.dumps(StrategistOutput.model_json_schema(), indent=2)
