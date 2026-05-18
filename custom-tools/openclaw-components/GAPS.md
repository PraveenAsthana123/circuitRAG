# GAPS.md — honest review against repo standards

> Per CLAUDE.md §47 (architecture) + §52 (40-row brutal tool review) +
> §43 (drill discipline) + §57 (production-grade discipline).
> Reviewer was asked for honest assessment, not flattery.
> **Severity:** P0 = will-break-prod · P1 = silent-degradation
> · P2 = operational · P3 = polish.

## Top-line verdict

These are **interview/teaching artifacts** with a "Production value: Yes"
table appended. The table is dishonest by this repo's standards. The code
demonstrates a pattern; it does not implement the pattern at production
strength. Examples:

- `console.log(JSON.stringify(...))` is **labeled** as "trace span" but is
  not OpenTelemetry, has no `request_id` baggage propagation, no
  context-carrier, and no exporter. A real span survives a
  service boundary; these do not.
- `Map<string, SessionState>` is **labeled** as session storage but is
  per-process in-memory. Two replicas = two session universes. First pod
  restart = total session loss.
- `calculator-tool.ts` no longer uses dynamic `Function(...)` execution; it now uses a small arithmetic parser with negative tests.

## Per-component gaps

### Component 1 — Gateway / Control Plane

| Gap | Severity | Fix |
|---|---|---|
| Sessions held in process-local `Map`; no persistence | **P0** | Redis / Postgres-backed session store; TTL; per-tenant partitioning |
| No auth / no RBAC at gateway | **P0** | OIDC validation, scope check, tenant_id from token claim |
| No rate limit | **P0** | Per-IP + per-tenant sliding window (e.g., upstream Envoy / `nestjs-throttler`) |
| No `request_id` minted; no baggage | **P0** | Generate `request_id` here; propagate via OTel baggage to every downstream call |
| No backpressure / queue | **P1** | When agent runtime is slow, reject with 429 rather than queue unbounded |
| No structured error envelope | **P2** | `{code, message, request_id}` per CLAUDE.md §6.2 |
| No drill (per §43) | **P0** | Negative-assertion drill: replay attack, wrong tenant, expired session |

### Component 2 — Agent Runtime / Planner / Executor

| Gap | Severity | Fix |
|---|---|---|
| `Planner.createPlan()` returns a **hardcoded 2-step plan** — same plan for any input | **P0** | LLM-driven planning with JSON-schema validated output per CLAUDE.md §59.4 |
| `AgentRuntime.run()` returns `string`, **not** `AgentResponse` from Component 1 | **P1** | Either align types (return `AgentResponse`) or build an adapter at the Gateway boundary |
| ~~Tool/model routing is wired, but memory, guardrails, and tracing are still not full runtime dependencies~~ ✅ Iter 64-65 (2026-05-17) | ~~P1~~ closed | Iter 64: `guardrails: GuardrailEngine` injected; input-side + output-side enforcement; traceId threaded (8 drill steps). Iter 65: `memory: MemoryGovernanceService` injected; new `action: "recall"` step type fetches via memory.read() preserving iter 62 cross-tenant defense; output = {key, value, found} for downstream composition (8 drill steps). Total component 2 drill count: 29. |

### Component 10 — Agent Workflow Engine

| Gap | Severity | Fix |
|---|---|---|
| `simulateToolExecution(toolName)` only throws when `toolName` is empty — but `ToolSelector.select()` ALWAYS returns a non-empty string (default `"default_agent_executor"`), so the `catch → replan` branch in `runNext()` is **unreachable** for any realistic flow. Same theatre-catch pattern as Component 2's `Executor`. | **P0** | Replace with a real tool invocation (delegate to Component 3's `ToolDispatcher`); the catch then handles real failures |
| `WorkflowState.history` is in-memory only — process restart = workflow lost | **P0** | Postgres + outbox pattern OR Temporal/Durable Objects for real durability |

### Component 3 — Tool Registry / Dispatcher

