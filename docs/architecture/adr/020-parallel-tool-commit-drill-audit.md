# ADR-020: Parallel-tool-authored commits require autonomous-loop drill audit

## Status

Accepted — observed across G-1 / G-2 / G-3 commits in the
2026-04-28 → 2026-04-29 session. Pattern crystallised when Phase
7E (`9a8d137`) closed a §43 gap on commit `5dfeb9c` (G-1,
parallel-tool-authored, 25 files / 2120 insertions, zero drills)
two days after the original commit landed.

## Context

ADR-018 names three actors (operator / parallel content-stream
tool / autonomous loop). §43 requires every code commit to ship a
drill with at least one negative assertion. The autonomous loop
self-enforces §43 because it always runs the readonly sweep
before committing and reports the drill score in the commit
message. Parallel-tool commits are different:

* The parallel-tool's review surface is internal to that tool's
  process. It may run its own tests, but those tests don't land
  in `mcp/tests/drill_*.py` and don't show up in the autonomous-
  loop's scoreboard.
* Parallel-tool conventions may diverge from the project's. G-1
  shipped `langgraph` and `langchain-core` unpinned in
  `requirements.txt` (CLAUDE.md §13.12 says pin every dep). A
  drill would have caught both at commit time.
* By the time the autonomous loop sees the parallel-tool's
  commit, it's already in `main`. The §43 gate that fires
  pre-commit on autonomous-loop iterations cannot retroactively
  block a parallel-tool commit.

The risk: parallel-tool ships a feature, autonomous loop never
audits it, the §43 contract holds for ~70% of the codebase
(autonomous-loop authorship) and silently breaks for the rest.
ADR-018 grants parallel-tool full sign-off authority for what it
authors; that grant is real, but it does NOT include a sign-off
for §43 discipline.

Concretely from this session:

