# Iter-94: MCP Tool Integration with Istio Mesh

**Date:** 2026-05-07
**Builds on:** iter-93 (Istio cluster up)
**Per:** §44 ONE-thing-per-iter, §47 architecture, §57.1 production-grade

## What landed

`scripts/generate_mesh_manifests.py` writes k8s manifests under
`infra/k8s/mesh/<ns>/` for every MCP server + OPA + Kustomization.

**Generated for 28 MCP namespaces** (one Deployment + Service each):
aws, azure, confluence, csv_ingest, datadog, deploy, documents, drills,
gcp, gdrive, github, github_actions, hr, itsm, jira, kubectl, observe,
ollama, pagerduty, paperclip, research, sentry, servicenow, slack,
sonarqube, teams, tests, whatsapp.

Each manifest:
- Deploys to `documind` namespace (istio-injection=enabled per iter-93)
- Sets `sidecar.istio.io/inject: "true"` annotation (explicit even if ns label
  already enables it — defense in depth)
- Sets `prometheus.io/scrape: "true"` for metrics
- Mounts `/mnt/deepa/rag` from minikube node (operator must run
  `minikube --profile documind-mesh mount /mnt/deepa/rag:/mnt/deepa/rag`)
- Liveness + readiness probes against `/health/live`
- OTel endpoint set to `jaeger-collector.istio-system.svc.cluster.local:4317`

**Plus:**
- `infra/k8s/mesh/opa/all.yaml` — standalone OPA evaluator pod with the
  `agent_dispatch.rego` ConfigMap (Stage-3 of §47.6 default-deny)
- `infra/k8s/mesh/kustomization.yaml` — `kubectl apply -k` ergonomics

## Verification (just performed)

| Pod | Status | Sidecar | Note |
|---|---|---|---|
| `hello` | 2/2 Running | ✓ injected | demo pod from iter-93 |
| `mcp-documents` | 1/2 Running (BackOff) | ✓ injected | server crashes on startup; needs pre-built image |
| `opa` | 0/2 (ErrImagePull) | ✓ injected | OPA image not in minikube cache |

**Mesh integration verified at Istio layer:** all 3 pods get sidecars
auto-injected via the namespace label. Container-start failures are
operator-tier follow-up (image build / cache / registry).

## Next iter (95+) operator workflow

To bring all 28 MCP tools fully online in the mesh:

```bash
# 1. Activate tooling
export PATH=/mnt/deepa/rag/.tools/bin:$PATH
export KUBECONFIG=/mnt/deepa/.kube/config

# 2. Mount source code into minikube (in a separate persistent shell)
minikube --profile documind-mesh mount /mnt/deepa/rag:/mnt/deepa/rag

# 3. Pre-pull the OPA image
minikube --profile documind-mesh image pull openpolicyagent/opa:0.66.0-rootless

# 4. Build a proper MCP container image (one-time)
#    Use services/mcp-base/Dockerfile (operator may need to author this) with all
#    requirements.txt deps pre-installed; tag and load into minikube cache:
#    eval $(minikube --profile documind-mesh docker-env)
#    docker build -t mcp-base:dev infra/k8s/mesh-image/
#    Then update infra/k8s/mesh/<ns>/deployment.yaml to use image: mcp-base:dev

# 5. Apply all 28 MCP namespaces + OPA
kubectl apply -k infra/k8s/mesh/

# 6. Watch pods come up
kubectl get pods -n documind -w

# 7. Open Kiali to see the mesh graph
kubectl port-forward -n istio-system svc/kiali 20001:20001
# Browser: http://localhost:20001/
```

## Trade-offs honestly named

- **python:3.11-slim + pip install on container start** is slow + needs
  internet from inside minikube. Production: build a proper mcp-base image.
- **hostPath volume mount for source** is dev-only. Production: bake source
  into the image.
- **No real upstream creds set** (most MCPs return stub responses). That's
  fine for mesh-graph verification (Kiali sees the topology) but the actual
  end-to-end traffic to upstream SaaS is operator-credential-tier work.

## §51 forensic substrate

- Date: 2026-05-07
- Location: praveen-dev-linux-x86_64
- Approach: autonomous-loop iter-94 (operator-approved "integrate with each tool")
- Policies: §42 §43 §44 §47 §51 §57 + global feedback `no_system_drive_install`
- Verification:
  ```
  python3 scripts/generate_mesh_manifests.py            # 28 + opa + kustomization
  kubectl get pods -n documind                          # 3 pods, all with sidecars
  kubectl describe pod -n documind -l app=mcp-documents # see sidecar injected
  ```
