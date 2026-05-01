# `ModelRouter` (`route()`) — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/model_router.py`
**Date:** 2026-05-01

## Triage

| Severity | Count |
|---|---|
| **P0** | 0 |
| **P1** | 2 (rows #21 budget storage backward compat, #25 routing decision NOT in /explain) |
| **P2** | several |

## Highlights

- ✅ Pure function — fully drillable
- ✅ Budget guard (R0) drilled with 7-step C1 drill
- ✅ Decision serializable for audit (`to_dict()`)
- ✅ 5 deterministic rules with explicit reasons

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 21 | Persistent budget | ⚠ | **P1** — `tenant_budgets` table exists; router accepts budget_remaining_cents from caller. Caller's responsibility to load/save. Service.py wiring not yet done. |
| 25 | Audit row | ⚠ | RouteDecision in task_runs.routing_decision; not exposed as a field of the /explain response |
| 39 | Cost ceiling | ✅ | C1 — drilled |

## Brutal one-liner

> Pure function, deterministic, drilled. **No P0 issues.** What's missing is
> caller wiring — service.py needs to load `tenant_budgets.used_today_cents`
> at task start and pass through. ~30 minutes of work.
