/**
 * BFF route for the Paperclip Stage-1 read-only sandbox aggregator.
 *
 * Per CLAUDE.md §47 (Policy → Manager → Workers) + ADR-012 (Paperclip
 * = sandbox-only). Calls the local Python aggregator
 * (scripts/paperclip_manager.py) via subprocess and returns the JSON
 * snapshot to the admin page.
 *
 * Stage-1 contract: read-only. This route does NOT proxy any write
 * verbs (push, dispatch, deploy). Mutating verbs would have to be
 * added explicitly here AND via PolisAI scope tokens — neither exists
 * in Stage-1.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const PAPERCLIP = path.join(REPO_ROOT, 'scripts', 'paperclip_manager.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');

type Snapshot = {
  stage: number;
  version: string;
  generated_at: number;
  council_batch: {
    total_attempted: number;
    unique_ids_run: number;
    total_elapsed_s: number;
    last_run_count: number;
  };
  apply_attempts: {
    window_days: number;
    total_attempts: number;
    applied: number;
    rejected: number;
    drill_failed: number;
    errored: number;
    apply_rate: number;
    honesty_signal: string;
  };
  audit_decisions: Array<{
    issue_id: string;
    lane: string;
    model: string;
    outcome: string;
    tokens_total: number;
    max_latency_s: number;
  }>;
  pending_issues: {
    total_pending: number;
    by_assignee: Record<string, number>;
    by_severity: Record<string, number>;
    by_difficulty: Record<string, number>;
  };
  council_outcomes: {
    by_outcome: Record<string, number>;
    total: number;
  };
};

function correlationId(): string {
  return `paperclip-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runSnapshot(windowDays = 7): Promise<Snapshot> {
  return new Promise((resolve, reject) => {
    const proc = spawn(
      PYTHON,
      [PAPERCLIP, 'snapshot', '--window-days', String(windowDays)],
      { cwd: REPO_ROOT, timeout: 15000 },
    );
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
        reject(new Error(`paperclip_manager exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`paperclip_manager output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

export async function GET(request: Request): Promise<NextResponse> {
  const cid = correlationId();
  const url = new URL(request.url);
  const windowDays = Number(url.searchParams.get('window_days') || '7');

  try {
    const snap = await runSnapshot(Number.isFinite(windowDays) ? windowDays : 7);
    return NextResponse.json(
      { data: snap, correlation_id: cid },
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
        detail: `Paperclip aggregator failed: ${msg}`,
        error_code: 'PAPERCLIP_AGGREGATOR_ERROR',
        correlation_id: cid,
      },
      { status: 502 },
    );
  }
}

// Stage-1 contract: explicitly reject every other HTTP method. PolisAI
// would also reject these, but a route-level 405 is a faster + clearer
// signal that mutating Paperclip via HTTP is not the Stage-1 surface.
export async function POST(): Promise<NextResponse> {
  return NextResponse.json(
    {
      detail:
        'Paperclip Stage-1 is read-only. Mutating verbs gated until Stage 2/3 (proposal-only / gated delegation) ship via MCP scope tokens + PolisAI confirm:42 boundary.',
      error_code: 'STAGE_1_READ_ONLY',
    },
    { status: 405 },
  );
}

export const PUT = POST;
export const DELETE = POST;
export const PATCH = POST;
