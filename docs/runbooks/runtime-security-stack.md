# Runtime Security Stack

DocuMind's runtime-security layer combines:

- **Tetragon** for eBPF process, file, and network observability.
- **Tracee** for eBPF runtime detection rules and JSON event output.
- **Wazuh** for SIEM/XDR-style correlation and dashboarding.

## Offline Readiness

```bash
env PYTHONPATH=scripts .venv/bin/python scripts/runtime_security_status.py --json --fail-on-not-ready
```

Expected:

- `runtime_security.ready=true`
- `wazuh.ready=true`
- `tetragon.ready=true`
- `tracee.ready=true`

## Kubernetes Apply

Install the Helm repos first:

```bash
helm repo add cilium https://helm.cilium.io/
helm repo add aqua https://aquasecurity.github.io/helm-charts/
helm repo update
```

Apply repo-owned namespaces/config/policies:

```bash
kubectl apply -k infra/runtime-security
```

Install Tetragon:

```bash
helm upgrade --install tetragon cilium/tetragon \
  -n tetragon \
  -f infra/runtime-security/helm-values/tetragon-values.yaml
```

Install Tracee:

```bash
helm upgrade --install tracee aqua/tracee \
  -n tracee \
  -f infra/runtime-security/helm-values/tracee-values.yaml
```

## Wazuh Opt-in

Wazuh is intentionally separate from the main compose stack because it is heavy:

```bash
docker compose -f infra/runtime-security/wazuh-compose.yml up -d
```

Ports:

- Wazuh dashboard: `http://localhost:5602`
- Wazuh manager API: `http://localhost:55000`
- Wazuh indexer: `http://localhost:9201`

## Drills

```bash
env PYTHONPATH=scripts .venv/bin/python mcp/tests/drill_runtime_security_stack.py
```
