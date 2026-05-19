// Iter 110 (2026-05-18): canonical agentic-decision audit row.
//
// Bridges the existing per-component audit emitters (memory_audit,
// approval_ticket, explainability, guardrail_evaluation,
// workflow_rollback, gateway_error) with the §38-compliant
// "every agent decision is a row" contract the Agentic Plan
// requires. This is the SCHEMA + the writer; durable persistence
// is plugged via EventSink (M2.3) — the same seam used by every
// other event emitter.
//
// Per CLAUDE.md §38: every agent decision must be identifiable,
// reproducible, explainable, versioned, auditable. Per the
// Agentic Plan §"Audit And Explainability": "every user-affecting
// agent decision writes a decision audit row" with input hash,
// output hash, model/tool used, policy, confidence, explanation,
// citations.

import { randomUUID, createHash } from "crypto";
import {
  EventSink,
  ConsoleEventSink,
} from "../06-observability/sinks";

/**
 * Decision kinds the row distinguishes. Adding a new kind requires
 * a deliberate union extension (forces audit-consumer review).
 */
export type DecisionKind =
  | "plan"        // planner produced a plan
  | "tool"        // tool selected + dispatched
  | "llm"         // LLM completion
  | "rag"         // retrieval + answer
  | "guardrail"   // input/output guardrail decision
  | "approval"    // human approval / denial
  | "rollback"    // workflow rolled back
  | "abandon";    // workflow abandoned

/**
 * Allowed final dispositions for any decision.
 */
export type DecisionDisposition = "allow" | "review" | "block" | "fail";

/**
 * Citation pointer — links a claim in the output to a source
 * chunk. Multiple citations per row are supported.
 */
export interface DecisionCitation {
  chunkId: string;
  documentId?: string;
  spanStart?: number;
  spanEnd?: number;
  score?: number;
}

/**
 * Optional explanation evidence per §48 — top factors,
 * counterfactual, model version. Free-shape because different
 * decision kinds carry different explanations.
 */
export interface DecisionExplanation {
  method?: string;             // "shap" | "lime" | "rule" | "prompt-template" | ...
  topFactors?: Array<{ name: string; weight: number }>;
  counterfactual?: string;     // human-readable "if X had been Y, decision would be Z"
  modelCardId?: string;        // link to ModelCard (iter 111)
  promptVersion?: string;
}

/**
 * Canonical decision audit row — schema-fingerprint locked by
 * the iter 110 drill. ADDING a field requires the drill update;
 * REMOVING a field is a breaking change that must rev a schema
 * version field (TODO when v2 is needed).
 */
export interface DecisionAuditRow {
  // ── identity ─────────────────────────────────────────────
  auditId: string;             // unique per row
  schemaVersion: 1;            // bump on breaking change
  timestamp: string;           // ISO-8601 UTC
  // ── correlation ──────────────────────────────────────────
  requestId: string;
  tenantId: string;
  userId: string;
  traceId?: string;
  sessionId?: string;
  workflowId?: string;
  stepId?: string;
  // ── decision ─────────────────────────────────────────────
  kind: DecisionKind;
  disposition: DecisionDisposition;
  actor: string;               // "agent" | "system" | userId for human actions
  // ── content hashes ───────────────────────────────────────
  inputHash?: string;          // SHA-256 of the request input
  outputHash?: string;         // SHA-256 of the produced output
  // ── execution ────────────────────────────────────────────
  modelId?: string;            // when kind === "llm" or "rag" via llm
  toolName?: string;           // when kind === "tool"
  durationMs?: number;
  // ── confidence + explanation ─────────────────────────────
  confidence?: number;         // 0..1 when the kind has one
  explanation?: DecisionExplanation;
  citations?: DecisionCitation[];
  // ── policy ───────────────────────────────────────────────
  policyVersion?: string;
  rulesApplied?: string[];
  // ── failure ──────────────────────────────────────────────
  errorName?: string;
  errorMessage?: string;
  retryCount?: number;
}

/**
 * Compute a deterministic SHA-256 hex digest of arbitrary
 * JSON-serializable input. Used for inputHash/outputHash so
 * forensic comparisons across runs detect drift.
 */
export function hashContent(value: unknown): string {
  return createHash("sha256")
    .update(JSON.stringify(value ?? null))
    .digest("hex");
}

/**
 * Writer that takes any input shape and produces a fully-populated
 * DecisionAuditRow with timestamp + auditId + schemaVersion auto-set.
 * Persists via the injectable EventSink.
 */
export class DecisionAuditWriter {
  private readonly sink: EventSink;
  constructor(sink?: EventSink) {
    this.sink = sink ?? new ConsoleEventSink();
  }

  /**
   * Build + emit a row. Required identity / correlation / decision
   * fields must be present; optional fields are passed through.
   */
  write(input: Omit<DecisionAuditRow, "auditId" | "schemaVersion" | "timestamp">): DecisionAuditRow {
    // Auto-fields come AFTER the spread so a malicious/buggy caller
    // (bypassing TS via @ts-expect-error or `as any`) can't override
    // them. Locks the trust boundary.
    const row: DecisionAuditRow = {
      ...input,
      auditId: randomUUID(),
      schemaVersion: 1,
      timestamp: new Date().toISOString(),
    };
    this.sink.emit({ type: "decision_audit", ...row });
    return row;
  }
}
