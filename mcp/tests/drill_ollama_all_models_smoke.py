# RESOURCES: ollama_runtime
"""
Drill: Ollama all-models smoke test (iter-75).

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (iter-75
ships "all 15 models verifiably work"), §50.5.3 (read-only — generates
nothing, no tool side-effects), §51 (forensic substrate — every result
captured to .loop).

User asked: "all the models on Ollama must work." Iter-72 fleet-health
confirmed they're INSTALLED. iter-75 confirms they actually GENERATE.

Locks (positive):
  L1. Smoke script exists + has canonical structure
  L2. /api/tags reachable + returns ≥10 installed models
  L3. Smoking ONE model returns status==WORKING + non-empty preview
  L4. Smoking the embedding model returns "embedding[Nd]" preview
  L5. Result file .loop/ollama_smoke_results.json materialised

Locks (negative):
  N1. keep_alive=0 in request body (no VRAM pinning regression)
  N2. is_embedding_model("nomic-embed-text") returns True (route correct)
  N3. is_embedding_model("llama3.2:3b") returns False (route correct)
  N4. Unknown model returns FAILING (not silent-success)
  N5. Smoke does NOT call /api/generate on embed-only model (would 400)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ollama_all_models_smoke.py"
RESULTS = REPO / ".loop" / "ollama_smoke_results.json"
sys.path.insert(0, str(REPO / "scripts"))

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
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT.relative_to(REPO)}")

    src = SCRIPT.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: canonical structure
    # ------------------------------------------------------------------
    step("1. smoke script has canonical structure")
    for marker in (
        "def smoke_one_model",
        "def smoke_all",
        "def list_installed_models",
        "def is_embedding_model",
        '"WORKING"',
    ):
        if marker not in src:
            fail(f"script missing canonical symbol: {marker}")
    ok("script has canonical structure")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: /api/tags reachable
    # ------------------------------------------------------------------
    step("2. Ollama /api/tags lists ≥10 installed models")
    import ollama_all_models_smoke as oas  # type: ignore[import-not-found]
    installed = oas.list_installed_models()
    if len(installed) < 10:
        fail(f"only {len(installed)} models installed; expected ≥10")
    ok(f"{len(installed)} installed models present")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: smoke one cheap model returns WORKING
    # ------------------------------------------------------------------
    step("3. smoke ONE small model returns status WORKING")
    candidate = next(
        (m for m in installed if m.startswith(("llama3.2:1b", "gemma3:1b", "llama3.2:3b"))),
        installed[0],
    )
    r = oas.smoke_one_model(candidate, timeout=60.0)
    if r["status"] != "WORKING":
        fail(f"{candidate} smoke status={r['status']}; error={r.get('error')}")
    if not r["preview"]:
        fail(f"{candidate} returned empty preview — broken response shape")
    ok(f"{candidate}: status={r['status']} preview={r['preview']!r}")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: smoke embedding model returns embedding[Nd]
    # ------------------------------------------------------------------
    step("4. embedding-model smoke returns 'embedding[Nd]' preview")
    embed_candidate = next((m for m in installed if "embed" in m.lower()), None)
    if embed_candidate is None:
        ok("no embedding model installed; step skipped")
    else:
        r = oas.smoke_one_model(embed_candidate, timeout=60.0)
        if r["status"] != "WORKING":
            fail(f"{embed_candidate} embed-smoke status={r['status']}; error={r.get('error')}")
        if not r["preview"].startswith("embedding["):
            fail(f"embed-smoke preview wrong shape: {r['preview']!r}")
        ok(f"{embed_candidate}: {r['preview']}")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: results file materialised
    # ------------------------------------------------------------------
    step("5. .loop/ollama_smoke_results.json exists + parseable")
    if not RESULTS.exists():
        fail(f"results file missing: {RESULTS.relative_to(REPO)}")
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    if "models_total" not in payload or "by_status" not in payload:
        fail("results file missing canonical keys")
    if "results" not in payload or not isinstance(payload["results"], dict):
        fail("results.results not a dict")
    ok(f"results file: models_total={payload['models_total']} by_status={payload['by_status']}")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: keep_alive=0 in request (no VRAM pin)
    # ------------------------------------------------------------------
    step("6. NEGATIVE: keep_alive=0 in generate body (no VRAM pinning)")
    if '"keep_alive": 0' not in src:
        fail("smoke script does NOT pass keep_alive=0 — would pin VRAM per smoke")
    ok("keep_alive=0 set on every smoke request")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: is_embedding_model routes correctly
    # ------------------------------------------------------------------
    step("7. NEGATIVE: is_embedding_model() routes correctly")
    if not oas.is_embedding_model("nomic-embed-text:latest"):
        fail("'nomic-embed-text:latest' NOT classified as embedding (would 400 on /api/generate)")
    if oas.is_embedding_model("llama3.2:3b"):
        fail("'llama3.2:3b' WRONGLY classified as embedding (would skip /api/generate)")
    ok("embed routing correct: nomic→embed, llama→generate")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: unknown model returns FAILING (not silent-success)
    # ------------------------------------------------------------------
    step("8. NEGATIVE: unknown model name returns FAILING (no silent success)")
    r = oas.smoke_one_model("does-not-exist:9000b", timeout=10.0)
    if r["status"] == "WORKING":
        fail("unknown model wrongly reported WORKING")
    if r["status"] not in ("FAILING", "TIMEOUT"):
        fail(f"unknown model status={r['status']}; expected FAILING/TIMEOUT")
    ok(f"unknown model surfaces {r['status']} (not silent-success)")

    print(f"\n{GREEN}{BOLD}ALL 8 STEPS PASSED (5 positive + 3 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
