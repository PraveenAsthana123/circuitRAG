"""Consistency Check agent - the lone reviewer. Scores each draft
review for relevance and concreteness; the chair uses these scores
to weight drafts when synthesising.

Why StarCoder2 (base, not instruct): scoring is a comparison task -
"is this review more actionable than that one?". The base completion
model attends to syntactic similarity + token overlap rather than
chasing instruction nuance, which suits a comparator role better
than the instruct variants.
"""
from .base import CoderAgent

AGENT = CoderAgent(
    name="consistency_check",
    role="reviewer",
    model="starcoder2:7b",
    description="scores each draft for relevance + concreteness",
    prompt_template=(
        "Score the draft review below for relevance and concreteness. "
        "Give a SCORE from 0-10 where 10 = highly actionable + "
        "specific to the code, 0 = vague or off-topic. "
        "End the response with 'SCORE: <integer 0-10>'.\n\n"
        "Code being reviewed:\n{task}\n\n"
        "Draft review:\n{draft_text}\n\n"
        "Critique + score:"
    ),
)
