// Negative drills for Iter 100 (2026-05-18): Workflow engine
// lifecycle sink injection. 4 emission types (workflow_started →
// log, workflow_step_started → log, workflow_step_retry → warn,
// workflow_abandoned → warn). Default StreamRoutedEventSink
// preserves multi-stream console contract iter 54/57/58/66/67
// drills depend on.

import { describe, it, expect, vi } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import {
  EventSink,
  EventRecord,
  InMemoryEventSink,
} from "../06-observability/sinks";
import { WorkflowContext } from "./types";

const CTX: WorkflowContext = {
  workflowId: "wf-lifecycle", requestId: "r",
  tenantId: "t", userId: "u", traceId: "tr",
};

function newEngine(lifecycleSink?: EventSink): {
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
    lifecycleSink ? { lifecycleSink } : {},
  );
  return { engine, store };
}

describe("Iter 100 — Workflow engine lifecycle sink injection (P1)", () => {
  it("BACKDOOR: default routes workflow_started → console.log (iter 54 contract)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const { engine } = newEngine();
      engine.start({ ...CTX, workflowId: "wf-1" }, "test");
      const started = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "workflow_started");
      expect(started.length).toBe(1);
      expect(started[0].workflowId).toBe("wf-1");
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: default routes workflow_step_started → console.log", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const { engine } = newEngine();
      const wf = engine.start({ ...CTX, workflowId: "wf-2" }, "test");
      await engine.runNext(wf.context.workflowId, "t");
      const stepStarted = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "workflow_step_started");
      expect(stepStarted.length).toBeGreaterThanOrEqual(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures ALL lifecycle events; console silent", async () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const { engine } = newEngine(sink);
      const wf = engine.start({ ...CTX, workflowId: "wf-3" }, "test");
      await engine.runNext(wf.context.workflowId, "t");

      const types = sink.list().map((r) => r.type);
      expect(types).toContain("workflow_started");
      expect(types).toContain("workflow_step_started");
      // Console silent for ALL lifecycle events.
      const lifecycleLogs = log.mock.calls.filter((c) => {
        const p = JSON.parse(c[0] as string);
        return p.type === "workflow_started" || p.type === "workflow_step_started";
      });
      expect(lifecycleLogs.length).toBe(0);
      const lifecycleWarns = warn.mock.calls.filter((c) => {
        const p = JSON.parse(c[0] as string);
        return p.type === "workflow_step_retry" || p.type === "workflow_abandoned";
      });
      expect(lifecycleWarns.length).toBe(0);
    } finally {
      log.mockRestore();
      warn.mockRestore();
    }
  });

  it("BACKDOOR: workflow_started payload schema preserved (iter 54 regression)", () => {
    const sink = new InMemoryEventSink();
    const { engine } = newEngine(sink);
    engine.start({ ...CTX, workflowId: "wf-4" }, "test goal");
    const r = sink.list().find((x) => x.type === "workflow_started");
    expect(r).toBeDefined();
    expect(r!.workflowId).toBe("wf-4");
    expect(r!.requestId).toBe("r");
    expect(r!.tenantId).toBe("t");
    expect(typeof r!.stepCount).toBe("number");
    expect(r!.traceId).toBe("tr");
    expect(typeof r!.timestamp).toBe("string");
  });

  it("workflow_step_started payload schema preserved (regression)", async () => {
    const sink = new InMemoryEventSink();
    const { engine } = newEngine(sink);
    const wf = engine.start({ ...CTX, workflowId: "wf-5" }, "test");
    await engine.runNext(wf.context.workflowId, "t");
    const r = sink.list().find((x) => x.type === "workflow_step_started");
    expect(r).toBeDefined();
    expect(r!.workflowId).toBe("wf-5");
    expect(typeof r!.stepId).toBe("string");
    expect(typeof r!.stepName).toBe("string");
    expect(typeof r!.selectedTool).toBe("string");
  });

  it("custom sink routes ALL 4 lifecycle event types (extension point)", async () => {
    const captured: EventRecord[] = [];
    class UnifiedSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    const { engine } = newEngine(new UnifiedSink());
    const wf = engine.start({ ...CTX, workflowId: "wf-6" }, "test");
    await engine.runNext(wf.context.workflowId, "t");

    const types = captured.map((r) => r.type);
    expect(types).toContain("workflow_started");
    expect(types).toContain("workflow_step_started");
    // workflow_step_retry + workflow_abandoned only fire on failure
    // paths exercised in iter 57/58/67 drills.
  });

  it("custom sink sees _stream hint when not using StreamRoutedEventSink", () => {
    const captured: EventRecord[] = [];
    class HintSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    const { engine } = newEngine(new HintSink());
    engine.start({ ...CTX, workflowId: "wf-hint" }, "test");
    // workflow_started uses _stream: "log"
    expect(captured[0]._stream).toBe("log");
  });

  it("backcompat: existing iter 54 spy pattern still works (no injection)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const { engine } = newEngine();
      engine.start({ ...CTX, workflowId: "wf-bc" }, "test");
      // Iter 54-style spy: parse console.log calls, filter by type.
      const started = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .find((p) => p.type === "workflow_started");
      expect(started).toBeDefined();
      expect(started.workflowId).toBe("wf-bc");
    } finally {
      log.mockRestore();
    }
  });

  it("StreamRoutedEventSink strips _stream from console-routed payloads", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const { engine } = newEngine();  // default StreamRoutedEventSink
      engine.start({ ...CTX, workflowId: "wf-strip" }, "test");
      const payload = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .find((p) => p.type === "workflow_started");
      expect(payload).toBeDefined();
      expect(payload._stream).toBeUndefined();  // stripped by StreamRoutedEventSink
    } finally {
      log.mockRestore();
    }
  });

  it("single-line JSON contract preserved on every lifecycle emission", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const { engine } = newEngine();
      engine.start({ ...CTX, workflowId: "wf-line" }, "test");
      for (const call of log.mock.calls) {
        expect((call[0] as string)).not.toContain("\n");
      }
    } finally {
      log.mockRestore();
    }
  });
});
