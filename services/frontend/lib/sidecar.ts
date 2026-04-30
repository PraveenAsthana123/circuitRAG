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
  rated_by: string | null;
  rating_notes: string | null;
};

export type SidecarEventFilters = {
  limit?: number;
  offset?: number;
  eventType?: string;
  ratingState?: 'all' | 'rated' | 'unrated';
  search?: string;
};

export type SidecarReviewerStat = {
  rated_by: string;
  ratings: number;
};

export type SidecarEventPage = {
  events: SidecarEvent[];
  total: number;
  rated: number;
  unrated: number;
  reviewers: SidecarReviewerStat[];
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
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

if operation == "list":
    limit = int(sys.argv[4])
    event_id = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    event_type = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else ""
    rating_state = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else "all"
    search = sys.argv[8] if len(sys.argv) > 8 and sys.argv[8] else ""
    offset = int(sys.argv[9]) if len(sys.argv) > 9 else 0
    if not db_path.exists():
        print(json.dumps({"events": [], "total": 0, "rated": 0, "unrated": 0, "reviewers": []}))
        raise SystemExit(0)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        base_sql = """
            FROM advisor_events
        """
        select_sql = """
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
              rated_at,
              rated_by,
              rating_notes
        """
        params = []
        clauses = []
        if event_id > 0:
            clauses.append("id = ?")
            params.append(event_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if rating_state == "rated":
            clauses.append("user_rating IS NOT NULL")
        elif rating_state == "unrated":
            clauses.append("user_rating IS NULL")
        if search:
            clauses.append(
                "(content LIKE ? OR source LIKE ? OR advisor_output LIKE ? OR rating_notes LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like])
        if clauses:
            base_sql += " WHERE " + " AND ".join(clauses)
        sql = select_sql + base_sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        query_params = list(params) + [limit, max(0, offset)]
        rows = conn.execute(
            sql,
            tuple(query_params),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) " + base_sql,
            tuple(params),
        ).fetchone()[0]
        rated = conn.execute(
            "SELECT COUNT(*) " + base_sql +
            (" AND user_rating IS NOT NULL" if clauses else " WHERE user_rating IS NOT NULL"),
            tuple(params),
        ).fetchone()[0]
        unrated = conn.execute(
            "SELECT COUNT(*) " + base_sql +
            (" AND user_rating IS NULL" if clauses else " WHERE user_rating IS NULL"),
            tuple(params),
        ).fetchone()[0]
        reviewers = conn.execute(
            """
            SELECT rated_by, COUNT(*) AS ratings
            """ + base_sql +
            (" AND rated_by IS NOT NULL AND rated_by != ''" if clauses else " WHERE rated_by IS NOT NULL AND rated_by != ''") +
            " GROUP BY rated_by ORDER BY ratings DESC, rated_by ASC LIMIT 5",
            tuple(params),
        ).fetchall()
    print(json.dumps({
        "events": [dict(row) for row in rows],
        "total": total,
        "rated": rated,
        "unrated": unrated,
        "reviewers": [dict(row) for row in reviewers],
    }))
    raise SystemExit(0)

if operation == "rate":
    event_id = int(sys.argv[4])
    rating = sys.argv[5]
    rated_by = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else None
    rating_notes = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None
    memory_mod = _load("sidecar_memory", "services/sidecar-advisor/memory.py")
    advisor_mod = _load("sidecar_advisor", "services/sidecar-advisor/advisor.py")
    memory = memory_mod.AdvisorMemory(db_path)
    advisor = advisor_mod.Advisor({}, memory=memory)
    ok = advisor.record_rating(
        event_id=event_id,
        rating=rating,
        rated_by=rated_by,
        rating_notes=rating_notes,
    )
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

export async function listRecentSidecarEvents(filters: SidecarEventFilters = {}): Promise<SidecarEvent[]> {
  const page = await listSidecarEventPage(filters);
  return page.events;
}

export async function listSidecarEventPage(filters: SidecarEventFilters = {}): Promise<SidecarEventPage> {
  const data = await runBridge([
    'list',
    String(filters.limit ?? 12),
    '0',
    filters.eventType || '',
    filters.ratingState || 'all',
    filters.search || '',
    String(filters.offset ?? 0),
  ]);
  return {
    events: Array.isArray(data.events) ? (data.events as SidecarEvent[]) : [],
    total: Number(data.total || 0),
    rated: Number(data.rated || 0),
    unrated: Number(data.unrated || 0),
    reviewers: Array.isArray(data.reviewers) ? (data.reviewers as SidecarReviewerStat[]) : [],
  };
}

export async function rateSidecarEvent(
  eventId: number,
  rating: 'useful' | 'not_useful',
  opts: { ratedBy?: string; ratingNotes?: string } = {},
): Promise<boolean> {
  const data = await runBridge([
    'rate',
    String(eventId),
    rating,
    opts.ratedBy || '',
    opts.ratingNotes || '',
  ]);
  return data.ok === true;
}

export async function getSidecarEventById(eventId: number): Promise<SidecarEvent | null> {
  const data = await runBridge(['list', '1', String(eventId), '', 'all', '', '0']);
  const events = Array.isArray(data.events) ? (data.events as SidecarEvent[]) : [];
  return events[0] ?? null;
}
