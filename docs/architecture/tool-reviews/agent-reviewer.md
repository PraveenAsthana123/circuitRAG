# `ReviewerAgent` + B3 Review-Loop — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/agents.py::ReviewerAgent` + `langgraph_flow.py` review-loop
**Date:** 2026-05-01

## Triage

| Severity | Count | Top items |
|---|---|---|
| **P0** | 0 | — |
| **P1** | 3 | rows #11 (no slow-review detection), #18 (no negative drill on score-extraction edge), #25 (review notes not surfaced as separate audit field) |
| **P2** | 3 | — |

## Highlights

- ✅ B3 max_iterations cap drilled with `<` strict — 4th retry MUST NOT loop
- ✅ score parsing handles `SCORE: <0-10>` regex
- ✅ Threshold REVIEW_THRESHOLD=0.7 codified (not env-driven; ADR-gated change)

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 11 | Slow-review detect | ✗ | **P1** — slow reviewer that times out at 60s would not flag as "review-bottleneck" |
| 18 | Score parsing edge | ✗ | **P1** — what if reviewer says "SCORE: 7.5"? Or "SCORE: high"? Drill doesn't cover; could throw ValueError silently |
| 23 | Cost of failures | ⚠ | Tier-A reviewer is cheap; no cost ceiling enforcement |
| 24 | Rollback signal | n/a | — |
| 25 | Audit row | ⚠ | reviewer_notes flow as task field; not as separate `/explain` slot |
| 26 | Per-tenant | ⚠ | inherited from pool |

## Brutal one-liner

> The B3 review-loop is **the cheapest quality win** in the entire pipeline — local
> Tier-A retry up to 3 times for free. The score parser has fragile assumptions
> ("SCORE: N" with N as int) that aren't drilled for malformed cases. P1: write
> a negative drill for "SCORE: 7.5" / "SCORE: high" / no score / multiple scores.
