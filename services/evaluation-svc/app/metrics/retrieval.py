"""Retrieval metrics — precision@k, recall, MRR, NDCG."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PrecisionAtK:
    k: int = 5

    def compute(self, *, retrieved: list[str], relevant: set[str]) -> float:
        """Fraction of the top-K retrieved IDs that are in the relevant set."""
        if self.k <= 0 or not retrieved:
            return 0.0
        topk = retrieved[: self.k]
        hits = sum(1 for d in topk if d in relevant)
        return hits / len(topk)


@dataclass
class Recall:
    def compute(self, *, retrieved: list[str], relevant: set[str]) -> float:
        """Fraction of relevant IDs found in retrieval (at any rank)."""
        if not relevant:
            return 1.0  # vacuous — no ground truth means perfect recall
        hits = sum(1 for d in relevant if d in retrieved)
        return hits / len(relevant)


@dataclass
class MRR:
    """Mean Reciprocal Rank — 1/rank of the first relevant hit, else 0."""

    def compute(self, *, retrieved: list[str], relevant: set[str]) -> float:
        for i, d in enumerate(retrieved, start=1):
            if d in relevant:
                return 1.0 / i
        return 0.0


@dataclass
class NDCG:
    """Normalized Discounted Cumulative Gain @ K (binary relevance)."""

    k: int = 10

    def compute(self, *, retrieved: list[str], relevant: set[str]) -> float:
        dcg = 0.0
        for i, d in enumerate(retrieved[: self.k], start=1):
            if d in relevant:
                # gain 1, discount log2(i+1); i starts at 1 so log2(2) at rank 1
                dcg += 1.0 / math.log2(i + 1)
        # Ideal DCG: all relevant (up to k) at the top
        ideal_hits = min(len(relevant), self.k)
        idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
        return dcg / idcg if idcg > 0 else 0.0
