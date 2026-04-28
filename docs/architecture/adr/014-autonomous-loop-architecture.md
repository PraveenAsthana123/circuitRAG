# ADR-014: Autonomous loop — deterministic gate + LLM augmentation, advisory not blocking

## Status

Accepted — landed across 24 commits this session (`ae28816` →
`d2fefc0`). All ungated phases shipped; remaining gates require
external infrastructure (API keys, Ollama Cloud) or new §7 entries.

## Context

The session built an autonomous loop that:

* **Captures** every code commit's diff (Phase 2A `git_capture.py`)
* **Reviews** captured diffs through a 3-author / 1-reviewer / 1-chair
  council (Phase 2D `council.py` composing AgentBoard `ae28816`)
* **Persists** events + per-author telemetry (Phases 1A + 2E in
  `memory.py`)
* **Distills** rated events into reusable patterns (Phase 2C
  `distillation.py`)
* **Gates** iteration continuation via a deterministic 5-rule
  `LoopWatcher` (Phase 4A) fed by a drill-status writer (Phase 4C),
  triggered by a post-commit hook (Phase 4B), with a verdict-replay
  + auto-revert path (Phase 4D)
* **Surfaces** the chain to operators via a static HTML dashboard
  (`render_dashboard.py`) embedded in a Next.js Server Component
  (`/admin/sidecar`) with C4 + scenario data-flow diagrams at
  `/admin/sidecar/deep` (Phase 5B)
* **Drains** backlogs of `--no-council` events through a batched
  replay using DispatchPool's bounded-concurrency primitive
  (Phase 2A3 + 3B)

The central architectural decision wasn't about any single piece —
it was about how the pieces compose. Two competing shapes were
plausible:

**Shape A — LLM-driven gate**: a persistent agent watches the
repo, reads every commit, decides whether to proceed via a chair
LLM call. Single source of truth in the model.

**Shape B — Deterministic gate + LLM augmentation**: the gate
itself is pure-Python rules over structured artifacts (commit
metadata + drill output + ledger state). LLM agents handle the
semantic work (code review) but never gate iteration; the chain
between them is replayable byte-for-byte.

This ADR captures the choice of Shape B + its consequences.

## The trade-off

**Reproducibility**: Shape A produces a different verdict on
identical inputs because LLMs are non-deterministic. Two runs of
the same commit could APPROVE / REJECT / HOLD differently. Shape B
produces the same verdict every time — re-replaying the verdict
log against the same drill state yields the identical outcome.

**Latency**: Shape A's gate requires an LLM call per commit
(~5-30s on local Ollama, more on cloud). Shape B's gate runs in
milliseconds (regex + JSON parse + dispositions table). At commit
frequency, the difference compounds: 100 commits × 20s = 33 min of
LLM time, vs <1s of rule evaluation.

**Drillability**: Shape A can only be probabilistically tested
("90% of obvious-bad inputs reject"). Shape B is unit-testable
with synthetic inputs producing exact outputs — every rule is one
drill assertion.

**Audit reconstruction**: Shape A's "why did the loop reject this
commit?" requires replaying the model + the prompt + the inputs.
Shape B's REJECT verdict carries `rule_fired` (1-6) — the audit
row pinpoints which of the 5 rules tripped without a model call.

**Cost under failure**: Shape A's failure mode is silent — model
gives a confidently wrong APPROVE on a clearly broken commit. Shape
B's failure mode is loud — a rule mismatch is a Python AssertionError.

## Decision

The loop's gate is **deterministic Python rules** (`LoopWatcher`)
over **structured artifacts** (commit metadata, drill outcome,
file disposition). LLM agents (the council) handle semantic work
that genuinely benefits from natural-language reasoning — code
review across 3 specialised authors with chair synthesis. The
**chain between them is replayable**: every event row + council_run
row + verdict log line is JSON-shaped, idempotent, and can be
re-derived from the inputs.

Specific commitments:

1. `LoopWatcher.decide()` is pure Python, no LLM call. Returns
   ApprovalDecision with `rule_fired` ∈ {1..6} for audit.
2. Council runs (LLM-bound) write structured telemetry to
   `advisor_council_runs`, joined to events by `event_id` FK.
3. Post-commit hook is **advisory** — exits 0 always, never
   blocks. The verdict log is the operator's decision input,
   not the gate.
4. Destructive operations (revert, prune) default to **dry-run**;
   `--apply` is the explicit consent.
5. `find_events_without_council_run` derives the worklist from
   the JOIN, not from a "reviewed" boolean column — single source
   of truth for "what's pending."
6. Per-event error isolation is the universal contract: one
   event's council error doesn't sink siblings.

## Consequences

**Positive**:

* Reproducibility: replay any verdict-log entry against the same
  drill status + matrix, get identical decision.
* Speed: gate runs in <1ms per commit; the LLM-bound council runs
  asynchronously in the post-commit hook (advisory).
* Drill-locked: 39 tier-1 drills, 272 cumulative steps. Every
  invariant is one drill assertion away.
* Operator-friendly: REJECT verdict says exactly which rule fired
  and on which file; no LLM-prompt forensics.
* Composable: each piece is one Python module + one CLI script +
  one drill. Adding a 6th rule is one new branch in `decide()` +
  one new drill step.

**Negative**:

* The deterministic gate is intentionally rigid. A commit that
  edits `services/governance-svc/` (gated per matrix row 18)
  ALWAYS holds — even if the change is trivially safe. The
  alternative (LLM evaluating "is this safe?") would be more
  permissive but less predictable.
