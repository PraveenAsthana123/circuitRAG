"""
Embedding cache — content-hash → vector with model-version namespacing
(§16.2 of the RAG playbook).

Why it's a separate module from the generic ``cache.py``:
- The cache key MUST include the embedding model + version. A 768-dim
  vector from ``nomic-embed-v1`` is incompatible with a vector
  from ``nomic-embed-v2`` even if the text is identical. Without
  versioning, model upgrades silently corrupt retrieval.
- Vectors are bytes, not JSON. The generic Cache.get_json/set_json
  flow round-trips through json.dumps which doesn't preserve
  numeric precision and inflates payload by ~3×.
- Cost-tracking is most useful at this layer (per-tenant token
  spend) — putting the counter here keeps it close to the cache
  hits/misses.

DSA: hash map (content + model version → vector bytes), with the
model version as a key prefix so a model swap is a one-liner
(`namespace = (model, new_version)` and the old vectors remain
untouched until they age out via TTL).

Vectors are stored as raw bytes (struct.pack of float32). float32
is the standard for embedding APIs; if the caller works in float64
they're paying 2× memory for sub-1% recall benefit. Use float32.
"""

from __future__ import annotations

import hashlib
import logging
import struct
from collections.abc import Sequence
from dataclasses import dataclass

import redis.asyncio as aioredis

__all__ = ["EmbeddingCache", "EmbeddingCacheStats", "vector_to_bytes", "bytes_to_vector"]

log = logging.getLogger(__name__)


@dataclass
class EmbeddingCacheStats:
    """Mutable stats. Reset by callers between report intervals."""

    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


def vector_to_bytes(vector: Sequence[float]) -> bytes:
    """Pack a sequence of floats as float32 bytes.

    Float32 is the standard precision for embedding APIs and saves
    50% memory vs float64 with no measurable recall impact.
    """
    return struct.pack(f"{len(vector)}f", *vector)


def bytes_to_vector(data: bytes) -> list[float]:
    """Unpack float32 bytes into a list of Python floats.

    The length is inferred from the byte count (4 bytes per float32).
    """
    if len(data) % 4 != 0:
        raise ValueError(f"corrupt vector bytes: len={len(data)} not divisible by 4")
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


class EmbeddingCache:
    """Tenant-aware embedding cache, model-version namespaced.

    Usage::

        cache = EmbeddingCache(redis, model="nomic-embed-v1.5")
        vec = await cache.get(tenant_id="acme", text="refund policy")
        if vec is None:
            vec = await embedder.embed("refund policy")
            await cache.put(tenant_id="acme", text="refund policy", vector=vec)

    On model swap, instantiate a NEW cache with the new model id —
    old keys won't collide and will age out via TTL.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        model: str,
        ttl_seconds: int = 30 * 24 * 3600,  # 30 days — embeddings are stable per model version
    ) -> None:
        if not model:
            raise ValueError("model is required (must include version, e.g. 'nomic-embed-v1.5')")
        self._redis = redis
        self._model = model
        self._ttl = ttl_seconds
        self.stats = EmbeddingCacheStats()

    @staticmethod
    def _content_hash(text: str) -> str:
        """Stable, short hash of the input text. SHA-256 truncated
        to 16 hex chars — collisions are vanishingly rare at any
        practical corpus size."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _key(self, tenant_id: str, text: str) -> str:
        # Tenant prefix + model + content hash. Cross-tenant keys
        # impossible by construction (§38 isolation contract).
        if not tenant_id:
            raise ValueError("tenant_id is required")
        return f"tenant:{tenant_id}:emb:{self._model}:{self._content_hash(text)}"

    async def get(self, *, tenant_id: str, text: str) -> list[float] | None:
        """Return cached vector or None on miss. Fail-open on Redis
        errors (treat as miss).

        Updates self.stats.{hits, misses} so callers can dashboard
        the hit rate without separate instrumentation.
        """
        try:
            raw = await self._redis.get(self._key(tenant_id, text))
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            # Fail-open: a dead cache must NOT 5xx the user — fall
            # through to a fresh embedding call. §38 contract.
            log.warning("embedding_cache_get_fail_open err=%s", exc)
            self.stats.misses += 1
            return None

        if raw is None:
            self.stats.misses += 1
            return None
        try:
            vec = bytes_to_vector(raw)
        except ValueError as exc:
            # Corrupt cache row — treat as miss + log; don't crash.
            log.warning("embedding_cache_corrupt key=%s err=%s", self._key(tenant_id, text), exc)
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return vec

    async def put(self, *, tenant_id: str, text: str, vector: Sequence[float]) -> None:
        """Store vector. Fail-open on Redis errors (silently drop
        the cache write — better than 5xxing the user)."""
        if not vector:
            return  # never cache empty vectors — they'd mask real misses
        try:
            await self._redis.setex(
                self._key(tenant_id, text),
                self._ttl,
                vector_to_bytes(vector),
            )
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            log.warning("embedding_cache_put_fail_open err=%s", exc)

    async def invalidate_tenant(self, tenant_id: str) -> int:
        """Remove all cached embeddings for one tenant (e.g. on
        tenant suspension). Uses SCAN — KEYS would block at scale.
        Returns count removed."""
        if not tenant_id:
            raise ValueError("tenant_id is required")
        pattern = f"tenant:{tenant_id}:emb:{self._model}:*"
        count = 0
        async for key in self._redis.scan_iter(match=pattern, count=500):
            await self._redis.delete(key)
            count += 1
        log.info("embedding_cache_invalidated tenant=%s removed=%d", tenant_id, count)
        return count

    @property
    def model(self) -> str:
        """Current model namespace — exposed for telemetry."""
        return self._model
