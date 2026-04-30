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
- **Tier-1 readonly** (82 drills; 150 total catalog drills in current worktree):
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
    --webhook-format slack \
    --alert-on "filtered>0.5"
```

To keep the webhook secret out of crontab, put it in:

```bash
cat > /mnt/deepa/rag/.loop/council-stats.env <<'EOF'
COUNCIL_STATS_WEBHOOK="https://REAL-WEBHOOK-URL"
EOF
chmod 600 /mnt/deepa/rag/.loop/council-stats.env
```

`run_filter_pipeline.sh` loads that file automatically.

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

## Loop health dashboards (drill-based observability)

Four orthogonal dashboards answer "is the loop healthy?" — each
covers a different failure mode. Run any one in ≤2s; all four in
≤10s.

### 1. Drift-rate (verdict log analytics, Phase 7W)

Parses `.loop/watcher.log`; reports APPROVE/REJECT distribution +
recent trend + max consecutive REJECT streak.

```bash
python mcp/tests/drill_drift_rate_dashboard.py
```

Key signals:
* `overall APPROVE-rate` — long-term effectiveness of ADR-014's
  sweep-before-commit gate. Floor: 60%.
* `recent APPROVE-rate (last 20)` — short-term trend. Floor: 50%.
* `max consecutive REJECT streak` — sustained meltdown signal.
  Floor: 5 (current grandfathered max from Phase 7Q-7R cascade).
* `trend` line — "stable / improving / regressing" delta.

### 2. ADR-020 audit cadence (Phases 7Q / 7U / 7T / 7BB / 7II)

Reports per-G-bucket iteration-latency + wall-clock time-latency,
SLO compliance, in-SLO/grandfathered/inverted breakdown.

```bash
python mcp/tests/drill_adr020_audit_cadence.py
```

Key signals:
* Per-row marker: `[✓ lat=N]` (in-SLO), `[GF lat=N]` (grandfathered),
  `[!! lat=N]` (out-of-SLO and ungrandfathered).
* `avg-iter-latency` — should trend toward 0 across sessions.
* `avg-time-latency` — should trend NEGATIVE (audits-pre-shipped
  is the steady-state target per ADR-021).
* `inverted (audit pre-shipped)=N` — count of entries
  demonstrating ADR-021's pattern.

### 3. Drift volume (KNOWN_*/DOMAIN_* visibility, Phases 7X / 7Y)

Walks every drill_*.py via AST; reports per-drill KNOWN_*
ratchet entries + DOMAIN_* categorization floors.

```bash
python mcp/tests/drill_drift_volume_meta.py
```

Key signals:
* `DRIFT VOLUME (ratchets only): total=N` — paydown burden.
  HEALTHY ≤5; ELEVATED >5.
* `CATEGORIZATION FLOORS: M entries` — intent-to-track-reality
  (e.g., DOMAIN_ADR_NUMBERS).
* Per-drill table shows which ratchets are empty (paid down)
  vs non-empty (paydown candidates).

### 4. Drill-status freshness (Phases 7DD / 7FF)

Verifies `.loop/last_drill_outcome.json` is fresh + per_drill
catalog membership. Catches the stale-snapshot regression that
caused Phase 7Z/7AA's REJECT verdicts.

```bash
python mcp/tests/drill_drill_status_freshness.py
```

Key signals:
* `FRESHNESS: snapshot N.Nmin old` — should be < 15 minutes
  during active iteration.
* `N/M drills green; K failed` — last sweep's outcome.
* Step 7 fires if `per_drill` keys reference deleted drills
  (catalog drift between snapshot + disk).

### Composing the four

For a complete health check before declaring "loop is healthy":

```bash
PY=/mnt/deepa/rag/.venv/bin/python
$PY mcp/tests/drill_drift_rate_dashboard.py     | grep -E "DRIFT-RATE|trend"
$PY mcp/tests/drill_adr020_audit_cadence.py     | grep -E "ratchet:|SLO:|Wall-clock"
$PY mcp/tests/drill_drift_volume_meta.py        | grep -E "DRIFT VOLUME|CATEGORIZATION"
$PY mcp/tests/drill_drill_status_freshness.py   | grep -E "FRESHNESS"
```

Each dashboard is independently green-able. None of them masks
another's failure.

## Override signals (operator vocabulary, Phase 7V)

When the autonomous loop yields with the §44.4 red flag, the
operator resumes with one of:

| Signal | Effect |
|---|---|
| `next` | single-iteration override; drain one drift item |
| `drain` | multi-iteration override; keep auditing until worktree clean |
| `commit-as-is` | land worktree without audit pass; KNOWN_* ratchets grow temporarily; future iterations pay them down |
| `pause` | full halt; operator coordinates with parallel-tool stream offline |

See `docs/runbooks/parallel-tool-coordination.md` for the full
runbook with cascade-handling protocol.

## Agentic control plane

Operator-facing surfaces for the normalized project/task execution chain:

| Surface | Purpose |
|---|---|
| `/admin` | compact operator summary: project count, pending approvals, latest approvals, latest memories |
| `/admin/monitoring` | runtime/service/resource truth; running/unhealthy services, resource consumers, agent activity summary, observability links |
| `/admin/agentic` | create tasks/projects, set policy, approve tasks |
| `/admin/agentic/control-plane` | full view: role routing, normalized plan rows, task runs, approvals, task/project memories |
| `/app-meta/runtime-status` | local JSON route for Docker/Ollama runtime truth used by the monitoring page |

Truth split:

- **platform/runtime truth**
  - `/admin/monitoring`
    - includes Grafana / Prometheus / Alertmanager / Jaeger links
    - local stack inventory includes node-exporter and cAdvisor
  - `/app-meta/runtime-status`
- **agentic control-plane truth**
  - `/admin/agentic`
  - `/admin/agentic/control-plane`
- **sidecar/council truth**
  - `/admin/sidecar`
  - `/admin/sidecar/telemetry`

Important limit:

- “active agents” currently means active agentic workflows/tasks plus configured role bindings
- it does **not** yet mean worker-thread occupancy or per-model live concurrency

Read APIs behind the control-plane UI:

| Endpoint | Returns |
|---|---|
| `GET /api/v1/agentic/projects/{project_id}/plan-items` | normalized project plan rows |
| `GET /api/v1/agentic/tasks/{task_id}/runs` | started/final task run history |
| `GET /api/v1/agentic/tasks/{task_id}/approvals` | persisted human decisions |
| `GET /api/v1/agentic/memories?scope_type=project&scope_id=...` | project-scoped distilled memory |
| `GET /api/v1/agentic/memories?scope_type=task&scope_id=...` | task-scoped distilled memory |

Control-plane verification drills:

- `python3 mcp/tests/drill_agentic_control_plane_api.py`
- `python3 mcp/tests/drill_agentic_control_plane_ui.py`
- `python3 mcp/tests/drill_agentic_control_plane_chain.py`
- `python3 mcp/tests/drill_admin_agentic_summary_panel.py`

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
mcp/tests/drill_*.py               # drill catalog (150 total, 82 tier-1 readonly)
```

