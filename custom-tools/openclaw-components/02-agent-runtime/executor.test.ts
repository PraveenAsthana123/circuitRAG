// Negative drills for Iter 48 (2026-05-17): Executor real routing.

import { describe, it, expect } from "vitest";
import { Executor } from "./executor";
import { ModelClient } from "./model-client";
import { ToolDispatcher } from "../03-tooling/tool-dispatcher";
import { ToolRegistry } from "../03-tooling/tool-registry";
import { Logger } from "../03-tooling/logger";
import { Telemetry } from "../03-tooling/telemetry";
import { ResponsibleAIGuard } from "../03-tooling/responsible-ai-guard";
import { ExplainabilityRecorder } from "../03-tooling/explainability-recorder";
import { LLMRouter } from "../08-llm-router/llm-router";
import { ModelRegistry } from "../08-llm-router/model-registry";
import { RoutingPolicy } from "../08-llm-router/routing-policy";
import { SafetyGate } from "../08-llm-router/safety-gate";
import { EchoLLMClient } from "../08-llm-router/llm-client";
import { AgentPlan, AgentTask } from "./types";

function buildTooling() {
  const reg = new ToolRegistry();
  reg.register({
    name: "calculator",
    description: "n/a",
    riskLevel: "low",
    allowedRoles: ["user"],
    async execute(input) { return { result: input.expression }; },
  });
  return new ToolDispatcher(
    reg, new Logger(), new Telemetry(),
    new ResponsibleAIGuard(), new ExplainabilityRecorder(),
  );
}

function buildModelClient() {
  const router = new LLMRouter(
    new ModelRegistry([{
      modelId: "echo", provider: "ollama", supportedTasks: ["chat"],
      costPer1kTokensUsd: 0, maxContextTokens: 1024,
      priority: 1, enabled: true,
    }]),
    new RoutingPolicy(),
    new SafetyGate(),
    new EchoLLMClient(),
  );
  return new ModelClient(router);
}

const TASK: AgentTask = {
  sessionId: "s", userId: "u", userInput: "what's 2+2?",
  tenantId: "tenant-A", requestId: "req-1",
  traceId: "tr-1", roles: ["user"],
};

describe("Executor — real per-step routing (P0)", () => {
  it("BACKDOOR CHECK: 'think' step actually calls modelClient", async () => {
    const e = new Executor({ modelClient: buildModelClient() });
    const plan: AgentPlan = {
      taskId: "t",
      steps: [{ stepId: "s1", action: "think", description: "ponder" }],
    };
    const [result] = await e.executeWithTask(plan, TASK);
    expect(result.success).toBe(true);
    // EchoLLMClient prefixes outputs with [ECHO STUB - NOT PRODUCTION].
    expect((result.output as any).text).toContain("[ECHO STUB - NOT PRODUCTION]");
  });

  it("BACKDOOR CHECK: 'tool' step actually calls toolDispatcher", async () => {
    const e = new Executor({ toolDispatcher: buildTooling() });
    const plan: AgentPlan = {
      taskId: "t",
      steps: [{
        stepId: "s1", action: "tool", description: "calc",
        toolName: "calculator", toolInput: { expression: "2+2" },
      }],
    };
    const [result] = await e.executeWithTask(plan, TASK);
    expect(result.success).toBe(true);
    expect((result.output as any).result).toBe("2+2");
  });

  it("'respond' step returns the description as the reply", async () => {
    const e = new Executor();
    const plan: AgentPlan = {
      taskId: "t",
      steps: [{ stepId: "s1", action: "respond", description: "Hi!" }],
    };
    const [result] = await e.executeWithTask(plan, TASK);
    expect(result.success).toBe(true);
    expect((result.output as any).reply).toBe("Hi!");
  });

  it("'tool' step without dispatcher → error (no silent success)", async () => {
    const e = new Executor();
    const plan: AgentPlan = {
      taskId: "t",
      steps: [{
        stepId: "s1", action: "tool", description: "calc",
        toolName: "calculator",
      }],
    };
    const [result] = await e.executeWithTask(plan, TASK);
    expect(result.success).toBe(false);
    expect(result.error).toContain("no toolDispatcher wired");
  });

  it("'think' step without modelClient → error", async () => {
    const e = new Executor();
    const plan: AgentPlan = {
      taskId: "t",
      steps: [{ stepId: "s1", action: "think", description: "ponder" }],
    };
    const [result] = await e.executeWithTask(plan, TASK);
    expect(result.success).toBe(false);
    expect(result.error).toContain("no modelClient wired");
  });

  it("first failure stops the chain (no further steps run)", async () => {
    const e = new Executor();
    const plan: AgentPlan = {
      taskId: "t",
      steps: [
        { stepId: "s1", action: "think", description: "x" },  // fails (no model)
        { stepId: "s2", action: "respond", description: "should not run" },
      ],
    };
    const results = await e.executeWithTask(plan, TASK);
    expect(results.length).toBe(1);
    expect(results[0].success).toBe(false);
  });

  it("step-budget cap rejects oversized plans", async () => {
    const e = new Executor({ maxSteps: 2 });
    const plan: AgentPlan = {
      taskId: "t",
      steps: Array(5).fill(null).map((_, i) => ({
        stepId: `s${i}`, action: "respond", description: `s${i}`,
      })),
    };
    const results = await e.executeWithTask(plan, TASK);
    // Two real results + one budget-exceeded marker.
    expect(results.length).toBe(3);
    expect(results[2].error).toContain("Plan has 5 steps; budget is 2");
  });

  it("'tool' step without tenantId/requestId → error (no silent context loss)", async () => {
    const e = new Executor({ toolDispatcher: buildTooling() });
    const plan: AgentPlan = {
      taskId: "t",
      steps: [{
        stepId: "s1", action: "tool", description: "calc",
        toolName: "calculator",
      }],
    };
    const [result] = await e.executeWithTask(plan, {
      sessionId: "s", userId: "u", userInput: "x",
      // intentionally no tenantId/requestId
    });
    expect(result.success).toBe(false);
    expect(result.error).toContain("tenantId");
  });

  it("constructor rejects maxSteps < 1", () => {
    expect(() => new Executor({ maxSteps: 0 })).toThrow();
  });
});
