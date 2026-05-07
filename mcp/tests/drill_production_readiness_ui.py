# RESOURCES: readonly
"""
Drill: production readiness scorecard + UI (iter-78).

Per CLAUDE.md §43 (drill ≥3 negatives), §44 (iter-78 ships scorecard),
§38 §47 §52 §53 §55 (the policies the scorecard aggregates),
§51 (forensic substrate).

User asked: "all must be 100% working, production grade readiness with
UI report, visualization."

Locks (positive):
  L1. Scorecard script exists with canonical 5 dimensions
  L2. Running --write produces .loop/production_readiness_scorecard.json
  L3. JSON has overall_score + production_grade + 5 dimensions
  L4. BFF + page exist at canonical paths
  L5. Page renders RadialGauge + ScoreBar + per-dim cards

Locks (negative):
  N1. production_grade is FALSE when ANY dimension below threshold
      (don't silently claim production-grade when gaps exist)
  N2. §55 brutal-rule banner shows when G5 < 50 (no glossing)
  N3. BFF returns 503 on missing scorecard file
  N4. Frontend ONLY hits /api/v1/production-readiness
  N5. Auto-refresh ≤ BFF cache TTL (no thrash)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "production_readiness_scorecard.py"
REPORT = REPO / ".loop" / "production_readiness_scorecard.json"
BFF = REPO / "services" / "frontend" / "app" / "api" / "v1" / "production-readiness" / "route.ts"
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "production-readiness" / "page.tsx"
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
    # Step 1
    step("1. scorecard script + canonical 5 dimensions")
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT.relative_to(REPO)}")
    src = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "def score_governance",
        "def score_architecture",
        "def score_tool_reviews",
        "def score_maturity",
        "def score_outcome",
        "def aggregate",
    ):
        if marker not in src:
            fail(f"script missing canonical fn: {marker}")
    ok("5 dimension scorers + aggregate present")

    # Step 2
    step("2. --write produces .loop/production_readiness_scorecard.json")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--write"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO),
    )
    if proc.returncode != 0:
        fail(f"script exited {proc.returncode}; stderr: {proc.stderr[:200]}")
    if not REPORT.exists():
        fail(f"report not written: {REPORT.relative_to(REPO)}")
    ok(f"report file: {REPORT.relative_to(REPO)}")

    # Step 3
    step("3. JSON has overall_score + production_grade + 5 dimensions")
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    for k in ("overall_score", "production_grade", "dimensions", "thresholds"):
        if k not in payload:
            fail(f"report missing top-level key: {k}")
    expected_dims = {
        "G1_governance_38", "G2_architecture_47", "G3_tool_reviews_52",
        "G4_maturity_53", "G5_outcome_55",
    }
    actual = set(payload["dimensions"].keys())
    if actual != expected_dims:
        fail(f"dimensions mismatch: {actual} != {expected_dims}")
    ok(f"overall={payload['overall_score']} grade={payload['production_grade']}")

    # Step 4
    step("4. BFF + page exist at canonical paths")
    if not BFF.exists():
        fail(f"missing BFF: {BFF.relative_to(REPO)}")
    if not PAGE.exists():
        fail(f"missing page: {PAGE.relative_to(REPO)}")
    bff_src = BFF.read_text(encoding="utf-8")
    page_src = PAGE.read_text(encoding="utf-8")
    ok("BFF + page present")

    # Step 5
    step("5. page renders RadialGauge + ScoreBar + per-dim cards")
    for needle in ("RadialGauge", "ScoreBar", "dimensions"):
        if needle not in page_src:
            fail(f"page missing component / data ref: {needle}")
    ok("RadialGauge + ScoreBar + dimensions present")

    # Step 6 — NEGATIVE: production_grade=FALSE when any dim < threshold
    step("6. NEGATIVE: production_grade is FALSE when any dim below threshold")
    import production_readiness_scorecard as prs  # type: ignore[import-not-found]
    # Use the actual aggregator with no scoring change. If current scorecard
    # has any gap, production_grade should be False per the rule.
    summary = prs.aggregate()
    any_below = any(
        summary["dimensions"][k]["score"] < summary["thresholds"][k]
        for k in summary["dimensions"]
    )
    if any_below and summary["production_grade"]:
        fail(
            "production_grade=True even though a dimension is below threshold "
            "— would falsely claim production-grade with named gaps"
        )
    if not any_below and not summary["production_grade"]:
        fail(
            "production_grade=False even though all dimensions cleared "
            "thresholds — false negative"
        )
    ok(f"production_grade={summary['production_grade']} aligns with all-dims-pass={not any_below}")

    # Step 7 — NEGATIVE: §55 banner present in page
    step("7. NEGATIVE: §55 brutal-rule banner present (no glossing)")
    if "§55" not in page_src:
        fail("page missing §55 brutal-rule reference")
    if "G5_outcome_55.score < 50" not in page_src:
        fail("page doesn't conditionally show banner on low outcome score")
    ok("§55 banner conditionally rendered when outcome < 50")

    # Step 8 — NEGATIVE: BFF returns 503 on missing
    step("8. NEGATIVE: BFF returns 503 on missing scorecard")
    if "production_readiness_scorecard_missing" not in bff_src:
        fail("BFF missing canonical error code production_readiness_scorecard_missing")
    if "503" not in bff_src:
        fail("BFF missing 503 status")
    ok("BFF returns 503 with structured JSON on missing file")

    # Step 9 — NEGATIVE: frontend only hits canonical BFF
    step("9. NEGATIVE: frontend only fetches /api/v1/production-readiness")
    fetches = re.findall(r"fetch\((['\"])([^'\"]+)\1", page_src)
    if not fetches:
        fail("no fetch calls — page broken")
    for _, url in fetches:
        if not url.startswith("/api/v1/production-readiness"):
            fail(f"frontend fetches unexpected URL: {url}")
    ok(f"all {len(fetches)} fetches go to /api/v1/production-readiness")

    # Step 10 — NEGATIVE: auto-refresh ≤ cache TTL
    step("10. NEGATIVE: auto-refresh ≤ BFF cache TTL (no thrash)")
    m_ttl = re.search(r"CACHE_TTL_MS\s*=\s*(\d[\d_]*)", bff_src)
    if not m_ttl:
        fail("BFF missing CACHE_TTL_MS")
    ttl = int(m_ttl.group(1).replace("_", ""))
    m_int = re.search(r"setInterval\(load,\s*(\d[\d_]*)\)", page_src)
    if not m_int:
        fail("page missing setInterval auto-refresh")
    interval = int(m_int.group(1).replace("_", ""))
    if interval > ttl:
        fail(f"auto-refresh {interval}ms > cache TTL {ttl}ms — script-fork thrash")
    ok(f"auto-refresh {interval}ms ≤ cache TTL {ttl}ms")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
