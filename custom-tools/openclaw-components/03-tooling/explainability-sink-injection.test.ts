// Negative drills for M3.3 (2026-05-18): ExplainabilityRecorder
// sink injection. Reuses EventSink (from M2.3) since explainability
// emissions are opaque event-shaped JSON. Pre-fix:
// recordDecision() called console.log directly, blocking the
// path to a real DecisionAuditStoreSink (Postgres append-only per
// CLAUDE.md §38 audit row schema).

import { describe, it, expect, vi } from "vitest";
import { ExplainabilityRecorder } from "./explainability-recorder";
import { ToolRequest, ToolResult } from "./types";
import {
  EventSink,
  EventRecord,
  InMemoryEventSink,
} from "../06-observability/sinks";

const REQ: ToolRequest = {
  toolName: "calculator",
  input: { expression: "1+1" },
  context: {
    requestId: "r-1", sessionId: "s-1", userId: "u-1",
    tenantId: "t-1", traceId: "tr-1",
  },
};
const OK: ToolResult = { success: true, output: { result: 2 }, durationMs: 5 };

describe("M3.3 — ExplainabilityRecorder sink injection (P1)", () => {
  it("BACKDOOR: default sink emits to console (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ExplainabilityRecorder().recordDecision(REQ, OK, "passed");
      expect(log.mock.calls.length).toBe(1);
      const p = JSON.parse(log.mock.calls[0][0] as string);
      expect(p.type).toBe("explainability");
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: injected sink captures; console silent", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ExplainabilityRecorder(sink).recordDecision(REQ, OK, "passed");
      expect(sink.size()).toBe(1);
      expect(sink.list()[0].type).toBe("explainability");
      expect(sink.list()[0].toolName).toBe("calculator");
      expect(log.mock.calls.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: payload schema preserved through sink (regression iter 78)", () => {
    const sink = new InMemoryEventSink();
    new ExplainabilityRecorder(sink).recordDecision(REQ, OK, "passed");
    const r = sink.list()[0];
    const keys = Object.keys(r).sort();
    expect(keys).toEqual(
      ["durationMs", "reason", "requestId", "sessionId", "success", "timestamp", "toolName", "type"].sort(),
    );
  });

  it("failure result captured through sink (regression iter 78)", () => {
    const fail: ToolResult = { success: false, error: "blew up", durationMs: 1 };
    const sink = new InMemoryEventSink();
    new ExplainabilityRecorder(sink).recordDecision(REQ, fail, "policy denial");
    expect(sink.list()[0].success).toBe(false);
    expect(sink.list()[0].reason).toBe("policy denial");
  });

  it("does NOT leak request input via sink (iter 78 privacy contract preserved)", () => {
    const sink = new InMemoryEventSink();
    const sensitive: ToolRequest = {
      ...REQ, input: { ssn: "123-45-6789", email: "user@example.com" },
    };
    new ExplainabilityRecorder(sink).recordDecision(sensitive, OK, "ok");
    const raw = JSON.stringify(sink.list()[0]);
    expect(raw).not.toContain("123-45-6789");
    expect(raw).not.toContain("user@example.com");
  });

  it("does NOT leak tool output via sink (iter 78 privacy contract)", () => {
    const sink = new InMemoryEventSink();
    const sensitive: ToolResult = {
      success: true, output: { creditCard: "4111111111111111" }, durationMs: 5,
    };
    new ExplainabilityRecorder(sink).recordDecision(REQ, sensitive, "ok");
    expect(JSON.stringify(sink.list()[0])).not.toContain("4111111111111111");
  });

  it("custom sink can route to a decision-audit store (extension point regression)", () => {
    // A DecisionAuditStoreSink (future) implementing EventSink would
    // append every record to a Postgres audit table. Drill that
    // arbitrary sinks plug in.
    const captured: EventRecord[] = [];
    class AuditSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    new ExplainabilityRecorder(new AuditSink()).recordDecision(REQ, OK, "audited");
    expect(captured.length).toBe(1);
    expect(captured[0].reason).toBe("audited");
  });

  it("multiple recordDecision calls accumulate in sink (regression — no batching/dedup)", () => {
    const sink = new InMemoryEventSink();
    const rec = new ExplainabilityRecorder(sink);
    rec.recordDecision(REQ, OK, "first");
    rec.recordDecision(REQ, OK, "second");
    rec.recordDecision(REQ, OK, "third");
    expect(sink.size()).toBe(3);
    expect(sink.list().map((r) => r.reason)).toEqual(["first", "second", "third"]);
  });
});
