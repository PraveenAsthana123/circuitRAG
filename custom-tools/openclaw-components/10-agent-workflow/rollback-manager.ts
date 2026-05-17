// ✅ P1 FIXED (2026-05-17): rollback() now PERSISTS the rolled-back
//     status to the store before returning. The pre-fix version
//     returned `{...restored, status: "rolled_back"}` but never called
//     store.save(), so the store still held `restored` with its
//     original status. Caller's view and store's view disagreed —
//     classic compound bug that demos passed but production reads
//     would catch.
//
//     Negative drill: rollback-manager.test.ts

import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowState } from "./types";

export class RollbackManager {
  constructor(private readonly store: WorkflowStateStore) {}

  rollback(workflowId: string, reason: string): WorkflowState {
    const restored = this.store.rollback(workflowId);

    const rolledBack: WorkflowState = {
      ...restored,
      status: "rolled_back",
    };

    // Persist the rolled-back status so subsequent store.get() agrees
    // with what we return. Pre-fix bug: this save() was missing.
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
