"""Judge engine — synthesizes agent responses into a CouncilDecision.

6-dimension scoring (per the user's spec — exact weights):
  Correctness  25
  Evidence     20
  Risk/Safety  20
  Completeness 15
  Cost/ROI     10
  Clarity      10
                ─── sum = 100

Phase 2 of the 7-phase plan. The judge is a SINGLE Ollama call with a
strict JSON-only system prompt; falls back to a deterministic
keyword-scoring path if the LLM JSON is malformed (drill enforces both).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
JUDGE_MODEL = os.getenv("COUNCIL_JUDGE_MODEL", "llama3.1:8b")
DEFAULT_TIMEOUT_S = 180

# Weight schedule per the user's spec.
DIM_WEIGHTS: dict[str, float] = {
    "correctness": 25.0,
    "evidence": 20.0,
    "risk_safety": 20.0,
    "completeness": 15.0,
    "cost_roi": 10.0,
    "clarity": 10.0,
}

JUDGE_SYSTEM = (
    "You are the Council Judge. Score the agent responses on 6 dimensions, "
    "synthesize a final answer, and emit STRICT JSON only (no prose).\n\n"
    "Dimensions and weights (each 0.0-1.0; the harness multiplies by weight):\n"
    "  correctness  (25)\n"
    "  evidence     (20)\n"
    "  risk_safety  (20)\n"
    "  completeness (15)\n"
    "  cost_roi     (10)\n"
    "  clarity      (10)\n\n"
    'Output JSON: {"final_decision": "approve|approve_with_changes|revise|reject|escalate", '
    '"recommended_action": "<paragraph>", "risks": ["..."], '
    '"scores": {"correctness": 0.85, "evidence": 0.7, ...}}'
)


@dataclass
class JudgeResult:
    final_decision: str
    recommended_action: str
    risks: list[str]
    scores_pct: dict[str, float]   # weighted 0-100 per dim
    confidence: float              # sum of weighted / 100
    raw: dict[str, Any]


def _llm_judge(prompt: str, *, timeout_s: int) -> dict[str, Any]:
    started = time.time()
    r = requests.post(
        OLLAMA_URL,
        json={
            "model": JUDGE_MODEL, "stream": False,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.2},
        },
        timeout=timeout_s,
    )
    r.raise_for_status()
    body = r.json()
    content = body["message"]["content"]
    fenced = re.search(r"\{[\s\S]*\}", content)
    if not fenced:
        raise ValueError("judge produced no JSON object")
    return {
        "parsed": json.loads(fenced.group(0)),
        "raw_content": content,
        "latency_ms": int((time.time() - started) * 1000),
    }


def _normalize_scores(raw_scores: dict[str, Any]) -> dict[str, float]:
    """Coerce judge scores into [0,1] and weight by DIM_WEIGHTS."""
    weighted: dict[str, float] = {}
    for dim, weight in DIM_WEIGHTS.items():
        v = raw_scores.get(dim, raw_scores.get(dim.replace("_", ""), 0.0))
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.0
        f = max(0.0, min(1.0, f))
        weighted[dim] = round(f * weight, 2)
    return weighted


def _fallback_scores() -> dict[str, float]:
    """Deterministic neutral score when judge fails — no auto-approve."""
    return {dim: round(weight * 0.5, 2) for dim, weight in DIM_WEIGHTS.items()}


_VALID_DECISIONS = {
    "approve", "approve_with_changes", "revise", "reject", "escalate",
}


def judge(
    *,
    user_input: str,
    agent_responses: list[Any],  # list of AgentResponse
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> JudgeResult:
    """Run the judge over the agent responses. Always returns a result.

    On LLM failure → fallback to neutral scores + ``revise`` decision —
    NEVER auto-approves on failure (§38 governance).
    """
    bullets = "\n\n".join(
        f"=== {a.role.upper()} (model={a.model}) ===\n{a.content}"
        for a in agent_responses
    )
    prompt = f"User question:\n{user_input}\n\n{bullets}"

    try:
        out = _llm_judge(prompt, timeout_s=timeout_s)
        parsed = out["parsed"]
        decision = str(parsed.get("final_decision", "revise")).lower()
        if decision not in _VALID_DECISIONS:
            decision = "revise"
        recommended = str(parsed.get("recommended_action", ""))[:2000]
        risks = [str(r)[:200] for r in (parsed.get("risks") or [])][:8]
        weighted = _normalize_scores(parsed.get("scores") or {})
        confidence = round(sum(weighted.values()) / 100.0, 3)
        return JudgeResult(
            final_decision=decision,
            recommended_action=recommended or "(no recommendation produced)",
            risks=risks,
            scores_pct=weighted,
            confidence=confidence,
            raw=parsed,
        )
    except Exception as e:  # noqa: BLE001 — single boundary
        weighted = _fallback_scores()
        return JudgeResult(
            final_decision="revise",
            recommended_action=(
                f"Judge call failed; fallback to revise. error={e!s}"
            ),
            risks=[f"judge_failed: {type(e).__name__}"],
            scores_pct=weighted,
            confidence=round(sum(weighted.values()) / 100.0, 3),
            raw={"error": str(e), "fallback": True},
        )


__all__ = ["DIM_WEIGHTS", "JudgeResult", "judge"]
