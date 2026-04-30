# ADR-022: Convergent work — autonomous-loop and parallel-tool arriving at identical decisions

## Status

Accepted — observed twice in the 2026-04-29/30 session, with
both empirical cases producing byte-identical content despite
the two AI streams working in parallel without explicit
coordination.

## Context

ADR-018 declares the three-way work allocation (operator,
parallel content-stream tool, autonomous loop) and assumes the
three actors work on *different* surfaces. ADR-020 covers the
asymmetric case (parallel-tool produces source, autonomous-loop
audits afterwards). ADR-021 covers the inverted case (autonomous-
loop pre-ships audits before parallel-tool's source).

This ADR covers the *symmetric* case: both streams independently
arrive at the same architectural decision and produce nearly
identical artifacts.

### Two empirical instances

**Case 1 — ADR-021 itself** (`91cd8a8`, 2026-04-29 18:51):

* Autonomous-loop drafted `docs/architecture/adr/021-pre-shipped-
  drill-audit-cadence.md` based on observing G-3/G-4/G-5's
  inverted cadence.
* Within minutes, parallel-tool committed `91cd8a8` with the
  exact same filename and BYTE-IDENTICAL content (verified via
  `diff` returning empty).
* The autonomous-loop's intended Phase 7-something commit became
  a no-op because the file was already in `main`.

**Case 2 — Phase 7RR / 214c2c4** (`214c2c4`, 2026-04-30 ~04:25):

* Autonomous-loop staged `drill_cadence_detection_regex.py` (NEW)
  + a NEGATIVE-marker fix to `drill_admin_monitoring_runtime_
  surface.py` (parallel-tool's drill).
* Parallel-tool committed `214c2c4` ("docs(runtime): align
  monitoring and agentic truth surfaces") which BUNDLED both
  files plus additional doc updates.
* My `git commit` for Phase 7RR returned "nothing added to
  commit, working tree clean" because parallel-tool had already
  picked up the staged changes.

Both cases share three properties:

1. The two streams worked in parallel *without explicit message-
   passing* — neither stream consulted the other before commit.
2. The artifacts produced were not just *similar* but identical
   (Case 1) or compatible (Case 2 — different commits but the
   same files landed).
3. The trigger was the *operator's* request pattern: in both
   cases the operator's "next" cadence implicitly authorized
   both streams to act on the same problem.

## Why this happens

Three contributing factors:

### 1. Shared observable substrate

Both streams read the same:
* git log + worktree
* drill catalog state (failed drills, recent commits)
* operator's recent messages
* documentation in `docs/runbooks/`, `docs/architecture/`, and
  `~/.claude/policies/`

When the catalog state cleanly suggests a next move (e.g., "G-5
just landed and ADR-020 cadence drill needs a registry entry"),
both streams independently arrive at the same conclusion.

### 2. Project conventions are highly constraining

The project enforces:
* §43 drill template (RESOURCES tag, NEGATIVE marker, banner format)
* ADR-015 ratchet shape (KNOWN_X / DOMAIN_X distinction)
* ADR-017 structural-rewrite preference
* ADR-018 audit cadence expectations
* §49 compose-with footer pattern

When two streams independently solve "write a drill that
verifies X", both follow the same template. The output converges
because the template is rigid enough to leave little stylistic
room.

### 3. Both streams use the same naming heuristics

Slugs derived from observed convention:
* ADR-021 slug = `021-pre-shipped-drill-audit-cadence` because
  "drill-audit" is the canonical phrase from ADR-020 and
  "pre-shipped" naturally describes the inverted timing.
* Phase 7V's coordination runbook lives at
  `docs/runbooks/parallel-tool-coordination.md` because that
  matches the cheatsheet's existing `*-coordination.md` shape.

When two streams generate slugs from the same conventions, they
converge.

## Decision

**Convergent work is acceptable and need not be prevented.** Two
streams arriving at the same artifact is a positive signal that
the project's conventions are doing their job.

The autonomous-loop SHOULD:

1. **Detect convergence at commit time.** If `git status`
   reports "nothing added to commit" and the file in question
   is already in `main`, treat it as a successful convergence,
   not a bug.
2. **Verify byte-equivalence (or compatibility).** Run `diff`
   between the in-progress draft and the in-main version. If
   identical: log convergence, move on. If non-trivial diff:
   resolve via the standard merge-conflict pattern (rebase,
   review, decide).
3. **Register the parallel-tool's commit in PARALLEL_TOOL_COMMITS**
   pointing at the audit drill that the autonomous-loop's draft
   referenced. This preserves the cadence ratchet's accuracy
   without double-counting.
4. **Acknowledge convergence in commit messages or retrospectives.**
   Don't hide it; name it. Operators reading session history
   should see "parallel-tool committed an identical version
   first" as a feature of the pattern, not as confusion.

## Consequences

### Positive

* **Convergence validates the conventions.** When two AI
  streams independently produce the same artifact, the
  conventions are sufficiently rigid to be operator-trustable.
  Loose conventions would diverge.
* **No wasted work.** Either stream's output is acceptable;
  whichever lands first satisfies the operator's intent.
* **Faster cadence.** When one stream is blocked (running
  drills, waiting on hook), the other can land — net time-to-
  artifact decreases.
* **Empirical evidence of architectural soundness.** Multiple
  ADRs in this project have been "extracted from" practice
  rather than "prescribed." Convergent-work is itself the
  third-party verification that the practice was right.

### Negative

* **Duplicate work invisible to operator.** Both streams may
  spend cycles on the same task. With the autonomous-loop
  reporting per-iteration insights and parallel-tool reporting
  per-batch summaries, the operator sees ~2x the "work narrative"
  for 1x the artifact.
* **Wasted council fires.** The post-commit LLM council fires
  on every commit. If two streams commit identical-content
  diffs at different times, both fires happen — token cost
  doubles for a single conceptual change.
* **Staging conflicts.** If both streams stage the same files
  simultaneously, git's "nothing added" response can confuse
  the autonomous-loop's iteration logic ("did my commit land?
  why is the file already in main?"). Phase 7RR encountered
  this; recovery was straightforward but required manual
  diagnosis.

### Risks accepted

* When the two streams *don't* converge (Case 1 outcome A vs
  outcome B), one stream's work is wasted. Mitigation:
  conventions reduce divergence space; when divergence does
  happen, the standard merge-resolution applies.
* Operator can't reliably attribute changes to one stream.
  Mitigation: commit author + Co-Authored-By trailer remains
  the source of truth at the commit level; ADR / runbook
  attribution is informational, not load-bearing.

## Alternatives considered

1. **Lock files / mutex between streams**: would prevent
   convergence but at the cost of forced serialization. Both
   streams would be slower than either alone. Rejected.
2. **Explicit message-passing protocol**: requires shared state
   (e.g., a "claim" file in `.loop/`) where each stream announces
   intent before acting. Higher engineering cost than the
   problem warrants — convergence has only been observed twice
   and resolved cleanly each time.
3. **Make one stream authoritative on each artifact type**: e.g.,
   only autonomous-loop writes ADRs. Rejected because it
   contradicts ADR-018's three-way allocation and the parallel-
   tool clearly *can* write ADRs (Case 1 demonstrates the
   capability).

## How to detect convergent work

```bash
# After a commit attempt that returns "nothing added to commit":
# check if the intended file is already in main.

git log -1 --pretty="%H %s" -- path/to/intended/file
# If the file's last-modified commit IS the parallel-tool's
# commit (not the autonomous-loop's), you've witnessed convergence.

# Verify byte-equivalence:
diff <local-draft.md> <(git show <commit>:path/to/file)
# Empty diff = byte-identical. Convergent work confirmed.
```

`drill_adr020_audit_cadence`'s registry should contain the
parallel-tool's commit hash mapped to the audit drill that
the autonomous-loop's draft referenced. The autonomous-loop's
intended commit is a no-op (skipped or merged into the
follow-up registry-update commit).

## References

* ADR-018 — Three-way work allocation
* ADR-020 — Parallel-tool commit drill audit
* ADR-021 — Pre-shipped drill audit cadence (Case 1: convergent
  ADR-021 itself)
* §43 — Drill testing pattern (template that drives convergence)
* §44 — Autonomous feature loop
* Phase 7F (`3b1cc02`) — autonomous-loop's ADR-021 draft
* Phase 7RR — autonomous-loop's drill_cadence_detection_regex
  draft
* `91cd8a8` — parallel-tool's convergent ADR-021 commit
* `214c2c4` — parallel-tool's convergent docs-runtime bundle
  that absorbed Phase 7RR's drills
