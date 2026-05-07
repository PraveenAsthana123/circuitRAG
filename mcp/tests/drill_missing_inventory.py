#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: MISSING.md state-of-art gap inventory contract.

Locks docs/MISSING.md so the canonical answer to "what would top-1%
need that we don't have" stays current. Without the drill, MISSING.md
can drift to claim things are shipped when they aren't (or worse,
claim things aren't shipped when they were just added).

Negative assertions cover: doc absent; missing critical category
section; placeholders left in; brutal-rule + recommended-adoption-
order sections both required.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "MISSING.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: MISSING.md exists --")
    if not DOC.exists():
        raise AssertionError(f"missing {DOC.relative_to(REPO)}")
    text = DOC.read_text(encoding="utf-8")
    print("  ok: MISSING.md present")

    print("-- 2. POSITIVE: covers all 6 canonical state-of-art categories --")
    for section in (
        "## Inference performance",
        "## Evaluation frameworks",
        "## Guardrails / Safety frameworks",
        "## Interpretability / Explainability",
        "## Agentic / A2A protocols",
        "## Governance / Responsible AI",
    ):
        require(text, section, f"section: {section}")
    print("  ok: 6 canonical sections present")

    print("-- 3. POSITIVE: covers each tool the operator listed --")
    for tool in (
        "vLLM",
        "TensorRT",
        "ONNX",
        "MLC-LLM",
        "KV cache",
        "Ragas",
        "Deepeval",
        "Guardrails AI",
        "NeMo Guardrails",
        "SHAP",
        "LIME",
        "MLflow",
        "EvidentlyAI",
        "Giskard",
        "LangGraph",
        "MCP",
    ):
        if tool not in text:
            raise AssertionError(f"MISSING.md does not cover '{tool}'")
    print("  ok: 16 tools/frameworks covered")

    print("-- 4. POSITIVE: backward + forward compat section present --")
    require(text, "Backward compat", "backward-compat section")
    require(text, "Forward compat", "forward-compat section")
    print("  ok: backward + forward compat both covered")

    print("-- 5. POSITIVE: recommended adoption order present --")
    require(text, "Recommended adoption order", "adoption order section")
    require(text, "Langfuse", "Langfuse top of adoption order")
    print("  ok: adoption order section + Langfuse cited (just shipped)")

    print("-- 6. POSITIVE: Brutal rule present --")
    require(text, "Brutal rule", "Brutal rule heading")
    require(text, "integrating standard frameworks", "integration framing")
    print("  ok: Brutal rule + integration framing")

    print("-- 7. NEGATIVE: doc MUST NOT carry placeholder language --")
    for forbidden in ("TODO", "TBD", "FIXME", "Lorem ipsum"):
        if forbidden in text:
            raise AssertionError(f"forbidden placeholder in MISSING.md: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 8. NEGATIVE: top-tier verdict MUST be honest, not aspirational --")
    # The doc should clearly state the platform is NOT yet top-tier
    # without the listed framework integrations.
    require(text, "NOT top 1%", "honest verdict")
    require(text, "mid-tier", "mid-tier framing")
    print("  ok: honest verdict declared")

    print("-- 9. POSITIVE: composes with STATUS.md --")
    require(text, "STATUS.md", "STATUS.md cross-reference")
    print("  ok: composes with STATUS.md")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
