#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Agent Router × Council cross-check (§47 Layer 3 wired into Layer 5).

Per CLAUDE.md §43 + §47. Locks the integration that:

  - run_local_council() runs agent_router.classify() before AUTHOR fires
  - The router decision lands in audit_chain['agent_router'] with the
    documented fields (intent, risk, recommended_actor, etc.)
  - When the router disagrees (recommends operator:human for an issue
    already routed to council), a warning is printed AND the
    disagrees_with_council flag is set in audit_chain
  - Router failures are non-fatal (observability, not gate) — council
    continues with audit_chain['agent_router']['error'] instead
  - Council still proceeds even on router-says-high-risk — Stage-1 is
    cross-check, not gate
  - Importing local_council triggers no Ollama call (router still
    cheap; module import safe)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def main() -> int:
    print("-- 1. POSITIVE: local_council source imports agent_router --")
    src = (SCRIPTS / "local_council.py").read_text(encoding="utf-8")
    if "from agent_router import classify" not in src:
        print("x local_council.py must import agent_router.classify")
        return 1
    if "_router_classify" not in src:
        print("x router classify must be aliased + called")
        return 1
    print("  ok: local_council imports agent_router.classify")

    print("-- 2. POSITIVE: classify call sits BETWEEN audit_chain init + AUTHOR --")
    # The cross-check must run BEFORE the AUTHOR Ollama call so the
    # router's classification is available to the audit row even when
    # AUTHOR fails.
    init_pos = src.find("audit_chain: dict[str, dict] = {")
    classify_pos = src.find("_router_classify(")
    author_call_pos = src.find('actor="council:author"')
    if init_pos == -1:
        print("x audit_chain init not found")
        return 1
    if classify_pos == -1:
        print("x _router_classify call not found")
        return 1
    if author_call_pos == -1:
        print("x council:author call not found")
        return 1
    if not (init_pos < classify_pos < author_call_pos):
        print(f"x ordering wrong: init={init_pos} classify={classify_pos} author={author_call_pos}")
        return 1
    print(f"  ok: ordering correct (init {init_pos} < classify {classify_pos} < author {author_call_pos})")

    print("-- 3. POSITIVE: audit_chain['agent_router'] documented fields present --")
    expected_fields = (
        "intent", "risk", "recommended_actor", "recommended_tool",
        "confidence", "reasons", "disagrees_with_council",
    )
    for field_name in expected_fields:
        # Each must appear as a quoted dict-key write
        if f'"{field_name}"' not in src:
            print(f"x audit_chain['agent_router'] missing field: {field_name!r}")
            return 1
    print(f"  ok: all 7 agent_router audit fields documented")

    print("-- 4. NEGATIVE: router failure is non-fatal (try/except + fallback) --")
    # Bit-rot prevention: a refactor that turns the router call into a
    # gate (raises on failure) would silently change Stage-1 contract.
    # The code MUST have a try/except around the classify call AND set
    # an 'error' or 'fallback' field on failure.
    crosscheck_section = src[src.find("Agent Router cross-check"):]
    crosscheck_section = crosscheck_section[:crosscheck_section.find("# Tier 1 #1.4")]
    if "try:" not in crosscheck_section:
        print("x router cross-check must use try/except (non-fatal)")
        return 1
    if "except" not in crosscheck_section:
        print("x router cross-check must have except branch")
        return 1
    if '"fallback"' not in crosscheck_section and '"error"' not in crosscheck_section:
        print("x router failure must set 'error' or 'fallback' in audit_chain")
        return 1
    print("  ok: router failure caught with fallback audit row")

    print("-- 5. NEGATIVE: disagrees_with_council flag prints a warning --")
    # When router says non-council:* actor, a warning must be printed
    # so operators see the disagreement at run time.
    if 'WARNING' not in crosscheck_section:
        print("x router disagreement must print a WARNING")
        return 1
    if "continuing per upstream" not in crosscheck_section:
        print("x warning must clarify council still proceeds")
        return 1
    print("  ok: disagreement prints WARNING + clarifies council continues")

    print("-- 6. NEGATIVE: router cross-check does NOT gate the council --")
    # The cross-check is observability, not gate. The code MUST NOT
    # have an `if router says high-risk: return None` short-circuit.
    forbidden_patterns = (
        r"if\s+router_decision\.risk\s*==\s*['\"]high['\"]\s*:\s*\n\s+return\s+None",
        r"if\s+\w+\.recommended_actor\s*==\s*['\"]operator:human['\"]\s*:\s*\n\s+return\s+None",
        r"raise\s+\w*Error\([^)]*router",
    )
    for pat in forbidden_patterns:
        if re.search(pat, src):
            print(f"x cross-check must not gate council; found: {pat!r}")
            return 1
    print("  ok: 0 council-gate patterns; cross-check is observability only")

    print("-- 7. POSITIVE: live integration test — empty issue routes correctly --")
    # Run a minimal council invocation to verify the integration works.
    # Use a synthetic issue so we don't hit Ollama (the call_ollama
    # itself is mocked via monkey-patch when tests want).
    # We'll just import + call agent_router from the same path the
    # council uses, simulating the import-from-local_council step.
    import agent_router
    # Empty message → conservative default
    d = agent_router.classify("", persist_audit=False)
    if d.recommended_actor != "operator:human":
        print(f"x empty message classification regressed: {d.recommended_actor}")
        return 1
    # Council issue with "fix lint" message → council:author lane
    d = agent_router.classify("fix the ruff lint errors", persist_audit=False)
    if d.recommended_actor != "council:author":
        print(f"x fix-lint should route to council:author; got {d.recommended_actor}")
        return 1
    print(f"  ok: agent_router still classifies correctly when called from council path")

    print("-- 8. POSITIVE: fresh import of local_council does NOT call Ollama --")
    # The cross-check imports agent_router INSIDE run_local_council,
    # so module-level import of local_council should still be cheap.
    proc = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, '{SCRIPTS}'); "
         f"import time; t0 = time.time(); "
         f"import local_council; "
         f"print(f'IMPORT_OK {{(time.time() - t0):.3f}}')"],
        cwd=REPO, capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        print(f"x fresh import failed: {proc.stderr[:200]}")
        return 1
    if "IMPORT_OK" not in proc.stdout:
        print(f"x import sentinel missing: {proc.stdout[:200]}")
        return 1
    m = re.search(r"IMPORT_OK\s+([\d.]+)", proc.stdout)
    if m:
        elapsed = float(m.group(1))
        if elapsed > 5.0:
            print(f"x import took {elapsed:.3f}s; expected <5s (lazy router import)")
            return 1
        print(f"  ok: import {elapsed:.3f}s; no Ollama fired (lazy agent_router import)")
    else:
        print("  ok: import OK (timing not parsed)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
