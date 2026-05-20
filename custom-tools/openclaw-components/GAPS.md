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
| ~~SessionManager owned process-local `Map` directly with no persistence adapter seam~~ ✅ Iter 98 (2026-05-18) | ~~P0 local gap~~ closed | `SessionManager` now depends on an injectable `SessionPersistenceStore`; default `InMemorySessionStore` preserves TTL/LRU behavior and tests pin the adapter contract. Production still needs Redis/Postgres-backed store wiring for cross-replica durability. |
| ~~No auth boundary at gateway~~ ✅ Iter 50 (2026-05-17) | ~~P0 local gap~~ closed | `AuthMiddleware` runs before session creation, default `NoOpAuthMiddleware` denies by default, and authenticated claims override body-supplied tenant/user. Production still needs real OIDC/RBAC middleware. |
| ~~No local gateway rate limit~~ ✅ Iter 11 (2026-05-17) | ~~P0 local gap~~ closed | `RateLimiter` enforces tenant:user request buckets and cross-tenant isolation tests cover the boundary. Production still needs upstream distributed limits. |
| ~~No request_id minted at gateway~~ ✅ Iter 11/71 (2026-05-17) | ~~P0 local gap~~ closed | `Gateway` mints UUID request IDs for success and error envelopes; baggage drills verify uniqueness, UUID format, and gateway_error correlation. Real OTel baggage propagation remains an infra gap. |
| ~~No local delegated job mechanism for agent workflow backpressure~~ ✅ Iter 92 (2026-05-18) | ~~P1 local gap~~ closed | `JobScheduler` + `WorkflowDelegator` provide delayed/priority/idempotent delegated `runNext` jobs with leases, retries, jitter backoff, cancellation, and dead-lettering. Production still needs durable Postgres/Redis/Kafka backing. |
| ~~No always-on/cold-start supervisor for agent workflow runtime~~ ✅ Iter 93 (2026-05-18) | ~~P1 local gap~~ closed | `AgentSupervisor` now schedules warmup + recurring heartbeat jobs, drains delegated workflow jobs each tick, tracks `cold/warming/ready/degraded/stopped`, emits metrics, and sends notifications for start/warmup/heartbeat/degraded/stop. Production still needs process manager/K8s probes + durable scheduler backing. |
| ~~No 100-agent fleet or non-interactive approval/next-action policy control plane~~ ✅ Iter 94 (2026-05-18) | ~~P1 local gap~~ closed | `AgentFleetSupervisor` now reconciles to 100 active agents by default, verifies working-ready agents separately from merely active agents, warms healthy replacements in the same reconcile cycle, replaces degraded/stopped agents, and emits active/working/not-working fleet metrics. `ApprovalPolicy` and `NextActionPolicy` decide allow/request_approval/deny and run/delegate/wait/stop without interactive prompts. Production still needs K8s/HPA/process manager backing and durable policy state. |
| ~~No structured gateway error envelope~~ ✅ Iter 11/98 (2026-05-18) | ~~P2 local gap~~ closed | Gateway failures return `{detail, errorCode, requestId}` and emit correlated `gateway_error` through an injectable sink. |
| ~~No gateway drills~~ ✅ Iter 50/53/71/98 (2026-05-18) | ~~P0 local gap~~ closed | Gateway tests cover default-deny auth, claim override, rate-limit overflow, payload size limit, requestId baggage, and error-sink correlation. Replay/expired-session drills remain for a real token middleware. |

### Component 2 — Agent Runtime / Planner / Executor

| Gap | Severity | Fix |
|---|---|---|
| ~~`Planner.createPlan()` only had a hardcoded fallback plan with no validated provider boundary~~ ✅ Iter 97 (2026-05-18) | ~~P0 local gap~~ closed | `Planner` now accepts an injected `PlanProvider` and validates provider output against the local `AgentPlan` schema, failing closed on invalid actions, missing tool names, missing memory keys, and malformed step data. Production still needs a real LLM planner adapter and JSON Schema contract. |
| ~~`AgentRuntime.run()` returned an unstructured legacy string~~ ✅ Iter 51 (2026-05-17) | ~~P1 local gap~~ closed | `AgentRuntime.run()` returns `AgentRuntimeResult` with `ok`, final `output`, `failedAt`, and per-step execution results; runtime tests pin the non-string shape. Gateway adapter alignment remains production integration work. |
| ~~Tool/model routing is wired, but memory, guardrails, and tracing are still not full runtime dependencies~~ ✅ Iter 64-65 (2026-05-17) | ~~P1~~ closed | Iter 64: `guardrails: GuardrailEngine` injected; input-side + output-side enforcement; traceId threaded (8 drill steps). Iter 65: `memory: MemoryGovernanceService` injected; new `action: "recall"` step type fetches via memory.read() preserving iter 62 cross-tenant defense; output = {key, value, found} for downstream composition (8 drill steps). Total component 2 drill count: 29. |