* The chain has many pieces (Phases 1A through 5B). Onboarding
  cost is the per-iteration drill output; the C4 deep-dive page
  exists specifically to amortise that cost across operators.
* Tier-1 drills run in <30s wall but are not zero-cost. The full
  resource-aware suite (drills-stack tier 3a) takes longer; a
  fresh box can't gate a commit until tier-1 enrolment is set up.

**Risks accepted**:

* The deterministic gate's rules are encoded as Python — a future
  refactor that "cleans up" `LoopWatcher.decide()` could subtly
  reorder rule priority. Step 8 of `drill_loop_watcher.py`
  explicitly locks the rule-1-wins-over-rule-2 priority; without
  that drill the regression would be silent. Mitigation: §43
  drill discipline + §44.6 same-file-3+iter red flag.
* The matrix in `NEXT_POLICY.md §1.5` is the source of truth for
  scope, but it lives in markdown (regex-parseable, not strict-
  schema). A row with a typo'd disposition (`pre-aproved`) would
  fall into the "unknown" bucket and silently get gated.
  Mitigation: `drill_next_policy_structure.py` step 5 enums the
  disposition value against `{pre-approved, gated, never, pending,
  denied}`.
* The post-commit hook's advisory contract means a REJECTed commit
  STILL LANDS. If the operator doesn't run `replay_verdict_log
  --apply`, broken commits accumulate. Mitigation: the dashboard
  surfaces unreplayed REJECTs visibly; the §44 autonomous loop
  policy adds a "stop on drill fail" trigger that pauses the loop
  when verdicts go red.

## Alternatives considered

**Alternative 1: LLM-driven gate (Shape A above).** Rejected for
reproducibility + speed reasons. The operator's most common
question — "why did the loop reject this commit?" — needs a
deterministic answer, not "the model thought it should."

**Alternative 2: Pre-commit hook (blocking).** Rejected because
post-commit can inspect HEAD; pre-commit can't. To gate at commit
time you'd need to inspect the staged diff, but the council needs
the FULL committed state for context (file paths, neighboring
files). Post-commit gives the right inputs at the cost of
"advisory only" — which we accept as the right trade.

**Alternative 3: Centralized service for the loop (instead of
scripts + cron).** Rejected because operators run this on their
own machines, not on shared infra. Each script is a single Python
file invokable via cron or CI; a service would need its own
deployment, monitoring, etc. The current shape (scripts + cron +
local SQLite) deploys with `git clone`.

**Alternative 4: Python ORM (SQLAlchemy) instead of raw SQL.**
Rejected per CLAUDE.md §3 ("no ORM for SQLite"). The schema is
small (3 tables), the queries are simple (LEFT JOIN, COUNT, INSERT).
ORM overhead would obscure the actual SQL behind a layer that
doesn't help the operator inspect what's happening.

## References

Phase commits in chronological order:

| Phase | Commit | Title |
|---|---|---|
| Board-1 | `ae28816` | AgentBoard parallel pattern + drill |
| Board-2 | `c6fa110` | AgentBoard observability |
| Sidecar-1A | `12953bd` | Sidecar Advisor backend + Ollama catalogue |
| Sidecar-2D | `4aa7bcd` | pr_review delegates to AgentBoard council |
| Sidecar-2C | `05b17a2` | Memory pattern distillation |
| Sidecar-2E | `ca4115a` | Council telemetry → audit table |
| Policy-1 | `058f22c` | NEXT_POLICY ledger + Kimi K2 catalogue |
| Phase-3A | `adc618c` | multi_hop_agent parallel sub-query fanout |
| Phase-3B | `ae06ded` | DispatchPool — 100+ task fanout |
| Phase-3D | `069b7ed` | agents/ registry + policy_approver |
| Phase-3E | `aab7b65` | 40-row proposed-approvals matrix |
| Phase-3C | `19d3051` | BulkPrReview = DispatchPool × council |
| Phase-4A | `901d81f` | LoopWatcher deterministic gate |
| Phase-4B | `f02f556` | post-commit hook auto-fires LoopWatcher |
| Phase-4C | `f905ae1` | drill-status writer (rule 1 input) |
| Phase-4D | `22c278e` | verdict-log replay + opt-in --apply revert |
| Phase-2A | `5655d4e` | git-diff capture |
| Phase-2A2 | `1ba5f42` | capture_and_review pipeline |
| Phase-2F | `dfddcd4` | council retention purge |
| Phase-2A3 | `4f5d4db` | batched council replay against unreviewed events |
| Phase-1B-static | `9661753` | HTML dashboard renderer |
| Phase-1B | `b140146` | Next.js Server Component dashboard |
| Phase-5A | `06bed6c` | e2e meta-drill + capture/event update gap fix |
| Phase-5B | `d2fefc0` | sidecar deep-dive C4 + scenario data flow |

Related ADRs: `011-drill-pattern-real-stack-no-mocks.md` (drill
discipline applies to every Phase here),
`012-orchestration-layer-local-first.md` (the loop runs locally;
no shared infra).

Related global policies: `~/.claude/policies/autonomous-feature-loop.md`
(§44), `~/.claude/policies/autonomy-operations.md` (§42),
`~/.claude/policies/drill-testing-pattern.md` (§43).

UI: `services/frontend/app/admin/sidecar/deep/page.tsx` —
operator-facing C4 + per-scenario sequence diagrams.
