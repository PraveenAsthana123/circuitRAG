/**
 * §19/§25 Smoke E2E for admin deep-dive pages.
 *
 * Every /admin/<topic>/deep page must:
 *   - Return 200
 *   - Render the §49 compose-footer ("Composes with" header)
 *   - NOT log any console.error during initial paint
 *
 * The page list is derived dynamically from disk so this never
 * drifts out of sync with new pages added to app/admin/<x>/deep.
 *
 * Mirror drill: `mcp/tests/drill_e2e_admin_smoke.py` (Python harness;
 * authoritative gate). This spec is for operator-facing
 * `npm run test:e2e` UX.
 */
import { test, expect } from '@playwright/test';
import { readdirSync, statSync } from 'node:fs';
import path from 'node:path';

function discoverDeepPages(): string[] {
  const adminDir = path.resolve(__dirname, '../app/admin');
  const out: string[] = [];
  for (const entry of readdirSync(adminDir)) {
    const candidate = path.join(adminDir, entry, 'deep', 'page.tsx');
    try {
      if (statSync(candidate).isFile()) {
        out.push(`/admin/${entry}/deep`);
      }
    } catch {
      // not a deep-dive page; skip
    }
  }
  return out.sort();
}

const DEEP_PAGES = discoverDeepPages();

test.describe('admin deep-dive smoke', () => {
  for (const route of DEEP_PAGES) {
    test(`${route} loads with compose-footer and no console errors`, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          consoleErrors.push(msg.text());
        }
      });

      const resp = await page.goto(route, { waitUntil: 'domcontentloaded' });
      expect(resp?.status(), `HTTP status for ${route}`).toBeLessThan(400);

      // §49 compose-footer must render — the component renders a
      // visible "Composes with" header. Anchor the assertion on text,
      // not class/component name, so it survives styling refactors.
      await expect(page.getByText(/Composes with/i).first()).toBeVisible({
        timeout: 5_000,
      });

      expect(consoleErrors, `console errors on ${route}`).toHaveLength(0);
    });
  }
});
