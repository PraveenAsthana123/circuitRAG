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
| 1.1 | Pydantic CouncilProposal schema | ✅ DONE | structurally sound output |
| 1.2 | **Agent-lead-first routing** (manager agent decides: direct-fix vs council vs escalate vs skip) | 6hr | ~25% (cheap rules skip council overhead; complex routes correctly). Matches user's "agent lead first approach" ask. LangGraph supervisor pattern. |
| 1.3 | **Per-rule fix-strategy table** | 3hr | ~30% (mechanical rules now apply) |
| 1.4 | **Adaptive context window (research → council)** | 4hr | ~50% (F841-class real bugs become tractable) |
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

---

## Total — and the honest answer to "how do I get to 100%"

**~146 hours of net-new engineering** to fully execute the 11 rapid-fire asks (8 original + agent-lead routing + RLHF + outcome-based evaluation). **Asymptotic 100%** apply rate; realistic ceiling ~95% sustained.

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
