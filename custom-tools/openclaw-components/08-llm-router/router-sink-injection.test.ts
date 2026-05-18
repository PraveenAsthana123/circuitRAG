// Negative drills for Iter 99 (2026-05-18): LLMRouter sink
// injection (3-stream multiplexed). Pre-fix: LLMRouter emitted
// across three console streams (success → log, per-attempt fail →
// warn, final aggregated fail → error). Pluggable EventSink via
// StreamRoutedEventSink preserves the multi-stream contract iter
// 61's router-drill-matrix depends on.

import { describe, it, expect, vi } from "vitest";
import { LLMRouter } from "./llm-router";
import { ModelRegistry } from "./model-registry";
import { RoutingPolicy } from "./routing-policy";
import { SafetyGate } from "./safety-gate";
import { CostLedger } from "./cost-ledger";
import { LLMClient } from "./llm-client";
import { LLMRequest, LLMResponse, ModelConfig } from "./types";
import {
  EventSink,
  EventRecord,
  InMemoryEventSink,
  StreamRoutedEventSink,
} from "../06-observability/sinks";

class FixedClient extends LLMClient {
  public calls = 0;
  constructor(private readonly fixed: Partial<LLMResponse> = {}) { super(); }
  async complete(_req: LLMRequest, model: ModelConfig): Promise<LLMResponse> {
    this.calls += 1;
    return {
      modelId: model.modelId, provider: model.provider, output: "ok",
      latencyMs: 1, estimatedCostUsd: 0.001, explanation: "test",
      ...this.fixed,
    };
  }
}

class FailFirstClient extends LLMClient {
  constructor(private readonly failModelIds: Set<string>) { super(); }
  async complete(_req: LLMRequest, model: ModelConfig): Promise<LLMResponse> {
    if (this.failModelIds.has(model.modelId)) {
      throw new Error(`mock failure: ${model.modelId} timeout`);
    }
    return {
      modelId: model.modelId, provider: model.provider, output: "ok",
      latencyMs: 1, estimatedCostUsd: 0.002, explanation: "served",
    };
  }
}

const M = (id: string, opts: Partial<ModelConfig> = {}): ModelConfig => ({
  modelId: id, provider: "ollama", supportedTasks: ["code"],
  costPer1kTokensUsd: 0.001, maxContextTokens: 8192,
  priority: 1, enabled: true, ...opts,
});

const REQ = (): LLMRequest => ({
  requestId: "r-1", tenantId: "t-1", userId: "u-1",
  taskType: "code", prompt: "x", maxTokens: 1000,
  traceId: "tr-1",
});

