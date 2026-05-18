// Negative drills for Iter 72 (2026-05-17): memory-aware think step.
//
// Closes the deliberately-deferred half from iter 65: the `recall`
// step's output was stored on ExecutionResult.output but no
// downstream step CONSUMED it. A subsequent `think` step built its
// prompt only from task.userInput + step.description — ignoring
// whatever memory was just recalled.
//
// Iter 72 fix: runThink now reads the executed-results-so-far slice.
// Any prior recall step whose found === true contributes its
// key+value to a "Prior memory:" preamble prepended to the prompt.
// Misses (found: false) do NOT inject. No recall steps at all →
// prompt is byte-identical to pre-iter-72 shape (backcompat).
//
// Negative assertions:
//   1. BACKDOOR: recall THEN think → think's prompt contains the
//      recalled value (positive path)
//   2. BACKDOOR: no recall steps → prompt is EXACTLY the pre-iter-72
//      shape (backcompat regression guard)
//   3. BACKDOOR: a recall that returned found=false does NOT inject
//      into the subsequent think prompt
//   4. multiple recall steps' values are ALL included in subsequent
//      think prompt (composition)
//   5. think step in the MIDDLE of multiple recalls sees only the
//      recalls BEFORE it, not after (slice-order invariant)
//   6. recall step output preserved on ExecutionResult unchanged
//      (iter 65 regression guard — fixing iter 72 must not corrupt
//      the recall step's own output shape)
//   7. think step still works when no memory wired at all
//      (defensive: a plan with no recall + no memory dep should
//      still let think run)

import { describe, it, expect } from "vitest";
import { Executor } from "./executor";
import { ModelClient } from "./model-client";
import { MemoryGovernanceService } from "../04-memory-governance/memory-governance-service";
import { MemoryStore } from "../04-memory-governance/memory-store";
import { MemoryAuditLog } from "../04-memory-governance/memory-audit-log";
import { PIIMasker } from "../04-memory-governance/pii-masker";
import { RetentionPolicy } from "../04-memory-governance/retention-policy";
import { LLMResponse } from "../08-llm-router/types";
import { AgentPlan, AgentTask, PlanStep } from "./types";

// ---- Fixtures ----------------------------------------------------

/** Records the LAST prompt the model received. Same pattern as
 *  iter 64's guardrail-injection drill. */
class FixedModelClient extends ModelClient {
  public lastPrompt: string | undefined;
  public callCount = 0;
  public prompts: string[] = [];
  constructor(private readonly output: string = "ok") {
    super({ route: async () => ({} as LLMResponse) } as never);
  }
  async complete(input: { prompt: string }): Promise<LLMResponse> {
    this.callCount += 1;
    this.lastPrompt = input.prompt;
    this.prompts.push(input.prompt);
    return {
      modelId: "fake-model", provider: "ollama",
      output: this.output, latencyMs: 1,
      estimatedCostUsd: 0, explanation: "fixture",
    };
  }
}

function newMemory() {
  return new MemoryGovernanceService(
    new MemoryStore(),
    new MemoryAuditLog(),
    new PIIMasker(),
    new RetentionPolicy(),
  );
}

const TASK: AgentTask = {
  sessionId: "sess", userId: "user-1", userInput: "what do I prefer?",
  tenantId: "tenant-1", requestId: "req-1", traceId: "tr",
};

const THINK_STEP: PlanStep = {
  stepId: "t1",
  action: "think",
  description: "summarize the user's preference",
};

const RECALL_STEP_LANG: PlanStep = {
  stepId: "r1",
  action: "recall",
  description: "fetch language pref",
  memoryKey: "pref-language",
};

const RECALL_STEP_TIMEZONE: PlanStep = {
  stepId: "r2",
  action: "recall",
  description: "fetch timezone",
  memoryKey: "pref-timezone",
};

