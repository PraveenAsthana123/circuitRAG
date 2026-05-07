/**
 * BFF route — agent readiness report (iter-77).
 *
 * Reads `.loop/agent_readiness_report.json` (written by
 * scripts/agent_readiness_check.py at iter-76) and proxies it.
 *
 * If the file is missing or stale (>5min), runs the script first
 * (Node child_process). 30s in-memory cache.
 *
 * Per CLAUDE.md §44 (iter-77 ship), §47 (observability is first-class),
 * §50.5.3 (read-only — script is read-only too), §51 (forensic
 * substrate — every probe carries evidence).
 *
 * Drill: mcp/tests/drill_agent_readiness_ui.py.
 */

import { NextResponse } from "next/server";
import { exec } from "node:child_process";
import { promisify } from "node:util";
import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const execP = promisify(exec);
const CACHE_TTL_MS = 30_000;
const STALE_THRESHOLD_MS = 5 * 60_000; // refresh if file older than 5 min

const REPO_ROOT = resolve(process.cwd(), "..", "..");
const REPORT_PATH = resolve(REPO_ROOT, ".loop", "agent_readiness_report.json");
const SCRIPT_PATH = resolve(REPO_ROOT, "scripts", "agent_readiness_check.py");
const VENV_PYTHON = resolve(REPO_ROOT, ".venv", "bin", "python3");

let _cache: { at: number; json: unknown } | null = null;

async function fileFreshMs(path: string): Promise<number | null> {
  try {
    const s = await stat(path);
    return Date.now() - s.mtimeMs;
  } catch {
    return null;
  }
}

async function refreshReport(): Promise<void> {
  // Best-effort: run the readiness script with --write. Suppress errors;
  // if it fails the read below will still surface whatever exists.
  try {
    await execP(`${VENV_PYTHON} ${SCRIPT_PATH} --write`, {
      cwd: REPO_ROOT,
      maxBuffer: 4 * 1024 * 1024,
      timeout: 30_000,
    });
  } catch {
    // ignored — read-only fall-through
  }
}

export async function GET() {
  const now = Date.now();
  if (_cache && now - _cache.at < CACHE_TTL_MS) {
    return NextResponse.json(_cache.json, {
      headers: { "Cache-Control": "no-store", "X-Cache": "HIT" },
    });
  }

  const ageMs = await fileFreshMs(REPORT_PATH);
  if (ageMs === null || ageMs > STALE_THRESHOLD_MS) {
    await refreshReport();
  }

  let parsed: unknown;
  try {
    const txt = await readFile(REPORT_PATH, "utf-8");
    parsed = JSON.parse(txt);
  } catch (e) {
    return NextResponse.json(
      {
        error: "agent_readiness_report_missing",
        message: (e as Error).message,
        generated_at: new Date().toISOString(),
      },
      { status: 503 },
    );
  }

  _cache = { at: now, json: parsed };
  return NextResponse.json(parsed, {
    headers: { "Cache-Control": "no-store", "X-Cache": "MISS" },
  });
}
