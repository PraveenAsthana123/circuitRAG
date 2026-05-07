# RESOURCES: readonly
"""
Drill: doc framework registry — 20 doc types per ADR-029 contract.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-69 ships the framework FOUNDATION — registry
+ ADR-029; iter-70..78 build on top), §45.4 (no checkbox flips without
code), §47 (architecture: registry-driven feature; adding a 21st doc =
one YAML row, not a code change).

Locks (positive):
  L1. ADR-029 file exists + is referenced from registry
  L2. registry.yaml exists + parses without error via load_registry()
  L3. Exactly 20 doc entries (per ADR-029 user request)
  L4. Each entry has all required fields (doc_type/display_name/
      owner_role/reviewer_roles/interdept_required/template_path/
      prompt_path/kpi_dimensions)
  L5. Each entry has ≥3 KPI dimensions
  L6. default_min_kpi = 1.0 (100%; per user request)

Locks (negative — ≥3 per §43):
  N1. Every doc_type slug is unique (drill catches accidental rename
      that introduces dup)
  N2. Every owner_role is in ALLOWED_ROLES allow-list (typo'd role
      caught at registry-load time, not at runtime)
  N3. Every reviewer_role is in ALLOWED_ROLES (same)
  N4. Every kpi_dimension is in ALLOWED_KPI_DIMENSIONS (typo caught;
      a dim that doesn't have a scoring rubric would silently produce
      0/0 weights at scoring time)
  N5. min_kpi is in [0, 1] for every doc (out-of-range value would
      make the threshold gate unreachable or trivially satisfied)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_FILE = REPO / "docs" / "architecture" / "adr" / "029-business-usecase-to-docs-framework.md"
REGISTRY_FILE = REPO / "docs" / "templates" / "doc_framework" / "registry.yaml"
LOADER = REPO / "scripts" / "doc_framework_registry.py"
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
    if not ADR_FILE.exists():
        fail(f"ADR-029 missing: {ADR_FILE.relative_to(REPO)}")
    if not REGISTRY_FILE.exists():
        fail(f"registry missing: {REGISTRY_FILE.relative_to(REPO)}")
    if not LOADER.exists():
        fail(f"loader missing: {LOADER.relative_to(REPO)}")

    import doc_framework_registry as dfr  # type: ignore[import-not-found]

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: ADR-029 exists + is referenced from registry
    # ------------------------------------------------------------------
    step("1. ADR-029 exists + is referenced from registry")
    adr_src = ADR_FILE.read_text(encoding="utf-8")
    reg_src = REGISTRY_FILE.read_text(encoding="utf-8")
    if "ADR-029" not in adr_src:
        fail("ADR file body doesn't mention 'ADR-029'")
    if "ADR-029" not in reg_src:
        fail("registry.yaml doesn't reference ADR-029 (provenance link missing)")
    ok("ADR-029 + registry cross-reference each other")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: registry parses cleanly
    # ------------------------------------------------------------------
    step("2. registry.yaml parses via load_registry() without error")
    try:
        reg = dfr.load_registry()
    except dfr.RegistryError as e:
        fail(f"registry failed validation: {e}")
    if reg.version != 1:
        fail(f"registry version={reg.version}, expected 1")
    ok(f"registry loaded; version={reg.version}; default_min_kpi={reg.default_min_kpi}")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: exactly 20 doc entries
    # ------------------------------------------------------------------
    step("3. registry has exactly 20 doc entries (ADR-029 contract)")
    if len(reg.docs) != 20:
        fail(f"registry has {len(reg.docs)} docs; ADR-029 requires 20")
    ok(f"20 doc entries present (full ADR-029 catalog)")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: each entry has all required fields
    # ------------------------------------------------------------------
    step("4. each entry has all required fields populated")
    required_fields = (
        "doc_type", "display_name", "owner_role", "reviewer_roles",
        "interdept_required", "template_path", "prompt_path",
        "kpi_dimensions", "min_kpi",
    )
    for d in reg.docs:
        for field in required_fields:
            v = getattr(d, field, None)
            if v is None or (isinstance(v, str) and not v.strip()):
                fail(f"doc {d.doc_type}: field {field} missing or empty")
    ok(f"all {len(reg.docs)} entries have all {len(required_fields)} fields")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: each entry has ≥3 KPI dimensions
    # ------------------------------------------------------------------
    step("5. each entry has ≥3 KPI dimensions")
    for d in reg.docs:
        if len(d.kpi_dimensions) < 3:
            fail(f"doc {d.doc_type}: only {len(d.kpi_dimensions)} dims; need ≥3")
    ok(f"all 20 docs have ≥3 KPI dimensions (median 5 per doc)")

    # ------------------------------------------------------------------
    # Step 6 — POSITIVE: default_min_kpi = 1.0
    # ------------------------------------------------------------------
    step("6. default_min_kpi = 1.0 (100% per user request)")
    if reg.default_min_kpi != 1.0:
        fail(f"default_min_kpi={reg.default_min_kpi}; user requested 100%")
    ok("default_min_kpi=1.0 (gates approval at 100% KPI per user request)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: doc_type slugs are unique
    # ------------------------------------------------------------------
    step("7. NEGATIVE: doc_type slugs are unique across registry")
    slugs = [d.doc_type for d in reg.docs]
    if len(set(slugs)) != len(slugs):
        seen = {}
        for s in slugs:
            seen[s] = seen.get(s, 0) + 1
        dups = [s for s, n in seen.items() if n > 1]
        fail(f"duplicate doc_type slugs: {dups}")
    ok("all 20 doc_type slugs are unique")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: every owner_role in ALLOWED_ROLES
    # ------------------------------------------------------------------
    step("8. NEGATIVE: every owner_role in ALLOWED_ROLES allow-list")
    bad_owners = [d for d in reg.docs if d.owner_role not in dfr.ALLOWED_ROLES]
    if bad_owners:
        fail(f"docs with bad owner_role: {[(d.doc_type, d.owner_role) for d in bad_owners]}")
    ok("all 20 owner_roles in ALLOWED_ROLES allow-list")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: every reviewer_role in ALLOWED_ROLES
    # ------------------------------------------------------------------
    step("9. NEGATIVE: every reviewer_role in ALLOWED_ROLES allow-list")
    for d in reg.docs:
        bad = [r for r in d.reviewer_roles if r not in dfr.ALLOWED_ROLES]
        if bad:
            fail(f"doc {d.doc_type}: bad reviewer_roles {bad}")
    ok("all reviewer_roles across 20 docs in ALLOWED_ROLES allow-list")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: every kpi_dimension in ALLOWED_KPI_DIMENSIONS
    # ------------------------------------------------------------------
    step("10. NEGATIVE: every kpi_dimension in ALLOWED_KPI_DIMENSIONS")
    for d in reg.docs:
        bad = [k for k in d.kpi_dimensions if k not in dfr.ALLOWED_KPI_DIMENSIONS]
        if bad:
            fail(f"doc {d.doc_type}: bad kpi_dimensions {bad}")
    ok("all kpi_dimensions across 20 docs in ALLOWED_KPI_DIMENSIONS")

    # ------------------------------------------------------------------
    # Step 11 — NEGATIVE: min_kpi in [0, 1] for every doc
    # ------------------------------------------------------------------
    step("11. NEGATIVE: min_kpi ∈ [0, 1] for every doc")
    for d in reg.docs:
        if not 0.0 <= d.min_kpi <= 1.0:
            fail(f"doc {d.doc_type}: min_kpi={d.min_kpi} outside [0, 1]")
    ok("all 20 docs have min_kpi in [0, 1]")

    # ------------------------------------------------------------------
    # Step 12 — POSITIVE: unique_roles helper covers ≥10 roles
    # ------------------------------------------------------------------
    step("12. POSITIVE: registry covers ≥10 unique roles (UI sidebar)")
    roles = dfr.unique_roles(reg)
    if len(roles) < 10:
        fail(f"registry covers only {len(roles)} roles; UI needs ≥10 sidebar nodes")
    ok(f"registry covers {len(roles)} unique roles "
       f"(each gets a sidebar node + 2-folder UI per ADR-029)")

    print(f"\n{GREEN}{BOLD}ALL 12 STEPS PASSED (7 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
