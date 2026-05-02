# Agent Task Handover Plan

> **My (Claude's) decision** on which roadmap items go to local Ollama vs which I (Claude) must do, with sequencing.

Per user directive 2026-05-02: "you decide as agent ... and sequence them, handover which task can be done by ollama, and task you can do ... create plan and fix all in parallel"

---

## The brutal split

### Ollama can do (with current toolchain after Tier 1 #1.3 lands)

Once the per-rule strategy table is wired (this session), Ollama can autonomously fix:

| Rule category | Examples | Why Ollama can | Required preconditions |
|---|---|---|---|
| Mechanical rewrites | UP035, UP041, UP037, E702, E711, E712 | Rule message describes the literal fix; no investigation needed | ✅ Tier 1 #1.3 strategy table (this commit); ✅ Tier 1 #1.1 schema |
| Import sort | I001 | Pattern-deterministic (stdlib/3rd/1st/relative ordering) | ✅ Tier 1 #1.3 |
| Unused-import | F401 | Usually safe to delete | ✅ Tier 1 #1.3 |
| Frontend entity escapes | react/no-unescaped-entities | Mechanical replacement | ✅ Tier 1 #1.3 |

**Estimated apply rate after Tier 1 #1.3 wired** (this commit): **30–40%** on the categories above.

### Ollama can do AFTER Tier 1 #1.4 lands (~4hr)

| Rule category | Examples | Why needs more | Item that unlocks |
|---|---|---|---|
| Real-bug investigation | F841, F811 | Needs grep-refs context (already in strategy table) | Tier 1 #1.4 fully wires research-agent → council |
| Type fixes | mypy index, no-untyped-def | Needs broader context | Tier 1 #1.4 |
| Frontend hooks-deps | react-hooks/exhaustive-deps | Needs to see the entire component | Tier 1 #1.4 |

**Estimated apply rate after Tier 1 #1.4 wired**: 50–60%.

### Ollama cannot do (period)

| Rule category | Why | Routing |
|---|---|---|
| Security (S*, B*) | Per §50.5.3 — never to model | `is_human_only()` returns True; routes to `.loop/human_review_queue.md` |
| Multi-file refactors | Single-file diff format only | Tier 3 #3.2 (12hr) needed; today: human |
| API design / new features | No requirements baseline | Always Claude or human |
| Architectural decisions | Need cross-system understanding | Always Claude or human |

---

## What Claude (me) must do

### Tier 1 — apply-rate unblockers (Claude can ship in 1-2 sessions)

| # | Item | Effort | Why Claude not Ollama |
|---|---|---|---|
| ✅ 1.1 | Pydantic CouncilProposal schema | DONE `0ee79fc` | Schema design; multi-file change |
| ✅ 1.3 | Per-rule fix-strategy table | THIS COMMIT | Dispatch-table design; multi-file integration |
| 1.0 | Agentic engineering framework | 8hr | Meta-pattern; cross-cutting code |
| 1.2 | Agent-lead-first routing | 6hr | LangGraph supervisor; multi-agent design |
| 1.4 | Adaptive context window (research → council) | 4hr | Wiring research-agent into council |

**Tier 1 unfinished: 18hr of Claude work.**

### Tier 2 — quality multipliers (Claude or Tier-B Claude/Codex CLI)

| # | Item | Effort | Notes |
|---|---|---|---|
| 2.1 | Retry-with-feedback | 6hr | Wiring; Claude does it |
| 2.2 | Prior-fix RAG | 8hr | RAG infra; Claude does it |
| 2.3 | Confidence-gated Tier-B fallback | 5hr | Claude wires; Tier-B IS Claude/Codex |
| 2.4 | In-loop verification | 6hr | Claude wires |
| 2.5 | Warm pool | 4hr | Ops script; Claude does it |
| 2.6 | Rollback tagging | 2hr | Git tag protocol; Claude does it |
| 2.7 | Verifiability framework (technical + business) | 10hr | Schema + pipeline; Claude does it |
| 2.8 | End-to-end MCP hybrid | 15hr | MCP server design; Claude does it |

**Tier 2: 56hr of Claude work.**

### Tier 3 — self-improvement (Claude designs; Ollama runs the trained model)

| # | Item | Effort | Notes |
|---|---|---|---|
| 3.1 | Preference-dataset capture | ✅ schema done via HITL framework `e8c78ab`; 3hr remaining (auto-capture from task-board events) |
| 3.2 | Multi-file refactor support | 12hr | Claude designs; Ollama with new context can run |
| 3.15 | LoRA fine-tune pipeline | 25hr | Claude scripts; runs offline; produces a fine-tuned model the daemon then uses |
| 3.16 | RLHF (PPO/DPO) | 20hr | Claude scripts; runs offline; reuses LoRA infra |

**Tier 3: ~60hr of Claude work; output is a model Ollama serves.**

### Tier 4 — meta / governance

| # | Item | Effort | Notes |
|---|---|---|---|
| 4.0 | Drill for daemon §42 boundaries | 30min | Claude |
| 4.1 | Daily rolling summary | 2hr | Claude |
| 4.2 | Apply-rate drift detection | 4hr | Claude (extends §44 drift_detection module) |
| 4.3 | Ownership matrix | 3hr | Claude |
| 4.4 | Per-issue run-book | 6hr | Claude |
| 4.5 | Outcome-based eval framework | 5hr | Claude |
| ✅ 4.6 | HITL framework | DONE `e8c78ab` | Claude shipped this session |

**Tier 4 unfinished: 20.5hr of Claude work.**

### Tier 5 — orchestration / management subsystems

All design + most code is Claude work; Ollama agents become *participants* in the orchestrated system once it's built.

| # | Item | Claude effort | Ollama role |
|---|---|---|---|
| 5.1 | Swarm orchestration | 12hr | Each agent participates as a council member |
| 5.2 | Deployment sequence framework | 8hr | Tester / Deployer / Observer agents fire in sequence |
| 5.3 | Workflow automation | 6hr | Council fires per workflow stage |
| 5.4 | Bug management | 10hr | Triage agent classifies; council proposes |
| 5.5 | PR management | 8hr | Author proposes diff; Tier-B reviews; auto-merge after gate |
| 5.6 | Error management | 8hr | Triage agent classifies error stream |
| 5.7 | Task management | 6hr | Manager agent assigns tasks |
| 5.8 | Agent monitoring | 10hr | Health probes per agent |
| 5.9 | Task delegation | 8hr | Manager picks agent per task |
| 5.10 | A2A chat protocol | 10hr | Each agent participates |
| 5.11 | Agent-first architecture | 14hr | Defines how every new feature gets an agent owner |
| ✅ 5.12 | Agent environment setup | DONE `9857ae6` | — |

**Tier 5 unfinished: ~100hr of Claude work; Ollama agents participate.**

---

## Sequencing — do these in this order

### Phase A — unblock the council (Claude, 22hr)
1. ✅ Tier 1 #1.3 — strategy table (this commit)
2. Tier 1 #1.4 — adaptive context window via research-agent (4hr)
3. Tier 1 #1.2 — agent-lead-first routing (6hr)
4. Tier 1 #1.0 — agentic engineering framework (8hr)
5. Tier 4 #4.0 — drill for daemon boundaries (30min)
6. Empirical measurement: re-run council on 5 fresh ruff issues; expect 30-50% apply rate

**Outcome**: apply rate moves 0% → 30-50% measurably. First win under §55.3 outcome contract.

### Phase B — operational hardening (Claude, 30hr)
7. Tier 2 #2.1 retry-with-feedback (6hr)
8. Tier 2 #2.5 warm pool (4hr)
9. Tier 2 #2.6 rollback tagging (2hr)
10. Tier 2 #2.4 in-loop verification (6hr)
11. Tier 2 #2.7 verifiability framework (10hr)
12. Tier 4 #4.5 outcome-based eval (5hr) — closes the measurement loop

**Outcome**: apply rate stable 70%+ under load; production weirdness traceable.

### Phase C — self-improvement (Claude, 60hr; Ollama runs the trained model)
13. Tier 3 #3.1 finish preference auto-capture (3hr)
14. Tier 2 #2.2 prior-fix RAG (8hr) — reuses preferences
15. Tier 3 #3.15 LoRA fine-tune pipeline (25hr)
16. Tier 3 #3.16 RLHF / PPO / DPO (20hr)

**Outcome**: deepseek-coder + LoRA-delta beats stock; apply rate pushes to 95%+.

### Phase D — orchestration subsystems (Claude, 100hr)
17–28. All Tier 5 items in priority of leverage:
    - 5.5 PR management (closes local→GitHub loop) — 8hr first
    - 5.4 Bug management (issue-tracker integration) — 10hr
    - 5.7 Task management (unified board) — 6hr
    - 5.6 Error management — 8hr
    - 5.8 Agent monitoring — 10hr
    - 5.9 Task delegation — 8hr
    - 5.1 Swarm orchestration — 12hr
    - 5.10 A2A chat — 10hr
    - 5.2 Deployment sequence — 8hr
    - 5.3 Workflow automation — 6hr
    - 5.11 Agent-first arch — 14hr

**Outcome**: end-to-end autonomous engineering platform.

---

## "Fix all in parallel" — what's ACTUALLY parallelizable

| Items | Can run in parallel? | Why |
|---|---|---|
| Phase A items 2-4 (1.4, 1.2, 1.0) | ✅ within Claude | Different files, no shared surface |
| Phase B items 7-9 (2.1, 2.5, 2.6) | ✅ within Claude | Disjoint surfaces |
| Phase B + Phase A | ❌ no | Phase B depends on Phase A's apply rate baseline |
| Tier 5 items | ✅ many parallel | Most touch separate subsystems |
| Tier 3 #3.15 + #3.16 | ❌ no | RLHF needs LoRA infra first |

In a single Claude session, "parallel" practically means **multi-commit per response**, not concurrent. Each commit must individually pass drill + smoke before the next starts.

---

## What I refuse to do

- Build all 22 items in one session — quality drops to garbage
- Add roadmap items without sequencing them — that's the trap this session almost fell into
- Push to GitHub without explicit operator confirmation — §42 boundary
- Auto-apply Ollama proposals that don't pass drill-gate — §43 boundary
- Touch security rules with any model — §50.5.3 boundary

---

## What I commit to

- Each session: ship 2-4 well-scoped iterations from this plan
- Every iteration: code + drill + §51 metadata + §54 no-trailer
- Every iteration: defend its outcome under §55.3 (apply rate / regression count / cost-per-fix)
- Stop the session when the operator says stop OR when context drift threatens quality

The plan itself is the deliverable. Future sessions execute against it.
