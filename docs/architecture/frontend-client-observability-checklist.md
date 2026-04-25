# Frontend Client Observability Checklist

Use this checklist to make browser-side issues observable and debuggable.

## 1. Error capture

- capture uncaught JS exceptions
- capture unhandled promise rejections
- capture React render errors via error boundaries
- capture chunk load failures
- capture hydration failures where detectable

## 2. Network capture

- wrap all API requests through one client layer
- record status code and latency
- record timeout and abort reasons
- record request category or feature name
- include correlation ID on outbound requests

## 3. Context capture

- include route name
- include app release/version
- include browser and device info
- include session ID
- include tenant/user context where allowed
- include feature/module name

## 4. Event model

- define frontend event names consistently
- emit `ui.api_failed`
- emit `ui.render_error`
- emit `ui.route_change_failed`
- emit `ui.action_submit_failed`
- emit `ui.chunk_load_failed`
- emit `ui.retry_clicked`

## 5. Backend linkage

- propagate correlation ID to gateway
- ensure backend logs/traces include same ID
- make request ID visible in support/debug UI where useful
- verify one client error can be tied to one backend trace when applicable

## 6. Dashboarding

- dashboard JS errors by route
- dashboard browser-side API failures
- dashboard release regressions
- dashboard client-visible latency
- dashboard top failing user actions

## 7. Alerting

- alert on sudden spike in JS errors
- alert on browser API failure surge
- alert on chunk load failure surge after release
- alert on route-specific client failure spikes

## 8. UX resilience

- use React error boundaries
- provide fallback UI
- provide retry path
- never leave infinite loading without timeout handling
- surface honest user-facing error states

## 9. Privacy and governance

- mask PII in telemetry
- avoid logging raw sensitive form contents
- define retention policy
- define who can access session replay or client error payloads

## 10. Validation drills

- trigger fake frontend runtime error and verify capture
- force API 500 and verify client event + backend trace linkage
- simulate timeout and verify browser telemetry
- simulate chunk load failure and verify dashboard visibility
- verify release tagging on client events

## 11. Repo-specific priority order

1. wrap frontend API client
2. add global runtime error capture
3. add error boundaries
4. add correlation propagation
5. build client error and browser API dashboards
6. add release-based regression monitoring
