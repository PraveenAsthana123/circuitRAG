"""Chunking quality catalog audit (iter-99).

Loads `config/agentic_observability/chunking_quality.yaml` and emits
per-stage gate distribution + writes
`.loop/chunking_quality_audit.json` for UI consumption.

Per CLAUDE.md §44 (iter-99), §47 (architecture as data),
§57.4 (self-healing as data not code), §57.6 (canonical fields).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "config" / "agentic_observability" / "chunking_quality.yaml"
OUT = REPO / ".loop" / "chunking_quality_audit.json"

ALLOWED_STAGES = frozenset({"ingest", "retrieve", "generate", "post"})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--blocking", action="store_true",
                   help="only show pipeline-blocking gates")
    args = p.parse_args()

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        print("pyyaml not installed", file=sys.stderr)
        return 2

    cat = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}
    metrics = cat.get("metrics", [])
    gates = cat.get("quality_gates", [])

    issues: list[str] = []
    by_stage: Counter[str] = Counter()
    by_emit_to: Counter[str] = Counter()
    blocking_count = 0

    metric_ids = set()
    for m in metrics:
        mid = m.get("id", "")
        if mid in metric_ids:
            issues.append(f"duplicate metric id: {mid}")
        metric_ids.add(mid)
        for required in ("id", "name", "why", "compute_via", "emit_to",
                         "threshold_default"):
            if required not in m:
                issues.append(f"metric {mid}: missing {required}")
        for tool in (m.get("emit_to") or "").split("+"):
            tool = tool.strip()
            if tool:
                by_emit_to[tool] += 1

    gate_ids = set()
    for g in gates:
        gid = g.get("id", "")
        if gid in gate_ids:
            issues.append(f"duplicate gate id: {gid}")
        gate_ids.add(gid)
        for required in ("id", "name", "stage", "threshold",
                         "action_on_fail", "blocks_pipeline", "enforced_by"):
            if required not in g:
                issues.append(f"gate {gid}: missing {required}")
        st = g.get("stage", "")
        if st not in ALLOWED_STAGES:
            issues.append(f"gate {gid}: invalid stage {st!r}")
        by_stage[st] += 1
        if g.get("blocks_pipeline") is True:
            blocking_count += 1

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics_total": len(metrics),
        "gates_total": len(gates),
        "blocking_gates": blocking_count,
        "by_stage": dict(by_stage),
        "by_emit_to_top": dict(by_emit_to.most_common(8)),
        "validation_issues": issues,
        "adaptive_engine_status": cat.get("adaptive_engine", {}).get("status", "?"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
        return 1 if issues else 0

    print("=" * 64)
    print("CHUNKING QUALITY CATALOG — audit")
    print("=" * 64)
    print(f"Total metrics:       {summary['metrics_total']}")
    print(f"Total quality gates: {summary['gates_total']}")
    print(f"Pipeline-blocking:   {summary['blocking_gates']}/{summary['gates_total']}")
    print(f"Adaptive engine:     {summary['adaptive_engine_status']}")
    print()
    print("Gates by stage:")
    for st, n in by_stage.most_common():
        print(f"  {n:>2}  {st}")
    print()
    print("Top emit-to targets:")
    for tool, n in by_emit_to.most_common(8):
        print(f"  {n:>2}  {tool}")
    if args.blocking:
        print()
        print("Blocking gates:")
        for g in gates:
            if g.get("blocks_pipeline"):
                print(f"  [{g['id']}] {g['name']} (stage={g['stage']}) — "
                      f"threshold: {g['threshold']}")
    print()
    print(f"Wrote: {OUT.relative_to(REPO)}")
    if issues:
        print(f"\nVALIDATION ISSUES ({len(issues)}):")
        for iss in issues[:5]:
            print(f"  - {iss}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
