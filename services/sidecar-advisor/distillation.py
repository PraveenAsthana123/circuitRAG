"""Memory pattern distillation — turns rated events into reusable patterns.

The Sidecar Advisor records every advisor_output + user_rating. Most
of those events are noise. A pattern emerges when the same advice
*shape* appears across multiple events with consistent ratings:

  * "add tests for the error path" — appeared in 5 events,
    all marked useful → pattern_kind=preference, confidence high
  * "rename foo to bar for style" — appeared in 3 events, all
    marked not_useful → pattern_kind=mistake, "skip this in future"

Phase 2C is heuristic-only:

  1. Group rated events by event_type.
  2. For each event_type, count advice-string frequency across the
     top_3_advice fields.
  3. Promote any advice that appears in ≥ MIN_FREQUENCY events with
     a consistent rating (≥ MIN_CONSISTENCY of one polarity) to a
     pattern.

What's NOT here (deferred to Phase 2C+):

  * Embedding-based clustering — exact-string match is brittle
    ("add tests" vs "add unit tests"). A 384-dim sentence
    embedder + cosine threshold catches paraphrases.
  * LLM-based pattern naming — the heuristic uses the raw advice
    string as pattern_text. An LLM could distil "add tests for
    error path" + "missing edge-case tests" → "user wants thorough
    error-path test coverage".
  * Scheduled background distillation — current design is operator-
    triggered (call distill() from CLI / future UI button).

Idempotency contract: distill() is safe to re-run. If a pattern
already exists with the same (pattern_kind, pattern_text), the
distiller appends new source_event_ids to it instead of inserting
a duplicate. Confidence is recomputed from the merged event set.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Defaults — tuneable. Conservative thresholds for Phase 2C MVP:
# fewer false-positive patterns at the cost of slower learning.
MIN_FREQUENCY = 3            # advice must appear in ≥ this many events
MIN_CONSISTENCY = 0.66       # ≥ 2/3 of ratings agree on direction
PREFERENCE_LABEL = "useful"
MISTAKE_LABEL = "not_useful"


@dataclass(frozen=True)
class DistilledPattern:
    """One pattern proposed by the distiller. Either inserted as a new
    advisor_memory row OR merged into an existing pattern with the
    same (kind, text)."""

    pattern_kind: str          # preference | mistake
    pattern_text: str
    confidence: float          # 0.0–1.0; freq-weighted polarity score
    source_event_ids: list[int]
    event_type: str            # which route's events produced this


def _extract_advice(advisor_output_json: str | None) -> list[str]:
    """Pull top_3_advice strings out of an event row. Returns empty
    list if the row never got an advisor_output (rare; happens when
    the advisor errored before producing JSON)."""
    if not advisor_output_json:
        return []
    try:
        data = json.loads(advisor_output_json)
    except (json.JSONDecodeError, TypeError):
        return []
    advice = data.get("top_3_advice") or []
    if not isinstance(advice, list):
        return []
    out = []
    for item in advice:
        s = str(item).strip().lower()
        if s:
            out.append(s)
    return out


def distill(
    events: list[dict],
    *,
    existing_patterns: list[dict] | None = None,
    min_frequency: int = MIN_FREQUENCY,
    min_consistency: float = MIN_CONSISTENCY,
) -> list[DistilledPattern]:
    """Run the heuristic distillation over a batch of events.

    Args:
        events: rows from advisor_events. Caller is responsible for
            filtering — typically pass `recent_events(rated_only=True)`.
            Events without a user_rating are silently skipped (the
            heuristic needs a polarity signal).
        existing_patterns: rows from advisor_memory. The returned
            DistilledPattern objects whose (kind, text) collide with
            an existing pattern carry only the NEW source_event_ids,
            so the caller can append rather than replace.
        min_frequency, min_consistency: tuneable thresholds. Defaults
            chosen for "useful from day 1" not "perfectly accurate".

    Returns:
        A list of DistilledPattern. Empty if no patterns met the
        thresholds (e.g. brand-new system, only 2 ratings yet).
    """
    if not events:
        return []
    existing_keys = set()
    if existing_patterns:
        for p in existing_patterns:
            existing_keys.add((p["pattern_kind"], p["pattern_text"]))

    # ── Step 1: group events by event_type ──────────────────────
    by_type: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        if ev.get("user_rating") not in (PREFERENCE_LABEL, MISTAKE_LABEL):
            continue
        by_type[ev["event_type"]].append(ev)

    proposals: list[DistilledPattern] = []

    # ── Step 2: per-type advice frequency + polarity ────────────
    for event_type, type_events in by_type.items():
        # advice_text → {rating → [event_ids]}
        advice_polarity: dict[str, dict[str, list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for ev in type_events:
            for advice in _extract_advice(ev.get("advisor_output")):
                advice_polarity[advice][ev["user_rating"]].append(ev["id"])

        # ── Step 3: promote eligible advice to patterns ─────────
        for advice, by_rating in advice_polarity.items():
            useful_ids = by_rating.get(PREFERENCE_LABEL, [])
            mistake_ids = by_rating.get(MISTAKE_LABEL, [])
            total = len(useful_ids) + len(mistake_ids)
            if total < min_frequency:
                continue
            useful_share = len(useful_ids) / total
            mistake_share = len(mistake_ids) / total

            if useful_share >= min_consistency:
                kind = "preference"
                source_ids = sorted(useful_ids)
                # Confidence: weight by frequency + polarity strength.
                # A 5-event 100%-useful advice is more confident than
                # a 3-event 67%-useful advice. Capped at 0.95 — never
                # claim certainty from a heuristic.
                confidence = min(0.95, 0.4 + 0.1 * total + 0.2 * useful_share)
            elif mistake_share >= min_consistency:
                kind = "mistake"
                source_ids = sorted(mistake_ids)
                confidence = min(0.95, 0.4 + 0.1 * total + 0.2 * mistake_share)
            else:
                # Mixed signal — appeared 3+ times but ratings
                # contradict each other. Skip; the user is
                # inconsistent on this item.
                log.info(
                    "distillation_skip_mixed advice=%r useful=%d mistake=%d",
                    advice[:60], len(useful_ids), len(mistake_ids),
                )
                continue

            proposals.append(DistilledPattern(
                pattern_kind=kind,
                pattern_text=advice,
                confidence=round(confidence, 3),
                source_event_ids=source_ids,
                event_type=event_type,
            ))

    # ── Step 4: dedupe against existing patterns (idempotent) ──
    # If (kind, text) already exists, the caller will append the
    # NEW event_ids. Mark the proposal so downstream knows. We do
    # this by emitting only event_ids the existing pattern doesn't
    # already cite. If the existing pattern already cites every
    # event_id in source_event_ids, the proposal is a no-op and
    # filtered out.
    if existing_patterns:
        existing_by_key: dict[tuple[str, str], dict] = {
            (p["pattern_kind"], p["pattern_text"]): p
            for p in existing_patterns
        }
        filtered: list[DistilledPattern] = []
        for prop in proposals:
            existing = existing_by_key.get(
                (prop.pattern_kind, prop.pattern_text)
            )
            if existing is None:
                filtered.append(prop)
                continue
            try:
                already_cited = set(json.loads(existing["source_events"]))
            except (json.JSONDecodeError, TypeError):
                already_cited = set()
            new_ids = [
                eid for eid in prop.source_event_ids
                if eid not in already_cited
            ]
            if not new_ids:
                continue  # nothing new — filter out
            # Emit a proposal carrying ONLY the new ids; caller appends.
            filtered.append(DistilledPattern(
                pattern_kind=prop.pattern_kind,
                pattern_text=prop.pattern_text,
                confidence=prop.confidence,
                source_event_ids=new_ids,
                event_type=prop.event_type,
            ))
        proposals = filtered

    # Stable sort by (kind asc, confidence desc) so the test asserts
    # are deterministic.
    proposals.sort(key=lambda p: (p.pattern_kind, -p.confidence))
    return proposals


def format_for_prompt(
    patterns: list[dict], *, max_per_kind: int = 3,
) -> str:
    """Render existing patterns into a prompt-context preamble.

    Top-K preferences + top-K mistakes per call. The advisor injects
    this above the user's content so the LLM sees what to lean into
    and what to avoid.

    Empty string if no patterns to render — caller can `if context:` a
    no-op when memory is cold.
    """
    if not patterns:
        return ""
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for p in patterns:
        by_kind[p["pattern_kind"]].append(p)
    for k in by_kind:
        # Sort each kind by confidence desc + recency
        by_kind[k].sort(
            key=lambda p: (p.get("confidence", 0.0)),
            reverse=True,
        )

    lines: list[str] = []
    prefs = by_kind.get("preference", [])[:max_per_kind]
    mistakes = by_kind.get("mistake", [])[:max_per_kind]

    if prefs:
        lines.append("User preferences (from past feedback):")
        for p in prefs:
            lines.append(
                f"- {p['pattern_text']} "
                f"(confidence={p.get('confidence', 0):.2f})"
            )
    if mistakes:
        if prefs:
            lines.append("")
        lines.append("Avoid suggesting (user has rejected before):")
        for p in mistakes:
            lines.append(
                f"- {p['pattern_text']} "
                f"(confidence={p.get('confidence', 0):.2f})"
            )
    return "\n".join(lines)
