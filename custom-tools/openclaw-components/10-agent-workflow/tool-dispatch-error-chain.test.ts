// Negative drills for M1.1 (2026-05-18): Tool dispatch error chain
// preservation. When a dispatched tool fails, the workflow engine
// must persist the FULL forensic trail (error class, stack, cause
// chain) in StepErrorEnvelope, not just a flattened message string.
//
// Pre-fix: executeSelectedTool threw `new Error(result.error)`,
// losing class name / stack / underlying cause.
// Post-fix: throws ToolDispatchFailedError with Error.cause chain
// populated from ToolDispatcher's new ToolResult.errorMeta.

import { describe, it, expect } from "vitest";
import {
  AgentWorkflowEngine,
  ToolDispatchFailedError,
  StepOutputContext,
} from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowContext, WorkflowStep } from "./types";
import {
  ToolDispatcher,
} from "../03-tooling/tool-dispatcher";
import { ToolRequest, ToolResult } from "../03-tooling/types";

/** Stub dispatcher that returns scripted ToolResults. */
class ScriptedDispatcher {
  public calls: ToolRequest[] = [];
  constructor(private readonly script: (req: ToolRequest) => ToolResult) {}
  async dispatch(req: ToolRequest): Promise<ToolResult> {
    this.calls.push(req);
    return this.script(req);
  }
}

function newEngine(dispatcher: ScriptedDispatcher): {
  engine: AgentWorkflowEngine;
  store: WorkflowStateStore;
} {
  const store = new WorkflowStateStore();
  const engine = new AgentWorkflowEngine(
    new WorkflowPlanner(),
    new Replanner(),
    new ToolSelector(),
    new HumanApprovalGate(),
    store,
    { toolDispatcher: dispatcher as unknown as ToolDispatcher },
  );
  return { engine, store };
}

