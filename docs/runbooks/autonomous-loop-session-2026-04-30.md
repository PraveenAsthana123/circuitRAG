# Session retrospective — 2026-04-30 autonomous-loop

> 25 commits across ~6 hours (UTC midnight rollover mid-arc) ·
> 0 ADRs · 18 new readonly drills · 104/104 readonly green at
> session pause · ADR-020 SLO tightened 2 → 1 · 100-drill
> milestone crossed · 5 cascade-handling iterations
>
> Operator-facing reference for what shipped, what was learned,
> and what's left. Composes with 2026-04-28 + 2026-04-29
> retrospectives; Arcs 9-12 continue from yesterday's Arc 8 close
> (Phase 7G).

## What shipped, by arc

### Arc 9: ADR-020 audit infrastructure buildout (Phases 7H–7M, 6 commits)

After Phase 7G's coordination retrospective, the next cluster
built the measurement infrastructure that ADR-020 (Phase 7F)
described in text. Each phase added one observability layer:

* **7H** (`652ffb5`) — `drill_resource_tag_integrity`: catalog
  honesty meta-drill. 155 drills scanned via AST; tag ↔ import
  consistency locked. Reverse-only direction (import → tag) for
  precision; `:read` sub-scope semantics formalized for
  transitive consumption.
* **7I** (`640312f`) — `drill_tts_proxy_route`: first practical
  ADR-020 audit landing on G-2's TTS proxy. 8 patterns checked:
  POST/GET exports, MAX_TEXT_CHARS=4000, audit log, env-sourced
  OPENAI_API_KEY, 4-provider chain, failover_chain stamping.
* **7J** (`f5349a1`) — `drill_adr020_audit_cadence`: binary
  "audited yet?" check + auto-discovery of new G-N commits.
  PARALLEL_TOOL_COMMITS registry introduced.
* **7K** (`cb31ab6`) — `drill_secret_format_audit`: project-wide
  secret-shape scan. 6 patterns (OpenAI, Anthropic, AWS, GitHub,
  Google, Slack) × 7837 files. 1 fixture allowlisted
  (`AKIAIOSFODNN7EXAMPLE`).
* **7L** (`0a89334`) — `drill_adr_categorization` +
  LOOP_KEYWORDS lifted to module-level. Every ADR is DOMAIN
  (001-013) or LOOP-DISCIPLINE (slug matches keywords).
  Self-extending failure messages emit copy-pasteable hints.
* **7M** (`b2a7bf7`) — secret-format extended to 8 patterns
  (+Stripe live keys, +JWT). Test keys (`sk_test_`/`pk_test_`)
  intentionally not matched.

### Arc 10: Cascade-handling apprenticeship (Phases 7N–7T + G-4, 8 commits)

The session's most operational arc. Parallel-tool started
producing drills faster than the autonomous loop could audit
them, generating four consecutive cascades. Each iteration
applied the same canonical fix-template (NEGATIVE-marker
docstring + canonical `ALL N STEPS PASSED` banner + body
NEGATIVE comment).

* **7N** (`fa596e6`) — 2 parallel-tool drills audited:
  `drill_agentic_project_plan_persistence`,
  `drill_agentic_task_run_persistence`.
* **7O** (`6012c08`) — `_suggest_keywords` helper: drill_adr_
  categorization's failure message now emits copy-pasteable
  candidates ordered shortest-first (2-token, 3-token, ...,
  full-slug).
* **7P** (`473fc8e`) — 2 more parallel-tool drills audited:
  `drill_agentic_approval_persistence`,
  `drill_agentic_memory_persistence`.
* **7Q** (`6797e4d`) — cadence-drill latency measurement.
  `git rev-list --count <pt_sha>..<audit_add_sha>`.
  KNOWN_LATE_AUDITS grandfathered G-1 (10) + G-2 (9).
* **7R** (`ee94d8d`) — 3 more parallel-tool drills audited:
  control-plane api/chain/ui.
* **7S** (`be6051f`) — 1 more: `drill_admin_agentic_summary_panel`.
* **G-4** (`480dd3e`) — agentic control plane batch landed.
  19 files / +1793 LOC. ALL 8 audit drills already shipped
  before source code (true inverted cadence; latency=0,
  time-latency=-0.2h).
