import { WorkflowState } from "./types";

export class WorkflowStateStore {
  private readonly states = new Map<string, WorkflowState>();
  private readonly history = new Map<string, WorkflowState[]>();

  save(state: WorkflowState): void {
    const old = this.states.get(state.context.workflowId);

    if (old) {
      const versions = this.history.get(state.context.workflowId) ?? [];
      versions.push(structuredClone(old));
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
}
