// Negative drills for Iter 59 (2026-05-17): stack-trace path redaction.
//
// Locks the invariant that lastError.stack does NOT leak absolute
// filesystem paths into the persisted workflow state (and from
// there into audit rows / operator UIs / webhooks).
//
// Negative assertions:
//   1. Default behavior REDACTS host paths in parenthesized stack lines
//   2. Default behavior REDACTS host paths in anonymous (no-parens) lines
//   3. Default behavior REDACTS file:// URL form (ESM)
//   4. Default behavior REDACTS Windows-style paths (C:\foo\bar)
//   5. Default behavior PRESERVES function names + :line:col
//   6. Default behavior PRESERVES node:internal/* lines (no host info)
//   7. opt-out (redactStackPaths: false) preserves raw stack (dev mode)
//   8. NonError throws (no stack) are unaffected (no crash)

import { describe, it, expect } from "vitest";
import {
  AgentWorkflowEngine,
  StepOutputContext,
  redactStackPaths,
} from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowContext, WorkflowStep } from "./types";

class ScriptedEngine extends AgentWorkflowEngine {
  constructor(
    private readonly script: () => Promise<unknown>,
    store: WorkflowStateStore,
    redact?: boolean,
  ) {
    super(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), store,
      redact === undefined ? {} : { redactStackPaths: redact },
    );
  }
  protected async simulateToolExecution(
    _toolName: string,
    _ctx: StepOutputContext,
    _step: WorkflowStep,
  ): Promise<unknown> {
    return this.script();
  }
}

const CTX: WorkflowContext = {
  workflowId: "wf-stack", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

describe("Iter 59 — redactStackPaths (unit)", () => {
  it("BACKDOOR: redacts a Linux absolute path inside parentheses", () => {
    const stack =
      "Error: probe\n" +
      "    at inner (/mnt/deepa/rag/custom-tools/openclaw-components/x.ts:42:10)";
    const out = redactStackPaths(stack)!;
    expect(out).not.toContain("/mnt/deepa/rag");
    expect(out).toContain("([redacted]:42:10)");
    // Function name preserved.
    expect(out).toContain("at inner");
  });

  it("BACKDOOR: redacts a file:// URL (Node ESM stack frame)", () => {
    const stack = "Error: x\n    at outer (file:///home/u/proj/file.mjs:7:3)";
    const out = redactStackPaths(stack)!;
    expect(out).not.toContain("file:///");
    expect(out).not.toContain("/home/u");
    expect(out).toContain("([redacted]:7:3)");
  });

  it("BACKDOOR: redacts anonymous (no-parens) stack lines", () => {
    const stack = "Error: x\n    at /tmp/x.ts:5:9";
    const out = redactStackPaths(stack)!;
    expect(out).not.toContain("/tmp/x.ts");
    expect(out).toContain("[redacted]:5:9");
  });

  it("redacts Windows-style paths (C:\\…)", () => {
    const stack = "Error: x\n    at fn (C:\\Users\\me\\app.ts:1:2)";
    const out = redactStackPaths(stack)!;
    expect(out).not.toContain("C:\\Users");
    expect(out).toContain("([redacted]:1:2)");
  });

  it("PRESERVES node:internal/* lines (no host info)", () => {
    const stack =
      "Error: x\n" +
      "    at fn (/mnt/deepa/rag/x.ts:1:1)\n" +
      "    at runScriptInThisContext (node:internal/vm:209:10)";
    const out = redactStackPaths(stack)!;
    // Host-path line redacted.
    expect(out).not.toContain("/mnt/deepa/rag/x.ts");
    // node:internal line unchanged (carries no host info).
    expect(out).toContain("(node:internal/vm:209:10)");
  });

  it("returns undefined when input is undefined (no crash)", () => {
    expect(redactStackPaths(undefined)).toBeUndefined();
  });

  it("redacts ALL paths in a multi-line stack (not just the first)", () => {
    const stack =
      "Error: x\n" +
      "    at a (/abs/a.ts:1:1)\n" +
      "    at b (/abs/b.ts:2:2)\n" +
      "    at c (/abs/c.ts:3:3)";
    const out = redactStackPaths(stack)!;
    expect(out).not.toContain("/abs/");
    // Three redactions = three :LINE:COL pairs preserved.
    expect((out.match(/\[redacted\]:\d+:\d+/g) ?? []).length).toBe(3);
  });
});

describe("Iter 59 — engine wires redactor into lastError.stack", () => {
  it("BACKDOOR: by default, persisted lastError.stack contains no host path", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("triggered from engine flow");
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-stack-1" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    const stack = after.steps[0].lastError!.stack!;

    expect(stack).toBeDefined();
    // No absolute path crumbs.
    expect(stack).not.toContain("/mnt/deepa/rag");
    expect(stack).not.toContain("/custom-tools/openclaw-components");
    expect(stack).not.toMatch(/file:\/\/\//);
    // Marker is present somewhere.
    expect(stack).toMatch(/\[redacted\]/);
  });

  it("opt-out: { redactStackPaths: false } preserves raw stack (dev mode)", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("dev mode trigger");
    }, store, false);

    const wf = engine.start({ ...CTX, workflowId: "wf-stack-2" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    const stack = after.steps[0].lastError!.stack!;

    // Now the absolute path SHOULD appear (we opted out).
    expect(stack).toMatch(/\/mnt\/deepa\/rag|file:\/\/\//);
    // No redaction marker.
    expect(stack).not.toContain("[redacted]");
  });

  it("non-Error throw (string) has no stack — redactor not invoked, no crash", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      throw "string-throw";
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-stack-3" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    const err = after.steps[0].lastError!;
    expect(err.name).toBe("NonError");
    expect(err.stack).toBeUndefined();
  });
});
