// Iter 112 (2026-05-18): legal workflow-status transition graph +
// validator. The existing WorkflowStatus enum (types.ts) had no
// transition-validity check, so a refactor could silently allow
// nonsensical state moves like "completed" → "executing" or
// "rolled_back" → "planning".
//
// Per Agentic Plan §"Recovery": "Add recovery states: pending,
// running, completed, failed, waiting_approval, replanned,
// rolled_back. Replanner must keep original error metadata.
// Rollback must verify actual compensation."
//
// Existing WorkflowStatus already covers all those states (with
// different names: created=pending, executing=running). This iter
// adds the transition GRAPH + the validator so a future iter can
// wire the engine to assertLegalTransition() and fail-closed on
// any unexpected move.

import { WorkflowStatus } from "./types";

/**
 * Static graph: from-status → list of legal to-statuses.
 *
 * Reading this:
 *   created → planning | failed
 *   planning → awaiting_approval | executing | failed
 *   awaiting_approval → executing | failed | rolled_back
 *   executing → executing (continued) | replanning | completed | failed | awaiting_approval
 *   replanning → executing | failed
 *   completed → rolled_back (post-hoc compensation only)
 *   failed → rolled_back | replanning (operator-driven recovery)
 *   rolled_back → (terminal — no further transitions)
 *
 * Identity transitions (X → X) are allowed where the engine
 * stays in the same status across operations (e.g., executing
 * step N then executing step N+1 — same status).
 */
export const LEGAL_TRANSITIONS: Readonly<Record<WorkflowStatus, readonly WorkflowStatus[]>> = {
  created: ["planning", "failed"],
  planning: ["awaiting_approval", "executing", "failed"],
  awaiting_approval: ["executing", "failed", "rolled_back"],
  executing: ["executing", "replanning", "completed", "failed", "awaiting_approval"],
  replanning: ["executing", "failed"],
  completed: ["rolled_back"],
  failed: ["rolled_back", "replanning"],
  rolled_back: [],  // terminal
} as const;

/**
 * Thrown by assertLegalTransition. Carries from/to so callers can
 * branch on the violation without re-parsing the message.
 */
export class WorkflowIllegalTransitionError extends Error {
  public readonly from: WorkflowStatus;
  public readonly to: WorkflowStatus;
  constructor(from: WorkflowStatus, to: WorkflowStatus) {
    super(
      `Illegal workflow status transition: ${from} → ${to}. ` +
      `Legal next states from "${from}": [${LEGAL_TRANSITIONS[from].join(", ") || "(terminal)"}]`,
    );
    this.name = "WorkflowIllegalTransitionError";
    this.from = from;
    this.to = to;
  }
}

/**
 * Pure check — returns true iff `to` is in the legal set for `from`.
 * Identity transitions (X → X) are legal only where the graph
 * explicitly lists X in its own from-list (e.g., executing).
 */
export function isLegalTransition(from: WorkflowStatus, to: WorkflowStatus): boolean {
  return LEGAL_TRANSITIONS[from].includes(to);
}

/**
 * Throws WorkflowIllegalTransitionError if the transition isn't
 * in the graph. Use at the engine's status-write sites once a
 * future iter is ready to enforce.
 */
export function assertLegalTransition(from: WorkflowStatus, to: WorkflowStatus): void {
  if (!isLegalTransition(from, to)) {
    throw new WorkflowIllegalTransitionError(from, to);
  }
}

/**
 * True iff the workflow has reached a terminal status (no further
 * transitions are legal). Useful for store/reaper logic.
 */
export function isTerminal(status: WorkflowStatus): boolean {
  return LEGAL_TRANSITIONS[status].length === 0;
}

/**
 * Returns the full set of statuses reachable from `start` via 1+
 * legal transitions. Used by static analysis / docs to verify
 * every status is reachable from "created".
 */
export function reachableStatuses(start: WorkflowStatus): Set<WorkflowStatus> {
  const visited = new Set<WorkflowStatus>();
  const queue: WorkflowStatus[] = [start];
  while (queue.length > 0) {
    const cur = queue.shift()!;
    for (const next of LEGAL_TRANSITIONS[cur]) {
      if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  return visited;
}
