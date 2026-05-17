from typing import Dict, Any, List


class SourceAttribution:
    def attribute(
        self,
        answer: str,
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        return {
            "answer": answer,
            "source_count": len(sources),
            "sources": [
                {
                    "chunk_id": source.get("chunk_id"),
                    "source": source.get("source"),
                    "score": source.get("score"),
                    "hybrid_score": source.get("hybrid_score"),
                    "retriever": source.get("retriever")
                }
                for source in sources
            ],
            "attribution_status": "available" if sources else "missing"
        }
