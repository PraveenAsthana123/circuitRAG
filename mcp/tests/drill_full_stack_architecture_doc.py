#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: full-stack architecture doc — locks the canonical placement.

Per CLAUDE.md §43 + §49 (compose-footer pattern). The architecture doc
captures the user-ratified placement of PolisAI / Paperclip / Council /
OpenClaw. The drill prevents bit-rot:

  - All 11 layers documented (API Gateway → OpenClaw)
  - Every shipped component cross-references its actual file path
  - Paperclip's sandbox-only contract stays load-bearing (4 invariants)
  - Composes-with section names §38 / §42 / §43 / §47 / §48.4 + ADR-012

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "architecture" / "full-stack-architecture.md"


def main() -> int:
    print("-- 1. POSITIVE: doc exists --")
    if not DOC.exists():
        print(f"x {DOC} missing")
        return 1
    src = DOC.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x doc too short ({len(src)} chars); expected >=4000")
        return 1
    print(f"  ok: doc present ({len(src)} chars)")

    print("-- 2. POSITIVE: all 11 layers named in the request path --")
    required_layers = (
        "API Gateway", "Agent Router", "PolisAI", "Agent Council",
        "Agent Execution Layer", "Paperclip Sandbox Layer", "MCP Tool Layer",
        "RAG", "Governance", "Observability", "OpenClaw",
    )
    for layer in required_layers:
        if layer not in src:
            print(f"x layer {layer!r} not documented")
            return 1
    print(f"  ok: all {len(required_layers)} layers named")

    print("-- 3. POSITIVE: shipped components reference actual file paths --")
    expected_paths = (
        "scripts/policy_check.py",
        "scripts/paperclip_manager.py",
        "scripts/local_council.py",
        "config/policies/agent_dispatch.json",
        "services/agent-orchestrator-svc",
        "services/api-gateway",
        "services/retrieval-svc",
        "mcp/server",
    )
    for p in expected_paths:
        if p not in src:
            print(f"x file path {p!r} not referenced")
            return 1
    print(f"  ok: {len(expected_paths)} file paths cross-referenced")

    print("-- 4. NEGATIVE: doc does NOT claim Paperclip is production-safe --")
    # The whole point of the user's architecture is Paperclip is sandbox-only.
    # Bit-rot would re-classify Paperclip as production. Prevent it.
    # Each pattern is a UNAMBIGUOUS positive claim — "Paperclip <verb> X" with
    # no negation slot. Avoid `.*` greedy matches across the doc which
    # accidentally catch "NOT for production-mutation".
    forbidden_phrases = (
        r"Paperclip\s+is\s+production-safe",
        r"Paperclip\s+is\s+production-grade",
        r"Paperclip\s+is\s+production-ready",
        r"Paperclip\s+is\s+safe\s+for\s+production",
        r"Paperclip\s+can\s+mutate\s+production",
        r"Paperclip\s+supports\s+production",
    )
    for pattern in forbidden_phrases:
        if re.search(pattern, src, re.IGNORECASE):
            print(f"x doc claims Paperclip is production-safe: pattern {pattern!r}")
            return 1
    print("  ok: no production-safe claims for Paperclip")

    print("-- 5. NEGATIVE: doc does NOT place Policy AFTER agent execution --")
    # PolisAI must come BEFORE agent execution, not after. The doc must
    # not inadvertently document the wrong ordering.
    # Find the position of "PolisAI" header and "Agent Execution Layer".
    polis_pos = src.find("PolisAI")
    exec_pos = src.find("Agent Execution Layer")
    if polis_pos == -1 or exec_pos == -1:
        print("x cannot find PolisAI or Agent Execution Layer markers")
        return 1
    if polis_pos > exec_pos:
        print(f"x PolisAI documented AFTER Agent Execution (pos {polis_pos} > {exec_pos})")
        return 1
    print(f"  ok: PolisAI (pos {polis_pos}) precedes Agent Execution (pos {exec_pos})")

    print("-- 6. NEGATIVE: 4 sandbox invariants documented for Paperclip --")
    # The drill steps that lock Paperclip's sandbox contract must be
    # mirrored in the doc so the contract is grep-discoverable.
    invariants = (
        "No write-style function names",
        "No outbound HTTP imports",
        "Write verbs refused",
        "Snapshot does not mutate",
    )
    for inv in invariants:
        if inv not in src:
            print(f"x sandbox invariant not documented: {inv!r}")
            return 1
    print(f"  ok: all {len(invariants)} sandbox invariants documented")

    print("-- 7. NEGATIVE: composes-with section references all required policies --")
    required_refs = ("§38", "§42", "§43", "§47", "§48.4", "ADR-012")
    for ref in required_refs:
        if ref not in src:
            print(f"x composes-with missing reference: {ref!r}")
            return 1
    print(f"  ok: all {len(required_refs)} policy refs present")

    print("-- 8. POSITIVE: gap table marks OpenClaw + Agent Router + Governance as missing --")
    # The doc must be honest about what's NOT shipped. If those gaps
    # disappear without commits adding the components, that's drift.
    # Check that at LEAST ONE occurrence of each item appears within
    # ±200 chars of a missing/❌ marker (gap-table row), not just the
    # first occurrence (which may be in the layer-listing where the
    # missing flag would be misleading).
    must_be_marked_missing = (
        "Intent + Risk classifier",
        "OpenClaw",
        "Guardrails AI",
        "Ragas",
    )
    for item in must_be_marked_missing:
        if item not in src:
            print(f"x doc must mark {item!r} as ❌ missing")
            return 1
        # Find ALL occurrences; require at least one paired with missing/❌
        flagged = False
        start = 0
        while True:
            idx = src.find(item, start)
            if idx == -1:
                break
            window = src[max(0, idx - 200):idx + 200]
            if "missing" in window.lower() or "❌" in window:
                flagged = True
                break
            start = idx + len(item)
        if not flagged:
            print(f"x {item!r} mentioned but never flagged as ❌ missing")
            return 1
    print(f"  ok: {len(must_be_marked_missing)} gaps explicitly flagged as missing")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
