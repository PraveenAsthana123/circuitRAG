# Runbook — Agentic control plane

> Focused operator/developer runbook for the normalized agentic
> project/task execution chain. Companion to
> `docs/runbooks/autonomous-loop-cheatsheet.md`.

## What it is

The agentic control plane exposes the execution chain for:

- projects
- normalized project plan rows
- task execution runs
- human approvals
- distilled task/project memories

This is the operator-visible surface for the advanced multi-agent
planner/executor flow in `services/agent-orchestrator-svc/`.

## UI surfaces

| Surface | Purpose |
|---|---|
| `/admin` | compact operator summary panel |
| `/admin/monitoring` | runtime/service/resource truth surface that now complements the agentic pages |
| `/admin/agentic` | create tasks/projects, manage policy, approve tasks |
| `/admin/agentic/control-plane` | full read view of normalized records |
| `/app-meta/runtime-status` | local frontend-owned runtime status route for Docker/Ollama truth |

Left-menu path:

- `Admin` → `Agentic tasks`
- `Admin` → `Agentic control plane`
- `Admin` → `Monitoring + health`

## Runtime truth

For current truth, distinguish between:

- **agentic control-plane truth**
  - projects
  - plan rows
  - task runs
  - approvals
  - memories
- **runtime/platform truth**
  - running vs unhealthy compose services
  - Docker stats resource usage
  - Ollama systemd state

Use:

- `/admin/agentic/control-plane`
  - normalized agentic records
- `/admin/monitoring`
  - runtime/service/resource view
- `/app-meta/runtime-status`
  - local JSON runtime feed used by the monitoring page

Important limit:

- “active agents” in the UI currently means **active agentic workflows/tasks**
  plus configured role bindings
- it does **not** yet mean live worker occupancy or per-model concurrent execution threads

The operator dashboard also shows an `Agentic control plane summary`
panel with:

- project count
- tracked task count
- pending approval count
- recent approval decisions
- recent distilled memories

## Data model

Normalized persistence tables live under the orchestrator schema and
are introduced by:

- `services/agent-orchestrator-svc/migrations/007_agentic_project_memory.sql`

Core records:

| Record | Meaning |
|---|---|
| `agent_project_plan_items` | normalized expansion of `ProjectView.planned_tasks` |
| `agent_task_runs` | started/final execution history for each task |
| `agent_approvals` | human approval/rejection decisions |
| `agent_memories` | distilled task/project memories |

Related existing records:

| Record | Meaning |
|---|---|
| `agent_projects` | project shell + embedded planned task JSON |
| `agent_tasks` | live task state |

## Read APIs

The control-plane UI reads these endpoints:

| Endpoint | Returns |
|---|---|
| `GET /api/v1/agentic/projects/{project_id}/plan-items` | normalized project plan rows |
| `GET /api/v1/agentic/tasks/{task_id}/runs` | task execution history |
| `GET /api/v1/agentic/tasks/{task_id}/approvals` | persisted human decisions |
| `GET /api/v1/agentic/memories?scope_type=project&scope_id=...` | project memory rows |
| `GET /api/v1/agentic/memories?scope_type=task&scope_id=...` | task memory rows |

Related runtime/operator feed outside the orchestrator API namespace:

| Endpoint | Returns |
|---|---|
| `GET /app-meta/runtime-status` | local compose service states, Docker stats resource rows, Ollama runtime state |

Existing write surfaces remain:

- `POST /api/v1/agentic/projects`
- `POST /api/v1/agentic/tasks`
- `POST /api/v1/agentic/tasks/{task_id}/approve`
- `GET /api/v1/agentic/tasks`
- `GET /api/v1/agentic/projects`
- `GET /api/v1/agentic/policy`
- `PUT /api/v1/agentic/policy`

## Expected flow

### Project path

1. create project
2. manager expands `planned_tasks`
3. project persists
4. normalized plan rows persist
5. project may auto-run child tasks
6. project completion writes project memory

### Task path

1. create task
2. started task-run row persists
3. workflow reaches completed or waiting-for-approval
4. final task-run row persists
5. approval decision persists when applicable
6. completed task writes task memory

## Verification drills

Persistence drills:

- `python3 mcp/tests/drill_agentic_project_plan_persistence.py`
- `python3 mcp/tests/drill_agentic_task_run_persistence.py`
- `python3 mcp/tests/drill_agentic_approval_persistence.py`
- `python3 mcp/tests/drill_agentic_memory_persistence.py`

Control-plane drills:

- `python3 mcp/tests/drill_agentic_control_plane_api.py`
- `python3 mcp/tests/drill_agentic_control_plane_ui.py`
- `python3 mcp/tests/drill_agentic_control_plane_chain.py`
- `python3 mcp/tests/drill_admin_agentic_summary_panel.py`

## Fast debugging flow

### 1. Operator page looks empty

Check:

- `/admin`
- `/admin/monitoring`
- `/admin/agentic`
- `/admin/agentic/control-plane`

Then run:

```bash
python3 mcp/tests/drill_agentic_control_plane_ui.py
python3 mcp/tests/drill_admin_agentic_summary_panel.py
```

### 2. Control-plane page renders but has no rows

Check API surfaces:

```bash
python3 mcp/tests/drill_agentic_control_plane_api.py
python3 mcp/tests/drill_agentic_control_plane_chain.py
```

This tells you whether the issue is:

- no records being written
- read APIs broken
- cross-surface identity drift

If the question is instead “is the platform up but the agentic data empty?”,
check:

- `/admin/monitoring`
- `/app-meta/runtime-status`

That separates:

- platform/runtime outage
- service reachability issue
- empty-but-healthy agentic state

### 3. Persistence seems broken

Run the narrower drills:

```bash
python3 mcp/tests/drill_agentic_project_plan_persistence.py
python3 mcp/tests/drill_agentic_task_run_persistence.py
python3 mcp/tests/drill_agentic_approval_persistence.py
python3 mcp/tests/drill_agentic_memory_persistence.py
```

### 4. Fallback path is in use

The orchestrator starts with `PostgresTaskStore` when DB connect works,
otherwise it degrades to `InMemoryTaskStore`.

If records disappear across restart, check whether the service fell back
to in-memory mode.

## Key files

Backend:

- `services/agent-orchestrator-svc/app/main.py`
- `services/agent-orchestrator-svc/app/service.py`
- `services/agent-orchestrator-svc/app/postgres_store.py`
- `services/agent-orchestrator-svc/app/store.py`
- `services/agent-orchestrator-svc/app/models.py`
- `services/agent-orchestrator-svc/migrations/007_agentic_project_memory.sql`

Frontend:

- `services/frontend/app/admin/page.tsx`
- `services/frontend/app/admin/monitoring/page.tsx`
- `services/frontend/app/admin/agentic/page.tsx`
- `services/frontend/app/admin/agentic/control-plane/page.tsx`
- `services/frontend/app/app-meta/runtime-status/route.ts`
- `services/frontend/components/Sidebar.tsx`
- `services/frontend/lib/api.ts`

Drills:

- `mcp/tests/drill_agentic_project_plan_persistence.py`
- `mcp/tests/drill_agentic_task_run_persistence.py`
- `mcp/tests/drill_agentic_approval_persistence.py`
- `mcp/tests/drill_agentic_memory_persistence.py`
- `mcp/tests/drill_agentic_control_plane_api.py`
- `mcp/tests/drill_agentic_control_plane_ui.py`
- `mcp/tests/drill_agentic_control_plane_chain.py`
- `mcp/tests/drill_admin_agentic_summary_panel.py`
