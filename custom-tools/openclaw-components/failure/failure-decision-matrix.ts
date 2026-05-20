// Iter 133 (2026-05-20): failure-handling decision matrix. Closes
// P1 GAPS row "§13 Failure Handling Flow shows 'Circuit Breaker →
// Retry → Fallback Model → Escalation → HITL Review' without
// saying when to choose which."
//
// Until this iter, the 5 strategies were a linear sequence in the
// reference architecture diagram. In reality the right strategy
// depends on the FAILURE KIND — a 4xx invalid-request MUST NOT
// retry (the input is wrong; retry is denial-of-service against
// yourself); a guardrail block MUST go to HITL not retry (the
// content was flagged for a reason); auth 401 MUST escalate not
// retry (brute-force against config/secret).
//
// This iter ships:
//   1. FailureKind taxonomy (15 named failure types covering
//      transient / permanent / safety / quota categories).
//   2. FailureStrategy → operator-actionable response.
//   3. decisionMatrix() — the typed lookup that returns the
//      strategy for a failure kind.
//   4. nextAction(failure, attemptNumber) — the per-attempt
//      decision engine: retry / escalate / fail-fast / HITL.
//   5. Composes with iter 130 NFR (failures feed cycleDurationsMs +
//      alert levels), iter 131 KPI (FPR/TPR tracks how often
//      strategies fire), iter 132 risk-class (HIGH-RISK failures
//      escalate sooner per Art. 14 human-oversight).
//
// Per CLAUDE.md §43 (drillable), §47.6 STRIDE (failure kinds map
// to STRIDE categories — e.g., auth 401 = Elevation), §57.7
// (the matrix prevents the easy-but-wrong "always retry" reflex
// that turns a transient blip into a self-inflicted DoS).

// ───────────────────────────── Types ─────────────────────────────

export type FailureCategory =
  | "transient"   // expected to recover on retry / backoff / failover
  | "permanent"   // will not recover — different action needed
  | "safety"      // guardrail / policy flag — not a "failure" per se but a STOP
  | "quota";      // rate-limit / token-budget / capacity

export type FailureStrategy =
  | "retry"           // exponential backoff, bounded attempts
  | "circuit_breaker" // open the breaker, fail-fast subsequent calls
  | "fallback_model"  // route to alternate provider/model
  | "escalation"      // page on-call (config/secret/permissions issue)
  | "hitl_review"     // human-in-the-loop required before continuing
  | "fail_fast";      // refuse immediately, no retry

export type FailureKind =
  // Transient
  | "transient_network_5xx"
  | "transient_rate_limit_429"
  | "transient_timeout"
  | "transient_provider_5xx"
  // Permanent
  | "permanent_4xx_invalid_request"
  | "permanent_auth_401"
  | "permanent_auth_403"
  | "data_integrity_violation"
  | "tool_authorization_denied"
  | "planner_invalid_plan"
  // Safety
  | "guardrail_block"
  | "hallucination_detected"
  // Quota / capacity
  | "model_quota_exceeded"
  | "circuit_open_already"
  | "timeout_breach_p95";

/** §47.6 STRIDE category the failure belongs to. */
export type STRIDECategory = "S" | "T" | "R" | "I" | "D" | "E" | "N";  // N = not-stride

export interface FailureDecision {
  readonly failureKind: FailureKind;
  readonly category: FailureCategory;
  readonly primaryStrategy: FailureStrategy;
  /** Strategy when primary is exhausted (maxAttempts reached). */
  readonly secondaryStrategy: FailureStrategy;
  /** Max attempts of primary strategy before falling through to secondary.
   *  fail_fast / escalation strategies have maxAttempts=1 (no retry). */
  readonly maxAttempts: number;
  /** Initial backoff for retry strategies. undefined when not applicable. */
  readonly initialBackoffMs?: number;
  /** True iff this failure MUST be persisted to §38 decision audit row. */
  readonly recordToAudit: boolean;
  /** True iff a human MUST review before the next attempt. */
  readonly requiresHITL: boolean;
  /** STRIDE category for STRIDE-aware threat modeling. */
  readonly strideCategory: STRIDECategory;
  /** Operator-readable rationale for the chosen strategy. */
  readonly rationale: string;
}

export interface NextActionInput {
  readonly failureKind: FailureKind;
  readonly attemptNumber: number;  // 1-indexed; first attempt = 1
  /** When provided, high-risk classifications can shorten the
   *  retry envelope (Art. 14 human-oversight bias toward HITL). */
  readonly riskLevel?: "prohibited" | "high_risk" | "limited_risk" | "minimal_risk";
}

