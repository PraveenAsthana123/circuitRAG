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
import sys
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
    def parse(cls, raw_text: str, *, model_used: str) -> AdvisorOutput | None:
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
        council=None,
        memory=None,
    ) -> None:
        self._policy = policy
        self._ollama_url = ollama_url
        # Default generator → Ollama. Drill / Phase 2 swap-out plug-in
        # different generators here.
        self._generate = generate_fn or self._default_ollama_generate
        # Optional pluggable council for the pr_review route. Lazy
        # default in review() so an Advisor created without a
        # council still runs single-agent for non-pr_review routes
        # without paying the import cost of the council module.
        self._council = council
        # Optional AdvisorMemory — when set, distilled patterns are
        # injected into the prompt as a "preferences / avoid" preamble
        # AND the cited patterns get use_count + last_used_at bumped.
        # When None, the advisor runs as before — memory is opt-in,
        # not retrofitted onto callers who haven't built the memory.
        self._memory = memory

    def record_rating(
        self,
        *,
        event_id: int,
        rating: str,
        rated_by: str | None = None,
        rating_notes: str | None = None,
    ) -> bool:
        """Persist a user rating for an existing advisor event.

        This is the advisor-level write contract used by sidecar/admin
        surfaces. Phase 1B-2 stores:

        - ``user_rating`` + ``rated_at``
        - optional ``rated_by``
        - optional ``rating_notes``

        Accepted rating values remain ``useful`` or ``not_useful``.
        """
        if self._memory is None:
            raise RuntimeError("advisor memory is not configured")
        return self._memory.rate_event(
            event_id,
            rating,
            rated_by=rated_by,
            rating_notes=rating_notes,
        )

    async def review(
        self, *, event_type: str, content: str,
    ) -> tuple[AdvisorOutput | None, str | None, str, float, dict | None]:
        """Run one review. Returns:
            (parsed_output_or_None, raw_text_if_unparseable,
             model_used, duration_s, council_telemetry_or_None)

        council_telemetry is the raw_board dict from
        PrReviewCouncil.review() for the pr_review route — None
        otherwise. Callers persist it via memory.record_council_run
        for the audit log; see services/sidecar-advisor/migrations/
        002_council_runs.sql.

        The pr_review route delegates to the council (3 specialised
        authors → 1 cross-reviewer → 1 chair). All other routes use
        the single-agent path below. The council is constructed
        lazily on first pr_review call unless one was injected at
        construction time.
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
                None,
            )

        # ── Council path: pr_review delegates to the multi-agent
        # AgentBoard wrapper. Other routes stay single-agent.
        if event_type == "pr_review":
            council = self._get_or_build_council()
            try:
                parsed, raw_board = await council.review(content)
                duration = time.monotonic() - t0
                return (parsed, None, parsed.model_used, duration, raw_board)
            except Exception as exc:  # noqa: BLE001 — surface for retry
                duration = time.monotonic() - t0
                log.error("advisor_council_failed err=%s", exc)
                return (None, f"COUNCIL_ERROR: {exc}", "", duration, None)

        model = route["model"]
        timeout_s = float(route.get("timeout_s", 60.0))
        template = _PROMPT_TEMPLATES.get(event_type)
        if template is None:
            log.warning("advisor_no_template event_type=%s", event_type)
            return (None, None, model, 0.0, None)

        # Inject distilled memory patterns as a preamble. The preamble
        # is empty when memory is cold or no patterns of this kind
        # exist — same prompt as before, no behaviour drift on a fresh
        # system.
        memory_preamble, cited_pattern_ids = self._build_memory_preamble()
        prompt_body = template.format(content=content)
        if memory_preamble:
            prompt = f"{memory_preamble}\n\n{prompt_body}"
        else:
            prompt = prompt_body
        if cited_pattern_ids and self._memory is not None:
            # Bump use_count + last_used_at on the cited patterns so
            # operators can see which patterns are actually
            # influencing live calls (vs. stale).
            self._memory.record_pattern_use(cited_pattern_ids)

        try:
            raw = await self._generate(model, prompt, timeout_s)
        except Exception as exc:  # noqa: BLE001 — error contained
            log.error(
                "advisor_generate_failed event_type=%s model=%s err=%s",
                event_type, model, exc,
            )
            duration = time.monotonic() - t0
            return (None, f"GENERATE_ERROR: {exc}", model, duration, None)

        parsed = AdvisorOutput.parse(raw, model_used=model)
        duration = time.monotonic() - t0
        if parsed is None:
            return (None, raw, model, duration, None)
        return (parsed, None, model, duration, None)

    def _build_memory_preamble(self) -> tuple[str, list[int]]:
        """Pull top-K distilled patterns from memory and render them as
        a 'User preferences / Avoid' preamble. Returns
        (preamble_text, cited_pattern_ids) so the caller can bump
        use_count for each cited pattern.

        Empty preamble when:
          * memory not wired (Advisor constructed without memory=...)
          * no patterns yet (cold start)
          * patterns exist but none meet the rendering threshold
        """
        if self._memory is None:
            return ("", [])
        # Lazy import — distillation pulls in the heuristic + format
        # helpers; no need to load them on every Advisor() construction.
        try:
            from .distillation import format_for_prompt
        except ImportError:
            # Same fallback as council import: drill loads us without
            # a package context. Resolve by file path.
            import importlib.util
            from pathlib import Path
            p = Path(__file__).parent / "distillation.py"
            spec = importlib.util.spec_from_file_location(
                "_sidecar_distillation_fallback", p,
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules["_sidecar_distillation_fallback"] = mod
            spec.loader.exec_module(mod)
            format_for_prompt = mod.format_for_prompt

        patterns = self._memory.get_patterns()
        if not patterns:
            return ("", [])

        text = format_for_prompt(patterns, max_per_kind=3)
        if not text:
            return ("", [])

        # Citation set = top-3-of-each-kind, same logic format_for_prompt
        # applies. Re-derive here so the use_count bump matches the
        # rendered patterns (don't bump patterns the LLM never saw).
        from collections import defaultdict
        by_kind: dict[str, list[dict]] = defaultdict(list)
        for p in patterns:
            by_kind[p["pattern_kind"]].append(p)
        cited: list[int] = []
        for kind in ("preference", "mistake"):
            sub = sorted(
                by_kind.get(kind, []),
                key=lambda p: p.get("confidence", 0.0),
                reverse=True,
            )[:3]
            cited.extend(p["id"] for p in sub)
        return (text, cited)

    def _get_or_build_council(self):
        """Lazily construct the council the first time pr_review hits.
        Caching it so a second pr_review doesn't rebuild the AgentBoard
        + agents from scratch."""
        if self._council is None:
            # Import here to keep the council module's importlib
            # gymnastics off the import path of consumers who only use
            # single-agent advisor.review.
            from .council import PrReviewCouncil
            self._council = PrReviewCouncil(
                ollama_url=self._ollama_url,
                generate_fn=self._generate,
            )
        return self._council

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
