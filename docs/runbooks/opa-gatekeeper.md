# OPA Gatekeeper Runbook

DocuMind uses two OPA layers:

- App-level OPA for approval decisions: `approval_agent/policy.rego`.
- Kubernetes admission control through Gatekeeper: `infra/k8s/gatekeeper/`.

## Readiness Check

Run the offline checker before applying cluster changes:

```bash
env PYTHONPATH=scripts .venv/bin/python scripts/opa_gatekeeper_status.py --json --fail-on-not-ready
```

Expected state:

- `manifests_present=true`
- `constraint_templates=4`
- `constraints=4`
- `ready_for_apply=true`
- every embedded Rego template has `compiled=true`

## Apply Order

Install the Gatekeeper CRDs/controller first, then apply this repo's policy pack:

```bash
kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/master/deploy/gatekeeper.yaml
kubectl apply -k infra/k8s/gatekeeper
```

The policy pack is scoped to the `documind` namespace and uses
`enforcementAction: deny`.

## Controls

The Gatekeeper pack currently enforces:

- required workload labels: `app.kubernetes.io/name`, `app.kubernetes.io/part-of`, `app.kubernetes.io/managed-by`
- no host namespace access: `hostNetwork`, `hostPID`, `hostIPC`
- non-root, read-only runtime: `runAsNonRoot=true`, `allowPrivilegeEscalation=false`, `readOnlyRootFilesystem=true`, no privileged containers
- allowed image registry prefixes

## Drills

```bash
env PYTHONPATH=scripts .venv/bin/python mcp/tests/drill_opa_gatekeeper_advanced.py
env PYTHONPATH=. .venv/bin/python mcp/tests/drill_opa_approval_parity.py
env PYTHONPATH=scripts .venv/bin/python mcp/tests/drill_rego_sync.py
```
