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
| 1.0 | **Agentic engineering framework setup** (meta-pattern: how each agent is designed, named, scoped, drilled, observed; matches user's "Agentic engineering framework setup" ask) | 8hr | sets the *shape* every Tier 1.x item must follow — so the framework doesn't drift across iterations. CrewAI / LangGraph supervisor / role+goal+backstory pattern + per-agent §52 brutal-tool-review row. |
| 1.1 | Pydantic CouncilProposal schema | ✅ DONE | structurally sound output |
| 1.2 | **Agent-lead-first routing** (manager agent decides: direct-fix vs council vs escalate vs skip) | ✅ DONE | `scripts/agent_lead.py` `decide_route(issue)` returns one of 5 routes (council_full / small_direct / tier_b / human / skip). Strategy-table-driven (model_tier='small' → llama3.2:1b direct, no council; 'default' → full 4-role; 'tier_b' → defer to Claude/Codex; 'human' → §50.5.3 skip). Cost-estimated per route. Wired into daemon `cycle_one()` BEFORE council fires. Drilled 8/8 with cost-ordering invariant. |
| 1.3 | **Per-rule fix-strategy table** | ✅ DONE | 18 rules in dispatch table; 6 categories (investigation, mechanical_rewrite, import_sort, type_fix, frontend_jsx, default) + security skip. F841 → ±30 lines + grep_refs; UP035 → ±5 lines no-grep; B*/S* → human-only. Wired into local_council.py AUTHOR prompt. Drilled 8/8 with 6 negative assertions. |
| 1.4 | **Adaptive context window (research → council)** | ✅ DONE | qwen2.5 RESEARCHER step fires before AUTHOR for investigation + type-fix rules (when `strategy.needs_grep_refs=True`); brief embedded in AUTHOR prompt. Token-efficient: skipped for mechanical rules. Graceful degradation if researcher errors. Drilled 8/8 with 6 negative assertions covering both gates (when-fires + when-skipped) + empty-brief omission + error-fallback. |
| 2.5 | Retry-with-feedback on first schema failure | 6hr | ~70% (one rejection → second corrected attempt) |
| 2.6 | Prior-fix RAG (retrieve past fixes as few-shots) | 8hr | ~85% (pattern-matching on past success) |
| 2.7 | Confidence-gated Tier-B fallback (Claude/Codex CLI) | 5hr | ~95% (low-confidence escalates) |

### Tier 2 — quality multipliers (~28hr)

| # | Item | Effort | What it solves |
|---|---|---|---|
| 2.8 | In-loop verification (REVIEWER sees actual ruff exit code) | 6hr | reviewer's critique grounded in real test output |
| 2.9 | Warm pool (3 Ollama models RAM-resident) | 4hr | cold-start latency 109s → 5s |
| 2.10 | Rollback tagging (every auto-commit has revert-tag) | 2hr | atomic revert if production weirdness ties to a daemon commit |
| 5.0 | **Verifiability framework**: technical (ruff/mypy/pytest) + business (scorecard) | 10hr | trust signal ≠ "it compiled"; matches user's "business + technical verification" ask |
| 7.0 | **End-to-end MCP hybrid** (research-svc + Ollama + Tier-B over MCP) | 15hr | matches user's "end-to-end architecture, hybrid approach with MCP" ask |

### Tier 3 — strategic compounding (~46hr)

| # | Item | Effort | What it solves |
|---|---|---|---|
| 3.11 | Preference-dataset capture (CHAIR selections → `.loop/preferences.jsonl`) | 5hr | input for LoRA fine-tune |
| 3.12 | Multi-file refactor support | 12hr | F841-style bugs that span files |
| 3.13 | Hallucinated-path validation | 1hr | already partial (schema does it); extend to grep-cross-check |
| 3.14 | Token-cost dashboard | 3hr | cost visibility at scale |
| 3.15 | **LoRA fine-tune pipeline (DL/NN setup)** | 25hr | matches user's "deep learning neural network" + "NN framework" asks |
| 3.16 | **RLHF / preference reinforcement framework** | 20hr | matches user's "reinforcement framework" ask. Prereqs: 3.11 preference capture + 3.15 LoRA pipeline. Operator's CHAIR selections become reward signal; PPO / DPO over deepseek-coder LoRA delta. Eval gate against held-out test set before promotion. |

### Tier 4 — meta / governance (~15hr)

| # | Item | Effort | Maps to |
|---|---|---|---|
| 4.0 | Drill for daemon §42 boundaries | 30min | regression guard |
| 4.1 | Daily rolling summary (`.loop/daemon_daily_report.md`) | 2hr | operator visibility |
| 4.2 | Apply-rate drift detection (uses §44 drift_detection module) | 4hr | alert if quality drops |
| 4.3 | Ownership matrix per agent | 3hr | §43 + §53 |
| 4.4 | Per-issue end-to-end run-book (matches "end-to-end per topic" ask) | 6hr | runbook per rule code |
| 4.5 | **Outcome-based evaluation framework** (judge iterations by measured apply rate / regression count / cost-per-fix, NOT by effort or activity) | 5hr | matches user's "outcome based approach" ask. Eval gate per iteration: an iteration that ships without moving the needle on apply-rate, regression-count, or operator-override-rate is rejected. Forces every commit to defend its outcome contribution. |
| 4.6 | **HITL framework — multi-gate operator scoring** (`scripts/hitl_framework.py` + drill) | ✅ DONE | matches user's "HITL framework, each advance level, more score" ask. 6 gate types (research/author/reviewer/advisor/apply/post_commit), 5 verdicts (approve/reject/edit/escalate/skip), preference-pairs export ready for Tier 3 LoRA/RLHF. Drilled 8/8 with extra='forbid' + edit-pair-required gate. |

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
| 5.9 | **Agent-task delegation management** | 8hr | matches "agent task delegation management". The supervisor's policy: which agent gets which task; load balancing; capability-matching; cost optimization. |
| 5.10 | **Agent-to-agent communication / A2A chat protocol** | 10hr | matches "Agent talk to another agent" + "agent to agent chat". Structured messaging between agents (CrewAI message-bus / MCP-over-stdio / pubsub). Each agent can request another agent's specialty; auditable transcript per request_id. |
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
