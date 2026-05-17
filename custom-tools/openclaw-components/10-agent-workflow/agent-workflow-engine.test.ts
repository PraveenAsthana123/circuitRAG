import { describe, it, expect } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";

describe("AgentWorkflowEngine", () => {
  it("starts and runs a workflow step", async () => {
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(),
      new Replanner(),
      new ToolSelector(),
      new HumanApprovalGate(),
      new WorkflowStateStore()
    );

    const workflow = engine.start(
      {
        workflowId: "wf-1",
        requestId: "req-1",
        tenantId: "tenant-1",
        userId: "user-1",
        traceId: "trace-1",
      },
      "Generate RAG answer"
    );

    const next = await engine.runNext(workflow.context.workflowId, "tenant-1");

    expect(next.currentStepIndex).toBe(1);
  });
});
