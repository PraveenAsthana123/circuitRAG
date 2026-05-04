/**
 * BFF for /admin/health-pulse — synthesizes audit logs from all layers
 * into one live operational dashboard.
 *
 * Per §47 + §38. Promise.all-reads 6 audit log files in parallel
 * (no subprocess needed — pure file I/O is faster + dependency-free).
 */
import { NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const LOOP_DIR = path.join(REPO_ROOT, '.loop');

type LayerStats = {
  layer: string;
  audit_log: string;
  total: number;
  last_minute: number;
  last_hour: number;
  last_day: number;
  allow_rate: number | null;  // null when no allow/deny field exists
  recent_5: { ts: number; summary: string }[];
};

function correlationId(): string {
  return `pulse-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function parseTimestamp(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    // ISO or epoch-string
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) return parsed / 1000;
    const num = Number(value);
    if (Number.isFinite(num)) return num;
  }
  return 0;
}

async function readAuditLog(
  layer: string,
  filename: string,
  extractTimestamp: (row: Record<string, unknown>) => number,
  extractAllow: (row: Record<string, unknown>) => boolean | null,
  extractSummary: (row: Record<string, unknown>) => string,
): Promise<LayerStats> {
  const filePath = path.join(LOOP_DIR, filename);
  const stats: LayerStats = {
    layer,
    audit_log: filename,
    total: 0,
    last_minute: 0,
    last_hour: 0,
    last_day: 0,
    allow_rate: null,
    recent_5: [],
  };

  try {
    const contents = await readFile(filePath, 'utf-8');
    const lines = contents.trim().split('\n').filter((l) => l.length > 0);
    const now = Date.now() / 1000;
    let allowCount = 0;
    let denyCount = 0;
    const all_rows: { ts: number; summary: string }[] = [];

    for (const line of lines) {
      try {
        const row = JSON.parse(line) as Record<string, unknown>;
        stats.total += 1;
        const ts = extractTimestamp(row);
        const allow = extractAllow(row);
        const summary = extractSummary(row);
        all_rows.push({ ts, summary });
        if (ts > now - 60) stats.last_minute += 1;
        if (ts > now - 3600) stats.last_hour += 1;
        if (ts > now - 86400) stats.last_day += 1;
        if (allow === true) allowCount += 1;
        else if (allow === false) denyCount += 1;
      } catch {
        // skip malformed line
      }
    }

    if (allowCount + denyCount > 0) {
      stats.allow_rate = allowCount / (allowCount + denyCount);
    }

    // Last 5 rows by timestamp
    all_rows.sort((a, b) => b.ts - a.ts);
    stats.recent_5 = all_rows.slice(0, 5);
  } catch (e: unknown) {
    if (e instanceof Error && 'code' in e && (e as NodeJS.ErrnoException).code === 'ENOENT') {
      // File doesn't exist; stats stays at zeros
    } else {
      throw e;
    }
  }

  return stats;
}

export async function GET(_request: Request): Promise<NextResponse> {
  const cid = correlationId();

  try {
    const [policy, openclaw, router, gateway, council, apply] = await Promise.all([
      readAuditLog(
        'PolisAI Policy (Layer 4)',
        'policy_audit.jsonl',
        (r) => parseTimestamp(r.timestamp),
        (r) => (r.allow as boolean | undefined) ?? null,
        (r) => `${r.actor || '?'} → ${r.tool || '?'}`,
      ),
      readAuditLog(
        'OpenClaw A2A (Layer 11)',
        'openclaw_audit.jsonl',
        (r) => {
          const dec = (r.decision as Record<string, unknown> | undefined) || {};
          return parseTimestamp(dec.timestamp);
        },
        (r) => {
          const dec = (r.decision as Record<string, unknown> | undefined) || {};
          return (dec.allow as boolean | undefined) ?? null;
        },
        (r) => {
          const dec = (r.decision as Record<string, unknown> | undefined) || {};
          return `${dec.requesting_agent || '?'} → ${dec.target_agent || '?'} : ${dec.capability || '?'}`;
        },
      ),
      readAuditLog(
        'Agent Router (Layer 3)',
        'agent_router_audit.jsonl',
        (r) => parseTimestamp(r.timestamp),
        () => null,  // router doesn't have allow/deny — has risk levels
        (r) => `${r.intent || '?'} (risk=${r.risk || '?'})`,
      ),
      readAuditLog(
        'MCP Gateway (Layer 8)',
        'mcp_gateway_audit.jsonl',
        (r) => parseTimestamp(r.timestamp),
        (r) => (r.allow as boolean | undefined) ?? null,
        (r) => `${r.actor || '?'} → ${r.server || '?'}.${r.tool || '?'}`,
      ),
      readAuditLog(
        'Council outcomes (Layer 5)',
        'issue_audit.jsonl',
        (r) => parseTimestamp(r.ts || r.timestamp),
        (r) => {
          const outcome = (r.outcome as string | undefined) || '';
          if (outcome.includes('rejected') || outcome.includes('failed')) return false;
          if (outcome.includes('council_complete') || outcome.includes('validated')) return true;
          return null;
        },
        (r) => `${r.id || '?'} (${r.outcome || '?'})`,
      ),
      readAuditLog(
        'Apply attempts (daemon)',
        'agent_task_board_apply.jsonl',
        (r) => parseTimestamp(r.timestamp),
        (r) => {
          const outcome = (r.outcome as string | undefined) || '';
          return outcome === 'applied' ? true : (outcome === 'rejected' ? false : null);
        },
        (r) => `${r.id || '?'} → ${r.outcome || '?'}`,
      ),
    ]);

    const layers = [policy, openclaw, router, gateway, council, apply];
    const totals = {
      total: layers.reduce((acc, l) => acc + l.total, 0),
      last_minute: layers.reduce((acc, l) => acc + l.last_minute, 0),
      last_hour: layers.reduce((acc, l) => acc + l.last_hour, 0),
      last_day: layers.reduce((acc, l) => acc + l.last_day, 0),
    };

    return NextResponse.json(
      {
        data: {
          layers,
          totals,
          observed_at: Date.now() / 1000,
        },
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
        detail: `Health pulse BFF failed: ${msg}`,
        error_code: 'HEALTH_PULSE_BFF_ERROR',
        correlation_id: cid,
      },
      { status: 502 },
    );
  }
}

async function rejectMutating(): Promise<NextResponse> {
  return NextResponse.json(
    {
      detail: 'Health pulse BFF is read-only (read-only audit logs).',
      error_code: 'HEALTH_PULSE_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
