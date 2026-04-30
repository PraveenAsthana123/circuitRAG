"""Chair agent - the single advisor on the council. Synthesises
the three author drafts + reviewer scores into a single JSON
AdvisorOutput.

Why Kimi Cloud: the chair is the highest-value synthesis step in the
pipeline, so it is the one role worth upgrading from the local 7B
fleet to a larger cloud model. Authors stay local and cheap; the
chair gets the stronger cross-draft reasoning budget.
"""
from __future__ import annotations

import os

from .base import CoderAgent

DEFAULT_CHAIR_MODEL = "kimi-k2:1t-cloud"
DEFAULT_CHAIR_FALLBACK_MODEL = os.getenv("SIDECAR_CHAIR_FALLBACK_MODEL", "qwen2.5:latest")

AGENT = CoderAgent(
    name="chair",
    role="advisor",
    model=os.getenv("SIDECAR_CHAIR_MODEL", DEFAULT_CHAIR_MODEL),
    description="synthesises drafts + reviews into JSON top_3_advice",
    prompt_template=(
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
    ),
)
