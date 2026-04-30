import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const execFileAsync = promisify(execFile);
const REPO_ROOT = path.resolve(process.cwd(), '..', '..');

type RuntimeServiceRow = {
  name: string;
  service: string;
  state: string;
  status: string;
  health: string | null;
  ports: string;
  cpu_percent: string | null;
  mem_usage: string | null;
  mem_percent: string | null;
  net_io: string | null;
  pids: string | null;
  source: 'docker_compose';
};

type RuntimeStatusResponse = {
  generated_at: string;
  repo_root: string;
  ollama: {
    active: boolean;
    state: string;
  };
  services: RuntimeServiceRow[];
  totals: {
    running: number;
    unhealthy: number;
    not_running: number;
  };
  top_consumers: RuntimeServiceRow[];
  warnings: string[];
};

async function run(cmd: string, args: string[]) {
  const { stdout } = await execFileAsync(cmd, args, {
    cwd: REPO_ROOT,
    timeout: 15_000,
    maxBuffer: 8 * 1024 * 1024,
  });
  return stdout;
}

function parseJsonLines(text: string): Array<Record<string, unknown>> {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => {
      try {
        return [JSON.parse(line) as Record<string, unknown>];
      } catch {
        return [];
      }
    });
}

function cpuValue(value: string | null): number {
  if (!value) return -1;
  const numeric = Number.parseFloat(value.replace('%', '').trim());
  return Number.isFinite(numeric) ? numeric : -1;
}

async function dockerComposeRows(): Promise<RuntimeServiceRow[]> {
  let psRows: Array<Record<string, unknown>> = [];
  let statsRows: Array<Record<string, unknown>> = [];

  try {
    psRows = parseJsonLines(await run('docker', ['compose', 'ps', '--format', 'json']));
  } catch {
    return [];
  }

  try {
    statsRows = parseJsonLines(await run('docker', ['stats', '--no-stream', '--format', '{{json .}}']));
  } catch {
    statsRows = [];
  }

  const statsByName = new Map(
    statsRows.map((row) => [
      String(row.Name ?? ''),
      row,
    ]),
  );

  return psRows.map((row) => {
    const name = String(row.Name ?? row.Names ?? row.Service ?? '');
    const stats = statsByName.get(name);
    return {
      name,
      service: String(row.Service ?? name),
      state: String(row.State ?? 'unknown'),
      status: String(row.Status ?? 'unknown'),
      health: row.Health ? String(row.Health) : null,
      ports: String(row.Ports ?? ''),
      cpu_percent: stats?.CPUPerc ? String(stats.CPUPerc) : null,
      mem_usage: stats?.MemUsage ? String(stats.MemUsage) : null,
      mem_percent: stats?.MemPerc ? String(stats.MemPerc) : null,
      net_io: stats?.NetIO ? String(stats.NetIO) : null,
      pids: stats?.PIDs ? String(stats.PIDs) : null,
      source: 'docker_compose',
    };
  });
}

async function ollamaState(): Promise<{ active: boolean; state: string }> {
  try {
    const { stdout } = await execFileAsync('systemctl', ['is-active', 'ollama'], {
      timeout: 5_000,
      maxBuffer: 8 * 1024,
    });
    const state = stdout.trim() || 'unknown';
    return { active: state === 'active', state };
  } catch (err) {
    const state = (err as { stdout?: string }).stdout?.trim() || 'inactive';
    return { active: false, state };
  }
}

export async function GET() {
  const [services, ollama] = await Promise.all([dockerComposeRows(), ollamaState()]);
  const running = services.filter((row) => row.state === 'running').length;
  const unhealthy = services.filter((row) => row.health === 'unhealthy').length;
  const notRunning = services.filter((row) => row.state !== 'running').length;
  const topConsumers = [...services]
    .filter((row) => row.cpu_percent || row.mem_percent)
    .sort((a, b) => cpuValue(b.cpu_percent) - cpuValue(a.cpu_percent))
    .slice(0, 8);

  const warnings: string[] = [];
  if (services.length === 0) {
    warnings.push('docker compose status unavailable from frontend runtime');
  }
  if (!ollama.active) {
    warnings.push(`ollama systemd state is ${ollama.state}`);
  }
  if (unhealthy > 0) {
    warnings.push(`${unhealthy} compose service(s) report unhealthy`);
  }

  const body: RuntimeStatusResponse = {
    generated_at: new Date().toISOString(),
    repo_root: REPO_ROOT,
    ollama,
    services,
    totals: {
      running,
      unhealthy,
      not_running: notRunning,
    },
    top_consumers: topConsumers,
    warnings,
  };

  return NextResponse.json(body);
}
