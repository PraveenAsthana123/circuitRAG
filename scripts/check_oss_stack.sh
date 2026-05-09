#!/usr/bin/env bash
# check_oss_stack.sh — sanity-check OSS toolchain install state.
# Verifies repo-local .tools/bin binaries respond, minikube + kubectl
# are reachable, Ollama answers /api/tags. Read-only; safe to repeat.
case "${1:-}" in
  -h|--help)
    sed -n '2,5p' "$0" | sed 's/^# \?//'
    exit 0 ;;
esac
set -euo pipefail

ROOT="/mnt/deepa/rag"
TOOLS="$ROOT/.tools/bin"

export PATH="$TOOLS:$PATH"
export MINIKUBE_HOME="/mnt/deepa/.minikube"
export KUBECONFIG="/mnt/deepa/.kube/config"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

PASS=0
FAIL=0
WARN=0

ok() { echo "✅ $1"; PASS=$((PASS+1)); }
bad() { echo "❌ $1"; FAIL=$((FAIL+1)); }
warn() { echo "⚠️  $1"; WARN=$((WARN+1)); }

check_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "CLI found: $1 -> $(command -v "$1")"
  else
    bad "CLI missing: $1"
  fi
}

check_ns() {
  if kubectl get ns "$1" >/dev/null 2>&1; then
    ok "Namespace exists: $1"
  else
    bad "Namespace missing: $1"
  fi
}

check_helm() {
  if helm status "$1" -n "$2" >/dev/null 2>&1; then
    ok "Helm release deployed: $1 in namespace $2"
  else
    bad "Helm release missing/failed: $1 in namespace $2"
  fi
}

check_pods() {
  local ns="$1"
  echo ""
  echo "Pods in namespace: $ns"
  if kubectl get pods -n "$ns" >/dev/null 2>&1; then
    kubectl get pods -n "$ns"
    if kubectl get pods -n "$ns" --no-headers 2>/dev/null | grep -E "CrashLoopBackOff|ImagePullBackOff|ErrImagePull|Error|Pending" >/dev/null; then
      warn "Problem pods found in $ns"
    else
      ok "No obvious failed pods in $ns"
    fi
  else
    bad "Cannot read pods in $ns"
  fi
}

check_docker() {
  if docker ps --format '{{.Names}}' | grep -q "^$1$"; then
    ok "Docker container running: $1"
  else
    warn "Docker container not running: $1"
  fi
}

check_port() {
  if ss -tulnp | grep -q ":$1 "; then
    ok "Port in use/listening: $1"
  else
    warn "Port not listening: $1"
  fi
}

check_ollama_model() {
  if command -v ollama >/dev/null 2>&1 && ollama list | grep -q "$1"; then
    ok "Ollama model installed: $1"
  else
    warn "Ollama model missing: $1"
  fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OSS STACK HEALTH CHECK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "1. CLI tools"
check_cmd kubectl
check_cmd helm
check_cmd docker
check_cmd python3
check_cmd ollama || true

echo ""
echo "2. Cluster access"
if kubectl cluster-info >/dev/null 2>&1; then
  ok "Kubernetes cluster reachable"
else
  bad "Kubernetes cluster not reachable"
fi

echo ""
echo "3. Helm releases"
check_helm argocd argocd
check_helm kyverno kyverno
check_helm falco falco
check_helm openbao secrets
check_helm vault secrets
check_helm opencost cost
check_helm keda keda
check_helm argo-rollouts argo-rollouts
check_helm loki observability || true
check_helm tempo observability || true
check_helm kubecost cost || true

echo ""
echo "4. Namespaces"
for ns in argocd kyverno falco secrets cost keda argo-rollouts gatekeeper-system observability documind istio-system; do
  check_ns "$ns"
done

echo ""
echo "5. Pod status"
for ns in argocd kyverno falco secrets cost keda argo-rollouts gatekeeper-system observability documind istio-system; do
  if kubectl get ns "$ns" >/dev/null 2>&1; then
    check_pods "$ns"
  fi
done

echo ""
echo "6. Docker containers"
check_docker temporal
check_docker marquez
check_docker metabase
check_docker superset
check_docker redash
check_docker lightdash
check_docker dependency-track

echo ""
echo "7. Ports"
check_port 7233
check_port 8233
check_port 3100
check_port 8080
check_port 9090
check_port 18080
check_port 3000
check_port 8200

echo ""
echo "8. Ollama"
if curl -sf "$OLLAMA_BASE_URL/api/tags" >/dev/null 2>&1; then
  ok "Ollama reachable at $OLLAMA_BASE_URL"
else
  warn "Ollama not reachable at $OLLAMA_BASE_URL"
fi

check_ollama_model llama-guard3

echo ""
echo "9. Python packages"
python3 - <<'PY'
import importlib.util

packages = [
    "openlineage",
    "deepeval",
    "ragas",
    "giskard",
    "rebuff",
    "crewai",
    "dagster",
    "trulens",
]

for p in packages:
    if importlib.util.find_spec(p):
        print(f"✅ Python package found: {p}")
    else:
        print(f"⚠️  Python package missing: {p}")
PY

echo ""
echo "10. Current failed pods summary"
kubectl get pods -A | grep -E "CrashLoopBackOff|ImagePullBackOff|ErrImagePull|Error|Pending" || echo "✅ No obvious failed pods found"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PASS: $PASS"
echo "WARN: $WARN"
echo "FAIL: $FAIL"

if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: ❌ NOT READY"
  exit 1
elif [ "$WARN" -gt 0 ]; then
  echo "RESULT: ⚠️ PARTIALLY READY"
  exit 0
else
  echo "RESULT: ✅ READY"
  exit 0
fi
