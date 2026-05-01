# Project Standards

> §19 mandate. Substantive content lives in:
>
> See: [`~/.claude/CLAUDE.md`](../../.claude/CLAUDE.md) — global standards (every § is in scope here)
> See: [`docs/architecture/adr/`](architecture/adr/) — 23 ADRs governing project-specific decisions
> See: [`docs/architecture/tech-lead-audit-checklist.md`](architecture/tech-lead-audit-checklist.md) — pre-release gate
> See: [`docs/architecture/production-trust-quality-and-readiness.md`](architecture/production-trust-quality-and-readiness.md) — trust scorecard

## Global standards apply (CLAUDE.md)

Every § from `~/.claude/CLAUDE.md` is in scope for this project:

- §1–§17: Backend bootstrap, DI, security, error handling, testing
- §19: Mandatory bootstrap files (this stub closes one of them)
- §38: AI Production Governance — 15 production gates, audit row
- §43: Drill testing pattern — every commit ships a drill
- §44: Autonomous loop — opt-in continuous mode
- §47: Architecture & design patterns — C4 (7 levels), ADR, JAD, etc.
- §48: AI explainability
- §49: Compose-footer policy on deep-dive pages
- §50: Local-model issue dispatcher
- §51: GitHub update metadata policy

## Project-local additions

ADRs codify project-specific decisions that don't have a global
equivalent:

- ADR-001: audit_actor_id is text (not UUID) — supports system actors
- ADR-008: transport breakers — vector + graph
- ADR-011: drill pattern uses real stack, no mocks
- ADR-014: autonomous loop architecture
- ADR-015: ratchet pattern for discipline drift
- (full list under [`docs/architecture/adr/`](architecture/adr/))

## Pre-release gate (CLAUDE.md §47.11)

1. C4 diagrams up to date
2. ADRs filed for every locked decision in the release
3. STRIDE table per new container
4. DevSecOps gates green
5. Rollback path tested in staging
6. Health probes (startup + liveness + readiness)
7. Load test 5 phases passed
8. Eval gate for AI changes
9. Audit log writes verified
10. Runbook + on-call rotation updated

For circuitRAG specifically, also gate on:

11. All drills under `mcp/tests/drill_*.py` passing (or advisory
    failures explicitly noted per ADR-014)
12. Compose-footer audit (`drill_e2e_admin_smoke.py` step 1) green
13. Coverage ratchet not regressed (`fail_under` floor in
    `pyproject.toml`)
14. README.md snapshot section updated (§51.2)
15. Latest autonomous-loop-session-*.md runbook present if loop ran
