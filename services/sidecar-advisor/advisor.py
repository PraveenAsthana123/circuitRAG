"""The advisor — calls a model picked by the policy and parses the
structured output the prompt tells the model to produce.

Phase 1 design: HTTP to local Ollama, no streaming. The advisor is
deliberately small — its only job is "given an event_type + content,
return a parsed AdvisorOutput". Routing, memory, and UI live elsewhere.

A non-Ollama generate function can be injected at construction time.
That seam exists for two reasons:

1. The drill exercises the advisor without needing models pulled — it
   passes a stub generator.
2. Phase 2 swaps in Claude / Codex for the architecture / pr_review
   routes by just registering a different generator under those keys.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

log = logging.getLogger(__name__)

# Type alias: a "generate" callable takes (model, prompt, timeout_s)
# and returns text. Async because the default impl is httpx.AsyncClient.
GenerateFn = Callable[[str, str, float], Awaitable[str]]


@dataclass
class AdvisorOutput:
    """The contract the LLM is asked to produce. See policy.yaml's
    output_schema for the canonical definition."""

    summary: str
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH"
    top_3_advice: list[str] = field(default_factory=list)
    better_prompt_or_code: str = ""
    next_action: str = ""
    confidence: float = 0.0
    model_used: str = ""

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "risk_level": self.risk_level,
            "top_3_advice": list(self.top_3_advice),
            "better_prompt_or_code": self.better_prompt_or_code,
            "next_action": self.next_action,
            "confidence": self.confidence,
            "model_used": self.model_used,
        }

    @classmethod
    def parse(cls, raw_text: str, *, model_used: str) -> "AdvisorOutput | None":
        """Try to parse the LLM's response as the contract JSON. Returns
        None if the response isn't recoverable (caller should retry once
        and then surface the malformed text)."""
        # Models often wrap JSON in ```json fences or prefix it with
        # prose. Strip the fence if present, otherwise look for the
        # first { ... } block.
        text = raw_text.strip()
        if text.startswith("```"):
            # ```json\n{...}\n```  →  trim to inner block
            text = text.split("```", 2)[1]
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
            if text.endswith("```"):
                text = text[:-3]

        # Find the first balanced {...} block
        start = text.find("{")
        if start == -1:
            return None
        # Naive balance: track depth ignoring strings — adequate for
        # well-formed JSON the model produces. Robust JSON-streaming
        # parsing isn't worth the complexity for Phase 1.
        depth = 0
        in_str = False
        escape = False
        end = -1
        for i, ch in enumerate(text[start:], start=start):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == -1:
            return None

        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            return None

        # Normalise + apply defaults. Be lenient — a missing field
        # gets a placeholder, not a crash.
        risk = str(data.get("risk_level", "MEDIUM")).upper()
        if risk not in {"LOW", "MEDIUM", "HIGH"}:
            risk = "MEDIUM"

        advice = data.get("top_3_advice") or []
        if not isinstance(advice, list):
            advice = [str(advice)]
        advice = [str(x) for x in advice[:3]]

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return cls(
            summary=str(data.get("summary", "")).strip()[:500],
            risk_level=risk,
            top_3_advice=advice,
            better_prompt_or_code=str(data.get("better_prompt_or_code", ""))[:4000],
            next_action=str(data.get("next_action", ""))[:200],
            confidence=confidence,
            model_used=model_used,
        )


# Per-route prompt templates. Each ends with the same "Reply with JSON
# only" instruction so the parser has a consistent target.
_PROMPT_TEMPLATES: dict[str, str] = {
    "prompt": (
        "You are the Prompt Coach. Review the user's prompt for clarity, "
        "context, constraints, and success criteria. Suggest a stronger "
        "rewrite. Reply with JSON ONLY using this exact shape:\n"
        "{{\"summary\": str, \"risk_level\": \"LOW|MEDIUM|HIGH\", "
        "\"top_3_advice\": [str, str, str], \"better_prompt_or_code\": str, "
        "\"next_action\": str, \"confidence\": float between 0 and 1}}\n\n"
        "Prompt:\n{content}\n\nJSON:"
    ),
    "code": (
        "You are the Code Reviewer. Review the code below for bugs, "
        "missing tests, security issues, and maintainability. Reply with "
        "JSON ONLY:\n"
        "{{\"summary\": str, \"risk_level\": \"LOW|MEDIUM|HIGH\", "
        "\"top_3_advice\": [str, str, str], \"better_prompt_or_code\": str, "
        "\"next_action\": str, \"confidence\": float}}\n\n"
        "Code:\n{content}\n\nJSON:"
    ),
    "architecture": (
        "You are the Architect Advisor. Review the design / decision below "
        "for boundaries, scalability, failure modes, and ADR risks. Reply "
        "with JSON ONLY:\n"
        "{{\"summary\": str, \"risk_level\": \"LOW|MEDIUM|HIGH\", "
        "\"top_3_advice\": [str, str, str], \"better_prompt_or_code\": str, "
        "\"next_action\": str, \"confidence\": float}}\n\n"
        "Design:\n{content}\n\nJSON:"
    ),
    "pr_review": (
        "You are the PR Review chair. Review the diff below for correctness, "
        "test coverage, and merge-readiness. Reply with JSON ONLY:\n"
        "{{\"summary\": str, \"risk_level\": \"LOW|MEDIUM|HIGH\", "
        "\"top_3_advice\": [str, str, str], \"better_prompt_or_code\": str, "
        "\"next_action\": str, \"confidence\": float}}\n\n"
        "Diff:\n{content}\n\nJSON:"
    ),
    "debug": (
        "You are the Debug Advisor. Diagnose the error / traceback below "
        "and propose the most-likely root cause. Reply with JSON ONLY:\n"
        "{{\"summary\": str, \"risk_level\": \"LOW|MEDIUM|HIGH\", "
        "\"top_3_advice\": [str, str, str], \"better_prompt_or_code\": str, "
        "\"next_action\": str, \"confidence\": float}}\n\n"
        "Error:\n{content}\n\nJSON:"
    ),
}


class Advisor:
    """Routes events to models per policy + parses structured output."""

    def __init__(
        self,
        policy: dict,
        *,
        generate_fn: GenerateFn | None = None,
        ollama_url: str = "http://localhost:11434",
    ) -> None:
        self._policy = policy
        self._ollama_url = ollama_url
        # Default generator → Ollama. Drill / Phase 2 swap-out plug-in
        # different generators here.
        self._generate = generate_fn or self._default_ollama_generate

    async def review(
        self, *, event_type: str, content: str,
    ) -> tuple[AdvisorOutput | None, str | None, str, float]:
        """Run one review. Returns:
            (parsed_output_or_None, raw_text_if_unparseable,
             model_used, duration_s)
        """
        t0 = time.monotonic()
        route = (
            self._policy.get("advisor_policy", {})
            .get("routes", {})
            .get(event_type)
        )
        if route is None:
            log.warning("advisor_unknown_route event_type=%s", event_type)
            return (
                AdvisorOutput(
                    summary=f"unknown route: {event_type}",
                    risk_level="LOW",
                    confidence=0.0,
                    model_used="",
                ),
                None,
                "",
                0.0,
            )

        model = route["model"]
        timeout_s = float(route.get("timeout_s", 60.0))
        template = _PROMPT_TEMPLATES.get(event_type)
        if template is None:
            log.warning("advisor_no_template event_type=%s", event_type)
            return (None, None, model, 0.0)

        prompt = template.format(content=content)

        try:
            raw = await self._generate(model, prompt, timeout_s)
        except Exception as exc:  # noqa: BLE001 — error contained
            log.error(
                "advisor_generate_failed event_type=%s model=%s err=%s",
                event_type, model, exc,
            )
            duration = time.monotonic() - t0
            return (None, f"GENERATE_ERROR: {exc}", model, duration)

        parsed = AdvisorOutput.parse(raw, model_used=model)
        duration = time.monotonic() - t0
        if parsed is None:
            return (None, raw, model, duration)
        return (parsed, None, model, duration)

    async def _default_ollama_generate(
        self, model: str, prompt: str, timeout_s: float,
    ) -> str:
        """Default generator: POST /api/generate against local Ollama."""
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{self._ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 512,
                        "temperature": 0.2,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
