"""Base agent definition - one CoderAgent per role.

Every agent in the Sidecar Advisor council is described by this
dataclass:

    name           - human-readable id (used in metrics labels + audit)
    role           - "author" | "reviewer" | "advisor"
    model          - Ollama tag this agent calls
    prompt_template - format string with {content}, {task}, etc.
    description    - one-sentence "what this agent watches"

Each agent file under ./agents/ exports a single CoderAgent instance.
The registry imports all of them so the council + audit + UI all
have a single source of truth for "what agents exist".

This is the answer to "where is the advisor agent / review agent?"
- they live as one file per role under services/sidecar-advisor/agents/.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoderAgent:
    """One agent in the council. Frozen so the registry is immutable
    at runtime - hot-swapping models requires a code change + drill
    re-validation, not a runtime mutation."""

    name: str
    role: str               # author | reviewer | advisor | approver
    model: str              # Ollama tag, e.g. "deepseek-coder:6.7b-instruct"
    description: str        # one-sentence summary
    prompt_template: str    # format string

    def __post_init__(self):
        # Roles:
        #   author    - produces a review angle (code, security, test)
        #   reviewer  - critiques each author's draft (consistency_check)
        #   advisor   - synthesises drafts + reviews (chair)
        #   approver  - tracks the autonomous loop's commits and gates
        #               continuation per NEXT_POLICY.md (policy_approver)
        if self.role not in ("author", "reviewer", "advisor", "approver"):
            raise ValueError(
                f"role must be author|reviewer|advisor|approver, "
                f"got {self.role!r}"
            )
        if not self.name or not self.model or not self.prompt_template:
            raise ValueError(
                f"agent {self.name!r}: name, model, prompt_template required"
            )
