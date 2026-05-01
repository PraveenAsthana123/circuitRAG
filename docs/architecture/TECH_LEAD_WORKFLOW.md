# Tech Lead Workflow

> §19 mandate. Substantive content lives at:
>
> See: [`tech-lead-audit-checklist.md`](tech-lead-audit-checklist.md) — primary checklist
> See: [`tech-lead-audit-scorecard-and-report-template.md`](tech-lead-audit-scorecard-and-report-template.md) — scorecard + report shape
> See: [`production-trust-quality-and-readiness.md`](production-trust-quality-and-readiness.md) — 5-layer trust scorecard

## Daily / pre-merge cadence

```bash
# Pre-merge gate
cd services/frontend && npm run pre-merge   # lint + format + test + build
.venv/bin/python -m pytest libs/py/tests     # core lib unit tests
scripts/run_drills.py --parallel 4           # all drills
```

## Pre-release gate (CLAUDE.md §47.11)

See [`AI_GOVERNANCE_GUIDE.md`](AI_GOVERNANCE_GUIDE.md) for the 15
production gates and the HARD STOP list.

## Tech-lead audit (per release or quarterly)

1. **Architecture review**: every new container has an ADR + STRIDE
   table. Dependency graph (compose-footer drill) is green.
2. **Security review**: secrets scan + dep audit + threat model.
3. **AI review**: prompt versioning + eval baseline + guardrails
   per §38.6.
4. **Ops review**: logs + traces + alerts + runbook + ownership.
5. **Trust scorecard**: 5-layer per
   [`production-trust-quality-and-readiness.md`](production-trust-quality-and-readiness.md).

## Operator commands

```bash
# Drill catalog summary (which drills exist, which are passing)
python3 scripts/drill_catalog_summary.py

# Loop status (autonomous-loop iteration tracking)
python3 scripts/loop_status.py

# Coverage ratchet status (must only go UP)
python3 scripts/ratchet_status.py

# Issue dispatcher — local-model lint/type fixer (§50)
python3 ~/.claude/scripts/issue_scanner.py
python3 ~/.claude/scripts/issue_dispatcher.py --apply --only ruff:autofix

# Verify entire stack (services + drills + smoke)
bash scripts/verify-stack.sh   # if present in your tree

# Pre-deploy production checker (§27)
node scripts/production-checker.js   # added in iter 18/N
```

## Reading order for new tech leads

1. [`HLD-documind.md`](HLD-documind.md) — what the system does
2. [`C4-context.md`](C4-context.md) → [`C4-container.md`](C4-container.md) → [`C4-component.md`](C4-component.md)
3. [`adr/`](adr/) — read in numerical order (ADR-001 → ADR-022+)
4. [`tech-lead-audit-checklist.md`](tech-lead-audit-checklist.md)
5. [`autonomous-loop-architecture.md`](adr/014-autonomous-loop-architecture.md) — how the loop runs
6. Latest [`runbooks/autonomous-loop-session-*.md`](../runbooks/) — recent activity log

## When in doubt

- Check the latest `runbooks/autonomous-loop-session-*.md` — what's been
  changing and why
- Run `git log --oneline | head -30` — what shipped this week
- Read the latest commit's tail "Backend: N/9 gaps closed" — current
  audit progress
- Open the affected admin deep-dive page (`/admin/<topic>/deep`) — the
  compose-footer shows what the topic depends on

## Brutal rule (CLAUDE.md §47.13)

> A system without all 7 C4 surfaces (L1–L7) is not architected — it's
> just running. Production-grade = all 7 answered, with evidence,
> with version, with owner.
