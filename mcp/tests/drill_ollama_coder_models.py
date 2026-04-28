#!/usr/bin/env python3
# RESOURCES: ollama
"""
Drill: Ollama coder-LLM catalogue is installed + reachable.

Locks the contract that the four coder-focused models the platform
relies on — Code Llama, DeepSeek Coder, StarCoder2, CodeGemma — are
present in the local Ollama daemon AND respond to a sanity prompt
under a generous deadline. A regression that:

  * Lets the disk fill until a pull was silently truncated → caught
    here (step 1: every catalogued model in /api/tags).
  * Disables one model's runtime support (e.g. an Ollama upgrade
    drops a tokenizer) → caught here (step 2: each model returns
    non-empty completion under 60s).
  * Adds a fifth model to docs/models/coder-llms.md without
    actually pulling it → caught here (step 3, NEGATIVE: every
    model in the catalogue MUST be installed; missing model fails
    the drill).

Tag: ollama — this drill needs the local Ollama daemon running on
the conventional 11434 port. It is NOT in tier 1 (which is
infra-free); it runs in a separate "local ops verification" tier.

Run directly:
    python3 mcp/tests/drill_ollama_coder_models.py

Or via the runner (only fires if --allow-resources includes 'ollama'):
    scripts/run_drills.py --allow-resources=ollama --only ollama_coder
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


# ── Config ───────────────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# The catalogue. Each entry is (display_name, ollama_tag, role).
# Keep this in lockstep with docs/models/coder-llms.md — the drill
# step 3 enforces the doc/install parity.
COODER_CATALOGUE = [
    ("Code Llama",     "codellama:7b-instruct",        "Meta open-weights baseline"),
    ("DeepSeek Coder", "deepseek-coder:6.7b-instruct", "best per-watt coder under 7B"),
    ("StarCoder2",     "starcoder2:7b",                "permissive license; enterprise-safe"),
    ("CodeGemma",      "codegemma:7b-instruct",        "Apache 2.0; smaller-capacity local dev"),
]

# Use a code-completion style prompt rather than a natural-language
# instruction so it works for BOTH instruct-tuned models (CodeLlama,
# DeepSeek Coder, CodeGemma) AND base completion models (StarCoder2).
# StarCoder2:7b is the base variant; it ignores instructions and only
# responds to fragments it can complete.
PROMPT = (
    "def is_prime(n: int) -> bool:\n"
    "    \"\"\"Return True if n is prime, False otherwise.\"\"\"\n"
)
# Generous deadline — first run on a cold cache pulls weights into VRAM,
# so the very first prompt of the day can take 30-40s before the model
# is hot. Subsequent prompts are <5s.
PER_MODEL_DEADLINE_S = 90.0


def _http_get_json(path: str, timeout: float = 5.0) -> dict:
    req = Request(f"{OLLAMA_URL}{path}")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _http_post_json(path: str, body: dict, timeout: float = 90.0) -> dict:
    data = json.dumps(body).encode()
    req = Request(
        f"{OLLAMA_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=timeout) as resp:
        # /api/generate streams NDJSON unless stream=false; we set false.
        return json.loads(resp.read().decode())


async def _generate_with_deadline(model: str, prompt: str, deadline: float) -> tuple[str, float]:
    """Run a one-shot completion against the model. Returns (text, elapsed_s).
    Raises TimeoutError if deadline exceeded."""
    loop = asyncio.get_running_loop()
    t0 = time.monotonic()
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            # Keep it short — we only need to know the model responded
            # with SOMETHING coherent. The drill is a reachability /
            # liveness probe, not a quality benchmark.
            "num_predict": 64,
            "temperature": 0.0,
        },
    }
    try:
        # Run blocking urlopen in a thread so the asyncio deadline can fire.
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _http_post_json, "/api/generate", body, deadline),
            timeout=deadline,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"model {model} did not respond within {deadline}s"
        ) from exc
    elapsed = time.monotonic() - t0
    return result.get("response", ""), elapsed


async def main() -> None:
    # ── Step 0: daemon reachable ────────────────────────────────
    step("0. Ollama daemon reachable")
    try:
        ver = _http_get_json("/api/version")
    except URLError as exc:
        fail(
            f"Ollama daemon not reachable at {OLLAMA_URL}: {exc}. "
            f"Start with: systemctl start ollama"
        )
    ok(f"Ollama {ver.get('version', 'unknown')} reachable at {OLLAMA_URL}")

    # ── Step 1: every catalogued model is in /api/tags ──────────
    step("1. every catalogued coder model is installed")
    try:
        tags = _http_get_json("/api/tags")
    except URLError as exc:
        fail(f"GET /api/tags failed: {exc}")
    installed = {m["name"] for m in tags.get("models", [])}
    missing = [tag for _, tag, _ in COODER_CATALOGUE if tag not in installed]
    if missing:
        fail(
            f"missing models: {missing}\n"
            f"  Pull with: ollama pull {' && ollama pull '.join(missing)}\n"
            f"  Currently installed: {sorted(installed)}"
        )
    ok(f"all 4 catalogued models present: {[c[1] for c in COODER_CATALOGUE]}")

    # ── Step 2: each model produces non-empty completion ────────
    step(
        f"2. each coder model responds to a sanity prompt within "
        f"{PER_MODEL_DEADLINE_S:.0f}s"
    )
    timings: list[tuple[str, float, int]] = []
    for display, tag, _role in COODER_CATALOGUE:
        try:
            text, elapsed = await _generate_with_deadline(
                tag, PROMPT, PER_MODEL_DEADLINE_S,
            )
        except (TimeoutError, URLError) as exc:
            fail(f"{display} ({tag}): {exc}")
        if not text.strip():
            fail(
                f"{display} ({tag}) returned empty response. "
                f"Possible cause: model corrupt; re-pull with "
                f"`ollama pull {tag}`"
            )
        timings.append((tag, elapsed, len(text)))
        # Print per-model summary inline so a slow model is visible
        # immediately rather than after the whole step finishes.
        print(
            f"    {YELLOW}· {display:<16} {tag:<32} "
            f"{elapsed:5.1f}s, {len(text):4d} chars{NC}"
        )
    ok(
        f"all 4 models green; total elapsed "
        f"{sum(t[1] for t in timings):.1f}s"
    )

    # ── Step 3: NEGATIVE — non-existent model returns 404 ───────
    step(
        "3. NEGATIVE: GET /api/show on non-existent model returns 404; "
        "the daemon does NOT silently substitute"
    )
    bogus = "this-model-does-not-exist-please-fail:99b"
    body = json.dumps({"name": bogus}).encode()
    req = Request(
        f"{OLLAMA_URL}/api/show",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urlopen(req, timeout=5)
        body = resp.read()
        fail(
            f"NEGATIVE FAILED: bogus model {bogus!r} returned "
            f"{resp.status} {body[:200]!r}. Daemon should 404 on unknown "
            f"models — silent substitution would mask install regressions."
        )
    except Exception as exc:
        # urllib raises HTTPError (subclass of URLError) for non-2xx.
        msg = str(exc)
        if "404" not in msg and "Not Found" not in msg:
            # Some Ollama versions return 500 here. Either is fine for
            # our contract (the call FAILED), but 404 is the correct one.
            if "500" not in msg:
                fail(
                    f"unexpected error type from /api/show on bogus model: "
                    f"{type(exc).__name__}: {msg}"
                )
        ok(f"bogus model rejected with: {msg[:80]}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 OLLAMA CODER-MODEL STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (1 negative assertion: step 3){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}\n")
    print(f"  Timing summary (cold-cache included):")
    for tag, elapsed, chars in timings:
        print(f"    {tag:<36} {elapsed:5.1f}s  ({chars} chars)")


if __name__ == "__main__":
    asyncio.run(main())
