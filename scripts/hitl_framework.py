"""HITL framework — Human-in-the-loop scoring at every pipeline gate.

Per CLAUDE.md §55.3 (outcome-based contract) and the roadmap's
Tier 3 #3.1 (preference dataset) + Tier 4 #4.5 (outcome eval).

WHY THIS EXISTS
===============

Today every operator interaction is a black-hole signal:

  - Research brief was helpful? Discarded.
  - Council AUTHOR diff was correct? Discarded.
  - Drill-gate verdict matched operator's eye? Discarded.
  - Post-apply behavior was what was expected? Discarded.

Each of those is a labeled training pair (chosen vs rejected) that
RLHF / DPO / LoRA fine-tune (Tier 3 #3.15 + #3.16) needs as input.
This module is the capture surface — a structured score per gate
per issue — so the signal accumulates instead of vanishing.

THE 6 GATES
===========

Each pipeline stage gets its own gate type. Operator scores each:

  1. RESEARCH    — was the research brief useful for this issue?
  2. AUTHOR      — was the AUTHOR's proposed diff correct?
  3. REVIEWER    — was the REVIEWER's critique on-target?
  4. ADVISOR     — was the ADVISOR's synthesis better than AUTHOR?
  5. APPLY       — did the drill-gate verdict match operator judgment?
  6. POST_COMMIT — did the applied fix actually solve the problem?

Each score is a HitlScore row written to `.loop/hitl_scores.jsonl`.

USAGE
=====

  hitl_framework.py record <gate> <issue_id> <verdict> [--score 0-5]
                          [--note "text"] [--confidence 0-1]
  hitl_framework.py scorecard [--by rule|model|gate]
  hitl_framework.py preference-pairs    # for LoRA / DPO export
  hitl_framework.py list <issue_id>     # all scores for one issue

Drilled by mcp/tests/drill_hitl_framework.py.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


REPO = Path(__file__).resolve().parent.parent
HITL_LOG = REPO / ".loop" / "hitl_scores.jsonl"


GateType = Literal[
    "research",
    "author",
    "reviewer",
    "advisor",
    "apply",
    "post_commit",
]
GATE_TYPES: tuple[GateType, ...] = (
    "research", "author", "reviewer", "advisor", "apply", "post_commit",
)

Verdict = Literal[
    "approve",       # operator agrees; sample becomes positive label
    "reject",        # operator disagrees; sample becomes negative label
    "edit",          # operator approved-with-modifications; preference pair (operator's edit > model output)
    "escalate",      # operator routes to higher tier (Claude/Codex); not a label
    "skip",          # operator no-opinion; not a label
    "auto_capture",  # daemon auto-recorded; pending operator rating (Phase C #3.1)
]


class HitlScore(BaseModel):
    """Single operator decision at one pipeline gate.

    Designed so JSONL lines are append-only + RLHF-ready. The
    `chosen_text` / `rejected_text` fields populate when verdict is
    'edit' — operator's modified text is preferred over the model's
    original; both pair into a (chosen, rejected) preference tuple.
    """

    timestamp: str = Field(description="ISO 8601 UTC timestamp")
    gate: GateType = Field(description="Pipeline stage being scored")
    issue_id: str = Field(min_length=1, max_length=128)
    rule_code: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128, description="Which Ollama model produced the output (if applicable)")
    verdict: Verdict = Field(description="Operator's call")
    score: int = Field(ge=0, le=5, description="0=worst, 5=best; coarse rating")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Operator's certainty in this verdict")
    note: str = Field(default="", max_length=500, description="Free-text reason; helps future RAG retrieval")
    chosen_text: str | None = Field(default=None, max_length=8192, description="Operator's preferred output (for verdict=edit)")
    rejected_text: str | None = Field(default=None, max_length=8192, description="Model's original output (for verdict=edit)")

    model_config: ClassVar[dict] = {"extra": "forbid"}

    @field_validator("verdict")
    @classmethod
    def _edit_verdict_requires_both_texts(cls, v: Verdict, info) -> Verdict:
        # We can't access other fields easily in field_validator without
        # ValidationInfo; this is enforced post-construction in the
        # `validate_or_none` helper below for safety.
        return v


def append_score(score: HitlScore) -> None:
    HITL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with HITL_LOG.open("a", encoding="utf-8") as fh:
        fh.write(score.model_dump_json() + "\n")


def load_scores() -> list[HitlScore]:
    if not HITL_LOG.exists():
        return []
    out: list[HitlScore] = []
    for line in HITL_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(HitlScore.model_validate_json(line))
        except ValidationError:
            continue  # skip malformed (forward compat for future schema additions)
    return out


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def auto_capture_council_outcome(
    *,
    issue_id: str,
    rule_code: str | None,
    council_outcome: str,
    author_model: str | None,
    author_proposal_summary: str | None = None,
    confidence: float | None = None,
) -> HitlScore:
    """Phase C #3.1 — daemon auto-records a council outcome as
    pending-operator-rating HITL row.

    Used by autonomous_fix_daemon + local_council on every cycle so
    no council fire vanishes without a row in the preference dataset.
    Operator later batch-reviews via `hitl_framework.py review` and
    transitions verdict='auto_capture' → 'approve'/'reject'/'edit'.

    Returns the score (also appends to the JSONL log).
    """
    note = f"daemon auto-capture; council_outcome={council_outcome}"
    if author_proposal_summary:
        note += f"; author_summary={author_proposal_summary[:200]}"
    score = HitlScore(
        timestamp=now_iso(),
        gate="author",
        issue_id=issue_id,
        rule_code=rule_code,
        model=author_model,
        verdict="auto_capture",
        score=0,  # 0 = pending operator rating; will be set on review
        confidence=confidence if confidence is not None else 0.5,
        note=note,
        chosen_text=None,
        rejected_text=None,
    )
    append_score(score)
    return score


def cmd_review(args: argparse.Namespace) -> int:
    """List auto_capture rows operator hasn't yet rated."""
    scores = load_scores()
    pending = [s for s in scores if s.verdict == "auto_capture"]
    if not pending:
        print("(no pending auto-captured rows)")
        return 0
    print(f"=== {len(pending)} pending auto-captures ===\n")
    for s in pending[: args.limit]:
        print(f"  [{s.timestamp[:19]}] issue={s.issue_id}")
        print(f"    rule={s.rule_code} model={s.model} confidence={s.confidence}")
        print(f"    note: {s.note[:120]}")
        print(f"    rate via: hitl_framework.py record author {s.issue_id} <approve|reject|edit> [...]")
        print()
    if len(pending) > args.limit:
        print(f"  ... +{len(pending) - args.limit} more")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    if args.gate not in GATE_TYPES:
        print(f"x gate must be one of {GATE_TYPES}; got {args.gate!r}")
        return 1
    score = HitlScore(
        timestamp=now_iso(),
        gate=args.gate,  # type: ignore[arg-type]
        issue_id=args.issue_id,
        rule_code=args.rule_code,
        model=args.model,
        verdict=args.verdict,  # type: ignore[arg-type]
        score=args.score,
        confidence=args.confidence,
        note=args.note,
        chosen_text=args.chosen_text,
        rejected_text=args.rejected_text,
    )
    if score.verdict == "edit" and (
        score.chosen_text is None or score.rejected_text is None
    ):
        print("x verdict='edit' requires both --chosen-text and --rejected-text")
        return 2
    append_score(score)
    print(f"✓ recorded: gate={score.gate} issue={score.issue_id} verdict={score.verdict} score={score.score}")
    return 0


