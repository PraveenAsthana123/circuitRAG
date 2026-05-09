#!/bin/bash
# Install / activate the 53 pending tools from the canonical catalog.
#
# Categories of pending:
#   python       — pip install in .venv (py3.12)
#   github       — pip install git+... (counterfit, openai-evals-oss)
#   binaries     — CLI tools to .tools/bin/ (bandit, checkov, semgrep, etc.)
#   helm         — helm install in current K8s context (argo-cd, falco, etc.)
#   compose      — docker compose service additions (dagster, marquez, etc.)
#   manual       — needs explicit product decision (llama-guard model,
#                  eBPF agents tetragon/tracee, all 30 'planned' rows)
#
# Default: --dry-run prints the plan but installs nothing.
# Per category: bash scripts/install_pending_tools.sh --batch python
# All cheap wins: bash scripts/install_pending_tools.sh --batch python,binaries,github
# Everything (incl. helm cluster ops): bash scripts/install_pending_tools.sh --batch all
#
# Per CLAUDE.md §42 (gated operations) + §50.5.3 (security never to model)
# + §57.7 (honest about manual-decision rows).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

DRY_RUN=true
BATCHES=""
KUBECONFIG="${KUBECONFIG:-/mnt/deepa/.kube/config}"
MINIKUBE_CTX="${MINIKUBE_PROFILE:-dm-istio}"

for arg in "$@"; do
  case "$arg" in
    --dry-run)         DRY_RUN=true ;;
    --apply)           DRY_RUN=false ;;
    --batch=*)         BATCHES="${arg#--batch=}"; DRY_RUN=false ;;
    --batch)           shift; BATCHES="${1:-}"; DRY_RUN=false ;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0 ;;
  esac
  shift 2>/dev/null || true
done

GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; GRAY='\033[90m'
BOLD='\033[1m'; NC='\033[0m'

run_or_print() {
  local label="$1"; shift
  if $DRY_RUN; then
    echo -e "  ${GRAY}DRY-RUN  ${label}${NC}"
    echo -e "  ${GRAY}         $*${NC}"
  else
    echo -e "  ${BOLD}${label}${NC}"
    if "$@"; then
      echo -e "    ${GREEN}✓ ok${NC}"
    else
      echo -e "    ${RED}✗ failed (continuing)${NC}"
    fi
  fi
}

want_batch() {
  [[ "$BATCHES" == "all" ]] && return 0
  [[ ",$BATCHES," == *",$1,"* ]] && return 0
  return 1
}

if $DRY_RUN; then
  echo -e "${BOLD}=== DRY-RUN — pass --batch=<name>[,<name>...] to apply ===${NC}"
  echo "Categories: python | binaries | github | helm | compose | all"
  echo
fi

# ─── 1. PYTHON PACKAGES (pip in .venv py3.12) ────────────────────────
if want_batch python || $DRY_RUN; then
  echo -e "\n${BOLD}── 1. Python red-team tools (ISOLATED venv: .venv-redteam) ──${NC}"
  echo -e "  ${YELLOW}garak + pyrit pin newer pydantic/numpy/openai/scipy that conflict${NC}"
  echo -e "  ${YELLOW}with rebuff/giskard/inspect_ai. Installing into a separate venv.${NC}"
  if want_batch python; then
    if [[ ! -x .venv-redteam/bin/python ]]; then
      echo -e "  ${BOLD}Creating .venv-redteam${NC}"
      python3.12 -m venv .venv-redteam || python3 -m venv .venv-redteam
    fi
  fi
  run_or_print "garak (LLM red-team probes)" \
    .venv-redteam/bin/pip install garak
  run_or_print "pyrit (Microsoft AI red-team)" \
    .venv-redteam/bin/pip install pyrit
  echo -e "  ${GRAY}vigil-llm: SKIPPED — not on PyPI under that name (catalog typo;${NC}"
  echo -e "  ${GRAY}  see https://github.com/deadbits/vigil-llm — install manually if needed)${NC}"
fi

# ─── 2. GITHUB-ONLY PYTHON ───────────────────────────────────────────
if want_batch github || $DRY_RUN; then
  echo -e "\n${BOLD}── 2. GitHub-only Python (.venv-redteam) ──${NC}"
  echo -e "  ${GRAY}counterfit: SKIPPED — pins ancient h5py==3.1.0 + numpy==1.19.3${NC}"
  echo -e "  ${GRAY}  which won't build on py3.12. Project archived 2024; not maintainable.${NC}"
  if want_batch github && [[ ! -x .venv-redteam/bin/python ]]; then
    python3.12 -m venv .venv-redteam || python3 -m venv .venv-redteam
  fi
  run_or_print "openai-evals (OpenAI eval framework)" \
    .venv-redteam/bin/pip install "git+https://github.com/openai/evals.git"
fi

# ─── 3. CLI BINARIES (download to .tools/bin/) ───────────────────────
if want_batch binaries || $DRY_RUN; then
  echo -e "\n${BOLD}── 3. CLI binaries (→ .venv via pip) ──${NC}"
  mkdir -p .tools/bin
  run_or_print "bandit (Python SAST)" \
    .venv/bin/pip install bandit
  run_or_print "checkov (IaC scanner)" \
    .venv/bin/pip install checkov
  run_or_print "semgrep (multi-language SAST)" \
    .venv/bin/pip install semgrep
  run_or_print "locust (load generator)" \
    .venv/bin/pip install locust
  run_or_print "soda-core (data-quality)" \
    .venv/bin/pip install soda-core
  run_or_print "kube-hunter (k8s pen-test)" \
    .venv/bin/pip install kube-hunter