### Component 10 — Agent Workflow Engine

| Gap | Severity | Fix |
|---|---|---|
| ~~`simulateToolExecution(toolName)` was the default execution path, so workflow steps could complete without real tool work~~ ✅ Iter 91 (2026-05-18) | ~~P0~~ closed | `AgentWorkflowEngineOptions.toolDispatcher` now dispatches selected steps through Component 3 `ToolDispatcher`; `requireRealToolDispatcher` fails closed in production config. Legacy `simulateToolExecution` remains only as the local/test fallback. Drill: `tool-dispatcher-integration.test.ts`. |
| ~~`WorkflowState.history` was tied to in-memory `Map` storage — process restart = workflow lost~~ ✅ Iter 99 (2026-05-18) | ~~P0 local gap~~ closed | `WorkflowStateStore` now depends on injectable `WorkflowStatePersistence` for current state, rollback history, and outbox-style workflow events; default `InMemoryWorkflowStatePersistence` preserves local behavior and tests pin restart-style persistence reuse. Production still needs a concrete Postgres/outbox or Temporal/Durable Objects adapter. |

### Component 3 — Tool Registry / Dispatcher

| Gap | Severity | Fix |
|---|---|---|
| ~~Registry accepted any in-process tool with no pinned catalog check~~ ✅ Iter 95 (2026-05-18) | ~~P1 local gap~~ closed | `ToolRegistry` now supports a pinned catalog with SHA-256 metadata signatures and fails closed on unknown or tampered tool metadata. Production still needs a shared config source and cross-replica distribution. |
| ~~ResponsibleAIGuard was hardwired to substring checks with no classifier boundary~~ ✅ Iter 109 (2026-05-19) | ~~P1 local gap~~ closed | `ResponsibleAIGuard` now depends on injectable `ResponsibleAIClassifier`; default `PatternResponsibleAIClassifier` preserves the corpus-locked local rules while production can inject Llama Guard, Bedrock Guardrails, ProtectAI, or another policy classifier. `rai-guard-corpus.test.ts` still pins attack/benign/documented-limitation behavior. |
| ~~Component 3 telemetry emitted directly to console with no injectable sink~~ ✅ Iter 96 (2026-05-18) | ~~P1 local gap~~ closed | `Telemetry` now accepts an injectable `ToolTelemetrySink`, preserves the default single-line console JSON contract, and includes a bounded `InMemoryToolTelemetrySink` for drills/tests. Production still needs a real OTel/OTLP sink implementation. |

### Component 4 — Memory Governance

| Gap | Severity | Fix |
|---|---|---|
| ~~Audit log canonical storage was an in-memory `[]` — lost on restart~~ ✅ Iter 100 (2026-05-18) | ~~P0 local gap~~ closed | `MemoryAuditLog` now writes through an injectable `AuditRecordStore`; default `InMemoryAuditRecordStore` preserves local behavior and tests pin append-only storage, event emission, defensive copies, and restart-style store reuse. Production still needs a concrete append-only Postgres/SIEM-backed implementation per §38. |
| ~~No tenant isolation enforcement — caller can pass any tenantId~~ ✅ Iter 62 (2026-05-17) | ~~P0~~ closed | service-level enforcement at save() + read() via optional `callerTenantId` (auth-context tenant); mismatch → MemoryAccessDeniedError BEFORE persistence/retrieval. Backcompat preserved: omitted → defaults to body tenantId. Drill: cross-tenant-access.test.ts (8 steps, 6 negative). |

### Component 5 — Responsible-AI Guardrails

