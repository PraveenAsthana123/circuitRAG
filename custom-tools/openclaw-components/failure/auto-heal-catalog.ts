// Iter 134 (2026-05-20): auto-heal catalog. Closes P1 GAPS row
// "'Auto-Heal' in §12 incident management is named but unscoped
// — what can/cannot auto-heal?"
//
// Auto-heal is the SUBSET of iter 133's failure decision matrix
// where the system recovers itself without operator/human input.
// The other failures need either ESCALATION (ops fixes config /
// credentials / permissions) or HITL_REVIEW (human inspects
// content / decision before continuing). Every FailureKind in
// the iter 133 matrix MUST land in exactly one of these 3
// buckets — proved by the drill.
//
// Three-bucket taxonomy:
//   AUTO_HEALABLE       — system retries / circuits / falls back
//                          on its own; no human involved
//   ESCALATION_REQUIRED — ops must fix config / secret / permission
//                          before retry can succeed (paging on-call)
//   HITL_REQUIRED       — human must review content / decision
//                          before the workflow continues (queue +
//                          UI per iter 119 HumanReviewQueue)
//
// Per CLAUDE.md §43 (drillable), §47.7 (auto-heal is the app-layer
// rollback for transient failures), §57.7 (auto-heal scope is now
// drilled, not "everything that LOOKS recoverable"), §59.1 MDD
// (catalog is DERIVED from the iter 133 matrix — single source of
// truth; future failure kinds added to the matrix automatically
// flow through the categorizer).

import {
  FailureKind,
  FailureCategory,
  decisionFor,
  allDecisions,
} from "./failure-decision-matrix";

export type AutoHealBucket =
  | "auto_healable"
  | "escalation_required"
  | "hitl_required";

export interface AutoHealEntry {
  readonly failureKind: FailureKind;
  readonly category: FailureCategory;
  readonly healingStrategy: "retry" | "circuit_breaker" | "fallback_model";
  readonly maxAttempts: number;
  /** Estimated wall-clock for the heal to converge (worst-case sum
   *  of backoffs + per-attempt cost). Used by §53 item 35 DR metrics. */
  readonly estimatedRecoverySeconds: number;
}

export interface EscalationEntry {
  readonly failureKind: FailureKind;
  readonly escalationTarget: string;  // operator-readable: "ops", "platform", "auth-team"
  readonly reason: string;
}

export interface HITLEntry {
  readonly failureKind: FailureKind;
  readonly reviewQueue: string;       // matches iter 119 HumanReviewQueue id
  readonly reason: string;
}

// ───────────────────────────── Bucketing ─────────────────────────

/** Maps a failure kind to its auto-heal bucket. The result is
 *  the §57.7 honest answer to "can this auto-heal?" */
export function bucketFor(kind: FailureKind): AutoHealBucket {
  const d = decisionFor(kind);

  // Safety: anything requiring HITL is HITL — first precedence.
  if (d.requiresHITL) return "hitl_required";

  // Escalation: PRIMARY strategy is escalation (ops fix needed
  // before any recovery is possible).
  if (d.primaryStrategy === "escalation") {
    return "escalation_required";
  }

  // Caller-bug: both strategies fail_fast (e.g., 4xx invalid
  // request). NOT auto-healable — the caller must fix the input.
  // Ops sees these to identify the calling service that needs a fix.
  if (d.primaryStrategy === "fail_fast" && d.secondaryStrategy === "fail_fast") {
    return "escalation_required";
  }

  // Everything else has at least one recovery strategy (retry /
  // circuit_breaker / fallback_model) — auto-healable. This
  // includes:
  //   - primary=fallback_model + secondary=escalation
  //     (model_quota_exceeded — fallback heals; escalation is the
  //     ops-visible escape hatch when fallback also fails)
  //   - primary=fail_fast + secondary=fallback_model
  //     (circuit_open_already — fail-fast preserves recovery
  //     window, secondary routes to fallback)
  return "auto_healable";
}

export function isAutoHealable(kind: FailureKind): boolean {
  return bucketFor(kind) === "auto_healable";
}

