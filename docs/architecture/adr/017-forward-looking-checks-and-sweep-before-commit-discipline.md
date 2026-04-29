# ADR-017: Forward-looking checks fail; sweep-before-commit catches them

## Status

Accepted — landed across four demonstrations: Phase 5Z (`8d20369`),
Phase 5Y (`1bbcf97`), Phase 6F (`1fac9b1`), Phase 6G (`cd17d45`).
Has saved at least one iteration each from a regression that would
otherwise have shipped silently.

## Context

A drill written at time T can encode two kinds of invariants:

* **Structural**: properties of the artifact's shape that should
  hold across all time (e.g. "this ADR has a Status section";
  "this script has at least 5 schedule fields per cron line").
* **Forward-looking**: properties that only hold at time T (e.g.
  "ADR-014 is the latest ADR"; "this is the only file under
  sidecar/"; "the cron line uses default interpreter").

Forward-looking checks ALWAYS fail when the future arrives. The
session shipped several drills with forward-looking assertions
that broke when the natural next iteration landed:

| Phase | Forward-looking check | What broke it |
|---|---|---|
| 5Z (caused) | `drill_sidecar_deep_page` step 5: "exactly 4 scenarios" | Phase 5S added SCENARIO_5 |
| 5Z (caused) | `drill_sidecar_nextjs_page` step 8: "files only at sidecar/page.tsx + sidecar/deep/page.tsx" | Phase 5S added sidecar/telemetry/page.tsx |
| 6F (caused) | `drill_adr_014_structure` step 8: "ADR-015 doesn't yet exist" | Phase 6F added ADR-015 |
| 6G (caused) | `drill_install_snapshot_cron` step 6: "default interpreter doesn't appear in WHOLE stdout" | Operator's real crontab gained lines using default interpreter |

Each break manifested as a REJECT verdict in `.loop/watcher.log`
post-commit. Per ADR-014's advisory contract, the commit landed
but the verdict log captured the failure. In every case the fix
was: rewrite the check to assert the structural invariant the
forward-looking version was approximating.

The pattern is recurring enough to name. ADR-017 names it as both
an anti-pattern (forward-looking checks) and the discipline that
catches it before it ships (sweep-before-commit).

## Decision

**Anti-pattern: forward-looking checks**.

Don't write a drill assertion of the shape "X is the latest" /
"there are exactly N items" / "Y doesn't yet exist." These
assertions express how the world is at writing-time, not what
the artifact's contract actually requires.

Replace each with the corresponding **structural invariant**:

| Forward-looking (avoid) | Structural (use) |
|---|---|
| "ADR-N is the latest" | "ADR-N exists and is the only file matching `N-*.md`" |
| "exactly 4 scenarios" | "≥ 4 scenarios" with named-keyword matching for the canonical 4 |
| "files only at A and B" | KNOWN_ALLOWED set + ratchet (per ADR-015) |
| "default interpreter doesn't appear" | scope the check to the specific block being tested |
| "this is the only mention of X" | mention count ≥ 1 (or explicit count if X is bounded) |

The structural form survives the future arriving. The forward-
looking form fails as soon as someone exercises the natural next
extension.

**Discipline: sweep-before-commit**.

For any commit touching:

* `services/frontend/app/admin/sidecar/*` (HBR per Phase 5Y)
* `services/sidecar-advisor/`
* `mcp/server*.py`
* `docs/architecture/adr/*.md` (any ADR change)
* `scripts/*.py` or `scripts/*.sh` (any script change)
* `mcp/tests/drill_*.py` (any drill change)

run the full readonly sweep BEFORE committing:

```bash
/mnt/deepa/rag/.venv/bin/python scripts/write_drill_status.py --only-readonly
```

If the sweep regresses (count drops or a drill flips to FAILED),
fix the regression in the SAME commit OR stop and surface it. Do
not commit and let LoopWatcher log the REJECT silently — the
verdict log is a safety net, not the primary gate.

The rule applies to each iteration, not just to "feature" commits.
Doc commits, refactors, and even `_this commit_` ledger updates
benefit from it because they often touch ADR text or drill
fixtures.

## Consequences

### Positive

* **Regressions caught at iteration time, not verdict-log time**.
  Every demonstration since 5Z saved at least one ~5-minute
  REJECT-then-fix cycle by running the sweep before the broken
  commit landed.
* **Drills become more durable**. A structural invariant survives
  every subsequent iteration that exercises the natural extension.
  Forward-looking checks need updates every time the future
  arrives — that's churn cost the autonomous-loop can't absorb.
* **Composes with ADR-015 (ratchet pattern)**. When the structural
  form requires "the set of allowed paths is W", the W is itself
  a ratchet — empty by default, growable via §7 scope-extension
  log entries. Forward-looking checks have no ratchet equivalent;
  they just break.

### Negative

* **Sweep cost is ~12 seconds per iteration** when triggered via
  the pre-commit hook. Multi-commit sessions pay this several
  times. Mitigated by Phase 5F's staleness window (skip refresh
  when <600s old) and Phase 5Y's HBR scoping (force refresh only
  when high-blast-radius patterns are staged).
