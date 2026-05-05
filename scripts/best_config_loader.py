"""Best-config registry loader — Stage-1 adapter (per CLAUDE.md §56).

Reads .loop/best_config.json (produced by run_autorag_empirical.py)
so callers (inference-svc, retrieval-svc) can seed retrieval defaults
from the empirically-best config without hard-coding.

CONTRACT:
  - load_best_config(path) → BestConfig | None
  - get_default_min_score() → float (with safe fallback)
  - get_default_top_k() → int (with safe fallback)
  - get_default_rerank_enabled() → bool (with safe fallback)
  - is_available() / status()

OPERATOR FLOW:
  1. operator runs scripts/run_autorag_empirical.py to produce best_config.json
  2. inference-svc / retrieval-svc imports this module
  3. on first call, reads best_config.json
  4. caches in-process; re-reads on TTL or operator signal

SAFETY:
  - File missing → returns sane defaults (min_score=0.0, top_k=10, rerank=False)
  - File malformed → log + defaults
  - Defaults match the legacy un-tuned production behavior so callers
    that don't override get the same thing they had before

OPERATOR OPT-IN:
    BEST_CONFIG_LOADER_ENABLED=1
    BEST_CONFIG_PATH=.loop/best_config.json   # default

COMPOSES WITH:
    scripts/run_autorag_empirical.py — produces best_config.json
    scripts/autorag_optimizer.py — ConfigPoint shape
    services/inference-svc/app/services/rag_inference.py — Stage-2 wire site
    services/retrieval-svc/app/schemas/__init__.py — RetrieveRequest defaults
    docs/architecture/six-plane-audit-2026-05-04.md — control plane
    §38 (audit), §43 (drill), §47 (fail-safe defaults), §56 (Stage-1)
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Stage-3 default-flip (2026-05-05): default-on after Stage-3-earned
# verdict landed live with 19 promotions × 2 distinct configs × 1.00
# success ratio (per docs/runbooks/empirical-loop-stage3-promotion.md
# + ADR-024 superseding ADR-023). Operators can opt-OUT explicitly
# by setting BEST_CONFIG_LOADER_ENABLED=0; per §47 fail-safe, file
# missing/malformed still falls back to legacy un-tuned defaults
# (min_score=0.0, top_k=10, rerank=False).
_BEST_CONFIG_LOADER_RAW = os.getenv("BEST_CONFIG_LOADER_ENABLED", "1").strip()
BEST_CONFIG_LOADER_ENABLED = _BEST_CONFIG_LOADER_RAW != "0"
BEST_CONFIG_PATH = os.getenv("BEST_CONFIG_PATH", ".loop/best_config.json")
BEST_CONFIG_TTL_S = float(os.getenv("BEST_CONFIG_TTL_S", "300"))  # 5min cache

# Sane fallbacks — match legacy un-tuned behavior so callers that
# don't load best_config see no behavior change.
_DEFAULTS = {
    "min_score": 0.0,
    "top_k": 10,
    "rerank_enabled": False,
    "rerank_top_k": 10,
    "chunking_strategy": "recursive_paragraph_sentence",
}


class BestConfigLoaderDisabled(RuntimeError):
    """Raised when force-required loader is invoked but env unset."""


@dataclass
class BestConfig:
    """Promoted config from AutoRAG search."""
    min_score: float = 0.0
    top_k: int = 10
    rerank_enabled: bool = False
    rerank_top_k: int = 10
    chunking_strategy: str = "recursive_paragraph_sentence"
    pass_rate: float = 0.0
    promoted_at_ts: float = 0.0
    eval_set_size: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_score": self.min_score,
            "top_k": self.top_k,
            "rerank_enabled": self.rerank_enabled,
            "rerank_top_k": self.rerank_top_k,
            "chunking_strategy": self.chunking_strategy,
            "pass_rate": self.pass_rate,
            "promoted_at_ts": self.promoted_at_ts,
            "eval_set_size": self.eval_set_size,
        }


# Process-cached config + last-load timestamp. TTL-based refresh.
_cached: BestConfig | None = None
_cached_at: float = 0.0


def is_available() -> bool:
    """Stage-1 default-deny check."""
    return BEST_CONFIG_LOADER_ENABLED


def status() -> dict[str, Any]:
    """Operator status surface."""
    p = Path(BEST_CONFIG_PATH)
    return {
        "stage": 1,
        "enabled_env": BEST_CONFIG_LOADER_ENABLED,
        "available": is_available(),
        "config_path": str(p),
        "config_exists": p.exists(),
        "config_size_bytes": p.stat().st_size if p.exists() else 0,
        "ttl_s": BEST_CONFIG_TTL_S,
        "cache_warm": _cached is not None,
        "cache_age_s": (time.time() - _cached_at) if _cached_at else 0,
        "fallback_defaults": dict(_DEFAULTS),
        "wiring_status": "stage-1 loader; Stage-2 wires get_default_*() into rag_inference + HybridRetriever defaults",
        "next_stage": (
            "Stage-2 — rag_inference.ask reads BestConfig defaults when "
            "AskRequest fields are unset; HybridRetriever picks up "
            "min_score + top_k from BestConfig when RetrieveRequest "
            "doesn't override"
        ),
    }


def _read_file(path: str) -> BestConfig | None:
    """Read best_config.json from disk. Returns None on missing/malformed.

    Per §47 fail-safe: file errors NEVER raise; caller falls back to
    defaults via the get_default_* getters.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("best_config_loader: malformed JSON at %s: %s", path, exc)
        return None
    cfg = data.get("config") or {}
    return BestConfig(
        min_score=float(cfg.get("min_score", _DEFAULTS["min_score"])),
        top_k=int(cfg.get("retrieval_top_k", cfg.get("top_k", _DEFAULTS["top_k"]))),
        rerank_enabled=bool(cfg.get("rerank_enabled", _DEFAULTS["rerank_enabled"])),
        rerank_top_k=int(cfg.get("rerank_top_k", _DEFAULTS["rerank_top_k"])),
        chunking_strategy=str(cfg.get("chunking_strategy", _DEFAULTS["chunking_strategy"])),
        pass_rate=float(data.get("pass_rate", 0.0)),
        promoted_at_ts=float(data.get("promoted_at_ts", 0.0)),
        eval_set_size=int(data.get("eval_set_size", 0)),
        raw=data,
    )


