# Error Handling Guide

> §19 mandate. Substantive content lives at:
>
> See: [`docs/architecture/frontend-client-observability-and-f12-debugging.md`](architecture/frontend-client-observability-and-f12-debugging.md) — frontend
> See: [`docs/DEMO-ERROR-TRACKER.md`](DEMO-ERROR-TRACKER.md) — §26 ErrorTracker
> See: [`libs/py/documind_core/exceptions.py`](../libs/py/documind_core/exceptions.py) — backend AppError hierarchy
> See: [`libs/py/documind_core/middleware.py`](../libs/py/documind_core/middleware.py) — `register_exception_handlers` (exception → JSONResponse mapping)
> See: [`libs/py/documind_core/error_tracking.py`](../libs/py/documind_core/error_tracking.py) — error aggregation

## Layered error model

| Layer | Surface | Doc |
|---|---|---|
| Render error | `<ErrorBoundary />` | `services/frontend/components/ErrorBoundary.tsx` |
| Backend HTTP | `AppError` → `register_exception_handlers` | `libs/py/documind_core/middleware.py` |
| Client runtime (POST to backend) | `<ClientErrorReporter />` | `services/frontend/components/ClientErrorReporter.tsx` |
| Client runtime (F12) | `window.__errors` | `services/frontend/utils/errorTracker.ts` |
| Window error / unhandled rejection | both reporter AND tracker capture | parallel handlers |
| Service circuit breaker | `documind_core.observability.obs_breaker` | per-namespace breaker |

## Error envelope contract

All backend errors return:

```json
{"detail": "Human-readable", "error_code": "DECISION_NOT_FOUND", "correlation_id": "uuid"}
```

Per §6.2 of CLAUDE.md. Never bare `{"error": "..."}`. The
`error_code` is stable; the `detail` is human-facing.

## Rules (CLAUDE.md §10 + project specifics)

- NEVER swallow errors silently
- NEVER show raw stack traces to users
- ALWAYS log errors with context (correlation_id, tenant_id, route)
- ALWAYS use typed errors (`NotFoundError`, `ValidationError`,
  `ExternalServiceError`) — not bare `Exception`
- ALWAYS provide recovery action (retry, refresh, navigate-back)
