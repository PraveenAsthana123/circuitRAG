# DEMO — §27 Production Readiness Checker

## What it is

A 15-check pre-deploy scanner that catches structural failure
patterns before they reach production. Runs in <2 seconds.

## Run

```bash
node scripts/production-checker.js

# Or from frontend:
cd services/frontend && npm run check:prod

# JSON output (for CI / drills):
PROD_CHECK_JSON=1 node scripts/production-checker.js
```

Exit 0 = ready to deploy. Exit 1 = at least one ERROR-severity check
failed; do not deploy.

## The 15 checks (CLAUDE.md §27.1)

| # | Check | Severity |
|---|---|---|
| 1 | No hardcoded localhost URLs | ERROR |
| 2 | No `console.log` in prod frontend code | WARNING |
| 3 | No bare innerHTML assignments (XSS risk) | WARNING |
| 4 | No TODO/FIXME/HACK markers | WARNING |
| 5 | No hardcoded secrets / API keys (heuristic) | ERROR |
| 6 | `.env.template` exists | ERROR |
| 7 | ErrorBoundary component exists | ERROR |
| 8 | Lockfile present (package-lock or pnpm-lock) | ERROR |
| 9 | `.gitignore` covers `.env`, `*.key`, `*.pem` | ERROR |
| 10 | ≥3 unit test files | ERROR |
| 11 | CI pipeline exists | ERROR |
| 12 | `README.md` at root | ERROR |
| 13 | `<ErrorTrackerInit />` mounted in layout (§26) | WARNING |
| 14 | ≥10 drill_*.py files (§43) | ERROR |
| 15 | Compose footer on every deep-dive page (§49) | ERROR |

## Severity model

- **ERROR** — gates deployment. Each ERROR adds 1 to the exit code count.
- **WARNING** — prints but doesn't gate. For high-noise heuristics
  where a false positive shouldn't block ops at 2am.

## False-positive handling

The localhost-URL check skips lines matching:
- Single-line comments (`// http://localhost`)
- Block-comment lines (`* http://localhost`)
- `process.env.X || 'http://localhost:...'` (env-var fallback)
- `default:` keyword + localhost
- Makefile `@echo` lines (deep-dive docs embed Makefile snippets)

Add new skip-patterns to `production-checker.js` when a legitimate
default fires the check.

## Drill

[`mcp/tests/drill_production_checker.py`](../mcp/tests/drill_production_checker.py)
— 5 steps, **2 negative assertions**.

| Step | What it checks |
|---|---|
| 1 | Checker runs + emits valid JSON |
| 2 | Exactly 15 checks (§27.1 mandate) |
| 3 | Current repo state has 0 ERROR-severity failures |
| 4 (**negative**) | Inject `http://localhost:9999` in a temp .ts file → check count goes UP |
| 5 (**negative**) | After cleanup → count returns to baseline |

The negatives prove:
- Step 4: the checker reads the live filesystem (not a cached snapshot)
- Step 5: the checker doesn't fabricate findings (no hidden state)

## Run the drill

```bash
.venv/bin/python mcp/tests/drill_production_checker.py
```

## Composition

| Composes with | Why |
|---|---|
| §27 | Implements the 15 checks verbatim |
| §43 Drill discipline | 2 negative assertions (inject + verify cleanup) |
| §26 ErrorTracker (check 13) | Verifies init component is mounted |
| §49 Compose-footer (check 15) | Promotes the audit script to a per-deploy gate |
| §43 Drill count (check 14) | Self-referential — checker requires drills exist |
