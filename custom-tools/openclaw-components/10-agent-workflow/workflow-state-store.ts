// ✅ P0 FIXED (2026-05-17): get() and rollback() now require a
//     tenantId argument and refuse to return data for a different
//     tenant's workflow. Pre-fix: any caller with a workflowId could
//     read/rollback ANY tenant's workflow.
//
//     Mismatched-tenant requests throw WorkflowAccessDeniedError
//     (NOT NotFound) so the caller is told they cannot access vs.
//     the data does not exist. This trades one info leak (existence
//     of a workflowId across tenants) for accountability — callers
//     SHOULD be passing their own tenant_id from the auth context;
//     if they aren't, that's a bug worth surfacing.
//
//     save() carries tenantId on every state.context, so no separate
//     argument is needed there.
//
// ✅ P1 FIXED (2026-05-17, prior iteration): history is capped.
//     See git history for details.
//
//     Real durability still requires Postgres + outbox per
//     CLAUDE.md §47.7 — see GAPS.md Component 10 "in-memory only".

import { WorkflowState } from "./types";

const DEFAULT_MAX_HISTORY = 50;

export class WorkflowNotFoundError extends Error {
  constructor(workflowId: string) {
    super(`Workflow not found: ${workflowId}`);
    this.name = "WorkflowNotFoundError";
  }
}

export class WorkflowAccessDeniedError extends Error {
  constructor(workflowId: string, callerTenantId: string) {
    super(
      `Tenant ${callerTenantId} cannot access workflow ${workflowId} ` +
      `(owned by a different tenant)`
    );
    this.name = "WorkflowAccessDeniedError";
  }
}

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
      // Sanity check: same workflowId must keep its original tenant.
      if (old.context.tenantId !== state.context.tenantId) {
        throw new WorkflowAccessDeniedError(
          state.context.workflowId,
          state.context.tenantId,
        );
      }
      const versions = this.history.get(state.context.workflowId) ?? [];
      versions.push(structuredClone(old));
      while (versions.length > this.maxHistoryPerWorkflow) {
        versions.shift();
      }
      this.history.set(state.context.workflowId, versions);
    }

    state.updatedAt = new Date().toISOString();
    this.states.set(state.context.workflowId, structuredClone(state));
  }

  get(workflowId: string, callerTenantId: string): WorkflowState {
    const state = this.states.get(workflowId);
    if (!state) throw new WorkflowNotFoundError(workflowId);
    if (state.context.tenantId !== callerTenantId) {
      throw new WorkflowAccessDeniedError(workflowId, callerTenantId);
    }
    return structuredClone(state);
  }

  rollback(workflowId: string, callerTenantId: string): WorkflowState {
    // Authorize first — tenant of the current state must match caller.
    const current = this.states.get(workflowId);
    if (!current) {
      throw new WorkflowNotFoundError(workflowId);
    }
    if (current.context.tenantId !== callerTenantId) {
      throw new WorkflowAccessDeniedError(workflowId, callerTenantId);
    }

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
