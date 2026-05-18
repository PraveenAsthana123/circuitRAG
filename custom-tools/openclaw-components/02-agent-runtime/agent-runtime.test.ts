// Negative drills for Iter 51 (2026-05-17): AgentRuntime threading
// task context through to Executor.executeWithTask.

import { describe, it, expect } from "vitest";
import { AgentRuntime } from "./agent-runtime";
import { Planner } from "./planner";
import { Executor } from "./executor";
import { AgentTask, AgentPlan } from "./types";

const TASK: AgentTask = {
  sessionId: "s", userId: "u", userInput: "say hi",
  tenantId: "tenant-A", requestId: "req-1", traceId: "tr-1",
};

describe("AgentRuntime (Iter 51)", () => {
  it("returns AgentRuntimeResult shape (not legacy string)", async () => {
    const planner = new Planner();
    const executor = new Executor();  // no deps wired
    const rt = new AgentRuntime(planner, executor);
    // Default planner emits 'think' + 'respond'; without modelClient
    // the 'think' step errors → ok=false, failedAt populated.
    const result = await rt.run(TASK);
    expect(result.ok).toBe(false);
    expect(result.failedAt).toBeDefined();
    expect(result.failedAt!.error).toContain("no modelClient wired");
    expect(result.steps.length).toBeGreaterThan(0);
  });

  it("BACKDOOR CHECK: task context reaches executor", async () => {
    // We rely on Executor's tenantId/requestId checks. If runtime
    // dropped the context (pre-fix execute(plan) path), the error
    // would be "requires task.tenantId" instead of "no modelClient
    // wired". So this test pins that the context flows through.
    const planner = new Planner();
    const executor = new Executor();  // no model client
    const rt = new AgentRuntime(planner, executor);
    const result = await rt.run({
      sessionId: "s", userId: "u", userInput: "x",
      tenantId: "tenant-A", requestId: "req-1",
    });
    expect(result.ok).toBe(false);
    // 'no modelClient wired' (not 'tenantId/requestId missing')
    // confirms context flowed.
    expect(result.failedAt!.error).toContain("no modelClient wired");
  });

  it("happy path returns final step output", async () => {
    // Plan with only a respond step; executor doesn't need deps.
    const planner = {
      createPlan(t: AgentTask): AgentPlan {
        return {
          taskId: "t1",
          steps: [{
            stepId: "s1", action: "respond",
            description: `OK: ${t.userInput}`,
          }],
        };
      },
    } as Planner;
    const rt = new AgentRuntime(planner, new Executor());
    const r = await rt.run(TASK);
    expect(r.ok).toBe(true);
    expect((r.output as any).reply).toContain("say hi");
  });

  it("first failure stops + reports stepId", async () => {
    const planner = {
      createPlan(): AgentPlan {
        return {
          taskId: "t",
          steps: [
            { stepId: "s1", action: "think", description: "x" },   // will fail
            { stepId: "s2", action: "respond", description: "n/a" }, // should not run
          ],
        };
      },
    } as Planner;
    const rt = new AgentRuntime(planner, new Executor());  // no model
    const r = await rt.run(TASK);
    expect(r.ok).toBe(false);
    expect(r.failedAt?.stepId).toBe("s1");
    expect(r.steps.length).toBe(1);  // s2 didn't run
  });
});
