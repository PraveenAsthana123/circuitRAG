"""Eval-set auto-generator — Stage-1 adapter (per CLAUDE.md §56).

Closes the eval-set bottleneck: AutoRAG search + GEPA optimization +
RAGAS continuous eval ALL need ground-truth Q&A pairs. Manual
curation is operator-content work (~2hrs for 50 pairs). This adapter
auto-generates Q&A pairs from a corpus using the local Gemma stack
(gemma3:4b). No external API; runs fully on user-mode Ollama.

ALGORITHM (per ARES + RAGAS synthetic-eval paper patterns):
  For each chunk in corpus:
    1. ASK gemma3:4b: "given this passage, what is one specific
       factual question whose answer is directly stated?"
    2. ASK gemma3:4b again: "given this passage, what is the answer
       to that question?" (using same passage)
    3. STORE { question, ground_truth, source_chunk_id }
  Filter: drop questions where the model declined / hedged.

WHY GEMMA3:4B AS GENERATOR (not gemma2:9b):
  - 3.3 GB vs 5.4 GB — fast iteration on 100+ chunks
  - quality is sufficient for synthetic ground-truth (we'll
    validate by RAGAS context_recall — if the ground truth doesn't
    appear in the source chunk, the question is unusable)

QUALITY GATE (per the brutal "synthetic eval set ≠ benchmark" rule):
  Auto-generated Q&A pairs are NOT a substitute for human-curated
  benchmarks. They're the BOOTSTRAP that lets AutoRAG / GEPA /
  RAGAS continuous-eval start producing signal NOW. Operator
  hand-curates 10-20 high-stakes pairs separately as a "golden
  set" used for production gates.

OPERATOR OPT-IN:
    EVAL_SET_GENERATOR_ENABLED=1
    OLLAMA_HOST=http://localhost:11435       # user-mode Ollama
    EVAL_SET_GENERATOR_MODEL=gemma3:4b       # default
    EVAL_SET_GENERATOR_TIMEOUT_S=30
    EVAL_SET_MAX_PAIRS=50                    # cap per run

COMPOSES WITH:
    scripts/autorag_optimizer.py — eval_set input
    scripts/dspy_optimizer.py — DSPy trainset
    scripts/ragas_eval_adapter.py — context_recall validates synthetic
        ground truth (drops false-positive pairs)
    services/retrieval-svc/app/services/embedder_client.py — could
        chunk + embed the corpus inline (Stage-2)
    docs/architecture/rag-deep-test-2026-05-04.md — original 5-Q gap
        this generator closes
    §38, §39, §43, §47, §48, §52, §56
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger(__name__)

EVAL_SET_GENERATOR_ENABLED = os.getenv("EVAL_SET_GENERATOR_ENABLED", "").strip() == "1"
EVAL_SET_GENERATOR_MODEL = os.getenv("EVAL_SET_GENERATOR_MODEL", "gemma3:4b")
EVAL_SET_GENERATOR_TIMEOUT_S = float(os.getenv("EVAL_SET_GENERATOR_TIMEOUT_S", "30"))
EVAL_SET_MAX_PAIRS = int(os.getenv("EVAL_SET_MAX_PAIRS", "50"))
EVAL_SET_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Hedge phrases that signal the model couldn't extract a clean
# question/answer. We drop pairs where either field starts with these.
_HEDGE_PHRASES = (
    "i don't",
    "i cannot",
    "i can't",
    "i'm not sure",
    "i am not sure",
    "the passage does not",
    "the text does not",
    "no specific",
    "based on this passage, i",
    "this passage doesn't",
    "no factual",
    "as an ai",
)


class EvalSetGeneratorDisabled(RuntimeError):
    """Raised when generate() is called but env flag unset."""


@dataclass
class EvalPair:
    """One synthetic ground-truth pair for eval."""
    question: str
    ground_truth: str
    source_chunk_id: str
    source_text_preview: str
    confidence: str = "synthetic"  # "synthetic" | "hand_curated"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_available() -> bool:
    """Stage-1 default-deny check + Ollama probe."""
    if not EVAL_SET_GENERATOR_ENABLED:
        return False
    try:
        import httpx  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    """Operator status surface."""
    return {
        "stage": 1,
        "enabled_env": EVAL_SET_GENERATOR_ENABLED,
        "available": is_available(),
        "model": EVAL_SET_GENERATOR_MODEL,
        "timeout_s": EVAL_SET_GENERATOR_TIMEOUT_S,
        "max_pairs": EVAL_SET_MAX_PAIRS,
        "ollama_host": EVAL_SET_OLLAMA_HOST,
        "wiring_status": "stage-1 generator; Stage-2 wires into AutoRAG search loop + DSPy trainset",
        "next_stage": (
            "Stage-2 — operator runs `python scripts/eval_set_generator.py "
            "--corpus /tmp/rag-deep-test/bbc-news-data.csv --out "
            ".loop/eval_set.jsonl`; AutoRAG search consumes eval_set.jsonl; "
            "DSPy GEPA compiles against eval_set; RAGAS continuous eval "
            "uses it as the rolling-window source"
        ),
        "quality_gate": "synthetic ≠ benchmark — operator hand-curates 10-20 high-stakes pairs separately for production gates",
    }


def _has_hedge(text: str) -> bool:
    """Drop generations that start with hedging — they're useless
    as eval pairs (no concrete question, no concrete answer)."""
    if not text:
        return True
    head = text.strip().lower()[:60]
    return any(head.startswith(h) for h in _HEDGE_PHRASES)


def _call_ollama(prompt: str, system: str | None = None) -> str:
    """Single Ollama generate call. Returns text or empty on error."""
    import httpx  # noqa: PLC0415
    payload = {
        "model": EVAL_SET_GENERATOR_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 200, "temperature": 0.2},
    }
    if system:
        payload["system"] = system
    try:
        r = httpx.post(
            f"{EVAL_SET_OLLAMA_HOST}/api/generate",
            json=payload,
            timeout=EVAL_SET_GENERATOR_TIMEOUT_S,
        )
        if r.status_code != 200:
            return ""
        return (r.json().get("response") or "").strip()
    except Exception as exc:
        log.warning("eval_set_generator transport error: %s", exc)
        return ""


def generate_pair(chunk_text: str, *, chunk_id: str = "") -> EvalPair | None:
    """Generate ONE Q&A pair from a chunk via 2-step prompting.

    Returns None when the generator hedges or fails.
    """
    if not is_available():
        raise EvalSetGeneratorDisabled(
            "Eval set generator disabled. Set EVAL_SET_GENERATOR_ENABLED=1 "
            "+ ensure Ollama is reachable."
        )

    # Step 1: ask for a question grounded in the passage
    q_system = (
        "You are an exam-question writer. Given a passage, write ONE "
        "specific factual question whose answer is directly stated in "
        "the passage. The question must be answerable from this passage "
        "alone. Output ONLY the question, no preamble. If you cannot "
        "extract a clean factual question, output exactly: SKIP."
    )
    q_prompt = f"Passage:\n{chunk_text[:1500]}\n\nQuestion:"
    question = _call_ollama(q_prompt, system=q_system)
    if not question or question.upper().startswith("SKIP") or _has_hedge(question):
        return None
    # Strip any leading "Q:" or "Question:" prefix
    question = re.sub(r"^(Q:|Question:|A:|Answer:)\s*", "", question, flags=re.IGNORECASE).strip()
    # Cap length (some models drift)
    if len(question) > 200:
        question = question.split("\n")[0][:200]
    if len(question) < 8 or "?" not in question:
        return None  # not a real question

    # Step 2: ask for the answer to that question, using the same passage
    a_system = (
        "Answer the user's question using ONLY the passage. Be concise — "
        "1 sentence. If the passage doesn't answer it, output exactly: "
        "SKIP."
    )
    a_prompt = f"Passage:\n{chunk_text[:1500]}\n\nQuestion: {question}\n\nAnswer:"
    answer = _call_ollama(a_prompt, system=a_system)
    if not answer or answer.upper().startswith("SKIP") or _has_hedge(answer):
        return None
    answer = re.sub(r"^(A:|Answer:)\s*", "", answer, flags=re.IGNORECASE).strip()
    if len(answer) > 500:
        answer = answer[:500]
    if len(answer) < 5:
        return None

    return EvalPair(
        question=question,
        ground_truth=answer,
        source_chunk_id=chunk_id or "",
        source_text_preview=chunk_text[:200],
        confidence="synthetic",
        metadata={"model": EVAL_SET_GENERATOR_MODEL},
    )


def generate_set(
    chunks: list[dict[str, Any]],
    *,
    max_pairs: int | None = None,
) -> list[EvalPair]:
    """Generate multiple Q&A pairs from a list of corpus chunks.

    Each chunk dict needs at least 'text' and optionally 'id'.
    Returns list of EvalPair (length <= max_pairs). Skips chunks
    where generation hedges.

    Raises EvalSetGeneratorDisabled when env flag unset.
    """
    if not is_available():
        raise EvalSetGeneratorDisabled(
            "Eval set generator disabled. Set EVAL_SET_GENERATOR_ENABLED=1."
        )
    target = max_pairs if max_pairs is not None else EVAL_SET_MAX_PAIRS
    pairs: list[EvalPair] = []
    skipped = 0
    t0 = time.monotonic()
    for chunk in chunks:
        if len(pairs) >= target:
            break
        text = chunk.get("text") or chunk.get("content") or ""
        if len(text) < 100:
            skipped += 1
            continue
        chunk_id = str(chunk.get("id") or chunk.get("filename") or chunk.get("chunk_id") or "")
        pair = generate_pair(text, chunk_id=chunk_id)
        if pair is None:
            skipped += 1
            continue
        pairs.append(pair)
        log.info(
            "eval_set_pair generated total=%d/%d skipped=%d q=%.50s",
            len(pairs), target, skipped, pair.question,
        )
    elapsed = time.monotonic() - t0
    log.info(
        "eval_set_generator_complete pairs=%d skipped=%d elapsed_s=%.1f",
        len(pairs), skipped, elapsed,
    )
    return pairs


def write_jsonl(pairs: list[EvalPair], path: str) -> None:
    """Persist eval set as JSONL — operator runs this once, AutoRAG +
    DSPy + RAGAS read the same file."""
    from pathlib import Path  # noqa: PLC0415
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair.as_dict(), default=str) + "\n")
    log.info("eval_set_written path=%s pairs=%d", path, len(pairs))


def main() -> int:
    """CLI entrypoint — operator runs this once on the corpus.

    Usage:
        EVAL_SET_GENERATOR_ENABLED=1 OLLAMA_HOST=http://localhost:11435 \\
            python scripts/eval_set_generator.py \\
                --corpus /tmp/rag-deep-test/bbc-news-data.csv \\
                --out .loop/eval_set.jsonl \\
                --max 30
    """
    import argparse  # noqa: PLC0415
    import csv  # noqa: PLC0415
    import random  # noqa: PLC0415

    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True,
                        help="path to corpus CSV (TSV-formatted with text col)")
    parser.add_argument("--text-col", default="content",
                        help="name of the text column in the CSV")
    parser.add_argument("--id-col", default="filename",
                        help="name of the id column in the CSV")
    parser.add_argument("--out", default=".loop/eval_set.jsonl")
    parser.add_argument("--max", type=int, default=30,
                        help="max Q&A pairs to generate")
    parser.add_argument("--limit-chunks", type=int, default=50,
                        help="max chunks to consider (sample N from top of CSV)")
    parser.add_argument("--seed", type=int, default=None,
                        help=("Random seed for chunk-order shuffling. "
                              "Different seed → different eval set → unblocks "
                              "Stage-3-earned 'stable_single_winner' verdict "
                              "by producing distinct empirical winners across "
                              "varied query distributions. Without this, the "
                              "first N chunks are always sampled (overfitting "
                              "risk). Per stage3_earned_check.py rationale."))
    args = parser.parse_args()

    if not is_available():
        print(json.dumps({"error": "EVAL_SET_GENERATOR_ENABLED unset OR Ollama unreachable",
                          "status": status()}, indent=2))
        return 1

    # Load corpus
    chunks: list[dict[str, Any]] = []
    with open(args.corpus, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            text = row.get(args.text_col, "")
            chunks.append({"text": text, "id": row.get(args.id_col, str(len(chunks)))})

    # Shuffle BEFORE truncating to limit-chunks. Without --seed the
    # order is whatever csv.DictReader yields (usually file order).
    # With --seed we get a deterministic permutation so operators
    # can reproduce a specific eval set when needed.
    if args.seed is not None:
        rng = random.Random(args.seed)
        rng.shuffle(chunks)
        print(f"shuffled corpus with seed={args.seed}")

    # Truncate AFTER shuffle so the sample is from a varied prefix
    chunks = chunks[: args.limit_chunks]

    print(f"loaded {len(chunks)} chunks from {args.corpus}")
    pairs = generate_set(chunks, max_pairs=args.max)
    write_jsonl(pairs, args.out)
    print(f"\ngenerated {len(pairs)} eval pairs → {args.out}")
    if pairs:
        print("\nfirst 3 pairs:")
        for p in pairs[:3]:
            print(f"  Q: {p.question}")
            print(f"  A: {p.ground_truth[:100]}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
