"""PR-review council — composes AgentBoard with role-specialised authors.

Used by the Sidecar Advisor when a paste classifies as `pr_review`. A
single advisor.review() call would only get one model's perspective; a
council gets three coder LLMs each scoring from a different angle —
code quality, security, tests — and synthesises into a final top-3
action list.

Mapping to the user's spec ("Agent Council Framework"):

    Author 1   = code_reviewer    (DeepSeek)   bugs, edge cases, style
    Author 2   = security_auditor (CodeLlama)  auth, secrets, OWASP
    Author 3   = test_advisor     (CodeGemma)  missing tests, coverage
    Reviewer 1 = consistency_check (StarCoder2) scores each draft
    Advisor    = chair             (DeepSeek)   final top-3 actions

Why three different models, not three roles on one model:

* Diversity of training data → different blind spots covered.
* Each model's prompt is role-specific — focusing the model on
  ITS strength suits a 7B-class model better than asking one
  model to wear three hats sequentially.
* The cost is bounded — total = 3 + 3 + 1 = 7 LLM calls,
  ~30s wall at max_parallel=3.

The council outputs a Sidecar-compatible AdvisorOutput, so the rest
of the pipeline (memory.record_event, UI rendering) doesn't change.
"""
from __future__ import annotations

import importlib.util
import logging
import re
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from .advisor import AdvisorOutput

log = logging.getLogger(__name__)


