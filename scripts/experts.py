#!/usr/bin/env python3
"""Experts registry — named specialists backed by local Ollama models.

Each expert has:
  - name        (the CLI argument)
  - model       (local Ollama model that handles it)
  - purpose     (what kinds of tasks fit this expert)
  - prompt_lead (system-style prefix that puts the model in role)

Invocation:
    experts.py <expert> [--input <file>] [--prompt "<text>"] [--save]
                        [--repo <path>]

Examples:
    # Refactor a file
    experts.py code --input services/foo/bar.py --prompt "Make this function pure"

    # Generate docstrings
    experts.py doc --input services/foo/bar.py

    # Review the diff that's currently staged
    git diff --cached | experts.py review

    # Architectural advice on a design question
    experts.py advise --prompt "Should api-gateway live in compose or run native?"

    # Layer/dependency analysis
    experts.py layer --input services/foo/bar.py

    # General-purpose
    experts.py gpt --prompt "Summarize the docker-compose stack in 5 bullets"

Every invocation writes an audit row to .loop/experts_log.jsonl with
the expert name, model, prompt-hash, response-length, tokens, latency,
and ts. Use --save to also dump the full response to .loop/experts/<id>.txt.

Compose-with: scripts/issue_dispatcher.py uses author/reviewer/advisor
council roles internally. This experts.py is the chair-callable
catalog: humans + scripts call ONE specialist explicitly. The
dispatcher's COUNCIL_ROLES is a fixed 3-role pattern; the experts
registry is a 6+ open catalog for arbitrary delegation.

Locked by mcp/tests/drill_experts_registry.py (in any project that
adopts it).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path.cwd()
EXPERTS_LOG = REPO / ".loop" / "experts_log.jsonl"
EXPERTS_DIR = REPO / ".loop" / "experts"
OLLAMA = "http://localhost:11434/api/generate"


EXPERTS: dict[str, dict[str, str]] = {
    "code": {
        "model": "deepseek-coder:6.7b-instruct",
        "purpose": "Refactor / write Python or TypeScript code; produce minimal diffs.",
        "prompt_lead": (
            "You are the CODE expert. Given the input below, produce the "
            "minimal code change that satisfies the request. Output ONLY the "
            "new code or a unified diff — no explanatory prose, no markdown "
            "fences. Preserve indentation, type annotations, and existing "
            "comments unless explicitly asked to change them."
        ),
    },
    "doc": {
        "model": "qwen2.5:latest",
        "purpose": "Write / improve docstrings, README sections, runbook prose.",
        "prompt_lead": (
            "You are the DOC expert. Given the input below, write the "
            "documentation requested. Use plain English, active voice, "
            "concrete examples. NEVER invent function names or paths "
            "that aren't in the input. Output ONLY the documentation."
        ),
    },
    "review": {
        "model": "codegemma:7b-instruct",
        "purpose": "Review code / diffs for bugs, security risks, style.",
        "prompt_lead": (
            "You are the REVIEW expert. Given the input below, identify: "
            "(1) bugs (logic, off-by-one, null), (2) security risks (input "
            "validation, secrets, injection), (3) style issues (naming, "
            "complexity). Output a numbered list of specific concerns. "
            "If the input is clean, say 'no concerns' in one line."
        ),
    },
    "advise": {
        "model": "codellama:7b-instruct",
        "purpose": "Architectural advice on design decisions / tradeoffs.",
        "prompt_lead": (
            "You are the ADVISE expert. Given the question or design "
            "below, propose 2-3 options with their tradeoffs. Pick a "
            "recommended option with a 1-paragraph rationale. Be specific "
            "about cost / complexity / risk per option."
        ),
    },
    "layer": {
        "model": "codellama:7b-instruct",
        "purpose": "Architecture layering / dependency analysis.",
        "prompt_lead": (
            "You are the LAYER expert. Given the code or module structure "
            "below, analyze: (1) which layer this code sits in (router / "
            "service / repo / model), (2) any cross-layer leakage (e.g. "
            "SQL in a router, HTTPException in a service), (3) suggested "
            "boundary fix. Output 3 sections: 'layer:', 'leakage:', 'fix:'."
        ),
    },
    "gpt": {
        "model": "llama3.1:8b",
        "purpose": "General-purpose; use when no specialist fits the task.",
        "prompt_lead": (
            "You are a general-purpose assistant. Answer the question or "
            "complete the task below directly. Be concise. If the task is "
            "ambiguous, ask one clarifying question instead of guessing."
        ),
    },
}


def call_ollama(model: str, prompt: str, timeout_s: int = 180) -> tuple[str, int]:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }).encode()
    req = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read())
    return data.get("response", ""), data.get("eval_count", 0)


def write_log(row: dict) -> None:
    EXPERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {**row, "ts": datetime.now(UTC).isoformat(timespec="seconds")}
    with EXPERTS_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


def hash_prompt(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def list_experts() -> int:
    print(f"{'expert':<10} {'model':<35} purpose")
    print(f"{'-' * 10} {'-' * 35} {'-' * 50}")
    for name, info in EXPERTS.items():
        print(f"{name:<10} {info['model']:<35} {info['purpose']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("expert", nargs="?", help=f"one of: {','.join(EXPERTS)}")
    parser.add_argument("--input", help="file to read as input (default: stdin if piped)")
    parser.add_argument("--prompt", help="text prompt (replaces or augments input)")
    parser.add_argument("--save", action="store_true", help="dump response to .loop/experts/<id>.txt")
    parser.add_argument("--repo", help="project root (default: cwd)")
    parser.add_argument("--list", action="store_true", help="list available experts")
    args = parser.parse_args()

    if args.repo:
        global REPO, EXPERTS_LOG, EXPERTS_DIR
        REPO = Path(args.repo).resolve()
        EXPERTS_LOG = REPO / ".loop" / "experts_log.jsonl"
        EXPERTS_DIR = REPO / ".loop" / "experts"

    if args.list or not args.expert:
        return list_experts()

    if args.expert not in EXPERTS:
        print(f"unknown expert: {args.expert}", file=sys.stderr)
        print(f"available: {', '.join(EXPERTS)}", file=sys.stderr)
        return 2

    expert = EXPERTS[args.expert]

    body_parts: list[str] = [expert["prompt_lead"]]
    input_text = ""
    if args.input:
        input_text = Path(args.input).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        input_text = sys.stdin.read()
    if input_text.strip():
        body_parts.append("\n--- INPUT ---\n" + input_text)
    if args.prompt:
        body_parts.append("\n--- PROMPT ---\n" + args.prompt)
    if not input_text.strip() and not args.prompt:
        print("error: provide --input <file>, --prompt <text>, or pipe stdin", file=sys.stderr)
        return 2

    full_prompt = "\n".join(body_parts)
    prompt_hash = hash_prompt(full_prompt)
    print(f"[{args.expert}] model={expert['model']} prompt_hash={prompt_hash}", file=sys.stderr)

    started = time.time()
    try:
        response, tokens = call_ollama(expert["model"], full_prompt)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        write_log({
            "expert": args.expert,
            "model": expert["model"],
            "prompt_hash": prompt_hash,
            "outcome": "error",
            "error": str(e),
        })
        return 1
    elapsed = round(time.time() - started, 1)

    print(response)

    write_log({
        "expert": args.expert,
        "model": expert["model"],
        "prompt_hash": prompt_hash,
        "tokens": tokens,
        "latency_s": elapsed,
        "response_len": len(response),
        "outcome": "ok",
    })

    if args.save:
        EXPERTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = EXPERTS_DIR / f"{args.expert}-{prompt_hash}.txt"
        out_path.write_text(response, encoding="utf-8")
        print(f"\n[saved to {out_path}]", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
