/**
 * BFF for the Agent Router (Layer 3) — Stage-1 read-only.
 *
 * GET /api/v1/agent-router
 *   → { patterns, recent_classifications, stats }
 *
 * Per §47 Layer 3. Calls scripts/agent_router.py patterns + reads
 * .loop/agent_router_audit.jsonl.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import { readFile } from 'fs/promises';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const ROUTER_SCRIPT = path.join(REPO_ROOT, 'scripts', 'agent_router.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');
const AUDIT_LOG = path.join(REPO_ROOT, '.loop', 'agent_router_audit.jsonl');

type Pattern = {
  regex: string;
  intent: string;
  actor: string;
  tool: string;
};

type PatternsPayload = {
  stage: number;
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  patterns: { high: Pattern[]; medium: Pattern[]; low: Pattern[] };
};

type Classification = {
  intent: string;
  risk: 'low' | 'medium' | 'high' | 'unknown';
  recommended_actor: string;
  recommended_tool: string;
  confidence: number;
  reasons: string[];
  timestamp: number;
  message_hash: string;
};

function correlationId(): string {
  return `router-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runPatterns(): Promise<PatternsPayload> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON, [ROUTER_SCRIPT, 'patterns'], {
      cwd: REPO_ROOT,
      timeout: 8000,
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    proc.on('error', (err) => reject(err));
    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`agent_router patterns exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`agent_router output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

async function readRecent(limit = 50): Promise<Classification[]> {
  try {
    const contents = await readFile(AUDIT_LOG, 'utf-8');
    const lines = contents.trim().split('\n').filter((l) => l.length > 0);
    const tail = lines.slice(-limit);
    const rows: Classification[] = [];
    for (const line of tail) {
      try {
        rows.push(JSON.parse(line) as Classification);
      } catch {
        // Skip malformed
      }
    }
    return rows.reverse();
  } catch (e: unknown) {
    if (e instanceof Error && 'code' in e && (e as NodeJS.ErrnoException).code === 'ENOENT') {
      return [];
    }
    throw e;
  }
}

export async function GET(request: Request): Promise<NextResponse> {
  const cid = correlationId();
  const url = new URL(request.url);
  const limit = Number(url.searchParams.get('limit') || '50');

  try {
    const [patterns, recent] = await Promise.all([
      runPatterns(),
      readRecent(Number.isFinite(limit) ? limit : 50),
    ]);

    // Aggregate stats
    const byRisk: Record<string, number> = { low: 0, medium: 0, high: 0, unknown: 0 };
    const byIntent: Record<string, number> = {};
    for (const r of recent) {
      byRisk[r.risk] = (byRisk[r.risk] || 0) + 1;
      byIntent[r.intent] = (byIntent[r.intent] || 0) + 1;
    }

    return NextResponse.json(
      {
        data: {
          ...patterns,
          recent_classifications: recent,
          stats: {
            total: recent.length,
            by_risk: byRisk,
            by_intent: byIntent,
          },
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
        detail: `Agent Router BFF failed: ${msg}`,
        error_code: 'ROUTER_BFF_ERROR',
        correlation_id: cid,
      },
      { status: 502 },
    );
  }
}

async function rejectMutating(): Promise<NextResponse> {
  return NextResponse.json(
    {
      detail:
        'Agent Router BFF is read-only. Stage-1 cannot accept new patterns via HTTP; edit scripts/agent_router.py + redeploy.',
      error_code: 'ROUTER_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
