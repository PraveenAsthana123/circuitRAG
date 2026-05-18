// Negative drills for Iter 60 (2026-05-17): error-message PII /
// secret redaction.
//
// Locks the invariant that lastError.message does NOT leak common
// PII / credential patterns through the persisted envelope into
// audit rows, operator UIs, webhooks, or log shippers.
//
// Negative assertions:
//   1. Email addresses redacted
//   2. JWTs redacted (paired with iter 52 SecretScanner coverage)
//   3. Bearer tokens redacted
//   4. AWS access key IDs redacted
//   5. Credit-card-length digit runs redacted
//   6. Benign messages UNCHANGED (false-positive regression guard)
//   7. opt-out preserves raw message (dev mode)
//   8. Non-Error throws (string-typed) ALSO sanitized
//   9. undefined input handled (no crash)

import { describe, it, expect } from "vitest";
import {
  AgentWorkflowEngine,
  StepOutputContext,
  redactSensitiveMessage,
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
    redactMessages?: boolean,
  ) {
    super(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(),
      new HumanApprovalGate(), store,
      redactMessages === undefined ? {} : { redactMessages },
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
  workflowId: "wf-msg", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

describe("Iter 60 — redactSensitiveMessage (unit)", () => {
  it("BACKDOOR: redacts email addresses", () => {
    const out = redactSensitiveMessage(
      "Failed for user alice@example.com on tenant T",
    )!;
    expect(out).not.toContain("alice@example.com");
    expect(out).toContain("[REDACTED:email]");
    expect(out).toContain("on tenant T");  // context preserved
  });

  it("BACKDOOR: redacts JWT tokens", () => {
    const jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkphbmUifQ.abc123def456GHIJ";
    const out = redactSensitiveMessage(`Invalid token: ${jwt}`)!;
    expect(out).not.toContain(jwt);
    expect(out).toContain("[REDACTED:jwt]");
  });

  it("BACKDOOR: redacts Bearer tokens", () => {
    const out = redactSensitiveMessage(
      "Authorization: Bearer abc.def.ghi-jkl_mno was rejected",
    )!;
    expect(out).not.toContain("abc.def.ghi-jkl_mno");
    expect(out).toContain("[REDACTED:bearer_token]");
  });

  it("BACKDOOR: redacts AWS access key IDs", () => {
    const out = redactSensitiveMessage(
      "Token AKIAIOSFODNN7EXAMPLE was denied",
    )!;
    expect(out).not.toContain("AKIAIOSFODNN7EXAMPLE");
    expect(out).toContain("[REDACTED:aws_access_key]");
  });

  it("redacts credit-card-length digit runs (13-19 digits)", () => {
    const out1 = redactSensitiveMessage("CC: 4111 1111 1111 1111 declined")!;
    expect(out1).not.toContain("4111 1111 1111 1111");
    expect(out1).toContain("[REDACTED:digits]");

    const out2 = redactSensitiveMessage("Account 4111-1111-1111-1111 frozen")!;
    expect(out2).not.toContain("4111-1111-1111-1111");
    expect(out2).toContain("[REDACTED:digits]");
  });

  it("benign message is UNCHANGED (false-positive regression guard)", () => {
    const benign = "Failed to parse input: unexpected token at line 5";
    expect(redactSensitiveMessage(benign)).toBe(benign);
  });

  it("short numbers (order id 12345) are NOT redacted (FP guard)", () => {
    const msg = "order 12345 not found";
    expect(redactSensitiveMessage(msg)).toBe(msg);
  });

  it("undefined input → undefined output (no crash)", () => {
    expect(redactSensitiveMessage(undefined)).toBeUndefined();
  });

  it("empty string passes through unchanged", () => {
    expect(redactSensitiveMessage("")).toBe("");
  });

  it("multiple patterns in one message are ALL redacted", () => {
    const msg = "user alice@x.com with Bearer xyz123 failed";
    const out = redactSensitiveMessage(msg)!;
    expect(out).not.toContain("alice@x.com");
    expect(out).not.toContain("xyz123");
    expect(out).toContain("[REDACTED:email]");
    expect(out).toContain("[REDACTED:bearer_token]");
  });
});

describe("Iter 60 — engine wires sanitizer into lastError.message", () => {
  it("BACKDOOR: persisted error message has email REDACTED by default", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("Failed for user bob@example.org");
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-msg-1" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    const msg = after.steps[0].lastError!.message;

    expect(msg).not.toContain("bob@example.org");
    expect(msg).toContain("[REDACTED:email]");
  });

  it("opt-out: { redactMessages: false } preserves raw message (dev mode)", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error("Failed for user bob@example.org");
    }, store, false);

    const wf = engine.start({ ...CTX, workflowId: "wf-msg-2" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].lastError!.message).toContain("bob@example.org");
    expect(after.steps[0].lastError!.message).not.toContain("[REDACTED");
  });

  it("non-Error string-throw is ALSO sanitized", async () => {
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      throw "user carol@x.io blocked";
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-msg-3" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    const err = after.steps[0].lastError!;
    expect(err.name).toBe("NonError");
    expect(err.message).not.toContain("carol@x.io");
    expect(err.message).toContain("[REDACTED:email]");
  });

  it("benign error message unchanged through the engine (regression)", async () => {
    const benign = "Step plan invalid: missing requiredTool";
    const store = new WorkflowStateStore();
    const engine = new ScriptedEngine(async () => {
      throw new Error(benign);
    }, store);

    const wf = engine.start({ ...CTX, workflowId: "wf-msg-4" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const after = store.get(wf.context.workflowId, "t");
    expect(after.steps[0].lastError!.message).toBe(benign);
  });
});
