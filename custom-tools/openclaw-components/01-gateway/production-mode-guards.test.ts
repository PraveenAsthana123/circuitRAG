// Negative drills for M1.2 (2026-05-18): production-mode guards
// across the fleet. Catalogs every (component, stub-adapter,
// production-config) combination that MUST fail-closed at
// construction time. The drill is the authoritative list of
// "things production can never silently use".
//
// Lives in 01-gateway/ as a cross-component validator drill —
// the same pattern any service entry-point would run at startup.

import { describe, it, expect } from "vitest";

// Workflow engine — requires real toolDispatcher in production.
import {
  AgentWorkflowEngine,
} from "../10-agent-workflow/agent-workflow-engine";
import { WorkflowPlanner } from "../10-agent-workflow/planner";
import { Replanner } from "../10-agent-workflow/replanner";
import { ToolSelector } from "../10-agent-workflow/tool-selector";
import { HumanApprovalGate } from "../10-agent-workflow/human-approval";
import { WorkflowStateStore } from "../10-agent-workflow/workflow-state-store";
import { ToolDispatcher } from "../03-tooling/tool-dispatcher";

// LLM router — rejects EchoLLMClient in production.
import { LLMRouter } from "../08-llm-router/llm-router";
import { ModelRegistry } from "../08-llm-router/model-registry";
import { RoutingPolicy } from "../08-llm-router/routing-policy";
import { SafetyGate } from "../08-llm-router/safety-gate";
import { EchoLLMClient, LLMClient } from "../08-llm-router/llm-client";
import { LLMRequest, LLMResponse, ModelConfig } from "../08-llm-router/types";

class FakeRealLLMClient extends LLMClient {
  // Production-grade flag — passes the guard.
  async complete(_req: LLMRequest, model: ModelConfig): Promise<LLMResponse> {
    return {
      modelId: model.modelId,
      provider: "openai",
      output: "real",
      latencyMs: 1,
      estimatedCostUsd: 0,
      explanation: "real",
    };
  }
}

class FakeDispatcher {
  async dispatch() { return { success: true, output: null, durationMs: 1 }; }
}

describe("M1.2 — production-mode guards (P0)", () => {
  it("BACKDOOR: workflow engine refuses construction in production WITHOUT toolDispatcher", () => {
    expect(() => new AgentWorkflowEngine(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), new WorkflowStateStore(),
      { requireRealToolDispatcher: true },  // no dispatcher
    )).toThrow();
  });

  it("BACKDOOR: workflow engine ALLOWS construction in production WHEN toolDispatcher wired", () => {
    expect(() => new AgentWorkflowEngine(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), new WorkflowStateStore(),
      {
        requireRealToolDispatcher: true,
        toolDispatcher: new FakeDispatcher() as unknown as ToolDispatcher,
      },
    )).not.toThrow();
  });

  it("BACKDOOR: workflow engine in DEV mode allows construction without dispatcher (backcompat)", () => {
    expect(() => new AgentWorkflowEngine(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), new WorkflowStateStore(),
      {},  // no requireRealToolDispatcher
    )).not.toThrow();
  });

  it("BACKDOOR: LLMRouter refuses EchoLLMClient in production mode", () => {
    expect(() => new LLMRouter(
      new ModelRegistry([]),
      new RoutingPolicy(),
      new SafetyGate(),
      new EchoLLMClient(),
      undefined,
      { productionMode: true },
    )).toThrow(/stub/);
  });

  it("BACKDOOR: LLMRouter ALLOWS EchoLLMClient in DEV mode (backcompat)", () => {
    expect(() => new LLMRouter(
      new ModelRegistry([]),
      new RoutingPolicy(),
      new SafetyGate(),
      new EchoLLMClient(),
      undefined,
      {},  // no productionMode
    )).not.toThrow();
  });

  it("BACKDOOR: LLMRouter ALLOWS real LLMClient subclass in production", () => {
    expect(() => new LLMRouter(
      new ModelRegistry([]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FakeRealLLMClient(),
      undefined,
      { productionMode: true },
    )).not.toThrow();
  });

  it("EchoLLMClient.isProductionStub === true (the boolean the guard reads)", () => {
    expect(new EchoLLMClient().isProductionStub).toBe(true);
  });

  it("real subclass inherits isProductionStub === false (the boolean the guard reads)", () => {
    expect(new FakeRealLLMClient().isProductionStub).toBe(false);
  });

  it("production guards rejection error message identifies the stub class (audit visibility)", () => {
    try {
      new LLMRouter(
        new ModelRegistry([]),
        new RoutingPolicy(),
        new SafetyGate(),
        new EchoLLMClient(),
        undefined,
        { productionMode: true },
      );
      throw new Error("expected throw");
    } catch (e) {
      const msg = (e as Error).message;
      expect(msg.toLowerCase()).toContain("stub");
    }
  });

  it("composite production startup: ALL guards fire together (catalog test)", () => {
    // The canonical "ProductionConfig validator" pattern — a service
    // entry point's startup should compose every guard and fail
    // loudly with the first violation. This drill simulates that.
    const violations: string[] = [];

    // Workflow guard
    try {
      new AgentWorkflowEngine(
        new WorkflowPlanner(), new Replanner(), new ToolSelector(),
        new HumanApprovalGate(), new WorkflowStateStore(),
        { requireRealToolDispatcher: true },
      );
    } catch { violations.push("workflow:no-dispatcher"); }

    // LLM router guard
    try {
      new LLMRouter(
        new ModelRegistry([]),
        new RoutingPolicy(),
        new SafetyGate(),
        new EchoLLMClient(),
        undefined,
        { productionMode: true },
      );
    } catch { violations.push("llm:echo-stub"); }

    expect(violations).toEqual(["workflow:no-dispatcher", "llm:echo-stub"]);
  });
});
