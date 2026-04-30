# agent-orchestrator-svc

Bounded agentic orchestration service for manager/worker/reviewer/advisor flows.

## Current state vs target state

This service is **real and usable now**, but it is not a free-form
autonomous swarm or a full distributed workflow engine.

Current state:

- accepts bounded agentic tasks over HTTP
- supports project creation with normalized plan rows
- runs manager → worker → reviewer → advisor style task flow
- evaluates approval policy and can pause for human approval
- persists tasks, project plans, task runs, approvals, and memories
- exposes read APIs that feed the frontend control-plane pages
- falls back to in-memory storage if Postgres is unavailable

Target state:

- richer DAG planning with meaningful dependency scheduling
- deeper autonomous delegation and merge coordination
- stronger runtime visibility into worker occupancy / queue depth
- more complete operator approval, replay, and rollback tooling
- broader cross-service orchestration beyond the current bounded task shape

So the correct framing is:

- **current:** bounded orchestration service with real persistence and UI surfaces
- **not yet:** full autonomous multi-agent operating system

## What it does

- accepts agentic tasks over HTTP
- executes real MCP tools when `tool_namespace`, `tool_name`, and `tool_arguments` are provided
- persists task state to Postgres when available
- falls back to in-memory storage if Postgres is unavailable
- pauses high-risk or explicitly gated tasks for human approval

## What is real now

Backed by migrations through:

- `001_initial.sql`
- `002_approval_automation.sql`
- `003_global_policy.sql`
- `004_policy_scenarios.sql`
- `005_projects.sql`
- `006_project_plan.sql`
- `007_agentic_project_memory.sql`

Persisted data now includes:

- tasks
- global policy
- projects
- normalized project plan items
- task runs
- approvals
- memories

Behavior already wired in the service layer:

- `create_project()` persists normalized plan rows
- task execution writes task-run records
- `approve_task()` writes approval records
- completed task/project outcomes write memory records

## What exposes it

Frontend/operator surfaces:

- `/admin/agentic`
- `/admin/agentic/control-plane`
- `/admin`

The control-plane page exposes:

- active role routing
- approval policy
- project plan rows
- task runs
- approvals
- memories

Read APIs already exposed by this service:

- `GET /api/v1/agentic/projects/{project_id}/plan-items`
- `GET /api/v1/agentic/tasks/{task_id}/runs`
- `GET /api/v1/agentic/tasks/{task_id}/approvals`
- `GET /api/v1/agentic/memories?scope_type=...&scope_id=...`
- plus the existing task/project/policy endpoints

## Important limits

Be explicit about these:

- role count does **not** mean live concurrent worker count
- task activity is visible; per-model occupancy is not yet exposed
- project planning exists, but true dependency-aware execution is still shallow
- local in-memory fallback is operationally useful, but Postgres is the serious path
- this service composes with the sidecar advisor/council, but it is not itself the full council runtime

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

Optional but useful:

```bash
export DOCUMIND_AGENT_ADVISOR_MODEL=qwen2.5:latest
```

That keeps the advisor path local if you do not want a cloud/default chair path elsewhere in the stack.

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

## Runtime truth checks

Use these when you want current-state truth instead of assumptions:

```bash
# service health + runtime view from the frontend
open http://localhost:3000/admin/agentic/control-plane

# monitoring page with service/runtime/resource status
open http://localhost:3000/admin/monitoring

# local loop/ops status
python3 scripts/loop_status.py
```

If you want API-level truth:

```bash
curl http://localhost:8087/api/v1/agentic/agents
curl http://localhost:8087/api/v1/agentic/policy
curl http://localhost:8087/api/v1/agentic/projects?limit=10
curl http://localhost:8087/api/v1/agentic/tasks?limit=10
```

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

## Summary

This service is already a real bounded orchestration layer with:

- task/project creation
- policy gating
- persistence
- human approval
- normalized control-plane visibility

The main things it still lacks are the deeper workflow-engine and
autonomous-runtime behaviors that the broader architecture documents
describe as target state.
