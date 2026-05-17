# ✅ P0 FIXED (2026-05-17): `filters` argument is now actually passed
#     to Qdrant. The pre-fix version accepted `filters` and silently
#     dropped it, so callers that expected tenant filtering received
#     cross-tenant results.
#
#     The `filters` dict is converted into a Qdrant `Filter` object
#     with one MatchValue condition per key. For more complex filter
#     trees (must/should/must_not, ranges, geo), callers can pass a
#     pre-built `Filter` directly via the new `query_filter` argument.
#
#     Negative drill: tests/test_qdrant_filter_passthrough.py

import os
from typing import Dict, Any, List, Union
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue


class QdrantVectorClient:
    def __init__(self):
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY")
        )
        self.collection = os.getenv("QDRANT_COLLECTION", "enterprise_docs")

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
        query_filter: Filter | None = None,
    ) -> List[Dict[str, Any]]:

        # Build the Filter argument: prefer an explicit pre-built one,
        # otherwise translate the simple `filters` dict.
        effective_filter: Filter | None
        if query_filter is not None:
            effective_filter = query_filter
        elif filters:
            effective_filter = self._dict_to_filter(filters)
        else:
            effective_filter = None

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
                "source": item.payload.get("source")
            }
            for item in results
        ]

    @staticmethod
    def _dict_to_filter(filters: Dict[str, Any]) -> Filter:
        """Translate `{key: value}` into a Qdrant Filter with AND semantics."""
        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filters.items()
            ]
        )
