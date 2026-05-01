# Debugging Plugins

> §19 mandate. Substantive content lives at:
>
> See: [`docs/architecture/frontend-client-observability-checklist.md`](architecture/frontend-client-observability-checklist.md)
> See: [`docs/DEMO-ERROR-TRACKER.md`](DEMO-ERROR-TRACKER.md) — §26 in-browser tracker
> See: [`docs/architecture/frontend-client-observability-and-f12-debugging.md`](architecture/frontend-client-observability-and-f12-debugging.md)

## Browser-side debugging surface

| Tool | Purpose | Location |
|---|---|---|
| `window.__errors` | F12-introspectable error tracker | `services/frontend/utils/errorTracker.ts` |
| `<ClientErrorReporter />` | window.error / unhandledrejection → backend POST | `services/frontend/components/ClientErrorReporter.tsx` |
| `<ErrorBoundary />` | render-error capture | `services/frontend/components/ErrorBoundary.tsx` |
| Build-update banner | Detects newer frontend build than current tab | inside ClientErrorReporter |
| Chunk-recovery banner | Recovers from stale chunk loads with one reload | inside ClientErrorReporter |

## F12 cheat sheet (dev mode)

```javascript
window.__errors.getSummary()    // counts by category
window.__errors.getReport()     // full report including DOM scan
window.__errors.getErrors()     // captured errors
window.__errors.getWarnings()   // captured warnings
window.__errors.clear()         // reset

// Network: open Network tab; failed fetches also log via the
// reporter (server-side aggregation under /admin/client-errors).

// Performance: Performance tab → Record → Stop. Long tasks (>100ms)
// are also captured by __errors automatically via PerformanceObserver.
```

## Recommended Chrome extensions (CLAUDE.md §26.5)

- React Developer Tools — component/state inspection
- axe DevTools — accessibility audit (WCAG 2.1 AA)
- Lighthouse — built-in (Audits tab)
- Pesticide — CSS layout debugging

## Backend-side debugging

| Tool | Purpose |
|---|---|
| `/api/v1/admin/client-errors` | Aggregated frontend errors POST'd by reporter |
| `/api/v1/admin/trace/<correlation_id>` | Trace-link reconstruction (audit ↔ draft) |
| Jaeger UI | Distributed tracing |
| Grafana | Service metrics + SLO burn-rate |
| structured logs | `correlation_id` lookup across services |

## Drill-driven debugging

When something breaks: run the drill that owns the surface. Every
drill prints `✓`/`✗` markers per step, ending with `ALL N STEPS
PASSED` or per-step failure context.

```bash
# Frontend smoke
.venv/bin/python mcp/tests/drill_e2e_admin_smoke.py

# Per-service smoke
.venv/bin/python mcp/tests/drill_service_smoke.py

# Explainability endpoint
.venv/bin/python mcp/tests/drill_explain_endpoint.py

# All drills
scripts/run_drills.py --parallel 4
```
