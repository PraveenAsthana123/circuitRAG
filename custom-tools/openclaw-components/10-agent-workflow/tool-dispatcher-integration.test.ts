import { describe, it, expect } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { ToolDispatcher } from "../03-tooling/tool-dispatcher";
import { ToolRegistry } from "../03-tooling/tool-registry";
import { Logger } from "../03-tooling/logger";
import { Telemetry } from "../03-tooling/telemetry";
import { ResponsibleAIGuard } from "../03-tooling/responsible-ai-guard";
import { ExplainabilityRecorder } from "../03-tooling/explainability-recorder";
import { ToolDefinition } from "../03-tooling/types";

function dispatcherWith(tool: ToolDefinition): ToolDispatcher {
  const registry = new ToolRegistry();
  registry.register(tool);
  return new ToolDispatcher(
    registry,
    new Logger(),
    new Telemetry(),
    new ResponsibleAIGuard(),
    new ExplainabilityRecorder(),
  );
}

function engine(store: WorkflowStateStore, dispatcher: ToolDispatcher): AgentWorkflowEngine {
  return new AgentWorkflowEngine(
    new WorkflowPlanner(),
    new Replanner(),
    new ToolSelector(),
    new HumanApprovalGate(),
    store,
    { toolDispatcher: dispatcher, requireRealToolDispatcher: true },
  );
}

describe("AgentWorkflowEngine -> ToolDispatcher integration", () => {
  it("dispatches the selected workflow tool and persists its output", async () => {
    const store = new WorkflowStateStore();
    const dispatcher = dispatcherWith({
      name: "default_agent_executor",
      description: "test executor",
      riskLevel: "low",
      allowedRoles: ["agent"],
      async execute(input, context) {
        return {
          ok: true,
          tenantId: context.tenantId,
          stepName: input.stepName,
          previousOutputs: input.previousOutputs,
        };
      },
    });
    const wfEngine = engine(store, dispatcher);

    const wf = wfEngine.start({
      workflowId: "wf-dispatch-1",
      requestId: "req-dispatch-1",
      tenantId: "tenant-1",
      userId: "user-1",
      traceId: "trace-1",
      roles: ["agent"],
    }, "do real work");

    const after = await wfEngine.runNext(wf.context.workflowId, "tenant-1");

    expect(after.steps[0].status).toBe("completed");
    expect(after.steps[0].output).toMatchObject({
      ok: true,
      tenantId: "tenant-1",
      stepName: "understand_goal",
      previousOutputs: {},
    });
  });

  it("fails closed in production mode when no ToolDispatcher is supplied", () => {
    expect(() => new AgentWorkflowEngine(
      new WorkflowPlanner(),
      new Replanner(),
      new ToolSelector(),
      new HumanApprovalGate(),
      new WorkflowStateStore(),
      { requireRealToolDispatcher: true },
    )).toThrow(/requires a real ToolDispatcher/);
  });

  it("turns dispatch failures into failed workflow steps and replans", async () => {
    const store = new WorkflowStateStore();
    const dispatcher = dispatcherWith({
      name: "default_agent_executor",
      description: "test executor",
      riskLevel: "low",
      allowedRoles: ["agent"],
      async execute() {
        throw new Error("backend unavailable");
      },
    });
    const wfEngine = engine(store, dispatcher);

    const wf = wfEngine.start({
      workflowId: "wf-dispatch-2",
      requestId: "req-dispatch-2",
      tenantId: "tenant-1",
      userId: "user-1",
      traceId: "trace-1",
      roles: ["agent"],
    }, "do real work");

    const after = await wfEngine.runNext(wf.context.workflowId, "tenant-1");

    expect(after.status).toBe("replanning");
    expect(after.steps[0].status).toBe("failed");
    expect(after.steps[0].lastError?.message).toBe("backend unavailable");
    expect(after.replanHistory?.[0].errorMessage).toBe("backend unavailable");
  });
});