const CTX: WorkflowContext = {
  workflowId: "wf-dispatch", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

describe("M1.1 — Tool dispatch error chain preservation (P0)", () => {
  it("BACKDOOR: successful dispatch persists output (regression)", async () => {
    const dispatcher = new ScriptedDispatcher(() => ({
      success: true,
      output: { value: "ok" },
      durationMs: 5,
    }));
    const { engine, store } = newEngine(dispatcher);
    const wf = engine.start({ ...CTX, workflowId: "wf-ok" }, "test");

    await engine.runNext(wf.context.workflowId, "t");

    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].status).toBe("completed");
    expect(after.steps[0].output).toEqual({ value: "ok" });
    expect(after.steps[0].lastError).toBeUndefined();
    expect(dispatcher.calls.length).toBe(1);
  });

  it("BACKDOOR: dispatch failure THROWS ToolDispatchFailedError (not bare Error)", async () => {
    const dispatcher = new ScriptedDispatcher(() => ({
      success: false,
      error: "remote 502",
      errorMeta: {
        name: "BadGatewayError",
        message: "remote 502",
        stack: "BadGatewayError: remote 502\n    at fetch (/mnt/deepa/x:5:1)",
      },
      durationMs: 3,
    }));
    const { engine, store } = newEngine(dispatcher);
    const wf = engine.start({ ...CTX, workflowId: "wf-fail" }, "test");

    await engine.runNext(wf.context.workflowId, "t");

    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].status).toBe("failed");
    const env = after.steps[0].lastError!;
    expect(env).toBeDefined();
    expect(env.name).toBe("ToolDispatchFailedError");
    expect(env.message).toBe("remote 502");
  });

  it("BACKDOOR: dispatch failure PRESERVES original error class in cause", async () => {
    const dispatcher = new ScriptedDispatcher(() => ({
      success: false,
      error: "TLS handshake aborted",
      errorMeta: {
        name: "TLSError",
        message: "TLS handshake aborted",
      },
      durationMs: 1,
    }));
    const { engine, store } = newEngine(dispatcher);
    const wf = engine.start({ ...CTX, workflowId: "wf-cause-1" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const env = store.get(wf.context.workflowId, "t").steps[0].lastError!;
    expect(env.cause).toBeDefined();
    expect(env.cause!.name).toBe("TLSError");
    expect(env.cause!.message).toBe("TLS handshake aborted");
  });

  it("BACKDOOR: cause.stack is REDACTED (no host filesystem paths persisted)", async () => {
    const dispatcher = new ScriptedDispatcher(() => ({
      success: false,
      error: "timeout",
      errorMeta: {
        name: "TimeoutError",
        message: "timeout",
        // Stack passed through the dispatcher's redactStackPaths
        // helper before reaching here; assert the redaction made it
        // into the envelope. (We pre-redact here to simulate what
        // ToolDispatcher actually does in production.)
        stack: "TimeoutError: timeout\n    at op ([redacted]:42:10)",
      },
      durationMs: 1,
    }));
    const { engine, store } = newEngine(dispatcher);
    const wf = engine.start({ ...CTX, workflowId: "wf-redact" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const env = store.get(wf.context.workflowId, "t").steps[0].lastError!;
    expect(env.cause!.stack).toBeDefined();
    expect(env.cause!.stack).not.toContain("/mnt/deepa");
    expect(env.cause!.stack).toContain("[redacted]");
  });

  it("BACKDOOR: nested cause chain (tool wrapped HTTP error) survives one level", async () => {
    const dispatcher = new ScriptedDispatcher(() => ({
      success: false,
      error: "tool wrapped",
      errorMeta: {
        name: "ToolExecutionError",
        message: "tool wrapped",
        cause: {
          name: "HttpError",
          message: "502 Bad Gateway",
        },
      },
      durationMs: 1,
    }));
    const { engine, store } = newEngine(dispatcher);
    const wf = engine.start({ ...CTX, workflowId: "wf-nested" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const env = store.get(wf.context.workflowId, "t").steps[0].lastError!;
    expect(env.cause!.name).toBe("ToolExecutionError");
    // Nested HttpError reaches the audit envelope.
    expect(env.cause!.cause).toBeDefined();
    expect(env.cause!.cause!.name).toBe("HttpError");
    expect(env.cause!.cause!.message).toBe("502 Bad Gateway");
  });

  it("ToolDispatchFailedError carries toolName (audit visibility)", () => {
    const err = new ToolDispatchFailedError("calculator", "blew up", {
      name: "ParseError",
      message: "blew up",
    });
    expect(err.toolName).toBe("calculator");
    expect(err.name).toBe("ToolDispatchFailedError");
    expect(err.message).toBe("blew up");
  });

  it("ToolDispatchFailedError WITHOUT errorMeta still works (legacy dispatcher returns)", () => {
    const err = new ToolDispatchFailedError("legacy-tool", "old-style failure");
    expect(err.toolName).toBe("legacy-tool");
    expect((err as Error & { cause?: Error }).cause).toBeUndefined();
  });

  it("BACKDOOR: dispatch failure routes through replan (engine path regression)", async () => {
    const dispatcher = new ScriptedDispatcher(() => ({
      success: false,
      error: "permanent failure",
      errorMeta: { name: "ConfigError", message: "permanent failure" },
      durationMs: 1,
    }));
    const { engine, store } = newEngine(dispatcher);
    const wf = engine.start({ ...CTX, workflowId: "wf-replan" }, "test");
    const after = await engine.runNext(wf.context.workflowId, "t");

    expect(after.status).toBe("replanning");
    // Replan inserted a recovery_step; the failed step's lastError
    // is preserved through the replanner copy.
    const persisted = store.get(wf.context.workflowId, "t");
    const failedStep = persisted.steps.find((s) => s.status === "failed")!;
    expect(failedStep.lastError!.name).toBe("ToolDispatchFailedError");
    expect(failedStep.lastError!.cause!.name).toBe("ConfigError");
  });

  it("dispatch failure with NO errorMeta still produces a clean envelope (backcompat)", async () => {
    const dispatcher = new ScriptedDispatcher(() => ({
      success: false,
      error: "ancient-style failure",
      // No errorMeta — older dispatcher behavior.
      durationMs: 1,
    }));
    const { engine, store } = newEngine(dispatcher);
    const wf = engine.start({ ...CTX, workflowId: "wf-bc" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const env = store.get(wf.context.workflowId, "t").steps[0].lastError!;
    expect(env.name).toBe("ToolDispatchFailedError");
    expect(env.message).toBe("ancient-style failure");
    expect(env.cause).toBeUndefined();  // graceful absence
  });

  it("backcompat: WITHOUT toolDispatcher wired, simulateToolExecution path still works", async () => {
    // Engine constructed without a dispatcher; legacy test-friendly
    // simulateToolExecution path runs (returns undefined).
    const store = new WorkflowStateStore();
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(),
      new Replanner(),
      new ToolSelector(),
      new HumanApprovalGate(),
      store,
      {},  // no toolDispatcher
    );
    const wf = engine.start({ ...CTX, workflowId: "wf-no-disp" }, "test");
    const after = await engine.runNext(wf.context.workflowId, "t");
    // Simulator returns undefined → step completes successfully.
    expect(after.steps[0].status).toBe("completed");
  });
});
