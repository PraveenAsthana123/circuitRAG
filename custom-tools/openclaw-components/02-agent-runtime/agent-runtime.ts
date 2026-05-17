import { Planner } from "./planner";
import { Executor } from "./executor";
import { AgentTask } from "./types";

export class AgentRuntime {
  constructor(
    private readonly planner: Planner,
    private readonly executor: Executor
  ) {}

  async run(task: AgentTask): Promise<string> {
    const plan = this.planner.createPlan(task);
    const results = await this.executor.execute(plan);

    const failed = results.find((r) => !r.success);

    if (failed) {
      return `Task failed at step ${failed.stepId}: ${failed.error}`;
    }

    return results.map((r) => r.output).join("\n");
  }
}
