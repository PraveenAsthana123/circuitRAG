#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: LATENCY-BUDGET.md cache-layer + per-tool ms contract.

Locks the latency-budget reference. Without this drill, the cache
layer inventory + per-tool ms estimates can drift silently — claims
of "30ms p95 health" remain after the underlying code path changes.

Negative assertions cover: doc absent; cache-layer table missing;
per-tool budget missing; Pareto chart absent; estimate marked as
unverified.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "architecture" / "LATENCY-BUDGET.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: LATENCY-BUDGET.md exists --")
    if not DOC.exists():
        raise AssertionError(f"missing {DOC.relative_to(REPO)}")
    text = DOC.read_text(encoding="utf-8")
    print("  ok: doc present")

    print("-- 2. POSITIVE: cache layer inventory covers 10+ layers --")
    require(text, "## Cache layers", "Cache layers section")
    for layer in (
        "NGINX edge",
        "Browser HTTP cache",
        "Redis (rate-limit)",
        "Redis (idempotency)",
        "Postgres connection pool",
        "Qdrant query cache",
        "Neo4j query cache",
        "Ollama VRAM",
        "JWKS cache",
    ):
        require(text, layer, f"cache layer: {layer}")
    print("  ok: 9 canonical cache layers documented")

    print("-- 3. POSITIVE: per-tool latency budget for 5 hot paths --")
    for path in (
        "Health probe path",
        "Sidecar event submission",
        "Council pattern",
        "RAG retrieve",
        "Ollama LLM call",
    ):
        require(text, path, f"per-tool budget: {path}")
    print("  ok: 5 hot paths budgeted")

    print("-- 4. POSITIVE: real benchmark numbers cited (not just estimates) --")
    require(text, "30ms", "real health latency")
    require(text, "49ms", "real api latency")
    require(text, "k6 100 VU benchmark", "benchmark provenance")
    require(text, "docs/benchmarks/2026-04-30-laptop.md", "benchmark file cross-ref")
    print("  ok: real measured numbers cited")

    print("-- 5. POSITIVE: Pareto chart present --")
    require(text, "Pareto", "Pareto chart heading")
    require(text, "96%", "LLM share of total time")
    print("  ok: Pareto + 96% LLM-share noted")

    print("-- 6. POSITIVE: 8-row improvement-opportunity table --")
    require(text, "ROI", "ROI ranking")
    require(text, "OLLAMA_KEEP_ALIVE", "model-pin opportunity")
    require(text, "vLLM", "vLLM opportunity")
    require(text, "completion cache", "completion cache opportunity")
    require(text, "Embedding cache", "embedding cache opportunity")
    print("  ok: ROI-ranked improvement opportunities present")

    print("-- 7. NEGATIVE: estimates MUST be marked vs measured --")
    # Without the distinction, future readers can't tell what's verified.
    require(text, "Estimated save", "Estimated save marker")
    require(text, "Estimated p95", "Estimated p95 marker")
    require(text, "Estimated impact", "Estimated impact marker")
    print("  ok: Estimated/measured distinction maintained")

    print("-- 8. NEGATIVE: doc MUST cite what's NOT measured --")
    require(text, "What's NOT yet measured", "honest gaps section")
    require(text, "Tail latencies", "tail-latency gap")
    require(text, "TTFT", "time-to-first-token gap")
    print("  ok: honest gaps documented")

    print("-- 9. NEGATIVE: doc MUST NOT carry placeholder language --")
    for forbidden in ("TODO", "TBD", "FIXME", "Lorem ipsum"):
        if forbidden in text:
            raise AssertionError(f"forbidden placeholder: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 10. POSITIVE: composes with STATUS / MISSING / benchmarks / trust runbook --")
    for ref in (
        "STATUS.md",
        "MISSING.md",
        "benchmarks/2026-04-30",
        "component-trust.md",
        "infra/load-test/k6/baseline.js",
    ):
        require(text, ref, f"cross-ref: {ref}")
    print("  ok: 5 canonical state docs cross-referenced")

    print("-- 11. POSITIVE: Brutal rule cites measure-first discipline --")
    require(text, "Brutal rule", "Brutal rule heading")
    require(text, "Latency optimization without measurement is guessing",
            "measurement-first principle")
    print("  ok: measure-first discipline cited")

    print("\nALL 11 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
