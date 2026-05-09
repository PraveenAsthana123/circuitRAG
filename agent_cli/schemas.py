"""Pydantic schemas for typed agent outputs.

Each output format from the user's catalog (Strategy / Planner /
Advisory / Coder / Monitoring) is a strict schema — agents that produce
free text get parsed into one of these. Mismatches surface as
``ValidationError`` not silent text corruption.

Why typed outputs:
- Composability: downstream agents (Critic, Judge, Approval) read
  fields, not free text. No regex hacks.
- Drillability: drill instantiates the schema with edge values to
  prove the contract. Rejection on missing fields is the negative
  assertion.
- Audit: every approval row carries a parseable ``next_steps`` array,
  ``confidence`` float, ``risks`` list — auditors don't grep prose.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Confidence is bounded — agents that emit out-of-range values get rejected.
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")  # surface unexpected fields


class StrategyOutput(_Base):
    """Top-of-funnel output: what to build and why (not how)."""
    objective: str = Field(min_length=1, max_length=500)
    approach: str = Field(min_length=1, max_length=500)
    alternatives: list[str] = Field(default_factory=list)
    decision: str = Field(min_length=1, max_length=500)
    kpi: list[str] = Field(default_factory=list, min_length=1)
    risks: list[str] = Field(default_factory=list)
    mitigation: list[str] = Field(default_factory=list)
    timeline: str = Field(min_length=1, max_length=200)


class PlannerOutput(_Base):
    """How to build it: phased plan with risks + acceptance criteria."""
    phases: list[str] = Field(min_length=1, max_length=12)
    tasks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    mitigation: list[str] = Field(default_factory=list)
    timeline: str = Field(min_length=1, max_length=200)
    confidence: Confidence = 0.85
    acceptance_criteria: list[str] = Field(default_factory=list)


class AdvisoryOutput(_Base):
    """One pick + trade-offs."""
    decision: str = Field(min_length=1, max_length=500)
    alternatives: list[str] = Field(default_factory=list)
    trade_off: dict[str, str] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    recommendation: str = Field(min_length=1, max_length=500)
    confidence: Confidence = 0.85


class CoderOutput(_Base):
    """What the coder produced."""
    task_id: str = Field(min_length=1)
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    code_summary: str = Field(min_length=1, max_length=2000)
    tests_added: bool = False
    drill_added: bool = False
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class MonitoringOutput(_Base):
    """Snapshot a Monitoring Agent emits."""
    system_status: Literal["healthy", "degraded", "down"]
    alerts: list[str] = Field(default_factory=list)
    metrics: dict[str, str] = Field(default_factory=dict)
    risk: Literal["low", "medium", "high", "critical"] = "low"
    recommended_action: list[str] = Field(default_factory=list)


class CouncilDecision(_Base):
    """Final decision object emitted by the Council Engine judge.

    Schema is the user's spec exactly: 6-dim scoring, agent list,
    debate rounds, final decision verb.
    """
    council_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    agents: list[str] = Field(min_length=1)
    debate_rounds: int = Field(ge=1, le=5, default=1)
    final_decision: Literal[
        "approve", "approve_with_changes", "revise", "reject", "escalate"
    ]
    confidence: Confidence
    risks: list[str] = Field(default_factory=list)
    recommended_action: str = Field(min_length=1, max_length=2000)
    scores: dict[str, float] = Field(default_factory=dict)

    @field_validator("scores")
    @classmethod
    def _scores_in_range(cls, v: dict[str, float]) -> dict[str, float]:
        for k, score in v.items():
            if not (0.0 <= score <= 100.0):
                raise ValueError(f"score {k}={score} out of [0,100]")
        return v


__all__ = [
    "AdvisoryOutput",
    "CoderOutput",
    "Confidence",
    "CouncilDecision",
    "MonitoringOutput",
    "PlannerOutput",
    "StrategyOutput",
]
