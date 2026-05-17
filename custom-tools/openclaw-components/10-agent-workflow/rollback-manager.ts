import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowState } from "./types";

export class RollbackManager {
  constructor(private readonly store: WorkflowStateStore) {}

  rollback(workflowId: string, reason: string): WorkflowState {
    const restored = this.store.rollback(workflowId);

    console.warn(JSON.stringify({
      type: "workflow_rollback",
      workflowId,
      reason,
      restoredStatus: restored.status,
      timestamp: new Date().toISOString(),
    }));

    return {
      ...restored,
      status: "rolled_back",
    };
  }
}
