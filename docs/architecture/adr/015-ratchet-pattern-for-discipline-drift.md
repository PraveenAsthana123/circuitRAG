# ADR-015: Ratchet pattern for discipline drift

## Status

Accepted — landed in Phases 6B, 6C, 6D + the §7 scope-extension log
in `docs/NEXT_POLICY.md`. Three ratchets currently in production:

| Ratchet | Where | Locks |
|---|---|---|
| `KNOWN_MISSING` | drill_drill_catalog_discipline.py step 2 | `# RESOURCES:` tag presence |
| `KNOWN_MISSING_NEG_MARKER` | step 7 | §43.5 docstring marker |
| §7 scope-extension log | NEXT_POLICY.md | UI grant whitelist |

Current repo state: the two catalog-content ratchets are fully paid
down (`KNOWN_MISSING=0`, `KNOWN_MISSING_NEG_MARKER=0`); only the §7
scope whitelist remains active as a non-zero structural guard. The
ADR keeps the catalog ratchets listed because they are still the live
control shape in code, even when their grandfathered sets are empty.

## Context

Phase 6B introduced a meta-drill that audits the entire drill
catalog for §43-discipline compliance. The first run revealed 23
drills missing the `# RESOURCES:` tag, plus 2 frontend audits with
no exit-code signal — real drift accumulated before the meta-drill
existed. Those survey checks were later renamed out of the
`drill_*.py` namespace into `audit_*.py`, which retired the
exit-signal carve-out as a live ratchet.

Three approaches were plausible:

**Shape A — Strict assert + bulk fix**. The drill fails until all
existing drift is cleaned up. Authors must batch-fix 25 files
before any new drill can land.

**Shape B — Soft percentage threshold**. The drill passes if ≥X%
of drills comply. Tolerates current state, but the threshold drifts
upward with the catalog (false sense of progress) and individual
drills can quietly fall further behind.

**Shape C — Ratchet via grandfathered set**. Snapshot current
state as a frozen `KNOWN_*` set; the drill fails if a NEW drill
exhibits the drift, succeeds if the set shrinks (someone fixed
one), reports stale entries (set member that's actually compliant
now).

The same trade-off appeared in Phase 5Z, where Phase 5S landed a
new file outside the §7 UI scope-grant — Shape A would have
forced an immediate revert; Shape C let the change land + logged
a retroactive scope-extension entry.

## Decision

**Shape C — ratchet via grandfathered set — for any discipline rule
where existing drift is non-trivial AND fixing it isn't load-bearing
right now.**

A ratchet is not a permission to ignore drift forever; it's a
contract:

1. **Snapshot the current drift set explicitly** by exact filename
   (or other discriminator). No glob patterns; no "anything in
   directory X." The set is concrete + auditable.

2. **Gate growth**: any item NOT in the set that exhibits the drift
   is a hard FAIL. New drift cannot accumulate silently.

3. **Reward shrinkage**: when an item gets fixed, the drill
   automatically detects it (the item leaves the actual-drift list)
   and reports it as "stale entry — safe to remove." Operators
   shrink the set in their next commit touching the meta-drill.

4. **Refuse mechanical churn**: don't add bogus content to satisfy
   the syntactic check. Phase 6D refused to slap "negative" into 34
   drill docstrings without verifying actual assertion presence —
   that would have lied to the meta-drill while satisfying its
   regex.

5. **Document the carve-out**: when an item is in the set
   intentionally, the comment near the set must explain the design
   rationale + the future-naming convention if applicable. If the
   naming or namespace debt is later paid down, the ratchet should
   be retired rather than kept as dead history.

## Consequences

### Positive

* **No iteration churn**. Phase 6B's meta-drill landed without
  requiring 25 unrelated fixes first. The session continued.
* **Drift is visible**. Operators reading the meta-drill see
  exactly which files have which kinds of drift. No more "75% of
  drills comply" abstraction; it's "drill_admin_api.py is missing
  the RESOURCES tag" with the file name on screen.
* **Drift can be paid down asynchronously**. Phase 6C used parallel
  agents to clean `KNOWN_MISSING` in a single iteration. Could have
  taken many iterations; could have stayed grandfathered forever.
