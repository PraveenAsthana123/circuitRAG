// Negative drills for Iter 64 (2026-05-17): Executor guardrail
// injection (input-side + output-side).
//
// Closes GAPS.md Component 2 P1:
//   "Tool/model routing is wired, but memory, guardrails, and
//    tracing are still not full runtime dependencies — Constructor-
//    inject Components 4-6 dependencies; thread `traceId` through
//    every call"
//
// This iter closes the GUARDRAILS half. Memory injection deferred
// (no concrete use case yet — adding params nobody uses violates
// "no half-finished implementations" rule).
//
// Negative assertions:
//   1. BACKDOOR: blocked input → executor short-circuits with a
//      single guardrail-input-block failure result; NO steps run.
//   2. BACKDOOR: think-step model response that contains PII →
//      step fails with guardrail-output error.
//   3. Guardrails not wired → backcompat preserved (no enforcement).
//   4. Allowed input + clean response → steps execute normally
//      (positive regression guard).
//   5. "review" decision does NOT short-circuit (only "block" does).
//   6. Input guardrail receives the task's traceId in context
//      (trace-propagation regression guard).
//   7. Output guardrail block on think step → result.error names
//      the failed-rule id (audit visibility).

import { describe, it, expect } from "vitest";
import { Executor } from "./executor";
import { ModelClient } from "./model-client";
import { GuardrailEngine } from "../05-guardrails/guardrail-engine";
import { PIIDetector } from "../05-guardrails/pii-detector";
import { PromptInjectionDetector } from "../05-guardrails/prompt-injection-detector";
import { PolicyEngine } from "../05-guardrails/policy-engine";
import { ApprovalGate } from "../05-guardrails/approval-gate";
import {
  GuardrailContext,
  GuardrailRequest,
  GuardrailResult,
} from "../05-guardrails/types";
import { LLMResponse } from "../08-llm-router/types";
import { AgentPlan, AgentTask } from "./types";

// ---- Fixtures ----------------------------------------------------

class FixedModelClient extends ModelClient {
  public lastPrompt: string | undefined;
  public callCount = 0;
  constructor(private readonly output: string) {
    // We never call the underlying router; pass any cast.
    super({ route: async () => ({} as LLMResponse) } as never);
  }
  async complete(input: { prompt: string }): Promise<LLMResponse> {
    this.callCount += 1;
    this.lastPrompt = input.prompt;
    return {
      modelId: "fake-model", provider: "ollama",
      output: this.output, latencyMs: 1,
      estimatedCostUsd: 0, explanation: "fixture",
    };
  }
}

/** Stub engine — records every call + returns whatever the test
 *  configures. Lets the drill assert on the EXACT decision/context
 *  flow without depending on the real PII / injection rules. */
class StubGuardrailEngine extends GuardrailEngine {
  public requestCalls: GuardrailRequest[] = [];
  public responseCalls: Array<{ text: string; context: GuardrailContext }> = [];
  constructor(
    private readonly requestResult: GuardrailResult,
    private readonly responseResult: GuardrailResult = ALLOW,
  ) {
    super(
      new PIIDetector(),
      new PromptInjectionDetector(),
      new PolicyEngine(),
      new ApprovalGate(),
    );
  }
  evaluateRequest(req: GuardrailRequest): GuardrailResult {
    this.requestCalls.push(req);
    return this.requestResult;
  }
  evaluateResponse(text: string, ctx: GuardrailContext): GuardrailResult {
    this.responseCalls.push({ text, context: ctx });
    return this.responseResult;
  }
}

const ALLOW: GuardrailResult = { decision: "allow", findings: [], explanation: "ok" };
const REVIEW: GuardrailResult = {
  decision: "review",
  findings: [{ ruleId: "INPUT_PII_EMAIL", severity: "medium", message: "email seen" }],
  explanation: "review",
};
const BLOCK_INPUT: GuardrailResult = {
  decision: "block",
  findings: [{ ruleId: "INPUT_PROMPT_INJECTION", severity: "high", message: "injection" }],
  explanation: "block",
};
const BLOCK_OUTPUT: GuardrailResult = {
  decision: "block",
  findings: [{ ruleId: "OUTPUT_PII_PHONE", severity: "critical", message: "phone leak" }],
  explanation: "block",
};

const PLAN_THINK: AgentPlan = {
  taskId: "plan-1",
  steps: [
    { stepId: "s1", action: "think", description: "reason about the request" },
    { stepId: "s2", action: "respond", description: "Here is the answer" },
  ],
};

const TASK: AgentTask = {
  sessionId: "sess-1", userId: "user-1", userInput: "hello",
  tenantId: "tenant-1", requestId: "req-1", traceId: "trace-abc",
};

// ---- Drills ------------------------------------------------------