| Gap | Severity | Fix |
|---|---|---|
| ~~Prompt-injection detector was hardwired to substring rules with no classifier boundary~~ ✅ Iter 101 (2026-05-19) | ~~P0 local gap~~ closed | `PromptInjectionDetector` now depends on an injectable `PromptInjectionClassifier`; default `PatternPromptInjectionClassifier` preserves the expanded local rule set while production can inject Llama Guard, ProtectAI, or Bedrock Guardrails. Real classifier adapter wiring remains production work. |
| ~~PII detector was hardwired to regex-only detection with no provider boundary~~ ✅ Iter 102 (2026-05-19) | ~~P1 local gap~~ closed | `PIIDetector` now depends on injectable `PIIProvider`; default `RegexPIIProvider` preserves email/phone/SSN/card/IBAN/IP heuristics and tests pin provider injection. Production still needs Presidio, validator.js/libphonenumber, or another library-backed implementation. |
| ~~Approval gate `createApprovalTicket` only emitted an event; no queue-backed review ticket existed~~ ✅ Iter 103 (2026-05-19) | ~~P0 local gap~~ closed | `ApprovalGate` now persists canonical tickets through an injectable `HumanReviewQueue`; default `InMemoryHumanReviewQueue` preserves local behavior, supports list/get/approve/deny, and keeps the existing `approval_ticket` event schema unchanged. Production still needs SQS/Kafka/Postgres backing and a human-review UI. |
| ~~Severity → decision mapping was hardcoded~~ ✅ Iter 46 (2026-05-17) | ~~P2 local gap~~ closed | `PolicyEngine` already accepts configurable `severityMap` and per-rule `ruleOverrides`, with most-restrictive merge behavior covered by `policy-engine.test.ts`. Production can still externalize this config through OPA/Cedar or another policy store. |
| ~~No runtime guardrail false-positive/drift telemetry boundary existed~~ ✅ Iter 104 (2026-05-19) | ~~P1 local gap~~ closed | GuardrailEngine now accepts an injectable GuardrailDecisionMonitor; MetricsGuardrailDecisionMonitor emits per-tenant decision/clean/flagged/finding metrics with bounded labels for false-positive and drift baselines. Production still needs dashboards, alert thresholds, and eval-set labeling/feedback loop. |
| ~~No drill~~ ✅ Iter 63 (2026-05-17) | ~~P0~~ closed | attack-corpus.test.ts: 14-sample attack corpus + 4-sample benign-PII corpus + 5-sample clean corpus + 1-sample documented-limitation corpus. Asserts TPR_attack === 1.0 AND FPR_clean === 0.0 AND benign-block-rate === 0. 9 drill steps. Also fixed 3 pattern variants (1-word-insertion attacks) the drill caught: "ignore all previous instructions" etc. |

### Component 6 — Observability

| Gap | Severity | Fix |
|---|---|---|
| ~~Tracer emitted console-shaped spans without W3C trace identity or an OTel exporter boundary~~ ✅ Iter 105 (2026-05-19) | ~~P0 local gap~~ closed | `Tracer` now creates W3C `traceId`, `spanId`, `parentSpanId`, and `traceparent`, can continue an incoming traceparent, and can route spans through `OpenTelemetryTraceSink` to an OTel-shaped exporter interface. Production still needs OpenTelemetry SDK Node plus OTLP exporter package wiring. |
| ~~Workflow monitoring had no first-class metrics boundary for delegated agent execution~~ ✅ Iter 92 (2026-05-18) | ~~P1 local gap~~ closed | `ObservedWorkflowMonitor` now emits workflow start/delegate/step start/success/failure counters and histograms with bounded labels. Production still needs Prometheus/OTel exporter instead of console emission. |
| ~~`AIOpsEventBus.publish` only had console/sink emission with no event-bus dispatch contract~~ ✅ Iter 106 (2026-05-19) | ~~P0 local gap~~ closed | `AIOpsEventBus` now dispatches topic/key envelopes through an injectable `AIOpsEventDispatcher`; default `SinkAIOpsEventDispatcher` preserves console/sink behavior, with in-memory, Kafka-shaped, and webhook-shaped dispatcher adapters covered by tests. Production still needs real Kafka/webhook credentials and outbox-backed delivery. |
| ~~Trace-context drill coverage was partial for delegated workflow → tool execution~~ ✅ Iter 92 (2026-05-18) | ~~P1 local gap~~ closed | `workflow-observability-integration.test.ts` verifies delegated job trace, workflow step trace, and `tool.dispatch` trace share the same `traceId`. Real OTel exporter/propagator remains a production infra gap. |

### Component 7 — Resilience (Circuit Breaker)

| Gap | Severity | Fix |
|---|---|---|

### Component 8 — LLM Router

