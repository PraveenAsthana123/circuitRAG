import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const execFileAsync = vi.fn();

vi.mock('node:child_process', () => ({
  execFile: vi.fn(),
}));

vi.mock('node:util', async () => {
  const actual = await vi.importActual<typeof import('node:util')>('node:util');
  return {
    ...actual,
    promisify: () => execFileAsync,
  };
});

function dockerRow(row: Record<string, unknown>): string {
  return `${JSON.stringify(row)}\n`;
}

describe('runtime-status route', () => {
  beforeEach(() => {
    vi.resetModules();
    execFileAsync.mockReset();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('returns runtime status with totals, warnings, and top consumers', async () => {
    execFileAsync.mockImplementation(async (cmd: string, args: string[]) => {
      if (cmd === 'docker' && args.join(' ') === 'compose ps --format json') {
        return {
          stdout: [
            dockerRow({
              Name: 'documind-qdrant',
              Service: 'qdrant',
              State: 'running',
              Status: 'Up 2 hours',
              Health: 'unhealthy',
              Ports: '6333/tcp',
            }),
            dockerRow({
              Name: 'documind-grafana',
              Service: 'grafana',
              State: 'running',
              Status: 'Up 2 hours',
              Health: 'healthy',
              Ports: '3001/tcp',
            }),
            dockerRow({
              Name: 'documind-minio',
              Service: 'minio',
              State: 'exited',
              Status: 'Exited (1)',
              Ports: '59000/tcp',
            }),
          ].join(''),
        };
      }
      if (cmd === 'docker' && args[0] === 'stats') {
        return {
          stdout: [
            dockerRow({
              Name: 'documind-qdrant',
              CPUPerc: '44.5%',
              MemUsage: '512MiB / 4GiB',
              MemPerc: '12.5%',
              NetIO: '1MB / 2MB',
              PIDs: '14',
            }),
            dockerRow({
              Name: 'documind-grafana',
              CPUPerc: '3.1%',
              MemUsage: '220MiB / 4GiB',
              MemPerc: '5.4%',
              NetIO: '500kB / 800kB',
              PIDs: '9',
            }),
          ].join(''),
        };
      }
      if (cmd === 'systemctl' && args.join(' ') === 'is-active ollama') {
        return { stdout: 'active\n' };
      }
      throw new Error(`unexpected command: ${cmd} ${args.join(' ')}`);
    });

    const { GET } = await import('../app/app-meta/runtime-status/route');
    const res = await GET();
    expect(res.status).toBe(200);

    const body = (await res.json()) as {
      services: Array<{ service: string; cpu_percent: string | null; state: string; health: string | null }>;
      totals: { running: number; unhealthy: number; not_running: number };
      top_consumers: Array<{ service: string; cpu_percent: string | null }>;
      ollama: { active: boolean; state: string };
      warnings: string[];
    };

    expect(body.services).toHaveLength(3);
    expect(body.totals).toEqual({
      running: 2,
      unhealthy: 1,
      not_running: 1,
    });
    expect(body.ollama).toEqual({ active: true, state: 'active' });
    expect(body.top_consumers.map((row) => row.service)).toEqual(['qdrant', 'grafana']);
    expect(body.top_consumers[0]?.cpu_percent).toBe('44.5%');
    expect(body.warnings).toContain('1 compose service(s) report unhealthy');
  });

  it('degrades cleanly when docker compose and systemctl are unavailable', async () => {
    execFileAsync.mockImplementation(async (cmd: string, args: string[]) => {
      if (cmd === 'docker' && args.join(' ') === 'compose ps --format json') {
        throw new Error('docker unavailable');
      }
      if (cmd === 'systemctl' && args.join(' ') === 'is-active ollama') {
        throw Object.assign(new Error('inactive'), { stdout: 'inactive\n' });
      }
      throw new Error(`unexpected command: ${cmd} ${args.join(' ')}`);
    });

    const { GET } = await import('../app/app-meta/runtime-status/route');
    const res = await GET();
    expect(res.status).toBe(200);

    const body = (await res.json()) as {
      services: Array<unknown>;
      totals: { running: number; unhealthy: number; not_running: number };
      top_consumers: Array<unknown>;
      ollama: { active: boolean; state: string };
      warnings: string[];
    };

    expect(body.services).toEqual([]);
    expect(body.top_consumers).toEqual([]);
    expect(body.totals).toEqual({
      running: 0,
      unhealthy: 0,
      not_running: 0,
    });
    expect(body.ollama).toEqual({ active: false, state: 'inactive' });
    expect(body.warnings).toContain('docker compose status unavailable from frontend runtime');
    expect(body.warnings).toContain('ollama systemd state is inactive');
  });

  it('keeps service visibility when docker stats is unavailable', async () => {
    execFileAsync.mockImplementation(async (cmd: string, args: string[]) => {
      if (cmd === 'docker' && args.join(' ') === 'compose ps --format json') {
        return {
          stdout: dockerRow({
            Name: 'documind-jaeger',
            Service: 'jaeger',
            State: 'running',
            Status: 'Up 10 minutes',
            Health: '',
            Ports: '16686/tcp',
          }),
        };
      }
      if (cmd === 'docker' && args[0] === 'stats') {
        throw new Error('stats unavailable');
      }
      if (cmd === 'systemctl' && args.join(' ') === 'is-active ollama') {
        return { stdout: 'active\n' };
      }
      throw new Error(`unexpected command: ${cmd} ${args.join(' ')}`);
    });

    const { GET } = await import('../app/app-meta/runtime-status/route');
    const res = await GET();
    expect(res.status).toBe(200);

    const body = (await res.json()) as {
      services: Array<{ service: string; cpu_percent: string | null; mem_percent: string | null }>;
      totals: { running: number; unhealthy: number; not_running: number };
      top_consumers: Array<unknown>;
      warnings: string[];
    };

    expect(body.services).toHaveLength(1);
    expect(body.services[0]).toMatchObject({
      service: 'jaeger',
      cpu_percent: null,
      mem_percent: null,
    });
    expect(body.totals).toEqual({
      running: 1,
      unhealthy: 0,
      not_running: 0,
    });
    expect(body.top_consumers).toEqual([]);
    expect(body.warnings).toEqual([]);
  });
});
