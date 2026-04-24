import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Build-time repo-file reader. Only runs in Server Components, so the
 * repo contents never ship to the browser bundle — just the specific
 * file contents we choose to render.
 *
 * The REPO_ROOT walks up from the frontend package to the monorepo root.
 */
const REPO_ROOT = resolve(process.cwd(), '..', '..');

export function readRepoFile(relPath: string, maxLines?: number): string {
  try {
    const abs = resolve(REPO_ROOT, relPath);
    // Defense-in-depth: reject paths that try to escape the repo via ../
    if (!abs.startsWith(REPO_ROOT)) {
      return `// path outside repo root: ${relPath}`;
    }
    const content = readFileSync(abs, 'utf8');
    if (maxLines) {
      const lines = content.split('\n');
      if (lines.length > maxLines) {
        return lines.slice(0, maxLines).join('\n') + `\n\n// … (${lines.length - maxLines} more lines — see repo file)`;
      }
    }
    return content;
  } catch (err) {
    return `// could not read ${relPath}: ${(err as Error).message}`;
  }
}
