import { describe, it, expect } from "vitest";
import { ToolRegistry } from "./tool-registry";
import { ToolDispatcher } from "./tool-dispatcher";
import { Logger } from "./logger";
import { Telemetry } from "./telemetry";
import { ResponsibleAIGuard } from "./responsible-ai-guard";
import { ExplainabilityRecorder } from "./explainability-recorder";
import { calculatorTool } from "./calculator-tool";

describe("ToolDispatcher", () => {
  it("executes a safe tool successfully", async () => {
    const registry = new ToolRegistry();
    registry.register(calculatorTool);

    const dispatcher = new ToolDispatcher(
      registry,
      new Logger(),
      new Telemetry(),
      new ResponsibleAIGuard(),
      new ExplainabilityRecorder()
    );

    const result = await dispatcher.dispatch({
      toolName: "calculator",
      input: { expression: "2 + 3 * 4" },
      context: {
        requestId: "req-1",
        sessionId: "session-1",
        userId: "user-1",
        tenantId: "tenant-1",
      },
    });

    expect(result.success).toBe(true);
  });
});
