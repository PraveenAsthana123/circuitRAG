/**
 * BFF route — top-level executive dashboard summary.
 *
 * Consolidates the 24 Paperclip surface keys into a single operator-
 * readable JSON shape that powers the executive dashboard. NEVER
 * shells out to Paperclip directly (re-uses /api/v1/paperclip via
 * intra-process fetch) so the §42 read-only contract holds at one
 * surface, not two.
 *
 * Per CLAUDE.md §38 (governance), §42 (operational autonomy), §47
 * (architecture L6 observability), §52 row 4 (operator API gap),
 * §53.39 (observability taxonomy), §55.3 (outcome-based contract).
 *
 * Output shape (drill-locked at drill_dashboard_summary_api.py):
 *
 *   {
 *     "version": "summary-v1",
 *     "generated_at": <epoch_seconds>,
 *     "system_health": {
 *       "overall": "healthy" | "degraded" | "alarm",
 *       "outbox_status": "healthy" | "degraded" | "alarm",
 *       "drill_pass_rate": 0.0..1.0,
 *       "stale_outbox_5m": int,
 *     },
 *     "council_signal": {
 *       "apply_rate": 0.0..1.0,
 *       "bottleneck_active": bool,
 *       "bottleneck_reason": string,
 *       "suggested_action": string | null,
 *     },
 *     "approval_engine": {
 *       "policy_version": string,
 *       "auto_count": int,
 *       "ask_count": int,
 *       "batched_count": int,
 *       "blocked_count": int,
 *       "cache_hits": int,
 *       "queue_depth": int,
 *       "spam_reduction_pct": 0..100,
 *     },
 *     "providers": [{provider, attempted, applied, apply_rate, ...}],
 *     "ops_queue": {
 *       "tasks_total": int,
 *       "tasks_completed": int,
 *       "tasks_pending": int,
 *       "hitl_pending": int,
 *     },
 *     "honest_gaps": string[],
 *     "links": {
 *       "paperclip": "/api/v1/paperclip",
 *       "local_models": "/admin/local-models",
 *       "approvals": "/admin/approvals",
 *     }
 *   }
 *
 * Stage-1 read-only — GET only. Other methods 405 with §42 citation.
 */
import { NextResponse } from 'next/server';

const PAPERCLIP_URL = '/api/v1/paperclip';

type PaperclipSnapshot = {
  stage: number;
  version: string;
  generated_at: number;
  council_batch?: {
    total_attempted?: number;
    unique_ids_run?: number;
  };
  apply_attempts?: {
    apply_rate?: number;
    total_attempts?: number;
    applied?: number;
  };
  outbox_health?: {
    status?: string;
    stale_unpublished_5m?: number;
  };
  drill_history?: {
    pass_rate?: number;
    failed?: number;
    total?: number;
  };
  ops_worker?: {
    by_status?: Record<string, number>;
  };
  pending_issues?: {
    total_pending?: number;
    by_assignee?: Record<string, number>;
  };
  provider_comparison?: {
    providers?: Array<{
      provider: string;
      attempted: number;
      applied: number;
      apply_rate: number;
      avg_latency_s: number;
      tokens_total?: number;
      cost_usd?: number;
      cost_per_apply_usd?: number;
    }>;
    totals?: {
      attempted: number;
      applied: number;
      apply_rate: number;
      tokens_total?: number;
      cost_usd?: number;
    };
    bottleneck_signal?: {
      signal_active: boolean;
      reason: string;
      suggested_action?: string;
    };
    honest_gaps?: string[];
  };
  migrate_phase_status?: {
    flags?: Record<string, {
      env_var: string;
      enabled: boolean;
      since_iter: number;
      legacy_path: string;
      sql_table: string;
    }>;
    surfaces?: Record<string, {
      legacy_size_bytes: number;
      sql_count: number;
      parity: string;
    }>;
    honest_gaps?: string[];
    summary?: {
      active_count: number;
      total: number;
      sql_total_rows: number;
    };
  };
  approval_engine?: {
    policy_version?: string;
    patterns?: { auto_approve?: number; ask_once?: number; always_ask?: number; block?: number };
    cache?: { active_count?: number; total_hits?: number };
    batch?: { queue_depth?: number; is_due?: boolean };
    audit?: { total?: number; by_terminal?: Record<string, number> };
  };
};

