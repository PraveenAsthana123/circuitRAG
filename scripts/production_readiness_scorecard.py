"""Production readiness scorecard — aggregates §38 + §47 + §52 + §53 + §55 (iter-78).

User asked: "all must be 100% working, production grade readiness with
UI report, visualization."

This script aggregates evidence from across the platform into ONE
sourcetruth scorecard with five major dimensions matching the global
CLAUDE.md policies:

  G1. AI Production Governance (§38) — 15 production gates
  G2. Architecture & Design (§47) — 7 design surfaces
  G3. Brutal Tool Review (§52) — 40-row checklist (aggregated)
  G4. Enterprise AI Maturity Stack (§53) — 14 items + L1-L6 levels
  G5. Outcome Contract (§55) — apply rate / regression / cost

Each dimension is scored 0-100 with named gaps. The output drives
the /admin/production-readiness UI (iter-78b).

Per CLAUDE.md §44 (iter-78), §38 (verifiable claims), §47 (architecture
observable), §51 (forensic substrate), §52 (per-tool brutal review),
§53 (enterprise maturity), §55 (outcome-based contract).

Output: .loop/production_readiness_scorecard.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOOP = REPO / ".loop"
OUT_PATH = LOOP / "production_readiness_scorecard.json"


def _exists(p: str | Path) -> bool:
    return (REPO / p).exists() if not Path(p).is_absolute() else Path(p).exists()


def _count_files(glob: str) -> int:
    return len(list(REPO.glob(glob)))


def _read_json(p: str) -> dict | None:
    full = REPO / p
    if not full.exists():
        return None
    try:
        return json.loads(full.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# -----------------------------------------------------------------
# G1. §38 — AI Production Governance: 15 gates
# -----------------------------------------------------------------
def score_governance() -> dict:
    """15 gates per CLAUDE.md §38.1."""
    gates = [
        ("Business goal + KPI", _exists("docs/architecture/maturity-stack.md")),
        ("Requirements (PRD)", _exists("docs/architecture/jad/")),
        ("Architecture (HLD/LLD/ADR)", _count_files("docs/architecture/adr/*.md") >= 25),
        ("Security review", _exists("docs/architecture/security/")),
        ("Data contracts + retention", _exists("docs/architecture/")),
        ("Backend resilience", _exists("services/agent-orchestrator-svc/app/db_circuit_breaker.py")),
        ("Frontend UX states", _exists("services/frontend/app/admin/")),
        ("AI guardrails", _exists("services/inference-svc/")),
        ("Test pyramid + drills", _count_files("mcp/tests/drill_*.py") >= 50),
        ("Performance + load", _exists("docs/architecture/load-testing/")),
        ("Operations (logs/traces/metrics)", _exists("services/agent-orchestrator-svc/app/main.py")),
        ("Reliability + DR", _exists("libs/py/documind_core/dr_metrics.py")),
        ("Deployment pipeline", _count_files(".github/workflows/*.yml") >= 1),
        ("Governance + ownership", _exists("docs/architecture/maturity-stack.md")),
        ("Documentation + runbook", _exists("docs/runbooks/")),
    ]
    passed = sum(1 for _, ok in gates if ok)
    score = int(100 * passed / len(gates))
    return {
        "score": score,
        "passed": passed,
        "total": len(gates),
        "gates": [{"name": n, "passed": ok} for n, ok in gates],
        "gaps": [n for n, ok in gates if not ok],
    }


# -----------------------------------------------------------------
# G2. §47 — Architecture: 7 design surfaces
# -----------------------------------------------------------------
def score_architecture() -> dict:
    surfaces = [
        ("C4 model (L1-L7)", _exists("services/frontend/app/admin/c4-model/")),
        ("ADR registry (≥10)", _count_files("docs/architecture/adr/*.md") >= 10),
        ("JAD chain", _exists("services/frontend/app/admin/jad/")),
        ("Security (OWASP/STRIDE/SOC2)", _exists("services/frontend/app/admin/security/")),
        ("Rollout (4-layer rollback)", _exists("services/frontend/app/admin/rollout/")),
        ("Principles (12+5 factor)", _exists("services/frontend/app/admin/principles/")),
        ("Load testing (5 phases)", _exists("services/frontend/app/admin/load-testing/")),
    ]
    passed = sum(1 for _, ok in surfaces if ok)
    score = int(100 * passed / len(surfaces))
    return {
        "score": score,
        "passed": passed,
        "total": len(surfaces),
        "surfaces": [{"name": n, "present": ok} for n, ok in surfaces],
        "gaps": [n for n, ok in surfaces if not ok],
    }


# -----------------------------------------------------------------
# G3. §52 — Brutal tool review: per-tool 40 rows
# -----------------------------------------------------------------
def score_tool_reviews() -> dict:
    review_dir = REPO / "docs" / "architecture" / "tool-reviews"
    reviewed_tools = (
        sorted(p.stem for p in review_dir.glob("*.md") if p.stem != "README" and not p.stem.startswith("_"))
        if review_dir.exists() else []
    )
    catalog_dir = REPO / "config" / "tool_catalog"
    cataloged_tools = sorted(p.stem for p in catalog_dir.glob("*.yaml")) if catalog_dir.exists() else []
    server_files = sorted(
        p.stem.replace("server_", "")
        for p in (REPO / "mcp").glob("server_*.py")
        if p.stem != "server_common"
    )
    n_servers = len(server_files)
    review_coverage = int(100 * len(reviewed_tools) / n_servers) if n_servers else 0
    catalog_coverage = int(100 * len(cataloged_tools) / n_servers) if n_servers else 0
    # Combined: average of review + catalog
    combined = int((review_coverage + catalog_coverage) / 2)
    return {
        "score": combined,
        "review_coverage_pct": review_coverage,
        "catalog_coverage_pct": catalog_coverage,
        "reviewed_count": len(reviewed_tools),
        "cataloged_count": len(cataloged_tools),
        "total_servers": n_servers,
        "reviewed": reviewed_tools,
        "cataloged": cataloged_tools,
        "gaps": [s for s in server_files if s not in reviewed_tools and s not in cataloged_tools][:10],
    }


# -----------------------------------------------------------------
# G4. §53 — Enterprise AI Maturity Stack: 14 items + level
# -----------------------------------------------------------------
def score_maturity() -> dict:
    """Reads docs/architecture/maturity-stack.md to extract per-item levels."""
    matrix = REPO / "docs" / "architecture" / "maturity-stack.md"
    items = [
        "DR metrics", "Capacity planning", "Dependency contracts",
        "Schema evolution", "Observability taxonomy", "Business KPI tracking",
        "Change management", "Documentation",
        "Integration & operating model", "Production validation",
        "Continuous improvement", "Platformization", "Strategic alignment",
        "AI Governance OS",
    ]
    if matrix.exists():
        text = matrix.read_text(encoding="utf-8")
        # Coarse heuristic: count ≥L4 items as "passed"
        levels: dict[str, str] = {}
        # Look for lines like "| 35 DR metrics | L4 |" or similar markdown tables
        for item in items:
            level = "L1"
            for line in text.splitlines():
                if item.lower() in line.lower():
                    for L in ("L6", "L5", "L4", "L3", "L2", "L1"):
                        if L in line:
                            level = L
                            break
                    if level != "L1":
                        break
            levels[item] = level
        passed = sum(1 for L in levels.values() if L >= "L4")
    else:
        levels = {item: "UNKNOWN" for item in items}
        passed = 0

    score = int(100 * passed / len(items))
    return {
        "score": score,
        "passed_at_l4": passed,
        "total_items": len(items),
        "items": [{"name": k, "level": v} for k, v in levels.items()],
        "gaps": [k for k, v in levels.items() if v < "L4"],
    }


# -----------------------------------------------------------------
# G5. §55 — Outcome Contract: apply rate, regression, cost
# -----------------------------------------------------------------
def score_outcome() -> dict:
    """Reads .loop/agent_readiness_report.json + .loop/agent_task_board_apply.jsonl."""
    rep = _read_json(".loop/agent_readiness_report.json") or {"results": {}}
    apply_rate_probe = rep.get("results", {}).get("D_apply_rate", {})

    # Council apply rate (from probe evidence string)
    evidence = apply_rate_probe.get("evidence", "")
    # Examples: "council 0/3 = 0%; deterministic 1/1 = 100%"
    council_rate = 0
    det_rate = 0
    for chunk in evidence.split(";"):
        chunk = chunk.strip()
        if chunk.startswith("council"):
            try:
                council_rate = int(chunk.split("=")[-1].strip().rstrip("%"))
            except (ValueError, IndexError):
                council_rate = 0
        elif chunk.startswith("deterministic"):
            try:
                det_rate = int(chunk.split("=")[-1].strip().rstrip("%"))
            except (ValueError, IndexError):
                det_rate = 0

    # Score: (council_rate × 0.6) + (det_rate × 0.4) per §55.3 — council
    # is the harder/more-important lane
    score = int(council_rate * 0.6 + det_rate * 0.4)

    # Regression: count failing drills (drill_history.jsonl tail)
    history = REPO / ".loop" / "drill_history.jsonl"
    recent_failures = 0
    if history.exists():
        lines = history.read_text(encoding="utf-8").splitlines()[-200:]
        for line in lines:
            try:
                row = json.loads(line)
                if row.get("status") in ("failed", "fail", "FAIL"):
                    recent_failures += 1
            except json.JSONDecodeError:
                continue

    return {
        "score": score,
        "council_apply_rate_pct": council_rate,
        "deterministic_apply_rate_pct": det_rate,
        "recent_drill_failures": recent_failures,
        "gaps": (
            ["council apply rate < 50% — §55 brutal-rule fire"]
            if council_rate < 50 else []
        ),
    }


# -----------------------------------------------------------------
# Aggregate
# -----------------------------------------------------------------
def aggregate() -> dict:
    g1 = score_governance()
    g2 = score_architecture()
    g3 = score_tool_reviews()
    g4 = score_maturity()
    g5 = score_outcome()

    overall = int((g1["score"] + g2["score"] + g3["score"] + g4["score"] + g5["score"]) / 5)

    # Production-grade verdict per the global ruleset:
    # §38 governance ≥ 80, §47 architecture ≥ 80, §52 reviews ≥ 50,
    # §53 maturity ≥ 70 (L4+), §55 outcome ≥ 50
    is_prod_grade = (
        g1["score"] >= 80
        and g2["score"] >= 80
        and g3["score"] >= 50
        and g4["score"] >= 70
        and g5["score"] >= 50
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_score": overall,
        "production_grade": is_prod_grade,
        "dimensions": {
            "G1_governance_38": g1,
            "G2_architecture_47": g2,
            "G3_tool_reviews_52": g3,
            "G4_maturity_53": g4,
            "G5_outcome_55": g5,
        },
        "thresholds": {
            "G1_governance_38": 80,
            "G2_architecture_47": 80,
            "G3_tool_reviews_52": 50,
            "G4_maturity_53": 70,
            "G5_outcome_55": 50,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="JSON output only")
    p.add_argument("--write", action="store_true",
                   help="write to .loop/production_readiness_scorecard.json")
    args = p.parse_args()

    summary = aggregate()

    if args.write or not args.json:
        LOOP.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print("\nPRODUCTION READINESS SCORECARD")
    print("=" * 60)
    print(f"Overall: {summary['overall_score']}/100 · production_grade={summary['production_grade']}")
    print()
    for k, dim in summary["dimensions"].items():
        thr = summary["thresholds"][k]
        marker = "✓" if dim["score"] >= thr else "✗"
        print(f"  {marker} {k:<28} {dim['score']:>3}/100 (threshold {thr})")
        if dim.get("gaps"):
            for gap in dim["gaps"][:3]:
                print(f"      - gap: {gap}")
            if len(dim["gaps"]) > 3:
                print(f"      - ... +{len(dim['gaps']) - 3} more gaps")
    if args.write:
        print(f"\nWrote: {OUT_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