def load_best_config(*, path: str | None = None, force: bool = False) -> BestConfig | None:
    """Load BestConfig from disk with TTL caching.

    Returns None when file missing OR malformed OR loader disabled.
    Caller should use the get_default_* getters which fall back to
    sane defaults — never raises.

    `force=True` bypasses cache.
    """
    if not is_available():
        return None
    global _cached, _cached_at
    use_path = path or BEST_CONFIG_PATH
    now = time.time()
    if not force and _cached is not None and (now - _cached_at) < BEST_CONFIG_TTL_S:
        return _cached
    cfg = _read_file(use_path)
    if cfg is not None:
        _cached = cfg
        _cached_at = now
        log.info(
            "best_config_loaded path=%s min_score=%.2f top_k=%d rerank=%s pass_rate=%.2f",
            use_path, cfg.min_score, cfg.top_k, cfg.rerank_enabled, cfg.pass_rate,
        )
    return cfg


def get_default_min_score() -> float:
    """Return min_score from BestConfig, falling back to legacy default."""
    cfg = load_best_config()
    return cfg.min_score if cfg else _DEFAULTS["min_score"]


def get_default_top_k() -> int:
    """Return top_k from BestConfig, falling back to legacy default."""
    cfg = load_best_config()
    return cfg.top_k if cfg else _DEFAULTS["top_k"]


def get_default_rerank_enabled() -> bool:
    """Return rerank_enabled from BestConfig, falling back to legacy."""
    cfg = load_best_config()
    return cfg.rerank_enabled if cfg else _DEFAULTS["rerank_enabled"]


def force_reload() -> BestConfig | None:
    """Operator hook — force re-read from disk regardless of TTL."""
    return load_best_config(force=True)


if __name__ == "__main__":
    import sys
    print("scripts/best_config_loader.py — Stage-1 best-config registry reader")
    print(f"Stage-1 opt-in via BEST_CONFIG_LOADER_ENABLED=1")
    print()
    print(json.dumps(status(), indent=2, default=str))
    print()
    if is_available():
        cfg = load_best_config(force=True)
        if cfg:
            print(f"Loaded BestConfig:")
            print(json.dumps(cfg.as_dict(), indent=2))
        else:
            print(f"No best_config.json at {BEST_CONFIG_PATH} — using defaults")
            print(f"Defaults: {_DEFAULTS}")
    sys.exit(0)