* **Operators may cargo-cult the structural form**. "≥ N items"
  is structural-shaped but loses the original assertion's intent
  if the original was actually "exactly N items because that's
  the contract". The right structural rewrite preserves WHICH
  invariant was being asserted; "≥ 4 scenarios with names X, Y,
  Z, W explicitly listed" is the right shape, not the lazy
  ">= 4 something".
* **Some checks legitimately need to change with the future**.
  Drill catalog count, total drill steps, etc. all grow. Those
  are caught by ratchets (per ADR-015) — they're not forward-
  looking failures, they're forward-looking growth that the
  ratchet is designed to track.

### Risks accepted

* **Operators can `--no-verify` the pre-commit hook**, bypassing
  the sweep. The autonomous-loop policy says use this only on
  emergencies, but mistakes happen. Caught later by the
  post-commit verdict log.
* **An iteration's drill catches its OWN regression but not
  cross-cutting drills' regressions**. Phase 5S tested its new
  drill but didn't run the full sweep, missing two drills
  asserting forward-looking invariants. The sweep-before-commit
  discipline closes this gap; without it, only one in N
  cross-cutting failures would surface in time.

## Alternatives considered

### A. Auto-rewrite forward-looking checks to structural form

Idea: a meta-drill that detects forward-looking patterns
("exactly N", "doesn't yet exist", "the only X") and rewrites
the assertion to its structural equivalent.

Pros: removes operator judgment.
Cons: the rewrite isn't mechanical — it requires understanding
WHICH invariant the forward-looking form was approximating.
Phase 6F's drill_adr_014 step 8 said "ADR-015 doesn't yet
exist"; the structural rewrite ("ADR-014 numbering is unique")
required reading the COMMENT explaining the original intent.
A rewrite tool would have produced "exists or not" — the wrong
thing.

Discarded. The discipline is operator-judgment: when you write
a check, ask "what happens when the future arrives?"

### B. Block all checks that mention "exactly", "only", "doesn't"

Idea: regex on drill source rejects assertions using these
keywords without explicit grandfathering.

Pros: simple to implement.
Cons: many legitimate assertions use these words ("exactly 5
fields per cron line" is structural — cron's grammar requires
exactly 5). Banning the keywords would force false-positive
churn and operator workarounds.

Discarded. The discipline is intent-based; keyword-matching
catches both anti-pattern and legitimate uses.

### C. Sweep-after-commit only (current default behavior)

Pros: fastest commit cadence; LoopWatcher catches regressions
in the verdict log.
Cons: regressions accumulate silently; the next commit inherits
a broken catalog state. Phase 5S → 5X chain showed exactly this:
5S landed broken, 5X inherited, 5Z had to reconcile both.

Discarded for HBR commits; acceptable for low-blast-radius
docs-only commits where the pre-commit hook's staleness window
is sufficient.

### D. Just write better drills the first time

Pros: zero process overhead.
Cons: even careful authors write forward-looking checks
sometimes. The four demonstrations in this session were all
written by experienced AI iteration with the autonomous-loop
policy active. The discipline catches what the author missed.

Discarded as wishful thinking. Drills are written with the
future invisible; the sweep-before-commit makes the future
visible at commit time.

## References

| Phase | Commit | Forward-looking check | Structural fix |
|---|---|---|---|
| 5Z | `8d20369` | `drill_sidecar_deep_page` step 5: "exactly 4 scenarios" | bumped to 5 (and 6 in 5AA); list canonical names |
| 5Z | `8d20369` | `drill_sidecar_nextjs_page` step 8: "files only at A + B" | KNOWN_ALLOWED set + ratchet (ADR-015) |
| 6F | `1fac9b1` | `drill_adr_014_structure` step 8: "ADR-015 doesn't yet exist" | "ADR-014 numbering is unique" |
| 6G | `cd17d45` | `drill_install_snapshot_cron` step 6: "default interpreter not in WHOLE stdout" | scope check to `[DRY-RUN] would install:` block only |

Composes with: ADR-014 (the advisory contract — verdict log
is the safety net, sweep-before-commit is the primary gate),
ADR-015 (ratchet pattern — the structural rewrite for "files
only at X" is a ratchet on KNOWN_ALLOWED), ADR-016 (parallel-
agent allocation — applies the sweep-before-commit discipline
to multi-agent integration commits per Pattern C).
