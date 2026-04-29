# agent-orchestrator-svc

Bounded agentic orchestration service for manager/worker/reviewer/advisor flows.

## What it does

- accepts agentic tasks over HTTP
- executes real MCP tools when `tool_namespace`, `tool_name`, and `tool_arguments` are provided
- persists task state to Postgres when available
- falls back to in-memory storage if Postgres is unavailable
- pauses high-risk or explicitly gated tasks for human approval

## Local run

```bash
cd /mnt/deepa/rag
python services/agent-orchestrator-svc/scripts/bootstrap.py
python -m venv .venv-agentic
source .venv-agentic/bin/activate
pip install -e libs/py
pip install -r services/agent-orchestrator-svc/requirements.txt
uvicorn app.main:app --app-dir services/agent-orchestrator-svc --host 0.0.0.0 --port 8087
```

Required environment:

```bash
export DOCUMIND_PG_HOST=localhost
export DOCUMIND_PG_PORT=5432
export DOCUMIND_PG_DB=documind
export DOCUMIND_PG_USER=documind
export DOCUMIND_PG_PASSWORD=documind

export DOCUMIND_AGENTIC_URL=http://localhost:8087
export DOCUMIND_MCP_HR_URL=http://localhost:8091
export DOCUMIND_MCP_ITSM_URL=http://localhost:8092
export DOCUMIND_MCP_DRILLS_URL=http://localhost:8093
```

## Fully local mode

For a no-cloud setup, keep MCP on localhost and force the advisor/chair
path onto the local Qwen model:

```bash
export DOCUMIND_MCP_HR_URL=http://127.0.0.1:8091
export DOCUMIND_MCP_ITSM_URL=http://127.0.0.1:8092
export DOCUMIND_MCP_DRILLS_URL=http://127.0.0.1:8093

export SIDECAR_CHAIR_MODEL=qwen2.5:latest
export DOCUMIND_AGENT_ADVISOR_MODEL=qwen2.5:latest
```

Notes:

- `SIDECAR_CHAIR_MODEL` switches the Sidecar PR-review chair off the
  Kimi cloud default and onto local Qwen.
- `DOCUMIND_AGENT_ADVISOR_MODEL` switches the agent-orchestrator
  advisor path onto local Qwen through service settings.
- local coder/reviewer defaults remain unchanged unless you override
  them separately.

## Docker build and run

Build:

```bash
cd /mnt/deepa/rag
docker build -t documind/agent-orchestrator-svc -f services/agent-orchestrator-svc/Dockerfile .
```

Run:

```bash
docker run --rm -p 8087:8087 \
  -e DOCUMIND_POSTGRES_DSN=postgresql://documind:documind@host.docker.internal:5432/documind \
  -e DOCUMIND_MCP_HR_URL=http://host.docker.internal:8091 \
  -e DOCUMIND_MCP_ITSM_URL=http://host.docker.internal:8092 \
  -e DOCUMIND_MCP_DRILLS_URL=http://host.docker.internal:8093 \
  documind/agent-orchestrator-svc
```

## Bootstrap / migrations

The migration bootstrap is:

```bash
python services/agent-orchestrator-svc/scripts/bootstrap.py
```

What it does:

1. ensures `public._migrations` exists by applying `scripts/postgres-init.sql` once
2. applies `services/agent-orchestrator-svc/migrations/001_initial.sql`

If your cluster is already initialized, rerunning the bootstrap is safe.
