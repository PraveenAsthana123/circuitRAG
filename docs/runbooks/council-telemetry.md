# Runbook — council telemetry pipeline (Phases 5K–5AA)

> Operator's reference for the council-runs telemetry surface:
> snapshots, alerts, prometheus exports, daily cron, and the
> verdict-log chain. Companion to ADR-014 (advisory contract).

## What this is

The autonomous loop fires a council on every commit (Phase 2A2).
Each fire appends one row to `.loop/council_runs.log`. The
telemetry pipeline reads that log and exposes the data via five
operator-facing paths:

| Path | Phase | What it gives you |
|---|---|---|
| `council_filter_stats.py` (text) | 5K–5O | point-in-time histogram |
| `council_filter_stats.py --weekly` | 5M | per-week trend table |
| `council_stats_snapshot.py` | 5N | daily JSONL snapshot |
| `council_filter_stats.py --prometheus` | 5U | textfile-collector samples |
| `/admin/sidecar/telemetry` | 5S | live Server Component table |

The `run_filter_pipeline.sh` orchestrator (Phase 5X) composes
snapshot + prom export + alerts/webhook in one cron line.

## Files this references

```
.loop/
├── council_runs.log               # append-only JSONL; one row per council fire
├── council_stats_daily.jsonl      # one row per UTC date (5N writes)
├── watcher.log                    # one row per commit verdict (4B writes)
├── last_drill_outcome.json        # rolled-up drill status (5G writes)
└── dashboard.html                 # rendered dashboard (1B/embedded)

scripts/
├── council_filter_stats.py        # 5K-5W histogram / weekly / alerts / prom / webhook
├── council_stats_snapshot.py      # 5N daily snapshot writer
├── install_snapshot_cron.sh       # 5Q cron installer (dry-run by default)
├── run_filter_pipeline.sh         # 5X one-call orchestrator
└── git-hooks/
    ├── pre-commit                 # 5F refresh + 5Y HBR loud warning
    └── post-commit                # 4B watcher + 2A2 capture/council
```

## Daily operations

### Recommended cron line

Install once via `scripts/install_snapshot_cron.sh --apply`. The
default cron line:

```cron
5 0 * * * /mnt/deepa/rag/.venv/bin/python /mnt/deepa/rag/scripts/council_stats_snapshot.py
```

If you want the orchestrator (snapshot + prom export + alerts +
webhook in one fire), use `scripts/run_filter_pipeline.sh`:

```cron
5 0 * * * /mnt/deepa/rag/scripts/run_filter_pipeline.sh \
    --prometheus-out /var/lib/node_exporter/textfile/council.prom \
    --webhook-format slack \
    --alert-on "filtered>0.5" \
    --alert-on "too_short>0.5"
```

To avoid embedding secrets in crontab, store the webhook in:

```bash
cat > /mnt/deepa/rag/.loop/council-stats.env <<'EOF'
COUNCIL_STATS_WEBHOOK="https://REAL-WEBHOOK-URL"
EOF
chmod 600 /mnt/deepa/rag/.loop/council-stats.env
```

`run_filter_pipeline.sh` sources that file automatically before parsing flags.

### Manual histogram

```bash
# All-time outcome histogram
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py

# Last 7 days only
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --days 7

# Per-week trend (newest first)
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --weekly

# Last 4 weeks only
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --weekly --weeks 4

# JSON for piping
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --json
```

### Manual snapshot

```bash
# Snapshot yesterday (default)
/mnt/deepa/rag/.venv/bin/python scripts/council_stats_snapshot.py

# Snapshot a specific date
/mnt/deepa/rag/.venv/bin/python scripts/council_stats_snapshot.py --date 2026-04-28

# Read the deduped snapshot history
/mnt/deepa/rag/.venv/bin/python scripts/council_stats_snapshot.py --read
```

### Prometheus export

```bash
# Single-window samples (current state)
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --prometheus \
    --prometheus-out /var/lib/node_exporter/textfile/council.prom

# Per-week samples (week label)
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --prometheus --weekly \
    --prometheus-out council.prom

# Date-keyed historical samples (reads snapshot file, survives log rotation)
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py --prometheus --from-snapshot \
    --prometheus-out council.prom
```

## The verdict-log chain

Every commit produces ONE row in `.loop/watcher.log`:

```json
{
  "timestamp": "2026-04-28T19:24:48+00:00",
  "commit_sha": "1bbcf979cf5f",
  "commit_message_first_line": "fix(loop): Phase 5Y...",
  "files_touched_count": 3,
  "verdict": "APPROVE",
  "rule_fired": 6,
  "reason": "all rules passed",
  "blocking_files": [],
  "drill_outcome": "green",
  "drill_failures": []
}
```

`verdict` ∈ {`APPROVE`, `REJECT`}. Rule fired tells you WHICH of
LoopWatcher's rules fired the verdict (per Phase 4B):

| Rule | Description |
|---|---|
| 1 | drill_outcome=FAILED → REJECT (with drill_failures list) |
| 6 | all rules passed → APPROVE |

Tail it during ops:

```bash
tail -F .loop/watcher.log
```

## Debugging a REJECT — the 5S→5Z→5Y worked example

This actually happened during the autonomous loop session. It's
useful as a debugging template.

### What the operator saw

After committing Phase 5S (a UI iteration touching
`/admin/sidecar/deep/page.tsx` and adding `/admin/sidecar/telemetry/page.tsx`),
`watcher.log` showed:

