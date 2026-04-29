# Session retrospective — 2026-04-28 autonomous-loop

> ~70 commits across 14 hours · 6 ADRs · 71+ readonly drills green ·
> 4 cron lines deployed · 42 GB freed
>
> Operator-facing reference for what shipped, what was learned, and
> what's left.

## What shipped, by arc

### Arc 1: Telemetry surface (Phases 5K–5BB, 16 iterations)

Filter naming → histogram → weekly trend → daily snapshot → cron
installer → orchestrator → live UI sub-page → webhook → Prometheus
export → council retention prune → operator runbook.

Most operator-visible artifacts:

* `scripts/council_filter_stats.py` — filter histogram + alerts
* `scripts/council_stats_snapshot.py` — daily JSONL snapshot
* `scripts/install_snapshot_cron.sh` — idempotent cron installer
* `scripts/run_filter_pipeline.sh` — composed pipeline (5X)
* `/admin/sidecar/telemetry` — Server Component reading the snapshot
* `docs/runbooks/council-telemetry.md` — debug-a-REJECT walkthrough

### Arc 2: Discipline encoding (Phases 6A–6E, 5 iterations)

Cheatsheet → meta-drill → parallel-agent cleanup → ratchet pattern
→ JSONL retention pruner.

Most operator-visible artifacts:

* `docs/runbooks/autonomous-loop-cheatsheet.md` — session-wide reference
* `mcp/tests/drill_drill_catalog_discipline.py` — meta-drill enforcing §43
* `scripts/prune_loop_logs.py` — JSONL retention companion to 2F

### Arc 3: Drift detection + paydown (Phases 6F–6L, 7 iterations)

ADR-015 → drill_adr_commit_hash_resolution → drill_cheatsheet_cron_lines
→ PY_BIN fallback chain (failed-experiment recovery) → drill_catalog_inventory_tooling
→ KNOWN_AUDIT_DRILLS retirement + KNOWN_MISSING_NEG_MARKER paydown
→ docs+tooling integration.

Catalog ratchet state at end:

| Ratchet | Count | Status |
|---|---|---|
| KNOWN_MISSING (RESOURCES tag) | 0 | paid down |
| KNOWN_AUDIT_DRILLS | retired | files moved to `audit_*.py` |
| KNOWN_MISSING_NEG_MARKER | 0 | paid down |
| §7 sidecar scope-extension | 1 grant | healthy |

### Arc 4: Architectural reflection (Phases 6M–6V, 8 iterations)

ADR-016 (parallel-agent allocation) → ADR-017 (forward-looking-check
anti-pattern + sweep-before-commit) → drift cleanup + ADR coverage drill
→ cron-uses-venv drill → scripts-have-help drill → ADR-018 (three-way
allocation) → ADR-019 (graceful degradation) → THIS retrospective.

Six ADRs ship the loop's own architecture as durable artifacts:

| ADR | What it names |
|---|---|
| ADR-014 | Advisory contract: verdict log is safety net, sweep is gate |
| ADR-015 | Ratchet pattern: grandfather drift, gate growth, reward shrinkage |
| ADR-016 | Parallel-agent allocation: 5 preconditions + 3 patterns |
| ADR-017 | Forward-looking-check anti-pattern + sweep-before-commit |
| ADR-018 | Three-way work allocation: operator vs parallel-tool vs loop |
| ADR-019 | Graceful degradation: 5 failure modes + UX rule for stderr |

## Lessons (the meta-pattern)

### "Stop the question and do it"

§42 of CLAUDE.md grants pre-approval for almost everything in the
project boundary. The autonomous loop spent multiple iterations
asking permission for work that was already approved. The
operator's correction — "you have complete system approval" —
was the catalyst for ADR-018's allocation table. Net effect:
faster iteration cadence, less operator interruption.

### Drills lock the future, not the present

