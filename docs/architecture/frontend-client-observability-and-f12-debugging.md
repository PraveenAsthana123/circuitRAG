# Frontend Client Observability and F12 Debugging

This document explains how to make a system understand client-side issues:

- browser console errors
- F12 network failures
- route-level failures
- hydration and rendering errors
- broken UI actions
- browser-only regressions

The goal is to convert vague user reports like:

- "the page is broken"
- "button click does nothing"
- "F12 shows error"
- "frontend is slow"

into observable, traceable backend-linked events.

## 1. What the system should understand

A strong client-observability setup should answer:

- which page or route failed
- what exact browser error occurred
- what user or tenant was affected
- whether the error is frontend-only or backend-caused
- which API request failed
- which backend trace and service error it maps to
- whether the issue is new after a release
- how many sessions are affected

## 2. Types of client-side issues

### JavaScript runtime issues
- uncaught exceptions
- unhandled promise rejections
- React render errors
- hydration failures
- dynamic chunk load failures

### Network issues
- API 4xx and 5xx responses
- request timeouts
- CORS errors
- aborted requests
- schema mismatch between client and server

### UX and interaction issues
- button click has no result
- form submit fails silently
- route transition never finishes
- loading state hangs forever
- retry UI not shown

### Performance issues
- slow first render
- slow route transition
- slow API-backed page load
- large bundle or chunk delays
- browser memory or main-thread pressure

## 3. Main mechanisms

### Browser error capture

Capture:

- `window.onerror`
- `window.onunhandledrejection`
- React error boundary failures
- framework-specific route/render failures

This gives:

- error message
- stack trace
- file and line when available
- route and release context

### Network instrumentation

Wrap the browser HTTP client:

- `fetch`
- `axios`
- GraphQL client

Capture:

- method
- URL path
- status
- latency
- timeout
- correlation ID
- request category

### Route and session context

Every client telemetry event should include:

- page or route
- user or tenant context where allowed
- app version or release ID
- browser and device info
- session ID
- correlation ID

### Real User Monitoring

Measure:

- page load
- route transition time
- frontend-visible API latency
- JS error rate
- resource load failure
- Web Vitals

### User-action breadcrumbs

Track useful breadcrumbs such as:

- route visited
- button clicked
- form submitted
- modal opened
- retry clicked

These help reconstruct "what happened before the failure."

## 4. F12 issue interpretation model

People often say "F12 issue" when they mean one of these:

- console exception
- failed network request
- CORS problem
- script/chunk load failure
- React hydration warning or fatal runtime error
- client-side code calling wrong API or wrong route

So the system should not try to "capture DevTools."  
It should capture the structured equivalents of those signals.

## 5. Correlation with backend systems

This is the most important part.

Frontend events should carry a request or correlation ID into backend calls, so you can connect:

```text
User action
 -> browser event
 -> failed HTTP request
 -> gateway logs
 -> backend trace
 -> service error
 -> audit or workflow state
```

Without correlation, frontend and backend debugging stay disconnected.

## 6. Minimum implementation pattern

### Client runtime layer
- global error capture
- unhandled rejection capture
- React error boundary
- wrapped HTTP client

### Context layer
- route name
- release version
- session ID
- tenant/user context where safe
- correlation ID

### Transport layer
- telemetry endpoint or RUM SDK
- optional browser OTel
- log/error aggregation sink

### Operator layer
- dashboard for client JS errors
- dashboard for browser-side API failures
- release comparison view
- route-level incident view

## 7. Good event model

Examples of useful client events:

- `ui.page_loaded`
- `ui.route_change_failed`
- `ui.render_error`
- `ui.hydration_failed`
- `ui.api_failed`
- `ui.chunk_load_failed`
- `ui.action_submit_failed`
- `ui.retry_clicked`

Each event should include:

- timestamp
- route
- feature
- browser
- release
- session
- correlation ID
- normalized error class

## 8. Error boundaries and graceful fallback

A production frontend should not crash the whole page because one component fails.

Use:

- React error boundaries
- fallback UI
- retry path
- support/debug info panel where appropriate

The UI should degrade honestly and visibly.

## 9. Session replay and privacy

Session replay can help a lot for browser-only defects, but must be privacy-aware.

Recommended approach:

- mask text inputs
- mask PII fields
- avoid replaying sensitive admin workflows unless justified
- define retention policy

## 10. Tool categories

Useful tool categories:

- frontend error tracking
- RUM
- browser tracing
- session replay
- metrics and dashboards
- release regression tracking

Examples:

- Sentry
- Grafana Faro
- OpenTelemetry web
- Datadog RUM
- LogRocket
- FullStory

## 11. Repo-specific interpretation

For this repo, client observability matters most for:

- ask flow failures
- upload failures
- documents page API failures
- admin/operator dashboard failures
- mobile navigation or layout regressions
- auth or tenant-context-related client confusion

This is especially important because the backend already has strong observability direction. The missing piece is frontend-to-backend linkage.

## 12. Best dashboard slices

### Client error dashboard
- JS error rate by route
- top error signatures
- release-over-release error diff
- affected sessions/users

### Browser API dashboard
- frontend-visible API failure rate
- slow endpoints from browser perspective
- CORS/network timeout count
- correlation coverage

### UX failure dashboard
- submit failure count
- loading-hang signatures
- retry behavior
- route transition failures

## 13. Bottom line

To understand client-level and F12 issues, the system needs:

- frontend runtime instrumentation
- network instrumentation
- route and session context
- release tagging
- correlation IDs
- dashboards and alerting
- linkage to backend traces and service errors

That is what turns frontend problems from anecdotal complaints into operable system evidence.
