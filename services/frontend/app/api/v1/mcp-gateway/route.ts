/**
 * BFF for MCP Gateway — Stage-1 read-only.
 *
 * GET /api/v1/mcp-gateway
 *   → { enabled, allowlist, recent_decisions, stats }
 *
 * Per §47 Layer 8 + §56. Calls mcp_gateway.py status + reads
 * config/mcp/allowlist.json + .loop/mcp_gateway_audit.jsonl.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import { readFile } from 'fs/promises';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const GATEWAY = path.join(REPO_ROOT, 'scripts', 'mcp_gateway.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');
const ALLOWLIST = path.join(REPO_ROOT, 'config', 'mcp', 'allowlist.json');
const AUDIT_LOG = path.join(REPO_ROOT, '.loop', 'mcp_gateway_audit.jsonl');

type AllowlistServer = {
  name: string;
  module: string;
  risk: 'low' | 'medium' | 'high' | 'critical';
  approved_actors: string[];
  max_calls_per_minute: number;
  rationale: string;
};

type GatewayDecision = {
  allow: boolean;
  reason: string;
  actor: string;
  server: string;
  tool: string;
  risk: string;
  rule_matched: string;
  timestamp: number;
  request_id: string;
};

function correlationId(): string {
  return `mcpg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runStatus(): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON, [GATEWAY, 'status'], {
      cwd: REPO_ROOT,
      timeout: 5000,
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
        reject(new Error(`mcp_gateway status exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`status output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

async function readAllowlist(): Promise<{ servers: AllowlistServer[]; default_decision: string; policy_version: string }> {
  const contents = await readFile(ALLOWLIST, 'utf-8');
  return JSON.parse(contents);
}

async function readDecisions(limit = 50): Promise<GatewayDecision[]> {
  try {
    const contents = await readFile(AUDIT_LOG, 'utf-8');
    const lines = contents.trim().split('\n').filter((l) => l.length > 0);
    const tail = lines.slice(-limit);
    const rows: GatewayDecision[] = [];
    for (const line of tail) {
      try {
        rows.push(JSON.parse(line) as GatewayDecision);
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

export async function GET(_request: Request): Promise<NextResponse> {
  const cid = correlationId();

  try {
    const [status, allowlist, decisions] = await Promise.all([
      runStatus(),
      readAllowlist(),
      readDecisions(100),
    ]);

    const allowCount = decisions.filter((d) => d.allow).length;
    const denyCount = decisions.filter((d) => !d.allow).length;
    const byServer: Record<string, number> = {};
    for (const d of decisions) {
      byServer[d.server] = (byServer[d.server] || 0) + 1;
    }

    return NextResponse.json(
      {
        data: {
          status,
          allowlist,
          recent_decisions: decisions,
          stats: {
            total: decisions.length,
            allow: allowCount,
            deny: denyCount,
            allow_rate: decisions.length > 0 ? allowCount / decisions.length : 0,
            by_server: byServer,
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
        detail: `MCP Gateway BFF failed: ${msg}`,
        error_code: 'MCP_GATEWAY_BFF_ERROR',
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
        'MCP Gateway BFF is read-only. Adding servers requires editing config/mcp/allowlist.json + reload + drill update (per §56 6-gate adoption).',
      error_code: 'MCP_GATEWAY_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
