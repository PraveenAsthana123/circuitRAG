"""Ollama all-models smoke test (iter-75).

Issues a tiny /api/generate request to EVERY installed model and
records per-model status, latency, and the first 80 chars of output.
Embedding-only models (nomic-embed-text) are smoked via /api/embed.

Per CLAUDE.md §43 (drill discipline), §44 (iter-75 ships
"all 15 models verifiably work"), §47 (observability), §50.5.3
(read-only — generates nothing, no tool side-effects), §51
(forensic substrate — every result is a JSON row).

User asked: "all the models on Ollama must work."

Output
------
.loop/ollama_smoke_results.json — keyed by model name, columns:
  status: WORKING | FAILING | TIMEOUT | NOT_INSTALLED
  latency_ms: int
  bytes_in: int (response size)
  preview: str (first 80 chars of response)
  error: str | null
  smoked_at: ISO timestamp

CLI
---
$ python3 scripts/ollama_all_models_smoke.py            # smoke all installed
$ python3 scripts/ollama_all_models_smoke.py --json     # machine-readable
$ python3 scripts/ollama_all_models_smoke.py --only llama3.2:1b
$ python3 scripts/ollama_all_models_smoke.py --timeout 30
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOOP_DIR = REPO / ".loop"
RESULTS_PATH = LOOP_DIR / "ollama_smoke_results.json"

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_TIMEOUT = 60.0
EMBED_FAMILY_HINTS = ("embed", "embedding", "nomic-embed")


def _http_post(url: str, body: dict, timeout: float) -> tuple[int, bytes, float]:
    started = time.monotonic()
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (localhost)
        data = r.read()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return r.status, data, elapsed_ms


def list_installed_models() -> list[str]:
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_BASE}/api/tags", timeout=5.0,
        ) as r:  # noqa: S310 (localhost)
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: cannot list Ollama models: {e}", file=sys.stderr)
        return []


def is_embedding_model(name: str) -> bool:
    lower = name.lower()
    return any(h in lower for h in EMBED_FAMILY_HINTS)


def smoke_one_model(name: str, timeout: float) -> dict:
    """Returns a result dict (NEVER raises)."""
    is_embed = is_embedding_model(name)
    try:
        if is_embed:
            status, data, elapsed_ms = _http_post(
                f"{OLLAMA_BASE}/api/embed",
                {"model": name, "input": "smoke test", "keep_alive": 0},
                timeout=timeout,
            )
            payload = json.loads(data) if data else {}
            embeddings = payload.get("embeddings") or payload.get("embedding") or []
            preview = (
                f"embedding[{len(embeddings[0]) if embeddings else 0}d]"
                if embeddings else "(empty embedding)"
            )
            return {
                "status": "WORKING" if status == 200 and embeddings else "FAILING",
                "latency_ms": elapsed_ms,
                "bytes_in": len(data),
                "preview": preview,
                "error": None,
                "kind": "embed",
                "smoked_at": datetime.now(timezone.utc).isoformat(),
            }

        status, data, elapsed_ms = _http_post(
            f"{OLLAMA_BASE}/api/generate",
            {
                "model": name,
                "prompt": "Say 'ok' in one word.",
                "stream": False,
                "options": {"num_predict": 8, "temperature": 0.0},
                "keep_alive": 0,  # release VRAM immediately
            },
            timeout=timeout,
        )
        payload = json.loads(data) if data else {}
        response_text = (payload.get("response") or "").strip()
        return {
            "status": "WORKING" if status == 200 and response_text else "FAILING",
            "latency_ms": elapsed_ms,
            "bytes_in": len(data),
            "preview": response_text[:80],
            "error": None,
            "kind": "generate",
            "smoked_at": datetime.now(timezone.utc).isoformat(),
        }

    except urllib.error.HTTPError as e:
        return {
            "status": "FAILING",
            "latency_ms": -1,
            "bytes_in": 0,
            "preview": "",
            "error": f"HTTP {e.code}: {e.reason}",
            "kind": "embed" if is_embed else "generate",
            "smoked_at": datetime.now(timezone.utc).isoformat(),
        }
    except TimeoutError:
        return {
            "status": "TIMEOUT",
            "latency_ms": int(timeout * 1000),
            "bytes_in": 0,
            "preview": "",
            "error": f"timeout after {timeout}s",
            "kind": "embed" if is_embed else "generate",
            "smoked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "FAILING",
            "latency_ms": -1,
            "bytes_in": 0,
            "preview": "",
            "error": f"{type(e).__name__}: {e}",
            "kind": "embed" if is_embed else "generate",
            "smoked_at": datetime.now(timezone.utc).isoformat(),
        }


def smoke_all(only: str | None, timeout: float) -> dict:
    installed = list_installed_models()
    if only:
        installed = [m for m in installed if m == only]
        if not installed:
            print(f"NO model matches --only={only!r}", file=sys.stderr)
            return {
                "ollama_base_url": OLLAMA_BASE,
                "smoked_at": datetime.now(timezone.utc).isoformat(),
                "models_total": 0,
                "by_status": {},
                "results": {},
            }

    results: dict[str, dict] = {}
    for name in installed:
        print(f"  smoking {name}…", flush=True)
        results[name] = smoke_one_model(name, timeout)
        print(
            f"    → {results[name]['status']:<14} "
            f"{results[name]['latency_ms']}ms · "
            f"{results[name]['preview'][:40]!r}",
            flush=True,
        )

    by_status: dict[str, int] = {}
    for r in results.values():
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    return {
        "ollama_base_url": OLLAMA_BASE,
        "smoked_at": datetime.now(timezone.utc).isoformat(),
        "models_total": len(installed),
        "by_status": by_status,
        "results": results,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="emit JSON only")
    p.add_argument("--only", help="smoke just this model name")
    p.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"per-model timeout seconds (default {DEFAULT_TIMEOUT})",
    )
    p.add_argument(
        "--write", action="store_true",
        help="write to .loop/ollama_smoke_results.json",
    )
    args = p.parse_args()

    summary = smoke_all(args.only, args.timeout)

    if args.write or not args.json:
        LOOP_DIR.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))

    failing = sum(
        1 for r in summary["results"].values()
        if r["status"] not in ("WORKING",)
    )
    if not args.json:
        print(
            f"\nSummary: {summary['models_total']} models · "
            f"by_status={summary['by_status']}"
        )
        if args.write:
            print(f"Wrote: {RESULTS_PATH.relative_to(REPO)}")

    # Exit 0 if all WORKING; 1 if any FAILING/TIMEOUT
    return 0 if failing == 0 and summary["models_total"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
