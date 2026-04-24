"""
Repositories (Design Areas 46 — DB Strategy, 47 — Vector DB, 48 — Graph).

One repo per data store. ALL SQL/Cypher/Qdrant calls live here — routers
and services never write queries directly.

Each repo:

* Takes its client in ``__init__`` (constructor injection).
* Uses tenant-scoped access (RLS for Postgres, payload filters for Qdrant,
  property filters for Neo4j).
* Surfaces domain errors (``NotFoundError``, ``DataError``) — never raises
  raw driver exceptions to callers.
"""
from .chunk_repo import ChunkRepo
from .document_repo import DocumentRepo
from .neo4j_repo import Neo4jRepo
from .qdrant_repo import QdrantRepo
from .saga_repo import SagaRepo

__all__ = [
    "DocumentRepo",
    "ChunkRepo",
    "SagaRepo",
    "QdrantRepo",
    "Neo4jRepo",
]
