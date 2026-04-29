# ADR-018: Three-way work allocation — operator vs parallel-tool vs autonomous-loop

## Status

Accepted — landed across five demonstrations: Phase A1 (`8d20369`-era
Ollama migration completed by operator), Phase 6C (`c4e65ad`
parallel-agent catalog cleanup), Phase 6J (`8e5f1d1` cooperation
between this session and parallel content stream), Phase 6K + 6L
(`45c5ad5` + `887fa9a` integration commits landing parallel-tool
deliverables), Phase 6M (`d106223` ADR-016 reflective architecture).

## Context

The autonomous loop runs in a multi-agent ecosystem. Three
distinct work allocations show up across the session:

| Actor | What they do | Examples this session |
|---|---|---|
| **Operator** (the human) | sudo, secret URLs, billing decisions, scope grants | A1 Ollama sudo, A3 webhook URL pending, §7 grant decisions |
| **Parallel content-stream** (another AI tool / VS Code agent) | Iterates on a separate work tree; commits OR leaves work uncommitted; their own pacing | KNOWN_AUDIT_DRILLS rename, drill_catalog_summary.py, ratchet_status.py shipped, agent-orchestrator-svc/ in flight |
| **Autonomous loop** (this session) | Runs the §44 loop; commits per-iteration; integrates parallel work via Phase-6K/6L style commits | All Phase-X commits in `git log`; orchestration of 6C agents; ADR authorship |

Each actor has a different set of capabilities, blockers, and
verification mechanisms. Ad-hoc allocation worked for a while but
produced friction:

* The autonomous loop kept asking the operator for approval on
  things that were pre-approved per §42 — "you have complete
  system approval" was the operator's correction.
* The parallel content-stream and the autonomous loop occasionally
  stepped on each other (e.g. both proposing a `drill_catalog_summary.py`,
  both wanting to commit overlapping deltas).
* The operator's blockers (sudo, webhook URL, API keys) didn't
  always move while the loop iterated, leaving items "pending"
  for hours.

ADR-018 names the allocation explicitly so future iterations
recognize "this is operator work" / "this is parallel-tool work"
/ "this is autonomous-loop work" before starting.

## Decision

