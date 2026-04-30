#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/bench-tools.sh per-tool micro-benchmark contract.

Locks the per-tool benchmark harness so future edits cannot silently
drop a tool, drop the timestamped output convention, or ditch the
min/avg/p95/max stats line. Without this drill, "we have ms numbers"
claims drift away from a verifiable script.

Negative assertions: bench script absent; tool coverage shrinks
below the 14-tool floor; output dir convention abandoned; results
file lacks the deterministic header.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "bench-tools.sh"
OUT_DIR = REPO / ".loop" / "bench"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: scripts/bench-tools.sh exists --")
    if not SCRIPT.exists():
        raise AssertionError(f"missing {SCRIPT.relative_to(REPO)}")
    print("  ok: script present")

    print("-- 2. POSITIVE: script is executable --")
    mode = SCRIPT.stat().st_mode
    if not (mode & stat.S_IXUSR):
        raise AssertionError("bench-tools.sh is not executable (chmod +x missing)")
    print("  ok: chmod +x set")

    text = SCRIPT.read_text(encoding="utf-8")

    print("-- 3. POSITIVE: covers Tier-1 data stores (postgres, redis, qdrant, neo4j) --")
    for tool in (
        '"postgres-ping"',
        '"postgres-select1"',
        '"redis-ping"',
        '"redis-set-get"',
        '"qdrant-readyz"',
        '"qdrant-list"',
        '"neo4j-cypher"',
    ):
        require(text, tool, f"tier-1 tool: {tool}")
    print("  ok: 7 data-store probes present")

    print("-- 4. POSITIVE: covers LLM serving (ollama-tags + ollama-ps) --")
    require(text, '"ollama-tags"', "ollama tags probe")
    require(text, '"ollama-ps"', "ollama ps probe")
    print("  ok: ollama probes present")

    print("-- 5. POSITIVE: covers observability HTTP layer --")
    for tool in (
        '"prometheus-health"',
        '"grafana-health"',
        '"alertmgr-health"',
        '"jaeger-root"',
    ):
        require(text, tool, f"observability tool: {tool}")
    print("  ok: 4 observability probes present")

    print("-- 6. POSITIVE: covers filesystem + drill regression timing --")
    require(text, '"loop-jsonl-append"', "audit-row append probe")
    require(text, '"drill-langgraph"', "drill regression timing")
    require(text, '"drill-cdn-cache"', "drill cdn cache timing")
    require(text, '"drill-load-test"', "drill load-test timing")
    print("  ok: filesystem + 3 drill probes present")

    print("-- 7. POSITIVE: 14+ probes total (Tier 1+2+3 floor) --")
    probe_count = len(re.findall(r'time_cmd\s+"', text))
    if probe_count < 14:
        raise AssertionError(f"expected ≥14 probes; got {probe_count}")
    print(f"  ok: {probe_count} probes (≥14 floor)")

    print("-- 8. POSITIVE: stats output uses min/avg/p95/max --")
    for stat_field in ("min=", "avg=", "p95=", "max="):
        require(text, stat_field, f"stat field {stat_field}")
    print("  ok: min/avg/p95/max stat line wired")

    print("-- 9. POSITIVE: writes timestamped output to .loop/bench/ --")
    require(text, '.loop/bench"', "output dir convention")
    require(text, "$(date +%Y%m%d-%H%M%S)", "timestamped filename")
    print("  ok: .loop/bench/<ts>.md output")

    print("-- 10. POSITIVE: --iters and --tool flags supported --")
    require(text, "--iters", "--iters flag")
    require(text, "--tool", "--tool flag")
    print("  ok: configurable iterations + tool filter")

    print("-- 11. NEGATIVE: auth threading present (psql + qdrant) --")
    # Without PGPASSWORD or qdrant api-key, postgres-select1 + qdrant-list
    # SKIP. The drill catches the regression where someone strips auth.
    require(text, "PGPASSWORD", "PGPASSWORD env")
    require(text, "api-key:", "qdrant api-key header")
    print("  ok: auth threading wired for postgres + qdrant")

    print("-- 12. POSITIVE: at least one prior run is on disk --")
    if not OUT_DIR.exists():
        raise AssertionError(f"output dir absent: {OUT_DIR.relative_to(REPO)}")
    runs = sorted(OUT_DIR.glob("*.md"))
    if not runs:
        raise AssertionError("no bench runs on disk — has anyone executed bench-tools.sh?")
    latest = runs[-1].read_text(encoding="utf-8")
    if "bench-tools" not in latest:
        raise AssertionError("latest bench file missing canonical header")
    if "ms (n=" not in latest:
        raise AssertionError("latest bench file missing measurement rows")
    print(f"  ok: {len(runs)} run(s) on disk; latest is {runs[-1].name}")

    print("-- 13. NEGATIVE: --tool filter actually executes the live binary --")
    # Catches future regression where someone "optimizes" by reading
    # a cached file instead of timing fresh syscalls.
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--tool", "loop-jsonl-append", "--iters", "3"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=30,
    )
    if proc.returncode != 0:
        raise AssertionError(f"bench --tool loop-jsonl-append exited {proc.returncode}\n{proc.stderr}")
    if "loop-jsonl-append" not in proc.stdout:
        raise AssertionError("filtered run missing the requested probe")
    if "ms (n=3)" not in proc.stdout:
        raise AssertionError("filtered run missing n=3 stat row")
    print("  ok: --tool filter executes a live 3-iter measurement")

    print("\nALL 13 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