export interface NextAction {
  readonly action: FailureStrategy;
  readonly attemptNumber: number;
  readonly nextBackoffMs?: number;
  readonly reason: string;
  readonly remainingAttempts: number;
}

// ───────────────────────────── Decision matrix ───────────────────

const MATRIX: Record<FailureKind, FailureDecision> = {
  transient_network_5xx: {
    failureKind: "transient_network_5xx",
    category: "transient",
    primaryStrategy: "retry",
    secondaryStrategy: "circuit_breaker",
    maxAttempts: 3,
    initialBackoffMs: 500,
    recordToAudit: false,  // transient noise — not every blip
    requiresHITL: false,
    strideCategory: "N",
    rationale: "Network 5xx is typically transient; retry with exponential backoff then open circuit if persistent.",
  },
  transient_provider_5xx: {
    failureKind: "transient_provider_5xx",
    category: "transient",
    primaryStrategy: "retry",
    secondaryStrategy: "fallback_model",
    maxAttempts: 2,
    initialBackoffMs: 1000,
    recordToAudit: false,
    requiresHITL: false,
    strideCategory: "N",
    rationale: "Provider outage — retry briefly then route to fallback model.",
  },
  transient_rate_limit_429: {
    failureKind: "transient_rate_limit_429",
    category: "quota",
    primaryStrategy: "retry",
    secondaryStrategy: "fallback_model",
    maxAttempts: 4,
    initialBackoffMs: 2000,  // longer — respect Retry-After
    recordToAudit: true,     // quota tracking
    requiresHITL: false,
    strideCategory: "D",     // DoS (self-inflicted if not paced)
    rationale: "Rate limit — respect Retry-After header; if persistent, route to fallback to preserve user latency.",
  },
  transient_timeout: {
    failureKind: "transient_timeout",
    category: "transient",
    primaryStrategy: "retry",
    secondaryStrategy: "circuit_breaker",
    maxAttempts: 1,            // one retry only — timeouts cascade
    initialBackoffMs: 0,
    recordToAudit: false,
    requiresHITL: false,
    strideCategory: "D",
    rationale: "Timeout — single retry then circuit-break. Retrying timeouts compounds latency.",
  },
  permanent_4xx_invalid_request: {
    failureKind: "permanent_4xx_invalid_request",
    category: "permanent",
    primaryStrategy: "fail_fast",
    secondaryStrategy: "fail_fast",
    maxAttempts: 1,
    recordToAudit: true,  // input validation failure — caller needs to know
    requiresHITL: false,
    strideCategory: "T",
    rationale: "4xx invalid request is a client bug. Retrying = self-inflicted DoS against the API surface.",
  },
  permanent_auth_401: {
    failureKind: "permanent_auth_401",
    category: "permanent",
    primaryStrategy: "escalation",
    secondaryStrategy: "fail_fast",
    maxAttempts: 1,        // NEVER retry auth — looks like brute-force
    recordToAudit: true,
    requiresHITL: false,
    strideCategory: "S",   // Spoofing / Elevation
    rationale: "401 = expired/missing credential. Retrying brute-forces the auth provider. Escalate to ops for rotation.",
  },
  permanent_auth_403: {
    failureKind: "permanent_auth_403",
    category: "permanent",
    primaryStrategy: "escalation",
    secondaryStrategy: "fail_fast",
    maxAttempts: 1,
    recordToAudit: true,
    requiresHITL: false,
    strideCategory: "E",   // Elevation of privilege
    rationale: "403 = credential valid but lacks permission. Retrying changes nothing; escalate to ops for grant review.",
  },
  data_integrity_violation: {
    failureKind: "data_integrity_violation",
    category: "permanent",
    primaryStrategy: "fail_fast",
    secondaryStrategy: "hitl_review",
    maxAttempts: 1,        // corruption = no idempotency promise
    recordToAudit: true,
    requiresHITL: true,
    strideCategory: "T",   // Tampering
    rationale: "Data integrity violation. Retrying could amplify corruption. Halt + HITL review.",
  },
  tool_authorization_denied: {
    failureKind: "tool_authorization_denied",
    category: "permanent",
    primaryStrategy: "escalation",
    secondaryStrategy: "fail_fast",
    maxAttempts: 1,
    recordToAudit: true,
    requiresHITL: false,
    strideCategory: "E",
    rationale: "Tool scope denial. Retrying changes nothing — operator must grant or refuse the scope.",
  },
  planner_invalid_plan: {
    failureKind: "planner_invalid_plan",
    category: "permanent",
    primaryStrategy: "retry",        // one replan attempt
    secondaryStrategy: "hitl_review",
    maxAttempts: 2,
    initialBackoffMs: 0,
    recordToAudit: true,
    requiresHITL: true,
    strideCategory: "T",
    rationale: "Plan failed schema validation. Replan once (planner may converge); on second failure, halt + HITL.",
  },
  guardrail_block: {
    failureKind: "guardrail_block",
    category: "safety",
    primaryStrategy: "hitl_review",   // NOT a retry — content was flagged for a reason
    secondaryStrategy: "fail_fast",
    maxAttempts: 1,
    recordToAudit: true,
    requiresHITL: true,
    strideCategory: "I",  // InfoDisclosure
    rationale: "Guardrail flagged content. Retrying is bypass attempt; route to human reviewer.",
  },
  hallucination_detected: {
    failureKind: "hallucination_detected",
    category: "safety",
    primaryStrategy: "fallback_model",  // try a more capable model
    secondaryStrategy: "hitl_review",
    maxAttempts: 2,
    initialBackoffMs: 0,
    recordToAudit: true,
    requiresHITL: true,
    strideCategory: "T",
    rationale: "Hallucination detected (citation accuracy < 100% per §48.5). Try fallback model; on second failure HITL.",
  },
  model_quota_exceeded: {
    failureKind: "model_quota_exceeded",
    category: "quota",
    primaryStrategy: "fallback_model",
    secondaryStrategy: "escalation",
    maxAttempts: 1,
    recordToAudit: true,
    requiresHITL: false,
    strideCategory: "D",
    rationale: "Token/quota cap reached. Route to fallback; if also exhausted, escalate to ops for budget review.",
  },
  circuit_open_already: {
    failureKind: "circuit_open_already",
    category: "transient",
    primaryStrategy: "fail_fast",
    secondaryStrategy: "fallback_model",
    maxAttempts: 1,
    recordToAudit: false,  // breaker open is expected when downstream is bad
    requiresHITL: false,
    strideCategory: "D",
    rationale: "Circuit breaker open. Fail-fast preserves the downstream's recovery window; route to fallback if available.",
  },
  timeout_breach_p95: {
    failureKind: "timeout_breach_p95",
    category: "quota",
    primaryStrategy: "circuit_breaker",
    secondaryStrategy: "fallback_model",
    maxAttempts: 1,
    recordToAudit: true,    // SLO breach
    requiresHITL: false,
    strideCategory: "D",
    rationale: "p95 latency breaching SLO. Open circuit to shed load; route to fallback if available.",
  },
};

