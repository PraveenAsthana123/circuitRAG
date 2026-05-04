/**
 * BFF for techstack audit — Stage-1 read-only.
 *
 * GET /api/v1/techstack-audit
 *   → JSON payload from `python scripts/techstack_audit.py --json`
 *
 * Per §56 (techstack-additions policy gate 4 — empirical verification).
 * Calls the audit script via subprocess (10s timeout). Mutating verbs
 * gated.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const AUDIT_SCRIPT = path.join(REPO_ROOT, 'scripts', 'techstack_audit.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');

function correlationId(): string {
  return `audit-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runAudit(section?: string): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const args = [AUDIT_SCRIPT, '--json'];
    if (section) {
      args.push('--section', section);
    }
    const proc = spawn(PYTHON, args, { cwd: REPO_ROOT, timeout: 10000 });
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
      // Audit exits non-zero when tools are missing; that's expected,
      // not an error. Only reject on signal/spawn errors (negative code).
      if (code === null || code < 0) {
        reject(new Error(`audit exited abnormally (code=${code}): ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`audit output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

export async function GET(request: Request): Promise<NextResponse> {
  const cid = correlationId();
  const url = new URL(request.url);
  const section = url.searchParams.get('section') || undefined;

  try {
    const report = await runAudit(section);
    return NextResponse.json(
      { data: report, correlation_id: cid },
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
        detail: `Techstack audit BFF failed: ${msg}`,
        error_code: 'TECHSTACK_AUDIT_BFF_ERROR',
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
        'Techstack audit BFF is read-only. Adding tools requires the §56 6-gate adoption process (NOT HTTP).',
      error_code: 'TECHSTACK_AUDIT_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
