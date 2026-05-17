# custom-tools/INTEGRATION.md — how the two exploration folders relate

> This file maps the two alternative-approach folders to each other and
> to the real circuitRAG services in `services/`. It does NOT define an
> integration runtime — neither folder is wired into circuitRAG, and no
> integration code lives at this level.
>
> Per the source-fidelity convention used throughout `custom-tools/`,
> integration code is NOT invented from imagination. This document
> identifies the integration points an integrator WOULD wire up.

## The two folders

| Folder | Language | Style | Status |
|---|---|---|---|
| `openclaw-components/` | TypeScript | Interview-style components (numbered 1-9, 10, 42, 43) | 70 .ts files; 9 with tests; 2 docs-only |
| `enterprise-ai-os/` | Python + React | "Tool Sets" (numbered 11, 31, 32, 34-39) | 40 .py + 6 jsx/js + docs |

They are **alternative approaches** to similar problems, not
collaborating layers. Treating them as a stack would require an
adapter layer that does not exist.

## Capability overlap map

| Capability | openclaw-components | enterprise-ai-os |
|---|---|---|
| Channel routing / Gateway | Component 1 | (Tool Set 31 UI only — no backend gateway) |
| Agent runtime | Component 2 + Component 10 | (no equivalent in shipped Tool Sets 11/31/32/34-39) |
| Tool dispatch | Component 3 | (no equivalent shipped) |
| Memory + audit | Component 4 | Tool Set 36 (hash-chain audit only; no memory) |
| Guardrails / Responsible AI | Component 5 | (referenced in Tool Set 11 but not implemented) |
| Observability | Component 6 | Tool Set 34 OpenTelemetry SDK |
| Resilience (CB / retry / timeout) | Component 7 | (no equivalent shipped) |
| LLM Router | Component 8 | Tool Set 34 OpenAI client (single-provider, not router) |
| RAG Orchestrator | Component 9 | Tool Set 34 Qdrant client (search only, not orchestrator) |
| Workflow engine | Component 10 | (no equivalent shipped) |
| Explainability | (referenced in Component 5; not shipped) | Tool Set 11 (does NOT meet CLAUDE.md §48) |
| SLO + alerts | (no equivalent shipped) | Tool Set 38 |
| Release management | (no equivalent shipped) | Tool Set 37 |
| Identity / JWT | (no equivalent shipped) | Tool Set 35 (⚠ 2 P0 security bugs) |
| Runbooks | (no equivalent shipped) | Tool Set 39 |
| UI | (no UI) | Tool Set 31 (incomplete) |

**Where one folder has something the other lacks**, the cross-folder
seam is what an integrator would wire — NOT what's been done here.

## Mapping to the REAL circuitRAG services

| Capability | Real implementation in this repo | Notes |
|---|---|---|
| Gateway | `services/gateway-bff/` | Production-grade |
| Inference / LLM | `services/inference-svc/` | Real model routing + provider clients |
| Retrieval / RAG | `services/retrieval-svc/` | pgvector-backed, real reranking |
| Evaluation | `services/evaluation-svc/` | Ragas faithfulness gate (CLAUDE.md §59.4) |
| Ingestion / Kafka | `services/ingestion-svc/` | Real Kafka pipeline |
| MCP tool fleet | `mcp/` | 30+ MCP servers with scope-based RBAC |
| Audit | `mcp/server_audit.py` + Postgres | INSERT-only role, RLS per tenant |
| OTel collector | `ops-compose/` (Jaeger / Prometheus / Grafana) | Real W3C trace context propagation |
| Auth / OIDC | Real JWKS-based, not the Tool Set 35 HS256 + default-secret pattern | |
| Drill discipline | `mcp/tests/drill_*.py` + `scripts/run_drills.py` | CLAUDE.md §43 |

**For any feature you'd consider building in `custom-tools/`, the
real implementation already exists in `services/` at higher quality.**
The exploration folders are useful for *understanding* the patterns,
not for *replacing* anything.

## What an integration layer would need

If the goal were to actually run these as a unified system, you'd
need (none of which exists):

1. **Build orchestration** — TypeScript bundle + Python venv +
   React build coordinated via a single Makefile / Bazel
2. **Inter-runtime IPC** — TS → Python via HTTP / gRPC / Unix socket;
   currently impossible since they share no transport
3. **Single source of truth for types** — Pydantic on Python side vs
   TS interfaces on TS side; either OpenAPI-generated or Protobuf-
   generated bindings
4. **Single auth + tenant model** — the two folders disagree on what a
   tenant is (TS contexts vs Python dict)
5. **Single observability backbone** — TS `console.log("trace")` vs
   Python OTel SDK; need a single OTLP collector
6. **Single secrets layer** — TS reads `process.env`, Python reads
   `os.getenv`; need Vault / OpenBao with both clients
7. **Single audit layer** — Component 4 in-memory vs Tool Set 36
   in-memory; need one Postgres table with INSERT-only role

Estimated effort to actually wire this up: ~3-4 weeks of senior
engineering. Estimated value over the existing `services/` stack: zero.

## Recommendation

- For **interview prep or pattern learning**: read both folders +
  GAPS.md files. The honest gap analysis is the most valuable part.
- For **adding new capability to circuitRAG**: skip these folders.
  Read `docs/architecture/` + `services/` + CLAUDE.md.
- For **shipping anything to a tier-1 customer**: do not deploy any
  file from `custom-tools/` as-is. The two P0 security bugs in
  `enterprise-ai-os/identity/` are alone disqualifying.

## File-name stubs created in this round

To make the named-but-unprovided files resolvable, the following
stubs were added in this round. Each is clearly marked with a
`⚠️ STUB` header. None is derived from operator source.

| File | Why stub exists |
|---|---|
| `openclaw-components/01-gateway/channel-router.ts` | Named in Component 1 folder; minimal `ChannelAdapter` interface + registry |
| `openclaw-components/01-gateway/tool-dispatcher.ts` | Named in Component 1 folder; re-exports Component 3 |
| `openclaw-components/01-gateway/event-bus.ts` | Named in Component 1 folder; in-process `EventBus` |
| `openclaw-components/02-agent-runtime/model-client.ts` | Named in Component 2 folder; delegates to Component 8's `LLMRouter` |
| `enterprise-ai-os/ui/src/components/CostPanel.jsx` | Imported by `App.jsx`; minimal fetch-and-render |
| `enterprise-ai-os/ui/src/components/IncidentPanel.jsx` | Imported by `App.jsx`; minimal fetch-and-render |
| `enterprise-ai-os/ui/index.html` | Vite entrypoint HTML |
| `enterprise-ai-os/ui/src/main.jsx` | Vite entrypoint JSX bootstrapping `<App />` |
| `enterprise-ai-os/ui/vite.config.js` | Vite + React plugin config |

## What was NOT created (and why)

| Slot | Why not | Honest path |
|---|---|---|
| openclaw-components 11-41 (31 components) | Operator never showed source | Operator must paste; I will not invent 31 components |
| enterprise-ai-os Tool Sets 1-10, 12-30 (29 tool sets) | Operator never showed source | Same — operator must paste |

Inventing those 60 slots would be exactly the "marketing claim, not
engineering" anti-pattern flagged in every GAPS.md file in this folder.
The named-but-missing files above are different — they have an
explicit name + an inferred contract (what other files import from
them), so the stub is constrained, not invented.