| Gap | Severity | Fix |
|---|---|---|
| Registry is per-process; no shared state across replicas | **P1** | Tool catalog from config + signature pinning per CLAUDE.md §50 catalog pattern |
| ⚠ Partial close (Iter 73, 2026-05-17): substring contract locked + FP surface drilled + documented-limitations captured as regression flip points. Real-classifier upgrade still needed. | **P1** | Upgrade to real classifier (Llama Guard / Bedrock Guardrails). Today's drill: rai-guard-corpus.test.ts (8 steps; ATTACK + BENIGN_KEYWORD + CLEAN + DOCUMENTED_LIMITATION corpora; TPR===1.0, FPR===0.0). |
| Telemetry is `console.log` | **P1** | Real OTel `tracer.startActiveSpan()` with carrier injection |

### Component 4 — Memory Governance

| Gap | Severity | Fix |
|---|---|---|
| Audit log is in-memory `[]` — lost on restart | **P0** | Append-only Postgres table; per §38 audit row schema |
| ~~No tenant isolation enforcement — caller can pass any tenantId~~ ✅ Iter 62 (2026-05-17) | ~~P0~~ closed | service-level enforcement at save() + read() via optional `callerTenantId` (auth-context tenant); mismatch → MemoryAccessDeniedError BEFORE persistence/retrieval. Backcompat preserved: omitted → defaults to body tenantId. Drill: cross-tenant-access.test.ts (8 steps, 6 negative). |

### Component 5 — Responsible-AI Guardrails

| Gap | Severity | Fix |
|---|---|---|
| Prompt-injection detector is **6 hand-written substrings** | **P0** | Use a classifier model (Llama Guard, ProtectAI, Bedrock Guardrails). Substring lists fail to the first creative attacker. |
| PII detector — same regex limitations as Component 4 | **P1** | Library-based detection |
| Approval gate `createApprovalTicket` logs to console; no actual queue | **P0** | Push to durable queue (SQS/Kafka) + human-review UI |
| Severity → decision mapping is hardcoded | **P2** | Policy-as-code: OPA / Cedar rules file |
| No baseline rate of false-positives measured | **P1** | Per §48 fairness: track false-positive rate per tenant; alert on drift |
| ~~No drill~~ ✅ Iter 63 (2026-05-17) | ~~P0~~ closed | attack-corpus.test.ts: 14-sample attack corpus + 4-sample benign-PII corpus + 5-sample clean corpus + 1-sample documented-limitation corpus. Asserts TPR_attack === 1.0 AND FPR_clean === 0.0 AND benign-block-rate === 0. 9 drill steps. Also fixed 3 pattern variants (1-word-insertion attacks) the drill caught: "ignore all previous instructions" etc. |

### Component 6 — Observability

| Gap | Severity | Fix |
|---|---|---|
| Calls itself "tracer" but emits `console.log` — **not OpenTelemetry** | **P0** | Use `@opentelemetry/sdk-node` with OTLP exporter; spans must propagate via W3C traceparent headers |
| Metrics are `console.log` — no Prometheus scrape, no histogram bucketing | **P0** | Use `@opentelemetry/metrics` or `prom-client` with `/metrics` endpoint |
| `AIOpsEventBus.publish` logs to console — no real bus | **P0** | Kafka topic or webhook to incident-response system |
| Drill coverage is partial | **P1** | Existing tests cover sampling and metric cardinality; add a 3-hop trace-context propagation drill after real OTel is wired |

### Component 7 — Resilience (Circuit Breaker)

| Gap | Severity | Fix |
|---|---|---|

### Component 8 — LLM Router

| Gap | Severity | Fix |
|---|---|---|
| `LLMClient.complete` returns a fake string — there is **no real provider call** | **P0** | Wire real provider SDKs (Anthropic / OpenAI / Bedrock / Ollama HTTP) with timeout + auth |
| `SafetyGate` — same substring problem as Component 5 | **P0** | Real classifier |
| ~~Drill coverage is partial~~ ✅ Iter 61 (2026-05-17) | ~~P1~~ closed | router-drill-matrix.test.ts: 14 drill steps across 3 axes (cost-cap, safety-gate, provider-missing). Total component 8 drill count: 27. |

