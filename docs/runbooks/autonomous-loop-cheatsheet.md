# Cheatsheet — autonomous loop (session-wide reference)

> One-page operator reference for the autonomous-loop pattern.
> Companion to `docs/runbooks/council-telemetry.md` (which covers the
> 5K-5BB telemetry surface specifically). Both compose with
> `~/.claude/policies/autonomous-feature-loop.md` (the policy doc) and
> `docs/architecture/adr/014-autonomous-loop-architecture.md` (the
> ADR for the advisory contract).

## Activation phrases

The loop turns on when the operator types one of:

- "enter the loop" / "continuous mode" / "auto-next"
- "make next automated"
- "keep going until I say stop"
- "next" (after any completed iteration — implicit continuation)

Once on, every iteration runs: pick → build → drill → doc → commit
→ insight + hash + drill score → loop. No "next" needed between
iterations once activation is established.

## Stop conditions (when the loop yields control)

| Condition | What happens |
|---|---|
| Operator says "stop" / "pause" / "wait" | yield immediately |
| Gated operation needed (force-push, prod mutation, package publish) | yield with explicit ask |
| Drill fails + root cause not a 1-line fix | yield with the failing drill name |
| Two consecutive environmental flakes (e.g. MCP down twice) | yield with diagnosis |
| Outstanding pre-approved menu is empty | propose a new direction + yield |

## Pre-approved actions (no confirmation needed)

Per `~/.claude/CLAUDE.md` §42 (operational autonomy):

| Action | Why pre-approved |
|---|---|
| Edit any markdown file (`.md` / `.mdx`) | docs are always pre-approved, anywhere |
| Edit code in `services/` / `scripts/` / `mcp/` (non-server.py) | within project boundary |
| Add new drills under `mcp/tests/drill_*.py` | drill discipline (§43) |
| Edit `docs/NEXT_POLICY.md` | session ledger |
| Run any read-only CLI (`council_filter_stats.py`, `loop_status.py`) | no mutation |
| Run `git log` / `git status` / `git diff` | read-only |
| Run drill suite via `scripts/run_drills.py` | no mutation |
| Run `scripts/write_drill_status.py --only-readonly` | refreshes `.loop/last_drill_outcome.json` |
| Build embeddings / re-index vector DB / update prompts | within project |
| Modify agent / MCP config | within project |
| Pull models from trusted registries (Ollama, HuggingFace) | within project |

## Gated actions (yield to operator)

