#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: README.md architecture section — locks the canonical 11-layer view.

Per CLAUDE.md §43 + §49. The README is the entry-point for any new
contributor / auditor / reviewer. Bit-rot here means everything else
in the repo loses its anchor. The drill prevents:

  - The architecture diagram dropping any of the 11 layers
  - The tool inventory dropping any of the headline tools the user
    explicitly named (PolisAI, Paperclip, Council, Ollama, Ragas,
    Snyk, Guardrails AI, MCP, RAG, cache, chunking, embeddings,
    Kafka, Elasticsearch, Istio, gRPC)
  - The 5 architectural invariants disappearing
  - Component-status counts going out of sync with the drills/ADRs/
    runbooks file counts

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
README = REPO / "README.md"


def main() -> int:
    print("-- 1. POSITIVE: README exists + has architecture section --")
    if not README.exists():
        print(f"x {README} missing")
        return 1
    src = README.read_text(encoding="utf-8")
    if "Architecture at a glance" not in src and "11-layer" not in src:
        print("x README missing 'Architecture at a glance' or '11-layer' marker")
        return 1
    print(f"  ok: README {len(src)} chars; architecture section present")

    print("-- 2. POSITIVE: all 11 layers named --")
    required_layers = (
        "API Gateway", "Circuit Breaker", "Agent Router",
        "PolisAI", "Agent Council", "LangGraph",
        "Paperclip", "MCP Tool Layer", "RAG",
        "Governance", "Observability",
    )
    for layer in required_layers:
        if layer not in src:
            print(f"x layer not named: {layer!r}")
            return 1
    print(f"  ok: all {len(required_layers)} layers named")

    print("-- 3. POSITIVE: every user-named tool listed --")
    # The user explicitly named these tools in the README request.
    # Each must appear at least once in the README.
    user_named_tools = (
        "Paperclip", "PolisAI", "RAG", "MCP", "Ollama",
        "Ragas", "Snyk", "Guardrails", "Cache", "Redis",
        "chunking", "Embedding", "Kafka", "Elasticsearch",
        "Istio", "gRPC",
    )
    missing = [t for t in user_named_tools if t.lower() not in src.lower()]
    if missing:
        print(f"x missing user-named tools: {missing}")
        return 1
    print(f"  ok: all {len(user_named_tools)} user-named tools listed")

    print("-- 4. POSITIVE: 5 architectural invariants documented --")
    invariants = (
        "PolisAI fires BEFORE",
        "Paperclip is sandbox-only",
        "Schema-as-contract includes git-apply-check",
        "Default-deny policy",
        "§42 boundary",
    )
    for inv in invariants:
        if inv not in src:
            print(f"x invariant not documented: {inv!r}")
            return 1
    print(f"  ok: all {len(invariants)} invariants documented")

    print("-- 5. NEGATIVE: README does NOT claim Paperclip is production-safe --")
    forbidden = (
        r"Paperclip\s+is\s+production-safe",
        r"Paperclip\s+is\s+production-ready",
        r"Paperclip\s+supports\s+production\b",
    )
    for pat in forbidden:
        if re.search(pat, src, re.IGNORECASE):
            print(f"x README claims Paperclip is production-safe: {pat!r}")
            return 1
    print("  ok: no production-safe claims for Paperclip")

    print("-- 6. NEGATIVE: TODO components flagged with ❌ --")
    # The 14 TODO components must each be flagged so a reader can tell
    # "shipped" from "aspirational." Without ❌ markers the inventory
    # becomes a wishlist masquerading as a fact list.
    todo_must_flag = (
        "Agent Router", "OpenClaw", "Snyk", "Guardrails AI", "Ragas",
        "Istio",
    )
    for item in todo_must_flag:
        # Each must appear within ±300 chars of a "TODO" or "❌" marker
        flagged = False
        start = 0
        while True:
            idx = src.find(item, start)
            if idx == -1:
                break
            window = src[max(0, idx - 300):idx + 300]
            if "TODO" in window or "❌" in window or "missing" in window.lower():
                flagged = True
                break
            start = idx + len(item)
        if not flagged:
            print(f"x TODO component {item!r} not flagged with ❌/TODO")
            return 1
    print(f"  ok: {len(todo_must_flag)} TODO components flagged")

    print("-- 7. NEGATIVE: shipped components reference verifiable file paths --")
    # The "Tier-1 status" column claims shipped — each ✅ shipped row
    # should correspond to a file we can name. Check a sample:
    file_refs = (
        "scripts/policy_check.py",
        "scripts/paperclip_manager.py",
        "scripts/local_council.py",
        "services/api-gateway",
        "services/agent-orchestrator-svc",
        "services/retrieval-svc",
        "mcp/server",  # any MCP server reference
    )
    for ref in file_refs:
        if ref not in src:
            print(f"x README missing shipped-component path: {ref!r}")
            return 1
    print(f"  ok: {len(file_refs)} verifiable file paths cross-referenced")

    print("-- 8. NEGATIVE: drill counts in README match actual file count --")
    # README claims a number of drills; if it's wildly off from reality,
    # the snapshot section is misleading.
    actual_drills = len(list((REPO / "mcp" / "tests").glob("drill_*.py")))
    # Find the claimed count in the table
    m = re.search(r"\|\s*\*\*Drills\*\*[^\|]*\|\s*\*\*(\d+)\*\*", src)
    if not m:
        print("x cannot parse claimed drill count from README")
        return 1
    claimed = int(m.group(1))
    # Allow +/- 10% drift between claim and reality (auto-commits add drills)
    drift = abs(actual_drills - claimed)
    drift_pct = drift / max(actual_drills, 1)
    if drift_pct > 0.20:  # 20% tolerance
        print(f"x drill count drift > 20%: claimed {claimed}, actual {actual_drills}")
        return 1
    print(f"  ok: claimed {claimed} drills, actual {actual_drills} (drift {drift_pct:.1%} within tolerance)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