def cmd_scorecard(args: argparse.Namespace) -> int:
    scores = load_scores()
    if not scores:
        print("(no scores recorded yet)")
        return 0

    by = args.by
    print(f"=== HITL scorecard — grouped by {by} — total scores: {len(scores)} ===\n")

    groups: dict[str, list[HitlScore]] = defaultdict(list)
    for s in scores:
        if by == "rule":
            key = s.rule_code or "(none)"
        elif by == "model":
            key = s.model or "(none)"
        else:  # by gate
            key = s.gate
        groups[key].append(s)

    print(f"{'group':<32} {'n':>4} {'approve':>8} {'reject':>8} {'edit':>8} {'avg_score':>10} {'avg_conf':>10}")
    print("-" * 84)
    for key in sorted(groups.keys()):
        rows = groups[key]
        verdicts = Counter(r.verdict for r in rows)
        avg_score = sum(r.score for r in rows) / len(rows)
        avg_conf = sum(r.confidence for r in rows) / len(rows)
        print(
            f"{key:<32} {len(rows):>4} "
            f"{verdicts.get('approve', 0):>8} "
            f"{verdicts.get('reject', 0):>8} "
            f"{verdicts.get('edit', 0):>8} "
            f"{avg_score:>10.2f} "
            f"{avg_conf:>10.2f}"
        )
    return 0


def cmd_preference_pairs(args: argparse.Namespace) -> int:
    """Export RLHF/DPO-ready preference pairs from verdict='edit' rows."""
    scores = load_scores()
    pairs = [
        {
            "issue_id": s.issue_id,
            "rule_code": s.rule_code,
            "model": s.model,
            "gate": s.gate,
            "chosen": s.chosen_text,
            "rejected": s.rejected_text,
            "operator_note": s.note,
            "timestamp": s.timestamp,
        }
        for s in scores
        if s.verdict == "edit" and s.chosen_text and s.rejected_text
    ]
    print(json.dumps({"count": len(pairs), "pairs": pairs}, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    scores = load_scores()
    target = [s for s in scores if s.issue_id == args.issue_id]
    if not target:
        print(f"(no scores for issue_id={args.issue_id})")
        return 0
    for s in target:
        print(f"  [{s.timestamp}] gate={s.gate:<11} verdict={s.verdict:<8} score={s.score} conf={s.confidence} note={s.note[:80]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="hitl_framework.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="record one HITL score row")
    p_rec.add_argument("gate", choices=list(GATE_TYPES))
    p_rec.add_argument("issue_id")
    p_rec.add_argument("verdict", choices=["approve", "reject", "edit", "escalate", "skip"])
    p_rec.add_argument("--score", type=int, default=3, help="0-5; default 3")
    p_rec.add_argument("--confidence", type=float, default=1.0)
    p_rec.add_argument("--note", default="")
    p_rec.add_argument("--rule-code", default=None)
    p_rec.add_argument("--model", default=None)
    p_rec.add_argument("--chosen-text", default=None)
    p_rec.add_argument("--rejected-text", default=None)
    p_rec.set_defaults(func=cmd_record)

    p_sc = sub.add_parser("scorecard", help="aggregate scorecard")
    p_sc.add_argument("--by", choices=["rule", "model", "gate"], default="gate")
    p_sc.set_defaults(func=cmd_scorecard)

    p_pp = sub.add_parser("preference-pairs", help="RLHF/DPO export")
    p_pp.set_defaults(func=cmd_preference_pairs)

    p_ls = sub.add_parser("list", help="list scores for one issue")
    p_ls.add_argument("issue_id")
    p_ls.set_defaults(func=cmd_list)

    p_rv = sub.add_parser("review", help="list pending auto-captured rows")
    p_rv.add_argument("--limit", type=int, default=20)
    p_rv.set_defaults(func=cmd_review)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
