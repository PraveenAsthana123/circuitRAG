#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: per-module flow diagrams contract.

Locks docs/architecture/MODULE-FLOWS.md so every shipped module
keeps a verifiable input/process/output diagram. Without this drill,
modules can be added without their flowchart, and operators lose
the canonical reference for "how does X work end-to-end".

Negative assertions cover: file absent; missing module section;
mermaid block missing; placeholder language; PLANNED status not
honestly marked for vectorless RAG (wrapper shipped, integration
not).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "architecture" / "MODULE-FLOWS.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: MODULE-FLOWS.md exists --")
    if not DOC.exists():
        raise AssertionError(f"missing {DOC.relative_to(REPO)}")
    text = DOC.read_text(encoding="utf-8")
    print("  ok: doc present")

    print("-- 2. POSITIVE: covers all 11 canonical modules --")
    for section in (
        "## 1. MCP server",
        "## 2. Load balancer",
        "## 3. API gateway",
        "## 4. Circuit breaker",
        "## 5. Istio sidecar",
        "## 6. gRPC",
        "## 7. Kafka",
        "## 8. RAG (vector + graph hybrid",
        "## 9. Vectorless RAG",
        "## 10. Council pattern",
        "## 11. Sync vs async request paths",
    ):
        require(text, section, f"section: {section}")
    print("  ok: 11 module sections present")

    print("-- 3. POSITIVE: each module has a Mermaid flowchart --")
    flowcharts = re.findall(r"```mermaid\s+flowchart", text)
    if len(flowcharts) < 11:
        raise AssertionError(
            f"expected 11+ Mermaid flowcharts (one per module); got {len(flowcharts)}"
        )
    print(f"  ok: {len(flowcharts)} Mermaid flowchart blocks (>= 11)")

    print("-- 4. POSITIVE: each module has input/process/output table --")
    # Tables have the headers "| Layer | Input | Output |".
    layer_tables = text.count("| Layer | Input | Output |")
    if layer_tables < 8:
        raise AssertionError(
            f"expected 8+ input/output tables; got {layer_tables}"
        )
    print(f"  ok: {layer_tables} per-module input/output tables")

    print("-- 5. NEGATIVE: vectorless RAG MUST be marked PLANNED --")
    # The wrapper is shipped but no ingestion populates ES. If the
    # doc later claims it's wired, that's a false claim until
    # ingestion lands.
    require(text, "ingestion pipeline ❌ NOT WIRED", "vectorless PLANNED marker")
    print("  ok: vectorless RAG honestly marked PLANNED")

    print("-- 6. NEGATIVE: Istio MUST be marked CONFIG-only / not running --")
    # Same honesty rule: Istio YAML exists but mesh isn't deployed by
    # default. Operator runs scripts/istio-up.sh.
    require(text, "CONFIG SHIPPED, MESH NOT RUNNING", "Istio not-running marker")
    print("  ok: Istio status honestly marked")

    print("-- 7. POSITIVE: each module cites code path + drill --")
    require(text, "## Where each module's code lives", "code-path table")
    require(text, "drill_breaker_transitions", "breaker drill citation")
    require(text, "drill_api_gateway_compose", "api-gateway drill citation")
    require(text, "drill_elastic_searcher_skeleton", "elastic drill citation")
    print("  ok: code paths + drill references present")

    print("-- 8. POSITIVE: composes with STATUS + MISSING + component-trust --")
    require(text, "STATUS.md", "STATUS.md cross-ref")
    require(text, "MISSING.md", "MISSING.md cross-ref")
    require(text, "component-trust.md", "component-trust runbook cross-ref")
    require(text, "C4-context", "C4 cross-ref")
    print("  ok: 4 canonical state docs cross-referenced")

    print("-- 9. NEGATIVE: doc MUST NOT carry placeholder language --")
    for forbidden in ("TODO", "TBD", "FIXME", "Lorem ipsum"):
        if forbidden in text:
            raise AssertionError(f"forbidden placeholder in MODULE-FLOWS.md: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 10. POSITIVE: Brutal rule + aspirational-PLANNED warning --")
    require(text, "Brutal rule", "Brutal rule heading")
    require(text, "aspirational", "aspirational PLANNED warning")
    print("  ok: Brutal rule cites aspirational vs grounded")

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
