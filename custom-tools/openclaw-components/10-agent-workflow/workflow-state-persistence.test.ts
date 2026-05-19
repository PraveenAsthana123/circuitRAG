import { describe, expect, it } from "vitest";
import {
  InMemoryWorkflowStatePersistence,
  WorkflowPersistenceEvent,
  WorkflowStateCommit,
  WorkflowStatePersistence,
  WorkflowStateStore,
} from "./workflow-state-store";
import { WorkflowState } from "./types";

function newState(workflowId: string, status: WorkflowState["status"] = "created"): WorkflowState {
  return {
    context: {
      workflowId,
      requestId: "r",
      tenantId: "t",
      userId: "u",
      traceId: "tr",
    },
    status,
    userGoal: "g",
    steps: [],
    currentStepIndex: 0,
    createdAt: "2026-05-18T00:00:00.000Z",
    updatedAt: "2026-05-18T00:00:00.000Z",
  };
}

class SpyWorkflowPersistence implements WorkflowStatePersistence {
  readonly commits: WorkflowStateCommit[] = [];
  readonly events: WorkflowPersistenceEvent[] = [];
  private readonly delegate = new InMemoryWorkflowStatePersistence();

  loadState(workflowId: string): WorkflowState | undefined {
    return this.delegate.loadState(workflowId);
  }

  loadHistory(workflowId: string): WorkflowState[] {
    return this.delegate.loadHistory(workflowId);
  }

  commit(change: WorkflowStateCommit): void {
    this.commits.push(structuredClone(change));
    this.events.push(structuredClone(change.event));
    this.delegate.commit(change);
  }

  historyDepth(workflowId: string): number {
    return this.delegate.historyDepth(workflowId);
  }
}

describe("WorkflowStateStore persistence seam", () => {
  it("uses injected persistence for state, history, and outbox-style events", () => {
    const persistence = new SpyWorkflowPersistence();
    const store = new WorkflowStateStore(3, persistence);

    store.save(newState("wf-persist", "created"));
    store.save(newState("wf-persist", "executing"));

    expect(persistence.commits).toHaveLength(2);
    expect(persistence.historyDepth("wf-persist")).toBe(1);
    expect(persistence.events.map((event) => event.type)).toEqual([
      "workflow_state_saved",
      "workflow_state_saved",
    ]);
    expect(store.get("wf-persist", "t").status).toBe("executing");
  });

  it("can reuse the same persistence instance across store construction", () => {
    const persistence = new InMemoryWorkflowStatePersistence();
    const firstStore = new WorkflowStateStore(3, persistence);
    firstStore.save(newState("wf-restart", "created"));
    firstStore.save(newState("wf-restart", "executing"));

    const restartedStore = new WorkflowStateStore(3, persistence);
    expect(restartedStore.get("wf-restart", "t").status).toBe("executing");
    expect(restartedStore.historyDepth("wf-restart")).toBe(1);
  });

  it("commits rollback state and emits a rollback event through persistence", () => {
    const persistence = new SpyWorkflowPersistence();
    const store = new WorkflowStateStore(3, persistence);
    store.save(newState("wf-rollback", "executing"));
    store.save(newState("wf-rollback", "failed"));

    const restored = store.rollback("wf-rollback", "t");

    expect(restored.status).toBe("executing");
    expect(store.get("wf-rollback", "t").status).toBe("executing");
    expect(persistence.events.at(-1)?.type).toBe("workflow_state_rolled_back");
    expect(persistence.historyDepth("wf-rollback")).toBe(0);
  });

  it("default in-memory persistence keeps defensive copies", () => {
    const persistence = new InMemoryWorkflowStatePersistence();
    const store = new WorkflowStateStore(3, persistence);
    const original = newState("wf-copy", "created");
    store.save(original);

    original.status = "failed";
    const read = store.get("wf-copy", "t");
    read.status = "rolled_back";

    expect(store.get("wf-copy", "t").status).toBe("created");
    expect(persistence.outboxEvents()).toHaveLength(1);
  });
});
