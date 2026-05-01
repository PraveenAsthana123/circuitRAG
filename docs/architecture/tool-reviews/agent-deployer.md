# `DeployerAgent` + `mcp_deploy` — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/deployer.py` + `mcp/server_deploy.py`
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | — |
| **P1** | 4 | rows #19 (no operator override of preflight verdict), #20 (no audit hook on deploy events), #21 (no deploy history persisted at server side), #38 (no deadletter for failed deploys) |
| **P2** | 3 | — |

## Highlights

- ✅ §42 hard-stop enforced at THREE layers (DeployerAgent.preflight, langgraph node, mcp_deploy server)
- ✅ Drill `drill_deploy_hard_stop` proves no-approval rejection at server boundary
- ✅ Conservative heuristic default `deploy_safety='review_required'`

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 11 | Slow-deploy detection | n/a | Stub canned response |
| 19 | Operator override | ⚠ | Operator can't override deployer's "block" verdict; must approve via task |
| 20 | State-change callback | ✗ | **P1** — deployer has no on_deploy_complete hook (operator dashboards rely on polling) |
| 21 | Persistent state | ⚠ | DB has `deploy_records` table; mcp_deploy server itself is stateless (canned responses) — fine for stub, gap for real backing |
| 23 | Cost-of-failures | ✗ | Real deploys can leak resources on failure (orphan containers); no cost tracking |
| 24 | Rollback signal | ✅ | rollback_handle exposed for B6 observer |
| 25 | Audit row | ✅ | deploy_records persisted with approval_id |
| 33 | Rate limit | ✗ | **P1** — no rate limit on deploy.compose_apply (would be terrible if real backing) |
| 36 | Dep CB | ✗ | **P1** — no breaker around docker compose / kubectl when wired |
| 38 | Deadletter | ✗ | **P1** — failed deploy doesn't auto-trigger rollback or quarantine |

## Brutal one-liner

> §42 hard-stop is **drilled at 3 layers** — best-protected surface in the entire repo.
> What's missing is **post-apply discipline** — no rate limit, no breaker, no
> deadletter, no callback. Rate limit would have to be P0 if we ever wire real
> docker compose; today it's P1 because the server is canned.
