# Istio local deploy — minikube + istioctl + project YAMLs

> Brings the existing `infra/istio/` + `infra/kiali/` YAMLs from
> documentation-as-code to actually-running on a local minikube
> cluster. NOT for production.
>
> Locked by `mcp/tests/drill_minikube_istio_setup.py`.

## Prerequisites (operator installs once)

| Tool | Install |
| --- | --- |
| **minikube** | `https://minikube.sigs.k8s.io/docs/start/` (Linux: `curl -LO ...minikube-linux-amd64 && sudo install minikube-linux-amd64 /usr/local/bin/minikube`) |
| **kubectl** | `https://kubernetes.io/docs/tasks/tools/` |
| **docker** (driver) | already installed (compose stack uses it) |
| **istioctl** | optional — `istio-up.sh` will fetch v1.22.0 into `./istio-1.22.0/` if absent |

## Bring up

```bash
bash scripts/istio-up.sh
```

What it does (idempotent):

1. Tool check — fails fast with install hints if minikube/kubectl missing
2. `minikube start -p documind --memory=6144 --cpus=4 --driver=docker`
3. Enables the `ingress` addon
4. `istioctl install --set profile=demo -y` (skips if istiod already running)
5. Creates namespace `documind` with `istio-injection=enabled` label
6. `kubectl apply -f infra/istio/` (the existing AuthorizationPolicy +
   PeerAuthentication + VirtualService + DestinationRule + Telemetry YAMLs)
7. `kubectl apply -f infra/kiali/` (Kiali config map)
8. Prints next-step commands

Resource use: ~6 GB RAM + 4 CPU for the cluster. Adjust via:
```bash
MINIKUBE_MEMORY=4096 MINIKUBE_CPUS=2 bash scripts/istio-up.sh
```

## Verify

```bash
# Mesh control plane up?
kubectl -n istio-system get pods

# Project AuthorizationPolicies applied?
kubectl -n documind get authorizationpolicies

# Sidecar injection working? (requires app pods deployed; see below)
istioctl -n documind proxy-status

# Config validity
istioctl -n documind analyze
```

## Deploy app pods on the mesh (optional Phase 2)

Phase 1 (current default) runs services natively on the host (per
docker-compose.yml header philosophy). The mesh is empty until you
deploy app pods to the cluster.

To exercise the mesh end-to-end:

```bash
# 1. Point your shell's docker at minikube's daemon
eval $(minikube -p documind docker-env)

# 2. Build images (will land in minikube's docker, not host)
docker build -t documind/api-gateway:dev -f services/api-gateway/Dockerfile .

# 3. Apply k8s deployments (NOT in repo today; would need infra/k8s/)
kubectl -n documind apply -f infra/k8s/  # ← does not exist yet
```

The `infra/k8s/` directory is referenced in `docker-compose.yml` but
not present. That's the next iteration if you want full mesh exercise.
For now, the `infra/istio/` YAMLs are validated by `istioctl analyze`
but no app pods consume them.

## Tear down

```bash
bash scripts/istio-down.sh
```

Deletes the `documind` minikube profile entirely. Project YAMLs
remain on disk; re-running `istio-up.sh` re-creates the cluster from
scratch.

## What this gets you vs the docker-compose stack

| Capability | docker-compose | minikube + istio |
| --- | --- | --- |
| Service-level mTLS | ❌ | ✅ (PeerAuthentication STRICT after PERMISSIVE soak) |
| Mesh-internal authz | ❌ | ✅ (AuthorizationPolicy YAMLs enforced) |
| Per-service traffic policy | NGINX upstream only | ✅ (DestinationRule retry budget + outlier detection) |
| Kiali visualization | container running but no data | ✅ (queries istiod for mesh state) |
| Edge TLS termination | ✅ NGINX | (would also be ingress gateway in Istio profile=production) |
| Cost | low (single host) | high (cluster overhead ~6 GB RAM) |
| Operational complexity | medium | high |

