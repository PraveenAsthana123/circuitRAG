"""HyDE (Hypothetical Document Embeddings) adapter — Stage-1 (per §56).

Closes the empirical-test recall gap from
docs/architecture/rag-deep-test-2026-05-04.md: Q1 ("Half-Life 2") and
Q2 ("Apple iPod") returned 0 useful chunks because the corpus didn't
have matching content. The LLM saved it by refusing to hallucinate,
but vector search returned 5 unrelated chunks. HyDE bridges that
gap by generating a HYPOTHETICAL ANSWER first, embedding THAT, and
retrieving against it. Often improves recall on hard queries by
20-40% in published benchmarks.

ARCHITECTURE:
    User query → small LM generates hypothetical answer → embed
    hypothetical → retrieve against hypothetical embedding

Original RAG:
    Q "What is X?" → embed("What is X?") → retrieve nearest

HyDE RAG:
    Q "What is X?" → small LM: "X is a Y that Zs..." (hypothetical)
                  → embed(hypothetical) → retrieve nearest

The hypothetical doesn't need to be CORRECT — it just needs to be
in the same EMBEDDING NEIGHBORHOOD as a true answer document.
Empirically this beats query-only embedding because the hypothetical
is in the answer-distribution, not the question-distribution.

WHEN HYDE WINS:
  - Hard queries where direct embedding match fails
  - Queries phrased differently from corpus chunks
  - Answer-shape ≠ question-shape (most retrieval systems)

WHEN HYDE LOSES:
  - Easy queries (extra latency, no recall gain)
  - Queries already match corpus phrasing closely
  - Hallucinated hypothetical pulls retrieval into wrong neighborhood

HEURISTIC: only fire HyDE when min_score floor returns 0 chunks.
Composes with the empirical-gap fix from rag-deep-test.

OPERATOR OPT-IN:
    HYDE_ENABLED=1
    HYDE_MODEL=gemma3:1b              # small, fast
    HYDE_MAX_TOKENS=200               # hypothetical length
    HYDE_FIRE_ON_EMPTY=1              # only fire when min_score returns []

COMPOSES WITH (per §49):
    services/retrieval-svc/app/services/hybrid_retriever.py — Stage-2
        wires this AFTER min_score returns empty
    scripts/gemma_agent_council.py — uses same Ollama+Gemma stack
    docs/architecture/rag-deep-test-2026-05-04.md — empirical gap
    §38 — decision audit (HyDE fires logged with fall-back path)
    §43 — drill discipline
    §52 — brutal tool review (40-row when Stage-2 wires)
    §56 — Stage-1 6-gate adoption process
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

HYDE_ENABLED = os.getenv("HYDE_ENABLED", "").strip() == "1"
HYDE_MODEL = os.getenv("HYDE_MODEL", "gemma3:1b")
HYDE_MAX_TOKENS = int(os.getenv("HYDE_MAX_TOKENS", "200"))
HYDE_TIMEOUT_S = float(os.getenv("HYDE_TIMEOUT_S", "10"))
HYDE_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


class HyDEDisabled(RuntimeError):
    """Raised when generate() is called but env flag unset."""


@dataclass
class HyDEResult:
    """Per-call output. Caller embeds .hypothetical and retrieves."""
    ok: bool
    hypothetical: str
    original_query: str
    elapsed_ms: int
    model: str
    error: str | None = None


def is_available() -> bool:
    """Stage-1 §56 default-deny check."""
    return HYDE_ENABLED


def status() -> dict[str, Any]:
    """Operator status surface — same shape as other Stage-1 adapters."""
    return {
        "stage": 1,
        "enabled_env": HYDE_ENABLED,
        "available": is_available(),
        "model": HYDE_MODEL,
        "max_tokens": HYDE_MAX_TOKENS,
        "timeout_s": HYDE_TIMEOUT_S,
        "ollama_host": HYDE_OLLAMA_HOST,
        "wiring_status": "stage-1 adapter; Stage-2 wires into HybridRetriever as fallback when min_score returns empty",
        "next_stage": (
            "Stage-2 — wire generate() into HybridRetriever.retrieve "
            "AFTER min_score floor + only when chunks list is empty; "
            "embed the hypothetical and re-run vector search; "
            "audit row to .loop/hyde_audit.jsonl"
        ),
        "heuristic": "fire only when min_score returns []; avoid 2x latency on easy queries",
    }


def generate(query: str, *, model: str | None = None) -> HyDEResult:
    """Generate a hypothetical answer for the query.

    Returns HyDEResult with .hypothetical (the generated text) +
    .elapsed_ms + .model. Caller embeds the hypothetical and uses
    it as the retrieval query.

    Raises HyDEDisabled when env flag unset.

    On Ollama transport error: returns HyDEResult with ok=False +
    .error set; caller should fall back to original-query retrieval
    (safe default; HyDE is opt-in optimization, not a blocker).
    """
    if not is_available():
        raise HyDEDisabled(
            "HyDE disabled. Set HYDE_ENABLED=1 to use."
        )

    # The HyDE prompt is deliberately direct — we want a 1-paragraph
    # hypothetical answer in the answer-distribution, not a question
    # rephrase. Keep system prompt tight to keep latency low.
    system = (
        "Write a brief, factual paragraph that answers the user's "
        "question as if you knew the answer. Do not say 'I don't know'. "
        "Do not ask clarifying questions. Just write the most likely "
        "answer paragraph."
    )

    t0 = time.monotonic()
    chosen_model = model or HYDE_MODEL
    try:
        # Lazy httpx import — keeps cold-start fast for callers that
        # don't use HyDE.
        import httpx  # noqa: PLC0415
        r = httpx.post(
            f"{HYDE_OLLAMA_HOST}/api/generate",
            json={
                "model": chosen_model,
                "prompt": query,
                "system": system,
                "stream": False,
                "options": {
                    "num_predict": HYDE_MAX_TOKENS,
                },
            },
            timeout=HYDE_TIMEOUT_S,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if r.status_code != 200:
            return HyDEResult(
                ok=False,
                hypothetical="",
                original_query=query,
                elapsed_ms=elapsed_ms,
                model=chosen_model,
                error=f"ollama_status={r.status_code}",
            )
        data = r.json()
        hypothetical = (data.get("response") or "").strip()
        if not hypothetical:
            return HyDEResult(
                ok=False,
                hypothetical="",
                original_query=query,
                elapsed_ms=elapsed_ms,
                model=chosen_model,
                error="empty_hypothetical",
            )
        log.info(
            "hyde_generate q=%.40s len=%d elapsed_ms=%d model=%s",
            query, len(hypothetical), elapsed_ms, chosen_model,
        )
        return HyDEResult(
            ok=True,
            hypothetical=hypothetical,
            original_query=query,
            elapsed_ms=elapsed_ms,
            model=chosen_model,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.warning("hyde_generate transport error: %s", exc)
        return HyDEResult(
            ok=False,
            hypothetical="",
            original_query=query,
            elapsed_ms=elapsed_ms,
            model=chosen_model,
            error=f"{type(exc).__name__}: {str(exc)[:100]}",
        )


if __name__ == "__main__":
    import json
    import sys
    print("scripts/hyde_adapter.py — Stage-1 HyDE hypothetical-document adapter")
    print(f"Stage-1 opt-in via HYDE_ENABLED=1")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
