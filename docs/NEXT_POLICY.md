# Autonomous Loop — Next Policy + Pending Ledger

> Source of truth for the autonomous loop running in this session.
> When the loop continues without explicit user instruction, this is
> what it picks from. Updated per-iteration as commits land.

This file composes with:

* `~/.claude/policies/autonomous-feature-loop.md` — global loop discipline (§44)
* `~/.claude/policies/autonomy-operations.md` — global autonomy gates (§42)
* `~/.claude/policies/drill-testing-pattern.md` — drill discipline (§43)
* `services/sidecar-advisor/policy.yaml` — runtime advisor policy

---

## 1. Pre-approved scope (what the loop can do without asking)

| Area | Pre-approved | Gated (asks first) |
|---|---|---|
| **Code in `/mnt/deepa/rag/`** | Edit, refactor, add files within `services/sidecar-advisor/` (incl. new `agents/` subdir), `services/inference-svc/app/agents/`, `libs/py/documind_core/`, `mcp/tests/`, `docs/`, `scripts/` | Edits to `services/governance-svc/`, `services/frontend/`, `services/identity-svc/` (other-team-owned surfaces) — ask if scope unclear |
| **Agent registry** | Add new agents under `services/sidecar-advisor/agents/<name>.py` exporting `AGENT = CoderAgent(...)`. Allowed roles: `author`, `reviewer`, `advisor`, `approver`. The registry's `__init__.py` is the single source of truth — every new agent appends to `ALL_AGENTS` (never reorder). | Adding a new ROLE category (5th role) — needs scope extension log |
| **Drills (§43)** | Add new `mcp/tests/drill_*.py` with `# RESOURCES:` tag + ≥1 negative assertion | Removing existing drills |
| **Ollama models** | `ollama pull` from the trusted registry (deepseek, codellama, starcoder, codegemma, qwen, mistral) | Models requiring Ollama Cloud subscription / external API keys |
| **Local dependencies** | `pip install --user --break-system-packages` for already-pinned packages (prometheus_client, pyyaml, httpx) | New top-level deps not already required by some service |
| **SQLite migrations** | Add `migrations/NNN_*.sql` under `services/sidecar-advisor/` (idempotent `CREATE TABLE IF NOT EXISTS`) | Modifying existing migrations |
| **Git** | Commit my own work with `Co-Authored-By: Claude` trailer; rename/move files via `git mv` | `git push`, `--force`, `--no-verify`, `git reset --hard`, branch deletion |
| **Documentation** | Write/update under `docs/`, `services/*/README.md`, this file | — |
| **Background tasks** | Spawn long-running processes (model pulls, builds) with explicit timeout | Production-affecting operations |

**Scope check:** if a contemplated change is outside the table above, the loop must either (a) write a one-line "scope-extension request" at the bottom of section 7 below and yield to the user, or (b) find a way to accomplish the task within scope.

---

## 1.5. Comprehensive proposed-approvals matrix

> Every action the loop *might* want to take, with explicit disposition. The `policy_approver` agent (registered in `services/sidecar-advisor/agents/policy_approver.py`) consults this table before allowing the next iteration to proceed.

