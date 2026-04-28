"""Rule-based event classifier.

Maps a raw paste to one of: prompt | code | architecture | pr_review | debug.

Phase 1 keeps this rule-based — keyword matching with priority ordering.
The drill locks the classification rules so a future ML-based classifier
(Phase 2+) doesn't silently mis-route events with the same input shape.

Why rule-based first:
* Zero-cost (no LLM call to classify before LLMs run).
* Deterministic — same input always lands in the same route, which
  matters for the policy_version + advisor_events row attribution.
* Easy to debug — a regression is one rule away from being fixed.
"""
from __future__ import annotations

import re
from enum import Enum


class EventType(str, Enum):
    PROMPT = "prompt"
    CODE = "code"
    ARCHITECTURE = "architecture"
    PR_REVIEW = "pr_review"
    DEBUG = "debug"


# Patterns are scanned in order; the FIRST match wins. Order matters:
# debug (traceback) outranks code, because a Python stack trace contains
# both `File "x.py"` AND `def foo()`. Architecture outranks code because
# an ADR document often pastes code blocks alongside prose.
_RULES: list[tuple[EventType, list[re.Pattern[str]]]] = [
    (EventType.DEBUG, [
        # Python traceback
        re.compile(r"Traceback \(most recent call last\)", re.MULTILINE),
        # Generic stack frame markers
        re.compile(r"^\s*at\s+\S+\(.*:\d+:\d+\)", re.MULTILINE),
        # JS error
        re.compile(r"^\w*Error:\s", re.MULTILINE),
        # Common error keywords with a colon (likely error message)
        re.compile(
            r"\b(stacktrace|exception:|panic:|segfault|killed by signal|"
            r"npm err!|enoent|econnrefused)\b",
            re.IGNORECASE,
        ),
    ]),
    (EventType.PR_REVIEW, [
        # Diff hunk header
        re.compile(r"^@@\s+-\d+", re.MULTILINE),
        # Git format-patch / diff header
        re.compile(r"^diff --git ", re.MULTILINE),
        # PR review terms
        re.compile(r"\b(pull request|merge request|/review)\b", re.IGNORECASE),
    ]),
    (EventType.ARCHITECTURE, [
        # ADR / architecture document markers
        re.compile(r"\b(ADR-?\d+|architecture decision record)\b", re.IGNORECASE),
        re.compile(r"\b(c4 model|sequence diagram|system context)\b", re.IGNORECASE),
        # Common architecture verbs
        re.compile(
            r"\b(refactor architecture|design (the|a) (system|service)|"
            r"high-level design|hld|lld|scale to \d+)\b",
            re.IGNORECASE,
        ),
    ]),
    (EventType.CODE, [
        # Python def / class
        re.compile(r"^\s*(def|class|async def)\s+\w+", re.MULTILINE),
        # JS/TS function
        re.compile(r"^\s*(function|const|let|var)\s+\w+\s*[=(]", re.MULTILINE),
        # Java/C# method
        re.compile(r"^\s*(public|private|protected)\s+\w+\s+\w+\s*\(", re.MULTILINE),
        # Imports — strong code signal
        re.compile(r"^(import|from)\s+\w+", re.MULTILINE),
        # SQL DDL
        re.compile(r"\b(CREATE TABLE|ALTER TABLE|SELECT .+ FROM)\b", re.IGNORECASE),
    ]),
]


def classify_input(text: str) -> EventType:
    """Classify a paste into one of the EventType variants.

    Default: PROMPT (prose / instruction-shaped input that doesn't match
    any rule). The classifier is conservative — when in doubt, treat the
    input as a prompt and let the prompt_coach handle it.
    """
    if not text or not text.strip():
        return EventType.PROMPT

    for event_type, patterns in _RULES:
        for pat in patterns:
            if pat.search(text):
                return event_type
    return EventType.PROMPT


# Bumping this string forces the drill to be re-validated. Bump when
# adding/removing/reordering rules — the drill's expectations are pinned
# to a version, not "current behaviour".
CLASSIFIER_VERSION = "1.0.0"
