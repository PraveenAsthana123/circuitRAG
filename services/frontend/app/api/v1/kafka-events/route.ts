/**
 * BFF for Kafka event-publisher (Layer 8) — Stage-1 read-only.
 *
 * GET /api/v1/kafka-events
 *   → { enabled, topics, bootstrap_servers, schema_per_topic, recent_attempts }
 *
 * Per §47 Layer 8 + §41.5. Calls event_publisher.py status. Recent
 * attempts are sourced from the originating audit logs (policy_audit,
 * openclaw_audit, agent_router_audit) — the rows that WOULD have
 * been published when KAFKA_PUBLISH=1.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import { readFile } from 'fs/promises';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const EP_SCRIPT = path.join(REPO_ROOT, 'scripts', 'event_publisher.py');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');
const POLICY_AUDIT = path.join(REPO_ROOT, '.loop', 'policy_audit.jsonl');
const ROUTER_AUDIT = path.join(REPO_ROOT, '.loop', 'agent_router_audit.jsonl');
const OPENCLAW_AUDIT = path.join(REPO_ROOT, '.loop', 'openclaw_audit.jsonl');

type StatusPayload = {
  stage: number;
  enabled: boolean;
  topics: Record<string, string>;
  bootstrap_servers: string;
  note: string;
};

function correlationId(): string {
  return `kafka-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runStatus(): Promise<StatusPayload> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON, [EP_SCRIPT, 'status'], {
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
        reject(new Error(`event_publisher status exited ${code}: ${stderr.slice(0, 200)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`event_publisher output not JSON: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

async function countAuditRows(filePath: string): Promise<number> {
  try {
    const contents = await readFile(filePath, 'utf-8');
    return contents.split('\n').filter((l) => l.trim().length > 0).length;
  } catch {
    return 0;
  }
}

const SCHEMA_PER_TOPIC: Record<
  string,
  { source_layer: string; payload_shape: string; example_event_type: string }
> = {
  'documind.policy.decisions': {
    source_layer: 'PolisAI (Layer 4)',
    payload_shape:
      '{ allow, rule_matched, actor, tool, scope_required, scope_granted, missing_scopes, policy_version, policy_id, timestamp }',
    example_event_type: 'policy_decision_made',
  },
  'documind.paperclip.snapshots': {
    source_layer: 'Paperclip (Layer 7) — via BFF, NOT bare aggregator',
    payload_shape:
      '{ stage, version, generated_at, council_batch, apply_attempts, audit_decisions, pending_issues, council_outcomes }',
    example_event_type: 'paperclip_snapshot_taken',
  },
  'documind.openclaw.dispatches': {
    source_layer: 'OpenClaw (Layer 11)',
    payload_shape:
      '{ allow, rule_matched, requesting_agent, target_agent, capability, scope_required, scope_granted, missing_scopes, dispatch_id }',
    example_event_type: 'openclaw_dispatch_evaluated',
  },
  'documind.router.classifications': {
    source_layer: 'Agent Router (Layer 3)',
    payload_shape:
      '{ intent, risk, recommended_actor, recommended_tool, confidence, reasons, message_hash, timestamp }',
    example_event_type: 'router_classified',
  },
};

export async function GET(request: Request): Promise<NextResponse> {
  const cid = correlationId();

  try {
    const [status, policyCount, routerCount, openclawCount] = await Promise.all([
      runStatus(),
      countAuditRows(POLICY_AUDIT),
      countAuditRows(ROUTER_AUDIT),
      countAuditRows(OPENCLAW_AUDIT),
    ]);

    return NextResponse.json(
      {
        data: {
          ...status,
          schema_per_topic: SCHEMA_PER_TOPIC,
          would_have_published: {
            'documind.policy.decisions': policyCount,
            'documind.openclaw.dispatches': openclawCount,
            'documind.router.classifications': routerCount,
            'documind.paperclip.snapshots': 0, // no on-disk audit; published via BFF in Stage-3
          },
          total_would_have_published: policyCount + routerCount + openclawCount,
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
        detail: `Kafka events BFF failed: ${msg}`,
        error_code: 'KAFKA_EVENTS_BFF_ERROR',
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
        'Kafka events BFF is read-only. Publishing events is the originating layers job (PolisAI / OpenClaw / Agent Router); this BFF only displays status.',
      error_code: 'KAFKA_EVENTS_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
