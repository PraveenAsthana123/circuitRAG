// ✅ P1 FIXED (2026-05-17): history is now capped to prevent memory
//     leaks on long-running workflows. Each workflowId retains at
//     most MAX_HISTORY_PER_WORKFLOW versions; older versions are
//     pruned FIFO. Cap defaults to 50 but can be overridden via the
//     constructor.
//
//     This is a code-only mitigation. Real durability still requires
//     Postgres + outbox per CLAUDE.md §47.7 — see GAPS.md Component 10
//     "in-memory only" row.

import { WorkflowState } from "./types";

const DEFAULT_MAX_HISTORY = 50;

export class WorkflowStateStore {
  private readonly states = new Map<string, WorkflowState>();
  private readonly history = new Map<string, WorkflowState[]>();

  constructor(
    private readonly maxHistoryPerWorkflow: number = DEFAULT_MAX_HISTORY,
  ) {
    if (maxHistoryPerWorkflow < 1) {
      throw new Error("maxHistoryPerWorkflow must be >= 1");
    }
  }

  save(state: WorkflowState): void {
    const old = this.states.get(state.context.workflowId);

    if (old) {
      const versions = this.history.get(state.context.workflowId) ?? [];
      versions.push(structuredClone(old));
      // Cap history FIFO to prevent unbounded growth.
      while (versions.length > this.maxHistoryPerWorkflow) {
        versions.shift();
      }
      this.history.set(state.context.workflowId, versions);
    }

    state.updatedAt = new Date().toISOString();
    this.states.set(state.context.workflowId, structuredClone(state));
  }

  get(workflowId: string): WorkflowState {
    const state = this.states.get(workflowId);
    if (!state) throw new Error(`Workflow not found: ${workflowId}`);
    return structuredClone(state);
  }

  rollback(workflowId: string): WorkflowState {
    const versions = this.history.get(workflowId) ?? [];
    const previous = versions.pop();

    if (!previous) {
      throw new Error("No workflow history available for rollback");
    }

    this.states.set(workflowId, structuredClone(previous));
    this.history.set(workflowId, versions);

    return previous;
  }

  /** Test helper — returns the history depth for a workflowId. */
  historyDepth(workflowId: string): number {
    return (this.history.get(workflowId) ?? []).length;
  }
}
