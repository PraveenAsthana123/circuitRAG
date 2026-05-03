# Autonomous Fix-Bot Roadmap

> **Status as of 2026-05-02**: structural pipeline complete (scan → council → drill-gate → apply → auto-commit → cron). **Apply rate: 0%** across 72 council attempts. The infrastructure is ready; the council layer needs Tier 1 #3 + #4 to start producing usable output.

## What ships today

| Component | Commit | Status |
|---|---|---|
| Issue scanner (ruff + mypy + bandit + eslint) | `~/.claude/scripts/issue_scanner.py` | working |
| Issue dispatcher (global, free-text council) | `~/.claude/scripts/issue_dispatcher.py` | working but produces 0% applicable |
| **Local schema-aware council** | `0ee79fc` | working (Tier 1 #1) |
| Pydantic CouncilProposal contract | `0ee79fc` | drilled 8/8 |
| Drill-gated apply (ruff check before commit) | `532435c` | working |
| **Auto-commit with §51 metadata, no §54 trailer** | `e516976` | working |
| **Cron installer (every 30 min)** | `e516976` | ready to install |
| Operator task-board (`scripts/agent_task_board.py`) | `532435c` | working |
| Always-active daemon (`scripts/autonomous_fix_daemon.py`) | `532435c` + hardening | working |
| Human-review queue export (`.loop/human_review_queue.md`) | `ed3abe2` | working |
| Escalation log (`.loop/escalations.md`) | `ed3abe2` | working |
| §42 push-gate enforcement | by-design | working |
| §50.5.3 security-rule skip (S* / B*) | `ed3abe2` | working |
| §54 no-trailer commit policy | global | working |

## What's left — sequenced by leverage

### Tier 1 — apply rate 0% → 80%+ (~26hr total)

| # | Item | Effort | Apply-rate impact |
|---|---|---|---|
| 1.0 | **Agentic engineering framework setup** (meta-pattern: how each agent is designed, named, scoped, drilled, observed; matches user's "Agentic engineering framework setup" ask) | ✅ DONE | `libs/py/documind_core/agentic_framework.py` — `AgentSpec` Pydantic schema with 11 fields (name, role_type Literal[8], model_tier, goal, backstory, tools, constraints, observability, drill_path, requires_research, output_schema). `validate_agent(spec, repo_root)` checks drill_path resolves on disk + constraints non-empty. 4 reference agents (researcher/author/reviewer/advisor) catalogued in COUNCIL_AGENT_SPECS, all validate. Drilled 8/8 with extra='forbid', name-pattern (kebab/snake), Literal role_type, phantom-path rejection. |
| 1.1 | Pydantic CouncilProposal schema | ✅ DONE | structurally sound output |
| 1.2 | **Agent-lead-first routing** (manager agent decides: direct-fix vs council vs escalate vs skip) | ✅ DONE | `scripts/agent_lead.py` `decide_route(issue)` returns one of 5 routes (council_full / small_direct / tier_b / human / skip). Strategy-table-driven (model_tier='small' → llama3.2:1b direct, no council; 'default' → full 4-role; 'tier_b' → defer to Claude/Codex; 'human' → §50.5.3 skip). Cost-estimated per route. Wired into daemon `cycle_one()` BEFORE council fires. Drilled 8/8 with cost-ordering invariant. |
| 1.3 | **Per-rule fix-strategy table** | ✅ DONE | 18 rules in dispatch table; 6 categories (investigation, mechanical_rewrite, import_sort, type_fix, frontend_jsx, default) + security skip. F841 → ±30 lines + grep_refs; UP035 → ±5 lines no-grep; B*/S* → human-only. Wired into local_council.py AUTHOR prompt. Drilled 8/8 with 6 negative assertions. |
| 1.4 | **Adaptive context window (research → council)** | ✅ DONE | qwen2.5 RESEARCHER step fires before AUTHOR for investigation + type-fix rules (when `strategy.needs_grep_refs=True`); brief embedded in AUTHOR prompt. Token-efficient: skipped for mechanical rules. Graceful degradation if researcher errors. Drilled 8/8 with 6 negative assertions covering both gates (when-fires + when-skipped) + empty-brief omission + error-fallback. |
| 2.5 | Retry-with-feedback on first schema failure | ✅ DONE | AUTHOR fires twice; pass-2 prompt embeds top-3 Pydantic ValidationError messages so model can correct itself. Bounded at 1 retry (cap cost). Audit row preserves both attempts; legacy "author" key aliases winner. Drilled 8/8: empty / prose-only / missing-field / extra-field / tokenizer-artifact all yield human-readable feedback. |
| 2.6 | Prior-fix RAG (retrieve past fixes as few-shots) | ✅ DONE | `scripts/prior_fix_rag.py` — pure-Python BM25 over `.loop/hitl_scores.jsonl` rows where verdict ∈ ('approve', 'edit'). Rule_code repeated 3× as soft exact-match boost. Wired into local_council `_prior_fix_section` → AUTHOR prompt few-shot. Zero-data behavior: empty index → empty section → no prompt bloat. Drilled 8/8: rejected-verdict rows NEVER returned (anti-theater); rule_code boost ranks UP035-tagged > E702-tagged with same text; render_few_shot returns '' for empty list. |
| 2.7 | Confidence-gated Tier-B fallback (Claude/Codex CLI) | ✅ DONE | `scripts/tier_b_fallback.py` — `should_escalate_to_tier_b()` fires on 3 triggers: (1) both local AUTHOR attempts schema-rejected, (2) validated proposal confidence < 0.6, (3) advisor alternative with ≥3 risks OR 'breaking' keyword. `try_tier_b()` invokes `claude` CLI then `codex` CLI; output runs through SAME CouncilProposal validator (no schema bypass). Graceful degradation: no Tier-B on PATH → None → daemon escalates to human-review queue. Drilled 8/8 with confident-proposal-no-theater anti-test. |

### Tier 2 — quality multipliers (~28hr)

| # | Item | Effort | What it solves |
|---|---|---|---|
| 2.8 | In-loop verification (REVIEWER sees actual ruff exit code) | ✅ DONE | `local_council._verify_diff_in_worktree(repo, diff)` applies AUTHOR's diff with `git apply -p0`, runs ruff, captures exit code + output (truncated 2KB), ALWAYS rolls back via `git apply -p0 -R`. REVIEWER prompt embeds the result so critique cites "ruff CLEAN" or "ruff still has issues (exit=1)\n<actual stdout>". Drilled 8/8 with worktree-byte-identical-pre/post invariant + verification=None bloat omission. |
| 2.9 | Warm pool (4 Ollama models RAM-resident) | ✅ DONE | `scripts/warm_council_pool.py` warms all 4 council models with `keep_alive=24h` (overrides Ollama's 5min default). Subcommands: `warm` (one-shot), `status` (read-only via /api/ps), `watch --interval 600` (re-warm every 10 min). Drilled 8/8: 4-model roster, keep_alive=24h enforced, /api/ps read-only, no destructive ops, --interval ≥60s. |
| 2.10 | Rollback tagging (every auto-commit has revert-tag) | ✅ DONE | Daemon tags every successful auto-commit `auto-apply-<sanitized-id>` after `git commit`. `_sanitize_tag()` strips git-ref-forbidden chars (~^:?*[\\). Tag failure non-fatal — emits `daemon:tag_failed` event; commit not rolled back. `scripts/revert_auto_apply.sh --list/--revert/--revert-range/--status` operator surface, §42-safe (creates new commit, never force-pushes). Drilled 8/8 with format-check (`git check-ref-format refs/tags/auto-apply-X`). |
| 5.0 | **Verifiability framework**: technical (ruff/mypy/pytest) + business (scorecard) | 🟡 partial — TECHNICAL layer ✅ DONE | `scripts/verifiability_framework.py::run_technical_verification()` runs ruff + mypy + pytest sequentially. Frozen `ToolResult` + `VerificationResult` Pydantic-style dataclasses. ANY failing layer → all_pass=False. Ruff is REQUIRED (no skip flag); mypy + pytest skippable per operator. `failure_summary()` operator-readable per-layer breakdown. CLI: `--json`, `--skip-mypy`, `--skip-pytest`, `--timeout`. Drilled 8/8 with frozen-mutation reject + missing-binary path + timeout path. BUSINESS layer (regression eval against golden set + per-rule scorecard) ⏳ deferred to v2; needs preference data + golden test set first. |
| 7.0 | **End-to-end MCP hybrid** (research-svc + Ollama + Tier-B over MCP) | 15hr | matches user's "end-to-end architecture, hybrid approach with MCP" ask |

### Tier 3 — strategic compounding (~46hr)

| # | Item | Effort | What it solves |
|---|---|---|---|
| 3.11 | Preference-dataset auto-capture (every council outcome → HITL row) | ✅ DONE | `hitl_framework.auto_capture_council_outcome()` writes a `verdict='auto_capture'` row per council fire (score=0 = operator-pending). `local_council.run_local_council` invokes it fire-and-forget at end of every cycle. New CLI: `hitl_framework.py review` lists pending rows for batch operator triage; transition path is `record <id> approve|reject|edit`. Drilled 8/8 with extra='forbid' preserved + fire-and-forget guard required. |
| 3.12 | Multi-file refactor support | 12hr | F841-style bugs that span files |
| 3.13 | Hallucinated-path validation | 1hr | already partial (schema does it); extend to grep-cross-check |
| 3.14 | Token-cost dashboard | 3hr | cost visibility at scale |
| 3.15 | **LoRA fine-tune pipeline (DL/NN setup)** | 25hr | matches user's "deep learning neural network" + "NN framework" asks |
| 3.16 | **RLHF / preference reinforcement framework** | 20hr | matches user's "reinforcement framework" ask. Prereqs: 3.11 preference capture + 3.15 LoRA pipeline. Operator's CHAIR selections become reward signal; PPO / DPO over deepseek-coder LoRA delta. Eval gate against held-out test set before promotion. |

### Tier 4 — meta / governance (~15hr)

| # | Item | Effort | Maps to |
|---|---|---|---|
| 4.0 | Drill for daemon §42 boundaries | ✅ DONE | `mcp/tests/drill_daemon_safety_boundaries.py` 8/8 with 6 negative assertions: no `git push`, no destructive ops (rm -rf / rmtree / unlink / os.remove), SAFE_PATH_PREFIXES enforced, S*/B* filtered, 3 state-mutating reject paths audit-logged + escalate() rolling log + human-review queue, no Co-Authored-By trailer in auto_commit_applied (regex match for actual `Co-Authored-By: x@y` pattern), 24 emit() events all single-line for Monitor/cron-tail. |
| 4.1 | Daily rolling summary (`.loop/daemon_daily_report.md`) | 2hr | operator visibility |
| 4.2 | Apply-rate drift detection (uses §44 drift_detection module) | 4hr | alert if quality drops |
| 4.3 | Ownership matrix per agent | 3hr | §43 + §53 |
| 4.4 | Per-issue end-to-end run-book (matches "end-to-end per topic" ask) | 6hr | runbook per rule code |
| 4.5 | **Outcome-based evaluation framework** (judge iterations by measured apply rate / regression count / cost-per-fix, NOT by effort or activity) | ✅ DONE | `scripts/outcome_eval.py` computes the 3 §55.3 metrics (apply_rate, regression_count, cost_per_fix_cents) over a 7-day window. Subcommands: `snapshot --label X` (capture pre-iter state + passing-drill set); `compare-to X` (BEFORE→AFTER diff; flags regressed drills); `report` (current state); `contract` (§55.3 compliance check on last commit message). Drilled 8/8: edge cases (0 attempts → 0.0 apply_rate no /0; 0 fixes → None cost_per_fix); cost-ordering (claude-cli ≫ local-Ollama); snapshot write+read+unknown-label graceful reject. |
| 4.6 | **HITL framework — multi-gate operator scoring** (`scripts/hitl_framework.py` + drill) | ✅ DONE | matches user's "HITL framework, each advance level, more score" ask. 6 gate types (research/author/reviewer/advisor/apply/post_commit), 5 verdicts (approve/reject/edit/escalate/skip), preference-pairs export ready for Tier 3 LoRA/RLHF. Drilled 8/8 with extra='forbid' + edit-pair-required gate. |

| 5.13 | **Notifications — multi-channel push** (Slack / email / WhatsApp / webhook) | ✅ DONE | `scripts/notifications.py` — Notification Pydantic schema (extra='forbid', Literal channel + severity); 4 adapters (slack via webhook, email via Gmail SMTP, whatsapp via Twilio API, generic webhook); each NO-OPs gracefully when env vars missing; fan_out NEVER raises (channel failures contained as DispatchResult). Drilled 8/8 with PII-blocking + zero-hardcoded-secrets source check. CLI: `--severity --title --body --link --channels slack,email`. |
| 5.14 | **Database MCP server** (expose orchestration.* tables as MCP tools for agents) | ⏳ 8hr | matches user's "database MCP" ask. MCP-server-stdio that exposes read-only SQL over `orchestration.agent_tasks` / `agent_task_runs` / `agent_approvals` / `decision_audit` (read-only; tenant-RLS-enforced; per-tenant scope check). Read-only by design — never `INSERT`/`UPDATE`/`DELETE` from MCP layer. Drilled with both directions (valid query passes; out-of-scope table rejected). |
| 5.15 | **Ollama MCP server** (expose local Ollama as MCP tools) | ✅ DONE | matches user's "MCP for ollama model" ask. `mcp/server_ollama.py` exposes 3 tools (ollama.generate / ollama.list_models / ollama.warm) on FastAPI with the standard `/health/live` `/health/ready` `/tools/list` `/tools/call` routes. Pydantic args schemas with extra='forbid' + temperature 0-2 + prompt ≤32K + keep_alive default '24h' for warm. Per-tool scopes ('ollama:generate' / 'ollama:read' / 'ollama:warm'). Drilled 8/8. |
| 5.16 | **Figma MCP server** (design-to-code; export Figma frames + components for the orchestrator) | ⏳ 12hr | matches user's "figma mcp server" ask. MCP server wrapping Figma REST API: tools for `figma.get_file`, `figma.export_node`, `figma.list_components`. Auth via Figma personal access token from env. Drill: schema rejection of malformed file IDs; rate-limit handling (Figma's 60/min cap). |
| 5.17 | **GitHub MCP server** (PR / issue / commit ops via MCP) | ⏳ 10hr | matches user's "github mcp server" ask. MCP server wrapping GitHub REST API: tools for `github.create_pr`, `github.list_issues`, `github.get_commit`, `github.add_comment`. Auth via GITHUB_TOKEN. §42 SAFETY: writes (create_pr, add_comment) gated; never `force-push` or `delete-branch`. Drill: scope-namespacing (github:read / github:write) + rate-limit retry + secret scrub. |

### Tier 5 — orchestration / management subsystems (added 2026-05-02 batch)

The user requested 9 management/orchestration concerns in rapid succession. Each is its own subsystem.

| # | Item | Effort | What it solves |
|---|---|---|---|
| 5.1 | **Swarm-of-agents orchestration framework** | 12hr | matches "orchestrate a swarm of agent framework setup". CrewAI / LangGraph supervisor + subtask fanout. Multiple AUTHORs in parallel; voting on best diff. |
| 5.2 | **Deployment sequence framework** | 8hr | matches "deployment sequence framework". Per-§47.7 4-layer rollback (app/db/AI/infra) wired to canary → blue-green → full-rollout sequence with health-probe gates. |
| 5.3 | **Workflow automation — different parts** | 6hr | matches "automate different part of workflow". Beyond the daemon: scan-dispatch-fix-commit-test-pr is the chain; this expands to also include `pr-creation-and-review` + `dependabot-merge` + `release-note-generation`. |
| 5.4 | **Bug management subsystem** | 10hr | matches "bug management". Bug-triage pipeline: discovery (issue-tracker integration) → severity classification → assignment to fix-bot OR human → resolution tracking → post-mortem capture. |
| 5.5 | **PR management subsystem** | 8hr | matches "PR management". Auto-PR creation after auto-commit; auto-review by Tier-B Claude; auto-merge gates (CI green + drill green + reviewer approval); branch cleanup. |
| 5.6 | **Error management subsystem** | 8hr | matches "error management". Production error stream → triage agent classifies → routes to fix-bot OR human → tracks incident lifecycle. Sentry / Honeybadger / OTel error spans as input. |
| 5.7 | **Task management subsystem** | 6hr | matches "task management". Beyond the issue queue: feature work / chore / spike tasks; dependency graph; Gantt-ish view; assignment to humans + agents in unified board. |
| 5.8 | **Agent monitoring & management subsystem** | 10hr | matches "agent monitoring management". Per-agent health (latency / cost / error rate / drift); auto-disable on drift > threshold; redeploy / replace / retire workflow. |
| 5.9 | **Agent-task delegation management** | ✅ partial (foundation) | `delegate_task()` helper in a2a_protocol.py wraps the connector for the agent-side ergonomics. AgentRegistry + AgentConnector cover lookup + routing. Load-balancing / cost-optimization policy still ⏳ (built on top of this foundation in next iter). Drilled together with 5.10. |
| 5.10 | **Agent-to-agent communication / A2A chat protocol** | ✅ DONE | `libs/py/documind_core/a2a_protocol.py` — 4 primitives: AgentRegistry (singleton catalog), A2AMessageBus (in-process transport with auditable transcript), AgentConnector (high-level ask API), delegate_task helper. AgentMessage Pydantic schema with extra='forbid' + name-pattern + Literal message_type. §50.5.3 enforced: human-tier targets rejected at delivery. Drilled 8/8 with 6 negative assertions: unregistered / human-tier / non-AgentMessage handler return / wrong in_reply_to / extra field / bad name pattern all rejected. |
| 5.11 | **Agent-first architecture** | 14hr | matches "Agent first architect". Meta-pattern: every new system feature is designed as "what agent owns this?" first, code second. Map every CRUD to an agent role; auto-derive C4 L3 component diagram from agent registry. |
| 5.12 | **Agent environment setup** (`scripts/setup_agent_env.sh` + drill) | ✅ DONE | matches "setup agent environment". Preflight + init for venv / pip deps / Ollama models / .loop dir / cron status / sanity scan. 8/8 drill including §42-boundary check (no git push). |

**Tier 5 total: 76 hours** for the 9 orchestration/management subsystems.

---

## Updated grand total

| Tier | Effort |
|---|---|
| Tier 1 (output structure) | 26 hr (1.0 = 8hr; 1.1 ✅ done; 1.2-1.4 = 13hr; minus 5hr ✅ done = 21hr remaining) |
| Tier 2 (quality multipliers) | 28 hr |
| Tier 3 (self-improvement) | 46 hr |
| Tier 4 (meta/governance) | 15 hr (4.6 HITL ✅ done = 10hr remaining) |
| **Tier 5 (orchestration/mgmt)** | **76 hr** |
| **TOTAL** | **~181 hours of remaining net-new engineering** |

22 distinct user asks. ~25 dedicated iterations at ~7-8hr each. **6-month roadmap for one engineer; 8-week for a 4-engineer team.**

---

## Total — and the honest answer to "how do I get to 100%"

**~150 hours of net-new engineering** to fully execute the 13 rapid-fire asks (11 prior + HITL framework + agentic-engineering-framework). HITL is ✅ DONE this commit. **Asymptotic 100%** apply rate; realistic ceiling ~95% sustained.

**Quickest visible win**: Tier 1 #3 (3hr) → moves apply rate from 0% to ~30% on mechanical ruff rules.

**Highest strategic compound**: Tier 3 #15 (25hr LoRA + 5hr preference capture prereq = 30hr) → self-improving system that gets better with every operator selection.

**For business verification (the user's specific ask)**: Tier 2 #5.0 verifiability framework (10hr) — a scorecard surface that distinguishes "technically passing" (ruff/mypy/pytest) from "business correct" (regression eval against golden set).

---

## How to read this doc

- This roadmap is the **single source of truth** for what's pending vs. what's shipped on the autonomous-fix-bot.
- Cross-references the brutal-feedback list from session `2026-05-01` (Tier 1 / 2 / 3 numbering preserved).
- Each iteration must produce: a code change + a drill (per §43) + a §51 metadata commit + zero Co-Authored-By trailer per §54.
- Status updates: when an item ships, mark its row with the commit SHA and move it to the "what ships today" section above.

## See also

- [`docs/architecture/maturity-stack.md`](maturity-stack.md) — §35 / §44 / §48 maturity progression
- [`scripts/autonomous_fix_daemon.py`](../../scripts/autonomous_fix_daemon.py) — the live runtime
- [`scripts/agent_task_board.py`](../../scripts/agent_task_board.py) — operator task board
- [`scripts/council_schemas.py`](../../scripts/council_schemas.py) — Tier 1 #1 schema
- [`scripts/local_council.py`](../../scripts/local_council.py) — Tier 1 #1 runner
- [`mcp/tests/drill_council_proposal_schema.py`](../../mcp/tests/drill_council_proposal_schema.py) — schema drill
- [`scripts/install_daemon_cron.sh`](../../scripts/install_daemon_cron.sh) — cron installer
- CLAUDE.md §50 (issue dispatcher) + §52 (brutal tool review) + §53 (enterprise maturity stack)
