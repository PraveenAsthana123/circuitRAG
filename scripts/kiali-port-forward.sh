#!/bin/bash
# Port-forward Kiali (running inside minikube/dm-istio) to host:20001
# so the frontend BFF (services/frontend/app/api/v1/integrations-health)
# can reach Kiali at http://localhost:20001/kiali for the all-green
# tools-launcher status surface.
#
# Why this script exists:
#   Kiali v1.86 hard-blocks startup outside a real K8s API (the
#   docker-compose mesh-profile container crash-loops on
#   "unable to load in-cluster configuration"). The canonical install
#   is the official Istio kiali addon manifest applied INSIDE the
#   cluster. To probe it from the docker-compose frontend, we
#   port-forward the in-cluster ClusterIP service to a host port.
#
# Idempotent: kills any existing port-forward before starting a new one.
# Drilled by mcp/tests/drill_kiali_integration.py.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECTL="$REPO_ROOT/.tools/bin/kubectl"
KUBECONFIG_PATH="${KUBECONFIG:-/mnt/deepa/.kube/config}"
MINIKUBE_CTX="${MINIKUBE_PROFILE:-dm-istio}"
HOST_PORT="${KIALI_HOST_PORT:-20001}"
LOG_FILE="${KIALI_PF_LOG:-/tmp/kiali-pf.log}"

if [[ ! -x "$KUBECTL" ]]; then
  echo "ERROR: kubectl not found at $KUBECTL — run scripts/istio-up.sh first" >&2
  exit 1
fi

if ! "$KUBECTL" --context="$MINIKUBE_CTX" --kubeconfig="$KUBECONFIG_PATH" \
    -n istio-system get svc/kiali >/dev/null 2>&1; then
  echo "ERROR: kiali svc not found in istio-system on context $MINIKUBE_CTX" >&2
  echo "       Run: kubectl --context=$MINIKUBE_CTX apply -f \\" >&2
  echo "         https://raw.githubusercontent.com/istio/istio/release-1.22/samples/addons/kiali.yaml" >&2
  exit 1
fi

# Idempotent: kill any stale port-forward on the same target.
pkill -f "kubectl.*port-forward.*svc/kiali.*${HOST_PORT}:20001" 2>/dev/null || true
sleep 1

nohup "$KUBECTL" --context="$MINIKUBE_CTX" --kubeconfig="$KUBECONFIG_PATH" \
    -n istio-system port-forward svc/kiali "${HOST_PORT}:20001" \
    --address=0.0.0.0 \
    > "$LOG_FILE" 2>&1 &

PF_PID=$!
echo "Started kubectl port-forward kiali (pid=$PF_PID), log=$LOG_FILE"

# Verify ≤30s.
for i in $(seq 1 15); do
  if curl -sf -o /dev/null "http://localhost:${HOST_PORT}/kiali/healthz" 2>/dev/null; then
    echo "Kiali reachable: http://localhost:${HOST_PORT}/kiali/"
    exit 0
  fi
  sleep 2
done

echo "ERROR: Kiali port-forward did not become reachable on :${HOST_PORT} within 30s" >&2
echo "       Last 20 lines of $LOG_FILE:" >&2
tail -20 "$LOG_FILE" >&2
exit 1
