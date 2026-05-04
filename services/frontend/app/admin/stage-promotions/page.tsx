/**
 * /admin/stage-promotions — Stage-1/2/3 lifecycle tracker.
 *
 * Server Component. Per §44 autonomous-loop discipline + §56
 * techstack-additions policy: every adapter ships through
 * Stage-1 (contract) → Stage-2 (wiring) → Stage-3 (default-flip
 * or consolidation). This page tracks the lifecycle in one place.
 */

import Link from 'next/link';

type StageStatus = 'shipped' | 'pending' | 'na' | 'rejected';

const STAGE_STYLE: Record<StageStatus, { bg: string; fg: string; icon: string }> = {
  shipped:  { bg: '#dff2dd', fg: '#1f8a4c', icon: '✅' },
  pending:  { bg: '#fef3e1', fg: '#c47a1a', icon: '⏭' },
  na:       { bg: '#f0f0f0', fg: '#666', icon: '—' },
  rejected: { bg: '#fdeaea', fg: '#a4262c', icon: '❌' },
};

type Stage = {
  status: StageStatus;
  commit?: string;
  note?: string;
};

type Component = {
  name: string;
  category: string;
  source_path: string;
  stage1: Stage;
  stage2: Stage;
  stage3: Stage;
  next_action?: string;
};

const COMPONENTS: Component[] = [
  // ── Adapters (full Stage-1/2/3 chain pattern) ─────────────────────────
  {
    name: 'LiteLLM adapter',
    category: 'adapter',
    source_path: 'scripts/litellm_adapter.py',
    stage1: { status: 'shipped', commit: 'd57d15c', note: 'Adapter contract; signature parity with call_ollama' },
    stage2: { status: 'shipped', commit: '1858cad', note: 'Curl-failure fallback inside call_ollama' },
    stage3: { status: 'shipped', note: '_skip_gate consolidates double-gate (50% audit reduction on fallback)' },
    next_action: 'Stage-4: empirical eval to flip default (litellm-first vs curl-first)',
  },
  {
    name: 'PydanticAI adapter',
    category: 'adapter',
    source_path: 'scripts/pydanticai_adapter.py',
    stage1: { status: 'shipped', commit: 'b1df214', note: 'Adapter contract; validate(text, schema_cls)' },
    stage2: { status: 'shipped', note: 'Regex-failure fallback inside validate_council_proposal' },
    stage3: { status: 'pending', note: 'Default-flip blocked on empirical eval data' },
    next_action: 'Run 10+ council cycles with PYDANTICAI_ENABLED=1; measure rescue rate; flip if >0%',
  },
  {
    name: 'Kafka event-publisher',
    category: 'adapter',
    source_path: 'scripts/event_publisher.py',
    stage1: { status: 'shipped', commit: '589cfeb', note: '4 topics; CloudEvents envelope' },
    stage2: { status: 'shipped', note: '3 layers wired (PolisAI/OpenClaw/Router); Paperclip deliberately not wired' },
    stage3: { status: 'na', note: 'No Stage-3 needed — opt-in flag is the contract; no double-fire to consolidate' },
  },
  {
    name: 'MCP Gateway',
    category: 'adapter',
    source_path: 'scripts/mcp_gateway.py',
    stage1: { status: 'shipped', note: '4-layer defense (flag + allowlist + actors + rate-limit + audit)' },
    stage2: { status: 'shipped', commit: 'bcdeb1d', note: 'mcp/client.py routed through gateway before CB+HTTP' },
    stage3: { status: 'shipped', note: 'MCP_GATEWAY_STRICT mode — missing PolisAI rule → deny (vs fall-through)' },
    next_action: 'Stage-4: drill that fails build if STRICT mode lacks rules for any used mcp:<server>:<tool>',
  },

  // ── Layer scaffolds (different Stage-2/3 patterns) ────────────────────
  {
    name: 'PolisAI policy engine',
    category: 'layer-4',
    source_path: 'scripts/policy_check.py',
    stage1: { status: 'shipped', commit: '5fe82ac', note: 'Pure-Python evaluator over JSON policy file' },
    stage2: { status: 'shipped', commit: '3b56b99', note: 'Rego scaffold + JSON↔Rego sync validator (12 rules)' },
    stage3: { status: 'pending', note: 'OPA binary swap when on PATH; pure-Python fallback' },
    next_action: 'Stage-3: install OPA binary; policy_check.evaluate calls `opa eval`',
  },
  {
    name: 'Paperclip Sandbox',
    category: 'layer-7',
    source_path: 'scripts/paperclip_manager.py',
    stage1: { status: 'shipped', commit: '3fb3679', note: 'Read-only aggregator; brutal-honesty signal' },
    stage2: { status: 'shipped', commit: 'c6f9174', note: 'propose_next_task() suggestion-only advisor (no mutation)' },
    stage3: { status: 'shipped', commit: '880bac6', note: 'paperclip_dispatcher composes propose + openclaw.dispatch' },
    next_action: 'Stage-4: real RPC transport when agents become MCP servers (per OpenClaw Stage-4)',
  },
  {
    name: 'OpenClaw A2A',
    category: 'layer-11',
    source_path: 'scripts/openclaw_coordinator.py',
    stage1: { status: 'shipped', note: 'Gate-only; default-deny; envelope contract' },
    stage2: { status: 'shipped', commit: '6b4d3ee', note: 'dispatch() chains gate + envelope + transport (no-op for now)' },
    stage3: { status: 'pending', note: 'Real RPC transport when agents become MCP servers' },
    next_action: 'Stage-3: expose council agents as MCP servers; transport stops being no-op',
  },
  {
    name: 'Agent Router (Layer 3)',
    category: 'layer-3',
    source_path: 'scripts/agent_router.py',
    stage1: { status: 'shipped', commit: '8059e2e', note: 'Heuristic classifier; conservative-default' },
    stage2: { status: 'shipped', commit: 'c71a480', note: 'Ollama qwen2.5 classifier with heuristic fallback (opt-in)' },
    stage3: { status: 'pending', note: 'Default-flip: Ollama-first after empirical accuracy/latency parity' },
    next_action: 'Stage-3: 100+ classification calls with flag=1; flip default if >75% accuracy',
  },
  {
    name: 'Eval Harness (Ragas/Guardrails/DeepEval/Snyk)',
    category: 'layer-10',
    source_path: 'services/evaluation-svc/app/eval_harness.py',
    stage1: { status: 'shipped', commit: 'ed66b1b', note: '4 engine scaffolds; fail-OPEN for Guardrails' },
    stage2: { status: 'pending', note: 'Install deps; wire real library calls; flip stub flag to false' },
    stage3: { status: 'pending', note: 'Periodic eval jobs (Ragas 1% sample); inline output filter (Guardrails)' },
    next_action: 'Stage-2.1: pip install ragas guardrails-ai deepeval; rerun techstack_audit',
  },

  // ── Rejected (per tool-evaluation; never installed) ───────────────────
  {
    name: 'CrewAI',
    category: 'rejected',
    source_path: '(tool-evaluation: skip)',
    stage1: { status: 'rejected', note: 'verdict=specific-use; borrow patterns, do not adopt as dep' },
    stage2: { status: 'na', note: 'rejected at Stage-1' },
    stage3: { status: 'na', note: 'rejected at Stage-1' },
  },
  {
    name: 'Agno (Phidata)',
    category: 'rejected',
    source_path: '(tool-evaluation: skip)',
    stage1: { status: 'rejected', note: 'verdict=specific-use; borrow persistent-memory pattern only' },
    stage2: { status: 'na', note: 'rejected at Stage-1' },
    stage3: { status: 'na', note: 'rejected at Stage-1' },
  },
  {
    name: 'PraisonAI',
    category: 'rejected',
    source_path: '(tool-evaluation: skip)',
    stage1: { status: 'rejected', note: 'verdict=skip; YAML-config layer over CrewAI redundant with PolisAI' },
    stage2: { status: 'na', note: 'rejected at Stage-1' },
    stage3: { status: 'na', note: 'rejected at Stage-1' },
  },
];

