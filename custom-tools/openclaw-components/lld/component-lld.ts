// Iter 135 (2026-05-20): per-component Low-Level Design (LLD)
// registry. Closes P1 GAPS row "§5 LLD table lists 10 components
// in one sentence each — insufficient for engineering."
//
// Until this iter, the §5 LLD table was a one-liner per component
// ("Gateway: receives messages, routes them"). For engineering
// onboarding, incident triage, and §47 boundary discipline, that's
// useless — a new engineer can't tell what interfaces a component
// exposes, what errors it can throw, what NFRs/KPIs gate its
// release, or which components depend on it.
//
// This iter ships:
//   1. ComponentLLD type with 7 mandatory fields per component:
//        - id, description, primaryInterfaces, errorEnvelopes,
//          nfrRefs, kpiRefs, composesWith, riskCategories, owner
//   2. COMPONENT_LLDS — registry of all 10 components in the
//      openclaw-components folder, populated from real code.
//   3. Helpers: lldFor(id), componentsThatCompose(id),
//      validateRegistry(), interfacesByComponent(), etc.
//   4. Cross-reference validation drill — every composesWith
//      entry resolves to a real componentId; every nfrRef
//      resolves to a real NFR id from iter 130; every kpiRef
//      resolves to a real KPI id from iter 131.
//
// Per CLAUDE.md §43 (drillable), §47 (boundary discipline — LLD
// IS the boundary spec), §47.6 STRIDE per-container, §53 item 42
// documentation (LLD is the per-component onboarding artifact),
// §57.7 (the LLD is now drilled, not "documentation we keep
// promising to write"), §59.1 MDD (LLD is the model; the
// implementation derives from it).

import { CANONICAL_FLEET_NFRS } from "../nfr/nfr-targets";
import { CANONICAL_KPIS } from "../kpi/kpi-targets";

// ───────────────────────────── Types ─────────────────────────────

/** The 10 openclaw components — folder-named. */
export type ComponentId =
  | "01-gateway"
  | "02-agent-runtime"
  | "03-tooling"
  | "04-memory-governance"
  | "05-guardrails"
  | "06-observability"
  | "07-resilience"
  | "08-llm-router"
  | "09-rag-orchestrator"
  | "10-agent-workflow";

/** §47.6 STRIDE category — multi-select per component. */
export type STRIDECategory = "S" | "T" | "R" | "I" | "D" | "E";

export interface InterfaceDef {
  /** Symbol name (interface / class). */
  readonly name: string;
  /** File path relative to component folder. */
  readonly file: string;
  /** Short summary of the surface. */
  readonly surface: string;
  /** True iff this interface is a §52 boundary seam (DI point). */
  readonly isSeam: boolean;
}

export interface ErrorEnvelopeDef {
  readonly className: string;
  readonly file: string;
  /** What category of failure this signals. Maps to iter 133 FailureKind. */
  readonly failureKindHint: string;
}

export interface ComponentLLD {
  readonly id: ComponentId;
  readonly description: string;
  readonly primaryInterfaces: ReadonlyArray<InterfaceDef>;
  readonly errorEnvelopes: ReadonlyArray<ErrorEnvelopeDef>;
  /** NFR ids from iter 130 CANONICAL_FLEET_NFRS that gate this component. */
  readonly nfrRefs: ReadonlyArray<string>;
  /** KPI ids from iter 131 CANONICAL_KPIS that gate this component. */
  readonly kpiRefs: ReadonlyArray<string>;
  /** Component ids this component depends on at runtime. */
  readonly composesWith: ReadonlyArray<ComponentId>;
  /** STRIDE threat categories most relevant to this component. */
  readonly riskCategories: ReadonlyArray<STRIDECategory>;
  readonly owner: string;
}

// ───────────────────────────── Registry ─────────────────────────────

