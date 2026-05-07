/**
 * BFF route — production readiness scorecard (iter-78).
 *
 * Reads `.loop/production_readiness_scorecard.json` (written by
 * scripts/production_readiness_scorecard.py). Re-runs the script if
 * the file is missing or older than 5 min.
 *
 * Per CLAUDE.md §44 (iter-78), §38 §47 §52 §53 §55 (the policies
 * the scorecard aggregates), §50.5.3 (read-only), §51 (forensic).
 *
 * Drill: mcp/tests/drill_production_readiness_ui.py.
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
const STALE_THRESHOLD_MS = 5 * 60_000;

const REPO_ROOT = resolve(process.cwd(), "..", "..");
const REPORT_PATH = resolve(REPO_ROOT, ".loop", "production_readiness_scorecard.json");
const SCRIPT_PATH = resolve(REPO_ROOT, "scripts", "production_readiness_scorecard.py");
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
  try {
    await execP(`${VENV_PYTHON} ${SCRIPT_PATH} --write`, {
      cwd: REPO_ROOT,
      maxBuffer: 4 * 1024 * 1024,
      timeout: 30_000,
    });
  } catch {
    // ignored — read fall-through
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
        error: "production_readiness_scorecard_missing",
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
