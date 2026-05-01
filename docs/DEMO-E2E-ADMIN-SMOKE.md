# DEMO — §19/§25 Admin Smoke E2E

## What it is

A two-layer guarantee that every `/admin/<topic>/deep` page in the
frontend renders correctly and follows the §49 compose-footer
contract.

- **Static layer** (filesystem grep, <1 second): every deep page
  imports `DeepDiveCrossRefs` and has ≥3 entries in its `refs` array.
- **Runtime layer** (Playwright, ~10 seconds): a random sample of 4
  pages navigates successfully, renders the visible "Composes with"
  header, and emits zero `console.error` during paint.

## Why two layers

The static layer scales to 45 pages in <1s and catches structural
regressions immediately. The runtime layer catches what static
analysis can't see — JS errors during render, hydration mismatches,
duplicate React keys, broken imports.

The 2026-04-30 run of this drill caught a real bug: `Sidebar.tsx`
was using `key={link.href}` for sidebar items, but three sidebar
entries point at `/tools/nginx-cdn` (CDN, Load balancer, NGINX
edge). React fired duplicate-key warnings on every page with the
sidebar mounted. Fixed by switching to a composite key
`${href}::${label}`.

## How to run

### Quick (drill — Python, project default)

```bash
# from repo root, with `next dev` already running on :3000
PROD_URL=http://localhost:3000 \
  /tmp/pw-venv/bin/python mcp/tests/drill_e2e_admin_smoke.py
```

Expected: `ALL STEPS PASSED (45 static + 4 runtime)`.

### Operator-facing (npm)

```bash
cd services/frontend
npm install
npx playwright install chromium  # one-time browser download
npm run test:e2e
```

(JS Playwright is opt-in; first invocation needs `npx playwright
install` to fetch ~150 MB of Chromium.)

## Drill structure

| Step | What it checks | Type |
|---|---|---|
| 1 | All 45 deep pages import `DeepDiveCrossRefs` | static positive |
| 2 | All 45 pages have ≥3 entries in `refs={[...]}` | static positive |
| 3 | 4 sampled pages navigate OK, footer renders, 0 console.error | runtime positive |
| 4 | `/admin/__phantom_does_not_exist__/deep` returns 404 | **runtime negative** |

The negative is the load-bearing part: it proves Next.js routing
isn't silently catching unknown routes with a wildcard. Without
this, a refactor that adds `app/admin/[...slug]/page.tsx` would
make every route appear to "work" while masking real 404s.

## Files

| Path | Purpose |
|---|---|
| `services/frontend/playwright.config.ts` | Playwright config — testDir `e2e`, baseURL from `PROD_URL` |
| `services/frontend/e2e/admin-smoke.spec.ts` | TS spec discovers deep pages from disk and asserts each |
| `services/frontend/package.json` | Adds `test:e2e`, `format`, `validate`, `pre-merge` scripts |
| `mcp/tests/drill_e2e_admin_smoke.py` | Python drill (canonical gate) |
| `services/frontend/components/Sidebar.tsx` | Composite-key fix discovered by the drill |

## Composition

| Composes with | Why |
|---|---|
| §43 Drill pattern | Static + runtime + 1 negative assertion (phantom-route 404) |
| §49 Compose-footer policy | Static layer is the §49.4 audit script promoted to a drill |
| §19 Frontend toolchain | `playwright.config.ts` + e2e/ + npm scripts close §19 mandates |
| §25 Test pyramid | Smoke at the top of the pyramid, complementing unit tests |
| §26 ErrorTracker (sibling) | Both surface frontend runtime errors; tracker is dev F12, this is gate |
