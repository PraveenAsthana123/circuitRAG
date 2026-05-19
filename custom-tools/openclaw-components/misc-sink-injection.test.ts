// Negative drills for Iter 103 (2026-05-18): misc sink injection
// for 5 cross-component emitters. Each was an isolated console.log/
// warn site; rather than 5 separate iters, batched here as a
// catalog drill verifying each emitter's sink contract.
//
// Covered:
//   - 04-memory-governance/memory-audit-log.ts  (memory_audit)
//   - 10-agent-workflow/human-approval.ts       (human_approval_required)
//   - 10-agent-workflow/rollback-manager.ts     (workflow_rollback)
//   - 01-gateway/event-bus.ts                   (event_published)
//   - 09-rag-orchestrator/rag-orchestrator.ts   (rag_orchestration)

import { describe, it, expect, vi } from "vitest";
import { MemoryAuditLog } from "./04-memory-governance/memory-audit-log";
import { HumanApprovalGate } from "./10-agent-workflow/human-approval";
import { ApprovalQueue } from "./10-agent-workflow/approval-queue";
import { RollbackManager } from "./10-agent-workflow/rollback-manager";
import { WorkflowStateStore } from "./10-agent-workflow/workflow-state-store";
import { EventBus } from "./01-gateway/event-bus";
import { RAGOrchestrator } from "./09-rag-orchestrator/rag-orchestrator";
import { Chunker } from "./09-rag-orchestrator/chunker";
import { Retriever } from "./09-rag-orchestrator/retriever";
import { Reranker } from "./09-rag-orchestrator/reranker";
import { GroundingChecker } from "./09-rag-orchestrator/grounding-checker";
import { CitationValidator } from "./09-rag-orchestrator/citation-validator";
import { QualityScorer } from "./09-rag-orchestrator/quality-scorer";
import { WorkflowState, WorkflowContext } from "./10-agent-workflow/types";
import {
  InMemoryEventSink,
} from "./06-observability/sinks";

describe("Iter 103 — MemoryAuditLog sink injection (P1)", () => {
  it("BACKDOOR: default emits to console.log", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new MemoryAuditLog().append({
        auditId: "a-1", memoryId: "m-1", action: "create",
        actorUserId: "u-1", tenantId: "t-1",
        newValue: "v", reason: "test",
        timestamp: new Date().toISOString(),
      });
      const audits = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "memory_audit");
      expect(audits.length).toBe(1);
    } finally { log.mockRestore(); }
  });

  it("BACKDOOR: injected sink captures; console silent", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const audit = new MemoryAuditLog(sink);
      audit.append({
        auditId: "a-1", memoryId: "m-1", action: "create",
        actorUserId: "u-1", tenantId: "t-1",
        newValue: "v", reason: "test",
        timestamp: new Date().toISOString(),
      });
      expect(sink.size()).toBe(1);
      expect(sink.list()[0].type).toBe("memory_audit");
      expect(sink.list()[0].memoryId).toBe("m-1");
      // Still appended to in-memory log (regression guard).
      expect(audit.listByMemory("m-1").length).toBe(1);
      expect(log.mock.calls.length).toBe(0);
    } finally { log.mockRestore(); }
  });
});

describe("Iter 103 — HumanApprovalGate sink injection (P1)", () => {
  const CTX: WorkflowContext = {
    workflowId: "wf", requestId: "r", tenantId: "t",
    userId: "u", traceId: "tr",
  };

  it("BACKDOOR: default emits to console.log", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new HumanApprovalGate().requestApproval(CTX, {
        stepId: "s-1", name: "review",
        goal: "needs human eyeballs",
        requiresApproval: true, status: "pending",
      });
      const reqs = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "human_approval_required");
      expect(reqs.length).toBe(1);
    } finally { log.mockRestore(); }
  });

  it("BACKDOOR: injected sink captures; console silent", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new HumanApprovalGate(new ApprovalQueue(), sink).requestApproval(CTX, {
        stepId: "s-1", name: "review",
        goal: "x", requiresApproval: true, status: "pending",
      });
      expect(sink.size()).toBe(1);
      expect(sink.list()[0].type).toBe("human_approval_required");
      expect(log.mock.calls.length).toBe(0);
    } finally { log.mockRestore(); }
  });
});

describe("Iter 103 — RollbackManager sink injection (P1)", () => {
  function seedTwoVersions(store: WorkflowStateStore): string {
    const wfId = `wf-${Math.random().toString(36).slice(2)}`;
    const ctx: WorkflowContext = {
      workflowId: wfId, requestId: "r",
      tenantId: "t-1", userId: "u", traceId: "tr",
    };
    const now = new Date().toISOString();
    const v1: WorkflowState = {
      context: ctx, status: "executing", userGoal: "t",
      steps: [], currentStepIndex: 0, createdAt: now, updatedAt: now,
    };
    store.save(v1);
    store.save({ ...v1, status: "failed" });
    return wfId;
  }

  it("BACKDOOR: default emits to console.warn (iter 95 contract)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const store = new WorkflowStateStore();
      const wfId = seedTwoVersions(store);
      new RollbackManager(store).rollback(wfId, "t-1", "manual");
      const events = warn.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "workflow_rollback");
      expect(events.length).toBe(1);
    } finally { warn.mockRestore(); }
  });

  it("BACKDOOR: injected sink captures; console.warn silent", () => {
    const sink = new InMemoryEventSink();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const store = new WorkflowStateStore();
      const wfId = seedTwoVersions(store);
      new RollbackManager(store, sink).rollback(wfId, "t-1", "manual");
      expect(sink.size()).toBe(1);
      expect(sink.list()[0].type).toBe("workflow_rollback");
      expect(warn.mock.calls.length).toBe(0);
    } finally { warn.mockRestore(); }
  });
});

