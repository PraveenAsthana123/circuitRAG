#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: warm council pool — Tier 2 #2.5 contract.

Per CLAUDE.md §43 + §55. Locks the contract that the pool warmer:
  - knows all 4 council models
  - sends keep_alive=24h on every warm call
  - never invokes destructive ops
  - --status mode reports RAM-resident state without mutation

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "warm_council_pool.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("warm_council_pool", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["warm_council_pool"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: warm_council_pool imports + 5 exports --")
    wp = _load()
    for name in ("COUNCIL_MODELS", "KEEP_ALIVE", "warm_model",
                 "get_loaded_models", "main"):
        if not hasattr(wp, name):
            print(f"x step 1: missing export {name}")
            return 1
    print(f"  ok: 5 exports; KEEP_ALIVE={wp.KEEP_ALIVE}")

    print("-- 2. POSITIVE: COUNCIL_MODELS has all 4 council members --")
    expected = {
        "qwen2.5:latest",
        "deepseek-coder:6.7b-instruct",
        "codegemma:7b-instruct",
        "codellama:7b-instruct",
    }
    actual = set(wp.COUNCIL_MODELS)
    if actual != expected:
        print(f"x step 2: COUNCIL_MODELS mismatch — expected {expected}, got {actual}")
        return 1
    print("  ok: 4 models match the council roster")

    print("-- 3. NEGATIVE: KEEP_ALIVE is set to 24h (not default 5min) --")
    if wp.KEEP_ALIVE != "24h":
        print(f"x step 3: KEEP_ALIVE expected '24h'; got {wp.KEEP_ALIVE!r}")
        return 1
    print("  ok: KEEP_ALIVE='24h' overrides Ollama default 5m")

    print("-- 4. NEGATIVE: warm_model payload includes keep_alive --")
    src = SCRIPT.read_text(encoding="utf-8")
    if '"keep_alive": keep_alive' not in src:
        print("x step 4: warm_model payload missing keep_alive field")
        return 1
    print("  ok: warm_model JSON payload sets keep_alive")

    print("-- 5. NEGATIVE: script does NOT contain destructive ops --")
    forbidden = ("ollama rm", "ollama push", "ollama delete", "shutil.rmtree",
                 "rm -rf", "git push --force")
    for pattern in forbidden:
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if pattern in line:
                print(f"x step 5: forbidden op {pattern!r} in script: {stripped[:80]}")
                return 1
    print("  ok: no destructive ops; script is read+warm-only")

    print("-- 6. NEGATIVE: get_loaded_models hits /api/ps NOT /api/generate --")
    # /api/ps is read-only; /api/generate would mutate (load on demand).
    if "OLLAMA_PS_URL" not in src:
        print("x step 6: missing OLLAMA_PS_URL constant")
        return 1
    if "/api/ps" not in src:
        print("x step 6: status path not pointing at /api/ps (read-only endpoint)")
        return 1
    # Verify get_loaded_models uses _curl_json on PS_URL specifically
    get_loaded_match = re.search(
        r"def get_loaded_models\([^)]*\)[^:]*:(.*?)(?=\ndef |\Z)",
        src, re.DOTALL,
    )
    if get_loaded_match is None:
        print("x step 6: get_loaded_models() not found")
        return 1
    if "OLLAMA_PS_URL" not in get_loaded_match.group(1):
        print("x step 6: get_loaded_models() does not use OLLAMA_PS_URL")
        return 1
    print("  ok: status read via /api/ps (no model load triggered)")

    print("-- 7. NEGATIVE: --watch supports operator-tunable --interval --")
    if "--interval" not in src or "args.interval" not in src:
        print("x step 7: --watch missing --interval argument")
        return 1
    if "WATCH_INTERVAL_S" not in src:
        print("x step 7: WATCH_INTERVAL_S default missing")
        return 1
    if wp.WATCH_INTERVAL_S < 60:
        print(f"x step 7: WATCH_INTERVAL_S={wp.WATCH_INTERVAL_S}s; should be ≥60s to avoid Ollama spam")
        return 1
    print(f"  ok: --interval tunable; default {wp.WATCH_INTERVAL_S}s ({wp.WATCH_INTERVAL_S//60}min)")

    print("-- 8. POSITIVE: 3 subcommands (warm / status / watch) all wired --")
    for cmd in ("def cmd_warm(", "def cmd_status(", "def cmd_watch("):
        if cmd not in src:
            print(f"x step 8: missing {cmd}")
            return 1
    if 'add_parser("warm"' not in src or 'add_parser("status"' not in src or 'add_parser("watch"' not in src:
        print("x step 8: argparse subparsers missing one of warm/status/watch")
        return 1
    print("  ok: 3 subcommands wired (warm / status / watch)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