export const COMPONENT_LLDS: ReadonlyArray<ComponentLLD> = [
  {
    id: "01-gateway",
    description: "Ingress for user messages from chat / web / CLI channels; mints requestId + creates SessionState; routes to AgentRuntime.",
    primaryInterfaces: [
      { name: "Gateway", file: "channel-router.ts", surface: "handleMessage(UserMessage) → AgentResponse", isSeam: false },
      { name: "SessionManager", file: "session-manager.ts", surface: "getOrCreateSession(UserMessage) → SessionState", isSeam: true },
      { name: "SessionPersistenceStore", file: "session-manager.ts", surface: "get/set/delete/entries/oldestKey/size", isSeam: true },
      { name: "ApiKeyAuthMiddleware", file: "auth.ts", surface: "authenticate(headers) → {tenantId, userId} | throw", isSeam: true },
    ],
    errorEnvelopes: [
      { className: "GatewayError", file: "types.ts", failureKindHint: "permanent_4xx_invalid_request" },
    ],
    nfrRefs: ["reconcile-latency-p95"],  // gateway latency proxies via the daemon's reconcile loop
    kpiRefs: [],
    composesWith: ["02-agent-runtime", "06-observability"],
    riskCategories: ["S", "I", "D"],  // Spoofing (auth), InfoDisclosure (PII in request), DoS (rate limit)
    owner: "platform",
  },
  {
    id: "02-agent-runtime",
    description: "Plans and executes agent steps; orchestrates LLM calls + tool dispatch; persists state via WorkflowStateStore.",
    primaryInterfaces: [
      { name: "AgentRuntime", file: "agent-runtime.ts", surface: "run(goal, context) → AgentResult", isSeam: false },
      { name: "Planner", file: "planner.ts", surface: "createPlan(goal, context) → AgentPlan", isSeam: false },
      { name: "PlanProvider", file: "planner.ts", surface: "createPlan(...) — DI seam", isSeam: true },
      { name: "Executor", file: "executor.ts", surface: "executeStep(step, context) → StepResult", isSeam: false },
    ],
    errorEnvelopes: [
      { className: "InvalidPlanError", file: "planner.ts", failureKindHint: "planner_invalid_plan" },
      { className: "RetryableError", file: "../10-agent-workflow/types.ts", failureKindHint: "transient_network_5xx" },
    ],
    nfrRefs: ["reconcile-latency-p95"],
    kpiRefs: ["plan_action_validity", "tool_selection_accuracy"],
    composesWith: ["03-tooling", "08-llm-router", "06-observability"],
    riskCategories: ["T", "E"],
    owner: "agent-runtime",
  },
  {
    id: "03-tooling",
    description: "Tool registry + dispatcher; enforces ResponsibleAIGuard before tool execution; emits Telemetry per call.",
    primaryInterfaces: [
      { name: "ToolDispatcher", file: "tool-dispatcher.ts", surface: "dispatch(ToolRequest) → ToolResult", isSeam: false },
      { name: "ToolRegistry", file: "tool-registry.ts", surface: "register/lookup with catalog signatures", isSeam: true },
      { name: "ResponsibleAIGuard", file: "responsible-ai-guard.ts", surface: "validate(ToolRequest)", isSeam: false },
      { name: "ResponsibleAIClassifier", file: "responsible-ai-guard.ts", surface: "classify(ToolRequest) — DI seam (iter 109)", isSeam: true },
      { name: "ToolTelemetrySink", file: "telemetry.ts", surface: "emit(ToolTelemetryEvent) — DI seam (iter 96)", isSeam: true },
    ],
    errorEnvelopes: [
      { className: "ToolCatalogViolationError", file: "tool-registry.ts", failureKindHint: "tool_authorization_denied" },
    ],
    nfrRefs: ["reconcile-latency-p95"],
    kpiRefs: ["tool_selection_accuracy"],
    composesWith: ["05-guardrails", "06-observability"],
    riskCategories: ["E", "T", "I"],
    owner: "agent-runtime",
  },
  {
    id: "04-memory-governance",
    description: "Tenant-scoped memory store with versioning + rollback + audit log; PII masking via §48.4 audit row.",
    primaryInterfaces: [
      { name: "MemoryGovernanceService", file: "memory-governance-service.ts", surface: "store/retrieve/rollback with audit", isSeam: false },
      { name: "MemoryStore", file: "memory-store.ts", surface: "upsert/get/findByKey/rollback/delete tenant-scoped", isSeam: false },
      { name: "MemoryStoreI", file: "../interfaces.ts", surface: "DI seam — Postgres adapter target", isSeam: true },
      { name: "AuditRecordStore", file: "memory-audit-log.ts", surface: "append/listByMemory (iter 104 DI seam)", isSeam: true },
      { name: "Encryptor", file: "encryption.ts", surface: "encrypt/decrypt for at-rest values", isSeam: false },
    ],
    errorEnvelopes: [
      { className: "MemoryAccessDeniedError", file: "memory-store.ts", failureKindHint: "permanent_auth_403" },
      { className: "MemoryNotFoundError", file: "memory-store.ts", failureKindHint: "permanent_4xx_invalid_request" },
    ],
    nfrRefs: [],
    kpiRefs: [],
    composesWith: ["05-guardrails", "06-observability"],
    riskCategories: ["I", "T", "R"],
    owner: "platform",
  },
  {
    id: "05-guardrails",
    description: "PII detection + prompt-injection detection + policy decision + approval queue; per-decision metrics per tenant.",
    primaryInterfaces: [
      { name: "GuardrailEngine", file: "guardrail-engine.ts", surface: "evaluate(request) → GuardrailResult", isSeam: false },
      { name: "PIIDetector", file: "pii-detector.ts", surface: "detect(text) → GuardrailFinding[]", isSeam: false },
      { name: "PIIProvider", file: "pii-detector.ts", surface: "DI seam (iter 102) — Presidio/library", isSeam: true },
      { name: "PromptInjectionClassifier", file: "prompt-injection-detector.ts", surface: "DI seam (iter 101) — Llama Guard", isSeam: true },
      { name: "PolicyEngine", file: "policy-engine.ts", surface: "decide(findings) — config-driven severityMap (iter 46)", isSeam: true },
      { name: "ApprovalGate", file: "approval-gate.ts", surface: "requiresHumanApproval/createApprovalTicket", isSeam: false },
      { name: "HumanReviewQueue", file: "approval-gate.ts", surface: "DI seam (iter 103) — SQS/Kafka/Postgres", isSeam: true },
      { name: "GuardrailDecisionMonitor", file: "guardrail-monitor.ts", surface: "DI seam (iter 104) — metrics emit", isSeam: true },
    ],
    errorEnvelopes: [
      { className: "HumanReviewTicketNotFoundError", file: "approval-gate.ts", failureKindHint: "permanent_4xx_invalid_request" },
      { className: "HumanReviewTicketAlreadyResolvedError", file: "approval-gate.ts", failureKindHint: "permanent_4xx_invalid_request" },
    ],
    nfrRefs: ["reconcile-latency-p95"],
    kpiRefs: ["guardrail_false_positive_rate", "guardrail_true_positive_rate"],
    composesWith: ["06-observability"],
    riskCategories: ["I", "T", "S"],
    owner: "safety",
  },
  {
    id: "06-observability",
    description: "Structured logs + W3C traceparent + metrics counters + AIOps event dispatch; OTel-shaped exporter adapter.",
    primaryInterfaces: [
      { name: "Tracer", file: "tracer.ts", surface: "createSpan/endSpan with W3C traceparent (iter 105)", isSeam: true },
      { name: "OpenTelemetryTraceSink", file: "otel-trace-sink.ts", surface: "exportSpan(OtelSpanRecord) — exporter seam", isSeam: true },
      { name: "MetricsRecorder", file: "metrics.ts", surface: "counter/histogram with bounded labels", isSeam: false },
      { name: "AIOpsEventBus", file: "aiops-event-bus.ts", surface: "publish(topic, event) — dispatcher seam (iter 106)", isSeam: true },
      { name: "AIOpsEventDispatcher", file: "aiops-dispatcher.ts", surface: "DI seam — Kafka/webhook adapter", isSeam: true },
    ],
    errorEnvelopes: [],
    nfrRefs: ["reconcile-latency-p95", "reconcile-cadence"],
    kpiRefs: [],
    composesWith: [],  // foundational — depended-on, doesn't depend
    riskCategories: ["R", "I"],
    owner: "platform",
  },
  {
    id: "07-resilience",
    description: "Circuit breaker + retry + timeout + fallback; ResilienceContext propagated through tool dispatch.",
    primaryInterfaces: [
      { name: "CircuitBreaker", file: "circuit-breaker.ts", surface: "execute(op) with open/closed/half-open states", isSeam: false },
      { name: "RetryHandler", file: "retry.ts", surface: "executeWithRetry(op, policy)", isSeam: false },
      { name: "TimeoutHandler", file: "timeout.ts", surface: "executeWithTimeout(op, ms)", isSeam: false },
      { name: "FallbackHandler", file: "fallback-handler.ts", surface: "executeWithFallback(primary, fallback)", isSeam: false },
    ],
    errorEnvelopes: [
      { className: "CircuitOpenError", file: "circuit-breaker.ts", failureKindHint: "circuit_open_already" },
      { className: "TimeoutError", file: "timeout.ts", failureKindHint: "transient_timeout" },
    ],
    nfrRefs: ["reconcile-latency-p95"],
    kpiRefs: [],
    composesWith: ["06-observability"],
    riskCategories: ["D"],
    owner: "platform",
  },
  {
    id: "08-llm-router",
    description: "Routes LLM requests across providers with cost ledger + safety gate + fallback model selection.",
    primaryInterfaces: [
      { name: "LLMRouter", file: "llm-router.ts", surface: "route(LLMRequest) → LLMResponse with model selection", isSeam: false },
      { name: "SafetyGate", file: "safety-gate.ts", surface: "validate(LLMRequest) — pre-call safety check", isSeam: false },
      { name: "SafetyGateClassifier", file: "safety-gate.ts", surface: "DI seam (iter 107) — Llama Guard", isSeam: true },
      { name: "CostLedger", file: "cost-ledger.ts", surface: "recordCall/getSpend tenant/user-scoped", isSeam: true },
      { name: "ModelCardRegistry", file: "../audit/model-card.ts", surface: "DI seam — required for productionMode (iter 115)", isSeam: true },
    ],
    errorEnvelopes: [
      { className: "SafetyGateBlockedError", file: "safety-gate.ts", failureKindHint: "guardrail_block" },
      { className: "ModelCardMissingError", file: "../audit/model-card.ts", failureKindHint: "permanent_4xx_invalid_request" },
    ],
    nfrRefs: ["reconcile-latency-p95"],
    kpiRefs: ["guardrail_true_positive_rate"],
    composesWith: ["05-guardrails", "07-resilience", "06-observability"],
    riskCategories: ["T", "I", "D"],
    owner: "agent-runtime",
  },
  {
    id: "09-rag-orchestrator",
    description: "Retrieves + reranks + grounds + cites + scores RAG answers per the §48.5 four-part contract.",
    primaryInterfaces: [
      { name: "RAGOrchestrator", file: "rag-orchestrator.ts", surface: "answer(RAGRequest) → RAGResponse with citations", isSeam: false },
      { name: "RetrievalSource", file: "rag-orchestrator.ts", surface: "DI seam (iter 108) — pgvector/Qdrant adapter", isSeam: true },
      { name: "HybridRetriever", file: "hybrid-retriever.ts", surface: "Keyword + Vector + RRF fuse (iter 114)", isSeam: true },
      { name: "GroundingChecker", file: "grounding-checker.ts", surface: "verify(answer, retrieved) — §48.5 invariant", isSeam: false },
      { name: "CitationValidator", file: "citation-validator.ts", surface: "validate(answer.citations, retrieved)", isSeam: false },
      { name: "QualityScorer", file: "quality-scorer.ts", surface: "score(answer, retrieved) → 0..1", isSeam: false },
    ],
    errorEnvelopes: [],
    nfrRefs: ["reconcile-latency-p95"],
    kpiRefs: ["rag_hallucination_rate", "rag_citation_accuracy"],
    composesWith: ["06-observability", "05-guardrails"],
    riskCategories: ["I", "T"],
    owner: "ai-quality",
  },
  {
    id: "10-agent-workflow",
    description: "Multi-step workflow orchestration with status transitions + tool selection + fleet supervision + approval queue.",
    primaryInterfaces: [
      { name: "AgentWorkflowEngine", file: "agent-workflow-engine.ts", surface: "start/runNext/getStatus", isSeam: false },
      { name: "WorkflowStateStore", file: "workflow-state-store.ts", surface: "save/get/rollback tenant-scoped (iter 99)", isSeam: false },
      { name: "WorkflowStatePersistence", file: "workflow-state-store.ts", surface: "DI seam — Postgres/outbox adapter", isSeam: true },
      { name: "ToolSelector", file: "tool-selector.ts", surface: "select(step, tools) → tool", isSeam: false },
      { name: "AgentFleetSupervisor", file: "agent-fleet.ts", surface: "reconcile() → AgentFleetSnapshot", isSeam: false },
      { name: "ApprovalQueue", file: "approval-queue.ts", surface: "enqueue/poll/resolve", isSeam: true },
    ],
    errorEnvelopes: [
      { className: "WorkflowNotFoundError", file: "workflow-state-store.ts", failureKindHint: "permanent_4xx_invalid_request" },
      { className: "WorkflowAccessDeniedError", file: "workflow-state-store.ts", failureKindHint: "permanent_auth_403" },
      { className: "WorkflowIllegalTransitionError", file: "workflow-status-transitions.ts", failureKindHint: "permanent_4xx_invalid_request" },
    ],
    nfrRefs: ["fleet-availability", "reconcile-latency-p95", "reconcile-cadence"],
    kpiRefs: ["plan_action_validity"],
    composesWith: ["02-agent-runtime", "03-tooling", "05-guardrails", "06-observability", "07-resilience"],
    riskCategories: ["T", "D", "E"],
    owner: "agent-runtime",
  },
];

