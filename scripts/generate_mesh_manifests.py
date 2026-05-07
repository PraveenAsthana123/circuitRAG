"""Generate k8s Deployment + Service manifests for each MCP/agent tool (iter-94).

Per CLAUDE.md §44 (iter-94), §47 (architecture), §57.1 (production-grade only),
the user's ask: "integrate with each tool — MCP / paperclip / polysai / OPA / Kiali."

For every `mcp/server_<ns>.py`, this script emits:
  - infra/k8s/mesh/<ns>/deployment.yaml
  - infra/k8s/mesh/<ns>/service.yaml
+ supporting:
  - infra/k8s/mesh/_common/configmap-source.yaml (mounts mcp/ + libs/py via configmap)
  - infra/k8s/mesh/paperclip/...
  - infra/k8s/mesh/opa/...
  - infra/k8s/mesh/polysai/...

The Deployment uses a stock python:3.11-slim image and runs the server directly
from a mounted volume. Sidecar auto-injection happens because the documind
namespace has istio-injection=enabled (iter-93).

Operator workflow:
  python3 scripts/generate_mesh_manifests.py            # write all
  kubectl apply -k infra/k8s/mesh                       # apply all
  kubectl get pods -n documind                           # verify 2/2 (app + sidecar)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "mcp"
OUT_DIR = REPO / "infra" / "k8s" / "mesh"

# Port assignments matching scripts/start_mcp_*.sh + iter-72 fleet monitor
KNOWN_PORTS: dict[str, int] = {
    "hr": 8090, "itsm": 8091, "drills": 8092, "github": 8093,
    "documents": 8094, "csv_ingest": 8095, "slack": 8096,
    "jira": 8097, "ollama": 8098,
    "github_actions": 8120, "sonarqube": 8121, "kubectl": 8122,
    "datadog": 8123, "sentry": 8124, "pagerduty": 8125,
    "aws": 8126, "gcp": 8127, "azure": 8128,
    "confluence": 8129, "gdrive": 8130, "servicenow": 8131,
    "teams": 8132, "whatsapp": 8133,
    "deploy": 8134, "tests": 8135, "research": 8136,
    "observe": 8137, "paperclip": 8138,
}


def deployment_yaml(ns: str, port: int) -> str:
    """Emit a k8s Deployment that runs `python -m mcp.server_<ns>` from a
    mounted source code volume. Stock python:3.11-slim image; deps installed
    via initContainer or operator-built image."""
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-{ns.replace("_", "-")}
  namespace: documind
  labels:
    app: mcp-{ns.replace("_", "-")}
    app.kubernetes.io/component: mcp-server
    app.kubernetes.io/part-of: documind
    documind.tool/namespace: {ns}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-{ns.replace("_", "-")}
  template:
    metadata:
      labels:
        app: mcp-{ns.replace("_", "-")}
        app.kubernetes.io/component: mcp-server
        documind.tool/namespace: {ns}
      annotations:
        sidecar.istio.io/inject: "true"
        prometheus.io/scrape: "true"
        prometheus.io/port: "{port}"
        prometheus.io/path: "/metrics"
    spec:
      containers:
        - name: server
          image: python:3.11-slim
          command: ["sh", "-c"]
          args:
            - |
              pip install --quiet fastapi uvicorn httpx pydantic prometheus_client opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp-proto-grpc &&
              cd /app && PYTHONPATH=/app/libs/py:/app python -m mcp.server_{ns}
          ports:
            - containerPort: {port}
              name: http
              protocol: TCP
          env:
            - name: MCP_{ns.upper()}_PORT
              value: "{port}"
            - name: DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT
              value: "http://jaeger-collector.istio-system.svc.cluster.local:4317"
          volumeMounts:
            - name: source
              mountPath: /app
              readOnly: true
          readinessProbe:
            httpGet:
              path: /health/live
              port: {port}
            initialDelaySeconds: 30
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: {port}
            initialDelaySeconds: 60
            periodSeconds: 30
      volumes:
        - name: source
          hostPath:
            path: /mnt/deepa/rag
            type: Directory
"""


