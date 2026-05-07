"""Pydantic schemas for the local-Ollama issue-fix council.

Per CLAUDE.md §50 (issue dispatcher) + §43 (drill discipline).

WHY THIS EXISTS
===============

The §50 dispatcher's council pattern produces free-text output. The
daemon's extract_council_diff() then regex-greps a triple-backtick
diff block out of that text. Empirical session evidence: 0 of 6
council outputs applied through the drill-gate. Failure modes:

  - Diff truncated (council saw rule msg, summarized the line)
  - Tokenizer artifacts in file paths (deepseek `<｜begin▁of▁sentence｜>`)
  - "Add a semicolon to fix" — reviewer reversed the rule semantics
  - Broken @@ headers / wrong line counts
  - File path missing `services/` prefix entirely

Same root-cause as the Strategist agent's brittle JSON regex extractor
(closed earlier this session via Pydantic schema): **schema-as-contract**
forces the model to emit a structurally-valid proposal OR be rejected
at the validator boundary. No silent garbage downstream.

WHAT THIS PROVIDES
==================

  CouncilProposal       — Pydantic model with the full proposal shape
  validate_council_proposal(text: str) -> CouncilProposal | None
  PROMPT_ADDENDUM       — text appended to AUTHOR prompts so the model
                          sees the schema + an output instruction
  proposal_schema_text() - JSON-Schema text for prompt embedding

VALIDATION LAYERS (each catches a real-session failure mode)
============================================================

  1. Pydantic field validation (str / list / float ranges)
  2. extra='forbid' (model occasionally hallucinates a 'reasoning' field)
  3. Tokenizer-artifact rejection in file_path AND unified_diff
     (closes the deepseek `<｜begin▁of▁sentence｜>` failure)
  4. Diff-shape sanity (must contain `--- ` AND `+++ ` line markers)
  5. file_path resolves on disk relative to repo root

Drilled by mcp/tests/drill_council_proposal_schema.py — both
directions: valid proposal accepted, every failure mode rejected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field, ValidationError, field_validator

# Tokenizer artifacts seen empirically in deepseek-coder output (this
# session: 2 of 5 council runs produced these in file paths). Reject
# any proposal containing them.
TOKENIZER_ARTIFACTS: tuple[str, ...] = (
    "<｜begin▁of▁sentence｜>",
    "<｜end▁of▁sentence｜>",
    "<|begin_of_sentence|>",
    "<|end_of_sentence|>",
)


class CouncilProposal(BaseModel):
    """Structured fix-proposal from a single council role (AUTHOR).

    Reviewer + Advisor produce critique text, not proposals — they
    don't need this schema. AUTHOR's output is the only one that
    flows into the apply gate.
    """

    file_path: str = Field(
        min_length=1, max_length=512,
        description="Repo-relative path to the file the diff modifies",
    )
    rule_code: str = Field(
        min_length=1, max_length=64,
        description="The lint/check rule code being fixed (e.g. 'UP035', 'no-untyped-def', 'react-hooks/exhaustive-deps')",
    )
    summary: str = Field(
        min_length=1, max_length=400,
        description="One-sentence description of the fix",
    )
    unified_diff: str = Field(
        min_length=20, max_length=8192,
        description="Unified diff applicable via `git apply -p0`",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Self-assessed 0..1 — used for ranking when multiple authors propose",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Known risks of applying this fix (e.g. 'breaks downstream import')",
    )

    model_config: ClassVar[dict] = {
        "extra": "forbid",
    }

    @field_validator("file_path")
    @classmethod
    def _no_tokenizer_artifact_in_path(cls, v: str) -> str:
        for artifact in TOKENIZER_ARTIFACTS:
            if artifact in v:
                raise ValueError(
                    f"file_path contains tokenizer artifact {artifact!r} — "
                    "model output corruption; reject"
                )
        return v

    @field_validator("unified_diff")
    @classmethod
    def _no_tokenizer_artifact_in_diff(cls, v: str) -> str:
        for artifact in TOKENIZER_ARTIFACTS:
            if artifact in v:
                raise ValueError(
                    f"unified_diff contains tokenizer artifact {artifact!r} — "
                    "model output corruption; reject"
                )
        return v

    @field_validator("unified_diff")
    @classmethod
    def _diff_has_unified_markers(cls, v: str) -> str:
        if "--- " not in v or "+++ " not in v:
            raise ValueError(
                "unified_diff missing `--- ` or `+++ ` markers — "
                "not a valid unified diff"
            )
        if "@@" not in v:
            raise ValueError(
                "unified_diff missing `@@` hunk header — not a valid unified diff"
            )
        return v


def validate_council_proposal(
    raw_text: str,
    *,
    repo: Path | None = None,
) -> CouncilProposal | None:
    """Parse + validate raw AUTHOR output against CouncilProposal.

    Strategy:
      1. Strip markdown code fences.
      2. Find the FIRST balanced {...} substring (handles models that
         pre/post-amble the JSON despite "respond with ONLY JSON").
      3. Validate via Pydantic.
      4. If repo is provided, additionally check file_path resolves
         under repo root.

    Returns None for ANY failure mode. Caller (daemon / task_board)
    treats None as "no clean diff; escalate to human-review."
    """
    if not raw_text:
        return None
    cleaned = raw_text
    for fence in ("```json", "```"):
        cleaned = cleaned.replace(fence, "")
    cleaned = cleaned.strip()

    proposal: CouncilProposal | None = None
    candidate = _first_balanced_object(cleaned)
    if candidate is not None:
        try:
            proposal = CouncilProposal.model_validate_json(candidate)
        except (ValidationError, json.JSONDecodeError):
            proposal = None

    # Stage-2 PydanticAI fallback — when bracket-aware regex extraction
    # fails (no balanced object found OR parse rejected), try
    # pydanticai_adapter.validate() before giving up. Per the
    # 2026-05-04 tool-evaluation: PydanticAI may catch outputs the
    # regex path misses (e.g., split JSON, malformed fences).
    #
    # Fail-open: any exception from the fallback means "regex was
    # the truth; PydanticAI didn't help." Re-raises original-extraction
    # outcome (None) — does NOT propagate the fallback's exception.
    if proposal is None:
        try:
            from pydanticai_adapter import (  # noqa: PLC0415
                PydanticAIUnavailable,
            )
            from pydanticai_adapter import (
                validate as _pyaai_validate,
            )
            try:
                # Use the cleaned-of-fences text — pydantic-ai handles
                # extraction itself; we just give it the prose+JSON.
                proposal = _pyaai_validate(cleaned, CouncilProposal)
            except PydanticAIUnavailable:
                # Stage-1 default — adapter not enabled. Same outcome
                # as before this commit: regex failed → return None.
                pass
            except (ValueError, ValidationError, json.JSONDecodeError):
                # PydanticAI tried + failed validation. Same as regex
                # path failing — return None.
                proposal = None
        except ImportError:
            # pydanticai_adapter module missing — still fail-open;
            # this was the pre-Stage-2 behavior.
            pass

    if proposal is None:
        return None

    if repo is not None:
        target = (repo / proposal.file_path).resolve()
        try:
            target.relative_to(repo.resolve())
        except ValueError:
            return None  # path escape attempt
        if not target.exists():
            return None  # phantom file
    return proposal


def _first_balanced_object(text: str) -> str | None:
    """Return the first {...} substring whose braces balance (string-aware)."""
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


def proposal_schema_text() -> str:
    """JSON-Schema text for prompt embedding."""
    return json.dumps(CouncilProposal.model_json_schema(), indent=2)


PROMPT_ADDENDUM: str = (
    "\n\n"
    "<output_spec>\n"
    "Respond with ONLY a JSON object matching this schema (no prose,\n"
    "no markdown fences, no explanation outside the JSON):\n"
    "\n"
    "{\n"
    "  \"file_path\": \"<repo-relative path; e.g. services/foo/bar.py>\",\n"
    "  \"rule_code\": \"<rule being fixed, e.g. UP035>\",\n"
    "  \"summary\": \"<one-sentence fix description>\",\n"
    "  \"unified_diff\": \"<unified diff applicable via `git apply -p0`>\",\n"
    "  \"confidence\": <float 0..1>,\n"
    "  \"risks\": [\"<risk1>\", \"<risk2>\"]\n"
    "}\n"
    "\n"
    "STRICT RULES:\n"
    " 1. file_path MUST be the EXACT repo-relative path; no leading\n"
    "    './' and no missing prefix.\n"
    " 2. unified_diff MUST contain `--- `, `+++ `, and `@@ ...` markers.\n"
    " 3. unified_diff MUST be applicable via `git apply -p0` from the\n"
    "    repo root (paths NOT prefix-stripped).\n"
    " 4. DO NOT include any extra fields (e.g. 'reasoning',\n"
    "    'explanation') — the validator rejects extras.\n"
    " 5. DO NOT use markdown code fences around the JSON.\n"
    "</output_spec>\n"
)


if __name__ == "__main__":
    import sys
    print("scripts/council_schemas.py — Pydantic schemas for the local-Ollama issue-fix council")
    print("Library module — imported by scripts/local_council.py and 2 drills.")
    print("Exports: CouncilProposal · validate_council_proposal · PROMPT_ADDENDUM")
    print("This script has no CLI; --help prints this summary. See module docstring for full context.")
    sys.exit(0)
