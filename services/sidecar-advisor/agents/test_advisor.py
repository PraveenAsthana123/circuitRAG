"""Test Advisor agent - reviews for testability and coverage:
missing edge cases, untested error paths, missing assertions,
fragile fixtures.

Why CodeGemma: Apache-2 license fits "ship-with-product" customer
deployments where test infrastructure code redistribution matters.
Test review is a lower-stakes diversity slot than security or
correctness, so license breadth wins over absolute capability.
"""
from .base import CoderAgent

AGENT = CoderAgent(
    name="test_advisor",
    role="author",
    model="codegemma:7b-instruct",
    description="missing edge cases, untested error paths, fragile fixtures",
    prompt_template=(
        "You are the Test Advisor. Review ONLY for testability and "
        "test coverage: missing edge cases, untested error paths, "
        "missing assertions, fragile fixtures. Focus ONLY on "
        "tests - other reviewers cover bugs and security. Reply "
        "with ONE paragraph.\n\n"
        "Code:\n{content}\n\nReview:"
    ),
)
