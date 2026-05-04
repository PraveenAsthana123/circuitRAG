/**
 * BFF for eval-harness (Layer 10 — Governance + Evaluation).
 *
 * GET /api/v1/eval-harness
 *   → { engines, dependency_status, snyk_workflow_present, ... }
 *
 * Per §47 Layer 10 + §38 governance. Reads requirements.txt for the
 * 3 Python eval deps and checks for .snyk + workflow file.
 *
 * Doesn't import eval_harness.py directly (would emit "X not installed"
 * warnings to logs); just inspects file presence + dep declarations.
 */
import { NextResponse } from 'next/server';
import { access, readFile, stat } from 'fs/promises';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');

const PATHS = {
  evalHarness: path.join(REPO_ROOT, 'services', 'evaluation-svc', 'app', 'eval_harness.py'),
  evalRequirements: path.join(REPO_ROOT, 'services', 'evaluation-svc', 'requirements.txt'),
  snykPolicy: path.join(REPO_ROOT, '.snyk'),
  snykWorkflow: path.join(REPO_ROOT, '.github', 'workflows', 'snyk.yml'),
};

type EngineStatus = {
  name: string;
  available: boolean;
  required_dep: string;
  dep_pinned_in_requirements: boolean;
  layer: string;
  purpose: string;
};

type FileStatus = {
  path: string;
  present: boolean;
  bytes?: number;
};

function correlationId(): string {
  return `eval-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function fileStatus(p: string): Promise<FileStatus> {
  try {
    const s = await stat(p);
    return { path: p.replace(REPO_ROOT + '/', ''), present: true, bytes: s.size };
  } catch {
    return { path: p.replace(REPO_ROOT + '/', ''), present: false };
  }
}

async function reqHasDep(reqPath: string, dep: string): Promise<boolean> {
  try {
    const contents = await readFile(reqPath, 'utf-8');
    const re = new RegExp(`^${dep.replace(/-/g, '[\\-]')}\\b`, 'm');
    return re.test(contents);
  } catch {
    return false;
  }
}

export async function GET(_request: Request): Promise<NextResponse> {
  const cid = correlationId();

  try {
    const [
      evalHarnessFile,
      reqFile,
      snykPolicy,
      snykWorkflow,
      hasRagas,
      hasGuardrails,
      hasDeepEval,
    ] = await Promise.all([
      fileStatus(PATHS.evalHarness),
      fileStatus(PATHS.evalRequirements),
      fileStatus(PATHS.snykPolicy),
      fileStatus(PATHS.snykWorkflow),
      reqHasDep(PATHS.evalRequirements, 'ragas'),
      reqHasDep(PATHS.evalRequirements, 'guardrails-ai'),
      reqHasDep(PATHS.evalRequirements, 'deepeval'),
    ]);

    const engines: EngineStatus[] = [
      {
        name: 'Ragas',
        available: false, // Stage-1 scaffold; deps not installed in dev
        required_dep: 'ragas',
        dep_pinned_in_requirements: hasRagas,
        layer: 'Layer 10 — RAG eval',
        purpose: 'faithfulness · answer-relevance · context-precision · context-recall',
      },
      {
        name: 'Guardrails AI',
        available: false,
        required_dep: 'guardrails-ai',
        dep_pinned_in_requirements: hasGuardrails,
        layer: 'Layer 10 — output validation',
        purpose: 'PII detection · toxic content · jailbreak defense (fail-OPEN in Stage-1)',
      },
      {
        name: 'DeepEval',
        available: false,
        required_dep: 'deepeval',
        dep_pinned_in_requirements: hasDeepEval,
        layer: 'Layer 10 — RAG eval (alt)',
        purpose: 'answer-relevancy · faithfulness · contextual-precision/recall (triangulate vs Ragas)',
      },
      {
        name: 'Snyk',
        available: snykPolicy.present && snykWorkflow.present,
        required_dep: 'SNYK_TOKEN env (CI secret)',
        dep_pinned_in_requirements: snykPolicy.present && snykWorkflow.present,
        layer: 'Cross-cut — security scan',
        purpose: 'dep vulnerability scan · IaC scan · CI gate (HIGH+ blocks)',
      },
    ];

    const allReady = engines.every((e) => e.dep_pinned_in_requirements);

    return NextResponse.json(
      {
        data: {
          stage: 1,
          engines,
          all_stage1_scaffolds_ready: allReady,
          files: {
            eval_harness: evalHarnessFile,
            eval_requirements: reqFile,
            snyk_policy: snykPolicy,
            snyk_workflow: snykWorkflow,
          },
          stage2_wiring_plan: [
            'Stage-2.1 Install ragas + guardrails-ai + deepeval in evaluation-svc image',
            'Stage-2.2 Wire Guardrails AI as inline LLM-output filter (every council answer goes through)',
            'Stage-2.3 Wire Ragas as a periodic eval job (1% sample rate; alerts on faithfulness drift)',
            'Stage-2.4 Wire DeepEval weekly for triangulation against Ragas',
            'Stage-2.5 Configure SNYK_TOKEN secret + verify HIGH+ blocks merge',
            'Stage-2.6 Drill: every Stage-2 wiring updates drill_eval_governance_layer.py to flip stub:False',
          ],
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
        detail: `Eval-harness BFF failed: ${msg}`,
        error_code: 'EVAL_HARNESS_BFF_ERROR',
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
        'Eval-harness BFF is read-only. Stage-2 wiring (real library calls) requires service redeploy with deps installed.',
      error_code: 'EVAL_HARNESS_BFF_READ_ONLY',
    },
    { status: 405 },
  );
}

export const POST = rejectMutating;
export const PUT = rejectMutating;
export const DELETE = rejectMutating;
export const PATCH = rejectMutating;
