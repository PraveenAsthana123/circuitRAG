# Draft Replay Refactor Plan

This note turns the current draft replay discussion into a concrete,
incremental refactor plan for the DocuMind replay/resolve subsystem.

It is intentionally practical:

- identify the real subsystem
- define the invariants first
- choose cleaner boundaries
- migrate incrementally
- strengthen tests and observability alongside the refactor

---

## Problem statement

The current draft replay behavior is spread across several layers:

- route/admin resolve flow
- worker replay flow
- MCP client replay mechanics
- draft store persistence
- audit attribution

That creates a few recurring risks:

- route and worker semantics can drift
- replay policy is not owned by one clear workflow layer
- state transition safety is weaker than it should be
- audit attribution and replay semantics are coupled in awkward ways
- tests and drills can validate adjacent paths rather than the true
  production workflow path

This means draft replay is already a workflow subsystem, even if some of
the code still looks like helper-style orchestration.

---

## Target outcome

Refactor the subsystem so that:

- route layer handles HTTP/auth/error mapping only
- worker layer handles scheduling, scan, backoff, and stats only
- one workflow/service layer owns replay semantics
- store layer owns guarded persistence transitions
- client layer owns downstream tool-call mechanics
- audit remains a shared mechanism, not the owner of workflow policy

This should reduce drift, clarify ownership, and make tests more
truthful.

---

## Key files in scope

- [mcp/client.py](/mnt/deepa/rag/mcp/client.py)
- [mcp/drafts.py](/mnt/deepa/rag/mcp/drafts.py)
- [services/inference-svc/app/routers/__init__.py](/mnt/deepa/rag/services/inference-svc/app/routers/__init__.py)
- [services/inference-svc/app/workers/draft_replay.py](/mnt/deepa/rag/services/inference-svc/app/workers/draft_replay.py)
- [libs/py/documind_core/audit.py](/mnt/deepa/rag/libs/py/documind_core/audit.py)

Potential related test/drill coverage:

- [mcp/tests/drill_audit_actor_type.py](/mnt/deepa/rag/mcp/tests/drill_audit_actor_type.py)
- existing replay/admin/worker drills

---

## Invariants

Write these down before changing structure.

1. Only `pending` drafts may transition to `replayed`.
2. A successful replay should persist replay state exactly once.
3. Route/admin and worker replay paths should share the same replay
   semantics.
4. Actor attribution must reflect actual execution context:
   operator, worker, or service.
5. Degraded replay must not silently corrupt or advance draft state.
6. Important replay and audit failures must be visible operationally.

If the refactor does not make these easier to point to, it is not yet
good enough.

---

## Current boundary problems

### Route layer is doing too much

The admin resolve route currently does more than transport concerns. It
knows enough about replay behavior that drift between route and worker is
possible.

### Worker layer risks becoming its own workflow owner

The replay worker should own scheduling and retry timing, not a parallel
copy of replay business semantics.

### Client owns too much replay meaning

`MCPClient.resolve_draft()` is a useful primitive, but the higher-level
meaning of replay legality, attribution policy, and final state handling
should not be spread implicitly between route, worker, client, and
audit.

### Store transition is too important to stay vague

Draft persistence is part of correctness, not just persistence plumbing.
If replay transitions are not guarded strongly enough in storage, races
and duplicate execution remain possible.

---

## Target layering

### Route layer

Responsibilities:

- authenticate and authorize caller
- gather request context
- call workflow/service
- map workflow result to HTTP response

Should not own:

- replay semantics
- state transition policy
- deep orchestration of audit + client + store behavior

### Workflow/service layer

Proposed conceptual owner:

- `DraftReplayService`
- or `DraftResolveWorkflow`

Responsibilities:

- load draft
- validate replay eligibility
- determine actor attribution semantics
- invoke downstream replay via client
- persist guarded success transition
- write audit with explicit context
- return structured replay outcome

This is the main architectural missing piece.

### Store layer

Responsibilities:

- fetch draft by ID
- list pending drafts
- persist guarded transition from pending to replayed

This layer should expose domain-meaningful persistence operations rather
than vague mutation helpers.

Example direction:

- `get_draft(...)`
- `list_pending_drafts(...)`
- `mark_replayed_if_pending(...)`

### Client layer

Responsibilities:

- downstream tool invocation
- degraded draft creation behavior
- breaker behavior
- idempotency key handling
- tool error/result envelope handling

Client should stay the owner of call mechanics, not the sole owner of
workflow policy.

### Shared mechanisms

Good shared mechanisms:

- audit writer primitive
- circuit breaker primitive
- common request/result envelopes

Bad shared extraction:

- service-specific replay policy
- operator/worker/business-specific rules hidden in low-level utilities

---

## Practical migration sequence

Do not rewrite the subsystem all at once.

### Step 1: characterization coverage

Before moving code, lock down current important behavior:

- replay success path
- already-not-pending path
- degraded replay path
- audit attribution path
- route/admin behavior
- worker behavior

This includes strengthening drills where they currently validate a
convenient path rather than the real one.

### Step 2: strengthen store transition semantics

Make replay persistence safer first.

Desired direction:

- guarded replay update only when status is `pending`
- explicit success/failure result from store transition
- conflict already visible for replayed/rejected cases

This reduces correctness risk before larger code movement.

### Step 3: introduce workflow/service seam

Add a new workflow/service callable that preserves current behavior but
gives replay semantics one clear home.

Do not try to make it perfect immediately. It just needs to centralize
the orchestration boundary.

### Step 4: move route to workflow

Route becomes thinner:

- auth and request context
- workflow call
- HTTP mapping

No semantic change intended.

### Step 5: move worker to workflow

Worker keeps:

- polling
- backoff
- namespace grouping
- skip-when-breaker-open decisions
- stats/logging

Worker stops owning its own version of replay business meaning.

### Step 6: delete duplicated replay branching

Once both route and worker use the workflow layer, remove old parallel
paths and keep one replay owner.

### Step 7: tighten attribution semantics

After behavior is centralized, improve:

- operator/worker/service attribution rules
- invalid identity handling
- audit visibility on attribution failures

This is safer after structure is clearer.

### Step 8: upgrade drill truthfulness

Update or replace drills so they hit the real worker path where the doc
claims worker behavior is being tested.

### Step 9: add operational signals

Add or tighten visibility for:

- replay conflicts
- audit write failures
- degraded replay outcomes
- attribution failures where relevant

---

## Test plan

Refactor safety depends on layered proof.

### Unit/integration level

Add or strengthen tests for:

- replay allowed only from `pending`
- replay conflict when already replayed/rejected
- actor context mapping rules
- workflow result shape
- store guarded update semantics

### Drill/workflow level

Need real-path verification for:

- operator/admin replay
- worker replay
- degraded replay leaves draft pending
- audit attribution reflects true execution context

Important note:

If a drill claims worker behavior, it should exercise the worker path,
not only a client shortcut that touches similar code.

---

## Observability expectations

After refactor, operators should be able to answer:

- did replay succeed, degrade, or conflict?
- which actor type executed the replay?
- did audit succeed or fail?
- is worker replay diverging from admin replay?
- are pending drafts accumulating because replay is blocked or degraded?

Minimum useful signals:

- replay success count
- replay conflict count
- degraded replay count
- audit failure count for replay actions
- worker replay stats and backlog visibility

---

## What not to do

Avoid these refactor mistakes:

- rewriting route, worker, client, and store in one PR
- mixing behavior change with structural cleanup without tests
- introducing a giant generic “workflow manager”
- hiding important storage semantics behind generic repository methods
- moving service-specific policy into shared low-level code
- keeping old and new replay paths both alive indefinitely

---

## Definition of done

The subsystem is in a better state when all of these are true:

1. One workflow/service layer owns replay semantics.
2. Route and worker no longer duplicate replay business logic.
3. Store transition to replayed is guarded and explicit.
4. Actor attribution policy is clearer and easier to test.
5. Drill coverage validates the real worker/admin paths.
6. Replay conflicts and audit failures are operationally visible.
7. Old duplicated logic has been removed.

---

## Final check questions

After the refactor, these questions should have fast, concrete answers:

1. Where is replay legality decided?
2. Where is replay state transition guarded?
3. Where is actor attribution decided?
4. What is different between admin and worker paths, and why?
5. What test proves the real worker path?
6. What metric or log tells us replay/audit is going wrong?

If those answers are still fuzzy, the refactor is incomplete.