function correlationId(): string {
  return `summary-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function originFromRequest(req: Request): string {
  // Prefer the request's own origin so the inner fetch hits the same
  // BFF. Falls back to env var / localhost for non-HTTP test contexts.
  try {
    const u = new URL(req.url);
    return `${u.protocol}//${u.host}`;
  } catch {
    return process.env.FRONTEND_ORIGIN || 'http://localhost:3000';
  }
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function deriveOverallHealth(snap: PaperclipSnapshot): 'healthy' | 'degraded' | 'alarm' {
  // Simple rollup: alarm if outbox_health=alarm OR drill_pass_rate<0.8;
  // degraded if outbox=degraded OR drill_pass_rate<0.95; else healthy.
  const outbox = (snap.outbox_health?.status || '').toLowerCase();
  const passRate = Number(snap.drill_history?.pass_rate ?? 1.0);
  if (outbox === 'alarm') return 'alarm';
  if (passRate < 0.8) return 'alarm';
  if (outbox === 'degraded' || passRate < 0.95) return 'degraded';
  return 'healthy';
}

function buildSummary(snap: PaperclipSnapshot): {
  summary: Record<string, unknown>;
  honest_gaps: string[];
} {
  const gaps: string[] = [];

  // System health
  const overall = deriveOverallHealth(snap);
  const system_health = {
    overall,
    outbox_status: (snap.outbox_health?.status || 'unknown').toLowerCase(),
    drill_pass_rate: Number(snap.drill_history?.pass_rate ?? 1.0),
    drill_failed: Number(snap.drill_history?.failed ?? 0),
    stale_outbox_5m: Number(snap.outbox_health?.stale_unpublished_5m ?? 0),
  };

  // Council bottleneck signal (from v8 provider_comparison)
  const pc = snap.provider_comparison;
  const council_signal = {
    apply_rate: Number(
      pc?.providers?.find((p) => p.provider === 'ollama-council')?.apply_rate ??
        snap.apply_attempts?.apply_rate ??
        0,
    ),
    bottleneck_active: Boolean(pc?.bottleneck_signal?.signal_active ?? false),
    bottleneck_reason: String(pc?.bottleneck_signal?.reason || 'no signal'),
    suggested_action: pc?.bottleneck_signal?.suggested_action ?? null,
  };

  if (!pc) {
    gaps.push('provider_comparison missing — Paperclip likely older than v8');
  }

  // Approval engine telemetry (from v9 approval_engine)
  const ae = snap.approval_engine;
  const auditTotals = ae?.audit?.by_terminal || {};
  const auto_count = Number(auditTotals['AUTO_APPROVE'] || 0);
  const ask_count = Number(auditTotals['ASK'] || 0);
  const batched_count = Number(auditTotals['BATCHED'] || 0);
  const blocked_count = Number(auditTotals['BLOCK'] || 0);
  const total = auto_count + ask_count + batched_count + blocked_count;
  // Spam reduction: how much fewer prompts vs naive "ask everything"
  // policy. auto + cache-promoted-batches both count as "no prompt".
  const non_prompted = auto_count + blocked_count;
  const spam_reduction_pct = total > 0 ? clamp(Math.round((non_prompted / total) * 100), 0, 100) : 0;

  const approval_engine = {
    policy_version: ae?.policy_version || 'unknown',
    auto_count,
    ask_count,
    batched_count,
    blocked_count,
    cache_hits: Number(ae?.cache?.total_hits ?? 0),
    cache_active: Number(ae?.cache?.active_count ?? 0),
    queue_depth: Number(ae?.batch?.queue_depth ?? 0),
    queue_is_due: Boolean(ae?.batch?.is_due ?? false),
    audit_total: total,
    spam_reduction_pct,
  };

  if (!ae) {
    gaps.push('approval_engine missing — Paperclip likely older than v9');
  }

  // Provider rollup pass-through (includes cost columns from registry-v2)
  const providers = pc?.providers || [];

  // v10 — cost rollup. Sum tokens + cost across all providers for the
  // executive summary card. Per §55.3 outcome-based contract, this is
  // the FinOps signal: how much $ does the bottleneck-fixing iteration
  // actually cost the operator?
  const cost_summary = {
    tokens_total: Number(pc?.totals?.tokens_total ?? 0),
    cost_usd: Number(pc?.totals?.cost_usd ?? 0.0),
    paid_providers: providers.filter((p) => Number(p.cost_usd ?? 0) > 0).length,
    free_providers: providers.filter((p) => Number(p.cost_usd ?? 0) === 0).length,
  };

  // Ops queue
  const opsByStatus = snap.ops_worker?.by_status || {};
  const tasks_total = Object.values(opsByStatus).reduce((s, n) => s + Number(n), 0);
  const tasks_completed = Number(opsByStatus['COMPLETED'] || 0);
  const tasks_pending = Math.max(0, tasks_total - tasks_completed);
  const hitl_pending = Number(snap.pending_issues?.by_assignee?.['human-review'] || 0);

  const ops_queue = {
    tasks_total,
    tasks_completed,
    tasks_pending,
    hitl_pending,
    pending_issues_total: Number(snap.pending_issues?.total_pending ?? 0),
  };

  // v3 — migrate-phase status pass-through (iter 14 surface)
  const migrate_phase = snap.migrate_phase_status || {};

  return {
    summary: {
      version: 'summary-v3',
      paperclip_version: snap.version,
      generated_at: Math.floor(Date.now() / 1000),
      system_health,
      council_signal,
      approval_engine,
      providers,
      migrate_phase: migrate_phase,
      cost_summary,
      ops_queue,
      links: {
        paperclip: '/api/v1/paperclip',
        local_models: '/admin/local-models',
        approvals: '/admin/approvals',
        dashboard: '/admin/dashboard',
      },
    },
    honest_gaps: [
      ...gaps,
      ...(pc?.honest_gaps || []),
    ],
  };
}

