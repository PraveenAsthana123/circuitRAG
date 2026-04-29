'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, ApiError, type AgenticApprovalSimulation, type AgenticPolicy, type AgenticProject, type AgenticRole, type AgenticTask } from '../../../lib/api';

type Risk = 'low' | 'medium' | 'high';
type ApprovalMode = 'manual' | 'plan_once' | 'policy_auto';

export default function AgenticAdminPage() {
  const [goal, setGoal] = useState('');
  const [risk, setRisk] = useState<Risk>('medium');
  const [useGlobalPolicy, setUseGlobalPolicy] = useState(true);
  const [requireApproval, setRequireApproval] = useState(false);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>('plan_once');
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [policyActorId, setPolicyActorId] = useState('admin-user');
  const [policy, setPolicy] = useState<AgenticPolicy | null>(null);
  const [policyNamespacesText, setPolicyNamespacesText] = useState('identity, finops, itsm');
  const [projectName, setProjectName] = useState('');
  const [projectGoal, setProjectGoal] = useState('');
  const [projects, setProjects] = useState<AgenticProject[]>([]);
  const [agents, setAgents] = useState<AgenticRole[]>([]);
  const [projectId, setProjectId] = useState('');
  const [toolNamespace, setToolNamespace] = useState('');
  const [toolName, setToolName] = useState('');
  const [toolArgsText, setToolArgsText] = useState('{\n  "example": true\n}');
  const [actorId, setActorId] = useState('admin-user');
  const [decisionReason, setDecisionReason] = useState('');
  const [tasks, setTasks] = useState<AgenticTask[]>([]);
  const [selected, setSelected] = useState<AgenticTask | null>(null);
  const [simulation, setSimulation] = useState<AgenticApprovalSimulation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadTasks() {
    try {
      const rows = await api.agenticListTasks({ limit: 20 });
      setTasks(rows);
      setSelected((prev) => (prev ? rows.find((row) => row.task_id === prev.task_id) ?? prev : rows[0] ?? null));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function loadProjects() {
    try {
      const rows = await api.agenticListProjects({ limit: 20 });
      setProjects(rows);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function loadPolicy() {
    try {
      const current = await api.agenticGetPolicy();
      setPolicy(current);
      setRequireApproval(current.require_human_approval);
      setApprovalMode(current.approval_mode);
      setAutoAdvance(current.auto_advance);
      setPolicyNamespacesText(current.require_for_tool_namespaces.join(', '));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function loadAgents() {
    try {
      const rows = await api.agenticListAgents();
      setAgents(rows);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  useEffect(() => {
    void loadTasks();
    void loadPolicy();
    void loadProjects();
    void loadAgents();
  }, []);

  async function submitTask(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const toolArguments = toolArgsText.trim() ? JSON.parse(toolArgsText) : {};
      const task = await api.agenticCreateTask({
        goal,
        tenant_id: 'demo-tenant',
        project_id: projectId || null,
        risk_level: risk,
        use_global_policy: useGlobalPolicy,
        require_human_approval: useGlobalPolicy ? null : requireApproval,
        approval_mode: useGlobalPolicy ? undefined : approvalMode,
        auto_advance: useGlobalPolicy ? null : autoAdvance,
        tool_namespace: toolNamespace || undefined,
        tool_name: toolName || undefined,
        tool_arguments: toolArguments,
      });
      setGoal('');
      setSelected(task);
      await loadTasks();
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function createProject() {
    if (!projectName.trim() || !projectGoal.trim()) return;
    setBusy(true);
    try {
      await api.agenticCreateProject({
        name: projectName,
        goal: projectGoal,
        tenant_id: 'demo-tenant',
        use_global_policy: true,
      });
      setProjectName('');
      setProjectGoal('');
      await loadProjects();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runSimulation() {
    setBusy(true);
    try {
      const toolArguments = toolArgsText.trim() ? JSON.parse(toolArgsText) : {};
      const resp = await api.agenticSimulatePolicy({
        tenant_id: 'demo-tenant',
        goal: goal || 'simulated task',
        risk_level: risk,
        project_id: projectId || null,
        use_global_policy: useGlobalPolicy,
        require_human_approval: useGlobalPolicy ? null : requireApproval,
        approval_mode: useGlobalPolicy ? undefined : approvalMode,
        auto_advance: useGlobalPolicy ? null : autoAdvance,
        tool_namespace: toolNamespace || undefined,
        tool_name: toolName || undefined,
        tool_arguments: toolArguments,
      });
      setSimulation(resp);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function savePolicy() {
    setBusy(true);
    try {
      const updated = await api.agenticUpdatePolicy({
        require_human_approval: requireApproval,
        approval_mode: approvalMode,
        auto_advance: autoAdvance,
        require_for_high_risk: policy?.require_for_high_risk ?? true,
        require_for_low_confidence: policy?.require_for_low_confidence ?? true,
        confidence_threshold: policy?.confidence_threshold ?? 0.8,
        require_for_risk_flags: policy?.require_for_risk_flags ?? true,
        require_for_destructive_tools: policy?.require_for_destructive_tools ?? true,
        require_for_tool_namespaces: policyNamespacesText
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
        updated_by: policyActorId,
      });
      setPolicy(updated);
      setUseGlobalPolicy(true);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function decide(approved: boolean) {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await api.agenticApproveTask(selected.task_id, {
        approved,
        actor_id: actorId,
        reason: decisionReason || undefined,
      });
      setSelected(updated);
      await loadTasks();
      setDecisionReason('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Agentic tasks</h1>
          <p className="page-subtitle">
            Submit a bounded agentic task, choose whether approval happens manually, once after the
            plan, or automatically by policy, and let the workflow continue without repeated clicks.
          </p>
        </div>
        <div className="page-actions">
          <Link className="btn" href="/admin/agentic/control-plane">
            Open control plane
          </Link>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="page-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <div>
            <h2>Agent roles</h2>
            <div className="field-help">
              Active orchestrator role routing and local Ollama model bindings.
            </div>
          </div>
        </div>
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          {agents.map((agent) => (
            <div key={agent.role_id} className="surface-muted">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                <strong>{agent.display_name}</strong>
                <code>{agent.role_type}</code>
              </div>
              <div className="result-meta" style={{ marginTop: 6 }}>{agent.role_id}</div>
              <div style={{ marginTop: 10 }}>{agent.description}</div>
              <div style={{ marginTop: 10 }}>
                <strong>Model:</strong> <code>{agent.model}</code>
              </div>
              {agent.source_agent_name && (
                <div className="result-meta" style={{ marginTop: 6 }}>
                  mirrors sidecar agent <code>{agent.source_agent_name}</code>
                </div>
              )}
            </div>
          ))}
          {agents.length === 0 && <div className="field-help">No agent roles loaded.</div>}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="page-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <div>
            <h2>Projects</h2>
            <div className="field-help">Create a project once, then attach tasks so they inherit the same approval policy.</div>
          </div>
        </div>
        <div className="form-row">
          <div className="field-group">
            <label className="field-label" htmlFor="project-name">Project name</label>
            <input id="project-name" className="input" value={projectName} onChange={(e) => setProjectName(e.target.value)} />
          </div>
          <div className="field-group">
            <label className="field-label" htmlFor="project-goal">Project goal</label>
            <input id="project-goal" className="input" value={projectGoal} onChange={(e) => setProjectGoal(e.target.value)} />
          </div>
          <div className="field-group" style={{ alignSelf: 'end' }}>
            <button className="btn btn-primary" disabled={busy || !projectName.trim() || !projectGoal.trim()} onClick={() => void createProject()}>
              Create project
            </button>
          </div>
        </div>
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Status</th>
                <th>Planned tasks</th>
                <th>Tasks</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.project_id}>
                  <td>
                    <div><strong>{project.name}</strong></div>
                    <div className="result-meta">{project.project_id.slice(0, 8)}</div>
                  </td>
                  <td>{project.status}</td>
                  <td>{project.planned_tasks.length}</td>
                  <td>{project.task_ids.length}</td>
                </tr>
              ))}
              {projects.length === 0 && (
                <tr><td colSpan={4} className="field-help">No projects yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {projects.length > 0 && (
          <div className="surface-muted" style={{ marginTop: 16 }}>
            <strong>Latest project child-task plan</strong>
            <ol style={{ marginTop: 8, paddingLeft: 20 }}>
              {projects[0].planned_tasks.map((item) => (
                <li key={`${projects[0].project_id}-${item.step_id}`}>
                  <strong>{item.title}</strong>
                  {' · '}
                  <code>{item.suggested_risk}</code>
                  <div style={{ marginTop: 4 }}>{item.goal}</div>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="page-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <div>
            <h2>Global approval policy</h2>
            <div className="field-help">
              New tasks inherit this policy by default so you do not have to approve every step repeatedly.
            </div>
          </div>
          {policy?.updated_at && (
            <div className="result-meta">
              updated {new Date(policy.updated_at).toLocaleString()}
              {policy.updated_by ? ` by ${policy.updated_by}` : ''}
            </div>
          )}
        </div>
        <div className="form-row">
          <div className="field-group">
            <label className="field-label" htmlFor="policy-approval-mode">Approval mode</label>
            <select
              id="policy-approval-mode"
              className="select"
              value={approvalMode}
              onChange={(e) => setApprovalMode(e.target.value as ApprovalMode)}
            >
              <option value="manual">manual</option>
              <option value="plan_once">plan_once</option>
              <option value="policy_auto">policy_auto</option>
            </select>
          </div>
          <div className="field-group">
            <label className="field-label" htmlFor="policy-actor-id">Updated by</label>
            <input
              id="policy-actor-id"
              className="input"
              value={policyActorId}
              onChange={(e) => setPolicyActorId(e.target.value)}
              placeholder="admin-user"
            />
          </div>
        </div>
        <label className="field-help">
          <input type="checkbox" checked={requireApproval} onChange={(e) => setRequireApproval(e.target.checked)} /> require human approval
        </label>
        <label className="field-help">
          <input type="checkbox" checked={autoAdvance} onChange={(e) => setAutoAdvance(e.target.checked)} /> auto-advance after approval
        </label>
        <label className="field-help">
          <input
            type="checkbox"
            checked={policy?.require_for_high_risk ?? true}
            onChange={(e) => setPolicy((prev) => prev ? { ...prev, require_for_high_risk: e.target.checked } : prev)}
          /> require approval for high-risk tasks
        </label>
        <label className="field-help">
          <input
            type="checkbox"
            checked={policy?.require_for_low_confidence ?? true}
            onChange={(e) => setPolicy((prev) => prev ? { ...prev, require_for_low_confidence: e.target.checked } : prev)}
          /> require approval for low-confidence outputs
        </label>
        <label className="field-help">
          <input
            type="checkbox"
            checked={policy?.require_for_risk_flags ?? true}
            onChange={(e) => setPolicy((prev) => prev ? { ...prev, require_for_risk_flags: e.target.checked } : prev)}
          /> require approval for degraded/failing risk flags
        </label>
        <label className="field-help">
          <input
            type="checkbox"
            checked={policy?.require_for_destructive_tools ?? true}
            onChange={(e) => setPolicy((prev) => prev ? { ...prev, require_for_destructive_tools: e.target.checked } : prev)}
          /> require approval for destructive or write-capable tools
        </label>
        <div className="field-group">
          <label className="field-label" htmlFor="policy-confidence-threshold">Confidence threshold</label>
          <input
            id="policy-confidence-threshold"
            className="input"
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={policy?.confidence_threshold ?? 0.8}
            onChange={(e) => setPolicy((prev) => prev ? { ...prev, confidence_threshold: Number(e.target.value) } : prev)}
          />
        </div>
        <div className="field-group">
          <label className="field-label" htmlFor="policy-namespaces">Sensitive namespaces</label>
          <input
            id="policy-namespaces"
            className="input"
            value={policyNamespacesText}
            onChange={(e) => setPolicyNamespacesText(e.target.value)}
            placeholder="identity, finops, itsm"
          />
        </div>
        <div className="page-actions" style={{ marginTop: 12 }}>
          <button className="btn btn-primary" disabled={busy || !policyActorId.trim()} onClick={() => void savePolicy()}>
            Save global policy
          </button>
          <button className="btn" disabled={busy} onClick={() => void loadPolicy()}>
            Reload policy
          </button>
        </div>
      </div>

      <div className="split-grid">
        <div className="card">
          <h2 style={{ marginBottom: 12 }}>Create task</h2>
          <form className="form-stack" onSubmit={submitTask}>
            <div className="field-group">
              <label className="field-label" htmlFor="agentic-goal">Goal</label>
              <textarea
                id="agentic-goal"
                className="textarea"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Create an ITSM incident draft for the retrieval outage."
              />
            </div>
            <div className="form-row">
              <div className="field-group">
                <label className="field-label" htmlFor="agentic-risk">Risk</label>
                <select id="agentic-risk" className="select" value={risk} onChange={(e) => setRisk(e.target.value as Risk)}>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="agentic-project">Project</label>
                <select id="agentic-project" className="select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">none</option>
                  {projects.map((project) => (
                    <option key={project.project_id} value={project.project_id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="agentic-namespace">Tool namespace</label>
                <input id="agentic-namespace" className="input" value={toolNamespace} onChange={(e) => setToolNamespace(e.target.value)} placeholder="itsm" />
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="agentic-tool">Tool name</label>
                <input id="agentic-tool" className="input" value={toolName} onChange={(e) => setToolName(e.target.value)} placeholder="incident.create" />
              </div>
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="agentic-args">Tool arguments JSON</label>
              <textarea
                id="agentic-args"
                className="textarea"
                value={toolArgsText}
                onChange={(e) => setToolArgsText(e.target.value)}
                style={{ minHeight: 120, fontFamily: 'var(--font-mono)' }}
              />
            </div>
            <label className="field-help">
              <input type="checkbox" checked={useGlobalPolicy} onChange={(e) => setUseGlobalPolicy(e.target.checked)} /> use global approval policy
            </label>
            {!useGlobalPolicy && (
              <>
                <div className="field-group">
                  <label className="field-label" htmlFor="agentic-approval-mode">Per-task approval mode</label>
                  <select
                    id="agentic-approval-mode"
                    className="select"
                    value={approvalMode}
                    onChange={(e) => setApprovalMode(e.target.value as ApprovalMode)}
                  >
                    <option value="manual">manual</option>
                    <option value="plan_once">plan_once</option>
                    <option value="policy_auto">policy_auto</option>
                  </select>
                </div>
                <label className="field-help">
                  <input type="checkbox" checked={requireApproval} onChange={(e) => setRequireApproval(e.target.checked)} /> require human approval
                </label>
                <label className="field-help">
                  <input type="checkbox" checked={autoAdvance} onChange={(e) => setAutoAdvance(e.target.checked)} /> auto-advance after approval
                </label>
              </>
            )}
            <label className="field-help">
              Effective policy:
              {' '}
              <code>{useGlobalPolicy ? (policy?.approval_mode ?? 'loading') : approvalMode}</code>
            </label>
            <div className="surface-muted" style={{ fontSize: 13 }}>
              <strong>Modes</strong>
              <div style={{ marginTop: 8 }}>
                <code>manual</code>: pause whenever the policy says human approval is needed.
              </div>
              <div>
                <code>plan_once</code>: stop once after the plan is ready, then approval resumes the rest automatically.
              </div>
              <div>
                <code>policy_auto</code>: global policy auto-approves and runs to completion without button presses.
              </div>
            </div>
            <div className="page-actions">
              <button type="button" className="btn" disabled={busy} onClick={() => void runSimulation()}>
                Simulate approval
              </button>
              <button type="submit" className="btn btn-primary" disabled={busy || !goal.trim()}>
                {busy ? 'Submitting...' : 'Submit task'}
              </button>
            </div>
          </form>
          {simulation && (
            <div className="surface-muted" style={{ marginTop: 16 }}>
              <strong>Approval simulator</strong>
              <div className="result-meta" style={{ marginTop: 8 }}>
                {simulation.approval_required ? 'Approval required' : 'No approval required'}
                {' · '}
                mode <code>{simulation.effective_policy.approval_mode}</code>
              </div>
              <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                {simulation.approval_reasons.length > 0
                  ? simulation.approval_reasons.map((reason) => <li key={reason}>{reason}</li>)
                  : <li>none</li>}
              </ul>
            </div>
          )}
        </div>

        <div className="card">
          <div className="page-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <h2>Recent tasks</h2>
            <button className="btn" onClick={() => void loadTasks()}>Refresh</button>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Status</th>
                  <th>Risk</th>
                  <th>Tool</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.task_id} onClick={() => setSelected(task)} style={{ cursor: 'pointer', background: selected?.task_id === task.task_id ? '#fff7ed' : undefined }}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{task.task_id.slice(0, 8)}</td>
                    <td>{task.status}</td>
                    <td>{task.risk_level}</td>
                    <td>{task.tool_namespace && task.tool_name ? `${task.tool_namespace}.${task.tool_name}` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {selected && (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="page-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <div>
              <h2>Task detail</h2>
              <div className="result-meta">{selected.task_id}</div>
            </div>
            <div className="result-meta">
              {selected.status} · confidence {selected.confidence ?? '-'}
            </div>
          </div>

          <div className="split-grid">
            <div className="stack">
              <div className="surface-muted">
                <strong>Goal</strong>
                <div style={{ marginTop: 8 }}>{selected.goal}</div>
                <div className="result-meta" style={{ marginTop: 8 }}>
                  {selected.approval_mode} · auto-advance {selected.auto_advance ? 'on' : 'off'}
                </div>
              </div>
              <div className="surface-muted">
                <strong>Plan</strong>
                <ol style={{ marginTop: 8, paddingLeft: 20 }}>
                  {selected.plan.map((step) => <li key={step}>{step}</li>)}
                </ol>
              </div>
              <div className="surface-muted">
                <strong>Worker output</strong>
                <div style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>{selected.worker_output ?? '-'}</div>
              </div>
              <div className="surface-muted">
                <strong>Advisor summary</strong>
                <div style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>{selected.advisor_summary ?? '-'}</div>
              </div>
            </div>

            <div className="stack">
              <div className="surface-muted">
                <strong>Reviewer notes</strong>
                <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                  {selected.reviewer_notes.map((note) => <li key={note}>{note}</li>)}
                </ul>
              </div>
              <div className="surface-muted">
                <strong>Approval reasons</strong>
                <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                  {selected.approval_reasons.length > 0
                    ? selected.approval_reasons.map((reason) => <li key={reason}>{reason}</li>)
                    : <li>none</li>}
                </ul>
              </div>
              <div className="surface-muted">
                <strong>Approval</strong>
                <div className="form-stack" style={{ marginTop: 8 }}>
                  <input className="input" value={actorId} onChange={(e) => setActorId(e.target.value)} placeholder="actor id" />
                  <textarea className="textarea" value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} placeholder="Reason for approval/rejection" />
                  <div className="page-actions">
                    <button className="btn btn-primary" disabled={busy} onClick={() => void decide(true)}>
                      {selected.status === 'waiting_for_plan_approval' ? 'Approve plan and continue' : 'Approve'}
                    </button>
                    <button className="btn" disabled={busy} onClick={() => void decide(false)}>Reject</button>
                  </div>
                </div>
              </div>
              <details className="surface-muted">
                <summary style={{ cursor: 'pointer', fontWeight: 'var(--font-weight-medium)' }}>Audit trail</summary>
                <pre style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{JSON.stringify(selected.audit_events, null, 2)}</pre>
              </details>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
