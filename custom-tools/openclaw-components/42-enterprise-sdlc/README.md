# 42-enterprise-sdlc — operating-model document (no code)

## What this folder is

A 20-section enterprise operating-model document covering the SDLC, org
structure, governance workflow, risk classification, release gates,
testing pyramid, observability model, incident management, multi-agent
roles, HITL roles, KPI targets, maturity model, recommended tool stack,
and operating principles.

## What this folder is NOT

- Not TypeScript source
- Not a runnable component
- Not testable
- Not deployable on its own

Components 1–9 are code; Component 42 is a *map* for how an organization
runs AI. Both are useful; they answer different questions.

## Gap with components 1–9

The source paste skipped from Component 9 straight to Component 42 —
**components 10 through 41 are not in the repo**. If those were meant
to be part of the series, they're missing source.

## Honest review

See [`../GAPS.md` — Component 42 row](../GAPS.md). Short version: the
20 tables describe a target operating model. They are **aspirations**,
not **engineering deliverables**. Each row needs:

1. A real artifact (a doc, a dashboard, a runbook, a CI gate, an ADR)
2. An owner
3. A measurement (how do you know it's working?)
4. A drill that proves the artifact still works

Without those four, the table is a poster on the wall.

## Cross-reference with circuitRAG's actual policies

| Component 42 row | Where it's implemented (or partly) in this repo |
|---|---|
| §2 Governance Layer | CLAUDE.md §38 (AI Production Governance) |
| §6 Governance Workflow | CLAUDE.md §38.2 (HARD STOP gates) |
| §7 AI Risk Classification | CLAUDE.md §48.1 (Scope tier) |
| §8 Release Gates | CLAUDE.md §47.11 (10 pre-release gates) |
| §10 AI QA Strategy | CLAUDE.md §59.4 (Ragas thresholds) |
| §11 Observability Model | CLAUDE.md §47 (request_id baggage + decision audit) |
| §13 Multi-Agent Operating Model | CLAUDE.md §55 (Autonomous Fix-Bot Strategy) |
| §14 HITL Roles | CLAUDE.md §48.6 (LLM agent explainability HITL) |
| §15 Documentation Model | CLAUDE.md §47 (HLD/LLD/ADR) + §58 (folder README) |
| §17 KPI Framework | CLAUDE.md §53.3 (L1–L6 maturity levels) |
| §18 Maturity Model | CLAUDE.md §53 (Enterprise AI Maturity Stack §35-48) |
| §20 Operating Principles | CLAUDE.md §38 + §47 + §48 + §52 |

So most of Component 42 is **already encoded as repo policy** in
`~/.claude/CLAUDE.md`. The Component 42 document is a useful executive
summary; the repo policies are the implementation.
