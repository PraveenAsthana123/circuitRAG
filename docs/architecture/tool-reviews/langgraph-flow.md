# `langgraph_flow.py` (the DAG itself) — Brutal Tool Review

**Source:** `services/agent-orchestrator-svc/app/langgraph_flow.py`
**Date:** 2026-05-01

## Triage

| Severity | Count |
|---|---|
| **P0** | 0 |
| **P1** | 4 (rows #1 graph timeout, #14 per-node latency, #18 graph-shape drill, #34 shutdown drain) |
| **P2** | 3 |

## Highlights

- ✅ Conditional edges drilled (B3 review-loop, D1 v2 wiring)
- ✅ State schema explicit (TypedDict)
- ✅ Pipeline-v2 gated behind `pipeline_v2_enabled` flag

## Notable gaps

| # | Dim | Status | Note |
|---|---|---|---|
| 1 | Per-graph timeout | ✗ | **P1** — `ainvoke` has no overall timeout; a stuck node can pin the whole graph |
| 13 | Per-node latency | ✗ | **P1** — node-level histogram missing (only per-LLM-call) |
| 14 | Per-node success counter | ✗ | **P1** — operators can't see "tester node fail rate at 3%" |
| 18 | Graph-shape drill | ⚠ | drill_pipeline_v2_wired covers add_node + edges; not the GRAPH (e.g. "is there a path from entry to finalize?") |
| 19 | Manual override | ✗ | **P2** — operator can't override a node's decision mid-execution |
| 24 | Rollback signal | n/a | — |
| 34 | Graceful shutdown | ✗ | **P1** — in-flight ainvoke not drained; tasks "running" forever in DB |

## Brutal one-liner

> Graph topology is **clean and drilled at structure level**. What's missing is
> **graph-runtime hygiene** — no overall timeout, no per-node metrics, no
> shutdown drain. A stuck strategist call today can hold the entire graph
> forever (modulo the LLM-level timeout from CB-A1).