| # | Action | Disposition | Why | What unblocks (if not already approved) |
|---|---|---|---|---|
| 1 | Add Python files under `services/sidecar-advisor/`, `libs/py/documind_core/`, `mcp/tests/`, `scripts/`, `docs/` | **pre-approved** | Day-zero scope; never touches other teams | — |
| 2 | Add new agent files under `services/sidecar-advisor/agents/<name>.py` (roles: author/reviewer/advisor/approver) | **pre-approved** | New agents append; `ALL_AGENTS` ordering preserved; drill enforces | — |
| 3 | Add new SQLite migrations under `services/sidecar-advisor/migrations/NNN_*.sql` (idempotent `CREATE TABLE IF NOT EXISTS`) | **pre-approved** | Local DB, idempotent; never touches prod | — |
| 4 | Add new drills under `mcp/tests/drill_*.py` with `# RESOURCES:` tag + ≥1 negative | **pre-approved** | §43 drill discipline; tier classification enforced by meta-drill | — |
| 5 | Edit/delete drills | **gated** | Removing a drill removes a regression-catch; needs review | Operator says "drop drill X" |
| 6 | Pull Ollama models from trusted registry (codellama, deepseek-coder, starcoder2, codegemma, mistral, qwen, nomic-embed-text) | **pre-approved** | Free; local disk only; sized to ≤ 10GB per model | — |
| 7 | Pull cloud-only Ollama models (`*-cloud` tags, e.g. kimi-k2) | **gated** | Needs Ollama Cloud subscription + token cost | Operator signs into Ollama Cloud |
| 8 | `pip install --user --break-system-packages <pkg>` for already-pinned deps (httpx, pyyaml, prometheus_client) | **pre-approved** | Already in some service's requirements.txt | — |
| 9 | Add a NEW top-level dep not already required by any service | **gated** | Dependency surface widens; needs reasoned doc | Operator OKs the dep |
| 10 | Edit Markdown anywhere (READMEs, ADRs, this file, `~/.claude/policies/`, skill files) | **pre-approved** | Documentation is part of the loop output | — |
| 11 | `git mv` files within the repo | **pre-approved** | Renames preserve history; drills updated in same commit | — |
| 12 | `git commit` with `Co-Authored-By: Claude` trailer | **pre-approved** | Per §42 autonomous policy | — |
| 13 | `git push` to remote | **gated** | External effect; affects shared state | Operator runs `git push` themselves OR explicitly authorizes |
| 14 | `git push --force` | **never** | Destructive; can rewrite shared history | Operator does it manually |
| 15 | `git reset --hard`, `git clean -fd`, branch deletion | **gated** | Destructive; can lose work | Explicit operator request |
| 16 | `git commit --no-verify` (skip pre-commit hooks) | **never** | Subverts §43 drill gate | — |
| 17 | Modify `.github/workflows/*.yml` | **gated** | CI infra; affects every PR | Operator OKs the change |
| 18 | Edit `services/governance-svc/`, `services/frontend/`, `services/identity-svc/` | **gated** | Other-team-owned surfaces | Explicit operator task targeting that service |
| 19 | Edit `services/inference-svc/app/agents/multi_hop_*.py` | **pre-approved** | Co-owned with this loop's work | — |
| 20 | Spawn background processes via `run_in_background: true` (model pulls, builds) | **pre-approved** | Bounded by explicit timeout | — |
| 21 | Spawn long-running daemons (Postgres, Redis, Kafka brokers) | **gated** | Affects ports + system state | Operator OKs |
| 22 | `sudo` anything | **gated** | Out-of-scope per §42 | Operator runs the command themselves |
| 23 | `rm -rf` on directories outside `/tmp/` and `/mnt/deepa/rag/.runtime/` | **never** | Destructive; can delete user data | — |
| 24 | Modify files outside `/mnt/deepa/rag/` (e.g. `/home/`, `/opt/`, system files) | **gated** | Scope explicitly bounded to repo | Explicit operator file path |
| 25 | Modify `~/.claude/policies/*.md` (global Claude policies) | **pre-approved** | Markdown edits are pre-approved per §42 | — |
| 26 | Modify `~/.claude/CLAUDE.md` (user's private global instructions) | **gated** | Persists across all projects | Explicit operator request |
| 27 | Read sensitive files (`.env`, credentials, `~/.ssh/`, `*.key`) | **never** | PII / secrets risk per §4.5 | — |
| 28 | Send HTTP requests to public endpoints (registry, GitHub API, npm, pypi) | **pre-approved** | Read-only metadata; no auth tokens | — |
| 29 | Send HTTP requests to authenticated endpoints (private API, paid services) | **gated** | Cost / external state | Operator provides credential + scope |
| 30 | Run drills that hit the production database | **never** | Per §42; production is read-only by default | — |
| 31 | Modify production Postgres (any environment marked `prod=true`) | **never** | Per §42 | — |
| 32 | Operate on `advisor.db` (Sidecar Advisor's local SQLite) — read, write, migrate, vacuum | **pre-approved** | Local-only; not shared state | — |
| 33 | Generate or modify cryptographic keys (Fernet, JWT secrets) | **gated** | Affects auth surface | Operator-supplied |
| 34 | Add a 5th agent role beyond `author/reviewer/advisor/approver` | **gated** | Role enum is the council's contract | Scope-extension log entry |
| 35 | Run mass-data operations on `advisor.db` (DELETE FROM, TRUNCATE) | **pre-approved** | Local-only; reversible | — |
| 36 | Ship a feature without a drill (§43 violation) | **never** | Drill discipline non-negotiable | — |
| 37 | Same-file commits 3+ iterations in a row (§44.6 red flag) | **gated** | Loop-thrashing signal | Pause + plan iteration |
| 38 | Skip `record_step` / metrics / audit-row write on AgentBoard runs | **never** | §38 governance — every AI decision auditable | — |
| 39 | Issue a "release" / version-bump tag | **gated** | Externally-visible | Operator runs the tag command |
| 40 | Open external network connection to LLM provider (OpenAI, Anthropic, etc.) | **gated** | Cost; auth | Operator provides API key |

**Disposition values:**
- `pre-approved` — loop may proceed without asking
- `gated` — loop logs a scope-extension request in §7 and yields
- `never` — loop refuses; surfaces "this is never autonomous" to operator
- `pending` — proposed but not yet decided (no row currently uses this; reserved for future proposals)
- `denied` — explicitly refused by operator (no row currently uses this)

---

## 2. The pending ledger

Format: each phase has `id`, `title`, `status`, `commits` (cumulative shipped), `drills` (lock count), `blockers`, and `composes_with`.

### Shipped this session (anchors)

| ID | Title | Commit | Drills locked |
|---|---|---|---|
| Board-1 | AgentBoard parallel pattern + drill | `ae28816` | 7 (4 negatives) |
| Board-2 | AgentBoard observability — metrics + structured log + prompt version | `c6fa110` | 8 (5 negatives) |
| Sidecar-1A | Sidecar Advisor backend + Ollama coder catalogue | `12953bd` | 8 (5 negatives) + 4 Ollama (1 negative) |
| Sidecar-2D | pr_review delegates to AgentBoard council | `4aa7bcd` | 8 (5 negatives) |
| Sidecar-2C | Rated-event → memory pattern distillation | `05b17a2` | 8 (5 negatives) |
| Sidecar-2E | Council telemetry → audit table | `ca4115a` | 8 (5 negatives) |
| Policy-1 | NEXT_POLICY ledger + Kimi K2 cloud-tier catalogue | `058f22c` | docs only |
| Phase-3A | multi_hop_agent parallel sub-question fanout | `adc618c` | 8 (6 negatives) |
| Phase-3B | DispatchPool — 100+ task fanout w/ bounded LLM concurrency | `ae06ded` | 8 (6 negatives) |
| Phase-3D | agents/ registry — 6 first-class agents (incl. policy_approver) | `069b7ed` | 8 (5 negatives) |
| Phase-3E | NEXT_POLICY 40-row proposed-approvals matrix + structure drill | `aab7b65` | 8 (5 negatives) |
| Phase-3C | BulkPrReview — DispatchPool × council for N-file PR review | `19d3051` | 8 (5 negatives) |
| Phase-4A | LoopWatcher — deterministic policy_approver gate | `901d81f` | 8 (6 negatives) |
| Phase-4B | post-commit hook auto-fires LoopWatcher; appends verdict log | `f02f556` | 8 (6 negatives) |
| Phase-4C | drill-status writer — populates .loop/last_drill_outcome.json | _this commit_ | 8 (6 negatives) |

**Cumulative:** 15 commits this session, 111 drill steps green across 14 board+sidecar+agent+policy drills, 30 zero-infra drills total in tier 1, 4 catalogued Ollama coder models locally installed (+ Kimi K2 documented as cloud tier).

### Queued (autonomous loop picks from here)

| ID | Title | Status | Composes with | Blocker |
|---|---|---|---|---|
| ~~3A~~ | `multi_hop_agent` parallel sub-query fanout | **shipped** in this commit | inference-svc | — |
| ~~3B~~ | DispatchPool — 100+ task fanout with bounded LLM concurrency | **shipped** `ae06ded` | AgentBoard + Sidecar council | — |
| ~~3D~~ | agents/ registry — first-class agent files; policy_approver added | **shipped** in this commit | Sidecar-2D | — |
| 1B | Sidecar **Next.js** UI (paste box → Review → Rate → audit history) | not started — uses existing `services/frontend/` App Router pattern | Sidecar-1A | — |
| ~~3C~~ | BulkPrReview composes DispatchPool × council | **shipped** in this commit | Phase-3B + Sidecar-2D | — |
| ~~4A~~ | LoopWatcher — deterministic policy_approver gate (5 rules) | **shipped** in this commit | Phase-3D approver agent | — |
| ~~4B~~ | post-commit hook auto-fires LoopWatcher; verdict log at .loop/watcher.log | **shipped** in this commit | Phase-4A | install: `scripts/install_loop_watcher_hook.sh` |
| ~~4C~~ | drill-status writer — populates .loop/last_drill_outcome.json | **shipped** in this commit | Phase-4B | run: `python3 scripts/write_drill_status.py --only-readonly` |
| 2A | Git-diff capture (file watcher → auto-classify on commit) | not started | Sidecar-1A | — |
| 2B | Claude / Codex routes for `architecture` event_type | not started | Sidecar-2D council | needs API keys (gated) |
| 2F | Council retention policy (purge advisor_council_runs > N days) | not started | Sidecar-2E | none |
| Kimi-1 | Document Kimi K2 in coder catalogue (cloud tier) | this commit | Sidecar-1A catalogue | none |
| Kimi-2 | Wire Kimi as Phase 3 chair model when Ollama Cloud signed in | not started | Kimi-1 | needs Ollama Cloud subscription (gated) |

### Decided-not-doing (with reason)

| ID | Title | Reason |
|---|---|---|
| — | Embedding-based fuzzy clustering in distillation | Phase 2C heuristic suffices until ≥ 100 rated events; embeddings risk silent wrong-clustering |
| — | LLM-based pattern naming | Same — heuristic exact-match for now, LLM rename later |
| — | Auto-write of council_run from advisor.review | Caller (UI / CLI) wires `record_event` + `record_council_run` sequentially; Phase 1B does this |

---

## 3. Tracking surface — what's monitored

| Signal | Where | What you see |
|---|---|---|
| **Drill suite** | `python3 mcp/tests/drill_*.py` per drill, `python3 scripts/run_drills.py --allow-resources= --list` for tier-1 enrollment | step-by-step pass/fail with negative assertions |
| **Tier classification** | `python3 mcp/tests/drill_ci_tier_definitions.py` | locks tier 1 ⊆ tier 2 ⊆ tier 3a chain; subset relation |
| **AgentBoard runs** | `documind_agent_board_runs_total{outcome,advisor_id}` Prometheus counter; structured log `agent_board_run` | live LLM call mix (ok / partial / advisor_failed / all_authors_failed) |
| **AgentBoard latency** | `documind_agent_board_duration_seconds` Prometheus histogram | p50 / p95 / p99 by outcome |
| **Council audit rows** | `services/sidecar-advisor/advisor.db` → `advisor_council_runs` table | per-draft model_used, scores, errors; queryable by `outcome`, `event_id`, `created_at`, `advisor_id` |
| **Memory patterns in use** | `advisor_memory.use_count` + `last_used_at` columns | which distilled patterns are LIVE vs. stale |
| **Pending ledger** | This file, section 2 | what the autonomous loop picks next |
| **Session commits** | `git log --since="6 hours ago"` | every iteration's commit hash + title |
| **Ollama coder models** | `ollama list \| grep -E "codellama\|deepseek-coder\|starcoder2\|codegemma"` | local-pulled model availability |
| **Disk usage** | `du -sh /usr/share/ollama/.ollama/models` | model storage growth |

---

## 4. Status convention (for ledger entries)

| Status | Meaning |
|---|---|
| `not started` | Queued; no commits yet |
| `scaffolded` | Some files exist but logic incomplete; not commit-ready |
| `in-progress` | Actively edited in the current iteration |
| `drilled` | Code complete + drill green; awaiting commit |
| `committed` | Landed in `main` |
| `paused` | Started, then deprioritised; resumable from current state |

---

## 5. Update protocol (per iteration)

After every commit the loop:

1. Adds an entry to section 2's "Shipped this session" table with the commit hash + drill-step count.
2. Removes / updates the entry in "Queued" if its status changed.
3. If a new pending item emerged from the iteration (e.g. discovered tech debt), adds it to "Queued".
4. Increments cumulative drill count.

This file's diff is part of every commit, not a separate housekeeping commit.

---

## 6. Track / tracking commands (operator cheatsheet)

```bash
# What's in tier 1 (zero-infra) — runs on every PR
python3 scripts/run_drills.py --allow-resources= --list

# Run all six board+sidecar drills
for d in drill_agent_board_parallel drill_agent_board_metrics \
         drill_sidecar_advisor drill_sidecar_pr_review_council \
         drill_sidecar_distillation drill_sidecar_council_audit; do
  python3 mcp/tests/$d.py 2>&1 | tail -3 | head -1 | sed "s|^|$d: |"
done

# Tier classification chain still locked
python3 mcp/tests/drill_ci_tier_definitions.py

# Council audit rows by outcome (last 100)
sqlite3 services/sidecar-advisor/advisor.db \
  "SELECT outcome, COUNT(*) FROM advisor_council_runs GROUP BY outcome"

# Memory patterns in use (decay watch)
sqlite3 services/sidecar-advisor/advisor.db \
  "SELECT pattern_kind, pattern_text, use_count, last_used_at \
   FROM advisor_memory ORDER BY use_count DESC LIMIT 20"

# Local Ollama coder models
ollama list | awk '/codellama|deepseek-coder|starcoder2|codegemma/'

# Session commits (this loop's output)
git log --oneline --since="6 hours ago"
```

---

## 7. Scope-extension log

When the loop wants to do something outside section 1's pre-approved scope, it logs the request here and yields. The user reviews and either grants or denies; granted requests get folded into section 1.

| Date | Request | Disposition |
|---|---|---|
| 2026-04-28 | Add `approver` as a 4th agent role (`policy_approver` watches the loop). User explicitly requested "one agent must track this and approve" + "if something missing the update the approval policy and go ahead". | **Granted in §1 inline** — `agents/` row now lists `approver` as a pre-approved role; landed in this commit (`Phase-3D`). |

---

## 8. Brutal rules (apply always)

1. **No commit without a drill.** Every feature commit ships with a drill that has ≥1 negative assertion (per §43).
2. **One thing per iteration.** A commit message that requires "and" between top-level concepts is a signal to split.
3. **Tier classification is sacred.** New drills tagged `# RESOURCES:` correctly; `drill_ci_tier_definitions` must stay green.
4. **Markdown edits are pre-approved.** This file, READMEs, ADRs — never ask permission.
5. **Composability beats novelty.** If the next phase can compose with a shipped commit (`ae28816`, `c6fa110`, `12953bd`, `4aa7bcd`, `05b17a2`, `ca4115a`), prefer that path over rebuilding.