// ───────────────────────────── Helpers ────────────────────────────

export function lldFor(id: ComponentId): ComponentLLD | undefined {
  return COMPONENT_LLDS.find((c) => c.id === id);
}

export function allComponentIds(): ReadonlyArray<ComponentId> {
  return COMPONENT_LLDS.map((c) => c.id);
}

/** Returns components that DEPEND on `id` (reverse-dependency graph). */
export function componentsThatCompose(id: ComponentId): ReadonlyArray<ComponentId> {
  return COMPONENT_LLDS.filter((c) => c.composesWith.includes(id)).map((c) => c.id);
}

/** Returns all DI seam interfaces across the registry. */
export function allSeams(): ReadonlyArray<{ componentId: ComponentId; iface: InterfaceDef }> {
  return COMPONENT_LLDS.flatMap((c) =>
    c.primaryInterfaces.filter((i) => i.isSeam).map((iface) => ({ componentId: c.id, iface })),
  );
}

export interface RegistryValidationResult {
  readonly valid: boolean;
  readonly errors: ReadonlyArray<string>;
}

/** Validates the registry for cross-reference integrity:
 *  - every composesWith resolves to a real componentId
 *  - every nfrRef resolves to a CANONICAL_FLEET_NFRS id
 *  - every kpiRef resolves to a CANONICAL_KPIS id
 *  - no component composes with itself
 *  - exactly one entry per ComponentId (no duplicates) */
