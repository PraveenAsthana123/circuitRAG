"""Warm council pool — keep all 4 Ollama council models RAM-resident.

Per CLAUDE.md §50 + §55. Closes Tier 2 #2.5: cold-start latency on
the first council call is ~100s (4 models cold-load from disk).
Subsequent calls are ~30s. With models warm in RAM, every call is
near-instant.

Strategy: send a trivial request to each model with `keep_alive=24h`.
Ollama's `keep_alive` param keeps the model in RAM for the specified
duration after the request; default is 5 minutes (so calls 5+ min
apart cold-load again). 24h = effectively persistent for daemon
workloads.

USAGE
=====

  python3 scripts/warm_council_pool.py             # warm all 4 models once
  python3 scripts/warm_council_pool.py --status    # show which models are loaded right now
  python3 scripts/warm_council_pool.py --watch     # re-warm every 10 minutes (foreground)

Drilled by mcp/tests/drill_warm_council_pool.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_PS_URL = "http://localhost:11434/api/ps"
OLLAMA_GEN_URL = "http://localhost:11434/api/generate"

COUNCIL_MODELS: tuple[str, ...] = (
    "qwen2.5:latest",                # researcher
    "deepseek-coder:6.7b-instruct",  # author
    "codegemma:7b-instruct",         # reviewer
    "codellama:7b-instruct",         # advisor
)

KEEP_ALIVE = "24h"
WATCH_INTERVAL_S = 600  # 10 minutes between re-warms in --watch mode


def _curl_json(url: str, *, timeout: int = 5) -> dict | None:
    """GET a JSON endpoint via curl (avoids requests dep)."""
    proc = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 2,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def get_loaded_models() -> set[str]:
    """Return set of model names currently RAM-resident."""
    body = _curl_json(OLLAMA_PS_URL)
    if body is None:
        return set()
    return {m.get("name", "") for m in body.get("models", []) if m.get("name")}


def warm_model(model: str, *, keep_alive: str = KEEP_ALIVE, timeout: int = 120) -> tuple[bool, float]:
    """Send a trivial request to load + pin the model. Returns (ok, latency_s)."""
    payload = {
        "model": model,
        "prompt": "reply: ok",
        "stream": False,
        "options": {"num_predict": 4, "temperature": 0.0},
        "keep_alive": keep_alive,
    }
    started = time.time()
    proc = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout),
         "-X", "POST", OLLAMA_GEN_URL,
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    elapsed = time.time() - started
    if proc.returncode != 0:
        return False, elapsed
    try:
        body = json.loads(proc.stdout)
        if body.get("response") is None:
            return False, elapsed
        return True, elapsed
    except json.JSONDecodeError:
        return False, elapsed


def cmd_warm(_: argparse.Namespace) -> int:
    """Warm all 4 council models once."""
    print(f"Warming {len(COUNCIL_MODELS)} council models with keep_alive={KEEP_ALIVE}...")
    failures: list[str] = []
    for model in COUNCIL_MODELS:
        ok, elapsed = warm_model(model)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {model:<32} ({elapsed:.1f}s)")
        if not ok:
            failures.append(model)
    if failures:
        print(f"\nx {len(failures)} model(s) failed to warm: {failures}")
        return 1
    print(f"\n✓ all {len(COUNCIL_MODELS)} models warmed; pinned for {KEEP_ALIVE}")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    """Show which models are RAM-resident right now."""
    loaded = get_loaded_models()
    print(f"Ollama RAM-resident models ({len(loaded)} total):")
    for model in COUNCIL_MODELS:
        marker = "✓ loaded" if model in loaded else "✗ cold"
        print(f"  {marker:<10} {model}")
    extra = loaded - set(COUNCIL_MODELS)
    if extra:
        print(f"  (other models loaded: {sorted(extra)})")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Re-warm every WATCH_INTERVAL_S seconds (foreground; Ctrl-C to stop)."""
    interval = args.interval if args.interval > 0 else WATCH_INTERVAL_S
    print(f"Watching: re-warming {len(COUNCIL_MODELS)} models every {interval}s. Ctrl-C to stop.")
    cycles = 0
    try:
        while True:
            cycles += 1
            print(f"\n=== cycle {cycles} at {time.strftime('%H:%M:%S')} ===")
            cmd_warm(args)
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\nstopped after {cycles} cycle(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="warm_council_pool.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=False)
    p_warm = sub.add_parser("warm", help="warm all 4 models once (default)")
    p_warm.set_defaults(func=cmd_warm)
    p_status = sub.add_parser("status", help="show RAM-resident models")
    p_status.set_defaults(func=cmd_status)
    p_watch = sub.add_parser("watch", help="re-warm every N seconds (foreground)")
    p_watch.add_argument("--interval", type=int, default=WATCH_INTERVAL_S)
    p_watch.set_defaults(func=cmd_watch)
    parser.add_argument("--status", action="store_const", const="status", dest="alt_cmd")
    parser.add_argument("--watch", action="store_const", const="watch", dest="alt_cmd")
    args = parser.parse_args()
    if args.cmd is None:
        # Default to warm-once when no subcommand specified
        if getattr(args, "alt_cmd", None) == "status":
            return cmd_status(args)
        if getattr(args, "alt_cmd", None) == "watch":
            args.interval = WATCH_INTERVAL_S
            return cmd_watch(args)
        return cmd_warm(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