```json
{"verdict": "REJECT", "rule_fired": 1, "drill_outcome": "FAILED",
 "drill_failures": ["drill_sidecar_deep_page", "drill_sidecar_nextjs_page"]}
```

### Step 1: re-run the named drills

```bash
/mnt/deepa/rag/.venv/bin/python mcp/tests/drill_sidecar_deep_page.py
/mnt/deepa/rag/.venv/bin/python mcp/tests/drill_sidecar_nextjs_page.py
```

Each drill prints the failing step with a clear message. In this
case:

- `drill_sidecar_deep_page` step 5: "expected 4 sequence diagrams,
  got 5" (the new SCENARIO_5 broke an assumption baked in at Phase 5B).
- `drill_sidecar_nextjs_page` step 8: "files outside §7-granted paths:
  {'telemetry/page.tsx'}" (added a new sub-page without updating the
  scope-grant whitelist).

### Step 2: decide — fix the drill or revert the change?

If the assertion was capturing real drift (the change is wrong),
revert. If the assertion was correct-at-the-time but the change
is intentional, **update the drill** and log the scope extension
in `docs/NEXT_POLICY.md` §7.

In Phase 5Z's case: the change was intentional (we wanted both
the new scenario and the new sub-page), so the drills got updated:

- step 5: count 4 → 5 (now 6 after Phase 5AA)
- step 8: added `telemetry/page.tsx` to `allowed_relative`
- §7: retroactive scope-extension log entry

### Step 3: refresh status + commit the fix

```bash
/mnt/deepa/rag/.venv/bin/python scripts/write_drill_status.py --only-readonly
# Should print "53/53 passed" or similar
git add ... && git commit -m "fix(loop): Phase 5Z..."
```

The next commit's verdict log should show APPROVE rule 6.

### Step 4: encode the prevention

Phase 5Y added high-blast-radius (HBR) detection to the pre-commit
hook so this exact regression class can't slip through silently
again. When `git diff --cached --name-only` matches:

```regex
^(services/frontend/app/admin/sidecar/|mcp/server.*\.py$|services/sidecar-advisor/)
```

the hook (a) forces a fresh drill refresh ignoring the staleness
cache, (b) prints a loud === banner naming any failing drills.

## CLI cheat-sheet

### Pre-approved scripts (no operator confirmation needed)

```bash
# Telemetry
/mnt/deepa/rag/.venv/bin/python scripts/council_filter_stats.py [--days N | --weekly | --prometheus | --json]
/mnt/deepa/rag/.venv/bin/python scripts/council_stats_snapshot.py [--date YYYY-MM-DD | --read]
scripts/run_filter_pipeline.sh [--dry-run | --skip-snapshot | --skip-prometheus]

# Health
/mnt/deepa/rag/.venv/bin/python scripts/loop_status.py
/mnt/deepa/rag/.venv/bin/python scripts/write_drill_status.py [--only-readonly]

# Drills
/mnt/deepa/rag/.venv/bin/python scripts/run_drills.py --list
/mnt/deepa/rag/.venv/bin/python scripts/run_drills.py --parallel 4 [--only <substr>]
```

### Operator-required (sudo or destructive)

```bash
# Cron management — modifies user crontab
scripts/install_snapshot_cron.sh --apply       # installs daily cron
scripts/install_snapshot_cron.sh --rollback    # removes managed line

# Migration — moves files across filesystems
scripts/migrate_ai_caches_to_deepa.sh --apply   # Tier-1 caches
scripts/migrate_ollama_to_deepa.sh --apply      # Tier-2 (sudo + systemd)
```

## Escape hatches

| Knob | Effect |
|---|---|
| `SKIP_DRILL_STATUS=1 git commit ...` | pre-commit hook skips drill refresh (bypass on emergency) |
| `STALE_AFTER=60 git commit ...` | tighter staleness window than the 600s default |
| `CAPTURE_NO_COUNCIL=1 git commit ...` | post-commit hook records event but skips LLM council |
| `[skip-council] in commit subject line` | filters the commit out of council review (Phase 5K cost discipline) |
| `git commit --no-verify` | bypasses the pre-commit hook entirely (last resort) |

## When things misbehave

| Symptom | First check |
|---|---|
| Verdict log shows REJECT but you don't know why | `tail -1 .loop/watcher.log` — `drill_failures` field names the drills |
| Council never fires on commits | `tail -F .loop/council_runs.log` while committing; `[skip-council]` in subject? |
| Snapshot file empty | `cat .loop/council_stats_daily.jsonl`; cron installed? `scripts/install_snapshot_cron.sh --status` |
| `--prometheus-out` writes blank file | `cat .loop/council_runs.log | wc -l` — empty log = no samples |
| Pre-commit hook hangs | `SKIP_DRILL_STATUS=1 git commit ...` to bypass while debugging |
| Webhook never fires | check `.loop/council-stats.env` or pass `--webhook URL`; alert with no URL is noop |

## Composes with

- **ADR-014** — the advisory contract that lets failing commits land but logs them
- **Phase 4B** — LoopWatcher rules (rule 1 = drill_outcome=FAILED → REJECT)
- **Phase 5F** — pre-commit drill status refresh
- **Phase 5Y** — pre-commit HBR detection + loud warning
- **`docs/NEXT_POLICY.md`** §7 — scope-extension log (must record any new UI surface)
- **`/admin/sidecar/deep`** — visual SCENARIO_1–6 sequence diagrams of the same flows