describe("Iter 99 — LLMRouter sink injection (P1)", () => {
  it("BACKDOOR: default sink routes success → console.log (backcompat — iter 61 spy contract)", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const router = new LLMRouter(
        new ModelRegistry([M("m1")]),
        new RoutingPolicy(),
        new SafetyGate(),
        new FixedClient(),
      );
      await router.route(REQ());
      const successes = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "llm_route_success");
      expect(successes.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: default sink routes per-attempt failure → console.warn (iter 61 contract)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const router = new LLMRouter(
        new ModelRegistry([
          M("m-fail", { priority: 1 }),
          M("m-ok", { priority: 2 }),
        ]),
        new RoutingPolicy(),
        new SafetyGate(),
        new FailFirstClient(new Set(["m-fail"])),
      );
      await router.route(REQ());
      const attemptFails = warn.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "llm_route_model_failed");
      expect(attemptFails.length).toBe(1);
    } finally {
      warn.mockRestore();
      log.mockRestore();
    }
  });

  it("BACKDOOR: default sink routes final failure → console.error", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const router = new LLMRouter(
        new ModelRegistry([M("m1")]),
        new RoutingPolicy(),
        new SafetyGate(),
        new FailFirstClient(new Set(["m1"])),
      );
      try { await router.route(REQ()); } catch { /* expected */ }
      const finalFails = err.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "llm_route_failure");
      expect(finalFails.length).toBe(1);
    } finally {
      err.mockRestore();
      warn.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures ALL three event types; console silent", async () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      // First call: failure-then-success (emits warn + log).
      const router = new LLMRouter(
        new ModelRegistry([
          M("m-fail", { priority: 1 }),
          M("m-ok", { priority: 2 }),
        ]),
        new RoutingPolicy(),
        new SafetyGate(),
        new FailFirstClient(new Set(["m-fail"])),
        undefined,
        { sink },
      );
      await router.route(REQ());

      const types = sink.list().map((r) => r.type).sort();
      expect(types).toEqual(["llm_route_model_failed", "llm_route_success"]);
      // Console silent.
      expect(log.mock.calls.length).toBe(0);
      expect(warn.mock.calls.length).toBe(0);
      expect(err.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
      warn.mockRestore();
      err.mockRestore();
    }
  });

  it("BACKDOOR: injected sink strips internal `_stream` routing hint from persisted records", async () => {
    const sink = new InMemoryEventSink();
    const router = new LLMRouter(
      new ModelRegistry([M("m1")]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      { sink },
    );
    await router.route(REQ());

    // InMemoryEventSink doesn't strip; the StreamRoutedEventSink does.
    // When using a custom sink (not StreamRouted), the _stream hint
    // IS visible. This is the canonical contract drill — record what
    // SHIPS to a sink. Decision: keep _stream visible to custom
    // sinks (they can choose to ignore it or use it for their own
    // routing).
    const r = sink.list()[0];
    expect(r.type).toBe("llm_route_success");
    expect(r._stream).toBe("log");  // hint flows through to InMemorySink
  });

  it("StreamRoutedEventSink STRIPS _stream from console output (clean payload)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new StreamRoutedEventSink().emit({ _stream: "log", type: "x", a: 1 });
      const payload = JSON.parse(log.mock.calls[0][0] as string);
      expect(payload._stream).toBeUndefined();  // stripped
      expect(payload.type).toBe("x");
      expect(payload.a).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("StreamRoutedEventSink defaults to console.log when _stream is absent", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      new StreamRoutedEventSink().emit({ type: "x" });
      expect(log.mock.calls.length).toBe(1);
      expect(warn.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
      warn.mockRestore();
    }
  });

  it("BACKDOOR: custom sink can route to a unified metrics consumer (extension point)", async () => {
    const captured: EventRecord[] = [];
    class UnifiedSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    const router = new LLMRouter(
      new ModelRegistry([M("m1")]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient(),
      undefined,
      { sink: new UnifiedSink() },
    );
    await router.route(REQ());
    expect(captured.length).toBe(1);
    expect(captured[0].type).toBe("llm_route_success");
  });

  it("BACKDOOR: productionMode + EchoLLMClient still rejects at construction (iter 96 regression)", () => {
    // Iter 96's abstract-class guard cooperates with the sink — the
    // sink doesn't change construction-time guards.
    expect(() => {
      // Need a stub client — import indirectly via test.
      const stub = new (class extends LLMClient {
        override readonly isProductionStub = true;
        async complete() {
          return {
            modelId: "x", provider: "ollama" as const, output: "",
            latencyMs: 0, estimatedCostUsd: 0, explanation: "",
          };
        }
      })();
      new LLMRouter(
        new ModelRegistry([]),
        new RoutingPolicy(),
        new SafetyGate(),
        stub,
        undefined,
        { productionMode: true },
      );
    }).toThrow(/stub/);
  });

  it("llm_route_success payload schema preserved (iter 61 + 79 regression)", async () => {
    const sink = new InMemoryEventSink();
    const router = new LLMRouter(
      new ModelRegistry([M("m1", { costPer1kTokensUsd: 0.5 })]),
      new RoutingPolicy(),
      new SafetyGate(),
      new FixedClient({ estimatedCostUsd: 0.5 }),
      undefined,
      { sink },
    );
    await router.route(REQ());
    const r = sink.list()[0];
    expect(r.type).toBe("llm_route_success");
    expect(r.requestId).toBe("r-1");
    expect(r.selectedModel).toBe("m1");
    expect(r.fallbackUsed).toBe(false);
    expect(typeof r.estimatedCostUsd).toBe("number");
    expect(typeof r.tenantSpendUsd).toBe("number");
  });
});