| Commit | Surface | Drill at commit | Drill at audit |
|---|---|---|---|
| `5dfeb9c` G-1 | agent-orchestrator-svc (25 files) | 0 | drill_agent_orchestrator_structure (Phase 7E, 2 days later) |
| `51bac70` G-2 | services/frontend/* (31 files) | 0 (autonomous-loop scope) | audit_frontend_link.py + audit_frontend_template_coverage.py (Phase 6K, retroactive) |
| `45633d2` G-3 | scripts/* (12 files) | drill_scripts_have_help (existing) | drill_scripts_have_help still gated; drift on sidecar_bootstrap.sh found via Phase 7B |

Three for three: every parallel-tool commit needed an autonomous-
loop audit pass to bring it back to §43 compliance.

## Decision

**The autonomous loop MUST run a drill-audit pass within ≤2
iterations after any parallel-tool-authored commit lands on
`main`.** The audit checks four things:

1. **Drill existence**: a drill in `mcp/tests/drill_*.py` exists
   that exercises the new code. "Exercises" means at least one
   step of the drill reads or imports the new file(s); not just
   touches the directory.
2. **Negative assertion**: the drill ships at least one
   "NEGATIVE: ..." step (per `drill_drill_catalog_discipline`).
   Happy-path-only drills are forward-looking-check anti-pattern
   territory (per ADR-017); they pass while the next regression
   silently lands.
3. **Convention compliance**: the drill follows project
   convention — `# RESOURCES: <tag>` header, `ALL N STEPS PASSED`
   banner (so `run_drills.py` recognises success), NEGATIVE-marker
   docstring breakdown.
4. **Project-rule audit**: the new code itself is checked
   against CLAUDE.md non-negotiables — no hardcoded URLs (§3),
   pinned deps (§13.12), parameterized SQL (§14.5), no f-string
   in SQL, etc. The audit is at the structural level (AST
   inspection / regex grep on source); behavioural checks belong
   in resourced-tier drills.

When the audit fails, the autonomous loop's next iteration
ships the missing drill and any required code fix. The audit
is a **paydown ratchet** in ADR-015 terms: the floor is the
current count of unaudited parallel-tool commits, paid down to
zero per iteration.

## Why two iterations and not one

A one-iteration constraint forces the autonomous loop to drop
its current work the moment a parallel-tool commit lands. That
churns the loop's own iteration cadence (per the ADR-016
parallel-agent allocation). Two iterations gives:

* Iteration N: complete current work
* Iteration N+1: drill-audit the parallel-tool commit

This honors §44.2 ("ONE thing per iteration") without letting
the audit gap exceed ~2 iterations of latency.

## Consequences

### Positive

* §43 discipline holds across all three authorship paths
  (operator / parallel-tool / autonomous-loop), not just two.
* Project-rule violations from parallel-tool authorship surface
  fast (≤2 iterations).
* The audit pattern is itself a reusable iteration template:
  drill stub for "this surface exists", paydown via project-rule
  audit, ratchet floor moves toward zero.

### Negative

* Extra autonomous-loop work after every parallel-tool batch.
  If parallel-tool ships at higher cadence than the loop, the
  audit queue fills and the 2-iteration constraint is missed.
* The audit cannot retroactively block bad commits. If
  parallel-tool ships an SQL injection in a service the
  autonomous loop hasn't gotten to yet, the bug is in `main`
  for ≤2 iterations.
* Parallel-tool may interpret the audit as a quality complaint
  about its work. ADR-018's three-way allocation makes clear
  that §43 is the project's contract, not a per-actor judgment.

### Risks accepted

* Parallel-tool continues to ship without drills. The
  autonomous loop catches up. This is faster and less friction-
  inducing than gating parallel-tool commits at the source.
* Audit may miss novel project-rule violations not yet in the
  CLAUDE.md non-negotiable list. The §43 drill catches the
  *known* shape; new rules ship as autonomous-loop drills first
  and propagate to the audit checklist later.

## Alternatives considered

1. **Pre-commit hook for parallel-tool**: would force §43 at
   commit time. Rejected because (a) parallel-tool's process is
   external; we can't reliably wire its hook chain; (b) the
   autonomous loop's strength is post-hoc paydown, not
   pre-commit gating across actor boundaries.
2. **Autonomous loop reviews every parallel-tool PR before
   merge**: makes the autonomous loop a serial reviewer for
   every parallel-tool PR. Rejected because it kills the
   parallel-agent allocation benefit (ADR-016).
3. **Drop §43 for parallel-tool commits**: would let
   parallel-tool ship under its own contract. Rejected because
   the project's discipline is one contract; ADR-018 names the
   actors, not separate contracts per actor.

## Drills that enforce this ADR

* `drill_drill_catalog_discipline` (meta-drill) — every drill
  has step-count + negative-marker docstring breakdown. Catches
  parallel-tool drills that skip conventions.
* `drill_docstring_cohesion` — drill output banners match
  `RESULT_RE` so the runner recognises success.
* `drill_agent_orchestrator_structure` (Phase 7E) — first
  example of an audit drill landing two days after the source
  commit. Future audits should follow the same shape.

## How operators check this ADR is being followed

```bash
# Pages without compose footer = release blocker (per §49)
# Drills without NEGATIVE marker = release blocker (per §43)
# Parallel-tool commits without audit drill = use this ADR

# Find recent commits authored by non-Claude:
git log --since="7 days ago" --pretty="%h %s" |
  grep -v "Co-Authored-By: Claude"

# For each, check if a drill exists that imports/reads from
# the touched paths:
git show --stat <commit_sha> |
  awk '/[+-]/ {print $1}' |
  while read path; do
    grep -l "$path" mcp/tests/drill_*.py 2>/dev/null || \
      echo "UNAUDITED: $path"
  done
```

## References

* ADR-016 — Parallel-agent allocation for independent n-file work
* ADR-017 — Forward-looking checks + sweep-before-commit
* ADR-018 — Three-way work allocation
* ADR-019 — Graceful degradation of loop tooling
* §43 — Drill testing pattern
* §44 — Autonomous feature loop
* CLAUDE.md §13.12 — Pin dependency versions
* CLAUDE.md §14.5 — Input validation at boundaries
* Phase 7E commit `9a8d137` — first audit landing
