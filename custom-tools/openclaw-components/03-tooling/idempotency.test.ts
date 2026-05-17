// Negative drills for Iter 16 (2026-05-17): ToolDispatcher idempotency.

import { describe, it, expect } from "vitest";
import { ToolRegistry } from "./tool-registry";
import { ToolDispatcher } from "./tool-dispatcher";
import { IdempotencyCache } from "./idempotency-cache";
import { Logger } from "./logger";
import { Telemetry } from "./telemetry";
import { ResponsibleAIGuard } from "./responsible-ai-guard";
import { ExplainabilityRecorder } from "./explainability-recorder";
import { ToolDefinition } from "./types";

/** Counter tool: increments and returns a per-instance counter so
 *  we can detect duplicate execution. */
function makeCounterTool(): { def: ToolDefinition; count: () => number } {
  let n = 0;
  return {
    count: () => n,
    def: {
      name: "counter",
      description: "counts invocations",
      riskLevel: "low",
      allowedRoles: ["user"],
      async execute() {
        n += 1;
        return { n };
      },
    },
  };
}

function buildDispatcher(extra?: IdempotencyCache) {
  const tool = makeCounterTool();
  const registry = new ToolRegistry();
  registry.register(tool.def);
  const dispatcher = new ToolDispatcher(
    registry,
    new Logger(),
    new Telemetry(),
    new ResponsibleAIGuard(),
    new ExplainabilityRecorder(),
    extra,
  );
  return { dispatcher, tool };
}

const baseCtx = {
  requestId: "r",
  sessionId: "s",
  userId: "u",
  tenantId: "tenant-A",
  roles: ["user"],
};

describe("ToolDispatcher — idempotency (P1)", () => {
  it("BACKDOOR CHECK: same idempotency key → second call replays cache, no re-execute", async () => {
    const { dispatcher, tool } = buildDispatcher();

    const first = await dispatcher.dispatch({
      toolName: "counter",
      input: {},
      context: baseCtx,
      idempotencyKey: "click-1",
    });
    const second = await dispatcher.dispatch({
      toolName: "counter",
      input: {},
      context: baseCtx,
      idempotencyKey: "click-1",
    });

    expect(first.success).toBe(true);
    expect(first.idempotentReplay).toBeUndefined();
    expect(second.success).toBe(true);
    expect(second.idempotentReplay).toBe(true);

    // Counter must have incremented EXACTLY ONCE despite two dispatches.
    expect(tool.count()).toBe(1);
    expect((second.output as { n: number }).n).toBe(1);
  });

  it("different idempotency keys → both execute", async () => {
    const { dispatcher, tool } = buildDispatcher();
    await dispatcher.dispatch({
      toolName: "counter", input: {}, context: baseCtx,
      idempotencyKey: "a",
    });
    await dispatcher.dispatch({
      toolName: "counter", input: {}, context: baseCtx,
      idempotencyKey: "b",
    });
    expect(tool.count()).toBe(2);
  });

  it("same key, DIFFERENT tenant → both execute (tenant-scoped cache)", async () => {
    const { dispatcher, tool } = buildDispatcher();
    await dispatcher.dispatch({
      toolName: "counter", input: {},
      context: { ...baseCtx, tenantId: "tenant-A" },
      idempotencyKey: "shared-key",
    });
    await dispatcher.dispatch({
      toolName: "counter", input: {},
      context: { ...baseCtx, tenantId: "tenant-B" },
      idempotencyKey: "shared-key",
    });
    // Per-tenant isolation: tenant-B must not replay tenant-A's result.
    expect(tool.count()).toBe(2);
  });

  it("no idempotency key → every call executes", async () => {
    const { dispatcher, tool } = buildDispatcher();
    await dispatcher.dispatch({
      toolName: "counter", input: {}, context: baseCtx,
    });
    await dispatcher.dispatch({
      toolName: "counter", input: {}, context: baseCtx,
    });
    expect(tool.count()).toBe(2);
  });

  it("failures are NOT cached (caller can retry)", async () => {
    // Tool that throws.
    let attempts = 0;
    const registry = new ToolRegistry();
    registry.register({
      name: "flaky",
      description: "fails first call, succeeds second",
      riskLevel: "low",
      allowedRoles: ["user"],
      async execute() {
        attempts += 1;
        if (attempts === 1) throw new Error("first-call fail");
        return { ok: true };
      },
    });
    const dispatcher = new ToolDispatcher(
      registry, new Logger(), new Telemetry(),
      new ResponsibleAIGuard(), new ExplainabilityRecorder(),
    );

    const r1 = await dispatcher.dispatch({
      toolName: "flaky", input: {}, context: baseCtx,
      idempotencyKey: "retry-me",
    });
    const r2 = await dispatcher.dispatch({
      toolName: "flaky", input: {}, context: baseCtx,
      idempotencyKey: "retry-me",
    });

    expect(r1.success).toBe(false);
    expect(r2.success).toBe(true);
    // Failure did NOT poison the cache.
    expect(r2.idempotentReplay).toBeUndefined();
    expect(attempts).toBe(2);
  });

  it("TTL expiry → cache miss after window", async () => {
    const cache = new IdempotencyCache(30 /* ttl ms */, 1000);
    const { dispatcher, tool } = buildDispatcher(cache);
    await dispatcher.dispatch({
      toolName: "counter", input: {}, context: baseCtx,
      idempotencyKey: "k",
    });
    await new Promise((r) => setTimeout(r, 50));
    await dispatcher.dispatch({
      toolName: "counter", input: {}, context: baseCtx,
      idempotencyKey: "k",
    });
    // TTL elapsed between calls, so the second one re-executed.
    expect(tool.count()).toBe(2);
  });
});
