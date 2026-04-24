"""
Embedding providers (Design Area 39 — Embedding Lifecycle, Area 65 —
Design-for-Change).

Every embedder implements :class:`EmbeddingProvider`. Switching from Ollama
to OpenAI (or Cohere, or a local ONNX model) is a single-line config change
— no other code moves.
"""
from .base import EmbeddingProvider
from .ollama_embedder import OllamaEmbedder

__all__ = ["EmbeddingProvider", "OllamaEmbedder"]
