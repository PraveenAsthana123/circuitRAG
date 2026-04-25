import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

async function readBuildId(): Promise<string | null> {
  try {
    const distDir = process.env.NEXT_DIST_DIR || '.next';
    const buildId = await readFile(path.join(process.cwd(), distDir, 'BUILD_ID'), 'utf8');
    return buildId.trim() || null;
  } catch {
    return null;
  }
}

export async function GET() {
  const buildId = await readBuildId();
  return NextResponse.json({
    build_id: buildId,
    app_version: process.env.npm_package_version ?? null,
    git_sha: process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.GIT_SHA ?? null,
    node_env: process.env.NODE_ENV ?? null,
    generated_at: new Date().toISOString(),
  });
}
