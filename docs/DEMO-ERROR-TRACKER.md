# DEMO — §26 Frontend ErrorTracker

## What it is

`window.__errors` — an F12-introspectable runtime diagnostic surface
that lets a developer see the real-time error stream without bouncing
to the backend admin console. Sibling to `<ClientErrorReporter />`,
not a replacement.

## How to use

Open Chrome DevTools (F12) on any `/admin/*` page in **dev mode** and
run in the Console:

```javascript
window.__errors.getSummary()    // counts by category
window.__errors.getReport()     // full structured report
window.__errors.getErrors()     // captured error events
window.__errors.getWarnings()   // captured warnings
window.__errors.clear()         // reset buffer
```

## What it captures

- `console.error` / `console.warn` — wrapped, original still fires
- `window.error` / `unhandledrejection` — separate listener from the
  reporter; doesn't double-wrap fetch
- Long tasks (>100ms) via `PerformanceObserver({entryTypes:['longtask']})`
- Layout shifts (CLS >0.1) via `PerformanceObserver({entryTypes:['layout-shift']})`
- DOM issues on demand via `getReport()`: missing alt, empty links,
  duplicate IDs, missing viewport/charset, unlabeled inputs

## Privacy

- No DOM **content** captured — just structural metadata
- Capped at 500 entries per category (ring buffer; oldest evicted)
- **Production builds**: tracker is a no-op. The init effect early-returns
  when `process.env.NODE_ENV !== 'development'`. Diagnostic noise is
  for the developer, not the end-user.

## Drill

[`mcp/tests/drill_frontend_error_tracker.py`](../mcp/tests/drill_frontend_error_tracker.py)
— 7 steps, **3 negative assertions** locking in:

1. **Step 4 (negative)**: a unique sentinel must be ABSENT before the
   trigger that produces it. Catches a faked tracker that pre-populates
   results.
2. **Step 5 (negative)**: after `clear()`, a different non-triggered
   sentinel must remain absent. Catches a tracker that fabricates
   entries.
3. **Step 7 (negative)**: a never-injected phantom ID must NOT appear
   in the DOM-scan output. Catches a scanner that reads a hardcoded list
   instead of the live tree.

## Run

```bash
# from repo root, with `next dev` already running on :3000
PROD_URL=http://localhost:3000 \
  /tmp/pw-venv/bin/python mcp/tests/drill_frontend_error_tracker.py
```

Expected output ends with `ALL 7 STEPS PASSED`.

## Files

| Path | Purpose |
|---|---|
| `services/frontend/utils/errorTracker.ts` | Tracker class + `errorTracker` singleton |
| `services/frontend/components/ErrorTrackerInit.tsx` | `'use client'` init component, mounted once in `app/layout.tsx` |
| `services/frontend/app/layout.tsx` | Mounts `<ErrorTrackerInit />` alongside `<ClientErrorReporter />` |
| `mcp/tests/drill_frontend_error_tracker.py` | Drill (7 steps, 3 negative) |

## Composition

| Composes with | Why |
|---|---|
| §43 Drill pattern | 3 negative assertions per the drill discipline |
| §26 (this) | The diagnostic surface §26 mandates |
| `<ClientErrorReporter />` (existing) | Tracker is sibling, not replacement; reporter sends to backend, tracker is local F12 |
| §47 Architecture | Frontend operational shell — was the laggard surface in the 2026-04-30 audit |
