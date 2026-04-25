# Testing And Error Debugging Map

This note is a learning map for testing and debugging in backend, frontend, and AI-heavy systems.

The goal is to move from:

- code runs on my machine

to:

- the system is testable, debuggable, and operationally trustworthy

## 1. The Main Testing Layers

Testing should be split into clear layers.

### Unit tests

Used for:

- pure functions
- local business rules
- state transitions
- data transformations
- scoring logic

Best for:

- speed
- edge-case coverage
- precise failure localization

### Integration tests

Used for:

- route to service to store flow
- service to dependency interactions
- DB behavior
- external client wrappers
- retry and timeout behavior

Best for:

- contract correctness
- wiring confidence
- realistic error paths

### Contract tests

Used for:

- API request and response shapes
- error envelope consistency
- tool or event schemas
- auth and tenant propagation assumptions

Best for:

- preventing drift between caller and callee

### End-to-end tests

Used for:

- real browser or full request flow
- user navigation
- upload to ask to result flow
- admin or operator workflows

Best for:

- real product behavior
- regression coverage across multiple layers

### Regression tests

Used for:

- old bugs
- prompt regressions
- retrieval regressions
- UI breakages
- error-envelope changes

Best for:

- protecting against repeat failures

### Drill and chaos tests

Used for:

- dependency outage
- breaker behavior
- replay after recovery
- degraded-mode correctness
- operational truthfulness

Best for:

- resilience validation
- incident-readiness

## 2. Error Testing Categories

A strong test strategy covers both success and failure behavior.

### Business errors

Examples:

- invalid workflow transition
- replay on non-pending draft
- unauthorized action
- duplicate request conflict

### Validation errors

Examples:

- bad payload
- missing required fields
- malformed params
- schema mismatch

### Dependency errors

Examples:

- timeout
- connection refused
- service unavailable
- partial dependency degradation

### Unexpected exceptions

Examples:

- unhandled code path
- serialization failure
- null or missing data
- bad config assumptions

### Degraded and fallback errors

Examples:

- breaker open
- draft fallback created
- retry exhausted
- fallback model or path selected

## 3. Browser And F12 Debugging

Frontend debugging should include DevTools-level testing, not only unit tests.

### Console errors

Check for:

- JS runtime exceptions
- React rendering issues
- hydration mismatches
- unhandled promise rejections

### Network errors

Check for:

- failed API requests
- wrong status code handling
- CORS issues
- timeout behavior
- bad error-envelope parsing

### Performance and UX issues

Check for:

- slow pages
- failed chunk loads
- excessive re-renders
- layout shifts
- accessibility warnings

## 4. API Error Testing

API testing should cover the full status and contract surface.

### Important categories

- `400` invalid payload
- `401` unauthenticated
- `403` unauthorized
- `404` missing resource
- `409` conflict
- `422` validation failure
- `429` rate limit
- `500` internal error
- `502` or `503` downstream unavailable

### What to verify

- stable error envelope
- machine-readable error code
- correlation ID propagation
- no internal secret leakage
- correct mapping of domain errors to HTTP semantics

## 5. Routing Error Testing

Routing needs both frontend and backend coverage.

### Frontend routing

- wrong page path
- broken navigation link
- route-level error boundary behavior
- auth-guard behavior
- mobile navigation behavior

### Backend and gateway routing

- wrong service target
- missing route registration
- path and query param validation
- tenant-scoping mistakes
- namespace or tool misrouting

## 6. Deep Testing Areas For AI Systems

AI systems need more than normal API testing.

### Retrieval and generation

- retrieval quality regression
- prompt regression
- unsupported answer behavior
- citation correctness
- empty-context behavior

### Tool and workflow execution

- correct tool selection
- denied tool path
- degraded fallback
- replay after recovery
- audit correctness

### Governance and safety

- PII masking
- guardrail firing
- policy denial
- actor attribution truthfulness
- tenant isolation

## 7. Frontend Deep Testing

High-value frontend testing areas:

- initial load state
- loading and retry state
- empty state
- failed request state
- mobile layout
- keyboard accessibility
- admin and operator workflow usability
- broken-link coverage

## 8. Backend Deep Testing

High-value backend testing areas:

- route to service to store correctness
- transaction behavior
- conditional update correctness
- idempotency
- retry behavior
- timeout handling
- correlation propagation
- audit write behavior
- config and feature-flag behavior

## 9. Best Testing Order

Use this order:

1. unit tests
2. integration tests
3. contract tests
4. frontend error-state tests
5. worker and degraded-path tests
6. drill or chaos tests
7. load and security tests

## 10. Strong Testing Principles

- test failure behavior, not only happy path
- make error states visible and intentional
- convert real bugs into regression tests
- treat browser DevTools findings as real test signal
- make degraded and recovery paths first-class
- keep contracts stable and explicit

## 11. Senior Debugging Mindset

A strong engineer asks:

- where did the failure first become visible?
- is this a code bug, contract bug, routing bug, or state bug?
- can the operator explain this from traces, logs, and UI?
- do we have a regression test for this class of failure?
- if the dependency is down, does the system fail honestly?