## Composes with

- **`~/.claude/policies/autonomous-feature-loop.md`** — the policy that defines activation, stop conditions, iteration shape
- **`~/.claude/CLAUDE.md`** §42 (operational autonomy), §43 (drill discipline), §49 (compose-footer)
- **`docs/architecture/adr/014-autonomous-loop-architecture.md`** (ADR-014) — the advisory contract that lets failing commits land but logs them
- **`docs/architecture/adr/015-ratchet-pattern-for-discipline-drift.md`** (ADR-015) — the ratchet pattern (grandfather current drift, gate growth, reward shrinkage); applies to drill catalog discipline + UI scope grants + future per-rule sets
- **`docs/architecture/adr/016-parallel-agent-allocation-for-independent-n-file-work.md`** (ADR-016) — when to spawn parallel agents (5 preconditions) vs single-thread; three allocation patterns observed across phases 5S, 6C, 6J, 6K
- **`docs/architecture/adr/017-forward-looking-checks-and-sweep-before-commit-discipline.md`** (ADR-017) — anti-pattern: drill assertions that say "X is the latest" or "exactly N items"; structural rewrites + sweep-before-commit discipline that catches the regression at iteration time, not verdict-log time
- **`docs/architecture/adr/018-three-way-work-allocation-operator-vs-parallel-tool-vs-autonomous-loop.md`** (ADR-018) — names the three actors (operator, parallel content-stream, autonomous loop) and which work allocates to whom; allocation table covers sudo, secrets, scope grants, multi-file refactors, drills, ADRs, doc maintenance
- **`docs/architecture/adr/019-graceful-degradation-of-loop-tooling.md`** (ADR-019) — every operator-facing script must handle 5 failure modes gracefully (missing input file, bad timestamp, malformed JSON, daemon transient state, missing executable); operator-facing UX rule: one-line stderr explanation per degradation event
- **`docs/architecture/adr/020-parallel-tool-commit-drill-audit.md`** (ADR-020) — every parallel-tool-authored commit (per ADR-018) must trigger a drill-audit pass within ≤2 autonomous-loop iterations; audit checks drill existence + negative assertion + convention compliance + project-rule audit (no hardcoded URLs, pinned deps, parameterized SQL); paydown ratchet pattern per ADR-015
- **`docs/architecture/adr/021-pre-shipped-drill-audit-cadence.md`** (ADR-021) — inverted-cadence pattern observed 3x (G-3/G-4/G-5): autonomous-loop pre-ships audit drills BEFORE parallel-tool's source commit when intent is visible; iteration-latency=0 + time-latency<0; tier-1 readonly drills enable this via AST-based source inspection; behavioral drills follow source-then-audit cadence per ADR-020
- **`docs/runbooks/council-telemetry.md`** — the deeper runbook for the 5K-5BB telemetry surface
- **`docs/runbooks/agentic-control-plane.md`** — focused runbook for the normalized agentic project/task/approval/memory chain and the `/admin/agentic/control-plane` UI
- **`docs/NEXT_POLICY.md`** — the session ledger; every phase entry includes drill score
