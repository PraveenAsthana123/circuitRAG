/**
 * §19 Mandatory Playwright config for frontend E2E.
 *
 * Run:
 *   npm run test:e2e
 *
 * First-time setup (browsers not bundled):
 *   npx playwright install chromium
 *
 * Drill discipline §43 — the canonical drill for these tests is
 * `mcp/tests/drill_e2e_admin_smoke.py`, which uses the project-wide
 * `/tmp/pw-venv` Python harness for cross-language consistency with
 * the rest of `mcp/tests/drill_*.py`. This .ts config is here so an
 * operator can also `npm run test:e2e` directly without bouncing to
 * Python.
 */
import { defineConfig, devices } from '@playwright/test';

const PROD_URL = process.env.PROD_URL ?? 'http://localhost:3000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,         // keep dev-server load predictable
  forbidOnly: !!process.env.CI, // no .only commits in CI
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: PROD_URL,
    trace: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
