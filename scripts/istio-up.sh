#!/usr/bin/env bash
# Bring up a local minikube cluster + install Istio + apply the
# project's existing YAML manifests under infra/istio/ + infra/kiali/.
#
# Idempotent: re-running re-applies the YAMLs against the existing
# cluster. Does NOT install minikube/kubectl/istioctl — operator
# installs those separately (commands printed on missing-tool exit).
#
# Operator workflow:
#   bash scripts/istio-up.sh         # bring everything up
#   bash scripts/istio-down.sh       # tear it down
#   make istio-status                # check cluster + mesh state
#
# Locked by mcp/tests/drill_minikube_istio_setup.py.

case "${1:-}" in
  -h|--help)
    cat <<'HELP'
istio-up.sh — bring up local minikube + install Istio + apply project manifests

Idempotent: re-running re-applies infra/istio/ + infra/kiali/ YAMLs
against the existing cluster. Does NOT install minikube / kubectl /
istioctl — operator installs those separately (commands printed on
missing-tool exit).

Usage:
  bash scripts/istio-up.sh         # bring everything up
  bash scripts/istio-down.sh       # tear it down
  make istio-status                # check cluster + mesh state

Env knobs:
  ISTIO_VERSION       (default 1.22.0)
  MINIKUBE_PROFILE    (default documind)
  MINIKUBE_MEMORY     (default 6144)
  MINIKUBE_CPUS       (default 4)
  ISTIO_NAMESPACE     (default documind)

Locked by mcp/tests/drill_minikube_istio_setup.py.
HELP
    exit 0
    ;;
esac

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ISTIO_VERSION="${ISTIO_VERSION:-1.22.0}"
MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-documind}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-6144}"
MINIKUBE_CPUS="${MINIKUBE_CPUS:-4}"
NAMESPACE="${ISTIO_NAMESPACE:-documind}"

color()  { local c="$1"; shift; printf "\033[${c}m%s\033[0m\n" "$*"; }
ok()     { color "32" "✓ $*"; }
info()   { color "36" "ℹ $*"; }
warn()   { color "33" "⚠ $*"; }
err()    { color "31" "✗ $*" >&2; }

require_tool() {
    local tool="$1"; local install_hint="$2"
    if ! command -v "$tool" >/dev/null 2>&1; then
        err "missing required tool: $tool"
        echo "    install: $install_hint"
        exit 2
    fi
}

# ---- 1. Tool check ---------------------------------------------------
info "Checking required tools..."
require_tool minikube "https://minikube.sigs.k8s.io/docs/start/  (or 'brew install minikube' on macOS)"
require_tool kubectl  "https://kubernetes.io/docs/tasks/tools/   (or 'brew install kubectl' on macOS)"

ISTIOCTL="${ISTIOCTL:-istioctl}"
if ! command -v "$ISTIOCTL" >/dev/null 2>&1; then
    warn "istioctl not on PATH; will fetch ${ISTIO_VERSION} into ./istio-${ISTIO_VERSION}/"
    if [ ! -d "${REPO_ROOT}/istio-${ISTIO_VERSION}" ]; then
        cd "${REPO_ROOT}"
        curl -L https://istio.io/downloadIstio | ISTIO_VERSION="${ISTIO_VERSION}" sh -
    fi
    ISTIOCTL="${REPO_ROOT}/istio-${ISTIO_VERSION}/bin/istioctl"
fi
ok "tools resolved (istioctl=$ISTIOCTL)"

# ---- 2. minikube ------------------------------------------------------
info "Starting minikube profile=$MINIKUBE_PROFILE..."
if minikube -p "$MINIKUBE_PROFILE" status >/dev/null 2>&1; then
    ok "minikube profile $MINIKUBE_PROFILE already running"
else
    minikube start \
        -p "$MINIKUBE_PROFILE" \
        --memory="$MINIKUBE_MEMORY" \
        --cpus="$MINIKUBE_CPUS" \
        --driver=docker
    minikube -p "$MINIKUBE_PROFILE" addons enable ingress
    ok "minikube profile $MINIKUBE_PROFILE up"
fi

kubectl config use-context "$MINIKUBE_PROFILE" >/dev/null

# ---- 3. Istio install -------------------------------------------------
info "Installing Istio ${ISTIO_VERSION} (profile=demo)..."
if kubectl get ns istio-system >/dev/null 2>&1 \
    && kubectl -n istio-system get pods -l app=istiod 2>/dev/null | grep -q Running; then
    ok "istiod already running in istio-system"
else
    "$ISTIOCTL" install --set profile=demo -y
    ok "istiod installed"
fi

# ---- 4. Project namespace + sidecar injection ------------------------
info "Creating namespace $NAMESPACE with Istio sidecar injection..."
kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE"
kubectl label ns "$NAMESPACE" istio-injection=enabled --overwrite
ok "namespace $NAMESPACE labeled istio-injection=enabled"

# ---- 5. Apply project YAMLs ------------------------------------------
info "Applying infra/istio/ + infra/kiali/ manifests..."
kubectl apply -f "${REPO_ROOT}/infra/istio/" --recursive
kubectl apply -f "${REPO_ROOT}/infra/kiali/" --recursive
ok "manifests applied"

# ---- 6. Verify --------------------------------------------------------
info "Verifying state..."
kubectl -n istio-system get pods --no-headers | head -5
echo
kubectl -n "$NAMESPACE" get authorizationpolicies --no-headers 2>/dev/null | head -10 \
    || warn "no AuthorizationPolicies in $NAMESPACE yet"

ok "Istio + project manifests up. Useful commands:"
cat <<EOM

  kubectl -n $NAMESPACE get pods                        # see app pods (when deployed)
  kubectl -n $NAMESPACE get authorizationpolicies       # confirm authz YAMLs landed
  $ISTIOCTL -n $NAMESPACE proxy-status                  # mesh sync state
  $ISTIOCTL -n $NAMESPACE analyze                       # config sanity
  minikube -p $MINIKUBE_PROFILE dashboard               # k8s dashboard
  bash scripts/istio-down.sh                            # tear down

To run the full app stack ON the mesh, build images into the minikube
docker daemon (eval \$(minikube -p $MINIKUBE_PROFILE docker-env)) then
kubectl apply your deployments. Phase-1 dev-mode (services natively
on host) does NOT exercise the mesh — that is the intended split.

EOM
