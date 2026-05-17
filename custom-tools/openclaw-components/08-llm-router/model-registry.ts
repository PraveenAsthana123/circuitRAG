import { ModelConfig, TaskType } from "./types";

export class ModelRegistry {
  constructor(private readonly models: ModelConfig[]) {}

  findCandidates(taskType: TaskType): ModelConfig[] {
    return this.models
      .filter((m) => m.enabled && m.supportedTasks.includes(taskType))
      .sort((a, b) => a.priority - b.priority);
  }
}
