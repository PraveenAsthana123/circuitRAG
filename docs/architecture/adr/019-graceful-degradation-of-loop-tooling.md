# ADR-019: Graceful degradation of loop tooling

## Status

Accepted — pattern observed across most autonomous-loop scripts:
`loop_status.py` (5I), `council_filter_stats.py` (5L+),
`council_stats_snapshot.py` (5N), `prune_loop_logs.py` (6E),
`install_snapshot_cron.sh` (5Q), `loop_status._ollama_active`
fallback (6O).

## Context

Operator-facing scripts run in many states:

* Pre-bootstrap (the loop is brand new; no logs exist yet)
* Steady-state (logs populated; council firing daily)
* Mid-migration (a daemon restarting; a file half-rewritten)
* Post-cleanup (some logs pruned; some files renamed)
* Cross-environment (operator copies the script to a different host)

A script that crashes on any of these states fails the operator
at exactly the wrong moment — usually during an incident when
they're trying to debug a different problem. The autonomous-loop
session converged on a graceful-degradation pattern across
multiple scripts without ever naming it. ADR-019 names it
explicitly.

The pattern, observed N times:

* `loop_status.py`: missing `.loop/watcher.log` → reports
  "no entries yet" (not crash). Missing `advisor.db` → reports
  "events_total: 0". Missing Ollama daemon → "ollama: inactive"
  with WARNING state.
* `council_filter_stats.py`: missing `council_runs.log` →
  empty histogram + stderr warning, exit 0. Bad timestamps in
  log lines → entries kept, not dropped.
* `council_stats_snapshot.py`: missing log → zero-row snapshot
  (so cron tick survives bootstrap state).
* `prune_loop_logs.py`: missing log → no-op + status string,
  not crash.
* `install_snapshot_cron.sh`: empty crontab on first install →
  installs without crashing.
* `loop_status._ollama_active` (Phase 6O): `systemctl is-active`
  returning a non-active state → falls back to direct `ollama list`
  probe (handles transient migration states).

The pattern is now strong enough to lift from "scripts happen
to do this" to "scripts MUST do this."

## Decision

**Every operator-facing script in `scripts/` MUST implement
graceful degradation for at least these failure modes:**

1. **Missing input file** → script reports the absence (not
   "FileNotFoundError" stack trace), continues with zero-state
   semantics. Examples: empty histogram, no-op prune, status =
   "no entries yet". The script must EXIT 0 if the missing-file
   state is a valid pre-bootstrap state.

2. **Bad timestamp in JSONL line** → entry kept, not dropped.
   Operators handle malformed rows manually if needed; the
   tooling never silently loses data because of one malformed
   field. (Per the data-preservation principle from Phase 5L.)

3. **Malformed JSON line** → skip the line with optional
   stderr log; don't abort. Append-only logs are written from
   multiple processes; partial writes are possible during a
   crash. The tooling reads what it can.

4. **External daemon transient state** → multi-probe with
   fallback. `systemctl is-active X` reporting transient states
   (activating, reloading, migrating) is normal during operator
   maintenance; a single probe gives the wrong answer. Fall
   back to a direct functional probe (`X --version` /
   `X list` / GET endpoint) before declaring the daemon down.

5. **Missing executable / dependency** → report the absence
   with a hint, exit non-zero IF the script can't operate, but
   never crash with a Python traceback that reaches the
   operator's stderr. Wrap subprocess invocations in
   `try/except (FileNotFoundError, subprocess.SubprocessError)`.

### What this is NOT

* **Not a license to swallow REAL errors silently**. A
  graceful-degradation script reports the missing state to
  stderr; it doesn't pretend the state is normal. The
  difference between "exits 0 because pre-bootstrap is valid"
  and "exits 0 because we hid the failure" is whether stderr
  shows the missing-state message.

* **Not retry logic**. Retries are for transient failures of
  the operation; degradation is for missing inputs. A script
  that retries 5 times before reporting a missing log file
  hangs the operator's terminal for 30 seconds.

* **Not blanket `except Exception`**. Catch the specific
  expected absences (`FileNotFoundError`, `json.JSONDecodeError`,
  `ValueError` on timestamp parse, `subprocess.SubprocessError`
  on daemon probe). A bare `except` masks bugs.

### Operator-facing UX rule

Whenever a script degrades, it MUST print a one-line stderr
explanation:

```
[script_name] missing X — running in pre-bootstrap mode
[script_name] daemon transient state; verified via fallback probe
[script_name] 3 malformed JSON lines skipped (kept readable)
```

The operator reading the stderr should know what degraded
without needing to read source.

## Consequences

### Positive