Every forward-looking drill assertion ("X is the latest", "exactly
N items", "Y doesn't yet exist") broke when the natural next
extension landed — Phase 5S, 5Z, 6F, 6G all hit this. The
structural rewrite ("X exists; numbering unique"; "≥N items with
canonical names listed") survives growth. ADR-017 names the
discipline.

### Sweep-before-commit > verdict log

ADR-014's advisory contract says verdict log is the safety net,
NOT the primary gate. Phase 5Z showed this concretely: a regression
slipped through to the verdict log; subsequent iterations needed
to reconcile. After 5Z every HBR commit ran the full readonly
sweep before committing — every regression since was caught at
iteration time, not after.

### Three-way work, not two-way

The session ran with three actors (operator, parallel content-
stream, autonomous loop). Pretending it was two-actor produced
friction. ADR-018 names the three with explicit allocation by
capability.

### Pay down ratchets when convenient

ADR-015's ratchet pattern accumulated grandfathered drift across
6B/6C/6D. Phase 6K + 6L (parallel content-stream's deliveries
integrated) paid two ratchets down to empty. Pattern: ratchet
catches drift; cleanup happens organically when the work is
already-needed.

### Graceful degradation > fail-fast (for operator scripts)

Bootstrap state is a first-class case. Pre-bootstrap, mid-migration,
post-cleanup, cross-environment — every script handles these
without crashing. ADR-019 lifts the pattern from "scripts happen
to do this" to "scripts MUST do this."

## What's deployed (in the operator's host)

* `/usr/share/ollama/.ollama` migrated to `/mnt/deepa/installed-software/ollama/`
  (42 GB moved off `/`; `--finalize` pending operator verification)
* Three cron lines installed:
  * `5 0 * * * council_stats_snapshot.py` (5N)
  * `0 4 * * 0 prune_council_runs.py --apply --vacuum` (2F)
  * `30 4 * * 0 prune_loop_logs.py --apply` (6E)
* `.venv` populated with 106 pkgs (httpx, asyncpg, prometheus_client,
  documind_core via editable install, etc)
* `~/.bashrc` aliases: `loop-status`, `loop-verdicts`, `loop-rejects`

## What's still pending

| # | Type | What | Why |
|---|------|------|-----|
| A1.5 | Operator | `migrate_ollama_to_deepa.sh --finalize` (after 1-2d) | Frees 42 GB on `/` |
| A3 | Operator | Slack/Discord webhook URL | Activates 5T alerting pipeline |
| G-1 | Gated | `services/agent-orchestrator-svc/` commit | Operator decision per ADR-018 |
| G-2 | Gated | `services/frontend/*` page edits | Outside §7 scope grant |
| B-1 | Gated | Phase 1B-2 write endpoints | New §7 grant for POST surface |
| B-2 | Gated | Phase 2B Claude/Codex routes | API keys |
| B-3 | Gated | Phase Kimi-2 chair model | Ollama Cloud subscription |

## Catalog status at session end

* Total drills: 142
* Tier-1 readonly: 71+ (every Phase X.0 commit reports `--only-readonly` count)
* Pre-existing environmental drill flakes: 2 (`drill_runner_junit`,
  `drill_tool_catalog_ttl` — need MCP service running; tag mismatch
  to clean up in a future iteration)
* Scripts in `scripts/`: 29 (22 conform to `--help` contract; 8
  grandfathered in `KNOWN_NO_HELP`)
* ADRs: 19 total (014–019 are loop-discipline; 001–013 are domain)

## How to use this retrospective

* **For onboarding**: read top-down (Arcs 1–4) for the timeline;
  read the Lessons section for the meta-pattern.
* **For incident triage**: skip to the cheatsheet
  (`docs/runbooks/autonomous-loop-cheatsheet.md`) and runbook
  (`docs/runbooks/council-telemetry.md`).
* **For architecture review**: read the 6 ADRs
  (`docs/architecture/adr/014..019-*.md`) in order.

## Composes with

* **`docs/runbooks/autonomous-loop-cheatsheet.md`** — the live
  reference; cheatsheet survives, this retrospective is dated.
* **`docs/runbooks/council-telemetry.md`** — deeper dive for
  the 5K-5BB telemetry surface.
* **`docs/NEXT_POLICY.md`** — the per-iteration ledger;
  retrospective abstracts; ledger is authoritative.
* **`docs/architecture/adr/014..019-*.md`** — six ADRs naming the
  loop's own architecture.
* **`~/.claude/policies/autonomous-feature-loop.md`** — the policy
  this session demonstrated.
