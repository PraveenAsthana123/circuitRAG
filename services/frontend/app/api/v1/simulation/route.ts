import { NextResponse } from 'next/server';
import { readFile, readdir, stat } from 'fs/promises';
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

async function fetchJson(url: string, timeoutMs = 3000): Promise<unknown> {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    if (!r.ok) return { error: `${r.status}` };
    return await r.json();
  } catch (e: unknown) {
    return { error: (e as Error).message };
  }
}

async function readJsonlTail(filePath: string, n: number): Promise<AuditRow[]> {
  if (!existsSync(filePath)) return [];
  const text = await readFile(filePath, 'utf-8');
  const lines = text.trim().split('\n').filter((l) => l.trim());
  return lines.slice(-n).map((l) => {
    try {
      return JSON.parse(l) as AuditRow;
    } catch {
      return {} as AuditRow;
    }
  });
}

async function countDrills(): Promise<{ total: number; recent: string[] }> {
  const drillDir = path.join(REPO_ROOT, 'mcp', 'tests');
  if (!existsSync(drillDir)) return { total: 0, recent: [] };
  const files = (await readdir(drillDir)).filter((f) => f.startsWith('drill_') && f.endsWith('.py'));
  return {
    total: files.length,
    recent: files.sort().slice(-10),
  };
}

async function listMcpServers(): Promise<string[]> {
  const mcpDir = path.join(REPO_ROOT, 'mcp');
  if (!existsSync(mcpDir)) return [];
  const files = await readdir(mcpDir);
  return files
    .filter((f) => f.startsWith('server_') && f.endsWith('.py'))
    .map((f) => f.replace(/^server_|\.py$/g, ''));
}

async function listAgentRoles(): Promise<string[]> {
  const reg = path.join(REPO_ROOT, 'services', 'agent-orchestrator-svc', 'app', 'agent_registry.py');
  if (!existsSync(reg)) return [];
  const text = await readFile(reg, 'utf-8');
  const matches = Array.from(text.matchAll(/role_id="([^"]+)"/g));
  return Array.from(new Set(matches.map((m) => m[1])));
}

async function listExperts(): Promise<string[]> {
  // Read EXPERTS dict keys from ~/.claude/scripts/experts.py if present, else
  // from project copy.
  const candidates = [
    path.join(process.env.HOME || '/home/praveen', '.claude/scripts/experts.py'),
    path.join(REPO_ROOT, 'scripts/experts.py'),
  ];
  for (const p of candidates) {
    if (!existsSync(p)) continue;
    const text = await readFile(p, 'utf-8');
    const m = Array.from(text.matchAll(/^\s{4}"([a-z]+)":\s*\{/gm));
    if (m.length) return m.map((x) => x[1]);
  }
  return [];
}

async function listFixtures(): Promise<{ name: string; size: number }[]> {
  const dir = path.join(REPO_ROOT, 'tests', 'fixtures', 'multimodal');
  if (!existsSync(dir)) return [];
  const files = await readdir(dir);
  const out = [] as { name: string; size: number }[];
  for (const f of files) {
    const s = await stat(path.join(dir, f));
    out.push({ name: f, size: s.size });
  }
  return out;
}

export async function GET() {
  const correlation_id = crypto.randomUUID();
  const [
    ollamaTags,
    ollamaPs,
    audit,
    drills,
    mcpServers,
    agentRoles,
    experts,
    fixtures,
  ] = await Promise.all([
    fetchJson(`${OLLAMA_BASE}/api/tags`),
    fetchJson(`${OLLAMA_BASE}/api/ps`),
    readJsonlTail(path.join(REPO_ROOT, '.loop', 'issue_audit.jsonl'), 50),
    countDrills(),
    listMcpServers(),
    listAgentRoles(),
    listExperts(),
    listFixtures(),
  ]);

  const installed = ((ollamaTags as { models?: { name: string; size: number }[] })?.models || []).map((m) => ({
    name: m.name,
    size_bytes: m.size,
  }));
  const loaded = ((ollamaPs as { models?: { name: string; size_vram?: number }[] })?.models || []).map((m) => ({
    name: m.name,
    size_vram: m.size_vram,
  }));

  // Council audit row dedup by id
  const councilByid = new Map<string, AuditRow>();
  for (const r of audit) {
    if (r.lane !== 'council' || !r.id) continue;
    const existing = councilByid.get(r.id);
    if (!existing || (r.ts || '') > (existing.ts || '')) councilByid.set(r.id, r);
  }
  const councilUnique = Array.from(councilByid.values()).sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));

  return NextResponse.json(
    {
      data: {
        as_of: new Date().toISOString(),
        infrastructure: {
          ollama_installed: installed,
          ollama_loaded: loaded,
          ollama_count: installed.length,
        },
        agents: {
          orchestrator_roles: agentRoles,
          experts_registry: experts,
          mcp_servers: mcpServers,
        },
        drills: {
          total: drills.total,
          recent: drills.recent,
        },
        council: {
          total_runs: audit.filter((r) => r.lane === 'council').length,
          unique_issues: councilUnique.length,
          most_recent: councilUnique.slice(-5),
        },
        single_model_runs: audit.filter((r) => r.lane && r.lane.includes(':') === false && !r.chain).slice(-10),
        fixtures,
      },
      correlation_id,
    },
    { status: 200 },
  );
}
