# Empirical retest 2026-05-04 — scanner timeout finding

**Date:** 2026-05-04 20:08 UTC (local 14:08 MDT)
**Run:** `python scripts/empirical_apply_test.py simulate --max-cycles 1 --apply`
**Outcome:** ❌ daemon failed at scan stage; subprocess.TimeoutExpired after 600s
**Root cause:** `~/.claude/scripts/issue_scanner.py --include-mypy --include-bandit --include-eslint`
exceeds the daemon's hardcoded 600s subprocess timeout on this repo.

## What this proves

The bottleneck on a fresh empirical retest is NOT the council
quality or the apply-check pre-flight. It is the SCAN stage —
specifically running mypy + bandit + eslint across the whole
repo (services/retrieval-svc/, mcp/, scripts/, services/frontend/).

Apply rate was never measured because no issue ever reached the
council. The 0/8 historical baseline (from the first retest with
malformed JSON / missing files / corrupt offsets) remains the
last data point.

## Concrete evidence

```
daemon:start max_cycles=1 interval=120.0 dry_run=False
daemon:cycle_start at=2026-05-04T20:08:46.140374+00:00
Traceback (most recent call last):
  ...
  File "scripts/autonomous_fix_daemon.py", line 121, in scan_issues
    proc = subprocess.run(...)
subprocess.TimeoutExpired: Command '['python3',
  '/home/praveen/.claude/scripts/issue_scanner.py',
  '--repo', '/mnt/deepa/rag',
  '--include-mypy', '--include-bandit', '--include-eslint']'
  timed out after 600 seconds
exit=1; elapsed 600.2s
```

## What needs to change to unblock the next retest

Three options, ordered by complexity:

1. **Narrow the daemon's scan surface for retest cycles.** Add a
   `--scan-paths tests/_empirical_synthetic.py` flag to the daemon
   so it scans only the synthetic file. Avoids the 600s timeout
   entirely. ~2 hr work.

2. **Cache or skip slow linters.** `mypy --strict` on the
   retrieval-svc surface alone takes most of the budget. Either
   cache mypy state per file, or run only ruff (fast) for the
   first cycle and gate slower linters behind a separate flag.
   ~6 hr work.

3. **Bump the daemon timeout.** Crude — masks the actual problem.
   600s is already aggressive; bumping to 1800s just delays the
   failure when scope grows further. Reject this option.

## Recommended next iteration

Option 1 (narrow scan surface). The empirical harness is the
canonical retest path; it already drops a deliberate F401 in a
single file. Scanning the whole repo for that 1 issue is wrong
by design.

## Composes with

- `scripts/empirical_apply_test.py` — operator harness; the wrapper
- `scripts/autonomous_fix_daemon.py` — has the 600s subprocess.run timeout
- `~/.claude/scripts/issue_scanner.py` — the slow component (mypy + bandit + eslint)
- `mcp/tests/drill_apply_check_preflight.py` — Tier 1.3.b synthetic 8/8 pre-check
- `docs/architecture/apply-rate-empirical-finding.md` — earlier 0/8 finding (different cause)
- §55.2 Tier 1.3 — adaptive context (per-rule strategy)
- §55.3 — apply rate as outcome contract

## The brutal rule, restated

> Empirical evidence beats theory. Today's retest produced ZERO
> apply-rate data — but produced ONE concrete root cause: the
> scan stage is the bottleneck, not the council. Fix the scan
> surface for retest cycles before claiming Tier 1.3.b moved
> apply rate.
