// ✅ P0 IMPROVED (Iter 48, 2026-05-17): real per-step routing.
//     Pre-fix the executor's try block held no statement that could
//     throw, so every step "succeeded" with a synthetic output. The
//     `action: "tool"` step type was defined in PlanStep but routed
//     nowhere.
//
//     Now: dispatch(step.action):
//       - "think"   → ModelClient.complete()
//       - "tool"    → ToolDispatcher.dispatch()
//       - "respond" → finalize (last step's content becomes output)
//     Steps without the required tool name / model client surface
//     as errors instead of silent success. Total-step budget caps
//     unbounded plans.
//
//     Backcompat: omit both deps → 'no executor wired' errors
//     (clearly an error, not silent success like pre-fix).

import { AgentPlan, AgentTask, ExecutionResult, PlanStep } from "./types";
import { ModelClient } from "./model-client";
import { ToolDispatcher } from "../03-tooling/tool-dispatcher";

const DEFAULT_MAX_STEPS = 20;

export interface ExecutorDeps {
  modelClient?: ModelClient;
  toolDispatcher?: ToolDispatcher;
  maxSteps?: number;
}

export class Executor {
  private readonly modelClient?: ModelClient;
  private readonly toolDispatcher?: ToolDispatcher;
  private readonly maxSteps: number;

  constructor(deps: ExecutorDeps = {}) {
    this.modelClient = deps.modelClient;
    this.toolDispatcher = deps.toolDispatcher;
    this.maxSteps = deps.maxSteps ?? DEFAULT_MAX_STEPS;
    if (this.maxSteps < 1) throw new Error("maxSteps must be >= 1");
  }

  /** Backcompat: pre-fix execute(plan) kept the synthetic-success
   *  shape. Iter 48 changes it to route by step.action; without
   *  a task context the dispatchers will reject. */
  async execute(plan: AgentPlan): Promise<ExecutionResult[]> {
    return this.executeWithTask(plan, {
      sessionId: "default", userId: "default", userInput: "",
    });
  }

  async executeWithTask(
    plan: AgentPlan,
    task: AgentTask,
  ): Promise<ExecutionResult[]> {
    const stepBudget = Math.min(plan.steps.length, this.maxSteps);
    const results: ExecutionResult[] = [];

    for (let i = 0; i < stepBudget; i++) {
      const step = plan.steps[i];
      try {
        const output = await this.runStep(step, task);
        results.push({
          stepId: step.stepId, success: true, output,
        });
      } catch (error) {
        results.push({
          stepId: step.stepId,
          success: false,
          output: null,
          error: error instanceof Error ? error.message : "Unknown error",
        });
        // Stop on first failure — let the caller decide whether
        // to replan. Same shape as Component 10's runNext catch.
        break;
      }
    }

    if (plan.steps.length > this.maxSteps) {
      results.push({
        stepId: "step-budget-exceeded",
        success: false,
        output: null,
        error: `Plan has ${plan.steps.length} steps; budget is ${this.maxSteps}`,
      });
    }

    return results;
  }

  private async runStep(step: PlanStep, task: AgentTask): Promise<unknown> {
    switch (step.action) {
      case "think":
        return this.runThink(step, task);
      case "tool":
        return this.runTool(step, task);
      case "respond":
        return this.runRespond(step, task);
      default:
        throw new Error(`Unknown step action: ${(step as PlanStep).action}`);
    }
  }

  private async runThink(step: PlanStep, task: AgentTask): Promise<unknown> {
    if (!this.modelClient) {
      throw new Error(`Step '${step.description}' is 'think' but no modelClient wired`);
    }
    if (!task.tenantId || !task.requestId) {
      throw new Error("'think' step requires task.tenantId and task.requestId");
    }
    const response = await this.modelClient.complete({
      requestId: task.requestId,
      tenantId: task.tenantId,
      userId: task.userId,
      prompt: `${step.description}\n\nUser input: ${task.userInput}`,
      traceId: task.traceId,
    });
    return { text: response.output, modelId: response.modelId };
  }

  private async runTool(step: PlanStep, task: AgentTask): Promise<unknown> {
    if (!this.toolDispatcher) {
      throw new Error(`Step '${step.description}' is 'tool' but no toolDispatcher wired`);
    }
    if (!step.toolName) {
      throw new Error(`Step '${step.description}' is 'tool' but step.toolName missing`);
    }
    if (!task.tenantId || !task.requestId) {
      throw new Error("'tool' step requires task.tenantId and task.requestId");
    }
    const result = await this.toolDispatcher.dispatch({
      toolName: step.toolName,
      input: step.toolInput ?? {},
      context: {
        requestId: task.requestId,
        sessionId: task.sessionId,
        userId: task.userId,
        tenantId: task.tenantId,
        traceId: task.traceId,
        roles: task.roles,
      },
    });
    if (!result.success) {
      throw new Error(result.error ?? "Tool dispatch failed");
    }
    return result.output;
  }

  private runRespond(step: PlanStep, _task: AgentTask): unknown {
    return { reply: step.description };
  }
}
