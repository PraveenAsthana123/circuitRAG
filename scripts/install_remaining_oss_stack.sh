#!/usr/bin/env bash
# install_remaining_oss_stack.sh — install the OSS tools NOT covered
# by install_ops_stack.sh: docker-compose extras + Python toolchain
# extras + npm CLI tools. Idempotent. Targets .tools/bin/ + ops-compose/.
case "${1:-}" in
  -h|--help)
    sed -n '2,4p' "$0" | sed 's/^# \?//'
    exit 0 ;;
esac
set -euo pipefail

ROOT="/mnt/deepa/rag"
TOOLS="$ROOT/.tools/bin"
CACHE="$ROOT/.tools/cache"
COMPOSE_DIR="$ROOT/ops-compose"

export PATH="$TOOLS:$PATH"
export PIP_CACHE_DIR="$CACHE/pip"
export NPM_CONFIG_CACHE="$CACHE/npm"
export MINIKUBE_HOME="/mnt/deepa/.minikube"
export KUBECONFIG="/mnt/deepa/.kube/config"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

MODE="${1:---base}"

mkdir -p "$TOOLS" "$CACHE/pip" "$CACHE/npm" "$COMPOSE_DIR"

log() { echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n$1\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }
has() { command -v "$1" >/dev/null 2>&1; }

log "0. Pre-check"

cd "$ROOT"

if ! has python3; then echo "python3 missing"; exit 1; fi
if ! has docker; then echo "docker missing"; exit 1; fi
if ! has kubectl; then echo "kubectl missing from PATH"; exit 1; fi
if ! has helm; then echo "helm missing from PATH"; exit 1; fi

kubectl cluster-info >/dev/null || echo "WARN: kubectl cluster not reachable"
docker ps >/dev/null || { echo "docker not running"; exit 1; }

log "1. Python OSS tools"

python3 -m pip install --upgrade pip

python3 -m pip install \
  openlineage-python \
  deepeval \
  ragas \
  giskard \
  openai-evals \
  crewai \
  dagster \
  trulens \
  inspect-ai \
  lm-eval \
  garak \
  pyrit \
  counterfit || true

python3 -m pip install rebuff || echo "WARN: rebuff dependency conflict; skipped"

log "2. Helm repos"

helm repo add argo https://argoproj.github.io/argo-helm || true
helm repo add kyverno https://kyverno.github.io/kyverno/ || true
helm repo add falcosecurity https://falcosecurity.github.io/charts || true
helm repo add hashicorp https://helm.releases.hashicorp.com || true
helm repo add openbao https://openbao.github.io/openbao-helm || true
helm repo add kubecost https://kubecost.github.io/cost-analyzer/ || true
helm repo add opencost https://opencost.github.io/opencost-helm-chart || true
helm repo add kedacore https://kedacore.github.io/charts || true
helm repo add argo-rollouts https://argoproj.github.io/argo-helm || true
helm repo add grafana https://grafana.github.io/helm-charts || true
helm repo add deliveryhero https://charts.deliveryhero.io/ || true
helm repo update

log "3. Core Kubernetes tools"

kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argocd argo/argo-cd -n argocd

kubectl create namespace kyverno --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install kyverno kyverno/kyverno -n kyverno

kubectl create namespace falco --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install falco falcosecurity/falco -n falco --set falcosidekick.enabled=false

kubectl create namespace secrets --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install openbao openbao/openbao -n secrets --set server.dev.enabled=true
helm upgrade --install vault hashicorp/vault -n secrets --set server.dev.enabled=true --set injector.enabled=false || true

kubectl create namespace cost --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install opencost opencost/opencost -n cost || true
helm upgrade --install kubecost kubecost/cost-analyzer -n cost || true

kubectl create namespace keda --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install keda kedacore/keda -n keda

kubectl create namespace argo-rollouts --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argo-rollouts argo/argo-rollouts -n argo-rollouts

log "4. Gatekeeper"

kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/master/deploy/gatekeeper.yaml || true

log "5. Loki + Tempo"

kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install loki grafana/loki -n observability || true
helm upgrade --install tempo grafana/tempo -n observability || true

log "6. Temporal local Docker fallback"

if ! docker ps --format '{{.Names}}' | grep -q '^temporal$'; then
  docker rm -f temporal >/dev/null 2>&1 || true
  docker run -d \
    --name temporal \
    -p 7233:7233 \
    -p 8233:8233 \
    temporalio/auto-setup:latest || true
fi

log "7. Marquez local Docker"

if ! docker ps --format '{{.Names}}' | grep -q '^marquez$'; then
  docker rm -f marquez >/dev/null 2>&1 || true
  docker run -d \
    --name marquez \
    -p 3100:3000 \
    marquezproject/marquez:latest || true
fi

log "8. Llama Guard optional"

if [[ "$MODE" == "--all" || "$MODE" == "--ollama" ]]; then
  if curl -sf "$OLLAMA_BASE_URL/api/tags" >/dev/null; then
    ollama pull llama-guard3 || true
  else
    echo "Ollama not reachable at $OLLAMA_BASE_URL; skipping llama-guard3"
  fi
else
  echo "Skipping llama-guard3. Use: $0 --ollama"
fi

log "9. Heavy Docker Compose stacks optional"

if [[ "$MODE" == "--all" || "$MODE" == "--heavy" ]]; then
  cat > "$COMPOSE_DIR/docker-compose.heavy.yml" <<'YAML'
services:
  metabase:
    image: metabase/metabase:latest
    container_name: metabase
    ports:
      - "3300:3000"

  superset:
    image: apache/superset:latest
    container_name: superset
    ports:
      - "8089:8088"
    environment:
      - SUPERSET_SECRET_KEY=local-dev-secret
    command: >
      /bin/sh -c "superset db upgrade &&
                  superset fab create-admin --username admin --firstname admin --lastname user --email admin@example.com --password admin || true &&
                  superset init &&
                  superset run -h 0.0.0.0 -p 8088"

  redash:
    image: redash/redash:latest
    container_name: redash
    ports:
      - "5001:5000"

  lightdash:
    image: lightdash/lightdash:latest
    container_name: lightdash
    ports:
      - "8087:8080"

  dependency-track:
    image: dependencytrack/apiserver:latest
    container_name: dependency-track
    ports:
      - "8081:8080"
YAML

  docker compose -f "$COMPOSE_DIR/docker-compose.heavy.yml" up -d || true
else
  echo "Skipping heavy BI/metadata stacks. Use: $0 --heavy"
fi

log "10. Check status"

echo "Helm releases:"
helm list -A || true

echo ""
echo "Kubernetes pods:"
kubectl get pods -A | egrep "argocd|kyverno|falco|openbao|vault|gatekeeper|opencost|kubecost|keda|rollouts|loki|tempo" || true

echo ""
echo "Docker containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | egrep "temporal|marquez|metabase|superset|redash|lightdash|dependency" || true

echo ""
echo "DONE"
