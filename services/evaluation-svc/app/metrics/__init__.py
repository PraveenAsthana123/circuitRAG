"""
Evaluation metrics (Design Area 26, 59, 60, 61).

Each metric is a class with a single ``compute`` method so we can compose
them, test them in isolation, and swap implementations per-tenant.

Metrics included
----------------

* :class:`PrecisionAtK` — retrieval: fraction of top-K chunks that are
  relevant to the ground-truth answer.
* :class:`Recall` — retrieval: fraction of ground-truth sources captured.
* :class:`MRR` — Mean Reciprocal Rank: how high is the first relevant hit?
* :class:`NDCG` — Normalized Discounted Cumulative Gain: graded relevance
  with rank discount.
* :class:`Faithfulness` — generation: is the answer supported by the
  retrieved context? Computed by token-overlap (dev) or LLM judge (prod).
* :class:`AnswerRelevance` — generation: does the answer address the
  question? Computed by cosine similarity of embeddings.
"""
from .retrieval import MRR, NDCG, PrecisionAtK, Recall
from .generation import AnswerRelevance, Faithfulness

__all__ = ["PrecisionAtK", "Recall", "MRR", "NDCG", "Faithfulness", "AnswerRelevance"]