// ───────────────────────────── Catalogs ─────────────────────────

const ESCALATION_TARGETS: Partial<Record<FailureKind, { target: string; reason: string }>> = {
  permanent_4xx_invalid_request: {
    target: "caller-team",
    reason: "Input bug in the calling service. Retrying = self-DoS; caller must fix.",
  },
  permanent_auth_401: {
    target: "auth-ops",
    reason: "Credential expired or missing. Rotate secret + redeploy.",
  },
  permanent_auth_403: {
    target: "auth-ops",
    reason: "Credential valid but lacks permission. Grant review required.",
  },
  tool_authorization_denied: {
    target: "platform",
    reason: "Tool scope denial. Operator must grant or refuse the scope.",
  },
  model_quota_exceeded: {
    target: "ai-platform",
    reason: "Token/quota cap reached. Increase quota or route permanently to fallback.",
  },
};

const HITL_QUEUES: Partial<Record<FailureKind, { queue: string; reason: string }>> = {
  guardrail_block: {
    queue: "guardrail-review",
    reason: "Content flagged by safety guardrail. Human reviewer determines whether to override.",
  },
  hallucination_detected: {
    queue: "rag-review",
    reason: "RAG answer cites chunks not in retrieval set (§48.5 violation). Reviewer verifies + corrects.",
  },
  data_integrity_violation: {
    queue: "data-integrity-review",
    reason: "Stored data violates invariant. Retrying could amplify corruption — human must investigate.",
  },
  planner_invalid_plan: {
    queue: "planner-review",
    reason: "Planner produced invalid plan after retry. Reviewer inspects goal + plan space.",
  },
};

export function autoHealCatalog(): ReadonlyArray<AutoHealEntry> {
  return allDecisions()
    .filter((d) => bucketFor(d.failureKind) === "auto_healable")
    .map((d) => {
      // Effective heal strategy: when primary is fail_fast (e.g.,
      // circuit_open_already), the SECONDARY is what actually
      // recovers. Otherwise the primary is the heal.
      const effectiveStrategy = d.primaryStrategy === "fail_fast"
        ? d.secondaryStrategy
        : d.primaryStrategy;
      return {
        failureKind: d.failureKind,
        category: d.category,
        healingStrategy: effectiveStrategy as AutoHealEntry["healingStrategy"],
        maxAttempts: d.maxAttempts,
        estimatedRecoverySeconds: estimateRecoverySeconds(d.maxAttempts, d.initialBackoffMs),
      };
    });
}

export function escalationCatalog(): ReadonlyArray<EscalationEntry> {
  return allDecisions()
    .filter((d) => bucketFor(d.failureKind) === "escalation_required")
    .map((d) => {
      const meta = ESCALATION_TARGETS[d.failureKind];
      return {
        failureKind: d.failureKind,
        escalationTarget: meta?.target ?? "platform",
        reason: meta?.reason ?? d.rationale,
      };
    });
}

export function hitlCatalog(): ReadonlyArray<HITLEntry> {
  return allDecisions()
    .filter((d) => bucketFor(d.failureKind) === "hitl_required")
    .map((d) => {
      const meta = HITL_QUEUES[d.failureKind];
      return {
        failureKind: d.failureKind,
        reviewQueue: meta?.queue ?? "general-review",
        reason: meta?.reason ?? d.rationale,
      };
    });
}

export function escalationTargetFor(kind: FailureKind): string | undefined {
  if (bucketFor(kind) !== "escalation_required") return undefined;
  return ESCALATION_TARGETS[kind]?.target ?? "platform";
}

// ───────────────────────────── Helpers ────────────────────────────

function estimateRecoverySeconds(maxAttempts: number, initialBackoffMs?: number): number {
  // Worst-case = sum of exponential backoffs + 200ms per attempt for the request itself
  let totalMs = 0;
  for (let i = 0; i < maxAttempts; i++) {
    totalMs += 200; // per-attempt request cost estimate
    if (initialBackoffMs !== undefined) {
      totalMs += initialBackoffMs * Math.pow(2, i);
    }
  }
  return Math.ceil(totalMs / 1000);
}