/** Lookup strategy for a failure kind. */
export function decisionFor(kind: FailureKind): FailureDecision {
  return MATRIX[kind];
}

/** Returns the matrix as an immutable array (for catalog / docs). */
export function allDecisions(): ReadonlyArray<FailureDecision> {
  return Object.values(MATRIX);
}

// ───────────────────────────── Per-attempt engine ────────────────

export function nextAction(input: NextActionInput): NextAction {
  const d = decisionFor(input.failureKind);

  // High-risk classifications shorten the retry envelope by 1
  // (Art. 14 human-oversight bias). Minimum 1 attempt.
  const adjustedMax = input.riskLevel === "high_risk"
    ? Math.max(1, d.maxAttempts - 1)
    : d.maxAttempts;

  if (input.attemptNumber < 1) {
    throw new Error(`attemptNumber must be >= 1 (got ${input.attemptNumber})`);
  }

  if (input.attemptNumber <= adjustedMax) {
    // Still within primary strategy envelope.
    const nextBackoffMs = d.initialBackoffMs !== undefined
      ? d.initialBackoffMs * Math.pow(2, input.attemptNumber - 1)
      : undefined;
    return {
      action: d.primaryStrategy,
      attemptNumber: input.attemptNumber,
      nextBackoffMs,
      reason: `Primary strategy ${d.primaryStrategy} (attempt ${input.attemptNumber}/${adjustedMax})${input.riskLevel === "high_risk" ? " — high-risk envelope shortened" : ""}`,
      remainingAttempts: adjustedMax - input.attemptNumber,
    };
  }

  // Primary exhausted → secondary
  return {
    action: d.secondaryStrategy,
    attemptNumber: input.attemptNumber,
    reason: `Primary ${d.primaryStrategy} exhausted after ${adjustedMax} attempts; falling through to ${d.secondaryStrategy}`,
    remainingAttempts: 0,
  };
}