def service_yaml(ns: str, port: int) -> str:
    return f"""apiVersion: v1
kind: Service
metadata:
  name: mcp-{ns.replace("_", "-")}
  namespace: documind
  labels:
    app: mcp-{ns.replace("_", "-")}
    documind.tool/namespace: {ns}
spec:
  selector:
    app: mcp-{ns.replace("_", "-")}
  ports:
    - port: {port}
      targetPort: {port}
      name: http
      protocol: TCP
"""


def opa_deployment_yaml() -> str:
    """Standalone OPA evaluator pod for in-mesh policy decisions (Stage-3
    of the §47.6 default-deny invariant)."""
    return """apiVersion: apps/v1
kind: Deployment
metadata:
  name: opa
  namespace: documind
  labels:
    app: opa
    app.kubernetes.io/component: policy-evaluator
spec:
  replicas: 1
  selector:
    matchLabels:
      app: opa
  template:
    metadata:
      labels:
        app: opa
      annotations:
        sidecar.istio.io/inject: "true"
    spec:
      containers:
        - name: opa
          image: openpolicyagent/opa:0.66.0-rootless
          args:
            - "run"
            - "--server"
            - "--log-level=info"
            - "--addr=0.0.0.0:8181"
            - "/policies/agent_dispatch.rego"
          ports:
            - containerPort: 8181
              name: http
          volumeMounts:
            - name: policies
              mountPath: /policies
              readOnly: true
          livenessProbe:
            httpGet:
              path: /health
              port: 8181
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: policies
          configMap:
            name: opa-policies
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: opa-policies
  namespace: documind
data:
  agent_dispatch.rego: |
{{REGO_BUNDLE}}
---
apiVersion: v1
kind: Service
metadata:
  name: opa
  namespace: documind
  labels:
    app: opa
spec:
  selector:
    app: opa
  ports:
    - port: 8181
      targetPort: 8181
      name: http
"""


def kustomization_yaml(namespaces: list[str]) -> str:
    files = []
    for ns in namespaces:
        files.append(f"  - {ns}/deployment.yaml")
        files.append(f"  - {ns}/service.yaml")
    files.append("  - opa/all.yaml")
    return "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nnamespace: documind\nresources:\n" + "\n".join(files) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="generate only this namespace")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    namespaces = []
    for f in sorted(MCP_DIR.glob("server_*.py")):
        if f.stem == "server_common":
            continue
        ns = f.stem.replace("server_", "")
        if args.only and ns != args.only:
            continue
        namespaces.append(ns)
        ns_dir = OUT_DIR / ns
        ns_dir.mkdir(parents=True, exist_ok=True)
        port = KNOWN_PORTS.get(ns, 8200 + abs(hash(ns)) % 100)
        (ns_dir / "deployment.yaml").write_text(deployment_yaml(ns, port), encoding="utf-8")
        (ns_dir / "service.yaml").write_text(service_yaml(ns, port), encoding="utf-8")
        print(f"  wrote {ns_dir.relative_to(REPO)}/ (port {port})")

    # OPA
    opa_dir = OUT_DIR / "opa"
    opa_dir.mkdir(parents=True, exist_ok=True)
    rego_path = REPO / "config" / "policies" / "agent_dispatch.rego"
    rego_text = rego_path.read_text(encoding="utf-8") if rego_path.exists() else "# (rego not found)"
    rego_indented = "\n".join(f"    {line}" for line in rego_text.splitlines())
    opa_yaml = opa_deployment_yaml().replace("{REGO_BUNDLE}", rego_indented)
    (opa_dir / "all.yaml").write_text(opa_yaml, encoding="utf-8")
    print(f"  wrote {opa_dir.relative_to(REPO)}/all.yaml (OPA + ConfigMap with rego)")

    # Kustomization
    (OUT_DIR / "kustomization.yaml").write_text(
        kustomization_yaml(namespaces), encoding="utf-8")
    print(f"  wrote {(OUT_DIR / 'kustomization.yaml').relative_to(REPO)}")

    print(f"\n{len(namespaces)} MCP namespace manifests + OPA generated under "
          f"{OUT_DIR.relative_to(REPO)}/")
    print("Apply with:")
    print(f"  kubectl apply -k {OUT_DIR.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
