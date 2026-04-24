"""The EmbeddingProvider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """
    Stateless interface for generating vector embeddings.

    Contracts every implementation MUST honor:

    * :meth:`embed_many` accepts a list, returns a list of the same length.
    * Vectors have the same dimensionality as :attr:`dimension`.
    * Order is preserved: ``embed_many(["a","b"])[0]`` is ``"a"``'s vector.
    * No tenant awareness at this layer — chunks are embedded the same way
      regardless of tenant. (Tenant filtering happens at the vector DB.)
    """

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    async def embed_many(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]:
        """Single-text convenience wrapper. Most callers want embed_many."""
        result = await self.embed_many([text])
        return result[0]
