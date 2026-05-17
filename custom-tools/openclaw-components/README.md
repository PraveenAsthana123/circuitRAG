# openclaw-components — alternative-approach exploration

> **Status: study / interview material, NOT production-grade.**
> This folder holds an OpenClaw-style decomposition of an AI-platform stack,
> presented as an *alternative approach* to a GitHub-based tool. It is
> deliberately kept OUT of `services/` to avoid being confused with the
> circuitRAG production services (`gateway-bff/`, `inference-svc/`,
> `retrieval-svc/`, `evaluation-svc/`, `ingestion-svc/`).

## What's here

| # | Component | Folder | Status |
|---|-----------|--------|--------|
| 1 | Gateway / Control Plane | `01-gateway/` | ✓ verbatim · folder listed `channel-router.ts` + `tool-dispatcher.ts` + `event-bus.ts` but no source provided |
| 2 | Agent Runtime / Planner / Executor | `02-agent-runtime/` | ✓ verbatim · folder listed `model-client.ts` but no source provided (see `02-agent-runtime/NOTES.md`) |
| 3 | Tool Registry / Dispatcher | `03-tooling/` | ✓ verbatim |
| 4 | Memory Governance | `04-memory-governance/` | ✓ verbatim |
| 5 | Responsible-AI Guardrails | `05-guardrails/` | ✓ verbatim |
| 6 | Observability | `06-observability/` | ✓ verbatim |
| 7 | Resilience (CB + retry + timeout) | `07-resilience/` | ✓ verbatim |
| 8 | LLM Router | `08-llm-router/` | ✓ verbatim |
| 9 | RAG Orchestrator | `09-rag-orchestrator/` | ✓ verbatim · test file backfilled with real source |
| 10 | Agent Workflow Engine | `10-agent-workflow/` | ✓ verbatim · 1 P0 + 2 P1 bugs flagged in GAPS |
| 11–41 | (gap) | — | ✗ NOT in source paste |
| 42 | Enterprise SDLC / Operating Model | `42-enterprise-sdlc/` | ✓ verbatim · operating-model doc, **no code**, no tests |
| 43 | Enterprise Reference Architecture | `43-reference-architecture/` | ✓ verbatim · architecture doc, **no code**, no tests |

## Source-fidelity notes

- **Component 1** folder layout listed `channel-router.ts`, `tool-dispatcher.ts`,
  and `event-bus.ts` but only 3 source files (`gateway.ts`, `session-manager.ts`,
  `types.ts`) were shown. The Gateway as-shipped therefore does not yet route
  channels, dispatch tools, or publish events.
- **Component 2** folder layout listed `model-client.ts` but only 4 source files
  (`types.ts`, `planner.ts`, `executor.ts`, `agent-runtime.ts`) were shown.
  The Executor's empty `try` block — which has no statement that can throw —
  was almost certainly meant to call `modelClient.complete(...)`. See
  `02-agent-runtime/NOTES.md`.
- **Components 1 and 2 have no test files** in the source paste, unlike
  components 3-9 which do.
- **Components 11–41 are missing.** Component 10 has been backfilled
  (Agent Workflow Engine). 31 components remain unaccounted for.
- **Components 42 and 43 are different shape from the code components.**
  42 = operating model (org + SDLC + governance + KPIs).
  43 = reference architecture (C4 + sequence + topology + tech stack).
  Both are documents, not TypeScript code. Cross-reference tables in their
  per-folder `README.md` files show ~70% of each is already encoded as
  repo policy in `~/.claude/CLAUDE.md` (§38, §47, §48, §52, §53, §59) or
  as actual implementation in `services/`.

## How to run

```bash
cd /mnt/deepa/rag/custom-tools/openclaw-components
npm install   # or pnpm install
npm test      # vitest across all components
```

## Honest gap analysis

See [GAPS.md](GAPS.md) — these components are interview/study-grade, not
production-grade by this repo's standards (CLAUDE.md §47 architecture +
§52 brutal tool review + §43 drill discipline). Every component has at
least one P0/P1 gap that would block real deployment.

## Composes with (the real services)

If you wanted to upgrade this code into the real stack, here's the rough
mapping — NOT done in this folder, just noted:

| OpenClaw component | circuitRAG counterpart |
|-------------------|------------------------|
| 1. Gateway | `services/gateway-bff/` |
| 3. Tool Registry | `mcp/` (MCP server fleet) |
| 4. Memory Governance | `libs/py/documind_core/` (with PII + audit) |
| 5. Guardrails | `services/inference-svc/` request middleware |
| 6. Observability | OTel collector + Jaeger (already in `ops-compose/`) |
| 7. Resilience | `libs/py/documind_core/circuit_breaker.py` |
| 8. LLM Router | `services/inference-svc/` model client + routing |
| 9. RAG Orchestrator | `services/retrieval-svc/` |

## What this folder is NOT

- NOT a service Claude will deploy
- NOT covered by repo drills (§43)
- NOT in any docker-compose
- NOT in CI
- NOT referenced from any production code
