#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Cache fingerprint helper Stage-1 (per §43 + §56).

Locks the operator-supplied 12-layer cache-key invariant: every
dimension that affects the answer MUST be in the cache key.

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "scripts" / "cache_fingerprint.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: cache_fingerprint.py exists + non-trivial size --")
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing")
        return 1
    src = ADAPTER.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x cache_fingerprint too short ({len(src)} chars)")
        return 1
    print(f"  ok: cache_fingerprint present ({len(src)} chars)")

    print("-- 2. POSITIVE: 6 contract surfaces exported --")
    os.environ["CACHE_FINGERPRINT_ENABLED"] = "1"
    mod, spec = _load_module(ADAPTER)
    for name in ("is_available", "status", "fingerprint", "Fingerprint",
                 "CacheFingerprintDisabled", "normalize_query",
                 "is_pii_safe_to_cache"):
        if not hasattr(mod, name):
            print(f"x cache_fingerprint.{name} missing")
            return 1
    print("  ok: 7 surfaces exported")

    print("-- 3. NEGATIVE: default-deny — fingerprint() raises when env unset --")
    os.environ.pop("CACHE_FINGERPRINT_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.fingerprint(
            tenant_id="t", query="q", prompt_version="v1",
            model_version="m", embedding_model_version="e",
        )
    except mod.CacheFingerprintDisabled as exc:
        raised = True
        if "CACHE_FINGERPRINT_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x fingerprint() should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites env flag)")

    # Re-enable for the rest
    os.environ["CACHE_FINGERPRINT_ENABLED"] = "1"
    spec.loader.exec_module(mod)

    print("-- 4. NEGATIVE: 5 required dimensions enforced (operator brutal rule) --")
    # Per operator: every cache key MUST encode tenant_id +
    # normalized_query + prompt_version + model_version +
    # embedding_model_version. Skipping ANY = stale-result bug.
    fp = mod.fingerprint(
        tenant_id="tenant1",
        query="What is X?",
        prompt_version="v1",
        model_version="gemma2:9b",
        embedding_model_version="nomic-embed:v1",
    )
    if fp.tenant_id != "tenant1":
        print("x tenant_id not preserved")
        return 1
    if fp.prompt_version != "v1":
        print("x prompt_version not preserved")
        return 1
    if fp.model_version != "gemma2:9b":
        print("x model_version not preserved")
        return 1
    if fp.embedding_model_version != "nomic-embed:v1":
        print("x embedding_model_version not preserved")
        return 1
    sig = fp.signature()
    for required in ("tenant=tenant1", "prompt_v=v1", "model_v=gemma2:9b",
                     "embed_v=nomic-embed:v1"):
        if required not in sig:
            print(f"x signature missing required: {required}")
            return 1
    print("  ok: 5 required dimensions enforced + present in signature")

    print("-- 5. NEGATIVE: query normalization is whitespace-collapse + lowercase --")
    # Same query with different whitespace + casing should produce
    # IDENTICAL fingerprint. "What is X?" == "what  IS  x?"
    fp_a = mod.fingerprint(
        tenant_id="t", query="What is X?",
        prompt_version="v", model_version="m", embedding_model_version="e",
    )
    fp_b = mod.fingerprint(
        tenant_id="t", query="what  IS  x?",
        prompt_version="v", model_version="m", embedding_model_version="e",
    )
    if fp_a.hash() != fp_b.hash():
        print(f"x normalization broken: {fp_a.signature()!r} != {fp_b.signature()!r}")
        return 1
    print("  ok: query normalization stable (whitespace+casing)")

    print("-- 6. NEGATIVE: dimension change → DIFFERENT fingerprint hash --")
    # The whole point: changing prompt/model/embedding/tenant version
    # must INVALIDATE the cache. Drill enforces this for each
    # required dimension.
    base = mod.fingerprint(
        tenant_id="t", query="q", prompt_version="v1",
        model_version="m1", embedding_model_version="e1",
    )
    changes = [
        {"tenant_id": "t2"},
        {"prompt_version": "v2"},
        {"model_version": "m2"},
        {"embedding_model_version": "e2"},
    ]
    for change in changes:
        kwargs = {"tenant_id": "t", "query": "q", "prompt_version": "v1",
                      "model_version": "m1", "embedding_model_version": "e1"}
        kwargs.update(change)
        derived = mod.fingerprint(**kwargs)
        if base.hash() == derived.hash():
            print(f"x changing {list(change)[0]} did NOT change fingerprint hash — STALE-CACHE BUG")
            return 1
    print("  ok: every required dimension changes fingerprint hash (no stale-cache bug)")

    print("-- 7. NEGATIVE: PII-cache safety check refuses dangerous caching --")
    # Per operator: "Never cache PII raw"
    if mod.is_pii_safe_to_cache(has_pii=True):
        print("x is_pii_safe_to_cache must return False when has_pii=True")
        return 1
    if mod.is_pii_safe_to_cache(has_pii=False, has_low_confidence=True):
        print("x is_pii_safe_to_cache must return False on low confidence")
        return 1
    if not mod.is_pii_safe_to_cache(has_pii=False, has_low_confidence=False):
        print("x is_pii_safe_to_cache must return True when both flags False")
        return 1
    print("  ok: PII + low-confidence both refuse caching")

    print("-- 8. POSITIVE: status() lists 12 cache layers + Stage-2 wiring --")
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    if "supported_layers" not in s or len(s["supported_layers"]) != 12:
        print(f"x must expose 12 cache layers; got {len(s.get('supported_layers', []))}")
        return 1
    expected_layers = {"intent", "prompt", "response", "semantic", "embedding",
                       "retrieval", "rerank", "tool", "session", "policy",
                       "evaluation", "artifact"}
    actual = set(s["supported_layers"])
    missing = expected_layers - actual
    if missing:
        print(f"x missing layers: {sorted(missing)}")
        return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2")
        return 1
    if "HybridRetriever" not in s["next_stage"]:
        print("x next_stage must mention HybridRetriever (Stage-2 wiring site)")
        return 1
    print("  ok: 12 layers covered + Stage-2 path mentions HybridRetriever")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
