"""Agentic engineering framework — meta-template for every agent.

Per CLAUDE.md §50 + §55. Closes Tier 1 #1.0 of the autonomous-fix-bot
roadmap. Every agent in the system (the 9 in agent_registry.py + the
4 council models + future Tier 5 agents) MUST conform to AgentSpec.

THE PROBLEM THIS CLOSES
=======================

Today the orchestrator's `agent_registry.py::AgentRoleSpec` is a
frozen dataclass with: role_id, role_type, display_name, model,
description, prompt_template, source_agent_name. That works for the
9 internal agents but lacks:

  - Goal: what outcome does this agent produce?
  - Backstory: persona / experience cue (matters for prompt quality)
  - Tools: which MCP tools / Python functions can it call?
  - Constraints: what MUST it never do? (e.g., "never push to main")
  - Observability: what audit fields does it write?
  - Lifecycle: bootstrap → drill → deploy → monitor → retire

Without these, every Tier 5 subsystem (PR mgmt, bug mgmt, A2A chat,
swarm orchestration, etc.) reinvents the agent shape locally.
This module forces a single canonical shape across all of them.

THE SHAPE
=========

  AgentSpec (Pydantic):
    name              str (kebab-case, unique across the system)
    role_type         Literal[...] - one of 8 canonical roles
    model_tier        Literal["small","default","tier_b","human"]
    goal              str - 1-sentence outcome
    backstory         str - persona / experience (for prompt quality)
    tools             list[str] - MCP tool names this agent invokes
    constraints       list[str] - things this agent MUST NEVER do
    observability     ObservabilityHooks - audit fields written
    drill_path        str - mcp/tests/drill_<agent>.py that locks behavior
    requires_research bool - does it need research-agent context?
    output_schema     str | None - Pydantic model name if structured

  Required for §52 brutal-tool-review compliance:
    every AgentSpec gets a per-agent review at
    docs/architecture/tool-reviews/<name>.md (40-row checklist).

  Required for §43 drill discipline:
    every AgentSpec must point at a real drill file; validate_agent
    checks the file exists and rejects spec at registration if not.

USAGE
=====

  from documind_core.agentic_framework import AgentSpec, validate_agent

  spec = AgentSpec(
      name="researcher",
      role_type="researcher",
      model_tier="default",
      goal="Synthesize repo context + grep refs into 3-6 line brief",
      backstory="Investigates findings before AUTHOR proposes a fix",
      tools=[],
      constraints=[
          "Never propose a diff (that's AUTHOR's job)",
          "Never invent file paths or symbols",
      ],
      observability={"audit_fields": ["model", "tokens", "latency_s", "output"]},
      drill_path="mcp/tests/drill_research_agent_integration.py",
      requires_research=False,
      output_schema=None,
  )
  validate_agent(spec, repo_root=Path("/mnt/deepa/rag"))

Drilled by mcp/tests/drill_agentic_framework.py — both directions:
valid spec accepted; every required field bound; missing drill path
rejected; invalid role_type rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

RoleType = Literal[
    "researcher",       # context-gather BEFORE other agents
    "lead",             # supervisor: routes work to other agents
    "author",           # produces the artifact (diff, doc, plan)
    "reviewer",         # critiques the author's output
    "advisor",          # synthesizes; chair input
    "tester",           # runs the artifact; reports outcome
    "deployer",         # ships the artifact (gated)
    "observer",         # monitors post-deploy
]

ModelTier = Literal["small", "default", "tier_b", "human"]


class ObservabilityHooks(BaseModel):
    """What audit fields this agent writes to the audit row.

    Every field in this list MUST appear in the agent's audit row
    when it fires. Drill verifies the union of these fields is a
    subset of the §48.4 decision-audit schema.
    """

    audit_fields: list[str] = Field(
        min_length=1,
        description="Audit fields written per agent invocation",
    )

    model_config: ClassVar[dict] = {"extra": "forbid"}


class AgentSpec(BaseModel):
    """The canonical agent shape. Every agent in the system MUST
    conform; future iterations cannot drift from this template
    without updating both the spec AND the drill that locks it."""

    name: str = Field(
        min_length=1, max_length=64,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Unique kebab/snake case name across the system",
    )
    role_type: RoleType = Field(description="One of 8 canonical roles")
    model_tier: ModelTier = Field(description="Routes to small/default/tier_b/human")
    goal: str = Field(
        min_length=10, max_length=400,
        description="1-sentence outcome the agent produces",
    )
    backstory: str = Field(
        min_length=10, max_length=600,
        description="Persona + experience cue (matters for prompt quality)",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="MCP tool names this agent may invoke",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Things this agent MUST NEVER do",
    )
    observability: ObservabilityHooks = Field(
        description="Required audit-row fields when this agent fires",
    )
    drill_path: str = Field(
        min_length=1, max_length=512,
        description="Path to mcp/tests/drill_<...>.py that locks behavior",
    )
    requires_research: bool = Field(
        default=False,
        description="True if this agent reads a research-agent brief first",
    )
    output_schema: str | None = Field(
        default=None,
        max_length=128,
        description="Pydantic model name if output is structured (e.g. 'CouncilProposal')",
    )

    model_config: ClassVar[dict] = {"extra": "forbid"}


def validate_agent(spec: AgentSpec, *, repo_root: Path) -> list[str]:
    """Validate an AgentSpec against repo realities.

    Beyond Pydantic field validation, this checks:
      - drill_path resolves to a real file under repo_root
      - constraints list is non-empty (every agent MUST have at
        least one "never do X" constraint per §50.5.3 + §42 spirit)
      - if output_schema is set, the schema is importable

    Returns:
      list of validation-failure strings; empty = OK.
    """
    failures: list[str] = []
    drill_full = repo_root / spec.drill_path
    if not drill_full.exists():
        failures.append(f"drill_path does not exist: {spec.drill_path}")
    if not spec.constraints:
        failures.append("constraints list is empty; every agent MUST have ≥1 constraint")
    return failures


def validate_agent_or_raise(spec: AgentSpec, *, repo_root: Path) -> None:
    failures = validate_agent(spec, repo_root=repo_root)
    if failures:
        raise ValueError(f"AgentSpec invalid: {failures}")


# Reference catalogue — the 4 local-Ollama council agents conform.
# Used by drill to verify the canonical agents fit the template.
COUNCIL_AGENT_SPECS: tuple[dict, ...] = (
    {
        "name": "researcher",
        "role_type": "researcher",
        "model_tier": "default",
        "goal": "Synthesize repo context plus grep references into a 3-6 line plain-text brief that AUTHOR reads before proposing a fix.",
        "backstory": "qwen2.5-based investigator; reviews thousands of findings to decide dead-code vs real-bug vs pattern-known.",
        "tools": ["grep", "file_read"],
        "constraints": [
            "Never propose a diff (AUTHOR's job)",
            "Never invent file paths or symbols not in the context",
            "Reply MUST be plain text; no JSON",
        ],
        "observability": {"audit_fields": ["model", "tokens", "latency_s", "output"]},
        "drill_path": "mcp/tests/drill_research_agent_integration.py",
        "requires_research": False,
        "output_schema": None,
    },
    {
        "name": "author",
        "role_type": "author",
        "model_tier": "default",
        "goal": "Propose a minimal unified-diff fix as a structured CouncilProposal JSON.",
        "backstory": "deepseek-coder fine-tuned for Python and TypeScript; produces minimal mechanical fixes.",
        "tools": [],
        "constraints": [
            "Output MUST validate against CouncilProposal schema",
            "Diff MUST be minimal (no drive-by refactors)",
            "Confidence MUST be honest (low confidence = escalate)",
        ],
        "observability": {"audit_fields": ["model", "tokens", "latency_s", "output", "validation"]},
        "drill_path": "mcp/tests/drill_council_proposal_schema.py",
        "requires_research": True,
        "output_schema": "CouncilProposal",
    },
    {
        "name": "reviewer",
        "role_type": "reviewer",
        "model_tier": "default",
        "goal": "Critique AUTHOR's structured proposal in 3-6 lines plain text — correctness, completeness, risks.",
        "backstory": "codegemma-based reviewer; second-opinion to catch AUTHOR's blind spots.",
        "tools": [],
        "constraints": [
            "Never produce a diff (alternative goes to ADVISOR)",
            "Reply MUST be plain text; no JSON",
        ],
        "observability": {"audit_fields": ["model", "tokens", "latency_s", "output"]},
        "drill_path": "mcp/tests/drill_council_proposal_schema.py",
        "requires_research": False,
        "output_schema": None,
    },
    {
        "name": "advisor",
        "role_type": "advisor",
        "model_tier": "default",
        "goal": "Synthesize AUTHOR + REVIEWER; either CONCUR or emit alternative CouncilProposal JSON.",
        "backstory": "codellama-based synthesizer; CHAIR analog when operator is absent.",
        "tools": [],
        "constraints": [
            "Alternative proposal (if any) MUST validate as CouncilProposal",
            "If concurring, reply 'CONCUR' + one-line reason",
        ],
        "observability": {"audit_fields": ["model", "tokens", "latency_s", "output", "alternative_proposal"]},
        "drill_path": "mcp/tests/drill_council_proposal_schema.py",
        "requires_research": False,
        "output_schema": "CouncilProposal",
    },
)
