"""Deterministic model router — picks (model, tier, backend) per role.

Pure function. No I/O, no DB, no clock. Takes:
  - role_id (must exist in catalog)
  - complexity ∈ {trivial, medium, high}
  - novelty ∈ {routine, novel}
  - has_tier_b: bool — budget allows + CLI installed (caller's concern)

Returns a RouteDecision with:
  - chosen: the primary handle
  - fallback_chain: ordered list to try next on LlmClientUnavailable
  - reason: one short string (audit trail, persisted by A5)

Negative-assertion contract (drilled):
  1. routine+trivial → NEVER returns tier_b even when has_tier_b=True
     and the role exposes a tier_b model. Cost guard.
  2. Unknown role_id → raises UnknownRoleError. Never silent default.
  3. has_tier_b=False with novel+high → falls back to tier_a_heavy,
     emits reason="tier_b_unavailable_fallback". Audit-visible.

Why pure function: routing is the highest-leverage decision in the
pipeline (a misroute bills 10x). Pure + deterministic = drillable
without infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .model_catalog import CatalogEntry, get_entry

Complexity = Literal["trivial", "medium", "high"]
Novelty = Literal["routine", "novel"]
Tier = Literal["tier_a", "tier_b"]


class UnknownRoleError(KeyError):
    """role_id is not present in the catalog."""


@dataclass(frozen=True)
class ModelHandle:
    role_id: str
    model: str
    tier: Tier
    backend: str  # "ollama" | "claude_cli" | "codex_cli"

    def to_dict(self) -> dict[str, str]:
        return {
            "role_id": self.role_id,
            "model": self.model,
            "tier": self.tier,
            "backend": self.backend,
        }


@dataclass(frozen=True)
class RouteDecision:
    chosen: ModelHandle
    fallback_chain: tuple[ModelHandle, ...]
    reason: str
    inputs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "chosen": self.chosen.to_dict(),
            "fallback_chain": [h.to_dict() for h in self.fallback_chain],
            "reason": self.reason,
            "inputs": dict(self.inputs),
        }


def _handle_a_primary(entry: CatalogEntry) -> ModelHandle:
    return ModelHandle(
        role_id=entry.role_id,
        model=entry.tier_a_primary,
        tier="tier_a",
        backend="ollama",
    )


def _handle_a_backup(entry: CatalogEntry) -> ModelHandle:
    return ModelHandle(
        role_id=entry.role_id,
        model=entry.tier_a_backup,
        tier="tier_a",
        backend="ollama",
    )


def _handle_a_heavy(entry: CatalogEntry) -> ModelHandle:
    model = entry.tier_a_heavy or entry.tier_a_primary
    return ModelHandle(
        role_id=entry.role_id,
        model=model,
        tier="tier_a",
        backend="ollama",
    )


def _handle_b(entry: CatalogEntry) -> ModelHandle | None:
    if not entry.tier_b:
        return None
    return ModelHandle(
        role_id=entry.role_id,
        model=entry.tier_b,
        tier="tier_b",
        backend=entry.tier_b_backend,
    )


def _dedupe_chain(chain: list[ModelHandle]) -> tuple[ModelHandle, ...]:
    """Drop duplicates while preserving order — same (model, backend) twice
    in the chain would waste a retry slot."""
    seen: set[tuple[str, str]] = set()
    out: list[ModelHandle] = []
    for h in chain:
        key = (h.model, h.backend)
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return tuple(out)


def route(
    *,
    role_id: str,
    complexity: Complexity = "medium",
    novelty: Novelty = "routine",
    has_tier_b: bool = True,
    budget_remaining_cents: int | None = None,
) -> RouteDecision:
    """Pick the right model for (role, complexity, novelty).

    Decision rules (evaluated in order):
      R0. budget_remaining_cents <= 0 → treat as has_tier_b=False with
          'budget_exhausted' annotation in reason (C1 cost guard, §41.1).
      R1. role=strategist → tier_b if available (always — D2 default).
      R2. novelty=novel AND complexity in {medium, high} AND has_tier_b → tier_b.
      R3. role=researcher AND complexity=high AND has_tier_b → tier_b.
      R4. complexity=high → tier_a_heavy.
      R5. else → tier_a_primary.

    Fallback chain after the chosen handle (in order):
      tier_a_heavy → tier_a_primary → tier_a_backup
    Deduped if any are equal.
    """
    entry = get_entry(role_id)
    if entry is None:
        raise UnknownRoleError(role_id)

    # C1 R0: budget exhausted blocks Tier-B selection. None = no tracking
    # (preserves pre-C1 behavior). 0 or negative = exhausted.
    budget_blocks_tier_b = (
        budget_remaining_cents is not None and budget_remaining_cents <= 0
    )
    effective_has_tier_b = has_tier_b and not budget_blocks_tier_b

    inputs = {
        "role_id": role_id,
        "complexity": complexity,
        "novelty": novelty,
        "has_tier_b": str(has_tier_b),
        "budget_remaining_cents": (
            str(budget_remaining_cents) if budget_remaining_cents is not None else "unset"
        ),
        "budget_blocks_tier_b": str(budget_blocks_tier_b),
    }
    tier_b = _handle_b(entry)

    chosen: ModelHandle
    reason: str

    # R1: strategist always Tier-B if available (D2 default).
    if role_id == "strategist" and tier_b is not None and effective_has_tier_b:
        chosen = tier_b
        reason = "R1_strategist_always_tier_b"
    # R2: novel + medium/high + effective tier_b
    elif (
        novelty == "novel"
        and complexity in ("medium", "high")
        and tier_b is not None
        and effective_has_tier_b
    ):
        chosen = tier_b
        reason = "R2_novel_complex_to_tier_b"
    # R3: researcher + high + effective tier_b
    elif (
        role_id == "researcher"
        and complexity == "high"
        and tier_b is not None
        and effective_has_tier_b
    ):
        chosen = tier_b
        reason = "R3_researcher_high_to_tier_b"
    # R4: high complexity → heavy local. Annotate WHY we didn't pick tier_b.
    elif complexity == "high":
        chosen = _handle_a_heavy(entry)
        if budget_blocks_tier_b and tier_b is not None:
            reason = "R4_high_complexity_budget_exhausted_fallback"
        elif tier_b is not None and not has_tier_b:
            reason = "R4_high_complexity_tier_b_unavailable_fallback"
        elif tier_b is None and novelty == "novel":
            reason = "R4_high_complexity_no_tier_b_for_role"
        else:
            reason = "R4_high_complexity_local_heavy"
    # R5: routine + trivial/medium → primary local
    else:
        chosen = _handle_a_primary(entry)
        if budget_blocks_tier_b:
            reason = "R5_routine_local_primary_budget_exhausted"
        else:
            reason = "R5_routine_local_primary"

    # Build fallback chain: heavy → primary → backup, minus the chosen.
    raw_chain: list[ModelHandle] = []
    raw_chain.append(_handle_a_heavy(entry))
    raw_chain.append(_handle_a_primary(entry))
    raw_chain.append(_handle_a_backup(entry))
    # Remove the chosen from the chain (router caller already has it).
    chain_excl = [
        h for h in raw_chain
        if (h.model, h.backend) != (chosen.model, chosen.backend)
    ]
    fallback_chain = _dedupe_chain(chain_excl)

    return RouteDecision(
        chosen=chosen,
        fallback_chain=fallback_chain,
        reason=reason,
        inputs=inputs,
    )
