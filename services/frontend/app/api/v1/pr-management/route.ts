/**
 * BFF for PR management — Stage-1 read-only push-queue surface.
 *
 * GET /api/v1/pr-management
 *   → { unpushed_count, head_branch, last_push_age, recent_unpushed_commits, by_type }
 *
 * Per §42 (operator-gated push) + §51 (forensic substrate). Reads
 * git log origin/main..HEAD via subprocess. Does NOT call gh CLI;
 * does NOT create or push PRs — that's pr_management.py create
 * gated behind --confirm.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');

type CommitRow = {
  sha: string;
  short_sha: string;
  subject: string;
  type: string; // feat / fix / docs / test / chore / refactor / etc
  age_seconds: number;
  iso_date: string;
};

function correlationId(): string {
  return `pr-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function gitLog(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn('git', args, { cwd: REPO_ROOT, timeout: 8000 });
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
        reject(new Error(`git ${args.join(' ')} exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      resolve(stdout);
    });
  });
}

function parseCommitLine(line: string, now: number): CommitRow | null {
  // Format: "<sha>|<unix>|<iso>|<subject>"
  const parts = line.split('|');
  if (parts.length < 4) return null;
  const sha = parts[0];
  const unix = parseInt(parts[1], 10);
  const iso = parts[2];
  const subject = parts.slice(3).join('|');
  const typeMatch = subject.match(/^([a-z]+)(?:\([^)]+\))?:/);
  return {
    sha,
    short_sha: sha.slice(0, 12),
    subject,
    type: typeMatch ? typeMatch[1] : 'unknown',
    age_seconds: Math.max(0, now - unix),
    iso_date: iso,
  };
}

export async function GET(_request: Request): Promise<NextResponse> {
  const cid = correlationId();
  const now = Math.floor(Date.now() / 1000);

  try {
    // Get unpushed commits (origin/main..HEAD)
    const logOut = await gitLog([
      'log', 'origin/main..HEAD',
      '--pretty=format:%H|%at|%aI|%s',
      '--max-count=300',
    ]);

    const lines = logOut.trim().split('\n').filter((l) => l.length > 0);
    const commits: CommitRow[] = [];
    for (const line of lines) {
      const row = parseCommitLine(line, now);
      if (row) commits.push(row);
    }

    // Aggregate by commit-type (feat/fix/docs/test/chore/refactor)
    const byType: Record<string, number> = {};
    for (const c of commits) {
      byType[c.type] = (byType[c.type] || 0) + 1;
    }

    // Get current branch + last-push timestamp
    const branchOut = await gitLog(['rev-parse', '--abbrev-ref', 'HEAD']);
    const headBranch = branchOut.trim();

    // Last push: timestamp of origin/main HEAD (when remote was last updated)
    let lastPushAge = -1;
    try {
      const remoteOut = await gitLog([
        'log', '-1', '--pretty=format:%at', 'origin/main',
      ]);
      const remoteUnix = parseInt(remoteOut.trim(), 10);
      if (Number.isFinite(remoteUnix)) {
        lastPushAge = Math.max(0, now - remoteUnix);
      }
    } catch {
      // origin/main may not be set up; lastPushAge stays -1
    }

    return NextResponse.json(
      {
        data: {
          unpushed_count: commits.length,
          head_branch: headBranch,
          last_push_age_s: lastPushAge,
          recent_unpushed_commits: commits.slice(0, 30), // top-30 for the table
          by_type: byType,
          push_command: 'bash scripts/run.sh push --confirm',
          push_warning: '§42 operator gate — needs --confirm OR GIT_PUSH_CONFIRM=1',
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
        detail: `PR management BFF failed: ${msg}`,
        error_code: 'PR_MANAGEMENT_BFF_ERROR',
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
        'PR management BFF is read-only. Pushing requires `bash scripts/run.sh push --confirm` (§42 operator gate); creating PRs requires `python scripts/pr_management.py create --confirm`.',
      error_code: 'PR_MANAGEMENT_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