### Component 9 — RAG Orchestrator

| Gap | Severity | Fix |
|---|---|---|
| `Retriever` is still in-memory, not a production vector DB | **P1** | Use the existing `services/retrieval-svc/` or pgvector/Qdrant for production durability and scale |

### Component 42 — Enterprise SDLC / Operating Model

> Shape note: this is a *document*, not a *component*. There is no source
> code to gap-review. The honest review here is whether the document is
> *useful* and *implementable*, not whether the code is correct (there
> is no code).

| Gap | Severity | Fix |
|---|---|---|
| Most rows are **aspirations** with no artifact / owner / measurement / drill behind them | **P0 (as governance)** | Each row needs: (a) named artifact, (b) named owner, (c) measurement, (d) drill per §43. Without those four, the table is a poster on the wall. |
| KPI targets are stated without baselines (`Hallucination Rate <3%` — measured how? on what eval set?) | **P0** | Per-KPI: dataset / methodology / sampling cadence / who reads the dashboard / alert threshold |
| Risk classification (§7) has 4 buckets but no decision tree for which bucket a use case falls into | **P1** | EU AI Act Annex III mapping + organization-specific risk matrix |
| Org-chart (§3) does not match what most enterprises actually look like (single Chief AI Officer is rare; usually CTO + Chief Data Officer + Chief Risk Officer share it) | **P2** | Document is a *reference* org, not *the* org — call that out |
| Tool-stack recommendations (§19) include both `LangGraph` and `Temporal` for "Workflow" without saying when to use which | **P2** | Decision criteria per row (e.g., LangGraph for LLM-native DAG, Temporal for durable cross-service orchestration) |
| Maturity Model (§18) Level 5 "Autonomous enterprise AI" is undefined | **P3** | Either define measurably or remove |
| "Auto-Heal" in §12 incident management is named but unscoped — what can/cannot auto-heal? | **P1** | Catalog: which failures are auto-healed, which require human |
| Multi-Agent Operating Model (§13) lists 8 agent roles but doesn't say which are required vs optional | **P2** | Minimal-viable set vs full set |
| No explicit mapping from "what an org does" → "what evidence proves it" | **P0** | Per row: evidence type (doc / dashboard / runbook / CI gate / ADR) |
| Document overlaps significantly with circuitRAG's existing `~/.claude/CLAUDE.md` §38/§47/§48/§52/§53 | **n/a (not a bug)** | See `42-enterprise-sdlc/README.md` cross-ref table — most rows are already encoded as repo policy with implementation details |

**Bottom line for §42:** the document is a useful executive summary of how
an enterprise should run AI. As a *target operating model* it's valuable
for stakeholder alignment. As an *engineering deliverable* it has zero
implementation surface — that work lives in CLAUDE.md §38/§47/§48/§52/§53
and in the actual `services/` directory of this repo.

### Component 43 — Enterprise Reference Architecture

> Shape note: same as Component 42 — operating-model document, not code.
> No source files, no tests. Describes the system's *shape*, not its
> *behavior*.

