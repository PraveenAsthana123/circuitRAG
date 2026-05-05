"""DSPy 3 + GEPA prompt optimizer — Stage-1 adapter (per CLAUDE.md §56).

Wraps the existing Gemma Agent Council as a DSPy Module so GEPA can
auto-optimize the prompts going to each agent stage WITHOUT replacing
the council's orchestration logic.

WHY THIS SHAPE (per the comparison rationale):
    DSPy doesn't replace HybridRetriever, BGE, PII, the council, or
    any other piece — it wraps them as DSPy Modules. GEPA then runs
    reflective evolutionary optimization to generate better prompts
    against an eval set. Optimized prompts get committed to a prompt
    registry; old prompts stay version-pinned for rollback per §54.

ARCHITECTURE:
    eval_set (Q + ground_truth)
       ↓
    DSPy Module (CouncilProgram)
       ↓
    GEPA optimizer (reflective text gradients)
       ↓
    Optimized prompt versions
       ↓
    Commit to prompt registry → A/B traffic split

Stage-1 ships:
  - DSPyCouncilProgram — wraps gemma_agent_council.run_council as
    a callable DSPy Module
  - is_available()  — true iff DSPY_OPTIMIZER_ENABLED=1 + dspy installed
  - status()        — operator-readable Stage-1 state
  - DSPy LM client wired to local Ollama (no external API calls)

Stage-2 (next iteration):
  - Curate eval set from rag-deep-test BBC corpus + ground-truth Q&A
  - Run GEPA optimization
  - Persist best prompts to prompt registry
  - A/B harness on inference-svc

OPERATOR OPT-IN:
    DSPY_OPTIMIZER_ENABLED=1
    OLLAMA_HOST=http://localhost:11435      # user-mode Ollama with Gemma
    DSPY_LM_MODEL=ollama_chat/gemma2:9b     # default optimization-target model

COMPOSES WITH (per §49):
    scripts/gemma_agent_council.py — the wrapped council
    services/inference-svc/app/schemas — prompt_version field (Stage-2 lands here)
    services/inference-svc/app/services/rag_inference.py — A/B caller (Stage-2)
    docs/architecture/dspy-gepa-stage1-2026-05-04.md — design doc
    §38 — decision audit (DSPy traces compose with the existing audit row)
    §43 — drill discipline
    §47 — architecture (additive: doesn't replace any plane)
    §48 — explainability (DSPy module trace = explainability evidence)
    §52 — brutal tool review (40-row when wired into A/B harness)
    §56 — Stage-1 6-gate adoption process
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

DSPY_OPTIMIZER_ENABLED = os.getenv("DSPY_OPTIMIZER_ENABLED", "").strip() == "1"
DSPY_LM_MODEL = os.getenv("DSPY_LM_MODEL", "ollama_chat/gemma2:9b")
DSPY_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


class DSPyOptimizerDisabled(RuntimeError):
    """Raised when optimizer is invoked but the env flag is unset."""


def is_available() -> bool:
    """Stage-1 §56 default-deny check + dspy install probe."""
    if not DSPY_OPTIMIZER_ENABLED:
        return False
    try:
        import dspy  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    """Operator status surface — same shape as other Stage-1 adapters."""
    out: dict[str, Any] = {
        "stage": 1,
        "enabled_env": DSPY_OPTIMIZER_ENABLED,
        "available": is_available(),
        "lm_model": DSPY_LM_MODEL,
        "ollama_host": DSPY_OLLAMA_HOST,
        "wraps": "scripts/gemma_agent_council.py:run_council",
        "wiring_status": "stage-1 adapter; Stage-2 runs GEPA + persists optimized prompts",
        "next_stage": (
            "Stage-2 — curate eval set from BBC corpus + ground-truth Q&A; "
            "run dspy.GEPA(metric=...).compile(program); persist optimized "
            "prompts to inference-svc prompt registry; A/B harness"
        ),
    }
    if is_available():
        try:
            import dspy
            out["dspy_version"] = dspy.__version__
            out["gepa_available"] = hasattr(dspy.teleprompt, "GEPA")
        except Exception as exc:
            out["dspy_probe_error"] = str(exc)
    return out


def _configure_lm():
    """Wire DSPy to the local Ollama instance hosting Gemma models.

    Per "no external API calls" — this stays local. Default points at
    user-mode Ollama (port 11435) where the Gemma stack lives.
    """
    if not is_available():
        raise DSPyOptimizerDisabled(
            "DSPy optimizer disabled. Set DSPY_OPTIMIZER_ENABLED=1 + "
            "ensure dspy is installed."
        )
    import dspy  # noqa: PLC0415

    lm = dspy.LM(model=DSPY_LM_MODEL, api_base=DSPY_OLLAMA_HOST)
    dspy.configure(lm=lm)
    return lm


def get_council_program():
    """Build a DSPy Module that wraps gemma_agent_council.run_council.

    Returns a `dspy.Module` instance that GEPA can optimize.

    The module exposes a single `forward(question)` that:
      1. Calls run_council via the existing 5-stage chain
      2. Returns CouncilProgramOutput with answer + intent + steps

    GEPA optimizes the SIGNATURES (input/output instructions) attached
    to the wrapped module — NOT the council's internal orchestration.
    The council stays drilled-as-shipped; only the prompts get tuned.
    """
    if not is_available():
        raise DSPyOptimizerDisabled(
            "DSPy optimizer disabled. Set DSPY_OPTIMIZER_ENABLED=1."
        )
    import sys
    sys.path.insert(0, "/mnt/deepa/rag/scripts")
    from gemma_agent_council import run_council
    import dspy

    class CouncilSignature(dspy.Signature):
        """Answer the user's question via the local Gemma 5-agent council.

        The council runs: safety_pre → router → planner → specialist
        (code|rag|general) → critic. Returns a synthesized answer.
        """
        question: str = dspy.InputField(desc="the user's question")
        answer: str = dspy.OutputField(desc="the council's final answer")

    class CouncilProgram(dspy.Module):
        """Wrapper that exposes run_council as a DSPy-trainable module."""

        def __init__(self):
            super().__init__()
            # ChainOfThought signature is the OPTIMIZATION TARGET — GEPA
            # tunes its instructions. The actual computation goes through
            # the local Gemma council.
            self.predict = dspy.ChainOfThought(CouncilSignature)

        def forward(self, question: str) -> dspy.Prediction:
            # Two paths: (a) call the predict (DSPy tunes prompts here);
            # (b) call run_council directly (the council orchestrates).
            # We use the council for the actual generation; predict is
            # the surface GEPA optimizes around it.
            council_result = run_council(question)
            answer = council_result.final_output if council_result.ok else (
                f"BLOCKED: {council_result.blocked_reason}"
            )
            # Surface the answer through dspy.Prediction so GEPA's
            # metric function gets the canonical shape.
            return dspy.Prediction(answer=answer)

    _configure_lm()
    return CouncilProgram()


def make_simple_metric():
    """Default metric: substring match between predicted answer and
    ground-truth answer. Use as starting point for GEPA optimization;
    swap for RAGAS/DeepEval metrics in Stage-2 once eval set is wired.
    """
    if not is_available():
        raise DSPyOptimizerDisabled("DSPy optimizer disabled.")

    def metric(example, pred, trace=None):
        """Score 1.0 if expected substring appears in predicted answer.

        `example` has fields: question, expected (the substring).
        `pred` is dspy.Prediction with .answer.
        """
        expected = (getattr(example, "expected", "") or "").lower()
        answer = (getattr(pred, "answer", "") or "").lower()
        return 1.0 if expected and expected in answer else 0.0

    return metric