describe("Iter 72 — memory-aware think step (closes iter 65 partial)", () => {
  it("BACKDOOR: recall THEN think → think prompt contains recalled value", async () => {
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-language", value: "TypeScript",
      reason: "user pref",
    });
    const model = new FixedModelClient();
    const exec = new Executor({ memory, modelClient: model });
    const plan: AgentPlan = {
      taskId: "p1",
      steps: [RECALL_STEP_LANG, THINK_STEP],
    };
    const results = await exec.executeWithTask(plan, TASK);
    expect(results).toHaveLength(2);
    expect(results[0].success).toBe(true);
    expect(results[1].success).toBe(true);
    // Think prompt should contain the recalled value.
    expect(model.lastPrompt).toContain("Prior memory:");
    expect(model.lastPrompt).toContain("pref-language: TypeScript");
    // And still contain the original step.description + userInput.
    expect(model.lastPrompt).toContain("summarize the user's preference");
    expect(model.lastPrompt).toContain("User input: what do I prefer?");
  });

  it("BACKDOOR: no recall steps → prompt EXACTLY matches pre-iter-72 shape (backcompat)", async () => {
    const model = new FixedModelClient();
    const exec = new Executor({ modelClient: model });
    const plan: AgentPlan = { taskId: "p2", steps: [THINK_STEP] };
    const results = await exec.executeWithTask(plan, TASK);
    expect(results[0].success).toBe(true);
    // Byte-identical to the pre-iter-72 shape:
    // `${step.description}\n\nUser input: ${task.userInput}`
    expect(model.lastPrompt).toBe(
      "summarize the user's preference\n\nUser input: what do I prefer?",
    );
    // Critically: NO "Prior memory:" anywhere.
    expect(model.lastPrompt).not.toContain("Prior memory:");
  });

  it("BACKDOOR: recall with found=false does NOT inject into think prompt", async () => {
    const memory = newMemory();
    // Do NOT save anything — recall will return found=false.
    const model = new FixedModelClient();
    const exec = new Executor({ memory, modelClient: model });
    const plan: AgentPlan = {
      taskId: "p3",
      steps: [RECALL_STEP_LANG, THINK_STEP],
    };
    const results = await exec.executeWithTask(plan, TASK);
    expect(results[0].success).toBe(true);
    expect((results[0].output as { found: boolean }).found).toBe(false);
    expect(results[1].success).toBe(true);
    // No "Prior memory:" because the only recall was a miss.
    expect(model.lastPrompt).not.toContain("Prior memory:");
    expect(model.lastPrompt).not.toContain("pref-language");
    // Same exact pre-iter-72 shape as the no-recall case.
    expect(model.lastPrompt).toBe(
      "summarize the user's preference\n\nUser input: what do I prefer?",
    );
  });

  it("multiple recall step values are ALL included in subsequent think prompt", async () => {
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-language", value: "TypeScript",
      reason: "user pref",
    });
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-timezone", value: "America/Denver",
      reason: "user pref",
    });
    const model = new FixedModelClient();
    const exec = new Executor({ memory, modelClient: model });
    const plan: AgentPlan = {
      taskId: "p4",
      steps: [RECALL_STEP_LANG, RECALL_STEP_TIMEZONE, THINK_STEP],
    };
    const results = await exec.executeWithTask(plan, TASK);
    expect(results).toHaveLength(3);
    expect(results.every((r) => r.success)).toBe(true);
    expect(model.lastPrompt).toContain("Prior memory:");
    expect(model.lastPrompt).toContain("pref-language: TypeScript");
    expect(model.lastPrompt).toContain("pref-timezone: America/Denver");
  });

  it("think step in MIDDLE of recalls sees only recalls BEFORE it, not after", async () => {
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-language", value: "TypeScript",
      reason: "user pref",
    });
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-timezone", value: "America/Denver",
      reason: "user pref",
    });
    const model = new FixedModelClient();
    const exec = new Executor({ memory, modelClient: model });
    // Order: recall-language, think, recall-timezone, think
    const plan: AgentPlan = {
      taskId: "p5",
      steps: [
        RECALL_STEP_LANG,
        { ...THINK_STEP, stepId: "t-mid" },
        RECALL_STEP_TIMEZONE,
        { ...THINK_STEP, stepId: "t-end" },
      ],
    };
    const results = await exec.executeWithTask(plan, TASK);
    expect(results).toHaveLength(4);
    expect(results.every((r) => r.success)).toBe(true);
    expect(model.prompts).toHaveLength(2);
    // First think sees ONLY language (timezone hasn't recalled yet).
    expect(model.prompts[0]).toContain("pref-language: TypeScript");
    expect(model.prompts[0]).not.toContain("pref-timezone");
    // Second think sees BOTH (language + timezone now in prior).
    expect(model.prompts[1]).toContain("pref-language: TypeScript");
    expect(model.prompts[1]).toContain("pref-timezone: America/Denver");
  });

  it("recall step output preserved on ExecutionResult unchanged (iter 65 regression guard)", async () => {
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-language", value: "TypeScript",
      reason: "user pref",
    });
    const model = new FixedModelClient();
    const exec = new Executor({ memory, modelClient: model });
    const plan: AgentPlan = {
      taskId: "p6",
      steps: [RECALL_STEP_LANG, THINK_STEP],
    };
    const results = await exec.executeWithTask(plan, TASK);
    // Iter 65's shape MUST still hold: { key, value, found }.
    expect(results[0].output).toEqual({
      key: "pref-language",
      value: "TypeScript",
      found: true,
    });
  });

  it("think step still works when no memory wired at all (defensive)", async () => {
    const model = new FixedModelClient();
    // Note: no `memory` dep, no `recall` steps in plan.
    const exec = new Executor({ modelClient: model });
    const plan: AgentPlan = { taskId: "p7", steps: [THINK_STEP] };
    const results = await exec.executeWithTask(plan, TASK);
    expect(results[0].success).toBe(true);
    expect(model.lastPrompt).toBe(
      "summarize the user's preference\n\nUser input: what do I prefer?",
    );
  });
});
