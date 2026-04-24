"""Generation metrics — faithfulness and answer relevance."""
from __future__ import annotations

from dataclasses import dataclass


def _tokenize(s: str) -> set[str]:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in s).split() if len(t) > 2}


@dataclass
class Faithfulness:
    """
    Token-overlap proxy: fraction of answer tokens that appear in the
    retrieved context. Not a true faithfulness measure (LLMs can
    rephrase), but a cheap, deterministic baseline that flags obvious
    hallucinations.

    Production: replace with an LLM judge that classifies each answer
    claim as "supported / unsupported / contradicted" by the context.
    """

    def compute(self, *, answer: str, context: str) -> float:
        ans = _tokenize(answer)
        if not ans:
            return 0.0
        ctx = _tokenize(context)
        return len(ans & ctx) / len(ans)


@dataclass
class AnswerRelevance:
    """
    Cheap proxy: jaccard of tokens between question and answer. Again, a
    baseline; production uses embedding cosine similarity between the
    question and answer, or an LLM judge.
    """

    def compute(self, *, question: str, answer: str) -> float:
        q, a = _tokenize(question), _tokenize(answer)
        if not q or not a:
            return 0.0
        return len(q & a) / len(q | a)
