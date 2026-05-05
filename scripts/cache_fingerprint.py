"""Cache fingerprint helper — Stage-1 (per CLAUDE.md §56).

Realizes the operator-supplied 12-layer cache architecture:

   1. Intent cache         user query → route
   2. Prompt cache         prompt → LLM output
   3. Response cache       final answer
   4. Semantic cache       similar query → answer
   5. Embedding cache      text chunk → vector
   6. Retrieval cache      query → top-k chunks
   7. Rerank cache         chunks → ranked chunks
   8. Tool result cache    API/tool output
   9. Session cache        conversation state
  10. Policy cache         permission decision
  11. Evaluation cache     answer → score
  12. Model artifact cache model/tokenizer files

THE CRITICAL INSIGHT (operator-supplied brutal rule):
    Every cache key MUST encode every dimension that affects the
    answer. Skip ANY dimension and you serve stale results when
    that dimension changes — the worst kind of bug because failures
    look like cache hits.

CACHE-KEY DIMENSIONS (operator-spec):
    cache_key = hash(
        tenant_id +
        normalized_query +
        prompt_version +
        model_version +
        embedding_model_version +
        index_version +
        policy_version +
        retrieval_context_hash
    )

This module ships:
  - Fingerprint class with 8+ dimensions
  - fingerprint(...) → stable hex hash
  - signature(...) → human-readable key for debugging
  - normalize_query() — strips whitespace + lowercases
  - is_pii_safe_to_cache(text, entities) — refuses to cache PII per
    operator's "Never cache PII raw" rule

Stage-1 ships the helper; Stage-2 wires it into:
  - HybridRetriever cache (currently uses tenant + query only)
  - inference-svc response cache (not yet wired)
  - LiteLLM semantic cache (Redis backend)

OPERATOR OPT-IN:
    CACHE_FINGERPRINT_ENABLED=1

COMPOSES WITH (per §49):
    services/retrieval-svc/app/services/hybrid_retriever.py — Stage-2
        wires fingerprint into _cache_key()
    docs/architecture/six-plane-audit-2026-05-04.md — caching gap
    §38 — decision audit (cache hit/miss logged with key fingerprint)
    §43 — drill discipline
    §47 — architecture (cache invalidation correctness)
    §52 — brutal tool review (40-row when wired)
    §56 — Stage-1 6-gate
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

CACHE_FINGERPRINT_ENABLED = os.getenv("CACHE_FINGERPRINT_ENABLED", "").strip() == "1"


class CacheFingerprintDisabled(RuntimeError):
    """Raised when fingerprint() is called but env flag unset."""


@dataclass
class Fingerprint:
    """Cache-key fingerprint — every dimension that affects the answer.

    Per operator's brutal rule: skipping a dimension serves stale
    results when that dimension changes. The hash() method produces a
    stable hex digest; signature() is the human-readable form for
    debugging "why did cache miss?" / "why did cache hit?".

    REQUIRED dimensions (always):
      - tenant_id        — multi-tenant isolation
      - normalized_query — what the user asked (whitespace-normalized)
      - prompt_version   — change → behavior change
      - model_version    — change → output drift
      - embedding_model_version — change → vectors invalid

    OPTIONAL dimensions (encode when relevant):
      - index_version    — corpus updated
      - policy_version   — RBAC/policy changed
      - retrieval_context_hash — top-K chunks changed
      - cache_layer      — which of 12 layers (avoids cross-layer
                           collision)
    """
    tenant_id: str
    normalized_query: str
    prompt_version: str
    model_version: str
    embedding_model_version: str
    index_version: str = ""
    policy_version: str = ""
    retrieval_context_hash: str = ""
    cache_layer: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def hash(self) -> str:
        """Stable hex digest. SHA-256 of the canonical signature."""
        sig = self.signature()
        return hashlib.sha256(sig.encode("utf-8")).hexdigest()

    def signature(self) -> str:
        """Human-readable key — useful for debugging cache hits/misses."""
        parts = [
            f"tenant={self.tenant_id}",
            f"q={self.normalized_query}",
            f"prompt_v={self.prompt_version}",
            f"model_v={self.model_version}",
            f"embed_v={self.embedding_model_version}",
        ]
        if self.index_version:
            parts.append(f"index_v={self.index_version}")
        if self.policy_version:
            parts.append(f"policy_v={self.policy_version}")
        if self.retrieval_context_hash:
            parts.append(f"ctx={self.retrieval_context_hash}")
        if self.cache_layer:
            parts.append(f"layer={self.cache_layer}")
        for k in sorted(self.extra.keys()):
            parts.append(f"{k}={self.extra[k]}")
        return "|".join(parts)


# Whitespace-only collapse + lowercase. Keeps semantic content
# preserved (don't strip stopwords here — that's a retrieval concern,
# not a cache concern).
_WS_RE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Canonical-form a query for cache-key stability.

    Same semantics as Redis-cache key normalization in production
    LLM systems: lowercase + collapse whitespace + strip. Anything
    fancier (stemming, semantic) belongs to the semantic-cache layer
    (#4 in the 12-cache list), not this fingerprint helper.
    """
    return _WS_RE.sub(" ", query.strip().lower())