**Each task has exactly ONE primary actor**. The other two are
reviewers, integrators, or subsequent users. Allocation is by
capability (what each actor can do that the others can't):

### Operator-required (only the human can do)

Work whose execution requires capabilities the AI agents don't
have:

* `sudo` (interactive password prompt)
* External secret URLs (webhook URLs, API keys, paid-service tokens)
* Billing decisions (subscription enable/disable; new vendor accounts)
* §7 scope-extension approvals (granting AI agents new file-tree
  scopes; the AI cannot grant itself new scope)
* Cross-environment cutover (prod deploy, schema change, secret rotation)

When operator-required: the autonomous loop **prepares** (writes
the commands, runs dry-run, gives copy-paste-ready blocks), then
**yields** with the explicit ask. Loop stays parked until operator
acts.

### Parallel-tool work (the other AI iterates independently)

Work the parallel content-stream picks up:

* Substantial multi-file refactors over a long wall window where
  serial committing would block the autonomous-loop's faster cadence
* Frontend page-stream edits that span topic-areas outside the
  autonomous loop's §7 grant
* Service-code authorship for new directories (e.g.
  `services/agent-orchestrator-svc/`)
* "Find all and fix" sweeps where the parallel tool's broader
  scope is an advantage

The autonomous loop **observes** (checks `git status` + working
tree) and **integrates** (Phase-6K / 6L pattern: split the
parallel tool's delta by scope and commit pre-approved subsets;
leave gated subsets for operator decision).

### Autonomous-loop work (this session's iterations)

Work that fits the §44 iteration shape:

* Single-iteration features ≤ 250 lines or ≤ 5 files
* Drill authorship + the corresponding feature in one commit
* ADR authorship after a pattern has 3+ demonstrations
* Doc maintenance (cheatsheets, runbooks, NEXT_POLICY.md ledger)
* Ratchet maintenance (per ADR-015)
* Compose-footer updates per §49

The autonomous loop **commits** as the primary actor; the operator
reviews via verdict log + ADR audit; the parallel tool benefits
from the discipline scaffolding (drills, ratchets, ADRs).

### Allocation table

| Capability | Operator | Parallel-tool | Autonomous-loop |
|---|---|---|---|
| sudo | ✅ | ❌ | ❌ |
| External secrets (URLs, API keys) | ✅ | ❌ | ❌ |
| §7 scope grants | ✅ | ❌ | ❌ |
| Multi-file refactor (>5 files, >250 lines) | — | ✅ | ⚠️ chunked via parallel agents (per ADR-016) |
| New service code (`services/X/`) | — | ✅ | ❌ (gated) |
| Single-iteration feature + drill | — | — | ✅ |
| ADR authorship (pattern named after ≥3 demos) | review | review | ✅ |
| Drill catalog discipline | — | — | ✅ |
| Doc cheatsheet + runbook | review | edit | ✅ |
| Verdict-log review (post-commit triage) | ✅ | observation | observation |

## Consequences

### Positive

* **Stop asking on pre-approved work**. The autonomous loop's
  recurring "should I do X?" friction was operator-corrected
  multiple times this session ("§42 — stop the question and do
  it"). Naming the allocation explicit removes the ambiguity at
  iteration start.
* **Parallel-tool deliveries integrate cleanly via Phase-6K/6L
  pattern**. Two streams iterating independently produce
  conflicting working-tree state; the integration-commit shape
  resolves it (split by scope, commit pre-approved subsets).
* **Operator gets back agency**. The "operator-only" list is
  short and explicit; everything else is delegated. Operators
  reviewing the verdict log + ADR catalog (asynchronous) instead
  of blocking on per-iteration approval.

### Negative

* **Three-actor coordination is harder than two-actor**. Most
  software-team patterns assume one human + one AI. Three actors
  (one human + two AIs) require explicit allocation; ad-hoc fails.
* **Some work has gray-zone allocation**. The 4 modified scripts
  by the parallel tool (interpreter path migration in
  `council_stats_snapshot.py` etc) are pre-approved per §42 but
  the parallel tool authored them. Phase 6L flagged this as
  "your call who signs"; ADR-018 now says this should default to
  the parallel tool committing (they authored = they sign).
* **The verdict log gets noisier with three actors**. Each
  actor's commits land independently; the verdict log shows the
  union. Operators triaging REJECTs need to know who authored
  which commit — `Co-Authored-By` trailer is the convention.

### Risks accepted

* **The parallel tool's pace can outrun the autonomous loop's
  drills**. Phase 6K integration showed the parallel tool's
  50-file delta needed careful scope-splitting before committing.
  If the parallel tool ships agent-orchestrator-svc faster than
  the autonomous loop can drill it, the gated commits accumulate.
* **Operator may not realize the loop is waiting**. The 4
  pending operator-required items (A1 finalize, A3 webhook,
  G-1 service-code commit decision, B-1/B-2/B-3 gate-lifts)
  could wait days without explicit notification. The cheatsheet's
  "Recommended cron" includes alerting (5T) but that requires A3
  to be done first — bootstrapping problem.

## Alternatives considered

### A. Single-actor (operator does everything)

Pros: zero coordination overhead.
Cons: defeats the autonomous-loop's compounding behavior; reduces
the parallel-tool to a typing assistant. The session's 65 commits
in one day wouldn't be possible.

### B. Two-actor (operator + one AI)

Pros: simplest mental model; matches most software team patterns.
Cons: misses the parallel-tool's value (broader scope; longer
wall windows). The session showed concrete wins from three-actor
allocation (5S parallel build; 6C catalog cleanup; 6J/6K cooperation).

### C. Round-robin between AI agents

Pros: load balanced.
Cons: no work is naturally round-robin-able. Each task has a
primary actor by capability; round-robin would force misaligned
allocations.

### D. Implicit allocation (no ADR; just figure it out per iteration)

Pros: no architecture overhead.
Cons: the friction we hit this session shows implicit doesn't
scale. "Should I do this myself or wait for the parallel tool?"
came up multiple times; explicit allocation removes the ambiguity.

## References

| Phase | Commit | Allocation example |
|---|---|---|
| A1 | `8d20369` (era) | Operator-required: ran `sudo scripts/migrate_ollama_to_deepa.sh --apply` after autonomous loop's pre-flight |
| 6C | `c4e65ad` | Autonomous-loop work: 3 parallel agents tagged 23 drills |
| 6J | `8e5f1d1` | Cooperation: parallel tool shipped 2 scripts; autonomous loop wrote the integration drill |
| 6K | `45c5ad5` | Integration: autonomous loop committed parallel tool's 50-file ratchet retirement |
| 6L | `887fa9a` | Integration: autonomous loop committed parallel tool's 27-file docs delta |
| 6M | `d106223` | Reflective architecture: ADR-016 named the parallel-agent allocation pattern |

Composes with: ADR-014 (the autonomous-loop's advisory contract —
verdict log shows verdicts from ALL three actors' commits),
ADR-016 (parallel-agent allocation — what the autonomous loop
does within ITS own iteration; ADR-018 covers cross-actor allocation),
ADR-017 (sweep-before-commit — the discipline that catches
regressions regardless of which actor authored the change),
~/.claude/CLAUDE.md §42 (operational autonomy — defines the
operator-required list this ADR codifies).
