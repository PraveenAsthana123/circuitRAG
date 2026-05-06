import { NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const OLLAMA_BASE = process.env.OLLAMA_BASE_URL || 'http://localhost:11434';

type AuditRow = {
  ts?: string;
  id?: string;
  lane?: string;
  outcome?: string;
  model?: string;
  tokens?: number;
  latency_s?: number;
  chain?: Record<string, { model: string; tokens: number; latency_s: number }>;
};

async function fetchOllama(p: string) {
  try {
    const r = await fetch(`${OLLAMA_BASE}${p}`, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) return { error: `ollama ${p} -> ${r.status}` };
    return await r.json();
  } catch (e: unknown) {
    return { error: `ollama unreachable: ${(e as Error).message}` };
  }
}

async function readJsonlTail(filePath: string, n: number): Promise<AuditRow[]> {
  if (!existsSync(filePath)) return [];
  const text = await readFile(filePath, 'utf-8');
  const lines = text.trim().split('\n').filter((l) => l.trim());
  const tail = lines.slice(-n);
  return tail.map((l) => {
    try {
      return JSON.parse(l) as AuditRow;
    } catch {
      return {} as AuditRow;
    }
  });
}

type ProviderRow = {
  provider: string;
  attempted: number;
  applied: number;
  apply_rate: number;
  avg_latency_s: number;
  latency_samples?: number;
  note?: string;
};

type ProviderComparison = {
  version: string;
  generated_at: number;
  window_days: number;
  providers: ProviderRow[];
  totals: { attempted: number; applied: number; apply_rate: number };
  honest_gaps: string[];
  bottleneck_signal: {
    signal_active: boolean;
    reason: string;
    suggested_action?: string;
    policy_ref?: string;
  };
};

// Lane→provider classification mirrors scripts/agent_task_registry.py.
// Drill-locked: drill_agent_task_registry.py step 3 + 4 enforce parity
// in the Python source. The TS mirror exists so the BFF doesn't need
// a Python subprocess on the request path; the registry script is the
// canonical source of truth and gets re-run by paperclip on cron.
function classifyLane(lane: string): string {
  if (!lane || lane === 'unknown') return 'ollama-other';
  if (lane === 'council' || lane === 'council_local') return 'ollama-council';
  if (
    lane === 'ruff:autofix' ||
    lane === 'eslint:autofix' ||
    lane === 'deterministic'
  )
    return 'ollama-deterministic';
  if (
    lane.includes(':') &&
    /(coder|gemma|llama|qwen|mistral)/.test(lane)
  )
    return 'ollama-single';
  return 'ollama-other';
}

async function readProviderComparison(repoRoot: string): Promise<ProviderComparison> {
  const issuePath = path.join(repoRoot, '.loop', 'issue_audit.jsonl');
  const applyPath = path.join(repoRoot, '.loop', 'agent_task_board_apply.jsonl');

  const empty: ProviderComparison = {
    version: 'registry-v1',
    generated_at: Date.now() / 1000,
    window_days: 7,
    providers: [],
    totals: { attempted: 0, applied: 0, apply_rate: 0.0 },
    honest_gaps: [],
    bottleneck_signal: { signal_active: false, reason: 'no data' },
  };

  type Bucket = {
    attempted: number;
    applied: number;
    latency_sum: number;
    latency_n: number;
  };
  const byProvider = new Map<string, Bucket>();
  const bump = (k: string): Bucket => {
    let b = byProvider.get(k);
    if (!b) {
      b = { attempted: 0, applied: 0, latency_sum: 0, latency_n: 0 };
      byProvider.set(k, b);
    }
    return b;
  };

  // Read all issue_audit rows (not just tail — apply-rate needs full window).
  const gaps: string[] = [];
  if (!existsSync(issuePath)) {
    gaps.push(`missing: issue_audit.jsonl`);
  } else {
    const text = await readFile(issuePath, 'utf-8');
    for (const line of text.split('\n')) {
      const t = line.trim();
      if (!t) continue;
      let row: AuditRow;
      try {
        row = JSON.parse(t) as AuditRow;
      } catch {
        continue;
      }
      const provider = classifyLane(String(row.lane || ''));
      const b = bump(provider);
      b.attempted += 1;
      if (typeof row.latency_s === 'number') {
        b.latency_sum += row.latency_s;
        b.latency_n += 1;
      }
    }
  }

  if (!existsSync(applyPath)) {
    gaps.push(`missing: agent_task_board_apply.jsonl`);
  } else {
    const text = await readFile(applyPath, 'utf-8');
    for (const line of text.split('\n')) {
      const t = line.trim();
      if (!t) continue;
      let row: { lane?: string; outcome?: string };
      try {
        row = JSON.parse(t);
      } catch {
        continue;
      }
      if (row.outcome !== 'applied') continue;
      const provider = classifyLane(String(row.lane || ''));
      const b = bump(provider);
      b.applied += 1;
    }
  }

  const providers: ProviderRow[] = [];
  for (const provider of [...byProvider.keys()].sort()) {
    const b = byProvider.get(provider)!;
    const apply_rate = b.attempted > 0 ? b.applied / b.attempted : 0.0;
    const avg_latency_s = b.latency_n > 0 ? b.latency_sum / b.latency_n : 0.0;
    providers.push({
      provider,
      attempted: b.attempted,
      applied: b.applied,
      apply_rate: Math.round(apply_rate * 10000) / 10000,
      avg_latency_s: Math.round(avg_latency_s * 100) / 100,
      latency_samples: b.latency_n,
    });
  }

  // claude-runtime row — TS BFF doesn't read postgres directly; it
  // surfaces the row with attempted=0 and an honest_gap so the widget
  // always shows the column. Operator can run scripts/agent_task_registry.py
  // CLI for the postgres-backed view.
  providers.push({
    provider: 'claude-runtime',
    attempted: 0,
    applied: 0,
    apply_rate: 0.0,
    avg_latency_s: 0.0,
    latency_samples: 0,
    note: 'postgres lookup deferred to CLI / paperclip — BFF stays JSONL-only for performance',
  });

  const totalAttempted = providers.reduce((s, p) => s + p.attempted, 0);
  const totalApplied = providers.reduce((s, p) => s + p.applied, 0);
  const overallRate = totalAttempted > 0 ? totalApplied / totalAttempted : 0.0;

  // Bottleneck signal (mirrors registry's _detect_bottleneck)
  const council = providers.find((p) => p.provider === 'ollama-council');
  let bottleneck: ProviderComparison['bottleneck_signal'];
  if (!council) {
    bottleneck = { signal_active: false, reason: 'no council samples' };
  } else if (council.attempted < 10) {
    bottleneck = {
      signal_active: false,
      reason: `council sample too small (attempted=${council.attempted}, threshold=10)`,
    };
  } else if (council.apply_rate < 0.1) {
    bottleneck = {
      signal_active: true,
      reason: `council apply_rate=${(council.apply_rate * 100).toFixed(2)}% over ${council.attempted} attempts`,
      suggested_action:
        'Implement §55 Tier 1.1 (Pydantic CouncilProposal schema) — schema-validation rejects malformed proposals before git apply --check',
      policy_ref: 'CLAUDE.md §55.2 Tier 1',
    };
  } else {
    bottleneck = {
      signal_active: false,
      reason: `council apply_rate=${(council.apply_rate * 100).toFixed(2)}% above 10% threshold`,
    };
  }

  return {
    ...empty,
    providers,
    totals: {
      attempted: totalAttempted,
      applied: totalApplied,
      apply_rate: Math.round(overallRate * 10000) / 10000,
    },
    honest_gaps: gaps,
    bottleneck_signal: bottleneck,
  };
}

async function readChecklistSummary(filePath: string) {
  if (!existsSync(filePath)) return { total: 0, by_difficulty: {}, by_assignee: {} };
  const text = await readFile(filePath, 'utf-8');
  const lines = text.trim().split('\n').filter((l) => l.trim());
  const issues = lines
    .map((l) => {
      try {
        return JSON.parse(l);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
  const byDifficulty: Record<string, number> = {};
  const byAssignee: Record<string, number> = {};
  for (const i of issues) {
    byDifficulty[i.difficulty] = (byDifficulty[i.difficulty] || 0) + 1;
    byAssignee[i.assigned_to] = (byAssignee[i.assigned_to] || 0) + 1;
  }
  return { total: issues.length, by_difficulty: byDifficulty, by_assignee: byAssignee };
}

export async function GET() {
  const correlation_id = crypto.randomUUID();
  const [tags, ps, audit, checklist, providerComparison] = await Promise.all([
    fetchOllama('/api/tags'),
    fetchOllama('/api/ps'),
    readJsonlTail(path.join(REPO_ROOT, '.loop', 'issue_audit.jsonl'), 30),
    readChecklistSummary(path.join(REPO_ROOT, '.loop', 'issue_checklist.jsonl')),
    readProviderComparison(REPO_ROOT),
  ]);

  let batchSummary: unknown = null;
  const batchPath = path.join(REPO_ROOT, '.loop', 'council_batch_summary.json');
  if (existsSync(batchPath)) {
    try {
      batchSummary = JSON.parse(await readFile(batchPath, 'utf-8'));
    } catch {
      batchSummary = { error: 'malformed council_batch_summary.json' };
    }
  }

  const installed: { name: string; size_bytes: number; modified: string }[] = (
    (tags as { models?: { name: string; size: number; modified_at: string }[] })?.models || []
  ).map((m) => ({
    name: m.name,
    size_bytes: m.size,
    modified: m.modified_at,
  }));

  const loaded: { name: string; size_vram?: number; expires?: string }[] = (
    (ps as { models?: { name: string; size_vram?: number; expires_at?: string }[] })?.models || []
  ).map((m) => ({
    name: m.name,
    size_vram: m.size_vram,
    expires: m.expires_at,
  }));

  return NextResponse.json(
    {
      data: {
        installed,
        loaded,
        installed_count: installed.length,
        loaded_count: loaded.length,
        recent_audit: audit,
        checklist_summary: checklist,
        council_batch_summary: batchSummary,
        provider_comparison: providerComparison,
        ollama_base: OLLAMA_BASE,
      },
      correlation_id,
    },
    { status: 200 },
  );
}
