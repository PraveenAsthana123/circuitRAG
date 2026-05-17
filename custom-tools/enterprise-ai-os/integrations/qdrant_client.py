# ✅ P0 FIXED (Iter 4, 2026-05-17): filters now passed (tenant
#     isolation).
# ✅ P1 FIXED (Iter 30, 2026-05-17): retry + per-request timeout
#     wrapper, mirroring the OpenAIClient pattern from Iter 24.
#     Pre-fix: a Qdrant 5xx or network blip bubbled straight to the
#     caller; a hung request could block the worker forever.

import os
from typing import Dict, Any, List
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import (
    UnexpectedResponse,
    ResponseHandlingException,
)
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

from integrations.retry_policy import RetryPolicy


_DEFAULT_TIMEOUT_SECONDS = 30.0


class QdrantVectorClient:
    def __init__(
        self,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        retry_policy: RetryPolicy | None = None,
    ):
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY"),
            timeout=timeout_seconds,
        )
        self.collection = os.getenv("QDRANT_COLLECTION", "enterprise_docs")
        self.retry_policy = retry_policy or RetryPolicy(
            max_retries=3,
            base_delay_ms=200,
            timeout_seconds=timeout_seconds,
            retry_on=(
                ConnectionError,
                TimeoutError,
                ResponseHandlingException,
                UnexpectedResponse,
            ),
        )

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
        query_filter: Filter | None = None,
    ) -> List[Dict[str, Any]]:

        effective_filter: Filter | None
        if query_filter is not None:
            effective_filter = query_filter
        elif filters:
            effective_filter = self._dict_to_filter(filters)
        else:
            effective_filter = None

        def _call():
            results = self.client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                limit=top_k,
                query_filter=effective_filter,
            )
            return [
                {
                    "chunk_id": str(item.id),
                    "score": item.score,
                    "payload": item.payload,
                    "text": item.payload.get("text"),
                    "source": item.payload.get("source"),
                }
                for item in results
            ]

        return self.retry_policy.execute(_call)

    @staticmethod
    def _dict_to_filter(filters: Dict[str, Any]) -> Filter:
        """Translate `{key: value}` into a Qdrant Filter with AND semantics."""
        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filters.items()
            ]
        )