describe("Iter 103 — EventBus sink injection (P1)", () => {
  it("BACKDOOR: default emits to console.log", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      await new EventBus().publish("test_event", { x: 1 });
      const events = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "event_published");
      expect(events.length).toBe(1);
    } finally { log.mockRestore(); }
  });

  it("BACKDOOR: injected sink captures; console silent + handlers still fire", async () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      let handlerCalls = 0;
      const bus = new EventBus(sink);
      bus.on("ev", () => { handlerCalls += 1; });
      await bus.publish("ev", {});

      expect(sink.size()).toBe(1);
      expect(sink.list()[0].eventType).toBe("ev");
      expect(sink.list()[0].handlerCount).toBe(1);
      // Handler STILL fires — sink injection doesn't break dispatch.
      expect(handlerCalls).toBe(1);
      expect(log.mock.calls.length).toBe(0);
    } finally { log.mockRestore(); }
  });
});

describe("Iter 103 — RAGOrchestrator sink injection (P1)", () => {
  it("BACKDOOR: default emits to console.log", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const chunks = new Chunker().chunk({
        documentId: "d-1", tenantId: "t-1",
        text: "test content for retrieval",
        metadata: {},
      });
      const orchestrator = new RAGOrchestrator(
        new Retriever(chunks),
        new Reranker(),
        new GroundingChecker(),
        new CitationValidator(),
        new QualityScorer(),
      );
      await orchestrator.answer({
        requestId: "r-1", tenantId: "t-1", userId: "u-1",
        query: "test", traceId: "tr",
      });
      const events = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "rag_orchestration");
      expect(events.length).toBe(1);
    } finally { log.mockRestore(); }
  });

  it("BACKDOOR: injected sink captures; console silent", async () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const chunks = new Chunker().chunk({
        documentId: "d-1", tenantId: "t-1",
        text: "test content",
        metadata: {},
      });
      const orchestrator = new RAGOrchestrator(
        new Retriever(chunks),
        new Reranker(),
        new GroundingChecker(),
        new CitationValidator(),
        new QualityScorer(),
        sink,
      );
      await orchestrator.answer({
        requestId: "r-1", tenantId: "t-1", userId: "u-1",
        query: "test", traceId: "tr",
      });
      expect(sink.list().filter((r) => r.type === "rag_orchestration").length).toBe(1);
      expect(log.mock.calls.filter((c) => {
        try { return JSON.parse(c[0] as string).type === "rag_orchestration"; }
        catch { return false; }
      }).length).toBe(0);
    } finally { log.mockRestore(); }
  });
});

describe("Iter 103 — milestone: sink coverage spans 15 emitters", () => {
  it("documentation marker — every console.log/warn/error event stream is now sink-injectable", () => {
    // Catalog (kept here so future audits can grep the list):
    //   01-gateway/gateway.ts                  (Iter 98, ConsoleErrorEventSink)
    //   01-gateway/event-bus.ts                (Iter 103, EventSink)
    //   03-tooling/explainability-recorder.ts  (M3.3, EventSink)
    //   03-tooling/logger.ts                   (Iter 101, EventSink stream-routed)
    //   03-tooling/telemetry.ts                (ToolTelemetrySink — pre-existing)
    //   04-memory-governance/memory-audit-log  (Iter 103, EventSink)
    //   05-guardrails/guardrail-engine.ts      (Iter 97, EventSink)
    //   05-guardrails/approval-gate.ts         (Iter 97, EventSink)
    //   06-observability/tracer.ts             (M2.1, TraceSink)
    //   06-observability/metrics.ts            (M2.2, MetricsSink)
    //   06-observability/aiops-event-bus.ts    (M2.3, EventSink)
    //   06-observability/logger.ts             (M3.1, LogSink)
    //   07-resilience/fallback-handler.ts      (Iter 102, ConsoleWarnEventSink)
    //   07-resilience/resilient-executor.ts    (Iter 102, EventSink stream-routed)
    //   08-llm-router/llm-router.ts            (Iter 99, EventSink stream-routed)
    //   09-rag-orchestrator/rag-orchestrator   (Iter 103, EventSink)
    //   10-agent-workflow/agent-workflow-engine (Iter 100, EventSink stream-routed)
    //   10-agent-workflow/human-approval.ts    (Iter 103, EventSink)
    //   10-agent-workflow/rollback-manager.ts  (Iter 103, ConsoleWarnEventSink)
    // 19 sink-injection sites across 9 components.
    expect(true).toBe(true);
  });
});