export async function GET(request: Request): Promise<NextResponse> {
  const cid = correlationId();
  const origin = originFromRequest(request);
  try {
    const r = await fetch(`${origin}${PAPERCLIP_URL}`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(20000),
    });
    if (!r.ok) {
      throw new Error(`paperclip BFF returned ${r.status}`);
    }
    const j = (await r.json()) as { data: PaperclipSnapshot };
    if (!j?.data) {
      throw new Error('paperclip BFF returned no data field');
    }
    const { summary, honest_gaps } = buildSummary(j.data);
    return NextResponse.json(
      {
        data: { ...summary, honest_gaps },
        correlation_id: cid,
      },
      {
        headers: {
          'X-Correlation-ID': cid,
          'Cache-Control': 'no-store',
        },
      },
    );
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      {
        detail: `Dashboard summary failed: ${msg}`,
        error_code: 'DASHBOARD_SUMMARY_ERROR',
        correlation_id: cid,
      },
      { status: 502 },
    );
  }
}

// Stage-1 contract: read-only. Other methods 405 per §42.
async function methodNotAllowed(): Promise<NextResponse> {
  return NextResponse.json(
    {
      detail:
        'Dashboard summary is read-only. Mutations belong on the resource-specific endpoints behind §42 gating.',
      error_code: 'METHOD_NOT_ALLOWED',
    },
    { status: 405 },
  );
}

export const POST = methodNotAllowed;
export const PUT = methodNotAllowed;
export const DELETE = methodNotAllowed;
export const PATCH = methodNotAllowed;
