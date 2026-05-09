#!/usr/bin/env bash
# install_ops_stack.sh — install repo-local OSS ops binaries into
# .tools/bin/ (kubectl, minikube, helm, k6, gitleaks, trivy, etc.).
# Idempotent: skips already-present binaries. Per CLAUDE.md §50.5
# (no system-drive install — use .tools/bin only).
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

mkdir -p "$TOOLS"

echo "== 0. Pre-check =="
kubectl cluster-info
docker ps >/dev/null

echo "== 1. Add Helm repos =="
helm repo add argo https://argoproj.github.io/argo-helm || true
helm repo add temporal https://go.temporal.io/helm-charts || true
helm repo add falcosecurity https://falcosecurity.github.io/charts || true
helm repo add kyverno https://kyverno.github.io/kyverno/ || true
helm repo add openlineage https://openlineage.github.io/helm-charts || true
helm repo add openmetadata https://helm.open-metadata.org/ || true
helm repo add openbao https://openbao.github.io/openbao-helm || true
helm repo add hashicorp https://helm.releases.hashicorp.com || true
helm repo add wazuh https://wazuh.github.io/wazuh-kubernetes || true
helm repo update

echo "== 2. Argo CD =="
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argocd argo/argo-cd \
  -n argocd \
  --set server.service.type=ClusterIP

echo "== 3. Temporal =="
kubectl create namespace temporal --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install temporal temporal/temporal \
  -n temporal \
  --set server.replicaCount=1 \
  --set cassandra.enabled=false \
  --set mysql.enabled=false \
  --set postgresql.enabled=true \
  --set prometheus.enabled=false \
  --set grafana.enabled=false \
  --set elasticsearch.enabled=false

echo "== 4. Kyverno =="
kubectl create namespace kyverno --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install kyverno kyverno/kyverno \
  -n kyverno \
  --set admissionController.replicas=1 \
  --set backgroundController.replicas=1 \
  --set cleanupController.replicas=1 \
  --set reportsController.replicas=1

echo "== 5. Falco =="
kubectl create namespace falco --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install falco falcosecurity/falco \
  -n falco \
  --set tty=true \
  --set falcosidekick.enabled=false

echo "== 6. Marquez / OpenLineage =="
kubectl create namespace lineage --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install marquez openlineage/marquez \
  -n lineage

echo "== 7. OpenBao =="
kubectl create namespace secrets --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install openbao openbao/openbao \
  -n secrets \
  --set server.dev.enabled=true \
  --set injector.enabled=false

echo "== 8. Vault optional install =="
helm upgrade --install vault hashicorp/vault \
  -n secrets \
  --set server.dev.enabled=true \
  --set injector.enabled=false

echo "== 9. Llama Guard via Ollama =="
if curl -sf "$OLLAMA_BASE_URL/api/tags" >/dev/null; then
  ollama pull llama-guard3 || true
else
  echo "Ollama not reachable at $OLLAMA_BASE_URL, skipping llama-guard3"
fi

echo "== 10. Optional heavy stack: OpenMetadata =="
if [[ "${INSTALL_HEAVY:-false}" == "true" ]]; then
  kubectl create namespace metadata --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install openmetadata openmetadata/openmetadata \
    -n metadata
else
  echo "Skipping OpenMetadata. Run with INSTALL_HEAVY=true to install."
fi

echo "== 11. Optional heavy stack: Wazuh SIEM =="
if [[ "${INSTALL_HEAVY:-false}" == "true" ]]; then
  kubectl create namespace wazuh --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install wazuh wazuh/wazuh \
    -n wazuh || true
else
  echo "Skipping Wazuh. Run with INSTALL_HEAVY=true to install."
fi

echo "== 12. Status =="
kubectl get pods -A | egrep "argocd|temporal|kyverno|falco|lineage|marquez|openbao|vault|metadata|wazuh" || true

echo "DONE"
