# RESOURCES: readonly
"""
Drill: ADR-025 feature-flag-gated dual-write pattern documentation.

Per CLAUDE.md §43 (drill discipline) + §47.3 (ADR rules: immutable
once accepted; PR description must link the ADR(s)). Iter 11/12/13
shipped 3 dual-writes using the SAME pattern; ADR-025 (iter 17)
documents the locked decision so future maintainers understand why
the env-flag opt-in pattern exists across all 3 surfaces.

Locks (positive):
  L1. ADR file exists at the canonical path
  L2. Status section says "Accepted"
  L3. References the 3 migrate-phase commits (iters 11, 12, 13)
  L4. References the 4 dual-write drills
  L5. Documents the 3 env flag names
  L6. Documents Alternatives Considered (≥2)
  L7. Documents Consequences (positive + negative + risks)

Locks (negative — ≥3 per §43):
  N1. ADR file is NOT empty (non-trivial content)
  N2. ADR doesn't accidentally drop the §47.7 reference (the
      pattern's grounding in the framework would be missing)
  N3. ADR doesn't claim a flag default of "1" (would silently
      enable dual-writes in fresh deploys, violating the
      operator-opt-in invariant)
  N4. ADR mentions the operator-side activation steps (without
      them, this is just an ivory-tower decision document)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "architecture" / "adr" / "025-feature-flag-gated-dual-write.md"

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
    # ===================================================================
    # Step 1 — file exists
    # ===================================================================
    step("1. ADR-025 file exists at the canonical path")
    if not ADR.exists():
        fail(f"missing: {ADR.relative_to(REPO)}")
    if ADR.stat().st_size < 1000:
        fail(f"ADR file too small ({ADR.stat().st_size}B); content missing")
    ok(f"ADR-025 exists ({ADR.stat().st_size}B)")

    text = ADR.read_text(encoding="utf-8")

    # ===================================================================
    # Step 2 — Status: Accepted
    # ===================================================================
    step("2. Status section says 'Accepted'")
    if "## Status" not in text:
        fail("missing '## Status' section")
    # Status must say Accepted (not Proposed / Draft / Superseded)
    status_idx = text.index("## Status")
    next_section_idx = text.find("##", status_idx + len("## Status"))
    status_block = text[status_idx:next_section_idx] if next_section_idx > 0 else text[status_idx:]
    if "Accepted" not in status_block:
        fail(f"status block must say Accepted; got: {status_block[:200]}")
    ok("status: Accepted")

    # ===================================================================
    # Step 3 — References the 3 migrate-phase commits
    # ===================================================================
    step("3. References the 3 migrate-phase commits (iters 11, 12, 13)")
    expected_commits = ("7c404e1", "1fc1b0b", "c23d142")
    missing = [c for c in expected_commits if c not in text]
    if missing:
        fail(f"missing commit refs: {missing}")
    ok(f"all 3 migrate commits referenced: {expected_commits}")

    # ===================================================================
    # Step 4 — References all 4 dual-write drills
    # ===================================================================
    step("4. References the 4 dual-write drills")
    expected_drills = (
        "drill_mcp_gateway_dual_write",
        "drill_ops_worker_dual_write",
        "drill_tools_catalog_sync",
        "drill_migrate_phase_status",
    )
    missing = [d for d in expected_drills if d not in text]
    if missing:
        fail(f"missing drill refs: {missing}")
    ok("all 4 drills referenced")

    # ===================================================================
    # Step 5 — Documents the 3 env flag names
    # ===================================================================
    step("5. Documents the 3 env flag names")
    expected_flags = (
        "MCP_GATEWAY_SQL_AUDIT_ENABLED",
        "OPS_WORKER_SQL_ENABLED",
        "MCP_TOOLS_SYNC_ENABLED",
    )
    missing = [f for f in expected_flags if f not in text]
    if missing:
        fail(f"missing env flag names: {missing}")
    ok("all 3 env flags documented")

    # ===================================================================
    # Step 6 — Alternatives Considered (≥2)
    # ===================================================================
    step("6. Alternatives Considered (≥2 alternatives required by §47.3)")
    if "## Alternatives" not in text:
        fail("missing '## Alternatives' section")
    alt_count = text.count("### A")
    if alt_count < 2:
        fail(f"fewer than 2 alternatives considered (got {alt_count})")
    ok(f"{alt_count} alternatives considered")

    # ===================================================================
    # Step 7 — Consequences: positive + negative + risks
    # ===================================================================
    step("7. Consequences section has positive + negative + risks")
    for header in ("### Positive", "### Negative", "### Risks accepted"):
        if header not in text:
            fail(f"missing consequences subsection: {header}")
    ok("consequences: positive + negative + risks all present")

    # ===================================================================
    # Step 8 — NEGATIVE: §47.7 reference is present
    # ===================================================================
    step("8. NEGATIVE: §47.7 reference present (grounding in framework)")
    if "§47.7" not in text:
        fail("ADR doesn't cite §47.7 — pattern's grounding missing")
    ok("§47.7 referenced; pattern grounded in CLAUDE.md framework")

    # ===================================================================
    # Step 9 — NEGATIVE: no claim of default=1
    # ===================================================================
    step("9. NEGATIVE: ADR doesn't claim default=1 (would auto-enable)")
    # Look for anything resembling "default 1" or "default: 1" in the
    # decision section. We expect "default 0" or "default `0` (off)".
    bad_patterns = ("default `1`", 'default "1"', "default 1 (")
    leaks = [p for p in bad_patterns if p in text.lower()]
    if leaks:
        fail(f"ADR claims default=1: {leaks} — would silently enable on deploy")
    if "default `0`" not in text.lower() and "default `0` (off)" not in text.lower():
        fail("ADR should explicitly state default=0 (off) for clarity")
    ok("ADR explicitly documents default=0; no rogue default=1 leaks")

    # ===================================================================
    # Step 10 — NEGATIVE: operator-side activation steps documented
    # ===================================================================
    step("10. NEGATIVE: operator-side activation steps present")
    if "Operator-side activation" not in text and "operator-side" not in text.lower():
        fail("ADR missing operator-side activation guidance — would make this "
             "an ivory-tower decision document")
    if "export " not in text:
        fail("ADR missing concrete activation example (export FLAG=1)")
    ok("operator-side activation steps documented with concrete example")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