describe("Iter 64 — Executor guardrail injection (P1)", () => {
  it("BACKDOOR: blocked input short-circuits — NO step runs, single failure result", async () => {
    const model = new FixedModelClient("response text");
    const guardrails = new StubGuardrailEngine(BLOCK_INPUT);
    const exec = new Executor({ modelClient: model, guardrails });

    const results = await exec.executeWithTask(PLAN_THINK, TASK);

    expect(results.length).toBe(1);
    expect(results[0].stepId).toBe("guardrail-input-block");
    expect(results[0].success).toBe(false);
    expect(results[0].error).toContain("INPUT_PROMPT_INJECTION");
    expect(model.callCount).toBe(0);  // model NEVER called
    expect(guardrails.requestCalls.length).toBe(1);  // input check ran
    expect(guardrails.responseCalls.length).toBe(0); // output NOT checked
  });

  it("BACKDOOR: think-step output blocked → step fails with guardrail-output error", async () => {
    const model = new FixedModelClient("Here is the secret: 415-555-0199");
    // Input passes; output blocks.
    const guardrails = new StubGuardrailEngine(ALLOW, BLOCK_OUTPUT);
    const exec = new Executor({ modelClient: model, guardrails });

    const results = await exec.executeWithTask(PLAN_THINK, TASK);

    // First (think) step recorded as failed; second step never ran
    // because executor stops on first failure (same pattern as
    // Component 10).
    expect(results.length).toBe(1);
    expect(results[0].stepId).toBe("s1");
    expect(results[0].success).toBe(false);
    expect(results[0].error).toContain("Guardrail blocked think output");
    expect(results[0].error).toContain("OUTPUT_PII_PHONE");
    expect(model.callCount).toBe(1);  // model WAS called
    expect(guardrails.responseCalls.length).toBe(1);  // output check ran
  });

  it("BACKCOMPAT: guardrails omitted → no enforcement (pre-iter-64 behavior)", async () => {
    const model = new FixedModelClient("response text");
    const exec = new Executor({ modelClient: model });  // no guardrails

    const results = await exec.executeWithTask(PLAN_THINK, TASK);

    // Both steps complete successfully (think + respond).
    expect(results.length).toBe(2);
    expect(results.every((r) => r.success)).toBe(true);
    expect(model.callCount).toBe(1);
  });

  it("guardrails wired + allowed → steps run normally (regression guard)", async () => {
    const model = new FixedModelClient("clean answer");
    const guardrails = new StubGuardrailEngine(ALLOW, ALLOW);
    const exec = new Executor({ modelClient: model, guardrails });

    const results = await exec.executeWithTask(PLAN_THINK, TASK);

    expect(results.length).toBe(2);
    expect(results.every((r) => r.success)).toBe(true);
    expect(guardrails.requestCalls.length).toBe(1);
    expect(guardrails.responseCalls.length).toBe(1);
  });

  it('"review" decision does NOT short-circuit (only "block" does)', async () => {
    const model = new FixedModelClient("response");
    // Both input and output return REVIEW (PII present but not blocked).
    const guardrails = new StubGuardrailEngine(REVIEW, REVIEW);
    const exec = new Executor({ modelClient: model, guardrails });

    const results = await exec.executeWithTask(PLAN_THINK, TASK);

    expect(results.length).toBe(2);  // both steps ran
    expect(results.every((r) => r.success)).toBe(true);
  });

  it("input guardrail receives task.traceId in its context (trace propagation)", async () => {
    const model = new FixedModelClient("response");
    const guardrails = new StubGuardrailEngine(ALLOW);
    const exec = new Executor({ modelClient: model, guardrails });
    await exec.executeWithTask(PLAN_THINK, TASK);
    expect(guardrails.requestCalls[0].context.traceId).toBe("trace-abc");
    expect(guardrails.requestCalls[0].context.requestId).toBe("req-1");
    expect(guardrails.requestCalls[0].context.tenantId).toBe("tenant-1");
  });

  it("output guardrail block names the failed-rule id in the step error (audit visibility)", async () => {
    const model = new FixedModelClient("output with phone 415-555-0199");
    const guardrails = new StubGuardrailEngine(ALLOW, BLOCK_OUTPUT);
    const exec = new Executor({ modelClient: model, guardrails });
    const results = await exec.executeWithTask(PLAN_THINK, TASK);
    expect(results[0].error).toMatch(/OUTPUT_PII_PHONE/);
  });

  it("input guardrail check SKIPPED when task lacks tenantId/requestId (no crash)", async () => {
    // Pre-iter-64 task type allows tenantId/requestId to be omitted
    // (e.g., original Component 1 Gateway smoke test). Guardrail must
    // not be invoked without context — that would crash on the
    // required tenantId field. Backcompat regression guard.
    const model = new FixedModelClient("response");
    const guardrails = new StubGuardrailEngine(BLOCK_INPUT);
    const exec = new Executor({ modelClient: model, guardrails });
    const minimalTask: AgentTask = {
      sessionId: "s", userId: "u", userInput: "hello",
    };
    const results = await exec.executeWithTask(PLAN_THINK, minimalTask);
    // Guardrail was not called; think step ran (will fail because
    // ModelClient.complete needs tenantId/requestId — but the
    // failure must come from THAT validator, not from the guardrail).
    expect(guardrails.requestCalls.length).toBe(0);
  });
});
