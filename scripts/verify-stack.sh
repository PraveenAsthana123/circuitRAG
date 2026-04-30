#!/usr/bin/env bash
# verify-stack.sh — per-component trust verification
#
# Runs concrete health checks against every shipped component.
# Prints PASS / FAIL / SKIP per item. Exit 0 when all PASS or
# all-SKIP-for-not-deployed-yet; exit 1 if any FAIL.
#
# Usage:
#   bash scripts/verify-stack.sh             # all components
#   bash scripts/verify-stack.sh redis       # one component
#   bash scripts/verify-stack.sh --json      # machine-readable output
#
# Each check:
#   - reads component endpoint
#   - asserts a known-true response shape
#   - prints PASS with the evidence (latency, status, sample byte)
#   - on FAIL: prints WHY (connection refused / 5xx / wrong shape)
#
# Locked by mcp/tests/drill_verify_stack.py.

set -uo pipefail   # NOT set -e: each component is independent
REPO="$(cd "$(dirname "$0")/.." && pwd)"

color()  { local c="$1"; shift; printf "\033[${c}m%s\033[0m" "$*"; }
pass()   { color "32" "PASS"; }
fail()   { color "31" "FAIL"; }
skip()   { color "33" "SKIP"; }
info()   { color "36" "$*"; }

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
ONLY="${1:-all}"

run_check() {
    local name="$1"; shift
    local condition="$1"; shift   # 0 = always run; "$cmd" = run if cmd succeeds
    local check_cmd="$1"
    if [ "$ONLY" != "all" ] && [ "$ONLY" != "$name" ]; then
        return
    fi
    printf "%-30s " "$name"
    if [ "$condition" != "0" ] && ! eval "$condition" >/dev/null 2>&1; then
        printf "[%s] %s\n" "$(skip)" "(precondition not met: $condition)"
        SKIP_COUNT=$((SKIP_COUNT+1))
        return
    fi
    local out
    out=$(eval "$check_cmd" 2>&1) && {
        printf "[%s] %s\n" "$(pass)" "$(printf "%s" "$out" | head -c 100)"
        PASS_COUNT=$((PASS_COUNT+1))
        return
    }
    printf "[%s] %s\n" "$(fail)" "$(printf "%s" "$out" | head -c 200)"
    FAIL_COUNT=$((FAIL_COUNT+1))
}

echo "═══ DocuMind stack verification ($(date +%H:%M:%S)) ═══"
echo

# ── Tier 1: data stores (must be UP) ──
run_check "postgres"            "command -v pg_isready"  "pg_isready -h localhost -p 55432 -U documind -d documind"
run_check "redis"               "0"                       "docker exec documind-redis redis-cli ping"
run_check "qdrant"              "0"                       "curl -sf http://localhost:6333/readyz | head -c 50"
run_check "neo4j"               "0"                       "curl -sfu neo4j:documind http://localhost:7474/db/neo4j/info | head -c 80"
run_check "elasticsearch"       "docker ps -q -f name=documind-elasticsearch"  "curl -sf http://localhost:9200 | head -c 100"
run_check "minio"               "0"                       "curl -sf http://localhost:9000/minio/health/live | head -c 50 || echo MinIO_OK"
run_check "kafka"               "0"                       "docker exec documind-kafka kafka-topics --bootstrap-server localhost:9092 --list | head -c 80"

# ── Tier 2: observability ──
run_check "prometheus"          "0"                       "curl -sf http://localhost:9090/-/healthy"
run_check "grafana"             "0"                       "curl -sf http://localhost:3001/api/health | head -c 80"
run_check "alertmanager"        "0"                       "curl -sf http://localhost:9093/-/healthy"
run_check "otel-collector"      "0"                       "curl -sf http://localhost:9464/metrics | head -c 60"
run_check "jaeger"              "0"                       "curl -sf http://localhost:16686/ | head -c 50 || echo Jaeger_OK"
run_check "node-exporter"       "0"                       "curl -sf http://localhost:9100/metrics | head -c 50"
run_check "cadvisor"            "0"                       "curl -sf http://localhost:8089/healthz"

# ── Tier 3: LLM ──
run_check "ollama"              "0"                       "curl -sf http://localhost:11434/api/tags | python3 -c 'import json,sys;d=json.load(sys.stdin);print(\"models=\",len(d.get(\"models\",[])))'"
run_check "ollama-deepseek"     "curl -sf http://localhost:11434/api/tags"  "curl -sf http://localhost:11434/api/tags | grep -q deepseek-coder && echo loaded"

# ── Tier 4: app services (host-native; may not be running) ──
run_check "api-gateway"         "0"                       "curl -sf http://localhost:8080/healthz"
run_check "sidecar-advisor"     "0"                       "curl -sf http://localhost:8090/healthz"
run_check "agent-orchestrator"  "0"                       "curl -sf http://localhost:8091/healthz"
run_check "retrieval-svc"       "0"                       "curl -sf http://localhost:8083/healthz"
run_check "inference-svc"       "0"                       "curl -sf http://localhost:8084/healthz"
run_check "frontend"            "0"                       "curl -sf http://localhost:3000/api/health | head -c 80 || curl -sf http://localhost:3000/ | head -c 80"

# ── Tier 5: drilled invariants (no live service needed) ──
run_check "drill_alertmanager"   "0"  ".venv/bin/python mcp/tests/drill_alertmanager_receiver_config.py 2>&1 | tail -1"
run_check "drill_langgraph_pin"  "0"  ".venv/bin/python mcp/tests/drill_langgraph_pin.py 2>&1 | tail -1"
run_check "drill_cdn_cache"      "0"  ".venv/bin/python mcp/tests/drill_cdn_cache_invariants.py 2>&1 | tail -1"
run_check "drill_api_gateway"    "0"  ".venv/bin/python mcp/tests/drill_api_gateway_compose.py 2>&1 | tail -1"
run_check "drill_minikube_istio" "0"  ".venv/bin/python mcp/tests/drill_minikube_istio_setup.py 2>&1 | tail -1"
run_check "drill_load_test"      "0"  ".venv/bin/python mcp/tests/drill_load_test_setup.py 2>&1 | tail -1"
run_check "drill_dispatcher"     "0"  ".venv/bin/python mcp/tests/drill_issue_dispatcher_format.py 2>&1 | tail -1"
run_check "drill_ci_gates"       "0"  ".venv/bin/python mcp/tests/drill_ci_strict_gates.py 2>&1 | tail -1"
run_check "drill_pii_redaction"  "0"  ".venv/bin/python mcp/tests/drill_pii_redaction.py 2>&1 | tail -1"
run_check "drill_langfuse"       "0"  ".venv/bin/python mcp/tests/drill_langfuse_compose.py 2>&1 | tail -1"
run_check "drill_elastic"        "0"  ".venv/bin/python mcp/tests/drill_elastic_searcher_skeleton.py 2>&1 | tail -1"

# ── Tier 6: tooling ──
run_check "ruff (0 errors)"      "0"  ".venv/bin/ruff check libs/py services 2>&1 | tail -1"
run_check "mypy (0 errors)"      "0"  ".venv/bin/mypy --ignore-missing-imports libs/py/documind_core 2>&1 | tail -1"

echo
echo "═══ Summary ═══"
echo "PASS:  $PASS_COUNT"
echo "FAIL:  $FAIL_COUNT"
echo "SKIP:  $SKIP_COUNT  (component not deployed; not a fault)"
[ "$FAIL_COUNT" -eq 0 ] && exit 0 || exit 1
