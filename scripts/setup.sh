#!/usr/bin/env bash
# setup.sh — canonical bootstrap for the circuitRAG / DocuMind project on the
# /mnt/deepa drive (per the no-system-drive policy in iter-93).
#
# Per CLAUDE.md §44 (iter-100), §57 (production-grade by default),
# §42 (operational autonomy — installs to /mnt/deepa, NOT system drive).
#
# Usage:
#   bash scripts/setup.sh                    # full bootstrap (interactive)
#   bash scripts/setup.sh --check            # only verify state, no install
#   bash scripts/setup.sh --tools            # only install CLI tools
#   bash scripts/setup.sh --venv             # only set up venv + Python deps
#   bash scripts/setup.sh --infra            # only bring up docker-compose infra
#   bash scripts/setup.sh --istio            # only set up minikube + Istio
#   bash scripts/setup.sh --verify           # run the full audit suite
#
# Idempotent: re-running skips what's already installed.

set -uo pipefail

# Colors
GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; BLUE="\033[36m"; BOLD="\033[1m"; NC="\033[0m"

# Paths — ALL on /mnt/deepa per the no-system-drive policy
REPO="/mnt/deepa/rag"
TOOLS_BIN="${REPO}/.tools/bin"
TOOLS_CACHE="${REPO}/.tools/cache"
TOOLS_LIB="${REPO}/.tools/lib"
VENV="${REPO}/.venv"
MINIKUBE_HOME_DIR="/mnt/deepa/.minikube"
KUBE_CONFIG_DIR="/mnt/deepa/.kube"

