#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-7 GEPA canary wire into rag_inference.ask.

Locks the runtime call site that consumes select_canary_version
(commit 4f7289e). Without this wire, the helper sits unused; with it,
GEPA_CANARY_ENABLED=1 + GEPA_CANARY_PERCENT > 0 can actually route
real traffic.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAG = REPO / "services" / "inference-svc" / "app" / "services" / "rag_inference.py"
PROMPT_REPO = REPO / "services" / "inference-svc" / "app" / "services" / "prompt_repo.py"


def main() -> int:
    print("-- 1. POSITIVE: rag_inference.ask calls select_canary_version --")
    if not RAG.exists():
        print(f"x {RAG} missing")
        return 1
    src = RAG.read_text(encoding="utf-8")
    if "select_canary_version" not in src:
        print("x rag_inference must call select_canary_version")
        return 1
    if "self._prompts.select_canary_version(" not in src:
        print("x must call helper via self._prompts (the builder instance)")
        return 1
    print("  ok: select_canary_version invocation present")

    print("-- 2. NEGATIVE: wire is INSIDE ask() (not module-level) --")
    tree = ast.parse(src)
    # Find ask method; verify the canary call is inside its body
    ask_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ask":
            ask_fn = node
            break
    if ask_fn is None:
        print("x async def ask not found")
        return 1
    ask_src = ast.unparse(ask_fn)
    if "select_canary_version" not in ask_src:
        print("x select_canary_version must be called inside ask() body")
        return 1
    print("  ok: wire is inside ask() body")

    print("-- 3. NEGATIVE: hasattr guard for legacy builders without helper --")
    # Some builder classes (in-code PromptBuilder, test fixtures) may
    # not have select_canary_version. Drill enforces hasattr() guard
    # so the wire degrades gracefully on legacy builders.
    if 'hasattr(self._prompts, "select_canary_version")' not in src:
        print("x must guard helper call with hasattr() (legacy builder fallback)")
        return 1
    print("  ok: hasattr guard preserves legacy-builder compat")

    print("-- 4. NEGATIVE: §47 fail-safe — helper errors fall back to baseline --")
    # The wire MUST wrap the helper call in try/except. If the helper
    # raises (shouldn't, but defense-in-depth), effective_template
    # falls back to self._default_prompt — request path NEVER blocks.
    # Find the canary block specifically.
    block_idx = src.find("Stage-7 GEPA canary routing")
    if block_idx < 0:
        print("x canary block marker missing")
        return 1
    block_end = src.find("system, user, citation_map = self._prompts.build(", block_idx)
    block = src[block_idx:block_end]
    if "try:" not in block:
        print("x wire must wrap helper call in try/except")
        return 1
    if "except Exception" not in block:
        print("x must catch generic Exception (fail-safe)")
        return 1
    if "effective_template = self._default_prompt" not in block:
        print("x except path must set effective_template = self._default_prompt (fail-safe)")
        return 1
    print("  ok: §47 fail-safe — canary errors don't block request")

    print("-- 5. NEGATIVE: build() consumes effective_template (NOT self._default_prompt) --")
    # If the build call still passes self._default_prompt, the canary
    # has no effect. Drill enforces effective_template threading.
    build_idx = src.find("system, user, citation_map = self._prompts.build(", block_idx)
    build_end = src.find(")", build_idx + 50)
    build_call = src[build_idx:build_end + 1]
    if "template_name=effective_template" not in build_call:
        print("x build() must consume effective_template (canary thread)")
        return 1
    if "template_name=self._default_prompt" in build_call:
        print("x build() must NOT pass self._default_prompt (defeats canary)")
        return 1
    print("  ok: build() reads effective_template after canary resolution")

    print("-- 6. POSITIVE: §48 explainability — trace.step records cohort --")
    # The canary cohort assignment is per-request. §48 explainability
    # requires the trace row carry which version fired so post-hoc
    # eval can attribute quality to the right cohort.
    if 'trace.step("prompt_canary_routing")' not in src:
        print("x must emit trace.step('prompt_canary_routing') for §48 explainability")
        return 1
    if "cohort=cohort" not in src and 'st.meta(cohort=' not in src:
        print("x trace step must record cohort metadata")
        return 1
    print("  ok: trace step records cohort (canary | baseline)")

    print("-- 7. POSITIVE: ast-valid + cohort label distinguishes both states --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x syntax error after Stage-7 wire: {exc}")
        return 1
    # Cohort labeling must distinguish baseline vs gepa
    if '"gepa" if effective_template != self._default_prompt' not in src:
        print("x cohort label must be 'gepa' iff effective != baseline")
        return 1
    if '"baseline"' not in src or '"gepa"' not in src:
        print("x cohort labels must include both 'baseline' and 'gepa'")
        return 1
    print("  ok: ast-valid; cohort label baseline-vs-gepa distinguishable")

    print("-- 8. NEGATIVE: prompt_repo.py UNCHANGED (no reverse import) --")
    # The Stage-7 wire is INTO inference-svc; the helper module must
    # NOT have grown an import of inference-svc (cycle prevention).
    repo_src = PROMPT_REPO.read_text(encoding="utf-8")
    if "from app.services.rag_inference" in repo_src:
        print("x prompt_repo must NOT import rag_inference (cycle risk)")
        return 1
    if "import rag_inference" in repo_src:
        print("x prompt_repo must NOT import rag_inference (cycle risk)")
        return 1
    print("  ok: prompt_repo source clean; no cycle introduced")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