* **7T** (`b5691c4`) — register G-4 in ratchet. ADR-020 ratchet:
  3/3 audited, 2 in-SLO (G-3, G-4), 2 grandfathered (G-1, G-2),
  avg-iter-latency=4.8.

### Arc 11: Operational maturity (Phases 7U–7Z, 6 commits)

Built dashboards + named patterns + tightened gates.

* **7U** (`e4ec765`) — wall-clock time-latency in cadence drill.
  Reveals G-1 + G-2 audits landed within ~12h wall-clock despite
  9-10 iteration-latency. Two metrics, two lenses.
* **7V** (`b8c58c4`) — `parallel-tool-coordination.md` runbook.
  Names `next` / `drain` / `commit-as-is` / `pause` operator
  override signals. Documents the canonical fix-template +
  cascade response patterns + inverted-cadence worked example.
* **7W** (`ff5c580`) — `drill_drift_rate_dashboard`: parses
  `.loop/watcher.log` (214 raw entries / 89 unique commits at
  landing). Reports overall + recent APPROVE-rate, max
  consecutive REJECT streak, schema integrity.
* **7X** (`c36df2e`) — `drill_drift_volume_meta`: KNOWN_*
  ratchet visibility across catalog. Caught 2 function-local
  KNOWN_* in `drill_drill_catalog_discipline` on first run;
  hoisted both to module level.
* **7Y** (`8d31578`) — meta extended to DOMAIN_* categorization.
  Crossed **100/100 readonly drills milestone**.
* **7Z** (`b2cb910`) — `MAX_AUDIT_LATENCY` tightened from 2 to
  1. Threshold-side ratchet shrinkage — KNOWN_LATE_AUDITS isn't
  shrinkable (history fixed) but the gate is.

### Arc 12: G-5 + freshness gate (Phases 7AA–7DD + G-5, 5 commits)

* **7AA** (`f631dff`) — section7 drill structural rewrite +
  sidecar rating drift. Hardcoded `{page.tsx, deep/page.tsx,
  telemetry/page.tsx}` 3-entry expectation broke when
  `[eventId]/page.tsx` landed. Replaced with "≥3 entries +
  rel-path-derived route check." Auto-extends.
* **G-5** (`dde309b`) — sidecar event rating surface. Backend
  (Advisor.record_rating, memory.rate_event) + write API +
  per-event drill-down UI + lib/sidecar.ts client. 9 files,
  +680 LOC. Audit drill (`drill_sidecar_advisor_record_rating`)
  shipped in same commit (latency=0, true simultaneous).
* **7BB** (`f890ef8`) — register G-5 in ratchet. ADR-020 ratchet:
  5/5 audited, 3 in-SLO, avg-iter-latency=3.8 (was 4.8),
  avg-time-latency=+3.6h (was +4.5h). Both averages monotonically
  decreasing.
* **7CC + G-5.1** (`14c7616`) — Phase 1B-2 metadata columns
  (`rated_by`, `rating_notes`) + Vitest infrastructure +
  migration 003. 12 files. Includes drill drift drain (5th
  cascade fix: `drill_sidecar_rating_metadata`,
  `drill_sidecar_rating_route` — NEGATIVE markers + canonical
  banner).
