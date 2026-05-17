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
  context-carrier, no exporter, no sampling. A real span survives a
  service boundary; these do not.
- `Map<string, SessionState>` is **labeled** as session storage but is
  per-process in-memory. Two replicas = two session universes. First pod
  restart = total session loss.
- `Function("use strict"; return (...))()` in `calculator-tool.ts` is a
  previously used dynamic code execution in `calculator-tool.ts`; this has been replaced with a small arithmetic parser and negative tests.

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
| `Executor.execute()` `try` block contains only `results.push(...)` — **no statement can throw**, so the `catch` is unreachable. `success: true` is hardcoded. | **P0** | Replace synthetic `output` with real per-step routing: `think → modelClient.complete()`, `tool → toolDispatcher.dispatch()`, `respond → finalize` |
| `action: "tool"` is defined in the type but **never routed** in the executor | **P0** | Switch on `step.action`; integrate Component 3's `ToolDispatcher` |
| `AgentRuntime.run()` returns `string`, **not** `AgentResponse` from Component 1 | **P1** | Either align types (return `AgentResponse`) or build an adapter at the Gateway boundary |
| `model-client.ts` listed in folder layout but **not provided** in source | **n/a** | Bridge to Component 8's `LLMRouter` is the natural mapping |
| No tool registry, no memory, no guardrails, no tracing wired in | **P0** | Constructor-inject Components 3-6 dependencies; thread `traceId` through every call |
| No max-iteration / step-budget guard | **P0** | LLM-driven planners loop. Without a cap, a buggy plan can burn unbounded tokens. |
| No test file in source paste | **n/a** | Drill per §43 — at minimum: happy path + budget exhausted + tool-step routed to dispatcher + failed-step error propagation |
| No drill | **P0** | Per §43, with the 3+ negative assertions above |

### Component 10 — Agent Workflow Engine

| Gap | Severity | Fix |
|---|---|---|
| `simulateToolExecution(toolName)` only throws when `toolName` is empty — but `ToolSelector.select()` ALWAYS returns a non-empty string (default `"default_agent_executor"`), so the `catch → replan` branch in `runNext()` is **unreachable** for any realistic flow. Same theatre-catch pattern as Component 2's `Executor`. | **P0** | Replace with a real tool invocation (delegate to Component 3's `ToolDispatcher`); the catch then handles real failures |
| `RollbackManager.rollback()` returns `{...restored, status: "rolled_back"}` but never `save()`s this overridden state back. The store still holds `restored` with its original status. Next `store.get()` returns inconsistent state vs what the caller saw. | **P1** | Call `store.save({...restored, status: "rolled_back"})` before returning |
| `runNext()` mutates `step.status = "running"` BEFORE any save. If the process crashes during `simulateToolExecution`, "running" is never persisted → on restart, the step looks `pending` again and runs twice. | **P1** | Save state with `status: "running"` before awaiting; on success save again with `"completed"` |
| `runNext()` returns `{ ...state, currentStepIndex: state.currentStepIndex + 1 }` — spread is shallow, so `nextState.steps` is the SAME array as the in-memory state. Works only because `store.save` calls `structuredClone`. Easy to break by removing the clone. | **P2** | Explicit deep copy at construction time; document the contract |
| `Replanner.replan()` inserts the recovery step AFTER `currentStepIndex` — so the original failed step at `currentStepIndex` is included in the "completed" prefix slice. Caller has to know to skip the failed step. | **P2** | Slice up to `currentStepIndex` (exclusive) instead, OR mark the failed step `skipped` |
| `WorkflowStateStore.history` grows unbounded — every `save()` pushes the prior version. Long-running workflows leak memory. | **P1** | Cap history length (e.g., last 50 versions); compact older ones |
| `WorkflowState.history` is in-memory only — process restart = workflow lost | **P0** | Postgres + outbox pattern OR Temporal/Durable Objects for real durability |
| No tenant filter on `store.get()` / `store.rollback()` — any caller with a `workflowId` can read/rollback any tenant's workflow | **P0** | Pass `WorkflowContext` to every accessor; enforce `state.context.tenantId === caller.tenantId` |
| `HumanApprovalGate.requestApproval` just logs to console — no real queue, no UI route, no expiry, no escalation if unanswered | **P0** | Push to durable queue (e.g., Postgres `approvals` table) + UI + 24h escalation per CLAUDE.md §48.6 |
| Test asserts only `currentStepIndex === 1` — single positive assertion. No verification of: rollback restoring prior state, approval gate blocking, replan recovery actually running, tenant isolation, history cap behavior | **P0** | Per CLAUDE.md §43, ≥3 negative drills required |

