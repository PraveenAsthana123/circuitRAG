#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: /admin/aiops/deep — OTel-everywhere topic (per §43 + §47.6 + §48 + §57.7).

Locks the AIOps deep-dive's "OpenTelemetry must link with every
tool" topic — the operator-readable surface for the per-tool span
coverage discipline. The discipline itself is implementation work
(instrument every tool with a span); this drill enforces that the
TOPIC is on the page, marked PARTIAL until empirical coverage
proves otherwise, and lists the canonical drills that lock the
implementation contract.

Eight steps. Four negative.

Step coverage:
  1. POSITIVE: aiops/deep/page.tsx exists + has the otel-everywhere
     topic slug
  2. POSITIVE: status is 'partial' (not 'shipped' — §57.7 honesty:
     coverage is a discipline, not a one-time merge)
  3. POSITIVE: topic references the 5 canonical lock drills
     (otel_actor_outcome_attrs, guardrail_otel_attributes,
     circuit_breaker_observability, observability_stack_provisioning,
     this drill itself)
  4. NEGATIVE: status MUST NOT be 'shipped' — flipping requires
     empirical per-tool coverage proof + a separate drill that
     enumerates every tool + asserts its span is observable
  5. NEGATIVE: topic mentions at least 3 failure modes (without
     them the topic is hopium — §47 fail-safe means surfacing
     what breaks)
  6. NEGATIVE: topic mentions at least 3 monitoring signals
     (without them you cannot detect drift in coverage)
  7. POSITIVE: process step references request_id baggage AND
     sampling — both are required for cross-service trace
     completeness
  8. POSITIVE: topic mentions both Jaeger AND Langfuse as
     consumers — same OTLP wire, two views, both required
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = (
    REPO / "services" / "frontend" / "app" / "admin" / "aiops" / "deep" / "page.tsx"
)


GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


# Required drills the topic MUST cite — these lock the
# implementation contract that makes "shipped" status defensible.
REQUIRED_DRILLS = [
    "drill_otel_actor_outcome_attrs",
    "drill_guardrail_otel_attributes",
    "drill_circuit_breaker_observability",
    "drill_observability_stack_provisioning",
    "drill_aiops_deep_otel_topic",
]


def main() -> int:
    # ── 1. file exists + slug present ─────────────────────────────────
    step("1. POSITIVE: aiops/deep/page.tsx has otel-everywhere topic slug")
    if not PAGE.exists():
        fail(f"missing: {PAGE.relative_to(REPO)}")
    src = PAGE.read_text(encoding="utf-8")
    if "'otel-everywhere-tool-coverage'" not in src and '"otel-everywhere-tool-coverage"' not in src:
        fail("topic slug 'otel-everywhere-tool-coverage' not found on page")
    ok(f"page {len(src)}b — topic slug present")

    # Locate just the otel topic block — between its slug and the next
    # `},` that closes a topic.
    slug_idx = max(
        src.find("'otel-everywhere-tool-coverage'"),
        src.find('"otel-everywhere-tool-coverage"'),
    )
    if slug_idx < 0:
        fail("cannot locate topic body")
    # Find the topic closure — heuristic: next "  },\n]" pattern after slug
    close_match = re.search(r"\n  \},\n\];", src[slug_idx:])
    if not close_match:
        fail("cannot locate topic closure")
    topic_block = src[slug_idx : slug_idx + close_match.start()]

    # ── 2. status is 'partial' (not 'shipped') — §57.7 honesty ────────
    step("2. POSITIVE: status is 'partial' (per §57.7 honesty)")
    if "status: 'partial'" not in topic_block and 'status: "partial"' not in topic_block:
        fail("topic status MUST be 'partial' until per-tool coverage proven")
    ok("status: 'partial' — honest reflection of incomplete coverage")

    # ── 3. all 5 canonical drills referenced ──────────────────────────
    step("3. POSITIVE: 5 canonical lock drills referenced")
    missing = [d for d in REQUIRED_DRILLS if d not in topic_block]
    if missing:
        fail(f"topic missing drill references: {missing}")
    ok(f"all {len(REQUIRED_DRILLS)} canonical drills cited")

    # ── 4. NEGATIVE: status MUST NOT be 'shipped' ─────────────────────
    step("4. NEGATIVE: status MUST NOT be 'shipped' on this topic")
    if "status: 'shipped'" in topic_block or 'status: "shipped"' in topic_block:
        fail(
            "status='shipped' for OTel-everywhere requires an empirical "
            "per-tool coverage drill + scorecard. Build that first, "
            "then flip — never the reverse (§57.7)."
        )
    ok("status drift to 'shipped' blocked at code-review time")

    # ── 5. NEGATIVE: at least 3 failure modes ─────────────────────────
    step("5. NEGATIVE: topic lists ≥ 3 failure modes (no hopium)")
    fm_count = topic_block.count("mode: '") + topic_block.count('mode: "')
    if fm_count < 3:
        fail(
            f"topic has only {fm_count} failure mode(s); §47 fail-safe "
            "requires surfacing what breaks (≥ 3)"
        )
    ok(f"{fm_count} failure modes enumerated")

    # ── 6. NEGATIVE: at least 3 monitoring signals ────────────────────
    step("6. NEGATIVE: topic lists ≥ 3 monitoring signals")
    # The monitoring array entries each appear on their own quoted line.
    monitor_match = re.search(
        r"monitoring:\s*\[(.*?)\],\s*\n", topic_block, re.DOTALL
    )
    if not monitor_match:
        fail("topic missing monitoring array")
    monitor_body = monitor_match.group(1)
    monitor_entries = re.findall(r"['\"][^'\"]+['\"]", monitor_body)
    if len(monitor_entries) < 3:
        fail(
            f"only {len(monitor_entries)} monitoring entries; without ≥ 3 "
            "you cannot detect drift in coverage"
        )
    ok(f"{len(monitor_entries)} monitoring signals enumerated")

    # ── 7. process references request_id baggage AND sampling ─────────
    step(
        "7. POSITIVE: process references request_id baggage AND sampling "
        "(both required for cross-service trace completeness)"
    )
    if "request_id" not in topic_block:
        fail("process must reference request_id baggage propagation")
    if "sampl" not in topic_block.lower():
        fail("process must reference sampling policy (head + tail)")
    ok("request_id baggage + sampling both referenced")

    # ── 8. mentions both Jaeger AND Langfuse ──────────────────────────
    step(
        "8. POSITIVE: topic mentions Jaeger AND Langfuse as OTLP "
        "consumers (same wire, two views)"
    )
    if "Jaeger" not in topic_block:
        fail("topic must mention Jaeger as a consumer")
    if "Langfuse" not in topic_block:
        fail("topic must mention Langfuse as the LLM-specific consumer")
    ok("Jaeger + Langfuse both referenced")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
