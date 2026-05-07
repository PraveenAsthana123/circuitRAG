/**
 * BFF route — MCP fleet health dashboard data.
 *
 * Exposes the 4-inventory health JSON the operator UI consumes.
 * Calls scripts/mcp_fleet_health.py --json --full via Node child_process,
 * caches the result in-memory for CACHE_TTL_MS so rapid page refreshes
 * don't fork a Python process per click.
 *
 * Per CLAUDE.md §44 (iter-73 UI), §47 (observability is a first-class
 * surface), §50.5.3 (read-only; never invokes write tools), §51
 * (forensic substrate — generated_at carried through).
 *
 * Drill: mcp/tests/drill_mcp_fleet_health_ui.py.
 */

import { NextResponse } from "next/server";
import { exec } from "node:child_process";
import { promisify } from "node:util";
import { resolve } from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const execP = promisify(exec);
const CACHE_TTL_MS = 30_000; // 30s; UI auto-refreshes every 10s

let _cache: { at: number; json: unknown } | null = null;

const REPO_ROOT = resolve(process.cwd(), "..", "..");

export async function GET() {
  const now = Date.now();
  if (_cache && now - _cache.at < CACHE_TTL_MS) {
    return NextResponse.json(_cache.json, {
      headers: { "Cache-Control": "no-store", "X-Cache": "HIT" },
    });
  }

  // Locate the Python script + venv (best-effort)
  const script = resolve(REPO_ROOT, "scripts", "mcp_fleet_health.py");
  const venvPython = resolve(REPO_ROOT, ".venv", "bin", "python3");
  const python = venvPython;

  const cmd = `${python} ${script} --json --full --probe-timeout 1.5`;
  let stdout = "";
  let stderr = "";
  try {
    const r = await execP(cmd, {
      cwd: REPO_ROOT,
      maxBuffer: 4 * 1024 * 1024,
      timeout: 30_000,
    });
    stdout = r.stdout;
    stderr = r.stderr;
  } catch (e: unknown) {
    const err = e as { stdout?: string; stderr?: string; message?: string };
    // Exit code 1 / 2 from the script means FAILING / NOT_INSTALLED present —
    // still has a valid JSON body. Only treat empty stdout as a real error.
    stdout = err.stdout ?? "";
    stderr = err.stderr ?? err.message ?? "";
    if (!stdout) {
      return NextResponse.json(
        {
          error: "fleet_health_script_failed",
          stderr: stderr.slice(0, 500),
          generated_at: new Date().toISOString(),
        },
        { status: 503 },
      );
    }
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch (e) {
    return NextResponse.json(
      {
        error: "fleet_health_invalid_json",
        message: (e as Error).message,
        stdout_head: stdout.slice(0, 200),
      },
      { status: 502 },
    );
  }

  _cache = { at: now, json: parsed };
  return NextResponse.json(parsed, {
    headers: { "Cache-Control": "no-store", "X-Cache": "MISS" },
  });
}
