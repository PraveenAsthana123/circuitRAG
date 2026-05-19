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
// ✅ P0 LOCAL FIXED (2026-05-18): state + history persistence is now
//     behind WorkflowStatePersistence so production can provide an
//     atomic Postgres/outbox or durable-orchestrator adapter. The
//     default InMemoryWorkflowStatePersistence preserves local behavior.

import { WorkflowState } from "./types";

const DEFAULT_MAX_HISTORY = 50;

export type WorkflowPersistenceEventType =
  | "workflow_state_saved"
  | "workflow_state_rolled_back";

export interface WorkflowPersistenceEvent {
  readonly type: WorkflowPersistenceEventType;
  readonly workflowId: string;
  readonly tenantId: string;
  readonly status: WorkflowState["status"];
  readonly occurredAt: string;
}

export interface WorkflowStateCommit {
  readonly workflowId: string;
  readonly state: WorkflowState;
  readonly history: WorkflowState[];
  readonly event: WorkflowPersistenceEvent;
}

export interface WorkflowStatePersistence {
  loadState(workflowId: string): WorkflowState | undefined;
  loadHistory(workflowId: string): WorkflowState[];
  commit(change: WorkflowStateCommit): void;
  historyDepth(workflowId: string): number;
}

export class InMemoryWorkflowStatePersistence implements WorkflowStatePersistence {
  private readonly states = new Map<string, WorkflowState>();
  private readonly history = new Map<string, WorkflowState[]>();
  private readonly events: WorkflowPersistenceEvent[] = [];

  loadState(workflowId: string): WorkflowState | undefined {
    const state = this.states.get(workflowId);
    return state ? structuredClone(state) : undefined;
  }

  loadHistory(workflowId: string): WorkflowState[] {
    return structuredClone(this.history.get(workflowId) ?? []);
  }

  commit(change: WorkflowStateCommit): void {
    this.states.set(change.workflowId, structuredClone(change.state));
    this.history.set(change.workflowId, structuredClone(change.history));
    this.events.push(structuredClone(change.event));
  }

  historyDepth(workflowId: string): number {
    return (this.history.get(workflowId) ?? []).length;
  }

  /** Test/helper surface for local outbox contract checks. */
  outboxEvents(): WorkflowPersistenceEvent[] {
    return structuredClone(this.events);
  }
}

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
  private readonly persistence: WorkflowStatePersistence;

  constructor(
    private readonly maxHistoryPerWorkflow: number = DEFAULT_MAX_HISTORY,
    persistence?: WorkflowStatePersistence,
  ) {
    if (maxHistoryPerWorkflow < 1) {
      throw new Error("maxHistoryPerWorkflow must be >= 1");
    }
    this.persistence = persistence ?? new InMemoryWorkflowStatePersistence();
  }

  save(state: WorkflowState): void {
    const workflowId = state.context.workflowId;
    const old = this.persistence.loadState(workflowId);
    const history = this.persistence.loadHistory(workflowId);

    if (old) {
      // Sanity check: same workflowId must keep its original tenant.
      if (old.context.tenantId !== state.context.tenantId) {
        throw new WorkflowAccessDeniedError(
          workflowId,
          state.context.tenantId,
        );
      }
      history.push(structuredClone(old));
      while (history.length > this.maxHistoryPerWorkflow) {
        history.shift();
      }
    }

    state.updatedAt = new Date().toISOString();
    const persisted = structuredClone(state);
    this.persistence.commit({
      workflowId,
      state: persisted,
      history,
      event: {
        type: "workflow_state_saved",
        workflowId,
        tenantId: persisted.context.tenantId,
        status: persisted.status,
        occurredAt: persisted.updatedAt,
      },
    });
  }

  get(workflowId: string, callerTenantId: string): WorkflowState {
    const state = this.persistence.loadState(workflowId);
    if (!state) throw new WorkflowNotFoundError(workflowId);
    if (state.context.tenantId !== callerTenantId) {
      throw new WorkflowAccessDeniedError(workflowId, callerTenantId);
    }
    return structuredClone(state);
  }

  rollback(workflowId: string, callerTenantId: string): WorkflowState {
    // Authorize first — tenant of the current state must match caller.
    const current = this.persistence.loadState(workflowId);
    if (!current) {
      throw new WorkflowNotFoundError(workflowId);
    }
    if (current.context.tenantId !== callerTenantId) {
      throw new WorkflowAccessDeniedError(workflowId, callerTenantId);
    }

    const versions = this.persistence.loadHistory(workflowId);
    const previous = versions.pop();
    if (!previous) {
      throw new Error("No workflow history available for rollback");
    }

    this.persistence.commit({
      workflowId,
      state: structuredClone(previous),
      history: versions,
      event: {
        type: "workflow_state_rolled_back",
        workflowId,
        tenantId: previous.context.tenantId,
        status: previous.status,
        occurredAt: new Date().toISOString(),
      },
    });

    return previous;
  }

  /** Test helper — returns the history depth for a workflowId. */
  historyDepth(workflowId: string): number {
    return this.persistence.historyDepth(workflowId);
  }
}
