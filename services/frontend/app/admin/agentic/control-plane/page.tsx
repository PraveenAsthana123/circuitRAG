'use client';

import { useEffect, useMemo, useState } from 'react';

import {
  api,
  ApiError,
  type AgenticApproval,
  type AgenticMemory,
  type AgenticPolicy,
  type AgenticProject,
  type AgenticProjectPlanItem,
  type AgenticRole,
  type AgenticTask,
  type AgenticTaskRun,
} from '../../../../lib/api';

import PipelineDagPanel, {
  PIPELINE_STAGES,
  type PipelineStage,
  type PipelineStageStatus,
} from './PipelineDagPanel';

/**
 * D2: derive pipeline stage states from task_runs.
 *
 * Each task_run.phase maps onto a role_id in PIPELINE_STAGES. We pick
 * the most recent run per role and translate its status into a
 * PipelineStageStatus. Stages with no runs are 'pending'. Stages whose
 * latest run carried routing_decision get tier + cost annotations.
 *
 * Why a derivation instead of a backend endpoint: today task_runs are
 * already loaded by the page; doing the derivation client-side avoids
 * a new API surface and keeps backend changes minimal per §28.
 */
function derivePipelineStages(
  runs: AgenticTaskRun[],
): PipelineStage[] {
  const latestByPhase = new Map<string, AgenticTaskRun>();
  for (const r of runs) {
    const existing = latestByPhase.get(r.phase);
    if (
      !existing ||
      (r.created_at ?? '') > (existing.created_at ?? '')
    ) {
      latestByPhase.set(r.phase, r);
    }
  }

  return PIPELINE_STAGES.map(({ role_id, display_name }) => {
    const run = latestByPhase.get(role_id);
    if (!run) {
      return {
        role_id,
        display_name,
        tier: null,
        cost_usd_cents: null,
        status: 'pending' as PipelineStageStatus,
      };
    }
    const status: PipelineStageStatus =
      run.status === 'completed' || run.status === 'success'
        ? 'success'
        : run.status === 'failed' || run.status === 'fail'
        ? 'fail'
        : run.status === 'blocked' || run.status === 'waiting_for_approval'
        ? 'blocked'
        : run.status === 'started' || run.status === 'in_progress'
        ? 'running'
        : 'pending';

    // routing_decision lives on TaskRunView (added in A5/A4).
    // It's not yet on the AgenticTaskRun TS type — read defensively.
    const routing = (run as unknown as Record<string, unknown>).routing_decision as
      | { chosen?: { tier?: 'tier_a' | 'tier_b' } }
      | null
      | undefined;
    const tier = routing?.chosen?.tier ?? null;
    const cost =
      ((run as unknown as Record<string, unknown>).cost_usd_cents as number | null | undefined) ?? null;

    return {
      role_id,
      display_name,
      tier,
      cost_usd_cents: cost,
      status,
    };
  });
}

