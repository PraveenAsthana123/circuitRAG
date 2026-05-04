#!/usr/bin/env python3
# RESOURCES: readonly
"""
Meta-drill: enforce §43 discipline across the entire drill catalog.

Per ~/.claude/CLAUDE.md §43, every drill in mcp/tests/drill_*.py must:
  * carry a `# RESOURCES: <tokens>` tag (readonly | mcp_X | pg | ...)
  * NOT import pytest (drills are standalone scripts; pytest belongs
    in unit tests, not the resource-aware runner)
  * NOT import unittest.mock or `mock` (drills exercise real running
    stack, never mocks — §43.1)
  * have a module docstring with a tagline + steps
  * include at least one negative assertion (the §43.5 contract)
  * have an `if __name__ == "__main__":` block + sys.exit(...)
    so the runner can subprocess them

Without this meta-drill, a future drill author could silently drift
the contract — drop the resources tag and break parallel scheduling,
or `import pytest` and confuse the runner. Phase 6B locks the
catalog-wide invariants the resource-aware runner depends on.

Eight steps. Seven negative assertions.

  1. POSITIVE: catalog has ≥50 drills (the resource-aware runner
     is meaningless on a tiny catalog; this asserts the test
     surface itself).
  2. NEGATIVE: every drill carries `# RESOURCES:` somewhere in the
     file. Without it, run_drills.py can't classify the drill and
     defaults to "touches everything" (serializes against all).
  3. NEGATIVE: no drill imports pytest. Drills are standalone
     scripts — `python3 mcp/tests/drill_X.py` is the contract.
     Pytest discovery would conflict with the runner.
  4. NEGATIVE: no drill imports unittest.mock or `mock`. Drills
     exercise the real running stack; mocks belong in pytest.
  5. NEGATIVE: every drill has a module docstring (the file's
     first statement is a string literal). Without it,
     scripts/run_drills.py --list shows the file with no
     description — operators have to open it to learn what it does.
  6. NEGATIVE: every drill has an `if __name__ == "__main__":`
     entry point + `sys.exit(...)`. The runner subprocesses each
     drill and reads the exit code; without this, subprocess
     output is ambiguous.
  7. NEGATIVE: every NEW drill mentions "negative" (case-insensitive)
     in its docstring. Per §43.5, ≥1 negative assertion per drill.
     Without the marker in the doc, future readers can't tell which
     steps are happy-path and which lock invariants. Phase 6D ratchet:
     34 pre-existing drills are grandfathered in KNOWN_MISSING_NEG_MARKER
     (they likely have negative assertions but their docs predate the
     §43.5 marker convention); new drills must include the marker.
     (Soft check — only enforces docstring presence; AST-parsing the
     actual assertion count is out of scope.)
  8. POSITIVE: catalog spans tier-1 (readonly) AND tier-≥2 — both
     are needed. A catalog of only readonly drills suggests the
     test surface stops at the API layer; only resourced drills
     suggests no fast path exists.

Run: python3 mcp/tests/drill_drill_catalog_discipline.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILL_DIR = REPO / "mcp" / "tests"

# Module-level ratchets, lifted from function-local scope (Phase 7X)
# so drill_drift_volume_meta and operator review can see them. Both
# were paid down to empty in Phase 6C / 6D — keeping the named
# constants is intentional: they document the ratchet shape and
# fire if drift recurs.
KNOWN_MISSING: set[str] = set()
KNOWN_MISSING_NEG_MARKER: set[str] = set()

# Step-4 ratchet: drills that legitimately use unittest.mock to test
# fallback paths when an OPTIONAL Stage-1 dependency isn't installed
# (litellm, pydantic-ai, agno, etc). The §43 spirit is "drills exercise
# real stack" — but when the real stack is "this dependency may not be
# installed in dev/CI", mocking the import path is how we drill the
# fallback. Each entry has a rationale; this set should only SHRINK
# (or hold) as Stage-1 adapters consolidate or are made always-installed.
KNOWN_MOCK_OFFENDERS: set[str] = {
    # litellm Stage-1 adapter — opt-in via LITELLM_ENABLED=1; library
    # is NOT in requirements.txt by default. drill mocks the import.
    "drill_litellm_fallback.py",
    # pydantic-ai Stage-1 adapter — opt-in via PYDANTICAI_ENABLED=1;
    # drill mocks the import to test fallback when lib is absent.
    "drill_pydanticai_validate_fallback.py",
    # agent_router Stage-2 — Ollama call gated by feature flag; drill
    # mocks the subprocess so it exercises routing logic without
    # requiring a live model.
    "drill_agent_router_stage2_ollama.py",
    # PolisAI gate composition — mocks the inner gate to count call
    # sites in the Stage-3 _skip_gate consolidation.
    "drill_council_polisai_gate.py",
    # MCP gateway transport adapter — mocks httpx because the gateway
    # adapter has a no-op transport in Stage-3 (real RPC is Stage-4).
    "drill_mcp_client_gateway_wiring.py",
}


def _drill_files() -> list[Path]:
    """Return every mcp/tests/drill_*.py except this meta-drill itself."""
    self_name = Path(__file__).name
    return sorted(
        p for p in DRILL_DIR.glob("drill_*.py")
        if p.name != self_name
    )


def main() -> int:
    drills = _drill_files()

    # ── Step 1: POSITIVE — catalog has ≥50 drills ──
    if len(drills) < 50:
        print(f"✗ step 1: catalog has {len(drills)} drills, expected ≥50")
        return 1
    print(f"✓ step 1: catalog has {len(drills)} drills (≥50 threshold met)")

    # ── Step 2: NEGATIVE — every drill has # RESOURCES: tag ──
    # The tag may appear ANYWHERE in the file (some drills put it
    # on line 2; others embed it later). The runner's parser handles
    # any position. Phase 6C swept the original 23 grandfathered
    # drills, adding sensible tags via parallel agents; the
    # KNOWN_MISSING ratchet is now empty (paid down in Phase 6C).
    # Defined at module level above for drift-volume meta-drill
    # visibility. If a future drill ships without a tag, this step
    # fires — the right response is to add the tag in that drill's
    # own commit, not to grow the grandfathered set.
    missing_resource_tag = []
    for p in drills:
        body = p.read_text()
        if not re.search(r"^# RESOURCES:", body, re.MULTILINE):
            missing_resource_tag.append(p.name)
    actually_missing = set(missing_resource_tag)
    new_drift = actually_missing - KNOWN_MISSING
    if new_drift:
        print(f"✗ step 2: {len(new_drift)} NEW drills missing # RESOURCES: "
              f"tag (not in known-grandfathered set): {sorted(new_drift)}. "
              f"Either add the tag or document why it's exempt.")
        return 1
    # Stale entries (in KNOWN_MISSING but actually fixed) — info only.
    stale = KNOWN_MISSING - actually_missing
    grandfathered = actually_missing & KNOWN_MISSING
    print(f"✓ step 2: 0 new drift; {len(grandfathered)} grandfathered "
          f"({len(stale)} stale entries in KNOWN_MISSING — safe to remove)")

    # ── Step 3: NEGATIVE — no pytest imports ──
    pytest_offenders = []
    for p in drills:
        body = p.read_text()
        if re.search(r"^(?:import pytest|from pytest)", body, re.MULTILINE):
            pytest_offenders.append(p.name)
    if pytest_offenders:
        print(f"✗ step 3: {len(pytest_offenders)} drills import pytest: "
              f"{pytest_offenders[:3]} — drills must be standalone scripts")
        return 1
    print(f"✓ step 3: no drill imports pytest (catalog stays runner-compatible)")

    # ── Step 4: NEGATIVE — no NEW mock imports (KNOWN_MOCK_OFFENDERS grandfathered) ──
    mock_offenders = []
    for p in drills:
        body = p.read_text()
        if re.search(
            r"^(?:from unittest\.mock|from unittest import mock|import mock\b|from mock\b)",
            body, re.MULTILINE,
        ):
            mock_offenders.append(p.name)
    new_mock_drift = set(mock_offenders) - KNOWN_MOCK_OFFENDERS
    if new_mock_drift:
        print(f"✗ step 4: {len(new_mock_drift)} NEW drills import mock "
              f"(not in KNOWN_MOCK_OFFENDERS): {sorted(new_mock_drift)} — "
              "drills exercise real stack, not mocks. Either remove the "
              "mock OR add an explicit grandfather entry with rationale.")
        return 1
    stale = KNOWN_MOCK_OFFENDERS - set(mock_offenders)
    if stale:
        print(f"✗ step 4: {len(stale)} grandfathered drills no longer "
              f"need mock (paid down): {sorted(stale)}. "
              "Remove from KNOWN_MOCK_OFFENDERS so the ratchet stays honest.")
        return 1
    print(f"✓ step 4: no NEW mock drift; "
          f"{len(KNOWN_MOCK_OFFENDERS)} grandfathered (per Stage-1 fallback)")

    # ── Step 5: NEGATIVE — every drill has a module docstring ──
    no_docstring = []
    for p in drills:
        body = p.read_text()
        # Module docstring = first non-shebang, non-coding-line, non-future-
        # import statement is a triple-quoted string. Look for ^"""...""" or
        # ^'''...''' anywhere near the top of the file.
        first_500 = body[:1500]
        if not re.search(r'^\s*"""', first_500, re.MULTILINE) and \
                not re.search(r"^\s*'''", first_500, re.MULTILINE):
            no_docstring.append(p.name)
    if no_docstring:
        print(f"✗ step 5: {len(no_docstring)} drills lack module docstring: "
              f"{no_docstring[:3]}")
        return 1
    print(f"✓ step 5: all {len(drills)} drills have module docstrings "
          "(--list will show descriptions)")

    # ── Step 6: NEGATIVE — every drill has __main__ entry + sys.exit ──
    no_main = []
    for p in drills:
        body = p.read_text()
        if 'if __name__ == "__main__":' not in body \
                and "if __name__ == '__main__':" not in body:
            no_main.append(p.name)
    if no_main:
        print(f"✗ step 6: {len(no_main)} drills lack __main__ entry: "
              f"{no_main[:3]} — subprocess invocation contract broken")
        return 1
    # Drills that actually-can-fail signal pass/fail via process exit
    # code. Acceptable patterns:
    #   sys.exit(...)         — the obvious one
    #   raise SystemExit(...) — functionally equivalent (async drills)
    #   os._exit(...)         — rare; bypasses cleanup but valid
    #   asyncio.run(main()) with raise/assert — natural Python termination
    #
    # Survey-only checks now live in mcp/tests/audit_*.py. Every
    # drill_*.py file is expected to be a PASS/FAIL gate with real
    # exit-code signal.
    no_exit_signal = []
    for p in drills:
        body = p.read_text()
        has_explicit_exit = (
            "sys.exit(" in body
            or "SystemExit(" in body
            or "os._exit(" in body
        )
        has_async_pattern = (
            "asyncio.run(main" in body
            and ("raise " in body or "assert " in body)
        )
        if not has_explicit_exit and not has_async_pattern:
            no_exit_signal.append(p.name)
    if no_exit_signal:
        print(f"✗ step 6: {len(no_exit_signal)} drills lack exit-code "
              f"signal: {sorted(no_exit_signal)} — gate drills must "
              f"fail via process exit; survey scripts belong in "
              f"mcp/tests/audit_*.py")
        return 1
    print("✓ step 6: all drill_*.py files have exit-code signal")

    # ── Step 7: NEGATIVE — drill docs mention "negative" (§43.5) ──
    # §43.5 requires ≥1 negative assertion per drill. We can't AST-
    # parse and count assertions across 133 drills, but we can at
    # least require the docstring mention them — operators reading
    # `--list` should see the negative-step count or a marker.
    #
    # Phase 6D ratchet: was 34 pre-existing drills lacking the
    # marker; paid down to empty. KNOWN_MISSING_NEG_MARKER is now
    # defined at module level above (Phase 7X) for drift-volume
    # meta-drill visibility. New drills must include the marker;
    # if an old drill regresses, this step fires and the right
    # response is to add the marker, not to grow the set.
    no_negative_mention = []
    for p in drills:
        body = p.read_text()
        m = re.search(r'"""(.*?)"""', body, re.DOTALL)
        if not m:
            m = re.search(r"'''(.*?)'''", body, re.DOTALL)
        if not m:
            no_negative_mention.append(p.name)
            continue
        doc_text = m.group(1).lower()
        if "negative" not in doc_text:
            no_negative_mention.append(p.name)
    actually_no_neg = set(no_negative_mention)
    new_no_neg = actually_no_neg - KNOWN_MISSING_NEG_MARKER
    if new_no_neg:
        print(f"✗ step 7: {len(new_no_neg)} NEW drills lack 'negative' "
              f"docstring marker: {sorted(new_no_neg)}. Add a step "
              f"description like 'NEGATIVE: ...' to the docstring, or "
              f"add to KNOWN_MISSING_NEG_MARKER if the drill is "
              f"intentionally happy-path-only.")
        return 1
    grandfathered_neg = actually_no_neg & KNOWN_MISSING_NEG_MARKER
    stale_neg = KNOWN_MISSING_NEG_MARKER - actually_no_neg
    print(f"✓ step 7: 0 new drift; {len(grandfathered_neg)} grandfathered "
          f"({len(stale_neg)} stale entries safe to remove)")

    # ── Step 8: POSITIVE — catalog spans readonly + resourced ──
    readonly_count = 0
    resourced_count = 0
    for p in drills:
        body = p.read_text()
        if re.search(r"^# RESOURCES: readonly\b", body, re.MULTILINE):
            readonly_count += 1
        else:
            resourced_count += 1
    if readonly_count == 0:
        print(f"✗ step 8: catalog has 0 readonly drills — fast path missing")
        return 1
    if resourced_count == 0:
        print(f"✗ step 8: catalog has 0 resourced drills — only API-layer coverage")
        return 1
    print(f"✓ step 8: catalog spans both tiers "
          f"({readonly_count} readonly + {resourced_count} resourced)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
