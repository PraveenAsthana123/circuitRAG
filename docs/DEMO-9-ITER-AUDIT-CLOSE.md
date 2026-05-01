# DEMO — Closing the 9-iteration audit (2026-04-30)

## Context

The audit on 2026-04-30 identified 9 structural gaps in circuitRAG
against the global CLAUDE.md mandates (§§ 8, 19, 25, 26, 27, 47, 48,
48.3, 49). This sweep closes all 9 with a drill per gap and a final
roll-up that verifies them end-to-end.

## What shipped

| Iter | Gap | Closed by | Drill |
|---|---|---|---|
| 13/N | §26 — F12 ErrorTracker | `services/frontend/utils/errorTracker.ts` + `<ErrorTrackerInit/>` | `drill_frontend_error_tracker.py` |
| 14/N | §19/§25 — Playwright + smoke E2E | `playwright.config.ts` + `e2e/admin-smoke.spec.ts` (caught real Sidebar dup-key bug) | `drill_e2e_admin_smoke.py` |
| 15/N | §48 — `/api/v1/explain` endpoint | `services/evaluation-svc/app/explain.py` + DecisionAuditRow + ExplainResponse | `drill_explain_endpoint.py` |
| 16/N | §8 — per-service smoke for 6 services | Tests in 6 services (1 Python + 5 Go) | `drill_service_smoke.py` |
| 17/N | §19 — 12 mandated doc stubs | Redirector files; drill checks every link target exists | `drill_doc_stubs_section19.py` |
| 18/N | §27 — production-checker.js | 15-check pre-deploy scanner with JSON output | `drill_production_checker.py` |
| 19/N | §19 — frontend toolchain | `.prettierrc` + `.prettierignore` + `.husky/pre-commit` | `drill_frontend_toolchain.py` |
| 20/N | §48.3 — model cards | INDEX + TEMPLATE + 4 cards (3 LLMs + bge-m3) | `drill_model_cards.py` |
| 21/N | §19 — sidecar-advisor Dockerfile | `services/sidecar-advisor/Dockerfile` + roll-up of all 9 drills | `drill_sidecar_dockerfile.py` |

## Roll-up drill

[`mcp/tests/drill_sidecar_dockerfile.py`](../mcp/tests/drill_sidecar_dockerfile.py)
runs every iter drill in sequence with the right venv (project
`.venv` for in-process drills; `/tmp/pw-venv` for browser drills).

Run:

```bash
# Prereq: `next dev` running on :3000 for the browser drills
.venv/bin/python mcp/tests/drill_sidecar_dockerfile.py
```

Expected tail: `ALL STEPS PASSED — 9-iteration sweep verified end-to-end`

## Numbers (2026-04-30)

```
✓ step 1: services/sidecar-advisor/Dockerfile exists
✓ step 2: Dockerfile has all 5 §19.13 sections
✓ step 3 (negative): no `USER root` regression
✓ step 4: all 12 services have a Dockerfile

Roll-up:
  ✓ iter 13/N — ErrorTracker (§26)        → ALL 7 STEPS PASSED
  ✓ iter 14/N — admin smoke E2E (§19/§25) → ALL STEPS PASSED (45 static + 4 runtime)
  ✓ iter 15/N — explain endpoint (§48)    → ALL 6 STEPS PASSED
  ✓ iter 16/N — service smoke (§8)        → ALL STEPS PASSED (6 services covered)
  ✓ iter 17/N — §19 doc stubs             → ALL 4 STEPS PASSED (13 §19 docs verified)
  ✓ iter 18/N — production-checker (§27)  → ALL 5 STEPS PASSED
  ✓ iter 19/N — frontend toolchain (§19)  → ALL 7 STEPS PASSED
  ✓ iter 20/N — model cards (§48.3)       → ALL STEPS PASSED (3 LLMs + 1 extra models)

ALL STEPS PASSED — 9-iteration sweep verified end-to-end
```

## What real bugs the drills caught

- **iter 14**: `Sidebar.tsx` had `key={link.href}` for sidebar items;
  3 entries pointed at `/tools/nginx-cdn` → React duplicate-key
  warning on every page. Fixed with composite `${href}::${label}`
  key.
- **iter 17**: 3 broken redirect links across the 12 doc stubs
  (wrong path in ERROR_HANDLING_GUIDE, forward-looking link in
  CODE_GUIDELINES, no links in FOLDER_STRUCTURE). Fixed before
  commit.
- **iter 18**: 0 ERROR-severity production-checker findings, 1
  acceptable WARNING (Mermaid SVG injection — by design for the
  mermaid library).

## Negative-assertion catalog (per §43)

Every drill carries at least one. Highlights:

- iter 13 step 4: sentinel ABSENT before trigger (causality lock)
- iter 13 step 5: clear() empties storage AND non-triggered
  sentinel stays absent (no fabrication)
- iter 14 step 4: phantom route `/admin/__phantom_…/deep` MUST 404
  (catches catch-all wildcard)
- iter 15 step 3: phantom prediction_id → 404 + DECISION_NOT_FOUND
- iter 15 step 4: missing query param → 422 (no implicit "latest")
- iter 16 step 4: list-size lock (drift catch on the audit scope)
- iter 17 step 3: every redirect target must exist on disk
- iter 18 step 4: inject bad pattern → count goes UP (proves
  checker reads live filesystem)
- iter 18 step 5: cleanup → count returns to baseline (no
  fabrication / no leaked state)
- iter 19 step 6: corrupt JSON parser test (validation isn't a
  tautology)
- iter 19 step 7: phantom npm script absent (script audit reads
  real package.json)
- iter 20 step 6: phantom-llm-9000 has NO card
- iter 20 step 7: stripping a §48.3 section is correctly DETECTED
- iter 21 step 3: no `USER root` regression after non-root USER

## Composition

This sweep adds 9 new drills, 4 new components (ErrorTracker,
ErrorTrackerInit, DecisionAuditStore, production-checker), 12 new
docs (the §19 stubs), 4 model cards, and tests across 6 services.
Drill total before sweep: 208. After: ~217.

| Composes with | Why |
|---|---|
| §43 Drill discipline | Every iter shipped a drill; every drill has ≥1 negative assertion |
| §44 Autonomous loop | This sweep was the loop output between iter 13–21; one commit per iter |
| §49 Compose-footer | Every new deep-dive page (n/a here, no new ones) would carry the footer; the existing 45 stayed at 100% compliance |
| §51 GitHub metadata | Each commit body cites the closed gap and the 4-line negative-assertion note |
