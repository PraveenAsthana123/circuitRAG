"""Disaster Recovery target metrics — single source of truth.

Per CLAUDE.md §35 (DR Metrics maturity item) + §41.2 (DR tiers).
docs/architecture/maturity-stack.md tracks current vs target.

Five canonical metrics — every regulated AI service MUST be able to
quote these on demand:

  - RTO  (Recovery Time Objective): max acceptable downtime
  - RPO  (Recovery Point Objective): max acceptable data-loss window
                                      (0 = synchronous replication)
  - MTTD (Mean Time To Detect):    how fast we notice an incident
  - MTTR (Mean Time To Recover):   how fast we restore service
  - Failover time:                 hot-standby promotion budget

Tiered per service criticality (CLAUDE.md §41.2):

  critical:  RTO 15 min / RPO 0
             auth, decision audit, payment-equivalent surfaces
  important: RTO 60 min / RPO 15 min
             core API — ingestion, retrieval, agentic orchestration
  standard:  RTO  4 hr / RPO 60 min
             analytics, batch jobs, dashboards (snapshot-recoverable)

Why a frozen dataclass and not Pydantic Settings: DR targets are a
governance contract, not a per-environment knob. They live in code
review (visible diff in any PR that loosens them) and are drilled by
`mcp/tests/drill_dr_metrics_targets.py`. If an operator wants to
override per-environment, layer a Pydantic Settings around this module
and document the override in the §35 ADR.

Maturity transition: L1 (no targets) → L2 (defined targets) lands here.
Subsequent iterations: L2 → L3 add a dashboard endpoint exposing
current vs target; L3 → L4 add a quarterly DR drill that measures
each metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["critical", "important", "standard"]


@dataclass(frozen=True)
class DrTargets:
    """Immutable DR target row — one per service tier.

    All durations are integer seconds. Invariants enforced in
    ``__post_init__`` and asserted independently by
    ``drill_dr_metrics_targets.py`` so a future refactor that drops
    the validation still gets caught.
    """

    tier: Tier
    rto_seconds: int
    rpo_seconds: int
    mttd_seconds: int
    mttr_seconds: int
    failover_seconds: int
    description: str

    def __post_init__(self) -> None:
        if self.rto_seconds <= 0:
            raise ValueError(f"{self.tier}: rto_seconds must be > 0")
        if self.rpo_seconds < 0:
            raise ValueError(f"{self.tier}: rpo_seconds must be >= 0")
        if self.mttd_seconds <= 0:
            raise ValueError(f"{self.tier}: mttd_seconds must be > 0")
        if self.mttr_seconds <= 0:
            raise ValueError(f"{self.tier}: mttr_seconds must be > 0")
        if self.failover_seconds <= 0:
            raise ValueError(f"{self.tier}: failover_seconds must be > 0")
        if self.mttr_seconds > self.rto_seconds:
            raise ValueError(
                f"{self.tier}: mttr_seconds ({self.mttr_seconds}s) cannot "
                f"exceed rto_seconds ({self.rto_seconds}s) — targets "
                "would be self-inconsistent"
            )


DEFAULT_TIER_TARGETS: dict[Tier, DrTargets] = {
    "critical": DrTargets(
        tier="critical",
        rto_seconds=15 * 60,
        rpo_seconds=0,
        mttd_seconds=60,
        mttr_seconds=14 * 60,
        failover_seconds=2 * 60,
        description=(
            "Auth, decision audit, payment-equivalent surfaces — "
            "zero-data-loss tier with synchronous replication."
        ),
    ),
    "important": DrTargets(
        tier="important",
        rto_seconds=60 * 60,
        rpo_seconds=15 * 60,
        mttd_seconds=2 * 60,
        mttr_seconds=55 * 60,
        failover_seconds=5 * 60,
        description=(
            "Core API surfaces — ingestion, retrieval, agentic "
            "orchestration. Asynchronous replication, 15-min RPO."
        ),
    ),
    "standard": DrTargets(
        tier="standard",
        rto_seconds=4 * 60 * 60,
        rpo_seconds=60 * 60,
        mttd_seconds=10 * 60,
        mttr_seconds=3 * 60 * 60,
        failover_seconds=15 * 60,
        description=(
            "Analytics, batch jobs, dashboards — snapshot-recoverable "
            "with hourly snapshot cadence."
        ),
    ),
}


def get_targets(tier: Tier) -> DrTargets:
    """Return the canonical DR targets for a tier.

    Raises:
        KeyError: tier is not one of critical/important/standard.
    """
    return DEFAULT_TIER_TARGETS[tier]


def all_targets() -> tuple[DrTargets, ...]:
    """Return all tier targets in critical→standard order. Stable across calls."""
    return (
        DEFAULT_TIER_TARGETS["critical"],
        DEFAULT_TIER_TARGETS["important"],
        DEFAULT_TIER_TARGETS["standard"],
    )
