"""Code Reviewer agent - one of three specialised authors on the
PR-review council. Focuses on bugs, edge cases, code-style issues,
and missing input validation.

Why DeepSeek: highest HumanEval pass@1 in the local 7B-class catalogue
(~73%). For correctness review, accuracy of bug detection matters more
than license breadth or speed.
"""
from .base import CoderAgent

AGENT = CoderAgent(
    name="code_reviewer",
    role="author",
    model="deepseek-coder:6.7b-instruct",
    description="bugs, edge cases, code-style, missing input validation",
    prompt_template=(
        "You are the Code Reviewer. Review ONLY the code below for "
        "bugs, edge cases, code-style issues, and missing input "
        "validation. Focus on correctness, NOT security or tests "
        "- other reviewers cover those. Reply with ONE paragraph.\n\n"
        "Code:\n{content}\n\nReview:"
    ),
)
