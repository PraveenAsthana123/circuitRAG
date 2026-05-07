# RESOURCES: readonly
"""
Drill: chunking quality catalog (iter-99).

Per CLAUDE.md §43 (drill ≥3 negatives), §44 (iter-99), §57.4 (self-healing
as data not code), user blueprint: 20 metrics + 15 quality gates.

Locks (positive):
  L1. catalog loads + has 20 metrics + 15 gates
  L2. audit script runs + writes JSON report
  L3. every metric has id/name/why/compute_via/emit_to/threshold_default
  L4. every gate has id/name/stage/threshold/action_on_fail/blocks_pipeline
  L5. ≥6 gates marked blocks_pipeline (forensic-substrate hard-stop guarantee)

Locks (negative):
  N1. duplicate metric IDs rejected
  N2. duplicate gate IDs rejected
  N3. gate.stage not in {ingest, retrieve, generate, post} rejected
  N4. blocks_pipeline must be boolean (not string "true")
  N5. canonical Ragas + DeepEval + Great Expectations + Prometheus
      all referenced as emit_to (no missing canonical OSS tool)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "config" / "agentic_observability" / "chunking_quality.yaml"
SCRIPT = REPO / "scripts" / "chunking_quality_audit.py"
REPORT = REPO / ".loop" / "chunking_quality_audit.json"

GREEN, RED, BOLD, NC = "\033[32m", "\033[31m", "\033[1m", "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        fail("pyyaml not installed")

    if not CATALOG.exists():
        fail(f"missing: {CATALOG.relative_to(REPO)}")
    cat = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}

    step("1. catalog loads + has 20 metrics + 15 gates")
    metrics = cat.get("metrics", [])
    gates = cat.get("quality_gates", [])
    if len(metrics) != 20:
        fail(f"expected 20 metrics; got {len(metrics)}")
    if len(gates) != 15:
        fail(f"expected 15 gates; got {len(gates)}")
    ok(f"metrics={len(metrics)} gates={len(gates)}")

    step("2. audit script runs + writes report")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=30, cwd=str(REPO),
    )
    if proc.returncode not in (0, 1):
        fail(f"audit exited {proc.returncode}: {proc.stderr[:200]}")
    if not REPORT.exists():
        fail(f"report not written: {REPORT.relative_to(REPO)}")
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    ok(f"report wrote {payload['metrics_total']} metrics + {payload['gates_total']} gates")

    step("3. every metric has all canonical fields")
    canonical = {"id", "name", "why", "compute_via", "emit_to", "threshold_default"}
    for m in metrics:
        missing = canonical - set(m.keys())
        if missing:
            fail(f"metric {m.get('id')}: missing {missing}")
    ok(f"all 20 metrics complete")

    step("4. every gate has all canonical fields")
    canonical_g = {"id", "name", "stage", "threshold", "action_on_fail",
                   "blocks_pipeline", "enforced_by"}
    for g in gates:
        missing = canonical_g - set(g.keys())
        if missing:
            fail(f"gate {g.get('id')}: missing {missing}")
    ok(f"all 15 gates complete")

    step("5. ≥6 gates blocks_pipeline=True (hard-stop coverage)")
    blocking = [g for g in gates if g.get("blocks_pipeline") is True]
    if len(blocking) < 6:
        fail(f"only {len(blocking)} blocking gates; expected ≥6 for production-grade")
    ok(f"{len(blocking)} blocking gates locked: {[g['id'] for g in blocking]}")

    step("6. NEGATIVE: no duplicate metric IDs")
    ids = [m.get("id") for m in metrics]
    if len(set(ids)) != len(ids):
        dups = [i for i in set(ids) if ids.count(i) > 1]
        fail(f"duplicate metric IDs: {dups}")
    ok("all 20 metric IDs unique")

    step("7. NEGATIVE: no duplicate gate IDs")
    gids = [g.get("id") for g in gates]
    if len(set(gids)) != len(gids):
        dups = [i for i in set(gids) if gids.count(i) > 1]
        fail(f"duplicate gate IDs: {dups}")
    ok("all 15 gate IDs unique")

    step("8. NEGATIVE: gate.stage in canonical 4 values")
    valid_stages = {"ingest", "retrieve", "generate", "post"}
    for g in gates:
        if g.get("stage") not in valid_stages:
            fail(f"gate {g.get('id')}: invalid stage {g.get('stage')!r}")
    ok("all gate.stage values valid")

    step("9. NEGATIVE: blocks_pipeline must be bool (not string)")
    for g in gates:
        v = g.get("blocks_pipeline")
        if not isinstance(v, bool):
            fail(f"gate {g.get('id')}: blocks_pipeline={v!r} (type={type(v).__name__})")
    ok("all blocks_pipeline values are real booleans")

    step("10. NEGATIVE: canonical OSS tools referenced as emit_to")
    all_emit = " ".join(m.get("emit_to", "") for m in metrics)
    required_tools = ("ragas", "deepeval", "great_expectations", "prometheus")
    missing_tools = [t for t in required_tools if t not in all_emit.lower()]
    if missing_tools:
        fail(f"canonical OSS tools missing from emit_to: {missing_tools}")
    ok(f"all required OSS tools present: {required_tools}")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    print(f"\nGates by stage: {payload['by_stage']}")
    print(f"Top emit_to:     {payload['by_emit_to_top']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
