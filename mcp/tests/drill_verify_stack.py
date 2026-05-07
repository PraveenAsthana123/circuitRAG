#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: verify-stack.sh + component-trust runbook contract.

Locks the per-component verification toolchain. Without this drill,
the verify script could silently lose health checks for critical
components (postgres, redis, qdrant, etc.) and operators would
get false-confidence PASS results that miss real failures.

Negative assertions cover: script absent or non-executable; missing
critical-tier component check; runbook absent or stripped of
correlation_id pattern; multimodal fixtures missing.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "verify-stack.sh"
RUNBOOK = REPO / "docs" / "runbooks" / "component-trust.md"
FIXTURES = REPO / "tests" / "fixtures" / "multimodal"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: verify-stack.sh exists + executable --")
    if not SCRIPT.exists():
        raise AssertionError(f"missing {SCRIPT.relative_to(REPO)}")
    if not (os.stat(SCRIPT).st_mode & 0o111):
        raise AssertionError(f"{SCRIPT.relative_to(REPO)} not executable")
    text = SCRIPT.read_text(encoding="utf-8")
    print("  ok: verify-stack.sh present + +x")

    print("-- 2. POSITIVE: covers all critical Tier-1 data stores --")
    for component in ("postgres", "redis", "qdrant", "neo4j", "minio", "kafka"):
        require(text, component, f"check for {component}")
    print("  ok: 6 Tier-1 data stores all checked")

    print("-- 3. POSITIVE: covers Tier-2 observability stack --")
    for component in ("prometheus", "grafana", "alertmanager", "otel-collector",
                      "jaeger", "node-exporter", "cadvisor"):
        require(text, component, f"check for {component}")
    print("  ok: 7 observability components all checked")

    print("-- 4. POSITIVE: covers Tier-3 LLM (ollama) --")
    require(text, "ollama", "ollama check")
    require(text, "11434", "ollama port")
    print("  ok: ollama checked")

    print("-- 5. POSITIVE: covers Tier-4 app services --")
    for component in ("api-gateway", "sidecar-advisor", "agent-orchestrator",
                      "retrieval-svc", "inference-svc", "frontend"):
        require(text, component, f"check for {component}")
    print("  ok: 6 app services all checked")

    print("-- 6. POSITIVE: covers Tier-5 critical drills --")
    for drill in ("drill_alertmanager", "drill_langgraph_pin",
                  "drill_cdn_cache", "drill_api_gateway",
                  "drill_minikube_istio", "drill_load_test",
                  "drill_dispatcher", "drill_ci_gates",
                  "drill_pii_redaction", "drill_langfuse",
                  "drill_elastic"):
        require(text, drill, f"runs {drill}")
    print("  ok: 11 critical drills wired")

    print("-- 7. POSITIVE: covers Tier-6 tooling (ruff + mypy) --")
    require(text, "ruff", "ruff check")
    require(text, "mypy", "mypy check")
    print("  ok: ruff + mypy hard-gates enforced")

    print("-- 8. NEGATIVE: SKIP/PASS/FAIL summary line MUST exist --")
    require(text, "PASS:", "PASS counter")
    require(text, "FAIL:", "FAIL counter")
    require(text, "SKIP:", "SKIP counter")
    print("  ok: 3-state summary present")

    print("-- 9. POSITIVE: runbook present + cites correlation_id pattern --")
    if not RUNBOOK.exists():
        raise AssertionError(f"missing {RUNBOOK.relative_to(REPO)}")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    require(runbook, "correlation_id", "correlation_id reference")
    require(runbook, "correlation_id = uuid", "correlation_id origin diagram")
    require(runbook, "issue_audit.jsonl", "audit JSONL reference")
    print("  ok: runbook documents correlation_id propagation")

    print("-- 10. NEGATIVE: runbook MUST cite Brutal rule --")
    # Without it, operators may trust narrative without verification.
    require(runbook, "Brutal rule", "Brutal rule heading")
    require(runbook, "verify-stack.sh", "verify-stack.sh reference")
    print("  ok: Brutal rule + verify-stack.sh cited")

    print("-- 11. POSITIVE: multimodal test fixtures present --")
    if not FIXTURES.exists():
        raise AssertionError(f"missing {FIXTURES.relative_to(REPO)}")
    for fname in ("sample.txt", "sample.csv", "sample.json"):
        f = FIXTURES / fname
        if not f.exists():
            raise AssertionError(f"missing fixture {f.relative_to(REPO)}")
        if f.stat().st_size < 50:
            raise AssertionError(f"fixture too small to be useful: {fname}")
    print("  ok: 3 multimodal fixtures present (txt, csv, json)")

    print("-- 12. NEGATIVE: fixtures MUST contain unique phrases for round-trip --")
    # Round-trip retrieval test depends on unique phrases that appear
    # ONCE in the corpus. If a refactor strips them, the round-trip
    # test in the runbook becomes non-falsifiable.
    txt = (FIXTURES / "sample.txt").read_text(encoding="utf-8")
    csv = (FIXTURES / "sample.csv").read_text(encoding="utf-8")
    json_f = (FIXTURES / "sample.json").read_text(encoding="utf-8")
    require(txt, "blue elephant", "txt unique phrase")
    require(csv, "orange porcupine", "csv unique phrase")
    require(json_f, "yellow zebra", "json unique phrase")
    print("  ok: 3 fixtures have unique phrases for round-trip retrieval")

    print("\nALL 12 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
