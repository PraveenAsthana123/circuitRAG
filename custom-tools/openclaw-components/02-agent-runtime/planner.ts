import { randomUUID } from "crypto";
import { AgentTask, AgentPlan, PlanStep } from "./types";

const ALLOWED_ACTIONS = new Set(["think", "tool", "respond", "recall"]);

export interface PlanProvider {
  createPlan(task: AgentTask): unknown;
}

export class InvalidPlanError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidPlanError";
  }
}

export class Planner {
  constructor(private readonly provider?: PlanProvider) {}

  createPlan(task: AgentTask): AgentPlan {
    if (this.provider) {
      return this.validatePlan(this.provider.createPlan(task));
    }

    return this.createDefaultPlan(task);
  }

  private createDefaultPlan(task: AgentTask): AgentPlan {
    return {
      taskId: randomUUID(),
      steps: [
        {
          stepId: randomUUID(),
          action: "think",
          description: "Understand user intent and required outcome",
        },
        {
          stepId: randomUUID(),
          action: "respond",
          description: `Answer user request: ${task.userInput}`,
        },
      ],
    };
  }

  private validatePlan(candidate: unknown): AgentPlan {
    if (candidate === null || typeof candidate !== "object") {
      throw new InvalidPlanError("Plan must be an object");
    }

    const plan = candidate as { taskId?: unknown; steps?: unknown };
    if (typeof plan.taskId !== "string" || plan.taskId.length === 0) {
      throw new InvalidPlanError("Plan taskId must be a non-empty string");
    }
    if (!Array.isArray(plan.steps) || plan.steps.length === 0) {
      throw new InvalidPlanError("Plan steps must be a non-empty array");
    }

    return {
      taskId: plan.taskId,
      steps: plan.steps.map((step, index) => this.validateStep(step, index)),
    };
  }

  private validateStep(candidate: unknown, index: number): PlanStep {
    if (candidate === null || typeof candidate !== "object") {
      throw new InvalidPlanError(`Step ${index} must be an object`);
    }

    const step = candidate as Record<string, unknown>;
    if (typeof step.stepId !== "string" || step.stepId.length === 0) {
      throw new InvalidPlanError(`Step ${index} stepId must be a non-empty string`);
    }
    if (typeof step.action !== "string" || !ALLOWED_ACTIONS.has(step.action)) {
      throw new InvalidPlanError(`Step ${index} action is invalid`);
    }
    if (typeof step.description !== "string" || step.description.length === 0) {
      throw new InvalidPlanError(`Step ${index} description must be a non-empty string`);
    }

    const out: PlanStep = {
      stepId: step.stepId,
      action: step.action as PlanStep["action"],
      description: step.description,
    };

    if (step.toolName !== undefined) {
      if (typeof step.toolName !== "string" || step.toolName.length === 0) {
        throw new InvalidPlanError(`Step ${index} toolName must be a non-empty string`);
      }
      out.toolName = step.toolName;
    }
    if (step.toolInput !== undefined) {
      if (step.toolInput === null || typeof step.toolInput !== "object" || Array.isArray(step.toolInput)) {
        throw new InvalidPlanError(`Step ${index} toolInput must be an object`);
      }
      out.toolInput = step.toolInput as Record<string, unknown>;
    }
    if (step.memoryKey !== undefined) {
      if (typeof step.memoryKey !== "string" || step.memoryKey.length === 0) {
        throw new InvalidPlanError(`Step ${index} memoryKey must be a non-empty string`);
      }
      out.memoryKey = step.memoryKey;
    }

    if (out.action === "tool" && !out.toolName) {
      throw new InvalidPlanError(`Step ${index} action 'tool' requires toolName`);
    }
    if (out.action === "recall" && !out.memoryKey) {
      throw new InvalidPlanError(`Step ${index} action 'recall' requires memoryKey`);
    }

    return out;
  }
}