# ── Locate AgentBoard from libs/py/documind_core ────────────────
# documind_core isn't pip-installed in every environment (the
# system Python doesn't have it). Bypass that by loading the
# module directly from the file. Same trick the drills use.
def _load_agent_board_mod():
    repo = Path(__file__).resolve().parents[2]
    p = repo / "libs" / "py" / "documind_core" / "agent_board.py"
    spec = importlib.util.spec_from_file_location(
        "documind_core_agent_board", p,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load agent_board from {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["documind_core_agent_board"] = mod
    spec.loader.exec_module(mod)
    return mod


_ab = _load_agent_board_mod()
AgentBoard = _ab.AgentBoard
make_agent = _ab.make_agent

# Type alias for caller-supplied generators (tests inject stubs).
GenerateFn = Callable[[str, str, float], Awaitable[str]]


# ── Role catalogue ──────────────────────────────────────────────
# Each role pairs a prompt template with the recommended model.
# A council instance can override the model assignments via
# `model_overrides` if a heavier model is locally available.
ROLE_AUTHORS: dict[str, tuple[str, str]] = {
    "code_reviewer": (
        "deepseek-coder:6.7b-instruct",
        # Prompt — instruct-style, one focused angle.
        "You are the Code Reviewer. Review ONLY the code below for "
        "bugs, edge cases, code-style issues, and missing input "
        "validation. Focus on correctness, NOT security or tests "
        "— other reviewers cover those. Reply with ONE paragraph.\n\n"
        "Code:\n{content}\n\nReview:",
    ),
    "security_auditor": (
        "codellama:7b-instruct",
        "You are the Security Auditor. Review ONLY for security "
        "issues: hardcoded secrets, missing auth checks, injection "
        "(SQL / shell / template), unsafe deserialisation, missing "
        "input sanitisation. Focus ONLY on security — other "
        "reviewers cover correctness and tests. Reply with ONE "
        "paragraph.\n\n"
        "Code:\n{content}\n\nReview:",
    ),
    "test_advisor": (
        "codegemma:7b-instruct",
        "You are the Test Advisor. Review ONLY for testability and "
        "test coverage: missing edge cases, untested error paths, "
        "missing assertions, fragile fixtures. Focus ONLY on "
        "tests — other reviewers cover bugs and security. Reply "
        "with ONE paragraph.\n\n"
        "Code:\n{content}\n\nReview:",
    ),
}

REVIEWER_MODEL = "starcoder2:7b"
REVIEWER_PROMPT_OVERRIDE = (
    "Score the draft review below for relevance and concreteness. "
    "Give a SCORE from 0-10 where 10 = highly actionable + "
    "specific to the code, 0 = vague or off-topic. "
    "End the response with 'SCORE: <integer 0-10>'.\n\n"
    "Code being reviewed:\n{task}\n\n"
    "Draft review:\n{draft_text}\n\n"
    "Critique + score:"
)

ADVISOR_MODEL = "deepseek-coder:6.7b-instruct"
ADVISOR_PROMPT_OVERRIDE = (
    "You are the Chair of a code-review board. Three specialist "
    "reviewers each wrote a one-paragraph review of the SAME code; "
    "a fourth reviewer scored each draft. Synthesise into a SINGLE "
    "JSON object with the top-3 most-important actions for the "
    "developer.\n\n"
    "Reply with JSON ONLY in this shape:\n"
    "{{\"summary\": str (1 sentence), \"risk_level\": "
    "\"LOW|MEDIUM|HIGH\", \"top_3_advice\": [str, str, str], "
    "\"better_prompt_or_code\": str (suggested fix snippet), "
    "\"next_action\": str, \"confidence\": float between 0 and 1}}\n\n"
    "Code:\n{task}\n\n"
    "{drafts_block}\n\n"
    "{reviews_block}\n\n"
    "JSON:"
)


# ── Council ─────────────────────────────────────────────────────
class PrReviewCouncil:
    """Build + run an AgentBoard instance scoped to PR review.

    Args:
        ollama_url: the URL the default generator hits.
        generate_fn: optional override; a callable
            ``(model, prompt, timeout_s) -> str`` used by every
            agent in the council. Tests inject a stub here so the
            drill runs in tier 1 without Ollama.
        max_parallel: passed through to AgentBoard. Default 3 —
            with 7 total calls (3 authors + 3 reviews + 1 advisor)
            this gives 3 parallel cohorts of ≤3 each, ~30s wall.
        timeout_s: per-LLM-call deadline. Default 90s.
    """

    def __init__(
        self,
        *,
        ollama_url: str = "http://localhost:11434",
        generate_fn: GenerateFn | None = None,
        max_parallel: int = 3,
        timeout_s: float = 90.0,
        model_overrides: dict[str, str] | None = None,
    ) -> None:
        self._generate = generate_fn or self._default_ollama_generate
        self._ollama_url = ollama_url
        self._max_parallel = max_parallel
        self._timeout_s = timeout_s
        self._models = self._build_model_table(model_overrides or {})

    def _build_model_table(self, overrides: dict[str, str]) -> dict[str, str]:
        """Resolved {role: model} table after applying overrides."""
        table = {role: model for role, (model, _) in ROLE_AUTHORS.items()}
        table["consistency_check"] = REVIEWER_MODEL
        table["chair"] = ADVISOR_MODEL
        for role, model in overrides.items():
            if role in table:
                table[role] = model
        return table

    def _agent_for(self, role: str, prompt_template: str):
        """Wrap the generator into an Agent that injects the role's
        model + prompt template. Each call substitutes the agent's
        prompt into {content} so the AgentBoard sees a Protocol-
        compatible (prompt) -> str callable."""
        model = self._models[role]
        timeout_s = self._timeout_s

        # AgentBoard calls the agent with a single arg — the rendered
        # prompt for that role. For authors, the rendering is done
        # at agent-call time using prompt_template. For reviewers /
        # advisor, AgentBoard does its own template substitution
        # (review_prompt_template, advisor_prompt_template) so the
        # agent's job is just to pass the prompt through.
        if "{content}" in prompt_template:
            async def _author_agent(prompt_or_content: str) -> str:
                rendered = prompt_template.format(content=prompt_or_content)
                return await self._generate(model, rendered, timeout_s)
            return make_agent(_author_agent)
        else:
            async def _passthrough_agent(prompt: str) -> str:
                return await self._generate(model, prompt, timeout_s)
            return make_agent(_passthrough_agent)

    def build_board(self) -> AgentBoard:
        authors = {
            role: self._agent_for(role, prompt_template)
            for role, (_model, prompt_template) in ROLE_AUTHORS.items()
        }
        reviewers = {
            "consistency_check": self._agent_for(
                "consistency_check",
                # Pass-through — AgentBoard substitutes the review
                # prompt template at run time.
                "PASSTHROUGH_NO_CONTENT_TOKEN",
            ),
        }
        advisor = self._agent_for(
            "chair",
            "PASSTHROUGH_NO_CONTENT_TOKEN",
        )
        return AgentBoard(
            authors=authors,
            reviewers=reviewers,
            advisor=advisor,
            advisor_id="pr_review_chair",
            max_parallel=self._max_parallel,
            review_prompt_template=REVIEWER_PROMPT_OVERRIDE,
            advisor_prompt_template=ADVISOR_PROMPT_OVERRIDE,
        )

    async def review(self, content: str) -> tuple[AdvisorOutput, dict]:
        """Run the council; return (sidecar AdvisorOutput, raw board
        result) so callers can both display the synthesised advice
        AND inspect per-author drafts in the audit log.

        On chair failure, fall back to the highest-scored draft (this
        is BoardResult's built-in fallback). The Sidecar AdvisorOutput
        in that case is best-effort — the chair's structured JSON
        wasn't available, so we surface the chair's text in
        better_prompt_or_code and leave top_3_advice empty.
        """
        board = self.build_board()
        result = await board.run(content)

        chair_text = result.final_advice
        # The chair's prompt asks for JSON; try to parse. Fall back
        # to a placeholder if the chair errored out (BoardResult
        # carries .error then) or the JSON was unrecoverable.
        parsed = AdvisorOutput.parse(chair_text, model_used=ADVISOR_MODEL)

        if parsed is None:
            parsed = AdvisorOutput(
                summary=(
                    f"council ran ({len(result.drafts)} drafts, "
                    f"{len(result.reviews)} reviews) — chair output "
                    f"was unparseable"
                ),
                risk_level="MEDIUM",
                top_3_advice=[],
                better_prompt_or_code=chair_text[:4000],
                next_action="re-run review or inspect drafts in audit log",
                confidence=0.0,
                model_used=ADVISOR_MODEL,
            )

        # Decorate with council telemetry so the audit row shows what
        # actually happened under the hood.
        raw_board = {
            "outcome": result.outcome,
            "duration_s": result.duration_s,
            "prompt_version": result.prompt_version,
            "drafts": [
                {
                    "author_id": d.author_id,
                    "model_used": self._models.get(d.author_id, ""),
                    "text": d.text,
                    "duration_s": d.duration_s,
                    "error": d.error,
                }
                for d in result.drafts
            ],
            "reviews": [
                {
                    "reviewer_id": r.reviewer_id,
                    "draft_author_id": r.draft_author_id,
                    "score": r.score,
                    "critique": r.critique,
                    "error": r.error,
                }
                for r in result.reviews
            ],
            "advisor_error": result.error,
            "failed_authors": list(result.failed_authors),
        }
        return parsed, raw_board

    async def _default_ollama_generate(
        self, model: str, prompt: str, timeout_s: float,
    ) -> str:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{self._ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 512, "temperature": 0.2},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
