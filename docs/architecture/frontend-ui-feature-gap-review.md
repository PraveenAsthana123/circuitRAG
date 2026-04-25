# Frontend UI Feature Gap Review

This document captures the current frontend UI gaps based on a code-level review of the `services/frontend` application.

The goal is to identify:

- what the UI already does well enough
- what is missing by feature
- where the current experience is still demo-grade instead of product-grade
- what should be fixed first

This is a code review of the frontend surface, not a browser screenshot review.

## 1. Overall assessment

The frontend is no longer a placeholder.

It now has:

- a responsive shell
- working core screens
- an operator dashboard
- client-error reporting
- structured navigation

However, several important areas are still incomplete from a product perspective:

- the document-management flow is shallow
- client-side observability is only partial
- core workflows stop too early after success
- some operator flows are read-only when they should become actionable

## 2. Feature-by-feature review

## Ask

### What is present
- question input
- retrieval strategy selector
- top-k selector
- answer rendering
- citation list
- debug payload
- run summary

### What is missing
- history of previous asks
- reset/clear action
- cancel action while waiting
- clickable citation drill-down
- document jump from citation to source view
- follow-on action from answer
- richer empty and error-state guidance

### Current maturity
- useful demo surface
- not yet a complete knowledge workflow

## Upload

### What is present
- file picker
- accepted file types
- async vs sync upload toggle
- selected file summary
- result state and message

### What is missing
- drag-and-drop upload
- progress indicator
- file validation feedback before submit
- post-upload navigation to document detail
- reset/replace-file affordance after success
- richer status timeline for async pipeline progress

### Current maturity
- functional ingestion entrypoint
- still feels like a basic form, not a full upload workflow

## Documents

### What is present
- list fetch
- search by filename
- state filter
- summary cards
- refresh action

### What is missing
- pagination or infinite scroll
- sorting
- row click / detail drill-down
- chunk inspection
- metadata detail view
- retry/delete/archive actions
- visible correlation between document state and ingestion health

### Highest-risk gap
The page hardcodes a fetch limit of 100. That makes the UI incomplete and misleading once the corpus grows beyond that size.

### Current maturity
- useful read-only list
- not yet a real document management surface

## Admin dashboard

### What is present
- health overview
- breaker state
- tool stats
- prompt registry
- upstream health
- trace lookup
- client-error screen as separate route

### What is missing
- operator actions beyond trace lookup
- explicit replay/admin remediation links
- draft backlog controls if/when supported
- release/regression views
- per-feature incident drill-down
- stronger dashboard-to-action workflow

### Current maturity
- credible operational read surface
- not yet a full operator console

## Client errors / F12 capture

### What is present
- global error reporter
- window error capture
- unhandled rejection capture
- admin screen for recent client errors

### What is missing
- explicit network/API failure telemetry
- route-transition failure capture
- chunk-load failure capture
- browser-side performance telemetry
- release-tagged regression tracking
- session breadcrumbs
- active component-boundary reporting

### Important limitation
The current implementation is not full "F12 capture". It captures part of the same problem space, mainly runtime exceptions.

### Current maturity
- useful first observability layer
- not yet full client observability

## Navigation and discoverability

### What is present
- grouped sidebar
- mobile drawer
- topbar admin shortcut

### What is missing
- search inside large tool catalogs
- prioritization of high-value screens
- collapse or personalization for very large nav sets
- stronger distinction between product screens and knowledge/catalog screens

### Current maturity
- workable
- beginning to feel crowded

## Error and fallback UI

### What is present
- route-level `app/error.tsx`
- custom error boundary component
- inline API error display on core pages

### What is missing
- actual mounted per-page/component error boundaries
- richer retry guidance
- consistent fallback patterns across screens
- user-facing support/debug info on failed actions

### Important gap
The custom `ErrorBoundary` component exists but is not mounted, so a declared part of the error-handling story is not actually active.

## 3. Main gaps

The highest-signal frontend gaps are:

1. document-management flow depth
2. partial client/F12 observability
3. shallow post-success flows in Ask and Upload
4. mostly read-only operator dashboard
5. increasingly crowded navigation

## 4. What is strongest already

The strongest parts of the UI today are:

- clear page framing
- improving visual consistency
- responsive shell
- useful operator telemetry surface
- central API client and shared error handling direction

## 5. Suggested fix order

### Priority 1
- finish Documents as a real management flow
- add pagination, sorting, row drill-down, and detail view

### Priority 2
- expand client observability beyond runtime exceptions
- include frontend API failures and route-level telemetry

### Priority 3
- improve Ask and Upload as multi-step workflows
- add citation drill-down, upload follow-through, and next actions

### Priority 4
- make admin more actionable
- connect operational insight to recovery actions where backend supports them

### Priority 5
- improve navigation and information architecture
- especially for tool/catalog pages

## 6. Practical next tasks

Good next implementation tasks:

- add document detail page
- add row click from documents list
- add client API failure telemetry
- wire and use real error boundaries
- add upload success CTA to view the uploaded document
- add citation-to-document navigation
- add document paging controls

## 7. Bottom line

The frontend has moved past being a placeholder, but the most important product and operator flows are still incomplete.

The biggest gap is not visual polish.

It is workflow depth:

- list without drill-down
- answer without follow-through
- upload without lifecycle visibility
- observability without full frontend coverage
- admin insight without enough action paths
