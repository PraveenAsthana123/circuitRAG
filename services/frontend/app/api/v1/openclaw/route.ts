/**
 * BFF for OpenClaw (Layer 11) — Stage-1 read-only.
 *
 * GET /api/v1/openclaw
 *   → { agents, recent_dispatches, stats }
 *
 * Per §47 Layer 11. Calls openclaw_coordinator.py agents + reads
 * .loop/openclaw_audit.jsonl. Stage-1 ships gate + envelope contract
 * only — Dispatch RPC is comment-only in the proto file.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import { readFile } from 'fs/promises';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const OC_SCRIPT = path.join(REPO_ROOT, 'scripts', 'openclaw_coordinator.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');
const AUDIT_LOG = path.join(REPO_ROOT, '.loop', 'openclaw_audit.jsonl');

type AgentInfo = {
  capabilities: string[];
  required_scope: string;
  endpoint: string;
};

type AgentsPayload = {
  stage: number;
  agent_count: number;
  agents: Record<string, AgentInfo>;
};

type DispatchAuditRow = {
  type: string;
  decision: {
    allow: boolean;
    rule_matched: string;
    reason: string;
    requesting_agent: string;
    target_agent: string;
    capability: string;
    timestamp: number;
    dispatch_id: string;
    missing_scopes: string[];
  };
  envelope: unknown;
};

function correlationId(): string {
  return `openclaw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runAgents(): Promise<AgentsPayload> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON, [OC_SCRIPT, 'agents'], {
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
        reject(new Error(`openclaw agents exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`openclaw output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

async function readDispatches(limit = 50): Promise<DispatchAuditRow[]> {
  try {
    const contents = await readFile(AUDIT_LOG, 'utf-8');
    const lines = contents.trim().split('\n').filter((l) => l.length > 0);
    const tail = lines.slice(-limit);
    const rows: DispatchAuditRow[] = [];
    for (const line of tail) {
      try {
        rows.push(JSON.parse(line) as DispatchAuditRow);
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
    const [agents, dispatches] = await Promise.all([
      runAgents(),
      readDispatches(Number.isFinite(limit) ? limit : 50),
    ]);

    const allowCount = dispatches.filter((d) => d.decision.allow).length;
    const denyCount = dispatches.filter((d) => !d.decision.allow).length;
    const byTarget: Record<string, number> = {};
    for (const d of dispatches) {
      byTarget[d.decision.target_agent] = (byTarget[d.decision.target_agent] || 0) + 1;
    }

    return NextResponse.json(
      {
        data: {
          ...agents,
          recent_dispatches: dispatches,
          stats: {
            total: dispatches.length,
            allow: allowCount,
            deny: denyCount,
            allow_rate: dispatches.length > 0 ? allowCount / dispatches.length : 0,
            by_target: byTarget,
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
        detail: `OpenClaw BFF failed: ${msg}`,
        error_code: 'OPENCLAW_BFF_ERROR',
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
        'OpenClaw BFF is read-only. Stage-1 cannot dispatch; Dispatch RPC is Stage-2 with PolisAI rules + drill update.',
      error_code: 'OPENCLAW_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
