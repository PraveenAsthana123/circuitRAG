import { NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';

const REPO_ROOT = path.resolve(process.cwd(), '..', '..');
const OLLAMA_BASE = process.env.OLLAMA_BASE_URL || 'http://localhost:11434';

type AuditRow = {
  ts?: string;
  id?: string;
  lane?: string;
  outcome?: string;
  model?: string;
  tokens?: number;
  latency_s?: number;
  chain?: Record<string, { model: string; tokens: number; latency_s: number }>;
};

async function fetchOllama(p: string) {
  try {
    const r = await fetch(`${OLLAMA_BASE}${p}`, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) return { error: `ollama ${p} -> ${r.status}` };
    return await r.json();
  } catch (e: unknown) {
    return { error: `ollama unreachable: ${(e as Error).message}` };
  }
}

async function readJsonlTail(filePath: string, n: number): Promise<AuditRow[]> {
  if (!existsSync(filePath)) return [];
  const text = await readFile(filePath, 'utf-8');
  const lines = text.trim().split('\n').filter((l) => l.trim());
  const tail = lines.slice(-n);
  return tail.map((l) => {
    try {
      return JSON.parse(l) as AuditRow;
    } catch {
      return {} as AuditRow;
    }
  });
}

async function readChecklistSummary(filePath: string) {
  if (!existsSync(filePath)) return { total: 0, by_difficulty: {}, by_assignee: {} };
  const text = await readFile(filePath, 'utf-8');
  const lines = text.trim().split('\n').filter((l) => l.trim());
  const issues = lines
    .map((l) => {
      try {
        return JSON.parse(l);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
  const byDifficulty: Record<string, number> = {};
  const byAssignee: Record<string, number> = {};
  for (const i of issues) {
    byDifficulty[i.difficulty] = (byDifficulty[i.difficulty] || 0) + 1;
    byAssignee[i.assigned_to] = (byAssignee[i.assigned_to] || 0) + 1;
  }
  return { total: issues.length, by_difficulty: byDifficulty, by_assignee: byAssignee };
}

export async function GET() {
  const correlation_id = crypto.randomUUID();
  const [tags, ps, audit, checklist] = await Promise.all([
    fetchOllama('/api/tags'),
    fetchOllama('/api/ps'),
    readJsonlTail(path.join(REPO_ROOT, '.loop', 'issue_audit.jsonl'), 30),
    readChecklistSummary(path.join(REPO_ROOT, '.loop', 'issue_checklist.jsonl')),
  ]);

  let batchSummary: unknown = null;
  const batchPath = path.join(REPO_ROOT, '.loop', 'council_batch_summary.json');
  if (existsSync(batchPath)) {
    try {
      batchSummary = JSON.parse(await readFile(batchPath, 'utf-8'));
    } catch {
      batchSummary = { error: 'malformed council_batch_summary.json' };
    }
  }

  const installed: { name: string; size_bytes: number; modified: string }[] = (
    (tags as { models?: { name: string; size: number; modified_at: string }[] })?.models || []
  ).map((m) => ({
    name: m.name,
    size_bytes: m.size,
    modified: m.modified_at,
  }));

  const loaded: { name: string; size_vram?: number; expires?: string }[] = (
    (ps as { models?: { name: string; size_vram?: number; expires_at?: string }[] })?.models || []
  ).map((m) => ({
    name: m.name,
    size_vram: m.size_vram,
    expires: m.expires_at,
  }));

  return NextResponse.json(
    {
      data: {
        installed,
        loaded,
        installed_count: installed.length,
        loaded_count: loaded.length,
        recent_audit: audit,
        checklist_summary: checklist,
        council_batch_summary: batchSummary,
        ollama_base: OLLAMA_BASE,
      },
      correlation_id,
    },
    { status: 200 },
  );
}
