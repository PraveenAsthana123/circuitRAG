// ✅ P1 FIXED (2026-05-17): rollback() now PERSISTS the rolled-back
//     status to the store before returning.
// ✅ P0 FIXED (Iter 8, 2026-05-17): callerTenantId required; the
//     wrapped store enforces tenant isolation and throws
//     WorkflowAccessDeniedError on mismatch.
//
//     Negative drill: rollback-manager.test.ts + tenant-isolation.test.ts

import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowState } from "./types";

export class RollbackManager {
  constructor(private readonly store: WorkflowStateStore) {}

  rollback(workflowId: string, callerTenantId: string, reason: string): WorkflowState {
    // store.rollback enforces tenant; throws on mismatch.
    const restored = this.store.rollback(workflowId, callerTenantId);

    const rolledBack: WorkflowState = {
      ...restored,
      status: "rolled_back",
    };

    this.store.save(rolledBack);

    console.warn(JSON.stringify({
      type: "workflow_rollback",
      workflowId,
      reason,
      restoredStatus: restored.status,
      newStatus: "rolled_back",
      timestamp: new Date().toISOString(),
    }));

    return rolledBack;
  }
}
