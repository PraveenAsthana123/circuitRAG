#!/usr/bin/env bash
# Tear down the local minikube cluster created by scripts/istio-up.sh.
#
# Default: deletes the documind minikube profile. The Istio control
# plane goes with it; project YAMLs remain on disk.
#
# Operator workflow:
#   bash scripts/istio-down.sh                 # delete documind profile
#   MINIKUBE_PROFILE=other bash scripts/istio-down.sh  # custom profile

set -euo pipefail

MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-documind}"

color()  { local c="$1"; shift; printf "\033[${c}m%s\033[0m\n" "$*"; }
ok()     { color "32" "✓ $*"; }
info()   { color "36" "ℹ $*"; }
warn()   { color "33" "⚠ $*"; }

if ! command -v minikube >/dev/null 2>&1; then
    warn "minikube not on PATH; nothing to delete"
    exit 0
fi

if minikube -p "$MINIKUBE_PROFILE" status >/dev/null 2>&1; then
    info "Stopping + deleting minikube profile $MINIKUBE_PROFILE..."
    minikube -p "$MINIKUBE_PROFILE" stop  || true
    minikube -p "$MINIKUBE_PROFILE" delete --purge
    ok "$MINIKUBE_PROFILE removed"
else
    warn "minikube profile $MINIKUBE_PROFILE not running; nothing to delete"
fi
