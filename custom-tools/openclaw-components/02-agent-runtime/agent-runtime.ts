// ✅ Iter 51 (2026-05-17): AgentRuntime calls Executor.executeWithTask
//     so the task's request context (tenantId, requestId, traceId,
//     roles) reaches downstream tool/model calls. Pre-fix run()
//     called the deprecated execute(plan) which dropped context —
//     any 'tool' or 'think' step with a real dispatcher would error
//     out with "missing tenantId/requestId" instead of succeeding.
//
//     Also: failed-step output now carries the structured error
//     rather than a stringified prefix, so callers can match on
//     code / stepId.

import { Planner } from "./planner";
import { Executor } from "./executor";
import { AgentTask, ExecutionResult } from "./types";

export interface AgentRuntimeResult {
  ok: boolean;
  output?: unknown;
  failedAt?: { stepId: string; error: string };
  steps: ExecutionResult[];
}

export class AgentRuntime {
  constructor(
    private readonly planner: Planner,
    private readonly executor: Executor,
  ) {}

  async run(task: AgentTask): Promise<AgentRuntimeResult> {
    const plan = this.planner.createPlan(task);
    // Iter 51: thread task context through to the executor so
    // tool/think steps can call dispatcher/modelClient.
    const steps = await this.executor.executeWithTask(plan, task);

    const failed = steps.find((s) => !s.success);
    if (failed) {
      return {
        ok: false,
        failedAt: {
          stepId: failed.stepId,
          error: failed.error ?? "Unknown error",
        },
        steps,
      };
    }

    return {
      ok: true,
      // Output of the last successful step (typically the
      // 'respond' step's reply).
      output: steps[steps.length - 1]?.output,
      steps,
    };
  }
}
