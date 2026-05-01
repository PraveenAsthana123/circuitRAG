'use client';

/**
 * PipelineDagPanel (Phase C5).
 *
 * Visualises the 9-stage agentic pipeline:
 *   research → strategy → code → review → test → security → advise → deploy → observe
 *
 * Each stage shows:
 *   - role display name
 *   - tier (A=local Ollama, B=cloud Claude/Codex)
 *   - cost cents (when stage has run)
 *   - status badge (pending / running / success / fail / blocked)
 *
 * Component is standalone — the parent control-plane page can mount
 * it as a tab. Today the props default to all-pending so it renders
 * a meaningful structural diagram even before a task is selected.
 *
 * Why a separate file: §28 backward compat — existing control-plane
 * page keeps working unchanged; adding the panel is one import line
 * for the operator to wire in their preferred layout.
 *
 * Drilled by mcp/tests/drill_pipeline_dag_panel.py — source-level
 * verification that all 9 stages and cost column are present.
 */

export type PipelineStageStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'fail'
  | 'blocked'
  | 'skipped';

export interface PipelineStage {
  role_id: string;
  display_name: string;
  tier?: 'tier_a' | 'tier_b' | null;
  cost_usd_cents?: number | null;
  status: PipelineStageStatus;
  notes?: string | null;
}

// The 9 canonical stages, in order, matching app/agent_registry.py.
export const PIPELINE_STAGES: ReadonlyArray<{ role_id: string; display_name: string }> = [
  { role_id: 'researcher', display_name: 'Researcher' },
  { role_id: 'strategist', display_name: 'Strategist' },
  { role_id: 'coder_executor', display_name: 'Coder Executor' },
  { role_id: 'reviewer', display_name: 'Reviewer' },
  { role_id: 'tester', display_name: 'Tester' },
  { role_id: 'security_advisor', display_name: 'Security Advisor' },
  { role_id: 'advisor', display_name: 'Advisor' },
  { role_id: 'deployer', display_name: 'Deployer' },
  { role_id: 'observer', display_name: 'Observer' },
];

const STATUS_COLORS: Record<PipelineStageStatus, string> = {
  pending: '#9ca3af',
  running: '#3b82f6',
  success: '#10b981',
  fail: '#ef4444',
  blocked: '#f59e0b',
  skipped: '#d1d5db',
};

const TIER_LABELS: Record<string, string> = {
  tier_a: 'A·local',
  tier_b: 'B·cloud',
};

interface PipelineDagPanelProps {
  stages?: PipelineStage[];
  totalCostCents?: number;
}

export default function PipelineDagPanel({
  stages,
  totalCostCents,
}: PipelineDagPanelProps) {
  // Default all stages to pending if no per-task data supplied.
  const effectiveStages: PipelineStage[] =
    stages ??
    PIPELINE_STAGES.map((s) => ({
      role_id: s.role_id,
      display_name: s.display_name,
      tier: null,
      cost_usd_cents: null,
      status: 'pending' as PipelineStageStatus,
    }));

  const totalCost =
    totalCostCents ??
    effectiveStages.reduce((sum, s) => sum + (s.cost_usd_cents ?? 0), 0);

  return (
    <section
      aria-label="Pipeline DAG"
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        padding: 16,
        background: '#ffffff',
      }}
    >
      <header
        style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}
      >
        <h3 style={{ margin: 0, fontSize: 16 }}>Pipeline DAG</h3>
        <span style={{ color: '#6b7280', fontSize: 13 }}>
          Total cost: <strong>${(totalCost / 100).toFixed(2)}</strong> ({totalCost} ¢)
        </span>
      </header>

      <ol
        style={{
          listStyle: 'none',
          padding: 0,
          margin: 0,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
          gap: 8,
        }}
      >
        {effectiveStages.map((stage, idx) => (
          <li
            key={stage.role_id}
            style={{
              border: `1px solid ${STATUS_COLORS[stage.status]}`,
              borderRadius: 6,
              padding: '8px 10px',
              background: '#fafafa',
              position: 'relative',
            }}
            aria-label={`Stage ${idx + 1}: ${stage.display_name}, status ${stage.status}`}
          >
            <div
              style={{
                fontSize: 11,
                color: '#6b7280',
                marginBottom: 2,
              }}
            >
              {idx + 1}. {stage.role_id}
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              {stage.display_name}
            </div>
            <div
              style={{
                display: 'flex',
                gap: 4,
                alignItems: 'center',
                fontSize: 11,
              }}
            >
              <span
                style={{
                  background: STATUS_COLORS[stage.status],
                  color: '#fff',
                  padding: '1px 6px',
                  borderRadius: 3,
                  fontWeight: 500,
                }}
              >
                {stage.status}
              </span>
              {stage.tier && (
                <span style={{ color: '#6b7280' }}>{TIER_LABELS[stage.tier]}</span>
              )}
              {stage.cost_usd_cents != null && stage.cost_usd_cents > 0 && (
                <span style={{ color: '#6b7280' }}>
                  {stage.cost_usd_cents}¢
                </span>
              )}
            </div>
            {stage.notes && (
              <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 4 }}>
                {stage.notes}
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