def is_available() -> bool:
    """Stage-1 default-deny check."""
    return CACHE_FINGERPRINT_ENABLED


def is_pii_safe_to_cache(*, has_pii: bool, has_low_confidence: bool = False) -> bool:
    """Per operator's brutal rules:
      - Never cache PII raw → return False if has_pii=True
      - Cache only high-confidence answers → return False if low_conf
    """
    return not (has_pii or has_low_confidence)


def fingerprint(
    *,
    tenant_id: str,
    query: str,
    prompt_version: str,
    model_version: str,
    embedding_model_version: str,
    index_version: str = "",
    policy_version: str = "",
    retrieval_context: list[str] | None = None,
    cache_layer: str = "",
    **extra: Any,
) -> Fingerprint:
    """Build a Fingerprint with all dimensions.

    Args:
        tenant_id: multi-tenant isolation (REQUIRED)
        query: raw user query (will be normalized)
        prompt_version: e.g. "rag_answer_v1"
        model_version: e.g. "gemma2:9b" or "ollama:gemma2:9b@<digest>"
        embedding_model_version: e.g. "nomic-embed-text:latest@<digest>"
        index_version: optional Qdrant collection version / corpus hash
        policy_version: optional PolisAI policy hash
        retrieval_context: optional list of chunk_ids (top-K) — hashed
                          into a single short digest to avoid bloating
                          the cache key
        cache_layer: one of intent / prompt / response / semantic /
                    embedding / retrieval / rerank / tool / session /
                    policy / evaluation / artifact

    Raises CacheFingerprintDisabled when env flag unset.
    """
    if not is_available():
        raise CacheFingerprintDisabled(
            "Cache fingerprint disabled. Set CACHE_FINGERPRINT_ENABLED=1 to use."
        )

    # Hash the retrieval context (chunk-id list) to a stable short
    # digest — prevents cache key bloat when top-K is 50+ chunks
    ctx_hash = ""
    if retrieval_context:
        joined = "|".join(sorted(retrieval_context))
        ctx_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]

    return Fingerprint(
        tenant_id=tenant_id,
        normalized_query=normalize_query(query),
        prompt_version=prompt_version,
        model_version=model_version,
        embedding_model_version=embedding_model_version,
        index_version=index_version,
        policy_version=policy_version,
        retrieval_context_hash=ctx_hash,
        cache_layer=cache_layer,
        extra=extra,
    )


def status() -> dict[str, Any]:
    """Operator status surface."""
    return {
        "stage": 1,
        "enabled_env": CACHE_FINGERPRINT_ENABLED,
        "available": is_available(),
        "supported_layers": [
            "intent", "prompt", "response", "semantic", "embedding",
            "retrieval", "rerank", "tool", "session", "policy",
            "evaluation", "artifact",
        ],
        "required_dimensions": [
            "tenant_id", "normalized_query", "prompt_version",
            "model_version", "embedding_model_version",
        ],
        "optional_dimensions": [
            "index_version", "policy_version",
            "retrieval_context_hash", "cache_layer",
        ],
        "wiring_status": "stage-1 helper; Stage-2 wires into HybridRetriever cache_key + inference-svc response cache + LiteLLM semantic cache",
        "next_stage": (
            "Stage-2 — replace HybridRetriever._cache_key() with "
            "fingerprint(); wire into inference-svc response cache "
            "with prompt_version + model_version dimensions; wire "
            "LiteLLM semantic cache with the same fingerprint shape"
        ),
    }


if __name__ == "__main__":
    import json
    import sys
    print("scripts/cache_fingerprint.py — Stage-1 12-layer cache key helper")
    print(f"Stage-1 opt-in via CACHE_FINGERPRINT_ENABLED=1")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
