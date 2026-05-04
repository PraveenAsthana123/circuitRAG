/**
 * BFF route for PolisAI policy engine — Stage-1 read-only.
 *
 * GET /api/v1/policy
 *   → { rules: [...], recent_decisions: [...], policy_version, ... }
 *
 * Per §47 (Layer 4 PolisAI) + ADR-012. Calls scripts/policy_check.py
 * `rules` for the static catalog and reads .loop/policy_audit.jsonl
 * for the recent decisions stream.
 *
 * Stage-1 contract: GET only. No POST / PUT / DELETE / PATCH —
 * mutating verbs (push, dispatch) are gated through the script's
 * own §42 refusal layer + can't reach this BFF.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import { readFile } from 'fs/promises';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const POLICY_CHECK = path.join(REPO_ROOT, 'scripts', 'policy_check.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');
const AUDIT_LOG = path.join(REPO_ROOT, '.loop', 'policy_audit.jsonl');

type PolicyRule = {
  rule_id: string;
  actor: string;
  tool: string;
  scope_required: string[];
  effect: 'allow' | 'deny';
};

type PolicyRulesPayload = {
  policy_id: string;
  policy_version: string;
  default_effect: 'allow' | 'deny';
  rule_count: number;
  rules: PolicyRule[];
};

type PolicyDecision = {
  allow: boolean;
  rule_matched: string;
  reason: string;
  actor: string;
  tool: string;
  scope_required: string[];
  scope_granted: string[];
  missing_scopes: string[];
  policy_version: string;
  timestamp: number;
};

function correlationId(): string {
  return `policy-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runPolicyRules(): Promise<PolicyRulesPayload> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON, [POLICY_CHECK, 'rules'], {
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
        reject(new Error(`policy_check rules exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`policy_check output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

async function readRecentDecisions(limit = 50): Promise<PolicyDecision[]> {
  try {
    const contents = await readFile(AUDIT_LOG, 'utf-8');
    const lines = contents.trim().split('\n').filter((l) => l.length > 0);
    const tail = lines.slice(-limit);
    const rows: PolicyDecision[] = [];
    for (const line of tail) {
      try {
        rows.push(JSON.parse(line) as PolicyDecision);
      } catch {
        // Skip malformed audit rows; don't fail the whole request
      }
    }
    return rows.reverse(); // newest first
  } catch (e: unknown) {
    if (e instanceof Error && 'code' in e && (e as NodeJS.ErrnoException).code === 'ENOENT') {
      return []; // audit log not yet created — empty list is correct
    }
    throw e;
  }
}

export async function GET(request: Request): Promise<NextResponse> {
  const cid = correlationId();
  const url = new URL(request.url);
  const limit = Number(url.searchParams.get('limit') || '50');

  try {
    const [rules, decisions] = await Promise.all([
      runPolicyRules(),
      readRecentDecisions(Number.isFinite(limit) ? limit : 50),
    ]);

    // Aggregate stats
    const allowCount = decisions.filter((d) => d.allow).length;
    const denyCount = decisions.filter((d) => !d.allow).length;
    const ruleCounts: Record<string, number> = {};
    for (const d of decisions) {
      ruleCounts[d.rule_matched] = (ruleCounts[d.rule_matched] || 0) + 1;
    }

    return NextResponse.json(
      {
        data: {
          ...rules,
          recent_decisions: decisions,
          decision_stats: {
            total: decisions.length,
            allow: allowCount,
            deny: denyCount,
            allow_rate: decisions.length > 0 ? allowCount / decisions.length : 0,
            by_rule: ruleCounts,
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
        detail: `Policy BFF failed: ${msg}`,
        error_code: 'POLICY_BFF_ERROR',
        correlation_id: cid,
      },
      { status: 502 },
    );
  }
}

// Stage-1: read-only. Mutating verbs are §42-gated and would have to
// be added explicitly here AND via PolisAI scope tokens.
async function rejectMutating(): Promise<NextResponse> {
  return NextResponse.json(
    {
      detail:
        'Policy BFF is read-only. Mutating policy rules requires direct edit of config/policies/agent_dispatch.json + reload + drill update.',
      error_code: 'POLICY_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