* **Bootstrap state is a first-class case**. Phase 5N's
  snapshot script can run on day 1 of a fresh install and
  produce an empty-but-valid snapshot row. No "FileNotFoundError"
  to debug; no special-case "first run" mode the operator must
  remember.
* **Migration windows survive**. Phase 6O's Ollama check now
  handles transient systemd states during the A1 migration;
  loop_status doesn't report false alarms while the daemon
  is restarting.
* **Cross-environment portability**. Scripts copied to a fresh
  box run cleanly; operator gets a clear stderr message about
  what's missing instead of a stack trace.
* **Composes with the cron pipeline**. Cron jobs that fire
  daily can't fail because "the file isn't there yet"; they
  produce zero-state output and continue. The pipeline's
  cumulative shape is robust to the per-day shape varying.

### Negative

* **Discrimination cost between "graceful" and "swallowed"**.
  The line between "this is pre-bootstrap" and "this is a
  silent failure" is operator judgment. Drills should encode
  it where possible (e.g. drill asserts that missing-input
  produces stderr explanation, not silent success).
* **Stderr noise during normal operation**. If every script
  prints a graceful-degradation stderr line every cron tick,
  operators learn to ignore stderr — defeating the warning
  purpose. Mitigated by only printing degradation messages
  when degradation actually fires (not on the happy path).
* **Multi-probe checks can mask real failures**. ADR-019's
  point 4 (fallback probe) means a daemon that's actually
  broken but happens to respond to `--version` looks healthy.
  The fallback should test the actual capability the script
  needs, not a generic "is it alive" probe.

### Risks accepted

* **A genuinely broken script gets reported as graceful
  degradation**. An operator interpreting "missing X — running
  in pre-bootstrap mode" might assume the system is fine when
  X is actually deleted by accident. The drill catalog catches
  this in part (drill_loop_status sweeps verifies behavior in
  bootstrap state); but rare environmental edges may slip past.
* **Performance cost of fallback probes**. Each multi-probe
  costs a subprocess fork. For per-iteration scripts this is
  negligible; for high-frequency probes (every-second daemon
  health checks) it would matter. Mitigated by `loop_status` /
  related being one-shot scripts, not steady-state probes.

## Alternatives considered

### A. Strict / fail-fast everywhere

Pros: every absence is a real error; no ambiguity.
Cons: bootstrap state IS a real and valid state; treating it
as an error blocks day-1 operations. Cron pipelines designed
for fail-fast crash on first run; operators have to special-
case "run once after install."

Discarded — the autonomous loop's daily cron would have to
include "if this is the first run, swallow errors" which is
exactly the silent-success anti-pattern.

### B. Retry-with-backoff for everything

Pros: handles transient failures uniformly.
Cons: retries amplify hangs; an operator running
`scripts/loop_status.py` to debug an incident doesn't want a
30-second backoff loop. Retries are for the operation
(network calls, lock acquires); not for missing files.

Discarded — orthogonal pattern.

### C. Schema-validated config at startup

Pros: every script declares its inputs; missing inputs are
discovered before any work runs.
Cons: defeats the bootstrap-friendly pattern; requires
schema authoring per script.

Discarded — over-engineered for the operator-facing
one-shot-script pattern. ADR-019's point 5 gives the same
guarantee with `try/except` at the use site.

### D. Just document the pattern in the runbook (no ADR)

Pros: lowest overhead.
Cons: the pattern is architectural (cross-cutting across
~6 scripts). Without an ADR the next operator authoring a
new script doesn't see the pattern as "what we do" — they
might revert to fail-fast.

Discarded — ADR-019 is the right artifact for cross-cutting
discipline.

## References

| Phase | Commit | Graceful-degradation site |
|---|---|---|
| 5I | (era) | `loop_status.py` — missing watcher.log → "no entries yet" |
| 5L | (era) | `council_filter_stats.py` — missing council_runs.log → empty histogram + stderr |
| 5N | (era) | `council_stats_snapshot.py` — missing log → zero-row snapshot |
| 6E | `c2cbe3b` | `prune_loop_logs.py` — missing log → no-op + status, not crash |
| 5Q | `7e64494` | `install_snapshot_cron.sh` — empty crontab on first install → no-error |
| 6O | `31e81cf` | `loop_status._ollama_active` — multi-probe fallback for transient systemd states |

Composes with: ADR-014 (advisory contract — graceful degradation
is what makes the loop's "advisory not blocking" possible at the
script level; the advisory contract handles commit-level failure,
graceful degradation handles input-level failure), ADR-016
(parallel-agent allocation — scripts authored by parallel
agents must follow ADR-019's pattern, since multiple authors
need a consistent contract), ADR-017 (sweep-before-commit —
graceful-degradation drills are part of the readonly tier-1
sweep that runs pre-commit).