| Gap | Severity | Fix |
|---|---|---|
| Same "aspirations without artifacts" pattern as Component 42 | **P0 (as architecture)** | Each diagram needs: matching code path, ADR justifying the choice, drill proving it works, runbook for failure modes |
| §1–§3 C4 diagrams have no L4 (code) level — that's where most production gaps actually live | **P1** | Add L4 per component per CLAUDE.md §47.2 |
| §5 LLD table lists 10 components in one sentence each — insufficient for engineering | **P1** | Per-component LLD with interface contracts, error envelopes, SLOs |
| §6 sequence has 10 steps but no failure branches (what if guardrail fails at step 3?) | **P1** | Annotate failure paths + the fallback for each step |
| §11 K8s topology shows pods but no probes, no PDB, no HPA, no NetworkPolicy | **P1** | Per CLAUDE.md §47.8 (3-probe pattern) + autoscale + isolation |
| §13 Failure Handling Flow shows "Circuit Breaker → Retry → Fallback Model → Escalation → HITL Review" without saying when to choose which | **P1** | Decision matrix per failure type |
| §14 Deployment Flow has no rollback path (despite Component 7 having a rollback manager) | **P0** | Per CLAUDE.md §47.7 — 4-layer rollback documented per layer |
| §16 Recommended Production Topology hardcodes vendor choices (Qdrant / Neo4j / Temporal / NGINX) without trade-off rationale | **P2** | ADRs per choice |
| §17 NFR Targets (99.9% availability, <5min recovery, "Zero trust") with no measurement methodology | **P0** | Each NFR needs: how measured, by whom, on what cadence, alert threshold |
| ~70% overlap with Component 42 (both describe the same operating model from different angles) | **n/a** | Merge or cross-link explicitly |

**Bottom line for §43:** the diagrams are useful for stakeholder
alignment and onboarding. As reference architecture they show intent.
As an engineering deliverable they need the artifact + owner + drill +
measurement layer that's missing.

### Components 11–41 — MISSING from source paste

The source jumps 10 → 42 (after Component 10 was backfilled). No code provided. If they were code components,
the gap is 32 components wide. Most likely some of these would have been:
Skills / Knowledge Graph / Vector Index / Embedding Service / Eval Harness /
Cost Ledger / Multi-Tenancy / API Versioning / Schema Registry / OPA Policy
Engine / Webhook Bus / Cache Layer / Rate Limiter / Audit Sink / Citation
Renderer / Feedback Collector / A-B Router / Canary Manager / Feature Store
/ Vault Client / Notification Service / Job Queue / Backfill Worker /
Migration Runner / Health Aggregator / Quota Service / Tenant Onboarder /
SSO Adapter / Workflow Runner / Replay Service / Backup Service. Pure
speculation — confirm with source.

## What "production-grade" would actually require

For ANY of these to be deployable to a tier-1 bank or healthcare system
per CLAUDE.md §53 (Enterprise AI Maturity Stack L4+):

1. Per-component **ADR** per §47.3 — recording why this design vs alternatives
2. Per-component **40-row brutal review** per §52 with P0/P1/P2/P3
3. Per-component **drill** per §43 with ≥3 negative assertions
4. **Decision audit row** per §38.3 for every action that affects a user
5. **Explainability evidence trail** per §48 (model card, SHAP/counterfactual where applicable)
6. **Real OTel** with W3C trace context per §47.6
7. **Rollback path** per §47.7 (4-layer rollback tested in staging)
8. **Load test** per §47.10 (5 phases — smoke, load, stress, soak, spike)
9. **Compose-footer** per §49 linking the 3-7 deep-dive pages this composes with
10. **Folder README** per §58 generated by `scripts/generate_folder_report.py`

This folder still does not meet the full production checklist, even though several local drills now exist.

## Recommended next steps (in priority order)

1. **If teaching/interview material:** stop here. Add commentary that
   labels each "Production value: Yes" as "Demonstrates the pattern;
   not production-grade." Honesty over polish.
2. **If actually deploying:** pick ONE component (most likely 7-Resilience
   or 5-Guardrails since they have the cleanest unit boundary), apply
   §47 + §52 + §43 to it as a proof, then decide whether to continue.
3. **If integrating into circuitRAG:** don't. The mapping table in
   README.md shows the real services already exist. Improve those
   instead of running a parallel stack.

## The brutal rule

> A "production value: Yes" claim without a drill that rejects a
> negative case is a marketing claim, not an engineering one. Per
> CLAUDE.md §43 + §57.7 + §52, every `✓` requires evidence.
> These components now have targeted local evidence for several fixes, but they still demonstrate ideas more than they prove production readiness.
