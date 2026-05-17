import os
from typing import Dict, Any, List
from qdrant_client import QdrantClient


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
        filters: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:

        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k
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
