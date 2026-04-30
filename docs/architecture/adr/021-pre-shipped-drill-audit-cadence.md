# ADR-021: Pre-shipped drill-audit cadence (the inverted-cadence pattern)

## Status

Accepted — observed three times in succession (G-3, G-4, G-5) on
2026-04-29/30. ADR-020 named the SLO ("≤2 iterations after
parallel-tool commit"); this ADR names the *fastest* pattern
that operationalizes it: ship the audit before the source.

## Context

ADR-020 (Phase 7F, `3b1cc02`) declared:

> Every parallel-tool-authored commit landing in main MUST trigger
> an autonomous-loop drill audit within ≤2 autonomous-loop
> iterations.

The text assumed the natural cadence is: parallel-tool ships
source → autonomous-loop ships audit. Phase 7Q's cadence drill
measures iteration-latency between them. Phase 7Z tightened
MAX_AUDIT_LATENCY from 2 to 1 after observing in-SLO entries
clustered at 0 — concrete evidence the bound was looser than
reality required.

What ADR-020's text did NOT anticipate:

  * G-3 (`45633d2`, scripts/* help-contract paydown):
    `drill_scripts_have_help` predates G-3 by months. Latency=0
    because audit-add-time predates pt-commit-time.
  * G-4 (`480dd3e`, agentic control plane, +1793 LOC):
    8 audit drills (project-plan, task-run, approval, memory,
    control-plane api/chain/ui, admin-summary) shipped in Phases
    7N/7P/7R/7S BEFORE the parallel-tool's source code in G-4.
    Latency=0; time-latency=-0.2h.
  * G-5 (`dde309b`, sidecar event rating surface):
    `drill_sidecar_advisor_record_rating` shipped in the same
    commit as `Advisor.record_rating`. Latency=0; time-latency=
    +0.0h (truly simultaneous).

The pattern is now strong enough to lift from "we keep doing this"
to "this is our preferred cadence."

## Decision

**The autonomous loop SHOULD pre-ship audit drills when the
parallel-tool's intent is visible.** Source-then-audit is still
the SLO floor; audit-then-source is the target steady-state.

Concretely, when any of these signals appear:

1. Parallel-tool drops new drill files in `mcp/tests/` whose
   imports reference paths that don't yet exist (e.g. importing
   from `services/agent-orchestrator-svc/app/X.py` before X.py
   is committed).
2. Operator narrates upcoming parallel-tool work ("they're
   shipping the agentic control plane next").
3. Worktree shows new directories under `services/` with
   placeholder files but no commit yet.
4. NEXT_POLICY's pending menu lists a parallel-tool-owned item.

The autonomous-loop's next 1-2 iterations SHOULD ship the
corresponding audit drills BEFORE the parallel-tool's source
commit lands. When the source commit then lands, the cadence
drill records iteration-latency=0 and time-latency≤0
(preexisting / inverted).

## Mechanics

### How the cadence drill records inverted cadence

`drill_adr020_audit_cadence`'s latency formula:

```
add_sha = git log --diff-filter=A --pretty=%H -1 -- <audit_drill>
iteration_latency = git rev-list --count <pt_sha>..<add_sha>
time_latency_h    = (commit_time(add_sha) - commit_time(pt_sha)) / 3600
```

When the audit was added BEFORE the parallel-tool commit:

  * `<pt_sha>..<add_sha>` is empty (add_sha isn't a descendant
    of pt_sha) → iteration-latency = 0 (preexisting).
  * `add_sha`'s commit-time predates `pt_sha`'s →
    time-latency is NEGATIVE.

Both metrics record the inverted state honestly. Phase 7U added
the time-latency metric specifically to surface this — iteration-
latency alone says "0 = preexisting OR simultaneous," but
time-latency disambiguates.

### Drills tagged `# RESOURCES: readonly` enable inverted cadence

Pre-shipped audits work best when they exercise the source code
*structurally* (file existence, schema shape, regex patterns)
without requiring the source code to actually run. Tier-1
readonly drills satisfy this constraint by design — they don't
need Postgres, MCP, or running services.

A drill tagged `# RESOURCES: pg` can't be pre-shipped because
its target backend doesn't exist yet. That's fine — those drills
ship at source-then-audit cadence (latency ≤ MAX_AUDIT_LATENCY).

### When inverted cadence is NOT appropriate

  * Behavioral / runtime drills that exercise live services.
  * Drills whose assertions depend on the parallel-tool's
    *implementation* choices (which can shift before source
    lands).
  * Drills covering APIs that aren't yet contractually frozen.

In those cases, the audit drill ships AFTER the source commit
lands, within MAX_AUDIT_LATENCY=1 iteration.

## Consequences

### Positive

* **Fastest possible cadence.** Source-and-audit land
  simultaneously (or audit slightly earlier); operators verify
  behavior immediately on G-bucket landing without paydown lag.
* **Drill-driven design.** Pre-shipping the audit forces the
  autonomous-loop to articulate the structural contract before
  the parallel-tool commits — surfaces ambiguities early.
* **avg-iter-latency trends downward.** Each in-SLO entry at
  latency=0 lowers the average. Session 2026-04-30: 6.3 → 4.8 → 3.8.
* **Threshold can tighten.** Phase 7Z dropped MAX_AUDIT_LATENCY
  from 2 to 1 specifically because inverted-cadence entries
  proved the bound was loose.

### Negative

* **Audit may diverge from source.** If parallel-tool's
  implementation shifts after the audit ships, the drill fails
  on landing. Drill must be structural enough to survive
  reasonable variation; otherwise it's a forward-looking-check
  per ADR-017.
* **Audit imports may reference future paths.** If pre-shipped
  drill imports `services/X/app/Y.py` and `Y.py` doesn't exist,
  Python import fails with `ModuleNotFoundError`. The drill
  must use AST-based source inspection (read text + parse) or
  graceful degradation (per ADR-019), not import-time loading.
* **Tier-1-only constraint.** Inverted cadence only works for
  readonly drills. mcp_*/pg/etc. drills follow source-then-
  audit cadence.

### Risks accepted

* Audit may not catch all regressions if structural assertions
  miss runtime behavior. Mitigation: tier-2 drills at
  source-then-audit cadence cover behavioral surfaces; tier-1
  inverted cadence covers structural surfaces. Both layers.
* Operator may pre-ship audits speculatively, then parallel-
  tool changes direction. Mitigation: drills are reversible
  (delete the file). Sunk cost is one drill iteration.

## Alternatives considered

1. **Strict source-then-audit (ADR-020 text as written)**:
   audit follows source within ≤2 iterations. Rejected as
   default because we have empirical evidence the inverted
   pattern is faster and lossless.
2. **No audit until source lands**: rejected because it
   reverts to ADR-020's pre-existing problem (audit gap window
   where the parallel-tool commit is in main without
   verification).
3. **Audit-only mode (no source)**: not applicable — source
   eventually lands; the audit is paired with it.

## Drills that enforce / measure this ADR

* `drill_adr020_audit_cadence` — measures iteration-latency
  AND time-latency per registry entry. Inverted-cadence shows
  as iteration-latency=0 AND time-latency<0. Phase 7U added
  the time-latency dimension specifically.
* `drill_drill_status_freshness` — catalog-membership step
  (Phase 7FF) catches stale per_drill keys when audit drills
  shift around inverted-cadence iterations.

## How operators check this ADR is being followed

```bash
# Run the cadence drill — output shows inverted entries
python mcp/tests/drill_adr020_audit_cadence.py

# Look for entries with time-latency NEGATIVE:
#   AUDITED [✓ lat=0   -4.7h] 45633d2  ...   <- inverted (G-3)
#   AUDITED [✓ lat=0   -0.2h] 480dd3e  ...   <- inverted (G-4)
#   AUDITED [✓ lat=0   +0.0h] dde309b  ...   <- simultaneous (G-5)

# Summary line at step 9:
#   Wall-clock: avg-time-latency=+3.6h;
#               inverted (audit pre-shipped)=2,
#               same-day=3
```

A healthy ADR-021 implementation: `inverted (audit pre-shipped)`
count grows with future G-buckets. If it stays flat while G-N
counts grow, the loop has reverted to source-then-audit and
ADR-020 is doing the work alone.

## References

* ADR-014 — Autonomous loop architecture (advisory contract)
* ADR-015 — Ratchet pattern (threshold shrinkage applies here)
* ADR-016 — Parallel-agent allocation
* ADR-017 — Forward-looking checks + sweep-before-commit
* ADR-018 — Three-way work allocation (operator / parallel-tool /
  autonomous-loop)
* ADR-019 — Graceful degradation (AST-based source inspection
  pattern this ADR depends on)
* ADR-020 — Parallel-tool commit drill audit (SLO this ADR's
  pattern beats)
* §43 — Drill testing pattern
* §44 — Autonomous feature loop
* Phase 7Q — Cadence drill (latency measurement infrastructure)
* Phase 7U — Wall-clock time-latency
* Phase 7Z — MAX_AUDIT_LATENCY tightened 2 → 1 based on inverted
  cadence evidence
* G-3 (`45633d2`) — first observed inverted (preexisting drill)
* G-4 (`480dd3e`) — first deliberate inverted (8 audits pre-
  shipped via Phases 7N/7P/7R/7S)
* G-5 (`dde309b`) — first simultaneous (audit + source same
  commit, latency=0)
