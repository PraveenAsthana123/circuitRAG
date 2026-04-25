# Frontend Chunk-Load Incident Report

This document captures the phase-by-phase analysis of the frontend incident where the browser showed:

- `Application error: a client-side exception has occurred`
- `ChunkLoadError: Loading chunk ... failed`
- `Failed to load resource ... 400`

## 1. Incident summary

The visible browser symptom initially looked like a generic client-side React failure.

The actual root cause was different:

- a stale Next.js frontend process was still bound to port `3000`
- it served HTML referencing an old build's chunk names
- the browser requested a chunk that did not belong to the current build on disk
- the chunk failed to load
- React then failed during hydration/runtime because required route code was missing

## 2. Phase-by-phase analysis

## Phase 1: source and build

Status:
- healthy

Evidence:
- `npm run build` completed successfully
- `/tools/rag-scenarios` was generated during static page build

Meaning:
- no source compile error
- no TypeScript error
- no build-time page failure

## Phase 2: artifact generation

Status:
- healthy current artifact
- mismatch with served artifact

Evidence:
- current build contained:
  - `/_next/static/chunks/app/tools/rag-scenarios/page-fa128454fa93e372.js`
- browser attempted to load:
  - `/_next/static/chunks/app/tools/rag-scenarios/page-d5f1edb0abe3b16e.js`

Meaning:
- the browser HTML and the current build output were from different frontend build states

## Phase 3: server process/runtime

Status:
- broken

Evidence:
- two `next-server` processes existed under `services/frontend`
- the process actually listening on `:3000` was an older stale process

Meaning:
- the running frontend process was stale
- the current build on disk was not what the browser was being served

## Phase 4: asset delivery

Status:
- broken

Evidence:
- request for the old chunk path failed
- request for the current chunk path succeeded once the correct process was running

Meaning:
- this was a chunk/version mismatch incident
- not a normal route logic defect

## Phase 5: browser runtime and hydration

Status:
- broken as a downstream effect

Evidence:
- browser logged `ChunkLoadError`
- browser then logged minified React error `#423`

Meaning:
- React failed because the route chunk did not load
- the React error was secondary, not primary

## Phase 6: route logic

Status:
- not primary cause

Evidence:
- `/tools/rag-scenarios` built successfully
- the page code existed in the generated artifact

Meaning:
- the route implementation was not the first failing phase

## Phase 7: API and backend

Status:
- not primary cause

Evidence:
- failure occurred at static chunk loading time
- no backend request was needed to trigger the initial crash

Meaning:
- this was not a gateway or service API defect

## Phase 8: observability

Status:
- initially weak
- improved during mitigation

Originally:
- generic app error did not identify the chunk mismatch clearly

Added during mitigation:
- mounted app-wide React error boundary
- root-level `global-error` handler
- client error reporting for React boundary and global errors
- build/deploy identity surface in admin

Meaning:
- future incidents of this type should be easier to identify and triage

## 3. Root cause

Primary root cause:

- stale Next.js frontend process serving old HTML/chunk references

Secondary effect:

- browser chunk load failure
- React hydration/runtime failure

## 4. Mitigations implemented

### Implemented
- mounted `ErrorBoundary` around the app shell
- added `global-error.tsx`
- wired `react_boundary` reporting
- added chunk-load auto-reload recovery in the client error reporter
- added frontend build/deploy ID panel in admin

### Operational fix
- stale frontend process on port `3000` was identified and replaced with the current build

## 5. Preventive actions

Recommended:

1. run the frontend under a single supervised process manager
2. ensure deploy replaces the old process instead of leaving a stale one bound to the port
3. expose build ID in UI and operator tools
4. auto-recover once on chunk-load mismatch
5. keep client error reporting active for root-level failures

## 6. Bottom line

This was not primarily a code bug in `/tools/rag-scenarios`.

It was a deployment/runtime consistency bug:

- stale process
- mismatched chunk references
- browser chunk failure
- React crash as downstream symptom
