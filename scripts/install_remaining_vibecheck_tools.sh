#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/deepa/rag"
TOOLS="$ROOT/.tools/bin"
CACHE="$ROOT/.tools/cache"
COMPOSE="$ROOT/ops-compose/docker-compose.remaining.yml"

export PATH="$TOOLS:$PATH"
export PIP_CACHE_DIR="$CACHE/pip"
export NPM_CONFIG_CACHE="$CACHE/npm"
export MINIKUBE_HOME="/mnt/deepa/.minikube"
export KUBECONFIG="/mnt/deepa/.kube/config"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

MODE="${1:---check}"

mkdir -p "$TOOLS" "$CACHE/pip" "$CACHE/npm" "$(dirname "$COMPOSE")"

log(){ echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n$1\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }

quick(){
  log "Quick Python installs"
  python3 -m pip install --upgrade pip || true
  python3 -m pip install \
    openlineage-python \
    openai-evals \
    crewai \
    dagster \
    vigil-llm \
    trulens \
    ragas \
    deepeval \
    rebuff || true

  python3 -m pip install giskard || echo "WARN: giskard may need Python 3.11/3.12"
}

helm_repos(){
  log "Helm repos"
  helm repo add argo https://argoproj.github.io/argo-helm || true
  helm repo add kubecost https://kubecost.github.io/cost-analyzer/ || true
  helm repo add kedacore https://kedacore.github.io/charts || true
  helm repo add cilium https://helm.cilium.io/ || true
  helm repo add aqua https://aquasecurity.github.io/helm-charts/ || true
  helm repo add litmuschaos https://litmuschaos.github.io/litmus-helm/ || true
  helm repo add grafana https://grafana.github.io/helm-charts || true
  helm repo update
}

k8s(){
  log "K8s installs"

  helm_repos

  kubectl create ns litmus --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install litmus litmuschaos/litmus \
    -n litmus || true

  kubectl create ns tetragon --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install tetragon cilium/tetragon \
    -n tetragon || true

  kubectl create ns tracee --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install tracee aqua/tracee \
    -n tracee || true

  kubectl create ns cost --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install kubecost kubecost/cost-analyzer \
    -n cost \
    --set global.clusterId=documind-cluster \
    --set kubecostProductConfigs.clusterName=documind-cluster || true

  kubectl create ns observability --dry-run=client -o yaml | kubectl apply -f -
  helm upgrade --install loki grafana/loki \
    -n observability \
    --set deploymentMode=SingleBinary \
    --set loki.auth_enabled=false \
    --set loki.commonConfig.replication_factor=1 \
    --set singleBinary.replicas=1 \
    --set read.replicas=0 \
    --set write.replicas=0 \
    --set backend.replicas=0 \
    --set loki.storage.type=filesystem \
    --set loki.useTestSchema=true || true
}

heavy(){
  log "Heavy Docker Compose stacks"

  cat > "$COMPOSE" <<'YAML'
services:
  temporal:
    image: temporalio/auto-setup:latest
    container_name: temporal
    ports:
      - "7233:7233"
      - "8233:8233"

  marquez:
    image: marquezproject/marquez:latest
    container_name: marquez
    ports:
      - "3101:3000"

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

  netdata:
    image: netdata/netdata:latest
    container_name: netdata
    ports:
      - "19999:19999"

  zabbix-server:
    image: zabbix/zabbix-server-pgsql:alpine-latest
    container_name: zabbix-server
    ports:
      - "10051:10051"

  nagios:
    image: jasonrivers/nagios:latest
    container_name: nagios
    ports:
      - "8086:80"
YAML

  docker compose -f "$COMPOSE" up -d || true
}

ollama_models(){
  log "Ollama models"
  if curl -sf "$OLLAMA_BASE_URL/api/tags" >/dev/null; then
    ollama pull llama-guard3 || true
  else
    echo "Ollama not reachable at $OLLAMA_BASE_URL"
  fi
}

check(){
  log "Remaining tool check"

  echo "Helm:"
  helm list -A | egrep 'loki|tempo|kubecost|litmus|tetragon|tracee|keda|argocd|falco|kyverno|openbao|vault' || true

  echo ""
  echo "Pods with issues:"
  kubectl get pods -A | grep -E 'CrashLoopBackOff|ImagePullBackOff|ErrImagePull|Pending|Error' || echo "No failed pods"

  echo ""
  echo "Docker:"
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | egrep 'temporal|marquez|metabase|superset|redash|lightdash|dependency-track|netdata|zabbix|nagios' || true

  echo ""
  echo "Python packages:"
  python3 - <<'PY'
import importlib.util
pkgs = ["openlineage", "crewai", "dagster", "trulens", "ragas", "deepeval", "rebuff", "giskard"]
for p in pkgs:
    print(("✅" if importlib.util.find_spec(p) else "❌"), p)
PY

  echo ""
  echo "Ollama:"
  ollama list | grep llama-guard3 || echo "❌ llama-guard3 missing"
}

case "$MODE" in
  --quick) quick ;;
  --k8s) k8s ;;
  --heavy) heavy ;;
  --ollama) ollama_models ;;
  --all) quick; k8s; heavy; ollama_models; check ;;
  --check) check ;;
  -h|--help)
    cat <<EOF
Usage: $0 [--quick|--k8s|--heavy|--ollama|--all|--check]

Install vibecheck tooling extras into repo-local .tools/bin/ + ops-compose/.

  --quick   Install lightweight Python + binary tools only
  --k8s     Install K8s tools (helm releases, etc.)
  --heavy   Install heavy ML deps (torch, transformers, etc.)
  --ollama  Pull Ollama models
  --all     Run --quick + --k8s + --heavy + --ollama + --check in order
  --check   Verify what is currently installed (read-only)
  -h, --help  Print this help
EOF
    exit 0 ;;
  *) echo "Usage: $0 [--quick|--k8s|--heavy|--ollama|--all|--check]"; exit 1 ;;
esac
