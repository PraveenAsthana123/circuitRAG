"""Council Phases 3-5: cross-critique → revision → evidence-check.

Q1/Q2/Q3 design picks (opinionated defaults — flip via env):

  Q1 (CONFIDENCE_AGGREGATION):
      ``trimmed_mean``  — drop highest + lowest score, mean the rest
                          (robust against outliers; see EU AI Act
                           "robust by design" guidance) — DEFAULT
      ``mean``          — democratic; vulnerable to one bad agent
      ``judge_weighted``— meritocratic but judge becomes SPOF

  Q2 (EVIDENCE_POLICY):
      ``demote``        — each uncited claim drops evidence dim by 0.1
                          (max -0.5); never rejects outright — DEFAULT
      ``reject``        — strict; reduces availability
      ``revise``        — costly extra round

  Q3 (DISSENT_POLICY):
      ``surface``       — final answer adds a "Minority view" block
                          when ≥2 agents strongly disagree — DEFAULT
      ``hide``          — single answer, dissent lost
      ``hitl``          — pause for human

Override via env::

    COUNCIL_AGGREGATION=mean
    COUNCIL_EVIDENCE_POLICY=reject
    COUNCIL_DISSENT_POLICY=hitl
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Literal

from council_engine.agents.roles import AgentResponse, run_role

log = logging.getLogger(__name__)

AGGREGATION = os.getenv("COUNCIL_AGGREGATION", "trimmed_mean").lower()
EVIDENCE_POLICY = os.getenv("COUNCIL_EVIDENCE_POLICY", "demote").lower()
DISSENT_POLICY = os.getenv("COUNCIL_DISSENT_POLICY", "surface").lower()

# Disagreement threshold — if ≥2 agents have a Jaccard similarity below
# this against the others, mark as strong dissent.
DISSENT_JACCARD_FLOOR = 0.18

# Per-claim evidence demotion magnitude.
EVIDENCE_DEMOTE_PER_CLAIM = 0.1
EVIDENCE_DEMOTE_MAX = 0.5


# ---------------------------------------------------------------------------
# Q1: Confidence aggregation
# ---------------------------------------------------------------------------

def aggregate_confidence(scores: list[float], *, mode: str | None = None) -> float:
    """Aggregate per-agent confidences into one number in [0, 1].

    Modes:
      ``trimmed_mean`` (default) — drop highest+lowest, mean rest.
        Falls through to mean for n < 4 (no points to trim).
      ``mean`` — straight mean.
      ``judge_weighted`` — first score is treated as judge weight; mean
        of others scaled by it. (Explicit single-judge override path.)

    NEVER returns nan/inf; clamps to [0, 1].
    """
    chosen = (mode or AGGREGATION).lower()
    if not scores:
        return 0.0
    if chosen == "judge_weighted":
        head = max(0.0, min(1.0, scores[0]))
        rest = scores[1:] or scores
        avg = sum(rest) / len(rest)
        out = head * avg
    elif chosen == "trimmed_mean" and len(scores) >= 4:
        srt = sorted(scores)
        trimmed = srt[1:-1]
        out = sum(trimmed) / len(trimmed)
    else:  # mean (or trimmed_mean fallback for small N)
        out = sum(scores) / len(scores)
    return max(0.0, min(1.0, out))


# ---------------------------------------------------------------------------
# Q2: Evidence checker
# ---------------------------------------------------------------------------

# Heuristic claim splitter — sentences that look like assertions.
# Production should use a small LLM call; the regex is deterministic and
# drillable.
CLAIM_VERBS = re.compile(
    r"\b(is|are|will|must|should|requires|reduces|improves|saves|guarantees)\b",
    re.I,
)

CITATION_RE = re.compile(
    r"\[(?:source|cite|ref|doc)[\s:]?[^\]]+\]|\(\s*\d{4}\s*\)|"
    r"https?://\S+|GPTCache|RAGAS|FAISS|HNSW|OPA",
    re.I,
)


@dataclass
class EvidenceVerdict:
    cited_count: int
    uncited_count: int
    demote_amount: float       # 0..EVIDENCE_DEMOTE_MAX
    decision: Literal["pass", "demote", "reject", "revise"]
    uncited_examples: list[str] = field(default_factory=list)


def check_evidence(text: str, *, policy: str | None = None) -> EvidenceVerdict:
    """Heuristic evidence check — split into claims, count cited vs uncited."""
    chosen = (policy or EVIDENCE_POLICY).lower()
    if not text:
        return EvidenceVerdict(0, 0, 0.0, "pass")

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    cited = 0
    uncited = 0
    examples: list[str] = []
    for s in sentences:
        if not CLAIM_VERBS.search(s):
            continue
        if CITATION_RE.search(s):
            cited += 1
        else:
            uncited += 1
            if len(examples) < 3:
                examples.append(s[:140])

    if uncited == 0:
        return EvidenceVerdict(cited, 0, 0.0, "pass", examples)

    if chosen == "reject":
        return EvidenceVerdict(cited, uncited, EVIDENCE_DEMOTE_MAX,
                               "reject", examples)
    if chosen == "revise":
        return EvidenceVerdict(cited, uncited, EVIDENCE_DEMOTE_PER_CLAIM,
                               "revise", examples)
    # demote (default)
    demote = min(EVIDENCE_DEMOTE_MAX, EVIDENCE_DEMOTE_PER_CLAIM * uncited)
    return EvidenceVerdict(cited, uncited, demote, "demote", examples)


# ---------------------------------------------------------------------------
# Q3: Dissent detection
# ---------------------------------------------------------------------------

def _shingles(text: str, n: int = 3) -> set[str]:
    tokens = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class DissentVerdict:
    has_dissent: bool
    dissenting_roles: list[str] = field(default_factory=list)
    similarities: dict[str, float] = field(default_factory=dict)


def detect_dissent(responses: list[AgentResponse]) -> DissentVerdict:
    """Pairwise Jaccard over agent shingles. Roles below floor against
    the median are flagged as dissenting."""
    if len(responses) < 2:
        return DissentVerdict(False)
    shingled = {r.role: _shingles(r.content) for r in responses}
    dissenting: list[str] = []
    sims: dict[str, float] = {}
    for r in responses:
        others = [other for other in responses if other.role != r.role]
        avg = sum(_jaccard(shingled[r.role], shingled[o.role]) for o in others) / len(others)
        sims[r.role] = round(avg, 3)
        if avg < DISSENT_JACCARD_FLOOR:
            dissenting.append(r.role)
    return DissentVerdict(
        has_dissent=len(dissenting) >= 2,
        dissenting_roles=dissenting,
        similarities=sims,
    )


# ---------------------------------------------------------------------------
# Phase 3: Cross-critique round
# ---------------------------------------------------------------------------

CRITIQUE_PROMPT = (
    "You are role={role}. Read the OTHER agents' answers below and emit "
    "ONE concrete risk OR weakness in the strongest one. Be specific. "
    "1-3 sentences. NO summary."
)


def cross_critique(responses: list[AgentResponse]) -> list[AgentResponse]:
    """Each agent reads the others, returns a critique. Sequential to
    avoid Ollama saturation; parallel is a follow-up."""
    others_by_role = {r.role: "\n\n".join(
        f"=== {o.role.upper()} ===\n{o.content[:600]}"
        for o in responses if o.role != r.role
    ) for r in responses}
    out: list[AgentResponse] = []
    for r in responses:
        critique = run_role(r.role, others_by_role[r.role])
        critique.role = f"{r.role}.critique"
        out.append(critique)
    return out


# ---------------------------------------------------------------------------
# Phase 4: Revision round
# ---------------------------------------------------------------------------

REVISION_PROMPT = (
    "You are role={role}. You wrote the FIRST draft below. The OTHER "
    "agents' critiques follow. Update your draft — keep what's right, "
    "fix what's wrong. 5-8 bullets max. Be terse."
)


def revise_round(
    initial: list[AgentResponse], critiques: list[AgentResponse],
) -> list[AgentResponse]:
    by_role = {a.role.replace(".critique", ""): a for a in critiques}
    out: list[AgentResponse] = []
    for r in initial:
        c = by_role.get(r.role)
        if c is None:
            out.append(r)  # no critique → keep original
            continue
        prompt = (
            f"YOUR DRAFT:\n{r.content[:800]}\n\n"
            f"CRITIQUE FROM OTHERS:\n{c.content[:600]}"
        )
        revised = run_role(r.role, prompt)
        revised.role = f"{r.role}.revised"
        out.append(revised)
    return out


__all__ = [
    "AGGREGATION", "DISSENT_POLICY", "EVIDENCE_POLICY",
    "DissentVerdict", "EvidenceVerdict",
    "aggregate_confidence", "check_evidence",
    "cross_critique", "detect_dissent", "revise_round",
]
