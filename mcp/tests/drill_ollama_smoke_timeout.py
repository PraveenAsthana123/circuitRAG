#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ollama_all_models_smoke.py default timeout MUST be ≥180s.

Why this drill exists:
  Initial DEFAULT_TIMEOUT was 60.0s, which silently tagged 5 of 15
  models TIMEOUT for cold-load reasons (not actual model failure).
  agent-readiness page reported "MIXED 10/15" → operators chasing
  phantom failures. The fix raises the floor to 180s which catches
  cold-loaded 7-8B models on dev-box CPU inference.

  This drill prevents regression: if a future "performance" patch
  drops the default back to 60s, the drill rejects.

5 steps, 3 negative.

  1. POSITIVE: scripts/ollama_all_models_smoke.py exists
  2. POSITIVE: DEFAULT_TIMEOUT constant declared
  3. POSITIVE: DEFAULT_TIMEOUT ≥ 180.0 (current floor for cold-loaded
              7-8B models on dev box)
  4. NEGATIVE: DEFAULT_TIMEOUT comment explains WHY it's 180s
              (operators reading the code without context would
              "optimize" it down again — the comment is the lock)
  5. NEGATIVE: smoke script does NOT silently bump per-call timeout
              over the CLI value (the CLI is the operator's
              expressed preference; the script must respect it)

Per CLAUDE.md §43 (drill discipline; ≥3 negatives — 3 here),
§57.7 honesty (5 TIMEOUT was cold-load not failure; drill prevents
"optimization" that re-introduces the false-negative).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "scripts" / "ollama_all_models_smoke.py"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. file exists ─────────────────────────────────────────────────
    step("1. POSITIVE: scripts/ollama_all_models_smoke.py exists")
    if not SMOKE.exists():
        fail(f"missing: {SMOKE.relative_to(REPO)}")
    text = SMOKE.read_text(encoding="utf-8")
    ok(f"smoke script present ({len(text)}b)")

    # ── 2. DEFAULT_TIMEOUT declared ───────────────────────────────────
    step("2. POSITIVE: DEFAULT_TIMEOUT constant declared")
    m = re.search(r"^DEFAULT_TIMEOUT\s*=\s*([0-9.]+)\s*$", text, re.MULTILINE)
    if not m:
        fail("DEFAULT_TIMEOUT constant not found at module scope")
    value = float(m.group(1))
    ok(f"DEFAULT_TIMEOUT = {value}")

    # ── 3. DEFAULT_TIMEOUT ≥ 180s ─────────────────────────────────────
    step("3. POSITIVE: DEFAULT_TIMEOUT ≥ 180.0 (cold-load floor)")
    if value < 180.0:
        fail(
            f"DEFAULT_TIMEOUT={value}s — too low for cold-loaded 7-8B models. "
            f"60s tagged 5 of 15 models TIMEOUT for cold-load reasons (NOT "
            f"actual failure). Floor is 180s; tighten via CLI --timeout for "
            f"warm-cache fast-fail scenarios."
        )
    ok(f"DEFAULT_TIMEOUT={value} satisfies ≥180s floor")

    # ── 4. NEGATIVE: WHY-comment present near DEFAULT_TIMEOUT ─────────
    step("4. NEGATIVE: DEFAULT_TIMEOUT comment explains the 180s rationale")
    # Find the DEFAULT_TIMEOUT line and look at the 12 lines preceding
    # it for an explanatory comment block.
    idx = text.find("DEFAULT_TIMEOUT")
    if idx < 0:
        fail("DEFAULT_TIMEOUT not found (impossible — already asserted in step 2)")
    preamble = text[max(0, idx - 1200) : idx]
    required_phrases = [
        "cold-load",      # the failure mode being defended against
        "keep_alive",     # the design choice making cold-load mandatory
        "180s",           # the explicit chosen value referenced in prose
    ]
    missing = [p for p in required_phrases if p not in preamble]
    if missing:
        fail(
            f"DEFAULT_TIMEOUT lacks explanatory comment phrases {missing} — "
            f"future readers will 'optimize' it down without understanding the "
            f"5-TIMEOUT regression that justifies 180s. Add a comment block."
        )
    ok("comment block explains WHY 180s (cold-load + keep_alive + value)")

    # ── 5. NEGATIVE: per-call timeout passes through CLI value ────────
    step("5. NEGATIVE: per-call timeout uses the operator-provided CLI value")
    # The smoke_one_model function takes `timeout: float` and passes it
    # through to _http_post. If anyone hardcodes a different value
    # there, the CLI flag becomes a lie.
    fn_block = re.search(
        r"def smoke_one_model\(name: str, timeout: float\) -> dict:.*?(?=\ndef |\Z)",
        text,
        re.DOTALL,
    )
    if not fn_block:
        fail("smoke_one_model function signature changed shape — drill needs update")
    body = fn_block.group(0)
    # Look for any `timeout=<literal-number>` in the function body; that
    # would shadow the parameter.
    bad = re.findall(r"timeout=([0-9]+\.?[0-9]*)\b", body)
    if bad:
        fail(
            f"smoke_one_model body hardcodes timeout values {bad}, "
            f"shadowing the CLI parameter — operator's --timeout flag would "
            f"silently become a lie for those calls"
        )
    if "timeout=timeout" not in body:
        fail("smoke_one_model does not pass `timeout=timeout` to _http_post — broken pass-through")
    ok("per-call timeout passes through cleanly (no hardcoded shadow)")

    print(f"\n{BOLD}{GREEN}ALL 5 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