| Gap | Severity | Fix |
|---|---|---|
| ~~`LLMClient.complete` returned only fake/demo output; no real provider adapter existed~~ ✅ Iter 91 (2026-05-18) | ~~P0~~ closed for Ollama path | Added `OllamaLLMClient` using `/api/generate` with timeout and response validation; `EchoLLMClient` is marked as a production stub and `LLMRouter({ productionMode: true })` rejects it. OpenAI/Anthropic/Bedrock adapters remain future provider work. |
| ~~`SafetyGate` was hardwired to substring checks with no classifier boundary~~ ✅ Iter 107 (2026-05-19) | ~~P0 local gap~~ closed | `SafetyGate` now depends on an injectable `SafetyGateClassifier`; default `PatternSafetyGateClassifier` preserves existing blocked-phrase behavior while production can inject Llama Guard, Bedrock Guardrails, ProtectAI, or another policy classifier. Real classifier adapter wiring remains production work. |
| ~~Drill coverage is partial~~ ✅ Iter 61 (2026-05-17) | ~~P1~~ closed | router-drill-matrix.test.ts: 14 drill steps across 3 axes (cost-cap, safety-gate, provider-missing). Total component 8 drill count: 27. |

### Component 9 — RAG Orchestrator

| Gap | Severity | Fix |
|---|---|---|
| ~~`RAGOrchestrator` was hard-typed to the in-memory `Retriever`, blocking production retrieval adapters~~ ✅ Iter 108 (2026-05-19) | ~~P1 local gap~~ closed | `RAGOrchestrator` now depends on a `RetrievalSource` port that accepts sync or async adapters; tests cover custom vector-DB-style retrieval, tenant-scoped adapter behavior, and telemetry counts. Production still needs a concrete pgvector/Qdrant/retrieval-svc adapter and durable index operations. |

### Component 42 — Enterprise SDLC / Operating Model

> Shape note: this is a *document*, not a *component*. There is no source
> code to gap-review. The honest review here is whether the document is
> *useful* and *implementable*, not whether the code is correct (there
> is no code).

| Gap | Severity | Fix |
|---|---|---|
| Most rows are **aspirations** with no artifact / owner / measurement / drill behind them | **P0 (as governance)** | Each row needs: (a) named artifact, (b) named owner, (c) measurement, (d) drill per §43. Without those four, the table is a poster on the wall. |
| ~~KPI targets stated without baselines~~ ✅ Iter 131 (2026-05-20) | ~~P0 local gap~~ closed | `kpi/kpi-targets.ts` ships typed `KPIDefinition` with 7 mandatory protocol fields (evalDataset / methodology / dashboardOwner / samplingCadence / alertThreshold / comparison / euAiActRelevant + complianceRefs) + `evaluateKPI()` 3-band evaluator + `CANONICAL_KPIS` catalog of 6 KPIs binding iters 116-118 canonical corpora to thresholds: rag_hallucination_rate, rag_citation_accuracy, guardrail_false_positive_rate, guardrail_true_positive_rate, tool_selection_accuracy, plan_action_validity. `euAiActDisclosureSet()` extracts compliance-relevant KPIs for public transparency dashboard. 17 drill tests, 5 negatives. |
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
| ~~§14 Deployment Flow had no rollback path~~ ✅ Iter 129 (2026-05-20) | ~~P0 local gap~~ closed | `deploy/k8s/ROLLBACK.md` operator runbook + `deploy/k8s/rollback-readiness.ts` validator + 11-test drill. Documents the §47.7 4-layer rollback model (App / DB / AI / Infra) with per-layer commands, decision tree, post-rollback verification, and 6-symptom troubleshooting table. The validator gates CD against §47.7 invariants (:latest forbidden, RollingUpdate maxUnavailable=0, grace period ≥ 30s, image-bundle in sync); 5 negative drills lock the gate. Composes with iters 126+127+128. |
| §16 Recommended Production Topology hardcodes vendor choices (Qdrant / Neo4j / Temporal / NGINX) without trade-off rationale | **P2** | ADRs per choice |
| ~~§17 NFR Targets had no measurement methodology~~ ✅ Iter 130 (2026-05-20) | ~~P0 local gap~~ closed | `nfr/nfr-targets.ts` ships typed `NFRDefinition` with mandatory measurement-protocol fields (signal / measureFrom / cadence / owner / alertThreshold / comparison) + `evaluateNFR()` 3-band evaluator (ok/warn/critical) + `CANONICAL_FLEET_NFRS` catalog (4 NFRs binding iter 126-129 signals to thresholds: availability, rollback-time, reconcile-latency-p95, reconcile-cadence). 18 drill tests, 6 negatives. Composes with daemon snapshot + rollback validator + cycle log window. |
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
