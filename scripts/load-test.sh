#!/usr/bin/env bash
# Load-test wrapper for the k6 baseline profile.
#
# Profiles (per global §47.10 + /admin/load-testing/deep playbook):
#   smoke    1 VU,   10s        sanity, no errors expected
#   load     100 VU, 3m         SLA target sustain
#   stress   100→1000 VU, 5m    find breakpoint
#   soak     100 VU, 10m        memory growth detection
#   spike    0→2000 VU, 60s     recovery test
#   full     all 5 phases sequentially (~22 min total)
#
# Usage:
#   bash scripts/load-test.sh smoke
#   bash scripts/load-test.sh full
#   BASE_URL=https://prod.documind.com bash scripts/load-test.sh load
#
# Exit code: passthrough from k6 (0 = thresholds green; 99 = breach).
#
# Locked by mcp/tests/drill_load_test_setup.py.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:-smoke}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
SCRIPT="${REPO_ROOT}/infra/load-test/k6/baseline.js"
RESULTS_DIR="${REPO_ROOT}/.loop/load-test"
mkdir -p "$RESULTS_DIR"

color()  { local c="$1"; shift; printf "\033[${c}m%s\033[0m\n" "$*"; }
ok()     { color "32" "✓ $*"; }
info()   { color "36" "ℹ $*"; }
warn()   { color "33" "⚠ $*"; }
err()    { color "31" "✗ $*" >&2; }

if ! command -v k6 >/dev/null 2>&1; then
    err "k6 not on PATH"
    echo "    install: https://k6.io/docs/get-started/installation/"
    echo "    quick:   curl -L https://github.com/grafana/k6/releases/latest/download/k6-linux-amd64.tar.gz | tar xz && sudo mv k6-*/k6 /usr/local/bin/"
    exit 2
fi

run_profile() {
    local profile="$1"
    local out="${RESULTS_DIR}/${profile}-$(date +%Y%m%d-%H%M%S).json"
    info "Running profile=$profile against $BASE_URL"
    info "Results JSON → $out"
    PROFILE="$profile" k6 run \
        -e "BASE_URL=${BASE_URL}" \
        -e "AUTH_BEARER=${AUTH_BEARER:-}" \
        --summary-export "$out" \
        "$SCRIPT"
    local rc=$?
    if [ $rc -eq 0 ]; then
        ok "$profile passed all SLOs"
    else
        warn "$profile exited $rc — SLO breach OR k6 error"
    fi
    return $rc
}

case "$PROFILE" in
    smoke|load|stress|soak|spike)
        run_profile "$PROFILE"
        ;;
    full)
        info "Running all 5 phases sequentially (~22 min)"
        for p in smoke load stress soak spike; do
            run_profile "$p" || warn "$p had issues; continuing"
            sleep 5
        done
        ok "Full profile complete; results in ${RESULTS_DIR}/"
        ;;
    *)
        err "unknown profile: $PROFILE"
        echo "    profiles: smoke | load | stress | soak | spike | full"
        exit 2
        ;;
esac
