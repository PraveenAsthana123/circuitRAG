/**
 * BFF for /admin/policy-rego-sync — runs scripts/rego_sync_check.py.
 *
 * Per §47 + §44. Read-only; treats non-zero exit (drift) as expected.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const SYNC_SCRIPT = path.join(REPO_ROOT, 'scripts', 'rego_sync_check.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');

function correlationId(): string {
  return `rego-sync-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runSync(): Promise<{ report: unknown; exit_code: number }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON, [SYNC_SCRIPT, '--json'], {
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
      // exit 0 = sync; 1 = drift; 3 = file missing. Treat 0/1 as expected.
      if (code === null || code < 0 || code > 3) {
        reject(new Error(`rego_sync_check exited unexpectedly (code=${code}): ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve({ report: JSON.parse(stdout), exit_code: code });
      } catch (e) {
        reject(new Error(`output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

export async function GET(_request: Request): Promise<NextResponse> {
  const cid = correlationId();
  try {
    const { report, exit_code } = await runSync();
    return NextResponse.json(
      { data: { ...(report as object), exit_code }, correlation_id: cid },
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
        detail: `Policy-rego sync BFF failed: ${msg}`,
        error_code: 'POLICY_REGO_SYNC_BFF_ERROR',
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
        'Policy-rego sync BFF is read-only. Edit JSON + Rego files directly + re-run drill.',
      error_code: 'POLICY_REGO_SYNC_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
