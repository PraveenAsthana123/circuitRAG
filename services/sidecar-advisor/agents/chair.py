"""Chair agent - the single advisor on the council. Synthesises
the three author drafts + reviewer scores into a single JSON
AdvisorOutput.

Why DeepSeek (also the code_reviewer's model): synthesising
heterogeneous prose into structured JSON is a more demanding task
than writing a single review - it benefits from the model with the
highest instruct-following score in the 7B class. The author/chair
role distinction is in the PROMPT TEMPLATE, not the model identity.
"""
from .base import CoderAgent

AGENT = CoderAgent(
    name="chair",
    role="advisor",
    model="deepseek-coder:6.7b-instruct",
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