### Component 3 — Tool Registry / Dispatcher

| Gap | Severity | Fix |
|---|---|---|
| Registry is per-process; no shared state across replicas | **P1** | Tool catalog from config + signature pinning per CLAUDE.md §50 catalog pattern |
| Responsible-AI guard is a substring matcher | **P1** | Use a real classifier (Llama Guard / Bedrock Guardrails) OR document the substring approach as detection-only, not enforcement |
| No idempotency key on `dispatch` | **P1** | `Idempotency-Key` header → cache by `(toolName, key)` for duplicates |
| Telemetry is `console.log` | **P1** | Real OTel `tracer.startActiveSpan()` with carrier injection |

### Component 4 — Memory Governance

| Gap | Severity | Fix |
|---|---|---|
| PII masker uses ASCII-only regex; misses Unicode emails / international phones | **P1** | Use `validator.js` + libphonenumber; add credit-card Luhn check |
| `findByKey` is O(n) over `Map.values()` | **P2** | Index by `(tenantId, userId, key)` |
| `rollback` only rolls back ONE version; multi-step rollback not supported | **P2** | Record `versions` as a list; rollback-to-version-N |
| Audit log is in-memory `[]` — lost on restart | **P0** | Append-only Postgres table; per §38 audit row schema |
| No tenant isolation enforcement — caller can pass any tenantId | **P0** | tenant_id from auth context, not request body |
| No encryption-at-rest for sensitive values | **P1** | Fernet/AES-GCM per CLAUDE.md §4.2 |
| No drill | **P0** | Drill: wrong-tenant read returns 0 rows; rollback restores prior; PII masked before write |

### Component 5 — Responsible-AI Guardrails

| Gap | Severity | Fix |
|---|---|---|
| Prompt-injection detector is **6 hand-written substrings** | **P0** | Use a classifier model (Llama Guard, ProtectAI, Bedrock Guardrails). Substring lists fail to the first creative attacker. |
| PII detector — same regex limitations as Component 4 | **P1** | Library-based detection |
| Approval gate `createApprovalTicket` logs to console; no actual queue | **P0** | Push to durable queue (SQS/Kafka) + human-review UI |
| Severity → decision mapping is hardcoded | **P2** | Policy-as-code: OPA / Cedar rules file |
| No baseline rate of false-positives measured | **P1** | Per §48 fairness: track false-positive rate per tenant; alert on drift |
| No drill | **P0** | Drill: known-attack corpus → expected decision; verify no false-positive on benign PII like address in support ticket |

### Component 6 — Observability

| Gap | Severity | Fix |
|---|---|---|
| Calls itself "tracer" but emits `console.log` — **not OpenTelemetry** | **P0** | Use `@opentelemetry/sdk-node` with OTLP exporter; spans must propagate via W3C traceparent headers |
| Metrics are `console.log` — no Prometheus scrape, no histogram bucketing | **P0** | Use `@opentelemetry/metrics` or `prom-client` with `/metrics` endpoint |
| `AIOpsEventBus.publish` logs to console — no real bus | **P0** | Kafka topic or webhook to incident-response system |
| No sampling strategy | **P1** | Probabilistic + always-on-error sampling |
| `traceOperation` swallows error type — re-throws `error` but loses original stack in some Node versions | **P2** | Verify by test that stack survives across the `.catch` boundary |
| No drill | **P0** | Drill: span survives 3-hop call chain; metric labels match cardinality budget |

### Component 7 — Resilience (Circuit Breaker)