* **Pattern composes**. The same shape applies to UI scope grants
  (§7), drill discipline (6B/6C/6D), and any future "we have N
  files that drift this way." Once operators learn the pattern,
  recognizing where to apply it is cheap.

### Negative

* **Visual noise in the meta-drill**. A `KNOWN_MISSING_NEG_MARKER`
  set with 34 entries occupies ~40 lines of source. New readers
  must understand that the set is grandfathered drift, not a
  spec.
* **Stale-entry sweeps require periodic attention**. A grandfathered
  drill that gets fixed but isn't removed from the set is
  technically dead weight. The drill reports stale entries — but
  operators must actually trim them, otherwise the set grows
  semantic-cruft over time.
* **The pattern can hide root causes**. If 50% of drills have a
  certain drift, ratcheting the rest is the comfortable choice;
  the harder question is "is the rule wrong?" Always consider
  whether the rule should change before grandfathering enforces it
  forever.
* **Retired ratchets require ADR cleanup**. Once a grandfathered
  set disappears from code, the ADR must stop claiming it as a live
  control or the architecture narrative drifts from the repo.

### Risks accepted

* **A regression gets grandfathered**. Operator commits a new
  broken drill, then mistakenly adds it to the set instead of
  fixing it. This is a process / review concern; the meta-drill
  can't distinguish "intentional carve-out" from "mistake." Comment
  rationale in the set definition catches this on review.
* **The catalog accretes ratchets indefinitely**. Each new
  discipline rule produces another `KNOWN_*` set. After 10+ ratchets
  the meta-drill becomes hard to read. Mitigated by extracting them
  to a separate constants module if the count grows past ~6.

## Alternatives considered

### A. Strict assert + bulk fix

Pros: forces the cleanup; no grandfathered drift.
Cons: blocks the iteration that introduces the rule; creates
distance between "we noticed the drift" and "we shipped the
discipline." The Phase 6B → 6C separation worked precisely because
6B could ship before 6C's cleanup completed.

### B. Soft percentage threshold

Pros: simple to implement; tolerates current state.
Cons: drift accumulates silently as the catalog grows. 80% of 100
drills compliant means 20 drift; 80% of 200 drills means 40 drift.
The threshold's denominator changes the semantics. Phase 6D
deliberately replaced this shape with the ratchet because
percentages obscure the absolute drift count.

### C. Ratchet via grandfathered set (the decision)

Pros: drift is concrete + visible; no churn; pattern composes.
Cons: visual noise; stale-entry sweep is manual; can hide root
cause questions.

The trade-off favors C because the alternatives produce either
churn (A) or invisible accumulation (B), both of which are worse
for an autonomous loop's compounding behavior.

### D. Per-rule timestamps

Idea: each ratchet entry records WHEN the drift entered the set.
Rule: entries can stay grandfathered for ≤90 days; older entries
auto-fail. Forces eventual cleanup.

Pros: hard cap on grandfather duration.
Cons: introduces time-based test instability; CI fails one day
without any code change. Discarded.

## References

| Phase | Commit | What it ratcheted |
|---|---|---|
| 5Z | `8d20369` | §7 scope grant for `telemetry/page.tsx` (retroactive log) |
| 6B | `ce4e56c` | Introduced `KNOWN_MISSING` + `KNOWN_NO_EXIT_SIGNAL` |
| 6C | `c4e65ad` | Cleaned `KNOWN_MISSING` to empty via parallel agents; renamed `KNOWN_NO_EXIT_SIGNAL` → `KNOWN_AUDIT_DRILLS` |
| 6D | `595040c` | Replaced 6B step 7 percentage threshold with `KNOWN_MISSING_NEG_MARKER` ratchet |
| 6H | _current worktree_ | Renamed the 2 survey-only frontend audits to `audit_*.py`; retired `KNOWN_AUDIT_DRILLS` as an active ratchet |
| 6J | _current worktree_ | Added truthful negative-coverage markers to the last 32 grandfathered drill docstrings; emptied `KNOWN_MISSING_NEG_MARKER` |

Composes with: ADR-014 (the advisory contract that lets failing
commits land but logs them — the ratchet is the same family of
"don't block forever; log + gate growth"), CLAUDE.md §43 (drill
discipline), CLAUDE.md §44 (autonomous loop activation).
