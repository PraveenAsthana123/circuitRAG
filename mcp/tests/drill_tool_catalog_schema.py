# RESOURCES: readonly
"""
Drill: tool catalog 9-axis schema (iter-74).

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-74 ships the catalog schema), §45.4 (no
checkbox flips without code), §47.6 (default-deny + DevSecOps),
§50.5.3 (read-only operator surface), §51 (forensic substrate).

User asked: "each tool must have fallback plan, input/process/output
plan, integration plan, testing plan, monitoring plan, visualization
plan on UI, integration with OpenTelemetry/Kibana, OPA/Rego,
observability log/trace/track."

iter-74 ships:
  - config/tool_catalog/README.md   (the 9-axis spec)
  - config/tool_catalog/<ns>.yaml   (4 starter entries — slack, github,
                                     documents, csv_ingest)
  - scripts/tool_catalog.py         (loader + validator)

This drill locks BOTH directions.

Locks (positive):
  L1. Catalog dir + README exist
  L2. ≥4 starter entries load + validate
  L3. validate_entry returns [] on a known-good entry
  L4. Loader rejects mismatched namespace/filename
  L5. Every entry's drill path (testing.drill) actually exists on disk
  L6. Every entry's opa_bundle path actually exists on disk

Locks (negative — ≥3 per §43):
  N1. Missing required axis → validate_entry surfaces error
  N2. policy.default != 'deny' → rejected (default-deny invariant)
  N3. io[].tool not prefixed with namespace → rejected
  N4. observability.otel.span_name not prefixed mcp.<ns>. → rejected
  N5. observability.log_fields missing request_id/tenant_id → rejected
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG_DIR = REPO / "config" / "tool_catalog"
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
    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: catalog dir + README exist
    # ------------------------------------------------------------------
    step("1. catalog dir + README + loader exist")
    if not CATALOG_DIR.is_dir():
        fail(f"missing dir: {CATALOG_DIR.relative_to(REPO)}")
    if not (CATALOG_DIR / "README.md").exists():
        fail("missing config/tool_catalog/README.md (the 9-axis spec)")
    if not (REPO / "scripts" / "tool_catalog.py").exists():
        fail("missing scripts/tool_catalog.py (the loader)")
    ok("dir + README + loader present")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: ≥4 starter entries load + validate
    # ------------------------------------------------------------------
    step("2. ≥4 starter entries load + validate")
    import tool_catalog as tc  # type: ignore[import-not-found]
    catalog = tc.load_catalog()
    if len(catalog) < 4:
        fail(f"catalog has {len(catalog)} entries; expected ≥4")
    ok(f"loaded {len(catalog)} entries: {sorted(catalog.keys())}")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: validate_entry returns [] on known-good
    # ------------------------------------------------------------------
    step("3. validate_entry returns [] on known-good entries")
    for ns, entry in catalog.items():
        errors = tc.validate_entry(entry.raw)
        if errors:
            fail(f"{ns}: validation failed: {errors}")
    ok("all 4 entries validate clean")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: Loader rejects mismatched ns/filename
    # ------------------------------------------------------------------
    step("4. loader rejects mismatched namespace vs. filename")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "slack.yaml"
        bad.write_text("namespace: not_slack\n", encoding="utf-8")
        try:
            tc.load_entry(bad)
            fail("loader did NOT reject mismatched namespace")
        except ValueError:
            pass
    ok("mismatched namespace/filename rejected")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: Every entry's drill path exists on disk
    # ------------------------------------------------------------------
    step("5. every entry's testing.drill path exists on disk")
    missing_drills: list[tuple[str, str]] = []
    for ns, entry in catalog.items():
        drill_path = entry.raw.get("testing", {}).get("drill", "")
        if not drill_path:
            continue
        full = REPO / drill_path
        if not full.exists():
            missing_drills.append((ns, drill_path))
    if missing_drills:
        fail(f"drill paths missing on disk: {missing_drills}")
    ok(f"all {len(catalog)} entries reference real drill files")

    # ------------------------------------------------------------------
    # Step 6 — POSITIVE: Every entry's opa_bundle path exists on disk
    # ------------------------------------------------------------------
    step("6. every entry's policy.opa_bundle path exists on disk")
    missing_rego: list[tuple[str, str]] = []
    for ns, entry in catalog.items():
        rego_path = entry.raw.get("policy", {}).get("opa_bundle", "")
        if not rego_path:
            continue
        full = REPO / rego_path
        if not full.exists():
            missing_rego.append((ns, rego_path))
    if missing_rego:
        fail(f"opa_bundle paths missing on disk: {missing_rego}")
    ok(f"all {len(catalog)} entries reference real .rego files")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: missing required axis → error
    # ------------------------------------------------------------------
    step("7. NEGATIVE: missing required axis → validate_entry errors")
    sample = copy.deepcopy(next(iter(catalog.values())).raw)
    sample.pop("fallback", None)
    errors = tc.validate_entry(sample)
    if not any("fallback" in e for e in errors):
        fail("dropping fallback axis was NOT detected as error")
    ok(f"missing axis surfaces error: {errors[0][:60]}…")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: policy.default != 'deny' rejected
    # ------------------------------------------------------------------
    step("8. NEGATIVE: policy.default != 'deny' rejected (default-deny lock)")
    sample = copy.deepcopy(next(iter(catalog.values())).raw)
    sample["policy"]["default"] = "allow"
    errors = tc.validate_entry(sample)
    if not any("default-deny" in e or "default" in e for e in errors):
        fail("policy.default='allow' was NOT rejected — security regression")
    ok("policy.default='allow' rejected (default-deny invariant locked)")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: tool not prefixed with namespace rejected
    # ------------------------------------------------------------------
    step("9. NEGATIVE: io[].tool without namespace prefix rejected")
    sample = copy.deepcopy(next(iter(catalog.values())).raw)
    if sample["io"]:
        sample["io"][0]["tool"] = "wrong_namespace.something"
    errors = tc.validate_entry(sample)
    if not any("doesn't start with" in e for e in errors):
        fail("namespace prefix violation NOT detected")
    ok("io[].tool namespace mismatch rejected")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: otel.span_name without mcp.<ns>. rejected
    # ------------------------------------------------------------------
    step("10. NEGATIVE: otel.span_name without mcp.<ns>. prefix rejected")
    sample = copy.deepcopy(next(iter(catalog.values())).raw)
    sample["observability"]["otel"]["span_name"] = "random.span.name"
    errors = tc.validate_entry(sample)
    if not any("span_name" in e for e in errors):
        fail("otel.span_name prefix violation NOT detected")
    ok("otel.span_name without mcp.<ns>. prefix rejected")

    # ------------------------------------------------------------------
    # Step 11 — NEGATIVE: log_fields missing request_id/tenant_id
    # ------------------------------------------------------------------
    step("11. NEGATIVE: log_fields missing request_id/tenant_id rejected")
    sample = copy.deepcopy(next(iter(catalog.values())).raw)
    sample["observability"]["log_fields"] = ["latency_ms", "outcome"]
    errors = tc.validate_entry(sample)
    if not any("request_id" in e for e in errors):
        fail("missing request_id in log_fields NOT detected")
    if not any("tenant_id" in e for e in errors):
        fail("missing tenant_id in log_fields NOT detected")
    ok("missing canonical log fields rejected (forensic substrate locked)")

    print(f"\n{GREEN}{BOLD}ALL 11 STEPS PASSED (6 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
