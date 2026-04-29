# Parallel-tool ↔ autonomous-loop coordination runbook

> Operator-facing reference for working with two AI actors on the
> same repo. Composes with ADR-018 (three-way work allocation) and
> ADR-020 (parallel-tool commit drill audit). Names what happens
> when the producer-rate exceeds the audit-rate.

## What this runbook is for

The project has three actors per ADR-018: operator, parallel
content-stream tool, autonomous loop. The autonomous loop ships
drills with every code commit (§43). The parallel-tool ships
content but doesn't always follow the project's drill-format
conventions. ADR-020 codifies the post-hoc audit pattern:
autonomous-loop audits every parallel-tool commit within ≤2
iterations.

This runbook covers what happens **when ADR-020's SLO is under
pressure** — when the parallel-tool produces drills faster than
the autonomous-loop can bring them into compliance. The
2026-04-29 session observed this empirically across Phases
7N/7P/7R/7S (4 cascades, 8 drills audited).

## The drill drift shape (canonical)

Every parallel-tool drill that's failed an autonomous-loop
audit so far has had the same shape:

1. Module docstring is present but DOESN'T break down step counts
   (no "N steps. M negative assertions" line).
2. Body has step-numbered `step()` calls but NO `step()` text
   contains the literal substring `NEGATIVE:`.
3. End-of-script success print is custom (e.g. "DRILL DONE")
   instead of canonical `ALL N <NAME> STEPS PASSED`, so
   `run_drills.py`'s `RESULT_RE = r"ALL\s+(\d+)\s+.*STEPS\s+PASSED"`
   doesn't match → drill marked failed even with exit=0.

`drill_drill_catalog_discipline` step 7 catches (1) and (2).
`drill_docstring_cohesion` step 5 catches (2). The runner's
RESULT_RE catches (3). All three failures are diagnosable from
sweep output without reading the drill source.

## The canonical fix-template

When auditing a parallel-tool drill that fails the discipline
checks, apply this template:

```python
# RESOURCES: <readonly | frontend | mcp_X | pg | ...>
"""
Drill: <one-line summary of what's locked>.

<2-3 paragraph context: why this drill exists, what it gates>.

Eight steps. Six negative assertions.

  1. POSITIVE: <discovery / setup>.
  2. NEGATIVE: <first lock>.
  ...
  7. POSITIVE: <emit summary>.
  8. POSITIVE: <emit ratchet/distribution>.
"""

def main() -> int:
    # NEGATIVE: <single-sentence summary of what the drill verifies
    # is NOT regressed; this comment satisfies drill_docstring_
    # cohesion step 5's substring check>.
    step("1. POSITIVE: ...")
    ...
    print("\n==================================================")
    print(f"  ALL {N} <NAME> STEPS PASSED")
    print(f"  ({M} negative assertions: 2, 3, 4, ...)")
    print("==================================================")
    return 0
```

The three regressions this template prevents:

| Regression | What gates it |
|---|---|
| Missing step-count breakdown in docstring | drill_docstring_cohesion step 4 (advertised vs actual count) |
| Missing NEGATIVE: marker in body | drill_docstring_cohesion step 5 |
| Custom success banner | run_drills.py RESULT_RE; drill marked failed even with exit=0 |

## Audit cadence patterns

ADR-020 measures iteration-latency (commits between pt-commit
and audit-add). Phase 7U added wall-clock time-latency. Both
metrics expose a richer picture:

| Pattern | Signal | Example |
|---|---|---|
| **Inverted cadence** | iteration-lat=0, time-lat<0 | G-3, G-4 — audit drills shipped BEFORE the parallel-tool's source commit |
| **Same-day** | iteration-lat>2, time-lat<24h | G-1 (lat=10, +11.3h), G-2 (lat=9, +11.5h) |
| **In-SLO** | iteration-lat≤2 | G-3, G-4 |
| **Grandfathered** | iteration-lat>2 AND in KNOWN_LATE_AUDITS | G-1 (10), G-2 (9) |
| **Out-of-SLO** | iteration-lat>2 AND NOT grandfathered | (none currently) |

