# Deep Testing Checklist

This checklist is meant for execution.
Use it when validating the repo during feature work, reviews, release prep, or drills.

## 1. Code Testing Checklist

- [ ] Unit tests cover local business rules and state transitions
- [ ] Integration tests cover route to service to store flow
- [ ] Contract tests cover request, response, and error shapes
- [ ] Regression tests exist for previously fixed bugs
- [ ] Security-sensitive logic has explicit negative-path tests
- [ ] Retry, timeout, and degraded-mode behavior are tested

## 2. Browser And F12 Checklist

- [ ] Browser console has no unexpected runtime errors
- [ ] Browser network tab shows expected status codes
- [ ] Failed API calls render useful user-facing errors
- [ ] Correlation ID or debug context is available where relevant
- [ ] No hydration or chunk-load errors appear
- [ ] Mobile navigation and page layout behave correctly
- [ ] Accessibility warnings are checked for high-value pages

## 3. API Error Checklist

- [ ] `400` invalid payload path tested
- [ ] `401` unauthenticated path tested
- [ ] `403` unauthorized path tested
- [ ] `404` missing resource path tested
- [ ] `409` conflict path tested
- [ ] `422` validation path tested where used
- [ ] `429` rate-limit path tested if applicable
- [ ] `500` internal error path uses stable error envelope
- [ ] `502` or `503` downstream unavailable path is intentional
- [ ] Error body does not leak sensitive internals

## 4. Routing Checklist

- [ ] Frontend navigation links resolve to the correct pages
- [ ] Route-level error boundary works
- [ ] Query and path params validate correctly
- [ ] Gateway routes map to the correct backend services
- [ ] Tenant and auth context survive routing layers
- [ ] Namespace or tool routing uses the correct downstream target

## 5. Frontend Workflow Checklist

- [ ] Loading state is visible
- [ ] Empty state is useful
- [ ] Error state is useful
- [ ] Retry path works
- [ ] Form validation errors are visible and specific
- [ ] Success feedback is visible where expected
- [ ] Desktop and mobile views both work

## 6. Backend Workflow Checklist

- [ ] Idempotency behavior is tested
- [ ] Conditional updates are race-safe where required
- [ ] DB transaction boundaries are correct
- [ ] Retry logic does not duplicate side effects
- [ ] Breaker-open behavior is explicit
- [ ] Audit writes or audit failures are visible
- [ ] Correlation and tenant context propagate correctly

## 7. MCP / Replay / Breaker Checklist

- [ ] MCP failure creates draft when expected
- [ ] Breaker open fast-rejects correctly
- [ ] Breaker half-open and recovery path are exercised
- [ ] Worker replay succeeds after recovery
- [ ] Replay on non-pending draft fails safely
- [ ] Operator and worker attribution stay truthful
- [ ] Replay conflicts are visible operationally

## 8. RAG And AI Quality Checklist

- [ ] Retrieval quality regressions are tested
- [ ] Prompt regressions are tested
- [ ] Unsupported-answer behavior is honest
- [ ] Citation or source behavior is tested where relevant
- [ ] Guardrails block unsafe output when expected
- [ ] PII handling is tested on input, output, and logs

## 9. Release Readiness Checklist

- [ ] CI lint and test surfaces are green or intentionally waived
- [ ] High-value negative paths were exercised recently
- [ ] Known flaky tests are tracked explicitly
- [ ] Degraded-mode behavior was validated, not assumed
- [ ] Operator can debug a failed request through logs or traces
- [ ] Recent bugs were converted into regression tests

## 10. Highest-Value Scenarios For This Repo

- [ ] MCP server unavailable creates draft instead of failing badly
- [ ] Worker replay succeeds after dependency recovery
- [ ] Admin resolve rejects invalid draft state cleanly
- [ ] Breaker open path is visible in metrics and behavior
- [ ] Frontend surfaces API failure usefully
- [ ] Routing preserves tenant and auth context
- [ ] Audit rows exist for sensitive actions
- [ ] Guardrail and PII paths are enforced and visible
