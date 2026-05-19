// ✅ P1 FIXED (2026-05-17): rollback() now PERSISTS the rolled-back
//     status to the store before returning.
// ✅ P0 FIXED (Iter 8, 2026-05-17): callerTenantId required; the
//     wrapped store enforces tenant isolation and throws
//     WorkflowAccessDeniedError on mismatch.
//
//     Negative drill: rollback-manager.test.ts + tenant-isolation.test.ts

import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowState } from "./types";
import {
  EventSink,
  ConsoleWarnEventSink,
} from "../06-observability/sinks";

export class RollbackManager {
  private readonly sink: EventSink;
  // Iter 103 (2026-05-18): pluggable sink for workflow_rollback
  // emissions. Default ConsoleWarnEventSink preserves iter 95's
  // console.warn-spy contract.
  constructor(
    private readonly store: WorkflowStateStore,
    sink?: EventSink,
  ) {
    this.sink = sink ?? new ConsoleWarnEventSink();
  }

  rollback(workflowId: string, callerTenantId: string, reason: string): WorkflowState {
    // store.rollback enforces tenant; throws on mismatch.
    const restored = this.store.rollback(workflowId, callerTenantId);

    const rolledBack: WorkflowState = {
      ...restored,
      status: "rolled_back",
    };

    this.store.save(rolledBack);

    this.sink.emit({
      type: "workflow_rollback",
      workflowId,
      reason,
      restoredStatus: restored.status,
      newStatus: "rolled_back",
      timestamp: new Date().toISOString(),
    });

    return rolledBack;
  }
}
