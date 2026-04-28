"""Agent registry for the Sidecar Advisor council.

This is the answer to "where is the advisor agent / review agent?":
each role is one file under this directory, exporting a CoderAgent
constant called AGENT. The registry collects them all so the council
+ audit + UI have a single source of truth.

To add a new agent:

  1. Create services/sidecar-advisor/agents/<name>.py
  2. Export AGENT = CoderAgent(name=..., role=..., model=..., ...)
  3. Import it below and add to ALL_AGENTS

The drill (mcp/tests/drill_sidecar_agents_registry.py) verifies the
registry stays in sync with the files.
"""
from __future__ import annotations

from .base import CoderAgent
from .chair import AGENT as CHAIR
from .code_reviewer import AGENT as CODE_REVIEWER
from .consistency_check import AGENT as CONSISTENCY_CHECK
from .policy_approver import AGENT as POLICY_APPROVER
from .security_auditor import AGENT as SECURITY_AUDITOR
from .test_advisor import AGENT as TEST_ADVISOR

# Stable ordering — drills assert this so the council always builds
# the same shape from the registry. Adding a new agent appends; never
# reorder.
ALL_AGENTS: tuple[CoderAgent, ...] = (
    CODE_REVIEWER,
    SECURITY_AUDITOR,
    TEST_ADVISOR,
    CONSISTENCY_CHECK,
    CHAIR,
    POLICY_APPROVER,
)


def by_role(role: str) -> tuple[CoderAgent, ...]:
    """Filter the registry by role. Used by the council to build
    its author / reviewer / advisor sets without hard-coding names."""
    return tuple(a for a in ALL_AGENTS if a.role == role)


def by_name(name: str) -> CoderAgent | None:
    for a in ALL_AGENTS:
        if a.name == name:
            return a
    return None


__all__ = [
    "CoderAgent",
    "ALL_AGENTS",
    "by_role",
    "by_name",
    "CODE_REVIEWER",
    "SECURITY_AUDITOR",
    "TEST_ADVISOR",
    "CONSISTENCY_CHECK",
    "CHAIR",
    "POLICY_APPROVER",
]