| Action | Why gated |
|---|---|
| Force-push to `main` / `master` | history rewrite |
| `rm -rf` on home dir / repo root / `/etc` / `/usr` | destructive scope |
| Drop / truncate production Postgres data | destructive prod |
| External messages (PR comments on others' repos, Slack, email) | third-party visibility |
| Publish packages (`npm publish`, `pip upload`, Docker Hub push) | external release |
| Modify billing / auth providers / secret stores | sensitive infrastructure |
| Add a new field requiring DB migration | (project-specific gate) |
| Touch shared MCP servers outside project | scope boundary |
| Agent action with financial / legal / compliance consequence | scope boundary |
| Production cutover (deploy, scale, schema change) | prod requires explicit auth |

## Drill discipline (always)

Per `~/.claude/CLAUDE.md` §43:

- **Every feature commit ships a drill** with ≥1 negative assertion.
- **Every bug-fix commit ships a drill** that would have caught the bug.
- **Drills run against the real running stack** (real DB, real HTTP,
  real subprocess) — NOT mocks. Mocks belong in pytest.
- **Drill files**: `mcp/tests/drill_*.py` with header
  `# RESOURCES: <tokens>` (or `readonly` for tier-1 safe drills).
- **Run the suite**: `scripts/run_drills.py --parallel 4 [--only <substr>]`
- **Tier-1 readonly** (74 drills; 141 total catalog drills in current worktree):
  `scripts/run_drills.py --parallel 4 --only ""` filtered by `# RESOURCES: readonly`.

## Pre-commit + post-commit hook chain

Per Phase 4B, 5F, 5Y:

```
git commit
  ↓
PRE-COMMIT HOOK (scripts/git-hooks/pre-commit)
  - 5F: refresh drill status if older than 600s (or HBR override)
  - 5Y: detect HBR staged files; force refresh + loud warning if drills failed
  - ALWAYS exits 0 (advisory contract per ADR-014)
  ↓
COMMIT LANDS
  ↓
POST-COMMIT HOOK (scripts/git-hooks/post-commit)
  - 4B: LoopWatcher reads drill_outcome.json; writes verdict to .loop/watcher.log
        (rule 1 = drill_outcome=FAILED → REJECT, rule 6 = APPROVE)
  - 2A2: capture_and_review fires the LLM council on the diff
        (~120-180s wall; appends to .loop/council_runs.log)
  - ALWAYS exits 0 (commits never reverted by the hook)
```

## Recommended cron lines

```cron
# Daily snapshot at 00:05 UTC (5N + 5Q)
5 0 * * * /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/council_stats_snapshot.py

# Weekly council retention prune (2F)
0 4 * * 0 /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/prune_council_runs.py --apply --vacuum

# Weekly JSONL log retention prune (6E) — keeps 90 days of watcher.log + council_runs.log
30 4 * * 0 /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/prune_loop_logs.py --apply

# Or composed pipeline (5X) — snapshot + prom export + alerts/webhook in one call
5 0 * * * /mnt/deepa/rag/scripts/run_filter_pipeline.sh \
    --prometheus-out /var/lib/node_exporter/textfile/council.prom \
    --webhook "$COUNCIL_STATS_WEBHOOK" \
    --webhook-format slack \
    --alert-on "filtered>0.5"
```

Install via the dry-run-by-default script:

```bash
scripts/install_snapshot_cron.sh --status      # see if it's installed
scripts/install_snapshot_cron.sh --apply       # install the daily snapshot cron
scripts/install_snapshot_cron.sh --rollback    # undo (preserves backup)
```

## Escape hatches per script

| Knob | Effect |
|---|---|
| `SKIP_DRILL_STATUS=1 git commit ...` | pre-commit hook skips drill refresh |
| `STALE_AFTER=60 git commit ...` | tighter drill-status freshness window than 600s default |
| `CAPTURE_NO_COUNCIL=1 git commit ...` | post-commit records event but skips LLM council fire |
| `[skip-council]` in commit subject line | filters the commit out of council review (5K) |
| `[no-council]` in commit subject line | same as `[skip-council]` (alternative wording) |
| `--dry-run` on every mutating script | preview without changes (Tier-1 + cron installer pattern) |
| `git commit --no-verify` | bypasses ALL git hooks (last resort) |

## Common debugging commands

```bash
# What did the loop do today?
git log --oneline --since="6 hours ago"

# What did the watcher decide on each commit?
tail -10 .loop/watcher.log | python3 -c "
import sys, json
for ln in sys.stdin:
    e = json.loads(ln)
    print(f\"{e['commit_sha'][:7]} {e['verdict']} (rule {e['rule_fired']}) — {e['commit_message_first_line']}\")
"

# Outcome histogram (per-window or per-week)
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --weekly --weeks 4

# One-shot health check (all rails)
/mnt/deepa/rag/.venv/bin/python scripts/loop_status.py
# Exit 0 = healthy, 1 = warnings, 2 = errors

# Run all drills (tier-1 only — readonly, ~12s)
scripts/run_drills.py --parallel 4

# Run drills matching a pattern
scripts/run_drills.py --parallel 2 --only sidecar

# Refresh the drill_status file (what LoopWatcher reads)
/mnt/deepa/rag/.venv/bin/python scripts/write_drill_status.py --only-readonly

# Replay verdict log to find recent REJECTs
grep -F '"verdict": "REJECT"' .loop/watcher.log | tail -5

# What's pre-approved vs gated this session? (this file)
cat docs/runbooks/autonomous-loop-cheatsheet.md
```

## Memory + context

The loop persists state across iterations via:

```
.loop/
├── council_runs.log               # one row per council fire (post-commit)
├── council_stats_daily.jsonl      # daily snapshot (cron via 5N)
├── watcher.log                    # one row per commit verdict (4B)
├── last_drill_outcome.json        # rolled-up drill status (5G)
└── dashboard.html                 # pre-rendered dashboard (1B-static)

advisor.db                         # SQLite: events + council_runs + ratings
docs/NEXT_POLICY.md                # session ledger (every phase entry)
docs/architecture/adr/             # ADRs (immutable; supersede, never edit)
mcp/tests/drill_*.py               # drill catalog (141 total, 74 tier-1 readonly)
```

## Composes with

- **`~/.claude/policies/autonomous-feature-loop.md`** — the policy that defines activation, stop conditions, iteration shape
- **`~/.claude/CLAUDE.md`** §42 (operational autonomy), §43 (drill discipline), §49 (compose-footer)
- **`docs/architecture/adr/014-autonomous-loop-architecture.md`** (ADR-014) — the advisory contract that lets failing commits land but logs them
- **`docs/architecture/adr/015-ratchet-pattern-for-discipline-drift.md`** (ADR-015) — the ratchet pattern (grandfather current drift, gate growth, reward shrinkage); applies to drill catalog discipline + UI scope grants + future per-rule sets
- **`docs/architecture/adr/016-parallel-agent-allocation-for-independent-n-file-work.md`** (ADR-016) — when to spawn parallel agents (5 preconditions) vs single-thread; three allocation patterns observed across phases 5S, 6C, 6J, 6K
- **`docs/architecture/adr/017-forward-looking-checks-and-sweep-before-commit-discipline.md`** (ADR-017) — anti-pattern: drill assertions that say "X is the latest" or "exactly N items"; structural rewrites + sweep-before-commit discipline that catches the regression at iteration time, not verdict-log time
- **`docs/runbooks/council-telemetry.md`** — the deeper runbook for the 5K-5BB telemetry surface
- **`docs/NEXT_POLICY.md`** — the session ledger; every phase entry includes drill score
