#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: best_config_loader Stage-1 (per §43 + §56).

Locks the registry-reader contract that lets inference-svc + retrieval-svc
seed retrieval defaults from the empirically-best config produced by
scripts/run_autorag_empirical.py — without raising on missing/malformed
files (§47 fail-safe).

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
LOADER = REPO / "scripts" / "best_config_loader.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: best_config_loader.py exists + non-trivial --")
    if not LOADER.exists():
        print(f"x {LOADER} missing")
        return 1
    src = LOADER.read_text(encoding="utf-8")
    if len(src) < 3000:
        print(f"x loader too short ({len(src)} chars)")
        return 1
    print(f"  ok: loader present ({len(src)} chars)")

    print("-- 2. NEGATIVE: loader doesn't IMPORT services (clean layering) --")
    import re
    rev_import = re.compile(
        r"^\s*(from\s+.*inference|from\s+.*retrieval|from\s+services\.|"
        r"import\s+.*inference|import\s+.*retrieval|import\s+services\.)",
        re.MULTILINE,
    )
    if rev_import.search(src):
        print("x best_config_loader imports services (cycle risk)")
        return 1
    print("  ok: loader doesn't import services (clean layering)")

    print("-- 3. POSITIVE: 8 contract surfaces exported --")
    os.environ["BEST_CONFIG_LOADER_ENABLED"] = "1"
    os.environ["BEST_CONFIG_PATH"] = "/nonexistent/path/best.json"
    mod, spec = _load_module(LOADER)
    for name in ("load_best_config", "get_default_min_score",
                 "get_default_top_k", "get_default_rerank_enabled",
                 "force_reload", "BestConfig", "is_available", "status"):
        if not hasattr(mod, name):
            print(f"x best_config_loader.{name} missing")
            return 1
    print("  ok: 8 contract surfaces exported")

    print("-- 4. NEGATIVE: post-Stage-3 default-on — env=0 disables, env unset enables --")
    # Per Stage-3 default-flip (2026-05-05; commit shipping with this
    # drill update): env-unset is now ENABLED (default-on after
    # earned-verdict landed live with 19 promotions × 2 distinct
    # configs). Explicit opt-OUT via BEST_CONFIG_LOADER_ENABLED=0.
    # See ADR-024 superseding ADR-023.
    os.environ.pop("BEST_CONFIG_LOADER_ENABLED", None)
    spec.loader.exec_module(mod)
    if not mod.is_available():
        print("x post-Stage-3: is_available() must be True when env unset (default-on)")
        return 1
    # Explicit opt-out
    os.environ["BEST_CONFIG_LOADER_ENABLED"] = "0"
    spec.loader.exec_module(mod)
    if mod.is_available():
        print("x explicit BEST_CONFIG_LOADER_ENABLED=0 must disable")
        return 1
    cfg = mod.load_best_config()
    if cfg is not None:
        print(f"x load_best_config() must return None when explicitly disabled; got {cfg}")
        return 1
    print("  ok: post-Stage-3 default-on; explicit env=0 opts out")

    print("-- 5. NEGATIVE: missing file → getters fall back to legacy defaults (§47 fail-safe) --")
    os.environ["BEST_CONFIG_LOADER_ENABLED"] = "1"
    os.environ["BEST_CONFIG_PATH"] = "/nonexistent/path/best.json"
    spec.loader.exec_module(mod)
    if mod.get_default_min_score() != 0.0:
        print(f"x missing-file min_score must be 0.0 (legacy); got {mod.get_default_min_score()}")
        return 1
    if mod.get_default_top_k() != 10:
        print(f"x missing-file top_k must be 10 (legacy); got {mod.get_default_top_k()}")
        return 1
    if mod.get_default_rerank_enabled() is not False:
        print(f"x missing-file rerank must be False (legacy); got {mod.get_default_rerank_enabled()}")
        return 1
    print("  ok: missing file → legacy defaults; never raises")

    print("-- 6. NEGATIVE: malformed JSON → defaults; never raises --")
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text("not-json-at-all{{{", encoding="utf-8")
        os.environ["BEST_CONFIG_PATH"] = str(bad)
        spec.loader.exec_module(mod)
        # MUST NOT raise
        try:
            cfg = mod.load_best_config(force=True)
        except Exception as exc:
            print(f"x malformed JSON must not raise; got {exc}")
            return 1
        if cfg is not None:
            print(f"x malformed JSON must yield None; got {cfg}")
            return 1
        # Getters still fall back
        if mod.get_default_min_score() != 0.0:
            print("x malformed JSON: getter must fall back to legacy default")
            return 1
    print("  ok: malformed JSON → defaults; never raises")

    print("-- 7. POSITIVE: valid file → BestConfig populated; getters reflect file --")
    with TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.json"
        good.write_text(json.dumps({
            "promoted_at_ts": 1730000000.0,
            "config": {
                "chunking_strategy": "recursive_paragraph_sentence",
                "min_score": 0.5,
                "rerank_enabled": True,
                "rerank_top_k": 10,
                "retrieval_top_k": 10,
            },
            "pass_rate": 1.0,
            "eval_set_size": 5,
        }), encoding="utf-8")
        os.environ["BEST_CONFIG_PATH"] = str(good)
        spec.loader.exec_module(mod)
        cfg = mod.load_best_config(force=True)
        if cfg is None:
            print("x valid file must produce BestConfig")
            return 1
        if cfg.min_score != 0.5:
            print(f"x min_score expected 0.5; got {cfg.min_score}")
            return 1
        if cfg.top_k != 10:
            print(f"x top_k expected 10; got {cfg.top_k}")
            return 1
        if cfg.rerank_enabled is not True:
            print(f"x rerank expected True; got {cfg.rerank_enabled}")
            return 1
        if cfg.pass_rate != 1.0:
            print(f"x pass_rate expected 1.0; got {cfg.pass_rate}")
            return 1
        # Getters reflect file
        if mod.get_default_min_score() != 0.5:
            print("x getter must reflect loaded file")
            return 1
        if mod.get_default_top_k() != 10:
            print("x getter must reflect loaded file")
            return 1
        if mod.get_default_rerank_enabled() is not True:
            print("x getter must reflect loaded file")
            return 1
        # as_dict() round-trip
        d = cfg.as_dict()
        for k in ("min_score", "top_k", "rerank_enabled", "rerank_top_k",
                 "chunking_strategy", "pass_rate", "promoted_at_ts",
                 "eval_set_size"):
            if k not in d:
                print(f"x BestConfig.as_dict() missing key {k}")
                return 1
    print("  ok: valid file → BestConfig populated; getters reflect")

    print("-- 8. NEGATIVE: status() shape + Stage-2 next-stage cite --")
    os.environ["BEST_CONFIG_LOADER_ENABLED"] = "1"
    os.environ["BEST_CONFIG_PATH"] = ".loop/best_config.json"
    spec.loader.exec_module(mod)
    st = mod.status()
    for k in ("stage", "enabled_env", "available", "config_path",
             "config_exists", "ttl_s", "cache_warm", "cache_age_s",
             "fallback_defaults", "next_stage", "wiring_status"):
        if k not in st:
            print(f"x status() missing key {k}")
            return 1
    if st["stage"] != 1:
        print(f"x status.stage must be 1; got {st['stage']}")
        return 1
    if "Stage-2" not in st["next_stage"]:
        print("x status.next_stage must reference Stage-2 wiring")
        return 1
    nxt_low = st["next_stage"].lower()
    if "rag_inference" not in nxt_low and "retrieve" not in nxt_low and "hybrid" not in nxt_low:
        print("x status.next_stage must mention rag_inference / retriever wiring site")
        return 1
    # fallback_defaults must match legacy
    fb = st["fallback_defaults"]
    if fb.get("min_score") != 0.0 or fb.get("top_k") != 10 or fb.get("rerank_enabled") is not False:
        print(f"x fallback_defaults must match legacy un-tuned behavior; got {fb}")
        return 1
    print("  ok: status() shape + Stage-2 path + legacy fallbacks")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
