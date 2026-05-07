import { execFile as execFileCb } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';

import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const execFile = promisify(execFileCb);
const frontendRoot = process.cwd();
const repoRoot = path.resolve(frontendRoot, '..', '..');
const pythonBin = path.join(repoRoot, '.venv', 'bin', 'python');

async function seedAdvisorDb(dbPath: string, withEvent: boolean): Promise<number> {
  const script = `
import importlib.util
import pathlib
import sys

repo_root = pathlib.Path(sys.argv[1])
db_path = pathlib.Path(sys.argv[2])
with_event = sys.argv[3] == "1"

spec = importlib.util.spec_from_file_location("sidecar_memory_seed", repo_root / "services/sidecar-advisor/memory.py")
if spec is None or spec.loader is None:
    raise RuntimeError("unable to load memory.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
mem = module.AdvisorMemory(db_path)
event_id = 0
if with_event:
    event_id = mem.record_event(
        event_type="prompt",
        source="manual",
        content="seed event for route test",
        model_used="stub-model",
        advisor_output={"summary": "ok"},
        duration_s=0.01,
    )
print(event_id)
`;
  const { stdout } = await execFile(pythonBin, ['-c', script, repoRoot, dbPath, withEvent ? '1' : '0'], {
    cwd: repoRoot,
  });
  return Number(stdout.trim() || '0');
}

async function readRatingRow(dbPath: string, eventId: number): Promise<Record<string, string | null>> {
  const script = `
import json
import sqlite3
import sys

db_path = sys.argv[1]
event_id = int(sys.argv[2])
with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT user_rating, rated_by, rating_notes, rated_at FROM advisor_events WHERE id = ?",
        (event_id,),
    ).fetchone()
print(json.dumps(dict(row) if row else {}))
`;
  const { stdout } = await execFile(pythonBin, ['-c', script, dbPath, String(eventId)], {
    cwd: repoRoot,
  });
  return JSON.parse(stdout.trim() || '{}') as Record<string, string | null>;
}

describe('sidecar rating route', () => {
  let tmpDir = '';
  let dbPath = '';

  beforeEach(async () => {
    tmpDir = await mkdtemp(path.join(os.tmpdir(), 'sidecar-rating-route-'));
    dbPath = path.join(tmpDir, 'advisor.db');
    vi.resetModules();
    process.env.PYTHON_BIN = pythonBin;
    process.env.SIDECAR_ADVISOR_DB = dbPath;
  });

  afterEach(async () => {
    delete process.env.PYTHON_BIN;
    delete process.env.SIDECAR_ADVISOR_DB;
    vi.resetModules();
    if (tmpDir) {
      await rm(tmpDir, { recursive: true, force: true });
    }
  });

  it('redirects with saved and persists rating metadata', async () => {
    const eventId = await seedAdvisorDb(dbPath, true);
    const { POST } = await import('../app/api/v1/sidecar/events/[eventId]/rating/route');

    const form = new FormData();
    form.set('rating', 'useful');
    form.set('rated_by', 'praveen');
    form.set('rating_notes', 'tight and actionable');
    const req = new NextRequest(`http://localhost/api/v1/sidecar/events/${eventId}/rating`, {
      method: 'POST',
      body: form,
    });

    const res = await POST(req, { params: Promise.resolve({ eventId: String(eventId) }) });
    expect(res.status).toBe(303);
    expect(res.headers.get('location')).toContain('/admin/sidecar?rating=saved#live-ratings');

    const row = await readRatingRow(dbPath, eventId);
    expect(row.user_rating).toBe('useful');
    expect(row.rated_by).toBe('praveen');
    expect(row.rating_notes).toBe('tight and actionable');
    expect(row.rated_at).toBeTruthy();
  });

  it('redirects with invalid for bad rating payloads', async () => {
    const eventId = await seedAdvisorDb(dbPath, true);
    const { POST } = await import('../app/api/v1/sidecar/events/[eventId]/rating/route');

    const form = new FormData();
    form.set('rating', 'maybe');
    const req = new NextRequest(`http://localhost/api/v1/sidecar/events/${eventId}/rating`, {
      method: 'POST',
      body: form,
    });

    const res = await POST(req, { params: Promise.resolve({ eventId: String(eventId) }) });
    expect(res.status).toBe(303);
    expect(res.headers.get('location')).toContain('/admin/sidecar?rating=invalid#live-ratings');
  });

  it('redirects with missing when the event id does not exist', async () => {
    await seedAdvisorDb(dbPath, false);
    const { POST } = await import('../app/api/v1/sidecar/events/[eventId]/rating/route');

    const form = new FormData();
    form.set('rating', 'not_useful');
    form.set('rated_by', 'operator');
    form.set('rating_notes', 'missing row');
    const req = new NextRequest('http://localhost/api/v1/sidecar/events/999/rating', {
      method: 'POST',
      body: form,
    });

    const res = await POST(req, { params: Promise.resolve({ eventId: '999' }) });
    expect(res.status).toBe(303);
    expect(res.headers.get('location')).toContain('/admin/sidecar?rating=missing#live-ratings');
  });

  it('redirects GET requests to the sidecar event detail page', async () => {
    const eventId = await seedAdvisorDb(dbPath, true);
    const { GET } = await import('../app/api/v1/sidecar/events/[eventId]/rating/route');

    const req = new NextRequest(`http://localhost/api/v1/sidecar/events/${eventId}/rating`, {
      method: 'GET',
    });

    const res = await GET(req, { params: Promise.resolve({ eventId: String(eventId) }) });
    expect(res.status).toBe(303);
    expect(res.headers.get('location')).toContain(`/admin/sidecar/${eventId}`);
  });

  it('redirects invalid GET event ids to the sidecar summary with invalid state', async () => {
    const { GET } = await import('../app/api/v1/sidecar/events/[eventId]/rating/route');

    const req = new NextRequest('http://localhost/api/v1/sidecar/events/bad/rating', {
      method: 'GET',
    });

    const res = await GET(req, { params: Promise.resolve({ eventId: 'bad' }) });
    expect(res.status).toBe(303);
    expect(res.headers.get('location')).toContain('/admin/sidecar?rating=invalid#live-ratings');
  });
});
