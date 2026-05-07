# Istio + Kiali Setup — iter-93 status

**Date:** 2026-05-07
**Approach:** autonomous-loop iter-93 (operator-approved "setup istio")
**Per global policy:** §57 production-grade + feedback `no_system_drive_install`
(tools on /mnt/deepa, not system drive)

## What ran

1. **Tooling installed** to `/mnt/deepa/rag/.tools/bin/` (per policy, NOT to system):
   - `kubectl` v1.30.0 (51 MB)
   - `minikube` v1.33.1 (95 MB)
   - `istioctl` 1.22.0 (91 MB)
   Total: 228 MB on deepa drive.
2. **Minikube state** at `/mnt/deepa/.minikube/` (symlinked from `~/.minikube`)
3. **Cluster name:** `documind-mesh` (not `documind` — to avoid network name
   collision with the existing docker-compose `documind` network at 172.30.0.0/16)
4. **Cluster:** 1 control-plane node, 3072 MB / 2 CPUs
5. **Istio control plane:** istiod + ingress gateway, both Running
6. **Project manifests applied** (from `infra/istio/`):
   - 1 Gateway, 2 VirtualServices, 4 DestinationRules
   - 7 AuthorizationPolicies (ALLOW for each project service)
   - 2 PeerAuthentication policies in **STRICT mTLS** mode
   - 1 Telemetry config
7. **Addons:** Kiali 1.86 + Prometheus + Jaeger (from `samples/addons/`)
8. **Demo:** `hello` pod in `documind` ns confirmed sidecar auto-injection
   (2 containers: `hello` app + `istio-proxy`)
9. **Drill verified:** `mcp/tests/drill_minikube_istio_setup.py` 15/15 PASS

## Activation env (operator: paste into your shell)

```bash
export PATH=/mnt/deepa/rag/.tools/bin:$PATH
export KUBECONFIG=/mnt/deepa/.kube/config
export MINIKUBE_PROFILE=documind-mesh
```

## How to access UIs

```bash
# Kiali (mesh visualization)
kubectl port-forward -n istio-system svc/kiali 20001:20001
# → http://localhost:20001

# Jaeger (distributed tracing)
kubectl port-forward -n istio-system svc/tracing 16686:80
# → http://localhost:16686

# Prometheus
kubectl port-forward -n istio-system svc/prometheus 9091:9090
# → http://localhost:9091
```

## Tear down

```bash
bash scripts/istio-down.sh                           # destroys cluster
# OR
minikube delete --profile documind-mesh              # alt
```

## Honest gaps (still pending operator action)

- [ ] **Application services not yet deployed to k8s** — inference-svc /
      retrieval-svc / agent-orchestrator-svc still run via docker-compose;
      to integrate with mesh, build container images + k8s Deployments +
      Services. This is migration work, not a 5-minute task.
- [ ] **Ingress LoadBalancer pending** — minikube needs `tunnel` or `nodePort`
      for external traffic. Run `minikube tunnel --profile documind-mesh` in
      a separate shell to expose `istio-ingressgateway`.
- [ ] **No traffic to mesh yet** — mesh shows 0 RPS until app pods deploy.
      The graph view in Kiali will be empty until then.

## Per-tool integration with Kiali (the user's ask)

Kiali surfaces every workload that:
1. Runs as a Pod in a `istio-injection=enabled` namespace
2. Has a Service exposing it
3. Is sending OR receiving traffic via the Envoy sidecar

Currently in mesh: only the `hello` demo pod. To get the project's MCP /
agent / inference services into Kiali, each one needs:
- Container image built (`docker build` + push to a registry minikube can pull from)
- k8s Deployment + Service manifest in `infra/istio/` (or a `helm/` chart)
- Re-apply with `kubectl apply -n documind`

## §51 forensic substrate
- Date: 2026-05-07
- Location: praveen-dev-linux-x86_64
- Approach: autonomous-loop iter-93
- Policies: §42 §47 §51 §57 (no system drive) + project drill_minikube_istio_setup.py
- Verification:
  ```
  export PATH=/mnt/deepa/rag/.tools/bin:$PATH KUBECONFIG=/mnt/deepa/.kube/config
  kubectl get pods -n istio-system        # 5 pods Running
  istioctl analyze -n documind            # 0 errors
  python3 mcp/tests/drill_minikube_istio_setup.py  # 15/15 PASS
  ```
