#!/usr/bin/env bash
# bench-tools.sh — per-tool micro-benchmark with real ms numbers
#
# For every running infrastructure tool, runs a representative
# operation N times and reports min/avg/p95/max latency. Writes
# results to .loop/bench/<timestamp>.md so trends are trackable.
#
# Usage:
#   bash scripts/bench-tools.sh                # all tools, default 20 iters
#   bash scripts/bench-tools.sh --iters 100    # bigger sample
#   bash scripts/bench-tools.sh --tool redis   # one tool
#
# Each tool = one micro-bench:
#   postgres   pg_isready + SELECT 1 (round-trip + simple query)
#   redis      PING + SET + GET (write + read)
#   qdrant     /readyz + collection list (HTTP round-trip)
#   neo4j      RETURN 1 cypher (Bolt round-trip)
#   ollama     /api/tags (HTTP — list models, very fast)
#   prom       /-/healthy (curl)
#   grafana    /api/health
#   alertmgr   /-/healthy
#   jaeger     / (HTML response)
#   nginx      /healthz (if api-gateway routed)
#   filesystem .loop/ JSONL append (drill audit speed)
#
# Locked by mcp/tests/drill_bench_tools.py.

set -uo pipefail

case "${1:-}" in
  -h|--help)
    cat <<'HELP'
bench-tools.sh — per-tool micro-benchmark with real ms numbers

For every running infrastructure tool, runs a representative
operation N times and reports min/avg/p95/max latency. Writes
results to .loop/bench/<timestamp>.md so trends are trackable.

Usage:
  bash scripts/bench-tools.sh                # all tools, default 20 iters
  bash scripts/bench-tools.sh --iters 100    # bigger sample
  bash scripts/bench-tools.sh --tool redis   # one tool

Tools covered: postgres, redis, qdrant, neo4j, ollama, prom,
grafana, alertmgr, jaeger, nginx, filesystem.

Locked by mcp/tests/drill_bench_tools.py.
HELP
    exit 0
    ;;
esac

ITERS="${ITERS:-20}"
ONLY=""
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO/.loop/bench"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/$(date +%Y%m%d-%H%M%S).md"

# Per-tool auth — exported so the timed sub-command inherits.
export PGPASSWORD="${PGPASSWORD:-documind}"
QDRANT_KEY="${DOCUMIND_QDRANT_API_KEY:-dev-qdrant-key}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --iters) ITERS="$2"; shift 2;;
        --tool)  ONLY="$2"; shift 2;;
        *) echo "unknown arg: $1"; exit 2;;
    esac
done

# Time one command N times; print min, avg, p95, max in ms.
# Reports ALL N measurements so caller can compute custom stats.
time_cmd() {
    local label="$1"; shift
    if [[ -n "$ONLY" && "$label" != "$ONLY" ]]; then
        return
    fi
    local times=()
    for i in $(seq 1 "$ITERS"); do
        local start_ns end_ns
        start_ns=$(date +%s%N)
        if ! "$@" >/dev/null 2>&1; then
            printf "%-20s [SKIP] tool not reachable / cmd failed on iter %d\n" "$label" "$i" | tee -a "$OUT"
            return
        fi
        end_ns=$(date +%s%N)
        times+=( $(( (end_ns - start_ns) / 1000000 )) )
    done
    # Compute stats via python (handles sort + p95 cleanly)
    local stats
    stats=$(python3 -c "
import sys
ts = sorted([$(IFS=,; echo "${times[*]}")])
n = len(ts)
print(f'min={ts[0]:>4}  avg={sum(ts)//n:>4}  p95={ts[int(n*0.95)-1]:>4}  max={ts[-1]:>4}')
")
    printf "%-20s %s ms (n=%d)\n" "$label" "$stats" "$ITERS" | tee -a "$OUT"
}

echo "# bench-tools — $(date -Is)" | tee "$OUT"
echo "# iters per tool: $ITERS"      | tee -a "$OUT"
echo "# system: $(uname -srm) — $(grep MemAvailable /proc/meminfo | awk '{print $2/1024/1024,"GiB available"}')" | tee -a "$OUT"
echo "" | tee -a "$OUT"

# ── Postgres ──
time_cmd "postgres-ping"     pg_isready -h localhost -p 55432 -U documind -d documind
time_cmd "postgres-select1"  psql -h localhost -p 55432 -U documind -d documind -c "SELECT 1" -t

# ── Redis ──
time_cmd "redis-ping"        docker exec documind-redis redis-cli ping
time_cmd "redis-set-get"     bash -c "docker exec documind-redis redis-cli SET bench:test 'value' && docker exec documind-redis redis-cli GET bench:test"

# ── Qdrant ── (api-key required for /collections; readyz is public)
time_cmd "qdrant-readyz"     curl -sf http://localhost:6333/readyz
time_cmd "qdrant-list"       curl -sf -H "api-key: $QDRANT_KEY" http://localhost:6333/collections

# ── Neo4j ──
time_cmd "neo4j-cypher"      docker exec documind-neo4j cypher-shell -u neo4j -p documind --format plain "RETURN 1"

# ── Ollama ──
time_cmd "ollama-tags"       curl -sf http://localhost:11434/api/tags
time_cmd "ollama-ps"         curl -sf http://localhost:11434/api/ps

# ── Observability HTTP ──
time_cmd "prometheus-health" curl -sf http://localhost:9090/-/healthy
time_cmd "grafana-health"    curl -sf http://localhost:3001/api/health
time_cmd "alertmgr-health"   curl -sf http://localhost:9093/-/healthy
time_cmd "jaeger-root"       curl -sf http://localhost:16686/

# ── Filesystem (audit row append speed) ──
time_cmd "loop-jsonl-append" bash -c "echo '{\"bench\":\"test\"}' >> /tmp/bench-test.jsonl"

# ── Drill execution time (regression-test ms) ──
time_cmd "drill-langgraph"   .venv/bin/python mcp/tests/drill_langgraph_pin.py
time_cmd "drill-cdn-cache"   .venv/bin/python mcp/tests/drill_cdn_cache_invariants.py
time_cmd "drill-load-test"   .venv/bin/python mcp/tests/drill_load_test_setup.py

echo "" | tee -a "$OUT"
echo "Results written to: $OUT" | tee -a "$OUT"
rm -f /tmp/bench-test.jsonl