ok() { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${BLUE}ℹ${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err() { echo -e "${RED}✗${NC} $*" >&2; }
section() { echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BOLD}  $*${NC}"; echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

check_repo() {
    if [[ ! -d "$REPO" ]]; then
        err "Repo not at $REPO — adjust REPO env var or run from /mnt/deepa/rag"
        exit 2
    fi
    cd "$REPO"
}

setup_dirs() {
    section "1. Project directories on /mnt/deepa"
    mkdir -p "$TOOLS_BIN" "$TOOLS_CACHE/pip" "$TOOLS_CACHE/npm" \
             "$TOOLS_LIB" "$MINIKUBE_HOME_DIR" "$KUBE_CONFIG_DIR" "$REPO/.loop"
    ok "Created/verified: $TOOLS_BIN $TOOLS_CACHE $VENV (next) $MINIKUBE_HOME_DIR $KUBE_CONFIG_DIR"
}

print_env() {
    section "Activation env (paste into your shell)"
    cat <<EOF
${BOLD}# Per ~/.claude memory feedback_no_system_drive_install:${NC}
export PATH=${TOOLS_BIN}:\$PATH
export PIP_CACHE_DIR=${TOOLS_CACHE}/pip
export NPM_CONFIG_CACHE=${TOOLS_CACHE}/npm
export MINIKUBE_HOME=${MINIKUBE_HOME_DIR}
export KUBECONFIG=${KUBE_CONFIG_DIR}/config
export OLLAMA_BASE_URL=\${OLLAMA_BASE_URL:-http://localhost:11434}
export PYTHONPATH=${REPO}/libs/py:\${PYTHONPATH:-}
EOF
}

install_tool_binary() {
    local name="$1" url="$2" tar_member="${3:-$1}"
    if [[ -x "$TOOLS_BIN/$name" ]]; then
        ok "$name already installed at $TOOLS_BIN/$name"
        return 0
    fi
    info "Installing $name from $url"
    if [[ "$url" == *.tar.gz ]]; then
        curl -fsSL "$url" -o "/tmp/${name}.tgz" || { err "download $name failed"; return 1; }
        tar xzf "/tmp/${name}.tgz" -C /tmp/ "$tar_member" || { err "extract $name failed"; return 1; }
        mv "/tmp/$tar_member" "$TOOLS_BIN/$name"
    else
        curl -fsSL "$url" -o "$TOOLS_BIN/$name" || { err "download $name failed"; return 1; }
    fi
    chmod +x "$TOOLS_BIN/$name"
    ok "$name installed"
}

install_tools() {
    section "2. CLI tools (binaries to .tools/bin on deepa)"

    install_tool_binary kubectl \
        "https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl"
    install_tool_binary minikube \
        "https://storage.googleapis.com/minikube/releases/v1.33.1/minikube-linux-amd64"

    if [[ ! -x "$TOOLS_BIN/istioctl" ]]; then
        info "Installing istioctl 1.22.0 (multi-file tarball)"
        curl -fsSL "https://github.com/istio/istio/releases/download/1.22.0/istio-1.22.0-linux-amd64.tar.gz" \
            | tar -xz -C /tmp/
        cp /tmp/istio-1.22.0/bin/istioctl "$TOOLS_BIN/istioctl"
        chmod +x "$TOOLS_BIN/istioctl"
        ok "istioctl installed"
    else
        ok "istioctl already installed"
    fi

    install_tool_binary trivy \
        "https://github.com/aquasecurity/trivy/releases/download/v0.70.0/trivy_0.70.0_Linux-64bit.tar.gz" \
        trivy
    install_tool_binary gitleaks \
        "https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_linux_x64.tar.gz" \
        gitleaks

    # Promptfoo via npm to .tools/lib/node
    if [[ ! -L "$TOOLS_BIN/promptfoo" && ! -x "$TOOLS_BIN/promptfoo" ]]; then
        info "Installing promptfoo via npm into $TOOLS_LIB/node"
        mkdir -p "$TOOLS_LIB/node"
        NPM_CONFIG_CACHE="$TOOLS_CACHE/npm" npm install --prefix "$TOOLS_LIB/node" promptfoo
        ln -sfn "$TOOLS_LIB/node/node_modules/.bin/promptfoo" "$TOOLS_BIN/promptfoo"
        ok "promptfoo installed"
    else
        ok "promptfoo already installed"
    fi

    section "Tool inventory:"
    ls -la "$TOOLS_BIN/" 2>&1 | tail -n +2
    echo
    info "Total .tools size: $(du -sh "$REPO/.tools" 2>&1 | cut -f1)"
}

setup_venv() {
    section "3. Python venv + deps (cached on deepa)"
    if [[ ! -f "$VENV/bin/python" ]]; then
        info "Creating venv at $VENV"
        python3 -m venv "$VENV"
    fi
    info "Upgrading pip + installing core deps"
    PIP_CACHE_DIR="$TOOLS_CACHE/pip" "$VENV/bin/pip" install --quiet --upgrade pip
    PIP_CACHE_DIR="$TOOLS_CACHE/pip" "$VENV/bin/pip" install --quiet \
        pyyaml fastapi uvicorn httpx pydantic prometheus_client \
        opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi \
        ragas deepeval giskard rebuff arize-phoenix semgrep great_expectations \
        pyjwt 2>&1 | grep -E "(ERROR|Successfully|already)" | head -10 || true
    ok "venv ready: $($VENV/bin/python --version)"
}

infra_up() {
    section "4. Infrastructure (docker compose)"
    info "Starting Postgres + Redis + Kafka + Ollama + Qdrant + Neo4j + MinIO + OTel + Jaeger + Prometheus + Grafana"
    docker compose up -d postgres redis kafka zookeeper minio ollama qdrant neo4j \
        otel-collector jaeger prometheus alertmanager grafana \
        elasticsearch kibana filebeat envoy 2>&1 | tail -3
    ok "Infra command issued (containers may take 30-60s to become healthy)"
    echo
    info "Verify health: docker ps --format \"{{.Names}}\\t{{.Status}}\" | grep documind"
}

istio_up() {
    section "5. Minikube + Istio + Kiali (cluster on deepa drive)"
    if [[ ! -x "$TOOLS_BIN/minikube" || ! -x "$TOOLS_BIN/kubectl" || ! -x "$TOOLS_BIN/istioctl" ]]; then
        err "minikube/kubectl/istioctl not in $TOOLS_BIN — run --tools first"
        return 1
    fi
    export PATH="$TOOLS_BIN:$PATH"
    export KUBECONFIG="$KUBE_CONFIG_DIR/config"
    if minikube status --profile documind-mesh 2>/dev/null | grep -q "host: Running"; then
        ok "Minikube cluster documind-mesh already up"
    else
        info "Starting minikube cluster documind-mesh (3072MB / 2 CPU)"
        minikube start --profile documind-mesh --memory 3072 --cpus 2 --driver docker
    fi
    info "Installing Istio control plane (idempotent)"
    istioctl install -y --set profile=default 2>&1 | tail -3
    info "Installing Kiali + Prometheus + Jaeger addons"
    if [[ -d /tmp/istio-1.22.0/samples/addons ]]; then
        kubectl apply -f /tmp/istio-1.22.0/samples/addons/kiali.yaml 2>&1 | tail -3
        kubectl apply -f /tmp/istio-1.22.0/samples/addons/prometheus.yaml 2>&1 | tail -3
        kubectl apply -f /tmp/istio-1.22.0/samples/addons/jaeger.yaml 2>&1 | tail -3
    else
        warn "Istio samples not at /tmp/istio-1.22.0/ — re-run scripts/setup.sh --tools to refetch"
    fi
    info "Applying project Istio manifests"
    kubectl apply -f infra/istio/ 2>&1 | tail -5 || true
    ok "Istio + Kiali up. Open with: kubectl port-forward -n istio-system svc/kiali 20001:20001"
}

run_audits() {
    section "6. Verification — run the full audit suite"

    info "Per-tool fleet health (28 MCP servers + Ollama + council + backends)"
    "$VENV/bin/python" scripts/mcp_fleet_health.py --probe-timeout 1.0 2>&1 | tail -5 || true
    echo

    info "Ollama all-models smoke (15 models — runs ~10-30s per cold model)"
    if [[ "${SKIP_OLLAMA_SMOKE:-0}" != "1" ]]; then
        "$VENV/bin/python" scripts/ollama_all_models_smoke.py --write 2>&1 | tail -5 || true
    else
        warn "SKIP_OLLAMA_SMOKE=1 — skipping (~3-5 min)"
    fi
    echo

    info "Agent readiness (7-dim probe)"
    "$VENV/bin/python" scripts/agent_readiness_check.py --write 2>&1 | grep -E "^[A-Z]_apply|by_status" | head -5 || true
    echo

    info "Production readiness scorecard (5 dims §38+§47+§52+§53+§55)"
    "$VENV/bin/python" scripts/production_readiness_scorecard.py --write 2>&1 | tail -10 || true
    echo

    info "OSS tooling catalog audit (91 OSS tools × 17 categories)"
    "$VENV/bin/python" scripts/oss_tooling_audit.py 2>&1 | head -10 || true
    echo

    info "Chunking quality catalog audit (20 metrics + 15 gates)"
    "$VENV/bin/python" scripts/chunking_quality_audit.py 2>&1 | head -10 || true
    echo

    info "Agentic observability catalog (35 scenarios)"
    "$VENV/bin/python" scripts/agentic_observability_audit.py 2>&1 | head -10 || true
    echo

    info "11-scenario E2E run (batch + inference + graph + vector + ES + OPA + telemetry + paperclip + openclaw + langgraph + vectorless)"
    if [[ "${SKIP_E2E:-0}" != "1" ]]; then
        "$VENV/bin/python" scripts/scenario_batch_and_inference.py 2>&1 | tail -5 || true
    else
        warn "SKIP_E2E=1 — skipping (~45 sec)"
    fi
    echo

    section "Audit reports written under .loop/"
    ls -la "$REPO/.loop/"*.json 2>&1 | tail -n +2 | head -15
}

usage() {
    cat <<'EOF'
setup.sh — canonical bootstrap for /mnt/deepa/rag

Usage:
  bash scripts/setup.sh                    # full bootstrap (default-deny on destructive ops)
  bash scripts/setup.sh --check            # only print state + activation env
  bash scripts/setup.sh --dirs             # only create project directories
  bash scripts/setup.sh --tools            # only install CLI tools to .tools/bin
  bash scripts/setup.sh --venv             # only set up venv + Python deps
  bash scripts/setup.sh --infra            # only bring up docker-compose infra
  bash scripts/setup.sh --istio            # only minikube + Istio + Kiali
  bash scripts/setup.sh --verify           # only run the audit suite (no installs)
  bash scripts/setup.sh --env              # print activation env

Notes:
  - Per the no-system-drive policy, ALL paths land on /mnt/deepa
  - Idempotent — re-running skips what's already installed
  - SKIP_OLLAMA_SMOKE=1 skips the slow LLM cold-load smoke
  - SKIP_E2E=1         skips the 11-scenario E2E run
EOF
}

# Main entry point
check_repo

case "${1:-}" in
    -h|--help|help)
        usage; exit 0 ;;
    --check)
        section "circuitRAG / DocuMind setup state — check mode"
        for x in kubectl minikube istioctl trivy gitleaks promptfoo; do
            if [[ -x "$TOOLS_BIN/$x" ]]; then
                ok "$x at $TOOLS_BIN/$x"
            else
                warn "$x missing"
            fi
        done
        if [[ -f "$VENV/bin/python" ]]; then
            ok "venv: $($VENV/bin/python --version)"
        else
            warn "venv missing at $VENV"
        fi
        print_env
        exit 0 ;;
    --env)
        print_env; exit 0 ;;
    --dirs)
        setup_dirs; exit 0 ;;
    --tools)
        setup_dirs; install_tools; exit 0 ;;
    --venv)
        setup_dirs; setup_venv; exit 0 ;;
    --infra)
        infra_up; exit 0 ;;
    --istio)
        istio_up; exit 0 ;;
    --verify)
        run_audits; exit 0 ;;
    "")
        section "circuitRAG / DocuMind — full bootstrap on /mnt/deepa"
        setup_dirs
        install_tools
        setup_venv
        warn "Skipping --infra and --istio in default flow (run them explicitly)"
        warn "Run: bash scripts/setup.sh --infra   # docker-compose stack"
        warn "Run: bash scripts/setup.sh --istio   # minikube + Istio"
        warn "Run: bash scripts/setup.sh --verify  # audit suite"
        print_env
        exit 0 ;;
    *)
        err "Unknown argument: $1"
        usage; exit 2 ;;
esac
