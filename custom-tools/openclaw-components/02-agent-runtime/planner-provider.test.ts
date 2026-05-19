import { describe, expect, it } from "vitest";
import { InvalidPlanError, Planner } from "./planner";
import { AgentTask } from "./types";

const TASK: AgentTask = {
  sessionId: "s",
  userId: "u",
  userInput: "calculate 2+2",
  tenantId: "t",
  requestId: "r",
};

describe("Planner provider and schema validation", () => {
  it("uses injected provider output instead of the default hardcoded two-step plan", () => {
    const planner = new Planner({
      createPlan(task) {
        return {
          taskId: "provider-plan",
          steps: [
            {
              stepId: "tool-step",
              action: "tool",
              description: `Calculate for ${task.userInput}`,
              toolName: "calculator",
              toolInput: { expression: "2+2" },
            },
            {
              stepId: "respond-step",
              action: "respond",
              description: "Return the calculator result",
            },
          ],
        };
      },
    });

    const plan = planner.createPlan(TASK);

    expect(plan.taskId).toBe("provider-plan");
    expect(plan.steps.map((step) => step.action)).toEqual(["tool", "respond"]);
    expect(plan.steps[0].toolName).toBe("calculator");
  });

  it("BACKDOOR: rejects provider plans with an unsupported action", () => {
    const planner = new Planner({
      createPlan() {
        return {
          taskId: "bad",
          steps: [{ stepId: "s1", action: "shell", description: "bad" }],
        };
      },
    });

    expect(() => planner.createPlan(TASK)).toThrow(InvalidPlanError);
  });

  it("BACKDOOR: rejects tool steps without toolName", () => {
    const planner = new Planner({
      createPlan() {
        return {
          taskId: "bad",
          steps: [{ stepId: "s1", action: "tool", description: "missing tool" }],
        };
      },
    });

    expect(() => planner.createPlan(TASK)).toThrow("requires toolName");
  });

  it("BACKDOOR: rejects recall steps without memoryKey", () => {
    const planner = new Planner({
      createPlan() {
        return {
          taskId: "bad",
          steps: [{ stepId: "s1", action: "recall", description: "missing key" }],
        };
      },
    });

    expect(() => planner.createPlan(TASK)).toThrow("requires memoryKey");
  });

  it("keeps default plan backward-compatible when no provider is supplied", () => {
    const plan = new Planner().createPlan(TASK);

    expect(plan.steps.map((step) => step.action)).toEqual(["think", "respond"]);
    expect(plan.steps[1].description).toContain(TASK.userInput);
  });
});
