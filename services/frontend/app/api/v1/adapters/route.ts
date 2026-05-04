/**
 * BFF for the adapter inventory — Stage-1 read-only.
 *
 * GET /api/v1/adapters
 *   → { adapters: [{name, status, source_path, drill_path, ...}] }
 *
 * Per §47 + §44. Each adapter exposes status() returning the same
 * shape: stage / available / feature_flag / installed / note.
 * The BFF Promise.all-invokes each adapter's status command + reports.
 */
import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python3');

type AdapterStatus = {
  stage: number;
  available: boolean;
  feature_flag: boolean;
  installed: boolean;
  note: string;
};

type AdapterInfo = {
  name: string;
  source_path: string;
  drill_path: string;
  feature_flag_env: string;
  source_layer: string;
  swap_target: string; // what call site this adapter would replace
  status?: AdapterStatus;
  status_error?: string;
};

const ADAPTERS: AdapterInfo[] = [
  {
    name: 'LiteLLM',
    source_path: 'scripts/litellm_adapter.py',
    drill_path: 'mcp/tests/drill_litellm_adapter.py',
    feature_flag_env: 'LITELLM_ENABLED',
    source_layer: 'Layer 5 — Council LLM transport',
    swap_target: 'scripts/local_council.py call_ollama() — curl-failure fallback',
  },
  {
    name: 'PydanticAI',
    source_path: 'scripts/pydanticai_adapter.py',
    drill_path: 'mcp/tests/drill_pydanticai_adapter.py',
    feature_flag_env: 'PYDANTICAI_ENABLED',
    source_layer: 'Layer 5 — Council AUTHOR validator',
    swap_target: 'scripts/council_schemas.py validate_council_proposal() — regex-failure fallback',
  },
  {
    name: 'Kafka event-publisher',
    source_path: 'scripts/event_publisher.py',
    drill_path: 'mcp/tests/drill_kafka_event_publisher.py',
    feature_flag_env: 'KAFKA_PUBLISH',
    source_layer: 'Layer 8 — event bus fan-out',
    swap_target: 'PolisAI / OpenClaw / Agent Router audit-row publishers',
  },
];

function correlationId(): string {
  return `adapters-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runStatus(scriptName: string): Promise<AdapterStatus | { error: string }> {
  const scriptPath = path.join(REPO_ROOT, scriptName);
  return new Promise((resolve) => {
    const proc = spawn(PYTHON, [scriptPath, 'status'], {
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
    proc.on('error', (err) => resolve({ error: err.message }));
    proc.on('close', (code) => {
      if (code !== 0) {
        resolve({ error: `${scriptName} exited ${code}: ${stderr.slice(0, 200)}` });
        return;
      }
      try {
        const parsed = JSON.parse(stdout);
        // Normalize key names — different adapters use slightly different keys
        // for "installed" (litellm_installed vs pydantic_ai_installed)
        const installedKey = Object.keys(parsed).find((k) => k.endsWith('_installed'));
        resolve({
          stage: parsed.stage ?? 1,
          available: parsed.available ?? false,
          feature_flag: parsed.feature_flag ?? parsed.enabled ?? false,
          installed: installedKey ? Boolean(parsed[installedKey]) : false,
          note: parsed.note ?? '',
        });
      } catch (e) {
        resolve({ error: `not JSON: ${stdout.slice(0, 200)}` });
      }
    });
  });
}

export async function GET(_request: Request): Promise<NextResponse> {
  const cid = correlationId();

  try {
    const enriched = await Promise.all(
      ADAPTERS.map(async (a) => {
        const status = await runStatus(a.source_path);
        if ('error' in status) {
          return { ...a, status_error: status.error };
        }
        return { ...a, status };
      }),
    );

    const all_stage1_present = enriched.every(
      (a) => a.status?.stage === 1 || a.status_error,
    );
    const any_enabled = enriched.some((a) => a.status?.available);

    return NextResponse.json(
      {
        data: {
          adapter_count: enriched.length,
          adapters: enriched,
          all_stage1_present,
          any_enabled_in_dev: any_enabled,
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
        detail: `Adapters BFF failed: ${msg}`,
        error_code: 'ADAPTERS_BFF_ERROR',
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
        'Adapters BFF is read-only. Toggle adapters via env vars (LITELLM_ENABLED / PYDANTICAI_ENABLED / KAFKA_PUBLISH) at process start; not via HTTP.',
      error_code: 'ADAPTERS_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