function StageBadge({ stage }: { stage: Stage }) {
  const style = STAGE_STYLE[stage.status];
  return (
    <span
      style={{
        background: style.bg,
        color: style.fg,
        padding: '2px 8px',
        borderRadius: 3,
        fontWeight: 600,
        fontSize: '0.85rem',
        whiteSpace: 'nowrap',
      }}
    >
      {style.icon} {stage.status}
    </span>
  );
}

export default function StagePromotionsPage() {
  const stats = {
    total: COMPONENTS.length,
    fullyPromoted: COMPONENTS.filter(
      (c) =>
        c.stage1.status === 'shipped' &&
        c.stage2.status === 'shipped' &&
        ['shipped', 'na'].includes(c.stage3.status),
    ).length,
    stage1Only: COMPONENTS.filter(
      (c) =>
        c.stage1.status === 'shipped' &&
        c.stage2.status !== 'shipped',
    ).length,
    rejected: COMPONENTS.filter((c) => c.stage1.status === 'rejected').length,
  };

  // Group by category
  const byCategory: Record<string, Component[]> = {};
  for (const c of COMPONENTS) {
    byCategory[c.category] = byCategory[c.category] || [];
    byCategory[c.category].push(c);
  }
  const categoryOrder = ['adapter', 'layer-3', 'layer-4', 'layer-7', 'layer-10', 'layer-11', 'rejected'];

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Stage Promotions Tracker</h1>
        <p style={{ color: '#666', marginTop: 8 }}>
          Per §44 autonomous-loop + §56 techstack-additions: every component
          ships through <strong>Stage-1 (contract) → Stage-2 (wiring) →
          Stage-3 (default-flip / consolidation)</strong>. This page is the
          single tracker for which components are at which stage.
        </p>
      </header>

      {/* Stats headline */}
      <section
        style={{
          padding: 16,
          border: '2px solid #ddd',
          borderRadius: 8,
          marginBottom: 24,
          background: '#fafafa',
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 16,
        }}
      >
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            Total components
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem' }}>{stats.total}</div>
        </div>
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            Fully promoted (Stage 1+2+3)
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#1f8a4c' }}>
            {stats.fullyPromoted}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            Stage-1 only (need wiring)
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#c47a1a' }}>
            {stats.stage1Only}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            Rejected (per tool-eval)
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#a4262c' }}>
            {stats.rejected}
          </div>
        </div>
      </section>

      {/* Per-category sections */}
      {categoryOrder.map((cat) => {
        const items = byCategory[cat];
        if (!items || items.length === 0) return null;
        return (
          <section key={cat} style={{ marginBottom: 24 }}>
            <h2 style={{ marginBottom: 12 }}>
              {cat === 'adapter' && '🔌 Adapters '}
              {cat.startsWith('layer-') && `🔢 ${cat.replace('layer-', 'Layer ')} surface `}
              {cat === 'rejected' && '❌ Rejected (per tool-evaluation) '}
              <span style={{ color: '#666', fontSize: '0.9rem', fontWeight: 'normal' }}>
                ({items.length})
              </span>
            </h2>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '0.85rem',
                background: '#fff',
                border: '1px solid #ddd',
              }}
            >
              <thead>
                <tr style={{ background: '#f0f0f0' }}>
                  <th style={{ textAlign: 'left', padding: 8, width: '20%' }}>Component</th>
                  <th style={{ textAlign: 'left', padding: 8 }}>Stage 1</th>
                  <th style={{ textAlign: 'left', padding: 8 }}>Stage 2</th>
                  <th style={{ textAlign: 'left', padding: 8 }}>Stage 3</th>
                  <th style={{ textAlign: 'left', padding: 8, width: '30%' }}>Next action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.name} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: 8, verticalAlign: 'top' }}>
                      <div style={{ fontWeight: 600 }}>{c.name}</div>
                      <code style={{ fontSize: '0.75rem', color: '#666' }}>{c.source_path}</code>
                    </td>
                    <td style={{ padding: 8, verticalAlign: 'top' }}>
                      <StageBadge stage={c.stage1} />
                      {c.stage1.commit && (
                        <div style={{ fontSize: '0.75rem', color: '#666', marginTop: 4 }}>
                          <code>{c.stage1.commit}</code>
                        </div>
                      )}
                      {c.stage1.note && (
                        <div style={{ fontSize: '0.75rem', color: '#666', marginTop: 2 }}>
                          {c.stage1.note}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 8, verticalAlign: 'top' }}>
                      <StageBadge stage={c.stage2} />
                      {c.stage2.commit && (
                        <div style={{ fontSize: '0.75rem', color: '#666', marginTop: 4 }}>
                          <code>{c.stage2.commit}</code>
                        </div>
                      )}
                      {c.stage2.note && (
                        <div style={{ fontSize: '0.75rem', color: '#666', marginTop: 2 }}>
                          {c.stage2.note}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 8, verticalAlign: 'top' }}>
                      <StageBadge stage={c.stage3} />
                      {c.stage3.commit && (
                        <div style={{ fontSize: '0.75rem', color: '#666', marginTop: 4 }}>
                          <code>{c.stage3.commit}</code>
                        </div>
                      )}
                      {c.stage3.note && (
                        <div style={{ fontSize: '0.75rem', color: '#666', marginTop: 2 }}>
                          {c.stage3.note}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: 8, verticalAlign: 'top', fontSize: '0.8rem', color: '#444' }}>
                      {c.next_action || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}

      {/* §49 footer */}
      <section
        style={{
          padding: 16,
          border: '1px dashed #999',
          borderRadius: 4,
          background: '#f8f8f8',
          fontSize: '0.85rem',
        }}
      >
        <strong>Composes with</strong> (per §49):
        <ul style={{ marginTop: 8 }}>
          <li>
            <Link href="/admin/adapters">Adapter inventory</Link> — live status
            of LiteLLM/PydanticAI/Kafka adapters.
          </li>
          <li>
            <Link href="/admin/tool-evaluation">Tool evaluation</Link> — what
            put CrewAI/Agno/PraisonAI in the rejected category.
          </li>
          <li>
            <Link href="/admin/techstack-audit">Techstack audit</Link> —
            empirical install state for every adopted dep.
          </li>
          <li>
            <Link href="/admin/enterprise-architecture">Enterprise architecture</Link>{' '}
            — the 11-layer stack each component slots into.
          </li>
          <li>
            <Link href="/admin/pr-management">PR management</Link> — every
            stage promotion lands as its own commit in the queue.
          </li>
        </ul>
        <div style={{ marginTop: 8, color: '#666' }}>
          Stage promotion rules: Stage-1 → Stage-2 → Stage-3 in order; no
          skipping. Stage-3 (default-flip) requires <strong>empirical
          eval</strong> showing parity with original path. No flipping
          defaults on speculation. Stage-4 introduces compliance gates
          (e.g., "fail build if STRICT mode lacks rules for in-use tools").
        </div>
      </section>
    </div>
  );
}