function formatWhen(value?: string | null): string {
  if (!value) return 'n/a';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export default function AgenticControlPlanePage() {
  const [agents, setAgents] = useState<AgenticRole[]>([]);
  const [policy, setPolicy] = useState<AgenticPolicy | null>(null);
  const [projects, setProjects] = useState<AgenticProject[]>([]);
  const [tasks, setTasks] = useState<AgenticTask[]>([]);
  const [planItems, setPlanItems] = useState<AgenticProjectPlanItem[]>([]);
  const [taskRuns, setTaskRuns] = useState<AgenticTaskRun[]>([]);
  const [approvals, setApprovals] = useState<AgenticApproval[]>([]);
  const [projectMemories, setProjectMemories] = useState<AgenticMemory[]>([]);
  const [taskMemories, setTaskMemories] = useState<AgenticMemory[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );
  const selectedTask = useMemo(
    () => tasks.find((task) => task.task_id === selectedTaskId) ?? null,
    [tasks, selectedTaskId],
  );
  const tasksForSelectedProject = useMemo(() => {
    if (!selectedProjectId) return tasks;
    return tasks.filter((task) => task.project_id === selectedProjectId);
  }, [tasks, selectedProjectId]);

  async function loadBase() {
    setBusy(true);
    try {
      const [roleRows, policyRow, projectRows, taskRows] = await Promise.all([
        api.agenticListAgents(),
        api.agenticGetPolicy(),
        api.agenticListProjects({ limit: 50 }),
        api.agenticListTasks({ limit: 50 }),
      ]);
      setAgents(roleRows);
      setPolicy(policyRow);
      setProjects(projectRows);
      setTasks(taskRows);
      setSelectedProjectId((prev) => {
        if (prev && projectRows.some((project) => project.project_id === prev)) return prev;
        return projectRows[0]?.project_id ?? '';
      });
      setSelectedTaskId((prev) => {
        if (prev && taskRows.some((task) => task.task_id === prev)) return prev;
        return taskRows[0]?.task_id ?? '';
      });
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadBase();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setPlanItems([]);
      setProjectMemories([]);
      return;
    }

    async function loadProjectDetails() {
      try {
        const [planRows, memoryRows] = await Promise.all([
          api.agenticListProjectPlanItems(selectedProjectId),
          api.agenticListMemories('project', selectedProjectId),
        ]);
        setPlanItems(planRows);
        setProjectMemories(memoryRows);
        setError(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      }
    }

    void loadProjectDetails();
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    if (tasksForSelectedProject.length === 0) {
      setSelectedTaskId('');
      return;
    }
    if (!tasksForSelectedProject.some((task) => task.task_id === selectedTaskId)) {
      setSelectedTaskId(tasksForSelectedProject[0]?.task_id ?? '');
    }
  }, [selectedProjectId, selectedTaskId, tasksForSelectedProject]);

  useEffect(() => {
    if (!selectedTaskId) {
      setTaskRuns([]);
      setApprovals([]);
      setTaskMemories([]);
      return;
    }

    async function loadTaskDetails() {
      try {
        const [runRows, approvalRows, memoryRows] = await Promise.all([
          api.agenticListTaskRuns(selectedTaskId),
          api.agenticListTaskApprovals(selectedTaskId),
          api.agenticListMemories('task', selectedTaskId),
        ]);
        setTaskRuns(runRows);
        setApprovals(approvalRows);
        setTaskMemories(memoryRows);
        setError(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      }
    }

    void loadTaskDetails();
  }, [selectedTaskId]);

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Agentic control plane</h1>
          <p className="page-subtitle">
            One place for the full agentic graph: role routing, approval policy, normalized project
            plan rows, task runs, human approvals, and distilled memories.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn" disabled={busy} onClick={() => void loadBase()}>
            {busy ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div
        style={{
          display: 'grid',
          gap: 12,
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          marginBottom: 24,
        }}
      >
        <div className="surface-muted">
          <div className="result-meta">Projects</div>
          <strong style={{ fontSize: 24 }}>{projects.length}</strong>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Tasks</div>
          <strong style={{ fontSize: 24 }}>{tasks.length}</strong>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Roles</div>
          <strong style={{ fontSize: 24 }}>{agents.length}</strong>
        </div>
        <div className="surface-muted">
          <div className="result-meta">Approval mode</div>
          <strong style={{ fontSize: 24 }}>{policy?.approval_mode ?? 'n/a'}</strong>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Jump to each surface</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          }}
        >
          <a className="surface-muted" href="#role-routing-policy" style={{ textDecoration: 'none', color: 'inherit' }}>
            <strong>Role routing and policy</strong>
            <div className="field-help" style={{ marginTop: 8 }}>
              Active roles, models, and approval defaults.
            </div>
          </a>
          <a className="surface-muted" href="#project-graph" style={{ textDecoration: 'none', color: 'inherit' }}>
            <strong>Project graph</strong>
            <div className="field-help" style={{ marginTop: 8 }}>
              Normalized plan rows and project memory.
            </div>
          </a>
          <a className="surface-muted" href="#task-execution-trail" style={{ textDecoration: 'none', color: 'inherit' }}>
            <strong>Task execution trail</strong>
            <div className="field-help" style={{ marginTop: 8 }}>
              Task runs, approvals, and task memory.
            </div>
          </a>
        </div>
      </div>

      <div id="role-routing-policy" className="card" style={{ marginBottom: 24 }}>
        <h2 style={{ marginBottom: 12 }}>Role routing and policy</h2>
        <div
          style={{
            display: 'grid',
            gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          }}
        >
          {agents.map((agent) => (
            <div key={agent.role_id} className="surface-muted">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <strong>{agent.display_name}</strong>
                <code>{agent.role_type}</code>
              </div>
              <div className="result-meta" style={{ marginTop: 6 }}>{agent.role_id}</div>
              <div style={{ marginTop: 10 }}>{agent.description}</div>
              <div style={{ marginTop: 10 }}>
                <strong>Model:</strong> <code>{agent.model}</code>
              </div>
            </div>
          ))}
        </div>
        {policy && (
          <div className="surface-muted" style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div><strong>Human approval:</strong> {String(policy.require_human_approval)}</div>
              <div><strong>Auto-advance:</strong> {String(policy.auto_advance)}</div>
              <div><strong>Confidence threshold:</strong> {policy.confidence_threshold}</div>
            </div>
            <div style={{ marginTop: 10 }}>
              <strong>Sensitive namespaces:</strong>{' '}
              <code>{policy.require_for_tool_namespaces.join(', ') || 'none'}</code>
            </div>
          </div>
        )}
      </div>

      <div id="project-graph" className="card" style={{ marginBottom: 24 }}>
        <div className="page-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <div>
            <h2>Project graph</h2>
            <div className="field-help">Normalized plan rows and project-scoped memory for the selected project.</div>
          </div>
          <div className="field-group" style={{ minWidth: 280 }}>
            <label className="field-label" htmlFor="agentic-project-select">Project</label>
            <select
              id="agentic-project-select"
              className="select"
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
            >
              <option value="">Select a project</option>
              {projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {selectedProject ? (
          <>
            <div className="surface-muted" style={{ marginBottom: 16 }}>
              <div><strong>{selectedProject.name}</strong></div>
              <div style={{ marginTop: 8 }}>{selectedProject.goal}</div>
              <div className="result-meta" style={{ marginTop: 8 }}>
                {selectedProject.project_id} · status={selectedProject.status} · tasks={selectedProject.task_ids.length}
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Risk</th>
                    <th>Task</th>
                  </tr>
                </thead>
                <tbody>
                  {planItems.map((item) => (
                    <tr key={item.plan_item_id}>
                      <td>{item.sort_index + 1}</td>
                      <td>
                        <div><strong>{item.title}</strong></div>
                        <div className="result-meta" style={{ marginTop: 4 }}>{item.objective}</div>
                      </td>
                      <td>{item.status}</td>
                      <td>{item.risk_level}</td>
                      <td><code>{item.task_id ?? 'pending'}</code></td>
                    </tr>
                  ))}
                  {planItems.length === 0 && (
                    <tr><td colSpan={5} className="field-help">No normalized plan items found yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 16 }}>
              <h3 style={{ marginBottom: 10 }}>Project memories</h3>
              {projectMemories.length === 0 && <div className="field-help">No project memory rows yet.</div>}
              <div style={{ display: 'grid', gap: 12 }}>
                {projectMemories.map((memory) => (
                  <div key={memory.memory_id} className="surface-muted">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <strong>{memory.memory_kind}</strong>
                      <span className="result-meta">{formatWhen(memory.created_at)}</span>
                    </div>
                    <div style={{ marginTop: 8 }}>{memory.summary}</div>
                    <pre style={{ marginTop: 10, overflowX: 'auto' }}>{pretty(memory.payload)}</pre>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="field-help">Select a project to inspect normalized plan rows and memories.</div>
        )}
      </div>

      <div id="task-execution-trail" className="card">
        <div className="page-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <div>
            <h2>Task execution trail</h2>
            <div className="field-help">Started/final task runs, human approvals, and task-scoped memory for the selected task.</div>
          </div>
          <div className="field-group" style={{ minWidth: 320 }}>
            <label className="field-label" htmlFor="agentic-task-select">Task</label>
            <select
              id="agentic-task-select"
              className="select"
              value={selectedTaskId}
              onChange={(e) => setSelectedTaskId(e.target.value)}
            >
              <option value="">Select a task</option>
              {tasksForSelectedProject.map((task) => (
                <option key={task.task_id} value={task.task_id}>
                  {task.goal.slice(0, 72)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {selectedTask ? (
          <>
            <div className="surface-muted" style={{ marginBottom: 16 }}>
              <div><strong>{selectedTask.goal}</strong></div>
              <div className="result-meta" style={{ marginTop: 8 }}>
                {selectedTask.task_id} · status={selectedTask.status} · risk={selectedTask.risk_level}
              </div>
              <div style={{ marginTop: 10 }}>
                <strong>Advisor summary:</strong> {selectedTask.advisor_summary ?? 'n/a'}
              </div>
              <div style={{ marginTop: 6 }}>
                <strong>Next action:</strong> {selectedTask.next_action ?? 'n/a'}
              </div>
            </div>

            <h3 style={{ marginBottom: 10 }}>Pipeline DAG</h3>
            <div style={{ marginBottom: 16 }}>
              <PipelineDagPanel
                stages={derivePipelineStages(taskRuns)}
                totalCostCents={taskRuns.reduce(
                  (sum, r) =>
                    sum +
                    (((r as unknown as Record<string, unknown>).cost_usd_cents as number | null | undefined) ?? 0),
                  0,
                )}
              />
            </div>

            <h3 style={{ marginBottom: 10 }}>Task runs</h3>
            <div className="table-wrap" style={{ marginBottom: 16 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Phase</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {taskRuns.map((run) => (
                    <tr key={`${run.run_id}-${run.status}-${run.created_at ?? 'na'}`}>
                      <td>{formatWhen(run.created_at)}</td>
                      <td>{run.phase}</td>
                      <td>{run.status}</td>
                      <td>{run.confidence ?? 'n/a'}</td>
                      <td>{run.risk_level ?? 'n/a'}</td>
                    </tr>
                  ))}
                  {taskRuns.length === 0 && (
                    <tr><td colSpan={5} className="field-help">No task runs found yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            {taskRuns.length > 0 && (
              <div className="surface-muted" style={{ marginBottom: 16 }}>
                <strong>Latest run payload</strong>
                <pre style={{ marginTop: 10, overflowX: 'auto' }}>{pretty(taskRuns[taskRuns.length - 1])}</pre>
              </div>
            )}

            <h3 style={{ marginBottom: 10 }}>Human approvals</h3>
            <div className="table-wrap" style={{ marginBottom: 16 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Decision</th>
                    <th>Actor</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {approvals.map((approval) => (
                    <tr key={approval.approval_id}>
                      <td>{formatWhen(approval.created_at)}</td>
                      <td>{approval.decision}</td>
                      <td>{approval.actor_id}</td>
                      <td>{approval.reason || 'n/a'}</td>
                    </tr>
                  ))}
                  {approvals.length === 0 && (
                    <tr><td colSpan={4} className="field-help">No approval rows found yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginBottom: 10 }}>Task memories</h3>
            {taskMemories.length === 0 && <div className="field-help">No task memory rows yet.</div>}
            <div style={{ display: 'grid', gap: 12 }}>
              {taskMemories.map((memory) => (
                <div key={memory.memory_id} className="surface-muted">
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <strong>{memory.memory_kind}</strong>
                    <span className="result-meta">{formatWhen(memory.created_at)}</span>
                  </div>
                  <div style={{ marginTop: 8 }}>{memory.summary}</div>
                  <pre style={{ marginTop: 10, overflowX: 'auto' }}>{pretty(memory.payload)}</pre>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="field-help">Select a task to inspect task runs, approvals, and task-scoped memories.</div>
        )}
      </div>
    </>
  );
}