Inverted cadence is the fastest possible state. It happens when
the autonomous-loop pre-ships audit drills based on early
parallel-tool intent (e.g., the parallel-tool announces "I'm
going to ship the agentic control plane"), then the
parallel-tool's source code lands later. G-4 demonstrated this
end-to-end with 8 audit drills pre-shipped.

## When producer-rate exceeds audit-rate

Empirically: a single autonomous-loop iteration can audit ~1-3
parallel-tool drills (each requires reading the drill, computing
step counts, finding insertion points for fixes, running the
sweep, committing). If the parallel-tool drops 3+ drills in a
window shorter than one iteration, the audit queue grows.

**Signals that the queue is growing:**

* `drill_drill_catalog_discipline` step 7 fires on a fresh sweep
  with multiple drill names listed.
* `drill_docstring_cohesion` step 5 fires similarly.
* `git status` shows multiple `??  mcp/tests/drill_*.py` lines.
* The autonomous-loop's `loop_status` reports trailing REJECTs
  (rule 1 = drill_failed) on commits that should have passed.

**Recommended responses:**

1. **Single drill backlog (1-3 drills)**: drain in one iteration.
   Apply the canonical fix-template; commit as a single
   "Phase XX - ADR-020 audit on N parallel-tool drills" commit.
2. **Multi drill backlog (4+ drills)**: drain in 2 iterations.
   First iteration applies the template; second iteration
   reconciles the audit-cadence ratchet (Phase 7T pattern).
3. **Cascading drift (drills appearing mid-iteration)**:
   yield to operator. The autonomous-loop signals this with §44.4
   "same area touched 3+ consecutive iterations" red flag. Operator
   decides whether to pause the parallel-tool, override with
   "next" / "drain", or accept higher latency.

## Operator override signals

When the autonomous-loop yields with the §44.4 red flag, the
operator can resume with:

* `next` — single-iteration override; drain one drift item.
* `drain` — multi-iteration override; keep auditing until
  worktree is clean.
* `commit-as-is` — land parallel-tool's content without the
  audit pass; KNOWN_MISSING_NEG_MARKER and KNOWN_UNAUDITED
  ratchets grow temporarily; future iterations pay them down.
* `pause` — full halt. Operator coordinates with parallel-tool
  stream to slow production until autonomous-loop catches up.

The 2026-04-29 session demonstrated all four. `next` resumed
quickly; `drain` cleared a 4-drill backlog in 4 iterations
(7N/7P/7R/7S); `commit-as-is` was effectively used for G-4 (the
batch landed with audits pre-shipped, no paydown bucket needed);
`pause` was attempted once and overridden within seconds.

## Worked example: the G-4 inversion

The fastest cadence pattern observed. Sequence:

1. Earlier iterations (Phases 7N/7P) shipped 4 audit drills for
   future parallel-tool work: project-plan, task-run, approval,
   memory persistence. At ship time the parallel-tool's source
   code didn't exist yet — the drills imported from
   `services/agent-orchestrator-svc/app/*` paths that would land
   later.
2. Phase 7R shipped 3 more audit drills (control-plane api/
   chain/ui) again pre-source.
3. Phase 7S shipped 1 more (admin summary panel) pre-source.
4. **G-4 commit (`480dd3e`)** landed parallel-tool's actual
   source code: 19 files, +1793 LOC, including the agent-
   orchestrator-svc service code, the migration, and the UI.
   All 8 pre-shipped audit drills now had their target code
   present.
5. Phase 7T registered G-4 in `PARALLEL_TOOL_COMMITS`. Cadence
   drill measured iteration-latency=0 and time-latency=-0.2h
   (audit add-time was ~12 minutes BEFORE pt-commit-time).

Lesson: when the parallel-tool's intent is communicated early
(via the drill files that get dropped into mcp/tests/), the
autonomous-loop can pre-ship audits and achieve the
mathematically-fastest possible ADR-020 cadence.

## Stop conditions specific to this coordination

In addition to the generic §44.3 stop conditions, the autonomous-
loop yields when:

| Specific to coordination | What happens |
|---|---|
| Same drill-drift shape repeats 3+ iterations | §44.4 red flag → yield + diagnosis |
| Watcher REJECTs accumulate (rule 1) on consecutive commits | yield + post-commit drill_outcome trace |
| KNOWN_UNAUDITED ratchet grows for 2 iterations without paydown | yield + paydown plan |
| Parallel-tool drill imports a path that doesn't yet exist in main | yield + "audit-pre-shipped, waiting for source" status |

## Composes with

* **`docs/architecture/adr/018-three-way-work-allocation-operator-vs-parallel-tool-vs-autonomous-loop.md`** —
  names the three actors; this runbook covers the gaps when actors
  bump into each other.
* **`docs/architecture/adr/020-parallel-tool-commit-drill-audit.md`** —
  the audit policy this runbook operationalises.
* **`docs/architecture/adr/015-ratchet-pattern-for-discipline-drift.md`** —
  KNOWN_LATE_AUDITS and KNOWN_UNAUDITED follow this pattern.
* **`docs/runbooks/autonomous-loop-cheatsheet.md`** — operator
  reference; this runbook is the deeper-dive on the cascade-handling
  parts.
* **`mcp/tests/drill_adr020_audit_cadence.py`** — the drill that
  measures everything described here.
* **`mcp/tests/drill_drill_catalog_discipline.py`** + **`drill_docstring_cohesion.py`** —
  the meta-drills that catch the canonical drift shape on every
  sweep.