* **7DD** (`14edae1`) — `drill_drill_status_freshness`: catches
  the stale-`.loop/last_drill_outcome.json` regression that
  caused Phase 7Z + 7AA's post-commit REJECTs. MAX_AGE=900s
  (1.5x the pre-commit hook's 600s TTL). Pre-bootstrap state
  short-circuits to PASS via ADR-019 graceful degradation.

## Lessons (the meta-pattern)

### Inverted cadence is the steady-state target

ADR-020 declared "≤2 iterations after parallel-tool commit."
G-3, G-4, G-5 all shipped at iteration-latency=0 — audit drills
landed BEFORE the parallel-tool's source code. This is the
fastest possible cadence; ADR-020's text didn't anticipate it.
The autonomous-loop pattern: when parallel-tool's intent is
visible (drill files dropped early signaling future work), the
loop pre-ships audits. Source code lands later; cadence drill
records latency=0 ("preexisting").

Phase 7Z's threshold tightening (2→1) was justified empirically:
3 consecutive G-buckets (G-3, G-4, G-5) shipped at lat=0, well
inside the new gate.

### Cascade handling vocabulary is now operator-facing

Phase 7V's runbook formalized `next` / `drain` / `commit-as-is` /
`pause` as the operator override signals. Before the runbook,
these were ad-hoc — `next` was just session-default, `drain`
was an intent I described once. Naming them creates a stable
API between operator and autonomous-loop.

All four observed in this session. `next` resumed after pause;
`drain` cleared the 4-drill cascade in 4 iterations (7N/7P/7R/7S);
`commit-as-is` was implicit in operator's "fix all" / "update
github"; `pause` was attempted once and overridden in seconds.

### Forward-looking-check anti-pattern showed up at every layer

ADR-017 named the pattern at the drill-assertion layer. This
session caught it at:

* **Drill output banner** (Phase 7C, 7M, 7AA): unnumbered or
  custom-formatted banner that doesn't match `RESULT_RE =
  r"ALL\s+(\d+)\s+.*STEPS\s+PASSED"`.
* **Drill step regex** (Phase 7D, 7M, 7W): `step("N. ...")` vs
  `step(f"N. ...")` — f-string prefix breaks the cohesion regex.
* **Allowlist cardinality** (Phase 7AA): hardcoded "exactly 3
  entries" instead of "≥3 + canonical floor."
* **KNOWN_* visibility** (Phase 7X): function-local declarations
  invisible to operator review.
* **Multi-line `step()` calls** (Phase 7Q, 7M): newline between
  `step(` and `"N. ..."` breaks the regex.

ADR-017's "structural beats specific" generalizes monotonically
across the stack. Each instance has the same shape: a hardcoded
specific is brittle; a structural rewrite survives growth.

### Drill ratchets at three different layers

ADR-015's ratchet pattern operates at:

1. **Grandfathered drift** (`KNOWN_NO_HELP=set()`): paid down
   over time toward 0.
2. **Threshold floors** (`MAX_AUDIT_LATENCY=1`, `MAX_CONSECUTIVE_
   REJECTS=5`): tightened over time toward stricter limits.
3. **Categorization floors** (`DOMAIN_ADR_NUMBERS={1..13}`):
   intent-to-track-reality, not paydown.

Phase 7Y's drift-volume meta-drill explicitly distinguishes
KNOWN_* (intent-to-shrink) from DOMAIN_* (intent-to-track) at
the metric layer. Conflating them hides the ratchet's purpose.

### Self-correcting drills compose with the advisory contract

Phase 7DD's freshness gate exemplifies a new pattern:

```
drill fails (stale snapshot)
→ pre-commit hook fires write_drill_status on next commit
→ snapshot refreshes
→ drill passes on next sweep
→ watcher sees fresh data → APPROVE
```

The drill itself triggers the corrective action. ADR-014's
advisory contract stays true (drill failure doesn't block
commit), but the system self-heals. Phase 7Z + 7AA's stale-
snapshot REJECTs would have been caught at sweep time before
the watcher fired had this drill existed.

### Cascade response: drain + commit-as-is is the operational mode

Five cascades observed (7N → 7P → 7R → 7S → 7AA → 7CC). The
pattern stabilized into:

* Parallel-tool drops drills with consistent drift shape
  (NEGATIVE marker missing / banner unnumbered / step()
  multi-line).
* Catalog discipline drills fire on first sweep.
* Autonomous-loop applies canonical fix-template within 1
  iteration.
* Catalog returns to clean state; drill count grows by N.

The cadence is sustainable as long as the producer-rate doesn't
exceed ~3 drills per autonomous-loop iteration. Beyond that,
yield to operator — `pause` / `commit-as-is` / new fix-template
upstream.

## What's deployed (delta from 2026-04-29 retrospective)

* All 25 commits pushed to origin/main; branch synced.
* G-4 (agentic control plane) in main: backend + migration 007 +
  control-plane UI + Sidebar entry. 8 audit drills cover.
* G-5 + G-5.1 (sidecar rating surface) in main: rated_by /
  rating_notes columns + Vitest infrastructure + per-event
  drill-down + write API.
* `chair.py` upgraded from `deepseek-coder:6.7b-instruct` to
  `kimi-k2:1t-cloud` (G-4 included this); SIDECAR_CHAIR_MODEL
  env override available for local fallback.
* New observability surfaces (5 drills):
  * `drill_resource_tag_integrity` — catalog tag ↔ import honesty
  * `drill_secret_format_audit` — 8 secret patterns × 7837 files
  * `drill_drift_rate_dashboard` — verdict log analytics
  * `drill_drift_volume_meta` — KNOWN_*/DOMAIN_* visibility
  * `drill_drill_status_freshness` — stale snapshot gate
* Coordination runbook: `docs/runbooks/parallel-tool-coordination.md`.

## What's still pending

| # | Type | What | Why |
|---|------|------|-----|
| A3 | Operator | Real Slack/Discord webhook URL | Pipeline + cron wiring complete; valid secret needed |
| ~~G-1..G-5~~ | Landed | All 5 G-buckets in main | Audited per ADR-020 |
| ~~B-1~~ | Approved | Phase 1B-2 write endpoints | G-5/G-5.1 SHIPPED IT — sidecar rating route is live |
| ~~B-2~~ | Approved | Phase 2B Claude/Codex routes | API keys still needed |
| ~~B-3~~ | Approved | Kimi-2 chair model | LIVE in chair.py since G-4; cloud subscription verifies |
| AR21 | Loop | ADR-021 codifying inverted-cadence + cascade patterns | Pattern observed 5x; ADR-worthy |
| TX | Loop | api-gateway G-4 verify (older menu item) | Tiny; absorbed in G-1 likely |

Phase 1B-2 (B-1 in pending matrix) was approved earlier as
"§7 POST/write-surface approval granted; implementation still
pending." G-5/G-5.1 IMPLEMENTED IT. The sidecar rating POST
endpoint at `/api/v1/sidecar/events/[eventId]/rating` is the
B-1 deliverable. Mark closed.

## Catalog status at session end

* Total drills: 174+ (was 150 at 2026-04-28 close)
* Tier-1 readonly: 104 (was 82)
* Pre-existing environmental drill flakes: 0 (still)
* Scripts in `scripts/`: 30 (29/29 conform; 1 added)
* ADRs: 20 (014-020 are loop-discipline; 001-013 are domain).
  No new ADRs this arc despite extensive operational learning —
  AR21 (inverted cadence) is the natural next.
* PARALLEL_TOOL_COMMITS registry: 5/5 audited (G-1 through G-5)
* Drift volume: 3 ratchet entries (HEALTHY) + 13 categorization
* Drift rate (recent 20 unique commits): 75% APPROVE
* Max consecutive REJECT streak: 5 (Phase 7Q-7R cascade, now
  grandfathered as floor)
* avg-iter-latency: 3.8 iterations (down from 6.3 at Phase 7Q)
* avg-time-latency: +3.6h (down from +4.5h)

## How to use this retrospective

* **For onboarding**: read top-down (Arcs 9-12) for the
  timeline; skip to Lessons for the meta-pattern.
* **For incident triage**: skip to the cheatsheet
  (`docs/runbooks/autonomous-loop-cheatsheet.md`) and the
  parallel-tool coordination runbook (Phase 7V).
* **For ADR-020 effectiveness**: run
  `python mcp/tests/drill_adr020_audit_cadence.py` for the
  current ratchet state with iteration + time-latency metrics.
* **For "is the loop healthy"**: `loop-status` (alias) or
  `python scripts/loop_status.py --json`. Plus
  `python mcp/tests/drill_drift_rate_dashboard.py` for verdict
  log analytics.

## Composes with

* **`docs/runbooks/autonomous-loop-session-2026-04-28.md`** —
  Arcs 1-4 (yesterday's session start).
* **`docs/runbooks/autonomous-loop-session-2026-04-29.md`** —
  Arcs 5-8 (yesterday's continuation; this retrospective picks
  up at Arc 9).
* **`docs/runbooks/autonomous-loop-cheatsheet.md`** — live
  reference; cheatsheet survives, this retrospective is dated.
* **`docs/runbooks/parallel-tool-coordination.md`** — Phase 7V's
  runbook; this retro's lessons section composes the meta-
  pattern observed across 5 cascades.
* **`docs/architecture/adr/014..020-*.md`** — seven loop-
  discipline ADRs. ADR-020 is the most-used in this session;
  Phase 7Q + 7T + 7U + 7BB all extend its enforcement.
* **`~/.claude/policies/autonomous-feature-loop.md`** — the
  policy this session demonstrated under cascade pressure.
* **`mcp/tests/drill_adr020_audit_cadence.py`** — the SLO
  enforcement drill itself.
