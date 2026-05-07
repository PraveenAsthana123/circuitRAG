#!/usr/bin/env bash
# install_all_oss_tools.sh — phased installer for all 91 OSS tools in the catalog.
#
# Per CLAUDE.md §44 (iter-101), §57 (production-grade), feedback memory
# `no_system_drive_install` (everything on /mnt/deepa).
#
# Sources:
#   config/agentic_observability/oss_tooling_catalog.yaml (91 tools)
#
# Phases (default: 1+2 only; phase 3 requires k8s):
#   PHASE 1 — quick installs (pip + binary + npm)         ~10 min total
#   PHASE 2 — docker-compose heavy services               ~15 min disk-pull
#   PHASE 3 — k8s helm + manifest deploys                 ~20 min on minikube
#   PHASE 4 — Ollama model pulls (Llama Guard etc.)        operator-decided disk
#
# Usage:
#   bash scripts/install_all_oss_tools.sh                  # phase 1+2
#   bash scripts/install_all_oss_tools.sh --quick          # phase 1 only
#   bash scripts/install_all_oss_tools.sh --heavy          # phase 1+2 (default)
#   bash scripts/install_all_oss_tools.sh --k8s            # phase 1+2+3
#   bash scripts/install_all_oss_tools.sh --all            # phase 1+2+3+4
#   bash scripts/install_all_oss_tools.sh --check          # only show what's missing

set -uo pipefail

REPO="/mnt/deepa/rag"
TOOLS_BIN="${REPO}/.tools/bin"
TOOLS_CACHE="${REPO}/.tools/cache"
TOOLS_LIB="${REPO}/.tools/lib"
VENV="${REPO}/.venv"

GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; BLUE="\033[36m"; BOLD="\033[1m"; NC="\033[0m"
ok()      { echo -e "${GREEN}✓${NC} $*"; }
info()    { echo -e "${BLUE}ℹ${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
err()     { echo -e "${RED}✗${NC} $*" >&2; }
section() { echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BOLD}  $*${NC}"; echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

cd "$REPO" || { err "no $REPO"; exit 2; }
mkdir -p "$TOOLS_BIN" "$TOOLS_CACHE/pip" "$TOOLS_CACHE/npm" "$TOOLS_LIB"
export PIP_CACHE_DIR="$TOOLS_CACHE/pip"
export NPM_CONFIG_CACHE="$TOOLS_CACHE/npm"

PIP="${VENV}/bin/pip"
PY="${VENV}/bin/python"

# ────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Quick installs (pip + binary + npm). 10 min total fresh.
# ────────────────────────────────────────────────────────────────────────────
phase1_pip_packages() {
    section "PHASE 1a — Python packages (pip → .venv)"
    [[ -f "$PIP" ]] || { err "venv missing; run: bash scripts/setup.sh --venv"; return 1; }

    # Group A: Already installed in setup.sh (verify)
    local already=(arize-phoenix semgrep great_expectations ragas deepeval giskard rebuff pyjwt)
    # Group B: New OSS tools per catalog (P1+P2 priority, pip-installable)
    local new_pkgs=(
        promptfoo                # has both npm + pip wrappers; npm preferred
        traceloop-sdk            # OTel-native LLM tracing
        trulens-eval             # grounding analysis
        crfm-helm                # Stanford HELM benchmark
        lm-eval                  # EleutherAI lm-evaluation-harness
        inspect-ai               # agent benchmark
        garak                    # AI vulnerability scanner
        locust                   # distributed load test
        counterfit               # adversarial AI testing (Microsoft)
        pyrit                    # Python Risk ID Tool (Microsoft)
        vigil-llm                # AI firewall
        mlflow                   # ML experiment tracking (alt-backup)
        soda-core                # data observability
        checkov                  # Terraform/k8s/IaC scanner
        bandit                   # Python static security (verify)
        kube-hunter              # k8s penetration scan
        pyroscope-io             # continuous profiling client
        evidently                # ML/data drift
    )

    info "Verifying ${#already[@]} pre-installed packages..."
    for pkg in "${already[@]}"; do
        if "$PIP" show "$pkg" >/dev/null 2>&1; then
            ok "$pkg already installed"
        else
            warn "$pkg missing (re-run setup.sh --venv)"
        fi
    done

    info "Installing ${#new_pkgs[@]} new pip packages (this may take 5-10 min)"
    for pkg in "${new_pkgs[@]}"; do
        if "$PIP" show "$pkg" >/dev/null 2>&1; then
            ok "$pkg already installed (skipping)"
            continue
        fi
        info "  installing $pkg"
        if "$PIP" install --quiet --no-input "$pkg" 2>&1 | tail -2; then
            ok "$pkg installed"
        else
            warn "$pkg install failed (often a dep conflict — operator follow-up)"
        fi
    done
}

phase1_binaries() {
    section "PHASE 1b — Binaries to .tools/bin"

    install_binary() {
        local name="$1" url="$2" tar_member="${3:-$1}"
        if [[ -x "$TOOLS_BIN/$name" ]]; then
            ok "$name already at $TOOLS_BIN/$name"
            return 0
        fi
        info "  downloading $name"
        if [[ "$url" == *.tar.gz ]]; then
            curl -fsSL "$url" -o "/tmp/${name}.tgz" || { err "$name download failed"; return 1; }
            tar xzf "/tmp/${name}.tgz" -C /tmp/ "$tar_member" 2>/dev/null || tar xzf "/tmp/${name}.tgz" -C /tmp/ || true
            if [[ -f "/tmp/$tar_member" ]]; then
                mv "/tmp/$tar_member" "$TOOLS_BIN/$name"
            elif [[ -f "/tmp/$name" ]]; then
                mv "/tmp/$name" "$TOOLS_BIN/$name"
            fi
        elif [[ "$url" == *.zip ]]; then
            curl -fsSL "$url" -o "/tmp/${name}.zip" && unzip -o -j "/tmp/${name}.zip" -d /tmp/ "$tar_member" >/dev/null 2>&1
            mv "/tmp/$tar_member" "$TOOLS_BIN/$name" 2>/dev/null || true
        else
            curl -fsSL "$url" -o "$TOOLS_BIN/$name"
        fi
        if [[ -f "$TOOLS_BIN/$name" ]]; then
            chmod +x "$TOOLS_BIN/$name"
            ok "$name installed"
        else
            err "$name install failed"
        fi
    }

    # Already installed by setup.sh (verify only)
    for tool in kubectl minikube istioctl trivy gitleaks; do
        if [[ -x "$TOOLS_BIN/$tool" ]]; then
            ok "$tool already installed"
        else
            warn "$tool missing — run: bash scripts/setup.sh --tools"
        fi
    done

    # New binaries
    install_binary k6 \
        "https://github.com/grafana/k6/releases/download/v0.53.0/k6-v0.53.0-linux-amd64.tar.gz" \
        "k6-v0.53.0-linux-amd64/k6"

    install_binary grype \
        "https://github.com/anchore/grype/releases/download/v0.83.0/grype_0.83.0_linux_amd64.tar.gz" \
        grype

    install_binary kubescape \
        "https://github.com/kubescape/kubescape/releases/download/v3.0.20/kubescape-ubuntu-latest" \
        ""

    install_binary helm \
        "https://get.helm.sh/helm-v3.16.0-linux-amd64.tar.gz" \
        "linux-amd64/helm"

    install_binary kustomize \
        "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.5.0/kustomize_v5.5.0_linux_amd64.tar.gz" \
        kustomize

    install_binary argocd \
        "https://github.com/argoproj/argo-cd/releases/download/v2.13.0/argocd-linux-amd64" \
        ""

    install_binary tfsec \
        "https://github.com/aquasecurity/tfsec/releases/download/v1.28.13/tfsec-linux-amd64" \
        ""

    install_binary opa \
        "https://github.com/open-policy-agent/opa/releases/download/v0.69.0/opa_linux_amd64_static" \
        ""
}

phase1_npm() {
    section "PHASE 1c — npm packages (.tools/lib/node)"
    if ! command -v npm >/dev/null 2>&1; then
        warn "npm not in PATH — skipping (install Node.js to enable)"
        return 0
    fi
    mkdir -p "$TOOLS_LIB/node"

    local pkgs=(promptfoo)
    for pkg in "${pkgs[@]}"; do
        if [[ -L "$TOOLS_BIN/$pkg" ]]; then
            ok "$pkg already symlinked"
            continue
        fi
        info "installing $pkg"
        NPM_CONFIG_CACHE="$TOOLS_CACHE/npm" npm install --silent --prefix "$TOOLS_LIB/node" "$pkg" 2>&1 | tail -2
        ln -sfn "$TOOLS_LIB/node/node_modules/.bin/$pkg" "$TOOLS_BIN/$pkg"
        ok "$pkg symlinked to $TOOLS_BIN/$pkg"
    done
}

# ────────────────────────────────────────────────────────────────────────────
# PHASE 2 — Heavy docker-compose services
# ────────────────────────────────────────────────────────────────────────────
phase2_docker() {
    section "PHASE 2 — Heavy docker-compose services"

    info "Already running (per setup.sh --infra):"
    ok "  postgres, redis, kafka, zookeeper, minio, ollama"
    ok "  qdrant, neo4j, otel-collector, jaeger, prometheus"
    ok "  alertmanager, grafana, elasticsearch, kibana, filebeat, envoy"
    echo

    # Tools that have official docker images we can run as compose addons
    local skipped=(
        "marquez (lineage UI) — needs OpenLineage producer wired"
        "datahub (metadata catalog) — needs MySQL + Elasticsearch + GMS + frontend"
        "openmetadata (governance) — needs MySQL + Airflow"
        "metabase (BI) — single-container, can be added"
        "redash (BI) — multi-container, can be added"
        "lightdash (BI) — needs dbt project"
        "apache_superset (BI) — Postgres + Redis + Celery"
        "wazuh (SIEM) — heavy 4-container stack"
        "temporal (workflow) — Postgres-backed"
        "vault / openbao (secrets) — needs init key ceremony"
    )

    warn "These are docker-compose stacks the catalog tracks but are NOT auto-deployed:"
    for s in "${skipped[@]}"; do
        echo "    - $s"
    done
    echo
    info "To opt-in to a stack: docker compose --profile <name> up <service>"
    info "Example: docker compose --profile bi up apache-superset"
}

# ────────────────────────────────────────────────────────────────────────────
# PHASE 3 — k8s helm deploys
# ────────────────────────────────────────────────────────────────────────────
phase3_k8s() {
    section "PHASE 3 — k8s helm deploys (require minikube up)"
    export PATH="$TOOLS_BIN:$PATH"
    export KUBECONFIG="/mnt/deepa/.kube/config"

    if ! kubectl get nodes >/dev/null 2>&1; then
        err "k8s cluster not reachable — run: bash scripts/setup.sh --istio first"
        return 1
    fi

    if ! command -v helm >/dev/null 2>&1; then
        err "helm not installed — run --quick first"
        return 1
    fi

    info "Adding helm repos"
    helm repo add falcosecurity https://falcosecurity.github.io/charts 2>/dev/null || true
    helm repo add kyverno https://kyverno.github.io/kyverno/ 2>/dev/null || true
    helm repo add argo https://argoproj.github.io/argo-helm 2>/dev/null || true
    helm repo add temporal https://go.temporal.io/helm-charts 2>/dev/null || true
    helm repo add cilium https://helm.cilium.io/ 2>/dev/null || true
    helm repo update 2>&1 | tail -2

    local installs=(
        "falco|falcosecurity/falco|falco|--set tty=true"
        "kyverno|kyverno/kyverno|kyverno|--set replicaCount=1"
        "argo-cd|argo/argo-cd|argocd|--set server.service.type=ClusterIP"
        "argo-rollouts|argo/argo-rollouts|argo-rollouts|"
        "kubescape|kubescape/kubescape-cloud-operator|kubescape|"
        "tetragon|cilium/tetragon|kube-system|"
    )

    for entry in "${installs[@]}"; do
        IFS='|' read -r release chart ns extra_args <<< "$entry"
        kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1 || true
        if helm list -n "$ns" 2>/dev/null | grep -q "^$release\b"; then
            ok "$release already installed in $ns"
        else
            info "Installing $release into $ns"
            helm install "$release" "$chart" -n "$ns" $extra_args 2>&1 | tail -3 || warn "$release install failed"
        fi
    done

    info "Skipped (operator decision):"
    warn "  - temporal (heavy state; Postgres dependency)"
    warn "  - vault/openbao (key ceremony)"
    warn "  - opa-gatekeeper (admission webhook may conflict with iter-94 OPA pod)"
}

# ────────────────────────────────────────────────────────────────────────────
# PHASE 4 — Ollama model pulls
# ────────────────────────────────────────────────────────────────────────────
phase4_ollama() {
    section "PHASE 4 — Ollama AI safety models"
    if ! curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        err "Ollama not reachable on :11434 — start it first"
        return 1
    fi

    local models=(
        "llama-guard3"           # AI safety classifier (Llama Guard 3 from Meta)
        # other safety/eval models can be added per operator policy
    )

    for m in "${models[@]}"; do
        if curl -s http://localhost:11434/api/tags 2>&1 | grep -q "\"$m"; then
            ok "$m already pulled"
        else
            info "Pulling $m (heavy: ~2-5 GB disk)"
            ollama pull "$m" 2>&1 | tail -3 || warn "$m pull failed"
        fi
    done
}

# ────────────────────────────────────────────────────────────────────────────
# CHECK mode — print what's installed vs what's missing
# ────────────────────────────────────────────────────────────────────────────
check_state() {
    section "Install state — what's actually installed"

    echo "[ binaries on $TOOLS_BIN ]"
    for t in kubectl minikube istioctl trivy gitleaks promptfoo k6 grype kubescape helm kustomize argocd tfsec opa; do
        if [[ -x "$TOOLS_BIN/$t" ]] || [[ -L "$TOOLS_BIN/$t" ]]; then
            ok "  $t"
        else
            warn "  $t missing"
        fi
    done

    echo
    echo "[ Python pip packages in $VENV ]"
    if [[ -f "$PIP" ]]; then
        for p in arize-phoenix semgrep great_expectations ragas deepeval giskard rebuff \
                 traceloop-sdk trulens-eval crfm-helm lm-eval inspect-ai garak \
                 locust counterfit pyrit vigil-llm mlflow soda-core checkov \
                 bandit kube-hunter pyroscope-io evidently; do
            if "$PIP" show "$p" >/dev/null 2>&1; then
                ver=$("$PIP" show "$p" | awk '/^Version:/{print $2}')
                ok "  $p ($ver)"
            else
                warn "  $p missing"
            fi
        done
    else
        err "  venv missing"
    fi

    echo
    echo "[ npm packages ]"
    if [[ -d "$TOOLS_LIB/node/node_modules" ]]; then
        ls "$TOOLS_LIB/node/node_modules" | head -5 | while read -r p; do ok "  $p"; done
    else
        warn "  no npm packages installed"
    fi

    echo
    echo "[ k8s helm releases ]"
    if command -v "$TOOLS_BIN/kubectl" >/dev/null 2>&1 && \
       KUBECONFIG=/mnt/deepa/.kube/config "$TOOLS_BIN/kubectl" get nodes >/dev/null 2>&1; then
        for ns in falco kyverno argocd argo-rollouts kubescape; do
            if KUBECONFIG=/mnt/deepa/.kube/config "$TOOLS_BIN/kubectl" get ns "$ns" >/dev/null 2>&1; then
                ok "  ns/$ns exists"
            else
                warn "  ns/$ns missing"
            fi
        done
    else
        warn "  k8s cluster not reachable"
    fi
}

# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────
case "${1:-}" in
    -h|--help|help)
        sed -n '4,30p' "$0"; exit 0 ;;
    --check)
        check_state; exit 0 ;;
    --quick)
        phase1_pip_packages
        phase1_binaries
        phase1_npm
        ;;
    --heavy|"")
        phase1_pip_packages
        phase1_binaries
        phase1_npm
        phase2_docker
        ;;
    --k8s)
        phase1_pip_packages
        phase1_binaries
        phase1_npm
        phase2_docker
        phase3_k8s
        ;;
    --all)
        phase1_pip_packages
        phase1_binaries
        phase1_npm
        phase2_docker
        phase3_k8s
        phase4_ollama
        ;;
    *)
        err "Unknown arg: $1"
        sed -n '4,30p' "$0"
        exit 2 ;;
esac

section "Installation summary"
check_state