fi

# ─── 4. HELM RELEASES (in current k8s context) ──────────────────────
if want_batch helm || $DRY_RUN; then
  echo -e "\n${BOLD}── 4. Helm releases (k8s context: ${MINIKUBE_CTX}) ──${NC}"
  HELM=.tools/bin/helm
  [[ -x "$HELM" ]] || HELM=$(command -v helm) || HELM="helm"
  if want_batch helm && [[ -x "$HELM" || "$(command -v helm)" ]]; then
    export KUBECONFIG
    $HELM repo add argo https://argoproj.github.io/argo-helm 2>/dev/null || true
    $HELM repo add falcosecurity https://falcosecurity.github.io/charts 2>/dev/null || true
    $HELM repo add kedacore https://kedacore.github.io/charts 2>/dev/null || true
    $HELM repo add kyverno https://kyverno.github.io/kyverno/ 2>/dev/null || true
    $HELM repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
    $HELM repo add openbao https://openbao.github.io/openbao-helm 2>/dev/null || true
    $HELM repo add opencost https://opencost.github.io/opencost-helm-chart 2>/dev/null || true
    $HELM repo update >/dev/null 2>&1
  fi
  run_or_print "argo-cd"          $HELM upgrade --install argo-cd argo/argo-cd -n argocd --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "argo-rollouts"    $HELM upgrade --install argo-rollouts argo/argo-rollouts -n argo-rollouts --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "falco"            $HELM upgrade --install falco falcosecurity/falco -n falco --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "keda"             $HELM upgrade --install keda kedacore/keda -n keda --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "kyverno"          $HELM upgrade --install kyverno kyverno/kyverno -n kyverno --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "loki"             $HELM upgrade --install loki grafana/loki -n loki --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "tempo"            $HELM upgrade --install tempo grafana/tempo -n tempo --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "openbao"          $HELM upgrade --install openbao openbao/openbao -n openbao --create-namespace --kube-context="$MINIKUBE_CTX"
  run_or_print "opencost"         $HELM upgrade --install opencost opencost/opencost -n opencost --create-namespace --kube-context="$MINIKUBE_CTX"
fi

# ─── 5. DOCKER-COMPOSE SERVICES (need compose entries) ──────────────
if want_batch compose || $DRY_RUN; then
  echo -e "\n${BOLD}── 5. docker-compose services (NEED compose entries — manual edit) ──${NC}"
  echo -e "  ${YELLOW}These need docker-compose.yml entries before starting:${NC}"
  echo "    dagster                — pip install dagster + compose svc on :3055"
  echo "    marquez                — compose svc on :5000 (collides with MLflow default)"
  echo "    opensearch-dashboards  — compose svc on :5602"
  echo "    pyroscope              — compose svc on :4040"
  echo
  echo -e "  ${YELLOW}Skipping (operator decision: do you want all 4 added to compose?)${NC}"
fi

# ─── 6. MANUAL — explicit product decisions ──────────────────────────
if want_batch manual || $DRY_RUN; then
  echo -e "\n${BOLD}── 6. Manual / product decisions (NOT auto-installed) ──${NC}"
  cat <<'EOF'
  llama-guard (HuggingFace model, not a pip pkg):
    HF_HUB_DOWNLOAD_TIMEOUT=300 python -c "from transformers import AutoModelForCausalLM; \
      AutoModelForCausalLM.from_pretrained('meta-llama/Llama-Guard-2-8B')"
    (requires HF_TOKEN with Llama gated-model access)

  tetragon + tracee (eBPF kernel agents):
    Need root + matching kernel headers + careful security review.
    Recommend running as DaemonSet in K8s, not on dev box. Skipped here.

  wazuh:
    K8s deployment with namespace 'wazuh' missing. Run:
      kubectl create namespace wazuh
      helm install wazuh wazuh/wazuh -n wazuh
    (requires wazuh helm repo + indexer + manager nodes — heavy)

  30 "planned" rows in catalog (agentsight, airflow, datahub, etc.):
    These are deliberate not-yet-deployed product decisions. Each
    needs a per-tool review before adoption. Don't bulk-install.
EOF
fi

# ─── Re-probe after install ─────────────────────────────────────────
if ! $DRY_RUN; then
  echo -e "\n${BOLD}── 7. Re-probe catalog (via .venv/bin/python) ──${NC}"
  .venv/bin/python scripts/catalog_tools_probe.py 2>&1 \
    | grep -E "^=== TOOLS-CATALOG|counts:" | head -3
  echo
  echo "Full result: .venv/bin/python scripts/catalog_tools_probe.py"
fi

echo
if $DRY_RUN; then
  echo -e "${BOLD}${GRAY}=== DRY-RUN complete — pass --batch to apply ===${NC}"
  echo "  bash scripts/install_pending_tools.sh --batch=python,github,binaries"
  echo "  bash scripts/install_pending_tools.sh --batch=helm"
  echo "  bash scripts/install_pending_tools.sh --batch=all"
else
  echo -e "${BOLD}${GREEN}=== install batch '$BATCHES' complete ===${NC}"
fi