export function validateRegistry(): RegistryValidationResult {
  const errors: string[] = [];
  const validNfrIds = new Set(CANONICAL_FLEET_NFRS.map((n) => n.id));
  const validKpiIds = new Set(CANONICAL_KPIS.map((k) => k.id));
  const validComponentIds = new Set(COMPONENT_LLDS.map((c) => c.id));
  const seen = new Set<ComponentId>();

  for (const c of COMPONENT_LLDS) {
    if (seen.has(c.id)) errors.push(`Duplicate component id: ${c.id}`);
    seen.add(c.id);

    for (const dep of c.composesWith) {
      if (dep === c.id) errors.push(`${c.id}: composes with itself`);
      if (!validComponentIds.has(dep)) errors.push(`${c.id}: unknown composesWith target ${dep}`);
    }

    for (const nfr of c.nfrRefs) {
      if (!validNfrIds.has(nfr)) errors.push(`${c.id}: unknown nfrRef ${nfr}`);
    }

    for (const kpi of c.kpiRefs) {
      if (!validKpiIds.has(kpi)) errors.push(`${c.id}: unknown kpiRef ${kpi}`);
    }

    if (!c.description || c.description.length < 30) {
      errors.push(`${c.id}: description must be >= 30 chars (got ${c.description.length})`);
    }
    if (c.primaryInterfaces.length === 0) {
      errors.push(`${c.id}: must have at least 1 primary interface`);
    }
    if (!c.owner) errors.push(`${c.id}: owner is required`);
    if (c.riskCategories.length === 0) {
      errors.push(`${c.id}: must have at least 1 STRIDE risk category`);
    }
  }

  return { valid: errors.length === 0, errors };
}
