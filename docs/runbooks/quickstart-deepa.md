# Quickstart — circuitRAG / DocuMind on the /mnt/deepa drive

> Per the no-system-drive policy (CLAUDE.md §57 + memory
> `feedback_no_system_drive_install`), every binary, cache, and
> minikube state lives on `/mnt/deepa`, NEVER on the OS root drive.

## TL;DR — 4 commands

```bash
cd /mnt/deepa/rag
bash scripts/setup.sh                    # full bootstrap (idempotent)
bash scripts/setup.sh --infra            # docker-compose stack
bash scripts/setup.sh --verify           # run the audit suite
```

That gets you: tools on deepa, venv on deepa, infra running, audits + scorecard rendered.

## Step-by-step

### 1. Set up directories + activation env (10 sec)

```bash
cd /mnt/deepa/rag
bash scripts/setup.sh --check         # what's installed today?
bash scripts/setup.sh --env           # print activation env to paste
```

Paste the env into your shell:

```bash
export PATH=/mnt/deepa/rag/.tools/bin:$PATH
export PIP_CACHE_DIR=/mnt/deepa/rag/.tools/cache/pip
export NPM_CONFIG_CACHE=/mnt/deepa/rag/.tools/cache/npm
export MINIKUBE_HOME=/mnt/deepa/.minikube
export KUBECONFIG=/mnt/deepa/.kube/config
export OLLAMA_BASE_URL=http://localhost:11434
export PYTHONPATH=/mnt/deepa/rag/libs/py:$PYTHONPATH
```

### 2. Install CLI tools (binaries to `.tools/bin/`)

```bash
bash scripts/setup.sh --tools
# → installs kubectl, minikube, istioctl, trivy, gitleaks, promptfoo
# → all binaries land in /mnt/deepa/rag/.tools/bin/ (NOT system PATH)
# → ~3-5 min on a fresh box
```

### 3. Create venv + install Python deps

```bash
bash scripts/setup.sh --venv
# → venv at /mnt/deepa/rag/.venv (NOT ~/.local)
# → pip cache at /mnt/deepa/rag/.tools/cache/pip
# → installs: pyyaml, fastapi, ragas, deepeval, giskard, rebuff,
#             arize-phoenix, semgrep, great_expectations, pyjwt
```

### 4. Bring up infrastructure (docker-compose)

```bash
bash scripts/setup.sh --infra
# → starts: postgres, redis, kafka, ollama, qdrant, neo4j, minio,
#           otel-collector, jaeger, prometheus, alertmanager, grafana,
#           elasticsearch, kibana, filebeat, envoy
# → ~60s for healthy state
```

### 5. (Optional) Bring up minikube + Istio + Kiali

```bash
bash scripts/setup.sh --istio
# → cluster: documind-mesh (3072MB / 2 CPU on docker)
# → istiod + ingress + Kiali + Prometheus + Jaeger addons
# → ~5 min on first run
```

### 6. Verify everything

```bash
bash scripts/setup.sh --verify
# OR individually:
make audit-fleet         # 28 MCP servers + Ollama + council + backends
make audit-readiness     # 7-dim probe
make audit-scorecard     # 5-dim production-readiness (94/100 today)
make audit-oss           # 91 OSS tools × 17 categories
make audit-chunking      # 20 metrics + 15 quality gates
make audit-scenarios     # 35 agentic observability scenarios
make e2e                 # 11-scenario E2E test (batch / inference / graph / ...)
make drills-catalogs     # all schema drills
```

## What lives where on /mnt/deepa

```
/mnt/deepa/
├── rag/                         # main repo
│   ├── .tools/bin/              # kubectl, minikube, istioctl, trivy, gitleaks, promptfoo
│   ├── .tools/cache/pip         # Python pip cache
│   ├── .tools/cache/npm         # Node npm cache
│   ├── .tools/lib/node          # promptfoo + dep tree
│   ├── .venv/                   # Python virtualenv
│   ├── .loop/                   # operator-readable evidence (audits, scorecards, drill history)
│   ├── config/agentic_observability/
│   │   ├── scenarios.yaml       # 35 tracking scenarios
│   │   ├── missing_tools.yaml   # 19 backlog tools
│   │   ├── oss_tooling_catalog.yaml  # 91 OSS tools
│   │   └── chunking_quality.yaml     # 20 metrics + 15 gates
│   ├── config/tool_catalog/     # 28 MCP server 9-axis specs
│   ├── docs/architecture/tool-reviews/  # 28 brutal-review docs
│   ├── docs/runbooks/           # operator runbooks (this file lives here)
│   └── infra/k8s/mesh/          # 28 MCP k8s manifests + OPA + Telemetry CRs
├── .minikube/                   # minikube cluster state
└── .kube/config                 # kubectl config
```

**Zero bytes** of project tooling on the OS root drive (system).

## Daily commands cheat sheet

| Command | What it does |
|---|---|
| `make setup-check` | Quick sanity check; lists installed tools + venv version |
| `make audit-scorecard` | Re-derive the 5-dim production readiness score |
| `make audit-fleet` | 28 MCP servers + Ollama + council + backends status |
| `make e2e` | 11-scenario end-to-end test |
| `make drills-catalogs` | Run all 5 catalog-schema drills |
| `make audit-all` | Sequential — fleet → readiness → scorecard → OSS → chunking → scenarios |
| `make help` | Full Makefile target listing |

## Troubleshooting

### "kubectl: command not found"
Activate the env: `export PATH=/mnt/deepa/rag/.tools/bin:$PATH`

### "Cannot create with that IP, address already in use" (minikube)
Profile name `documind` collides with existing docker network. Use `documind-mesh`:
```bash
minikube delete --profile documind
bash scripts/setup.sh --istio
```

### Phoenix import error (`ReadableLogRecord`)
OTel SDK version mismatch. Fix:
```bash
.venv/bin/pip install --upgrade 'opentelemetry-sdk>=1.27'
```

### ES "can not run elasticsearch as root"
Already fixed in `docker-compose.override.yml` (named volume + user 1000). Re-run `make setup-infra`.

### Ollama smoke takes 5+ minutes
Cold-load times for 7B+ models. Skip via:
```bash
SKIP_OLLAMA_SMOKE=1 bash scripts/setup.sh --verify
```

## §51 forensic substrate

- Date: 2026-05-07
- Location: praveen-dev-linux-x86_64
- Approach: autonomous-loop iter-100 (canonical bootstrap)
- Policies: §42 §44 §51 §57 + memory `feedback_no_system_drive_install`
- Verification:
  ```bash
  bash scripts/setup.sh --check        # tool inventory
  make audit-scorecard                  # 94/100 production_grade=True
  make drills-catalogs                  # 5 drills, all 10/10
  ```
