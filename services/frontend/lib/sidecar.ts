import { execFile } from 'node:child_process';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const WORKDIR = process.cwd();
const REPO_ROOT = path.resolve(WORKDIR, '..', '..');
const DEFAULT_PYTHON = path.join(REPO_ROOT, '.venv', 'bin', 'python');
const PYTHON_BIN = process.env.PYTHON_BIN || DEFAULT_PYTHON;
const ADVISOR_DB = process.env.SIDECAR_ADVISOR_DB || path.join(REPO_ROOT, 'advisor.db');

export type SidecarEvent = {
  id: number;
  created_at: string;
  event_type: string;
  source: string;
  content: string;
  content_preview: string;
  model_used: string | null;
  policy_version: string | null;
  duration_s: number | null;
  advisor_output: string | null;
  advisor_output_raw: string | null;
  user_rating: string | null;
  rated_at: string | null;
};

const PYTHON_BRIDGE = `
import importlib.util
import json
import pathlib
import sqlite3
import sys

repo_root = pathlib.Path(sys.argv[1])
db_path = pathlib.Path(sys.argv[2])
operation = sys.argv[3]

def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, repo_root / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

if operation == "list":
    limit = int(sys.argv[4])
    event_id = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    if not db_path.exists():
        print(json.dumps({"events": []}))
        raise SystemExit(0)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        sql = """
            SELECT
              id,
              created_at,
              event_type,
              source,
              content,
              substr(content, 1, 240) AS content_preview,
              model_used,
              policy_version,
              advisor_output,
              advisor_output_raw,
              duration_s,
              user_rating,
              rated_at
            FROM advisor_events
        """
        params = []
        if event_id > 0:
            sql += " WHERE id = ?"
            params.append(event_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(
            sql,
            tuple(params),
        ).fetchall()
    print(json.dumps({"events": [dict(row) for row in rows]}))
    raise SystemExit(0)

if operation == "rate":
    event_id = int(sys.argv[4])
    rating = sys.argv[5]
    memory_mod = _load("sidecar_memory", "services/sidecar-advisor/memory.py")
    advisor_mod = _load("sidecar_advisor", "services/sidecar-advisor/advisor.py")
    memory = memory_mod.AdvisorMemory(db_path)
    advisor = advisor_mod.Advisor({}, memory=memory)
    ok = advisor.record_rating(event_id=event_id, rating=rating)
    print(json.dumps({"ok": bool(ok)}))
    raise SystemExit(0)

raise RuntimeError(f"unknown operation: {operation}")
`;

async function runBridge(args: string[]) {
  const { stdout } = await execFileAsync(PYTHON_BIN, ['-c', PYTHON_BRIDGE, REPO_ROOT, ADVISOR_DB, ...args], {
    cwd: REPO_ROOT,
    maxBuffer: 1024 * 1024,
  });
  return JSON.parse(stdout.trim() || '{}') as Record<string, unknown>;
}

export async function listRecentSidecarEvents(limit = 12): Promise<SidecarEvent[]> {
  const data = await runBridge(['list', String(limit), '0']);
  return Array.isArray(data.events) ? (data.events as SidecarEvent[]) : [];
}

export async function rateSidecarEvent(eventId: number, rating: 'useful' | 'not_useful'): Promise<boolean> {
  const data = await runBridge(['rate', String(eventId), rating]);
  return data.ok === true;
}

export async function getSidecarEventById(eventId: number): Promise<SidecarEvent | null> {
  const data = await runBridge(['list', '1', String(eventId)]);
  const events = Array.isArray(data.events) ? (data.events as SidecarEvent[]) : [];
  return events[0] ?? null;
}