**Recommendation**: stay on docker-compose for daily dev. Spin up
minikube + Istio when:
- Testing the AuthorizationPolicy YAMLs against real mesh enforcement
- Reproducing a production-like mesh issue
- Demonstrating Istio's value to stakeholders

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `minikube start` hangs > 5 min | docker daemon not running OR insufficient memory | `systemctl status docker`; reduce MINIKUBE_MEMORY |
| `istioctl install` fails on TLS | corporate proxy intercepting cert | set `HTTPS_PROXY` + `NO_PROXY=192.168.49.0/24` |
| `kubectl apply` rejects YAML | Istio CRDs not yet ready | re-run `istio-up.sh` (idempotent); CRD install completes async |
| Sidecar not injecting | namespace label missing | `kubectl label ns documind istio-injection=enabled --overwrite` |
| Out of memory | minikube + istio + browser is heavy | `MINIKUBE_MEMORY=4096` + close other apps |

## Composes with

- `docs/runbooks/alertmanager-webhook.md` — same chmod-600 + .loop/
  secret pattern (not used by Istio but operationally adjacent)
- `/admin/service-mesh/deep` — narrative that this runbook makes runnable
- `infra/istio/50-authorization.yaml` — the canonical authz YAML this
  runbook deploys
- `docker-compose.yml` header — declares "for full K8s + Istio
  deployment, see infra/kind/ and infra/k8s/" (now: infra/minikube/
  via this runbook + scripts/istio-up.sh)

## The brutal rule

> Phase-1 dev does NOT need Istio running. The YAMLs are
> documentation-as-code; the mesh is overhead. Spin minikube + Istio
> only when you need to exercise the mesh's actual enforcement —
> otherwise NGINX + api-gateway + circuit-breakers cover ~80% of
> Istio's value at ~5% of the operational cost.

## Kiali in compose-mode (post-2026-05-06)

Kiali v1.86 hard-blocks startup on a K8s cache sync that cannot
complete in docker-compose mode (no real K8s API server is reachable).
Symptom: `documind-kiali` enters `Up (health: starting)` indefinitely
and never serves HTTP at `:20001/kiali/`. Logs show
`[Kiali Cache] Waiting for cluster-scoped cache to sync` followed by
endless K8s API connection-refused warnings.

The fix is **NOT** to start Kiali in docker-compose. Kiali is gated
behind `--profile mesh` so default `docker compose up` skips it.

### The two operator paths

**Path A — Full mesh (Kiali fully functional):**

```bash
bash scripts/istio-up.sh                    # bring up minikube + Istio
istioctl analyze -n documind                # smoke check
docker compose --profile mesh up kiali      # NOW Kiali can sync K8s cache
                                            # → http://localhost:20001/kiali/
```

**Path B — Compose-only dev (Kiali off):**

```bash
docker compose up -d                        # default; Kiali skipped
                                            # mesh-graph unavailable
                                            # Prometheus + Grafana still
                                            # cover service metrics on :3001
```

Drilled by `mcp/tests/drill_minikube_istio_setup.py` steps 12-15:
profile gate locked, signing-key length verified, kiali.yaml comment
required to reference `scripts/istio-up.sh`, runbook required to
document `--profile mesh` instruction.

### Why not just use a fake K8s API in compose

Tried (2026-05-06):

- Dummy kubeconfig pointing at 127.0.0.1:1 — Kiali still requires
  `KUBERNETES_SERVICE_HOST` env vars + service-account token files.
- Faked all of those — Kiali starts the binary cleanly but blocks
  forever on `[Kiali Cache] Waiting for cluster-scoped cache to sync`.
- Set `kubernetes_config.cache_enabled: false` + `cluster_wide_access:
  false` — flags ignored or insufficient; cache wait persists.

Conclusion: Kiali v1.86 requires a *responsive* K8s API; there is no
documented compose-mode escape. Older Kiali versions (≤ 1.50) had an
"external_services_only" mode but were dropped. The honest path is to
acknowledge the architecture mismatch and document the two operator
flows above.
