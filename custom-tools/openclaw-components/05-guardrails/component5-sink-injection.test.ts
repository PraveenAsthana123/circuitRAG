// Negative drills for Iter 97 (2026-05-18): Component 5 sink
// injection (GuardrailEngine + ApprovalGate). Completes sink-
// coverage for the security-audit emission paths. Both emitters
// reuse EventSink from M2.3 — opaque event-shaped JSON; the
// canonical-field contract stays with the emitter (iter 85 + 87
// schema-fingerprint drills).

import { describe, it, expect, vi } from "vitest";
import { GuardrailEngine } from "./guardrail-engine";
import { ApprovalGate } from "./approval-gate";
import { PIIDetector } from "./pii-detector";
import { PromptInjectionDetector } from "./prompt-injection-detector";
import { PolicyEngine } from "./policy-engine";
import {
  InMemoryEventSink,
  EventSink,
  EventRecord,
} from "../06-observability/sinks";
import { GuardrailResult } from "./types";

const CTX = {
  requestId: "r-1", sessionId: "s-1", userId: "u-1",
  tenantId: "t-1", traceId: "tr-1",
};

const REVIEW: GuardrailResult = {
  decision: "review",
  findings: [{ ruleId: "INPUT_PII_EMAIL", severity: "medium", message: "email" }],
  explanation: "review",
};

describe("Iter 97 — Component 5 sink injection (P1)", () => {
  it("BACKDOOR: GuardrailEngine default sink emits to console (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const engine = new GuardrailEngine(
        new PIIDetector(),
        new PromptInjectionDetector(),
        new PolicyEngine(),
        new ApprovalGate(),
      );
      engine.evaluateRequest({ inputText: "clean text", context: CTX });
      const evalLogs = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "guardrail_evaluation");
      expect(evalLogs.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: GuardrailEngine injected sink captures; console silent for guardrail_evaluation", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const engine = new GuardrailEngine(
        new PIIDetector(),
        new PromptInjectionDetector(),
        new PolicyEngine(),
        new ApprovalGate(),
        sink,
      );
      engine.evaluateRequest({ inputText: "clean", context: CTX });
      engine.evaluateResponse("clean", CTX);

      const evals = sink.list().filter((r) => r.type === "guardrail_evaluation");
      expect(evals.length).toBe(2);
      expect(evals[0].side).toBe("input");
      expect(evals[1].side).toBe("output");
      // No guardrail_evaluation logs went to console.
      const evalLogs = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "guardrail_evaluation");
      expect(evalLogs.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: ApprovalGate default sink emits to console", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ApprovalGate().createApprovalTicket(REVIEW);
      const ticketLogs = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "approval_ticket");
      expect(ticketLogs.length).toBe(1);
    } finally {
      log.mockRestore();
    }
  });

  it("BACKDOOR: ApprovalGate injected sink captures; console silent for approval_ticket", () => {
    const sink = new InMemoryEventSink();
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      const id = new ApprovalGate(sink).createApprovalTicket(REVIEW);
      expect(sink.size()).toBe(1);
      expect(sink.list()[0].type).toBe("approval_ticket");
      expect(sink.list()[0].ticketId).toBe(id);

      const ticketLogs = log.mock.calls
        .map((c) => JSON.parse(c[0] as string))
        .filter((p) => p.type === "approval_ticket");
      expect(ticketLogs.length).toBe(0);
    } finally {
      log.mockRestore();
    }
  });

  it("guardrail_evaluation payload schema preserved through sink (iter 85 regression)", () => {
    const sink = new InMemoryEventSink();
    const engine = new GuardrailEngine(
      new PIIDetector(),
      new PromptInjectionDetector(),
      new PolicyEngine(),
      new ApprovalGate(),
      sink,
    );
    engine.evaluateRequest({
      inputText: "user email: alice@example.com",
      context: CTX,
    });
    const r = sink.list()[0];
    expect(r.type).toBe("guardrail_evaluation");
    expect(r.side).toBe("input");
    expect(r.requestId).toBe("r-1");
    expect(r.tenantId).toBe("t-1");
    expect(r.decision).toBeDefined();
    expect(typeof r.findingCount).toBe("number");
    expect(typeof r.durationMs).toBe("number");
    expect(typeof r.timestamp).toBe("string");
  });

  it("approval_ticket payload schema preserved through sink (iter 87 regression)", () => {
    const sink = new InMemoryEventSink();
    new ApprovalGate(sink).createApprovalTicket(REVIEW);
    const r = sink.list()[0];
    const keys = Object.keys(r).sort();
    expect(keys).toEqual(
      ["decision", "findings", "ticketId", "timestamp", "type"].sort(),
    );
  });

  it("each createApprovalTicket call produces unique ticketId in sink (regression)", () => {
    const sink = new InMemoryEventSink();
    const gate = new ApprovalGate(sink);
    const a = gate.createApprovalTicket(REVIEW);
    const b = gate.createApprovalTicket(REVIEW);
    expect(a).not.toBe(b);
    expect(sink.size()).toBe(2);
    expect(sink.list()[0].ticketId).toBe(a);
    expect(sink.list()[1].ticketId).toBe(b);
  });

  it("custom sink routes both emitters' payloads (extension point)", () => {
    // A real DecisionAuditStoreSink would receive guardrail
    // evaluations + approval tickets through the same interface.
    const captured: EventRecord[] = [];
    class AuditSink implements EventSink {
      emit(r: EventRecord): void { captured.push(r); }
    }
    const sink = new AuditSink();
    const gate = new ApprovalGate(sink);
    const engine = new GuardrailEngine(
      new PIIDetector(),
      new PromptInjectionDetector(),
      new PolicyEngine(),
      gate,
      sink,
    );
    engine.evaluateRequest({ inputText: "clean", context: CTX });
    gate.createApprovalTicket(REVIEW);

    expect(captured.length).toBe(2);
    expect(captured[0].type).toBe("guardrail_evaluation");
    expect(captured[1].type).toBe("approval_ticket");
  });

  it("GuardrailEngine emits even when zero findings (regression — decision: allow + finding count 0)", () => {
    const sink = new InMemoryEventSink();
    const engine = new GuardrailEngine(
      new PIIDetector(),
      new PromptInjectionDetector(),
      new PolicyEngine(),
      new ApprovalGate(),
      sink,
    );
    engine.evaluateRequest({ inputText: "totally benign", context: CTX });
    expect(sink.size()).toBe(1);
    expect(sink.list()[0].decision).toBe("allow");
    expect(sink.list()[0].findingCount).toBe(0);
  });

  it("emission single-line JSON contract preserved (log-shipper safety regression)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    try {
      new ApprovalGate().createApprovalTicket(REVIEW);
      const ticketLog = log.mock.calls.find((c) => {
        const p = JSON.parse(c[0] as string);
        return p.type === "approval_ticket";
      });
      expect(ticketLog).toBeDefined();
      expect((ticketLog![0] as string)).not.toContain("\n");
    } finally {
      log.mockRestore();
    }
  });
});
