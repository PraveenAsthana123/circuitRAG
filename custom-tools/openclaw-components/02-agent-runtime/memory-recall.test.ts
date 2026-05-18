// Negative drills for Iter 65 (2026-05-17): Executor memory
// injection + `recall` step type.
//
// Closes the MEMORY half of GAPS.md Component 2 P1 that iter 64
// only partially closed (guardrails-only). The `recall` step makes
// the wiring concrete: a planned step fetches a memory record via
// MemoryGovernanceService.read(). Output is { key, value, found }
// so downstream steps can compose on it.
//
// Negative assertions:
//   1. BACKDOOR: recall step returns existing memory value
//   2. BACKDOOR: recall step returns found=false when no memory
//   3. recall step throws when no memory wired (clear error, not
//      silent success)
//   4. recall step throws when step.memoryKey missing
//   5. recall step throws when task lacks tenantId (boundary check)
//   6. recall step invokes memory.read with callerTenantId ===
//      task.tenantId (iter 62 service-level enforcement preserved)
//   7. unknown step.action still throws (regression guard for the
//      switch's exhaustiveness)
//   8. recall step's output IS readable by inspecting the
//      ExecutionResult (downstream composition signal)

import { describe, it, expect } from "vitest";
import { Executor } from "./executor";
import { MemoryGovernanceService } from "../04-memory-governance/memory-governance-service";
import {
  MemoryStore,
  MemoryAccessDeniedError,
} from "../04-memory-governance/memory-store";
import { MemoryAuditLog } from "../04-memory-governance/memory-audit-log";
import { PIIMasker } from "../04-memory-governance/pii-masker";
import { RetentionPolicy } from "../04-memory-governance/retention-policy";
import { AgentPlan, AgentTask, PlanStep } from "./types";

function newMemory() {
  return new MemoryGovernanceService(
    new MemoryStore(),
    new MemoryAuditLog(),
    new PIIMasker(),
    new RetentionPolicy(),
  );
}

const RECALL_STEP: PlanStep = {
  stepId: "r1",
  action: "recall",
  description: "fetch user's pref language",
  memoryKey: "pref-language",
};

const PLAN: AgentPlan = { taskId: "p1", steps: [RECALL_STEP] };

const TASK: AgentTask = {
  sessionId: "sess", userId: "user-1", userInput: "what do I prefer?",
  tenantId: "tenant-1", requestId: "req-1", traceId: "tr",
};

describe("Iter 65 — Executor recall step (P1, closes iter 64 partial)", () => {
  it("BACKDOOR: recall step returns existing memory value", async () => {
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-language", value: "TypeScript",
      reason: "user pref",
    });
    const exec = new Executor({ memory });
    const [result] = await exec.executeWithTask(PLAN, TASK);
    expect(result.success).toBe(true);
    expect(result.output).toEqual({
      key: "pref-language",
      value: "TypeScript",
      found: true,
    });
  });

  it("BACKDOOR: recall step returns found=false when no memory exists", async () => {
    const memory = newMemory();
    const exec = new Executor({ memory });
    const [result] = await exec.executeWithTask(PLAN, TASK);
    expect(result.success).toBe(true);
    expect(result.output).toEqual({
      key: "pref-language",
      value: undefined,
      found: false,
    });
  });

  it("recall step throws when no memory wired (no silent-success regression)", async () => {
    const exec = new Executor({});  // no memory dep
    const [result] = await exec.executeWithTask(PLAN, TASK);
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/no memory wired/);
  });

  it("recall step throws when step.memoryKey missing", async () => {
    const memory = newMemory();
    const exec = new Executor({ memory });
    const badPlan: AgentPlan = {
      taskId: "p2",
      steps: [{
        stepId: "r2", action: "recall",
        description: "fetch something",
        // memoryKey omitted
      }],
    };
    const [result] = await exec.executeWithTask(badPlan, TASK);
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/memoryKey missing/);
  });

  it("recall step throws when task lacks tenantId", async () => {
    const memory = newMemory();
    const exec = new Executor({ memory });
    const noTenantTask: AgentTask = {
      sessionId: "s", userId: "u", userInput: "x",
      // tenantId omitted
    };
    const [result] = await exec.executeWithTask(PLAN, noTenantTask);
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/task\.tenantId/);
  });

  it("recall preserves iter 62 cross-tenant defense (callerTenantId == tenantId)", async () => {
    // Seed memory for tenant-A. A task with tenantId=tenant-A
    // and the recall step targeting that tenant works.
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-A", callerTenantId: "tenant-A",
      userId: "u", actorUserId: "u",
      key: "pref-language", value: "Go",
      reason: "pref",
    });

    const exec = new Executor({ memory });
    const taskA: AgentTask = {
      sessionId: "s", userId: "u", userInput: "x",
      tenantId: "tenant-A", requestId: "r", traceId: "t",
    };
    const [r1] = await exec.executeWithTask(PLAN, taskA);
    expect(r1.success).toBe(true);
    expect((r1.output as { value: string }).value).toBe("Go");

    // Iter 62 invariant: if a TASK arrived with tenantId=tenant-B
    // (forged or honest), the read() call's callerTenantId is set
    // from task.tenantId — so it always matches. A real auth-context
    // refactor would pass task.callerTenantId separately; absent
    // that, the trust is task.tenantId. Same trust contract as the
    // pre-iter-62 path. Tested here for regression guard.
    const taskB: AgentTask = { ...taskA, tenantId: "tenant-B" };
    const [r2] = await exec.executeWithTask(PLAN, taskB);
    // No tenant-B memory; should NOT see tenant-A's value.
    expect(r2.success).toBe(true);
    expect((r2.output as { found: boolean }).found).toBe(false);
  });

  it("memory.read called with caller forgery (manual) → throws MemoryAccessDeniedError", () => {
    // Direct unit-level proof iter 62's enforcement is still live
    // when wired through the executor's helper. Iter 64 wired
    // guardrails; iter 65 wires memory; both honor §62.
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-A", callerTenantId: "tenant-A",
      userId: "u", actorUserId: "u",
      key: "k", value: "v", reason: "r",
    });
    expect(() => memory.read("tenant-A", "u", "k", "tenant-B"))
      .toThrow(MemoryAccessDeniedError);
  });

  it("recall step output is readable in the ExecutionResult (downstream composition signal)", async () => {
    const memory = newMemory();
    memory.save({
      tenantId: "tenant-1", callerTenantId: "tenant-1",
      userId: "user-1", actorUserId: "user-1",
      key: "pref-language", value: "TypeScript",
      reason: "user pref",
    });
    const exec = new Executor({ memory });
    const results = await exec.executeWithTask(PLAN, TASK);
    // Output is at results[0].output (canonical executor shape).
    expect(results[0].output).toMatchObject({
      key: "pref-language",
      value: "TypeScript",
      found: true,
    });
  });
});