| Gap | Severity | Fix |
|---|---|---|
| **Half-open race condition** — multiple concurrent requests can enter half-open simultaneously, defeating the breaker | **P0** | Add semaphore: only 1 in-flight in half-open; others fall back |
| `recordSuccess()` resets `failureCount` to 0 — single success after sustained failure flips to closed too eagerly | **P1** | Require N consecutive successes in half-open before close |
| `RetryPolicy` uses `Math.pow(2, attempt)` — exponential but no jitter; thundering herd risk | **P1** | Add jitter: `delayMs * (1 + Math.random())` |
| `Timeout` uses `Promise.race` — the operation keeps running after timeout (no actual cancellation) | **P1** | Use `AbortController` and ensure operation honors `signal` |
| `FallbackHandler` does NOT differentiate cache-replay from real fallback — both look identical in observability | **P1** | Tag fallback_source: `cache` / `static` / `degraded_model` |
| `ResilientExecutor` constructs `Timeout`, `RetryPolicy`, `FallbackHandler` in constructor — not injected, hard to mock | **P2** | DI per CLAUDE.md §3 |
| No drill | **P0** | Drill steps: timeout actually aborts; circuit opens after N; half-open only allows 1; fallback tagged correctly |

### Component 8 — LLM Router

| Gap | Severity | Fix |
|---|---|---|
| `LLMClient.complete` returns a fake string — there is **no real provider call** | **P0** | Wire real provider SDKs (Anthropic / OpenAI / Bedrock / Ollama HTTP) with timeout + auth |
| `RoutingPolicy.selectModel` hardcodes `<= 1.0 USD` as "affordable" | **P1** | Per-tenant budget from config; cumulative spend tracking per CLAUDE.md §41.1 |
| `SafetyGate` — same substring problem as Component 5 | **P0** | Real classifier |
| No fallback model when primary fails | **P1** | Try priority-2 model on failure; per CLAUDE.md §38 fallback-model gate |
| No model output validation (was the response actually JSON? did it follow the schema?) | **P1** | Zod validation of LLM response shape |
| No cost ledger — `estimatedCostUsd` is computed but never accumulated | **P1** | Per-tenant + per-user cost rollup; alert at 80% budget |
| No drill | **P0** | Drill: cost-cap rejects; safety-gate blocks; missing provider → fallback; correct model picked per task type |

### Component 9 — RAG Orchestrator

| Gap | Severity | Fix |
|---|---|---|
| `Retriever` is **keyword-match against in-memory `Chunk[]`** — not vector search | **P0** | Use real vector DB (pgvector / Qdrant / Weaviate); the existing `services/retrieval-svc/` already does this |
| `Reranker` is "+3 if exact substring" — not a cross-encoder | **P0** | Real reranker model (`bge-reranker-large`, Cohere rerank, etc.) |
| `GroundingChecker` is **bag-of-words overlap** — passes "the the the the the the" against any answer | **P0** | Use NLI model (e.g., `vectara/hallucination_evaluation_model`) OR Ragas faithfulness metric per CLAUDE.md §59.4 |
| `CitationValidator.validate` only **formats** citation strings — doesn't verify the answer spans actually reference those chunks | **P0** | Span-level citation extraction (regex `[doc:chunk]` markers in LLM output, then verify chunk_id exists in retrieval set) |
| `QualityScorer` weights are magic numbers (25/25/40/10) | **P2** | Tune against golden eval set; track score correlation with human rating |
| Test fixture text has no blank-line paragraph separators, so `Chunker` produces only **1 chunk** — the `chunks.length >= 2` branch of `QualityScorer` is never exercised | **P3** | Fixture should include `\n\n` between paragraphs to exercise multi-chunk path |
| Test asserts only `citations.length > 0` and `qualityScore > 0` — no negative assertion, no faithfulness threshold | **P1** | Add: wrong-tenant retrieval returns 0; query with no matching terms returns 0 citations; ungrounded answer (random text) flagged `grounded: false` |
| No drill | **P0** | Drill: faithfulness ≥ 0.85 on golden set; uncited claim → flagged; tenant isolation in retrieval |

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

This folder has **0/10** of those.

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
> These components have zero evidence. They demonstrate ideas well,
> nothing more.
