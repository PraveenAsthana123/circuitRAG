"""Retrieval-service configuration."""
from __future__ import annotations

from documind_core.config import BaseServiceSettings


class RetrievalSettings(BaseServiceSettings):
    service_name: str = "retrieval-svc"

    # How many candidates to pull from each backend before fusion/rerank
    vector_top_k: int = 20
    graph_top_k: int = 10

    # How many to return after fusion + reranking
    final_top_k: int = 10

    # Cache TTL for query results
    query_cache_ttl: int = 300
